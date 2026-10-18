// BG3 Icon Editor (Phase 7, D46). The drawing is a list of items: game strokes (bitmaps cut once by iconkit.editor) and
// vector strokes (app/brush.js: path + settings, re-rendered when either changes). Each item has an affine matrix and a
// list of eraser strokes (non-destructive). Every edit recomposes the grey line art (strokes merge as a union, like the
// game's single drawing) and repaints it on the GPU (glow.js); the PC hotbar cell and the export go through Python.
import {Painter} from "./glow.js";
import * as Brush from "./brush.js";
import {vectorize, match, barbDensity, barbs} from "./vectorize.js";

const N = 512, $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
let statusTimer = 0;
function status(t, kind = "") { const s = $("#status"); s.textContent = t; s.className = kind; clearTimeout(statusTimer); if (kind) statusTimer = setTimeout(() => s.className = "", 4000); }
const get = u => fetch(u).catch(() => new Promise(ok => setTimeout(ok, 500)).then(() => fetch(u)));   // one retry on a dropped connection
const getJSON = async u => { const r = await get(u); if (!r.ok) throw new Error(`${u}: ${r.status}`); return r.json(); };
async function post(u, body) {
  const req = () => fetch(u, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const r = await req().catch(() => new Promise(ok => setTimeout(ok, 500)).then(req));   // one retry on a dropped connection
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || r.status);
  return j;
}
function canvas(w, h = w) { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; }
const ctx2d = c => c.getContext("2d", {willReadFrequently: true});
const store = {get: (k, d) => { try { const v = localStorage.getItem("bg3ie." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
               set: (k, v) => { try { localStorage.setItem("bg3ie." + k, JSON.stringify(v)); } catch { /* private mode */ } }};
const Q = new URLSearchParams(location.search), GOLDEN = Q.has("golden"), BRUSHTEST = Q.has("brushtest"), PERFTEST = Q.has("perftest");
if (PERFTEST) addEventListener("error", e => fetch("/api/perf", {method: "POST", headers: {"Content-Type": "application/json"},   // headless runs: say why it stopped
  body: JSON.stringify({mode: "load", browser: navigator.userAgent, error: String(e.message)})}));
// start-up: the #boot screen names the current step (with a seconds count once it takes a while) and any failure;
// start-up times (ms since navigation) go to the server's log (and perf.json when slow or with /?boottest)
const BOOT = {module: Math.round(performance.now())}, mark = k => BOOT[k] = Math.round(performance.now());
let bootMsg = "";
const bootTick = setInterval(() => { const s = performance.now() / 1000; if (s > 3) $("#bootMsg").textContent = `${bootMsg} ${Math.round(s)} s`; }, 1000);
const bootStep = t => $("#bootMsg").textContent = bootMsg = t;
function bootDone() { clearInterval(bootTick); $("#boot").classList.add("done"); setTimeout(() => $("#boot").remove(), 250); }
function bootFail(e) {
  const b = $("#boot");
  if (!b || b.classList.contains("done")) return;
  clearInterval(bootTick); b.classList.add("err");
  $("#bootMsg").textContent = `The editor couldn't start: ${e.reason?.message || e.message || e.reason}. The terminal window has the details. Reload the page to try again.`;
}
addEventListener("error", bootFail); addEventListener("unhandledrejection", bootFail);
bootStep("Loading icons and shapes…");

// ---------------------------------------------------------------- data
const [R, IDX, PARTS_J, META0] = await Promise.all([getJSON("/api/recipes"), getJSON("/data/editor/index.json"),
  getJSON("/data/editor/parts.json"), post("/api/parts_hidden", {})]);
mark("data"); bootStep("Building the editor…");
const ICONS = IDX.icons, PARTS = PARTS_J.parts, PR = Object.fromEntries(R.presets.map(p => [p.name, p]));
let {hidden: HIDDEN, cats: CATS} = META0;       // part cards hidden as vague / their categories (iconkit/*.json)
const CAT_ORDER = ["Damage types", "Figures", "Hands & arms", "Creatures", "Skulls & bones", "Weapons", "Objects", "Elements & nature",
                   "Sun, moon & stars", "Rays & effects", "Frames & rings", "Symbols & marks", "Shapes & lines"];
const partById = id => PARTS.find(c => String(c.id) === String(id)), catOf = c => CATS[c.key] || "Other";
const BYNAME = Object.fromEntries(ICONS.map(e => [e.n, e]));
// the modder's own icons, imported and cut like game icons (outputs/editor/imported, user 7.0h)
let MINE = (await post("/api/imported", {}).catch(() => ({icons: []}))).icons;
for (const e of MINE) BYNAME[e.n] = e;
const iconDir = n => BYNAME[n]?.src === "import" ? "/imported/" : "/data/editor/";
const KIND_DEFAULT = {};                       // most common preset per kind: the colour when the fields say nothing
for (const k of ["Spell", "Action", "Illithid"]) {
  const c = {};
  for (const e of ICONS) if (e.k === k) c[e.p] = (c[e.p] || 0) + 1;
  KIND_DEFAULT[k] = Object.entries(c).sort((a, b) => b[1] - a[1])[0][0];
}
async function bitmapPixels(url) {             // exact pixels of an opaque PNG (no colour management, no premultiply)
  const blob = await (await get(url)).blob();
  const bmp = await createImageBitmap(blob, {colorSpaceConversion: "none", premultiplyAlpha: "none"});
  const c = canvas(bmp.width, bmp.height), x = ctx2d(c);
  x.drawImage(bmp, 0, 0);
  return x.getImageData(0, 0, bmp.width, bmp.height).data;
}
const strokeCache = new Map();
function strokesOf(n) {                         // icon -> {S: Map(stroke id -> {x0, y0, w, h, canvas, alpha}), la}
  if (!strokeCache.has(n)) strokeCache.set(n, (async () => {
    const base = iconDir(n) + "icons/" + encodeURIComponent(n);
    const [la, lb] = await Promise.all([bitmapPixels(base + ".png"), bitmapPixels(base + ".lab.png")]);
    const box = new Map();
    for (let i = 0; i < N * N; i++) {
      const id = lb[i * 4] + 256 * lb[i * 4 + 1];
      if (!id) continue;
      const x = i % N, y = (i / N) | 0, b = box.get(id);
      if (!b) box.set(id, [x, y, x, y]);
      else { if (x < b[0]) b[0] = x; if (x > b[2]) b[2] = x; if (y < b[1]) b[1] = y; if (y > b[3]) b[3] = y; }
    }
    const S = new Map();
    for (const [id, [x0, y0, x1, y1]] of box) S.set(id, {id, x0, y0, w: x1 - x0 + 1, h: y1 - y0 + 1, img: new ImageData(x1 - x0 + 1, y1 - y0 + 1)});
    for (let i = 0; i < N * N; i++) {
      const id = lb[i * 4] + 256 * lb[i * 4 + 1];
      if (!id) continue;
      const s = S.get(id), j = (((i / N) | 0) - s.y0) * s.w + (i % N) - s.x0, d = s.img.data;
      d[j * 4] = d[j * 4 + 1] = d[j * 4 + 2] = la[i * 4];
      d[j * 4 + 3] = la[i * 4 + 1];
    }
    for (const s of S.values()) {
      s.canvas = canvas(s.w, s.h);
      ctx2d(s.canvas).putImageData(s.img, 0, 0);
      s.alpha = new Uint8Array(s.w * s.h).map((_, j) => s.img.data[j * 4 + 3]);
      delete s.img;
    }
    return {S, la};
  })());
  return strokeCache.get(n);
}

// ---------------------------------------------------------------- affine [a, b, c, d, e, f] (canvas setTransform)
const I = () => [1, 0, 0, 1, 0, 0];
const mul = (A, B) => [A[0] * B[0] + A[2] * B[1], A[1] * B[0] + A[3] * B[1], A[0] * B[2] + A[2] * B[3], A[1] * B[2] + A[3] * B[3],
                       A[0] * B[4] + A[2] * B[5] + A[4], A[1] * B[4] + A[3] * B[5] + A[5]];
const about = (c, M) => mul([1, 0, 0, 1, c[0], c[1]], mul(M, [1, 0, 0, 1, -c[0], -c[1]]));
const apply = (M, x, y) => [M[0] * x + M[2] * y + M[4], M[1] * x + M[3] * y + M[5]];
function invert(M) {
  const det = M[0] * M[3] - M[1] * M[2];
  return [M[3] / det, -M[1] / det, -M[2] / det, M[0] / det, (M[2] * M[5] - M[3] * M[4]) / det, (M[1] * M[4] - M[0] * M[5]) / det];
}
const scaleOf = M => Math.sqrt(Math.abs(M[0] * M[3] - M[1] * M[2])) || 1;
const rot = a => [Math.cos(a), Math.sin(a), -Math.sin(a), Math.cos(a), 0, 0];

// ---------------------------------------------------------------- items
let items = [], sel = new Set(), uid = 1, nodeSel = -1;
const counters = {};
// groups (Figma / Affinity): item.g = a group id, GROUPS[id] = {name, open}. A group's strokes stay together in the
// stacking order; a click on the canvas picks the whole group, a double-click goes inside it (inGroup: its strokes one
// by one, until Esc or a click outside). No nesting.
let GROUPS = {}, inGroup = null;
const members = g => items.filter(i => i.g === g);
const unitOf = it => it.g && it.g !== inGroup ? members(it.g).filter(i => !i.hidden && !i.locked) : [it];   // what a click picks
function newGroup(name) { const id = Math.max(0, ...Object.keys(GROUPS).map(Number)) + 1; GROUPS[id] = {name: name || `Group ${id}`, open: false}; return id; }
function tidyGroups() {                          // each group's strokes together, where its topmost one is; empty groups go
  for (const g of Object.keys(GROUPS)) if (!items.some(i => i.g === +g)) delete GROUPS[g];
  for (const it of items) if (it.g && !GROUPS[it.g]) delete it.g;
  if (inGroup && !GROUPS[inGroup]) inGroup = null;
  const out = [], done = new Set();
  for (let k = items.length - 1; k >= 0; k--) {
    const it = items[k];
    if (!it.g) out.push(it);
    else if (!done.has(it.g)) { done.add(it.g); out.push(...members(it.g).reverse()); }
  }
  if (out.some((it, k) => it !== items[items.length - 1 - k])) items = out.reverse();
}
function insertAbove(copies, of) { const m = new Map(of.map((o, k) => [o, copies[k]])); items = items.flatMap(i => m.has(i) ? [i, m.get(i)] : [i]); }
function copiesOf(list, f) {                     // copies of whole groups form new groups; copies inside a group stay in it
  const gmap = {};
  return list.map(i => {
    const c = {...clone(i), id: uid++, name: i.name + " copy", ...f(i)};
    if (i.g && members(i.g).every(m => sel.has(m.id))) c.g = gmap[i.g] ??= newGroup(GROUPS[i.g].name + " copy");
    return c;
  });
}
// bitmap strokes -> vector strokes where the look stays (vectorize.js; user 7.0h): a fitted brush path is rendered
// and kept only when it covers the same pixels (match >= VEC_MATCH, 1 px edge tolerance); erased or branched strokes stay
const VEC_MATCH = .9;
function toVector(it) {                          // -> {vecs: [vec]} | {why}
  if (it.type !== "game") return {why: "already vector"};
  if (it.erase.length) return {why: "partly erased"};
  const f = vectorize(it.alpha, it.w, it.h);
  if (f.fail) return {why: f.fail};
  let best = null;
  for (const k of [1, .9, 1.1]) {                 // each mark's median width, and a little either side
    const vecs = f.marks.map(mk => ({kind: "path", pts: mk.pts.map(([x, y]) => [x + it.ox, y + it.oy]), corner: mk.corner || mk.pts.map(() => false), curve: 1,
      closed: mk.closed, width: Math.max(1, Math.round(mk.width * k * 10) / 10), rough: mk.dab ? .5 : 1, taperStart: mk.taperStart, taperEnd: mk.taperEnd,
      tip: .32, smooth: .5, barbs: 0, seed: 1 + Math.floor(Math.random() * 2 ** 30)}));
    const q = match(it.alpha, it.ox, it.oy, it.w, it.h, vecs.map(v => Brush.render(v)));
    if (!best || q > best.q) best = {vecs, q};
  }
  if (best.q < VEC_MATCH) return {why: "would look different", q: best.q};   // the shape, without barbs
  // the stroke's own barbs (its density, research/probes/barbs.py's measure), swept the way that covers it best
  const d = Math.round(barbDensity(it.alpha, it.w, it.h) * 10) / 10;
  if (d > 0) {
    const tries = [-1, 1].map(sweep => { const vecs = best.vecs.map(v => v.pts.length < 3 || v.width < 4 ? v : {...v, barbs: d, sweep});   // dots: none
      return {vecs, q: match(it.alpha, it.ox, it.oy, it.w, it.h, vecs.map(v => Brush.render(v)))}; });
    best = {...tries.sort((a, b) => b.q - a.q)[0], q: best.q};
  }
  return best;
}
function toVectors(list = selected(), quiet = false) {
  const game = list.filter(i => i.type === "game");
  if (!game.length) return quiet ? null : status("Select game or imported strokes to convert", "err");
  pushUndo();
  const why = {};
  let n = 0, marks = 0;
  for (const it of game) {
    const r = toVector(it);
    if (!r.vecs) { why[r.why] = (why[r.why] || 0) + 1; continue; }
    const g = r.vecs.length > 1 && !it.g ? newGroup(it.name.replace(/ · \d+$/, "") + " · " + it.name.split(" · ").pop()) : it.g;
    const fresh = r.vecs.map(v => vecItem(v, {m: it.m.slice(), second: it.second, hidden: it.hidden, locked: it.locked, ...(g ? {g} : {})}));
    items.splice(items.indexOf(it), 1, ...fresh);
    if (sel.delete(it.id)) for (const f of fresh) sel.add(f.id);
    n++; marks += fresh.length;
  }
  changed();
  const rest = Object.entries(why).map(([k, v]) => `${v} ${k}`).join(", ");
  if (quiet) return {n, of: game.length};
  status(`Converted ${n} of ${game.length} stroke${game.length > 1 ? "s" : ""} to vector strokes (${marks} in all)` + (rest ? ` · not converted: ${rest}` : ""), n ? "ok" : "");
  hud(`${n} of ${game.length} converted`);
}
function group() {
  const s = selected();
  if (!s.length) return status("Select strokes to group", "err");
  pushUndo();
  const id = newGroup();
  for (const it of s) it.g = id;
  inGroup = null; changed();
  hud(`Grouped ${s.length} into ${GROUPS[id].name}`);
}
function ungroup() {
  const gs = new Set(selected().map(i => i.g).filter(Boolean));
  if (!gs.size) return status("Select a group to ungroup", "err");
  pushUndo();
  for (const it of items) if (gs.has(it.g)) delete it.g;
  for (const g of gs) delete GROUPS[g];
  inGroup = null; changed();
  hud(gs.size > 1 ? `Ungrouped ${gs.size} groups` : "Ungrouped");
}
const effM = it => mul(it.m, [1, 0, 0, 1, it.ox, it.oy]);   // bitmap px -> drawing
const VEC_NAME = {free: "Brush", path: "Path", ellipse: "Ellipse"};
function nextName(k) { counters[k] = (counters[k] || 0) + 1; return `${k} ${counters[k]}`; }
const alphaOf = c => { const d = ctx2d(c).getImageData(0, 0, c.width, c.height).data; return new Uint8Array(c.width * c.height).map((_, j) => d[j * 4 + 3]); };
function eraseStroke(x, e, k, ox, oy) {        // an eraser stroke (local px) on a bitmap drawn at scale k, offset (ox, oy)
  x.lineCap = x.lineJoin = "round";
  x.lineWidth = e.w * k;
  x.strokeStyle = x.fillStyle = "#000";
  x.beginPath();
  if (e.pts.length === 1) { x.arc(e.pts[0][0] * k - ox, e.pts[0][1] * k - oy, e.w * k / 2, 0, 7); x.fill(); return; }
  e.pts.forEach(([px, py], i) => i ? x.lineTo(px * k - ox, py * k - oy) : x.moveTo(px * k - ox, py * k - oy));
  x.stroke();
}
function bake(it) {                            // base bitmap (restyled: barbs) minus the eraser strokes -> bmp + alpha (for picking)
  if (it.type === "game") {                     // a game stroke's barbs changed: its bitmap grows by the barbs' reach
    const r = it.barbs != null ? restyled(it) : {canvas: it.base, alpha: it.baseAlpha, pad: 0};
    Object.assign(it, {w: r.canvas.width, h: r.canvas.height, ox: it.ox0 - r.pad, oy: it.oy0 - r.pad});
    if (!it.erase.length) { it.bmp = r.canvas; it.alpha = r.alpha; return; }
    const c = canvas(it.w, it.h), x = ctx2d(c);
    x.drawImage(r.canvas, 0, 0);
    x.globalCompositeOperation = "destination-out";
    for (const e of it.erase) eraseStroke(x, e, 1, it.ox, it.oy);
    it.bmp = c; it.alpha = alphaOf(c);
    return;
  }
  if (!it.erase.length) { it.bmp = it.base; it.alpha = it.baseAlpha; return; }
  const c = canvas(it.w, it.h), x = ctx2d(c);
  x.drawImage(it.base, 0, 0);
  x.globalCompositeOperation = "destination-out";
  for (const e of it.erase) eraseStroke(x, e, 1, it.ox, it.oy);
  it.bmp = c;
  it.alpha = alphaOf(c);
}
// A game / imported stroke made smoother or thornier (user 7.0h: "convert an icon's strokes between smoother /
// thornier"): its own barbs cut off (vectorize.barbs: the mask opened with a disc of .4 widths; pieces farther than
// 1.5 px from the barb-free body go, its soft rim stays), then it.barbs per 100 px drawn on the body's edge with the
// brush's measured barb shapes (brush.js barbShape, BARB_CAL), all pointing one way along the stroke's own path (away
// from one end, along the body: a zigzag or a curve keeps its flow). Non-destructive: the base bitmap stays; it.barbs
// null = as drawn.
const barbBodies = new WeakMap();                // baseAlpha -> vectorize.barbs() + flow (the cut is the slow part)
const bodyOf = it => { let B = barbBodies.get(it.baseAlpha); if (!B) barbBodies.set(it.baseAlpha, B = barbs(it.baseAlpha, it.base.width, it.base.height)); return B; };
// steps along the body from one end of each piece (the farthest point from any point of it, found twice over): the
// stroke's flow. -1 outside the body.
function flowOf(B, w, h) {
  if (B.geo) return B.geo;
  const geo = new Int32Array(w * h).fill(-1), seen = new Int32Array(w * h).fill(-1);
  const bfs = (s, d) => {                       // fills d from s over the body, returns the last (farthest) pixel
    let q = [s], last = s, k = 0; d[s] = 0;
    while (q.length) {
      const nq = [];
      for (const p of q) { last = p; const x = p % w, y = (p / w) | 0;
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          const X = x + dx, Y = y + dy, j = Y * w + X;
          if (X >= 0 && Y >= 0 && X < w && Y < h && B.body[j] && d[j] < 0) { d[j] = k + 1; nq.push(j); }
        } }
      q = nq; k++;
    }
    return last;
  };
  for (let i = 0; i < w * h; i++) if (B.body[i] && seen[i] < 0) bfs(bfs(i, seen), geo);
  return B.geo = geo;
}
function restyled(it) {
  if (it._rs && it._rs.base === it.base && it._rs.barbs === it.barbs) return it._rs;
  const B = bodyOf(it), w0 = it.base.width, h0 = it.base.height, W = B.W, pad = Math.ceil(1.6 * W) + 2, w = w0 + 2 * pad, h = h0 + 2 * pad;
  const src = ctx2d(it.base).getImageData(0, 0, w0, h0).data, out = new ImageData(w, h), d = out.data;
  const greys = [];
  for (let y = 0; y < h0; y++) for (let x = 0; x < w0; x++) {
    const i = y * w0 + x, j = ((y + pad) * w + x + pad) * 4;
    if (!B.body[i] && B.fromBody[i] > 1.5) continue;           // a barb of its own: cut
    d[j] = d[j + 1] = d[j + 2] = src[i * 4]; d[j + 3] = src[i * 4 + 3];
    if (B.body[i] && (x === 0 || !B.body[i - 1] || x === w0 - 1 || !B.body[i + 1] || y === 0 || !B.body[i - w0] || y === h0 - 1 || !B.body[i + w0])) greys.push(i);
  }
  const c = canvas(w, h), x = ctx2d(c);
  x.putImageData(out, 0, 0);
  const n = Math.round(Math.max(0, it.barbs - Brush.BARB_CAL[0]) / Brush.BARB_CAL[1] * B.blen / 100);
  if (n > 0 && greys.length) {
    // the stroke's flow (barbs point along it), the grey just inside its edge (barbs are as bright as where they leave)
    const geo = flowOf(B, w0, h0), geoAt = (X, Y) => { const xx = Math.round(X), yy = Math.round(Y); return xx < 0 || yy < 0 || xx >= w0 || yy >= h0 ? -1 : geo[yy * w0 + xx]; };
    const inner = []; for (let i = 0; i < w0 * h0; i++) if (B.inBody[i] >= 2 && B.inBody[i] < 4) inner.push(src[i * 4]);   // the grey just inside the edge
    const g = inner.length ? inner.sort((a, b) => a - b)[inner.length >> 1] : greys.map(i => src[i * 4]).sort((a, b) => a - b)[greys.length >> 1];
    const rnd = Brush.mulberry32(it.barbSeed ??= 1 + Math.floor(Math.random() * 2 ** 30));
    const order = greys.slice();
    for (let k = order.length - 1; k > 0; k--) { const j = Math.floor(rnd() * (k + 1)); [order[k], order[j]] = [order[j], order[k]]; }
    const placed = [], gap = .6 * W, inB = (X, Y) => { const xx = Math.min(w0 - 1, Math.max(0, Math.round(X))), yy = Math.min(h0 - 1, Math.max(0, Math.round(Y))); return B.inBody[yy * w0 + xx]; };
    x.fillStyle = `rgb(${g},${g},${g})`;
    x.beginPath();
    for (const i of order) {
      if (placed.length >= n) break;
      const px = i % w0 + .5, py = ((i / w0) | 0) + .5;
      if (placed.some(([qx, qy]) => Math.hypot(qx - px, qy - py) < gap)) continue;
      let nx = inB(px - 2, py) - inB(px + 2, py), ny = inB(px, py - 2) - inB(px, py + 2);   // outward: down the distance inside the body
      const L = Math.hypot(nx, ny);
      if (L < 1e-3) continue;
      nx /= L; ny /= L;
      let tx = -ny, ty = nx;
      const ix = px - nx * 2, iy = py - ny * 2, g4 = [geoAt(ix + 2, iy), geoAt(ix - 2, iy), geoAt(ix, iy + 2), geoAt(ix, iy - 2)];
      if (g4.some(v => v < 0)) continue;
      const fx = g4[0] - g4[1], fy = g4[2] - g4[3], fl = Math.hypot(fx, fy);   // the flow here
      if (!fl || Math.abs(fx * nx + fy * ny) > .5 * fl) continue;   // an end or a corner: the edge runs across the flow
      if (tx * fx + ty * fy < 0) { tx = -tx; ty = -ty; }   // along the flow
      const b = Brush.barbShape(rnd, W), sw = b.same ? 1 : -1, poly = Brush.barbPoly([px, py], [tx * sw, ty * sw], [nx, ny], b, W), tip = poly[poly.tip], foot = poly.at(-1);
      if (inB(tip[0], tip[1]) > 0 || !inB(poly[0][0], poly[0][1]) || !inB(foot[0], foot[1])) continue;   // a tip back inside the stroke (inner curves), a foot off it (a narrow end)
      placed.push([px, py]);
      Brush.addPoly(x, poly.map(([qx, qy]) => [qx + pad, qy + pad]));   // one winding: overlaps never cancel
    }
    x.globalCompositeOperation = "lighten";     // union with the stroke
    x.filter = "blur(0.5px)";                  // the game's barbs have its soft edge, not a cut-paper one
    x.fill();
  }
  return it._rs = {base: it.base, barbs: it.barbs, canvas: c, alpha: alphaOf(c), pad};
}
function gameItem(n, s, extra = {}) {
  const e = BYNAME[n];
  const it = {id: uid++, type: "game", name: `${e ? e.t : n} · ${s.id}`, icon: n, label: s.id, base: s.canvas, baseAlpha: s.alpha,
              w: s.w, h: s.h, ox: s.x0, oy: s.y0, ox0: s.x0, oy0: s.y0, m: I(), erase: [], second: false, hidden: false, locked: false, ...extra};
  bake(it);
  return it;
}
function vecItem(vec, extra = {}) {
  const it = {id: uid++, type: "vec", name: nextName(VEC_NAME[vec.kind]), vec, m: I(), erase: [], second: false, hidden: false, locked: false, ...extra};
  rerender(it);
  return it;
}
function rerender(it) {                         // a stroke just drawn finishes its live pieces (= Brush.render, cheaper)
  const r = it.live ? Brush.finish(it.vec, it.live) : Brush.render(it.vec);
  delete it.live;
  Object.assign(it, {base: r.canvas, baseAlpha: r.alpha, w: r.w, h: r.h, ox: r.x0, oy: r.y0});
  bake(it);
}
// a stroke's box = its visible pixels (alpha >= half), not its bitmap: brush bitmaps carry a few px of empty margin,
// which would put aligned / snapped strokes visibly off. Cached per alpha array (a new bitmap gets a new array).
const tightOf = new WeakMap();
function tight(it) {
  let t = tightOf.get(it.alpha);
  if (!t) {
    const a = it.alpha;
    for (const thr of [128, 1]) {
      let x0 = it.w, y0 = it.h, x1 = -1, y1 = -1;
      for (let y = 0, k = 0; y < it.h; y++) for (let x = 0; x < it.w; x++, k++) if (a[k] >= thr) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; y1 = y; }
      if (x1 >= 0) { t = [x0, y0, x1 + 1, y1 + 1]; break; }
    }
    tightOf.set(it.alpha, t ??= [0, 0, it.w, it.h]);
  }
  return t;
}
const corners = it => { const M = effM(it), [x0, y0, x1, y1] = tight(it); return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(([x, y]) => apply(M, x, y)); };
function bounds(list) {
  let b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const it of list) for (const [x, y] of corners(it)) b = [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)];
  return b;
}
const selected = () => items.filter(i => sel.has(i.id));
function hitItem(x, y, tol = 3) {
  for (let k = items.length - 1; k >= 0; k--) {
    const it = items[k];
    if (it.hidden || it.locked) continue;
    const M = effM(it), [u, v] = apply(invert(M), x, y), r = Math.ceil(tol / scaleOf(M));
    if (u < -r || v < -r || u > it.w + r || v > it.h + r) continue;
    for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
      const uu = Math.floor(u) + dx, vv = Math.floor(v) + dy;
      if (uu >= 0 && vv >= 0 && uu < it.w && vv < it.h && it.alpha[vv * it.w + uu] > 60) return it;
    }
  }
  return null;
}

// ---------------------------------------------------------------- undo (snapshots share bitmaps; edits replace them)
let undoStack = [], redoStack = [], lastTag = null, lastT = 0;
const clone = it => ({...it, m: it.m.slice(), erase: it.erase.slice(), vec: it.vec && structuredClone(it.vec)});
const snapshot = () => ({items: items.map(clone), sel: [...sel], groups: structuredClone(GROUPS)});
function pushUndo(tag = null) {                // tagged pushes within 900 ms coalesce (slider drags, nudges)
  const now = performance.now();
  if (tag && tag === lastTag && now - lastT < 900) { lastT = now; return; }
  lastTag = tag; lastT = now;
  undoStack.push(snapshot());
  if (undoStack.length > 300) undoStack.shift();
  redoStack = [];
}
function restore(s) { items = s.items; sel = new Set(s.sel); GROUPS = s.groups || {}; nodeSel = -1; changed(); }
function undo() { if (undoStack.length) { redoStack.push(snapshot()); restore(undoStack.pop()); lastTag = null; status("Undone"); } }
function redo() { if (redoStack.length) { undoStack.push(snapshot()); restore(redoStack.pop()); lastTag = null; status("Redone"); } }

// ---------------------------------------------------------------- view (zoom / pan)
const vp = $("#vp"), stage = $("#stage"), ov = $("#overlay"), oc = ov.getContext("2d");
const view = {z: 1, x: 0, y: 0, fitted: false};
function applyView() {
  stage.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.z})`;
  stage.classList.toggle("px", view.z >= 2);
  $("#zoomv").textContent = `${Math.round(view.z * 100)}%`;
  drawOverlay();
}
function fit() {
  const r = vp.getBoundingClientRect();
  view.z = Math.max(.1, Math.min(r.width, r.height) * .92 / N);
  view.x = (r.width - N * view.z) / 2; view.y = (r.height - N * view.z) / 2; view.fitted = true;
  applyView();
}
function zoomAt(f, sx, sy) {
  const r = vp.getBoundingClientRect();
  sx ??= r.width / 2; sy ??= r.height / 2;
  const z = clamp(view.z * f, .1, 32);
  view.x = sx - (sx - view.x) * z / view.z; view.y = sy - (sy - view.y) * z / view.z; view.z = z; view.fitted = false;
  applyView();
  hud(`${Math.round(z * 100)}%`);
}
// the canvas box, kept by the ResizeObserver: reading it per pointer event forced a layout of the whole page each time
let vpRect = vp.getBoundingClientRect();
const toDoc = e => [(e.clientX - vpRect.left - view.x) / view.z, (e.clientY - vpRect.top - view.y) / view.z];
const toScr = ([x, y]) => [view.x + view.z * x, view.y + view.z * y];
new ResizeObserver(() => {
  const r = vpRect = vp.getBoundingClientRect(), dpr = devicePixelRatio || 1;
  ov.width = Math.round(r.width * dpr); ov.height = Math.round(r.height * dpr);
  if (view.fitted || !ov.dataset.ready) { ov.dataset.ready = 1; fit(); } else drawOverlay();
}).observe(vp);

// ---------------------------------------------------------------- rendering
const F = {kind: $("#kind"), name: $("#name"), intent: $("#intent"), damage: $("#damage"), source: $("#source"), frame: $("#frame"), mod: $("#mod"), key: $("#iconKey")};
const fieldVal = {colour: "", second: ""};    // "" = Auto / None
const painter = new Painter($("#gl"));
const artA = canvas(N), artB = canvas(N), artAll = canvas(N);
let lineView = false, dirty = false, hotTimer = 0, hotSeq = 0, tempPending = false, under = null, artRev = 0;   // artRev: +1 per recompose (export cache)
function compose(c, list, base = null) {       // union of strokes: "lighten" keeps the brighter of two overlapping strokes
  const x = c.getContext("2d");
  x.setTransform(1, 0, 0, 1, 0, 0);
  x.clearRect(0, 0, c.width, c.height);
  x.imageSmoothingEnabled = true;
  x.imageSmoothingQuality = "high";
  x.globalCompositeOperation = "lighten";
  if (base) x.drawImage(base, 0, 0);            // the strokes below, composed once (= drawing them here one by one)
  for (const it of list) {
    if (it.hidden) continue;
    if (it.live) {                             // a stroke being drawn: its settled pieces + its end (disjoint pixels)
      x.setTransform(1, 0, 0, 1, 0, 0);
      x.drawImage(it.live.done, 0, 0);
      x.drawImage(it.live.last.canvas, it.live.last.x0, it.live.last.y0);
      continue;
    }
    x.setTransform(...effM(it)); x.drawImage(it.bmp, 0, 0);
  }
  x.setTransform(1, 0, 0, 1, 0, 0);
  x.globalCompositeOperation = "source-over";
  return c;
}
// a stroke being drawn (brush, line, ellipse drag) only changes itself: the others are composed once per drag (`under`)
const drawing = () => !!(temp && drag && ["brush", "line", "ellipse"].includes(drag.mode));
function refreshTemp() {                       // the stroke being drawn: freehand paints only its unsettled end
  if (drag?.mode !== "brush") return rerender(temp);
  temp.live = Brush.live(temp.vec, temp.live, N);
}
const preset = () => fieldVal.colour && PR[fieldVal.colour] ? fieldVal.colour : defaultColour();   // a deleted custom colour falls back to Auto
const second = () => fieldVal.second && PR[fieldVal.second] && items.some(i => i.second && !i.hidden) ? fieldVal.second : "";
function recipe(p) {                             // variants.recipe
  const k = `${F.kind.value}|${p}`;
  return R.glow[k] || R.glow[R.borrow[k]] || R.glow[F.kind.value];
}
function invalidate() {                        // next frame; the timer covers background tabs (no frames)
  if (!dirty) { dirty = true; requestAnimationFrame(() => dirty && render()); setTimeout(() => dirty && render(), 100); }
}
const prof = PERFTEST ? {} : null;              // ?perftest: ms per part of a frame, summed
function timed(k, f) { if (!prof) return f(); const t = performance.now(), r = f(); prof[k] = (prof[k] || 0) + performance.now() - t; return r; }
function render() {
  artRev++;
  dirty = false;
  if (tempPending) { tempPending = false; if (temp) timed("stroke", refreshTemp); }
  const p2 = second(), live = drawing();
  if (!live) under = liveArt = liveBox = null;
  else if (!under) {                            // CPU canvases: read back per frame for the upload (see composeLive)
    const rest = items.filter(i => i !== temp);
    under = [compose(cpuCanvas(N), rest), p2 && compose(canvas(N), rest.filter(i => !i.second)), p2 && compose(canvas(N), rest.filter(i => i.second))];
  }
  const list = live ? [temp] : items, fast = live && !p2 && !lineView && !!temp.live;
  let rect = null;
  timed("compose", () => {
    if (fast) return rect = composeLive();
    compose(artAll, list, under?.[0]);
    if (p2) { compose(artA, list.filter(i => !i.second), under?.[1]); compose(artB, list.filter(i => i.second), under?.[2]); }
  });
  timed("glow", () => painter.render(fast ? liveArt : p2 ? artA : artAll, PR[preset()], recipe(preset()), p2 ? artB : null, p2 ? PR[p2] : null, p2 ? recipe(p2) : null, rect));
  if (lineView) { const x = $("#art").getContext("2d"); x.fillStyle = "#000"; x.fillRect(0, 0, N, N); x.drawImage(artAll, 0, 0); }
  if (!live) timed("previews", smallPreviews);   // not mid-stroke: their high-quality downscale is ~3 ms of GPU a frame
  timed("overlay", drawOverlay);
  timed("dom", () => {
    $("#empty").hidden = items.length > 0;
    $("#perf").textContent = `${items.length} stroke${items.length === 1 ? "" : "s"} · preview ${painter.ms.toFixed(1)} ms`;
    $("#undo").disabled = !undoStack.length; $("#redo").disabled = !redoStack.length;
  });
  clearTimeout(hotTimer);
  if (!GOLDEN && !live) hotTimer = setTimeout(hotbar, 350);   // not mid-stroke: a pause would stall the next frames
}
// a freehand stroke being drawn: the composite lives in a CPU canvas and only the area its end changed (this frame's
// end ∪ the last frame's, which holds any piece that just settled) is recomposed and uploaded: Firefox spent ~12 ms a
// frame reading a whole GPU canvas back for the preview. Same pixels as compose(): under, settled pieces, end, lighten.
let liveArt = null, liveBox = null;
const cpuCanvas = n => { const c = canvas(n); ctx2d(c); return c; };
function composeLive() {                       // -> [x, y, w, h] to upload, or null: upload all (the first frame)
  const L = temp.live.last, box = [L.x0, L.y0, L.x0 + L.w, L.y0 + L.h], first = !liveArt;
  liveArt ??= cpuCanvas(N);
  const u = first ? [0, 0, N, N] : [Math.min(liveBox[0], box[0]), Math.min(liveBox[1], box[1]), Math.max(liveBox[2], box[2]), Math.max(liveBox[3], box[3])];
  liveBox = box;
  const x0 = clamp(u[0], 0, N), y0 = clamp(u[1], 0, N), w = clamp(u[2], 0, N) - x0, h = clamp(u[3], 0, N) - y0;
  if (w > 0 && h > 0) {
    const x = liveArt.getContext("2d");
    x.save(); x.beginPath(); x.rect(x0, y0, w, h); x.clip();
    x.clearRect(x0, y0, w, h);
    x.globalCompositeOperation = "lighten";
    x.drawImage(under[0], 0, 0); x.drawImage(temp.live.done, 0, 0); x.drawImage(L.canvas, L.x0, L.y0);
    x.restore();
  }
  return first ? null : [x0, y0, Math.max(0, w), Math.max(0, h)];
}
function smallPreviews() {
  const gl = $("#gl"), dark = `rgb(${R.dark.map(v => Math.round(v * 255)).join(",")})`;
  const c = $("#ctrl").getContext("2d");
  c.fillStyle = dark; c.fillRect(0, 0, 144, 144);
  c.imageSmoothingQuality = "high"; c.drawImage(gl, 0, 0, 144, 144);
  const t = canvas(380), tx = t.getContext("2d");                       // fade.bottom_fade, then over the dark
  tx.imageSmoothingQuality = "high"; tx.drawImage(gl, 0, 0, 380, 380);
  const f = tx.createLinearGradient(0, 0, 0, 380);
  for (let k = 0; k <= 40; k++) {
    const y = k / 40, u = clamp((y - .253) / (1.247 - .253), 0, 1);
    f.addColorStop(y, `rgba(0,0,0,${Math.pow(1 - u * u * (3 - 2 * u), 1.8)})`);
  }
  tx.globalCompositeOperation = "destination-in"; tx.fillStyle = f; tx.fillRect(0, 0, 380, 380);
  const tp = $("#tip").getContext("2d");
  tp.fillStyle = dark; tp.fillRect(0, 0, 380, 380); tp.drawImage(t, 0, 0);
}
async function hotbar() {
  const seq = ++hotSeq;
  try {
    const r = await post("/api/hotbar", {master: $("#gl").toDataURL("image/png"), kind: F.kind.value, preset: preset(),
                                         second: second() || null, frame: frame()});
    if (seq === hotSeq) $("#hot").src = r.hotbar;
  } catch (e) { status("Hotbar preview: " + e.message, "err"); }
}
let panelTimer = 0, saveTimer = 0;
function changed() {                           // the drawing changed: repaint now, panels and autosave soon
  tidyGroups();
  invalidate();
  clearTimeout(panelTimer);
  panelTimer = setTimeout(() => { refreshLayers(); refreshProps(); refreshOpts(); refreshDocTabs(); }, 30);
  clearTimeout(saveTimer);
  if (!GOLDEN && !BRUSHTEST && !PERFTEST) saveTimer = setTimeout(autosave, 1500);
}

// ---------------------------------------------------------------- overlay (screen space)
const DEF = {...Brush.DEFAULTS, eraser: 24};
// barbs per 100 px (brush.js BARB): auto = the icon kind's median in the game (research/probes/barbs.py, 505 icons:
// 1,083 icons: spells 3.1, thorny in 81%; actions 1.0; illithid powers 1.3); ST.barbs null = auto, a number once moved
const KIND_BARBS = {Spell: 3.1, Action: 1.0, Illithid: 1.3};
Object.defineProperty(DEF, "barbs", {get: () => KIND_BARBS[F.kind.value] ?? 1.7, enumerable: true});
const barbsNow = () => ST.barbs ?? DEF.barbs;    // what a slider resets to (double-click, or Backspace when focused)
const ST = {...DEF, eraseMode: "pixels"};
Object.assign(ST, store.get("stroke", {}));
let tool = "select", drag = null, hover = null, cursor = null, pen = null, spaceDown = false, temp = null;
function handles() {
  if (!sel.size || tool !== "select") return null;
  const b = bounds(selected()), [x0, y0] = toScr([b[0], b[1]]), [x1, y1] = toScr([b[2], b[3]]);
  return {b, s: [x0, y0, x1, y1], corners: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], rot: [(x0 + x1) / 2, y0 - 24]};
}
const nodeItem = () => { if (tool !== "node" || sel.size !== 1) return null; const it = selected()[0]; return it?.type === "vec" && it.vec.kind === "path" ? it : null; };
function drawOverlay() {
  const dpr = devicePixelRatio || 1;
  oc.setTransform(1, 0, 0, 1, 0, 0);
  oc.clearRect(0, 0, ov.width, ov.height);
  oc.setTransform(dpr, 0, 0, dpr, 0, 0);
  oc.lineWidth = 1;
  const poly = (pts, close = true) => { oc.beginPath(); pts.forEach((p, i) => { const [x, y] = toScr(p); i ? oc.lineTo(x, y) : oc.moveTo(x, y); }); if (close) oc.closePath(); oc.stroke(); };
  if (hover && !sel.has(hover.id) && tool === "select") { oc.strokeStyle = "rgba(232,176,74,.5)"; poly(corners(hover)); }
  for (const it of selected()) { oc.strokeStyle = it.second ? "rgba(121,184,255,.95)" : "rgba(232,176,74,.95)"; poly(corners(it)); }
  const h = handles();
  if (h) {
    oc.setLineDash([4, 3]); oc.strokeStyle = "rgba(255,255,255,.7)";
    oc.strokeRect(h.s[0] - .5, h.s[1] - .5, h.s[2] - h.s[0] + 1, h.s[3] - h.s[1] + 1); oc.setLineDash([]);
    oc.beginPath(); oc.moveTo(h.rot[0], h.rot[1] + 5); oc.lineTo(h.rot[0], h.s[1]); oc.stroke();
    oc.fillStyle = "#e8b04a"; oc.strokeStyle = "#1b1305";
    for (const [x, y] of h.corners) { oc.fillRect(x - 4.5, y - 4.5, 9, 9); oc.strokeRect(x - 4.5, y - 4.5, 9, 9); }
    oc.beginPath(); oc.arc(h.rot[0], h.rot[1], 5, 0, 7); oc.fill(); oc.stroke();
  }
  drawGuides();
  if (drag?.mode === "box") {
    const [x0, y0] = toScr(drag.p0), [x1, y1] = toScr(drag.p);
    oc.fillStyle = "rgba(232,176,74,.08)"; oc.fillRect(x0, y0, x1 - x0, y1 - y0);
    oc.setLineDash([4, 3]); oc.strokeStyle = "rgba(255,255,255,.85)"; oc.strokeRect(x0, y0, x1 - x0, y1 - y0); oc.setLineDash([]);
  }
  const np = nodeItem();
  if (np) {                                    // points of the path being edited
    oc.strokeStyle = "rgba(121,184,255,.6)";
    poly(np.vec.pts.map(p => apply(np.m, ...p)), np.vec.closed);
    np.vec.pts.forEach((p, i) => {
      const [x, y] = toScr(apply(np.m, ...p));
      oc.fillStyle = i === nodeSel ? "#79b8ff" : "#101418"; oc.strokeStyle = "#79b8ff"; oc.lineWidth = 1.5;
      oc.beginPath();
      if (np.vec.corner[i]) oc.rect(x - 4.5, y - 4.5, 9, 9); else oc.arc(x, y, 5, 0, 7);
      oc.fill(); oc.stroke();
    });
    oc.lineWidth = 1;
  }
  if (pen) {
    oc.fillStyle = "#79b8ff"; oc.strokeStyle = "#101418";
    pen.pts.forEach((p, i) => { const [x, y] = toScr(p); oc.beginPath(); if (pen.corner[i]) oc.rect(x - 4, y - 4, 8, 8); else oc.arc(x, y, 4.5, 0, 7); oc.fill(); oc.stroke(); });
    if (pen.pts.length > 2 && cursor) {
      const [x, y] = toScr(pen.pts[0]), [cx, cy] = toScr(cursor);
      if (Math.hypot(x - cx, y - cy) < 10) { oc.strokeStyle = "#79b8ff"; oc.beginPath(); oc.arc(x, y, 9, 0, 7); oc.stroke(); }
    }
  }
  if (cursor && ["brush", "eraser", "line", "ellipse", "pen"].includes(tool) && (!drag || drag.mode === "brush")) {
    const [x, y] = toScr(cursor), r = Math.max(2, (tool === "eraser" ? ST.eraser : ST.width) / 2 * view.z);
    if (r >= 4) {                              // the outline at the stroke's width (white on a dark ring: any background)
      oc.strokeStyle = "rgba(255,255,255,.8)"; oc.beginPath(); oc.arc(x, y, r, 0, 7); oc.stroke();
      oc.strokeStyle = "rgba(0,0,0,.6)"; oc.beginPath(); oc.arc(x, y, r + 1, 0, 7); oc.stroke();
    }
    const c = r < 4 ? 6 : 3;                   // a cross at the hot spot; alone when the outline would be a dot
    for (const [col, lw] of [["rgba(0,0,0,.55)", 3], ["rgba(255,255,255,.9)", 1]]) {
      oc.strokeStyle = col; oc.lineWidth = lw; oc.beginPath();
      oc.moveTo(x - c, y); oc.lineTo(x + c, y); oc.moveTo(x, y - c); oc.lineTo(x, y + c); oc.stroke();
    }
    oc.lineWidth = 1;
  }
  if (drag?.mode === "eraser") {
    const [x, y] = toScr(drag.p); oc.strokeStyle = "rgba(255,138,120,.95)"; oc.beginPath(); oc.arc(x, y, ST.eraser / 2 * view.z, 0, 7); oc.stroke();
  }
}

// ---------------------------------------------------------------- snapping (Figma / Affinity smart guides)
// Moving or scaling, the selection's box snaps (within 6 screen px) to the page's edges and centre, to other strokes'
// edges and centres, and to equal gaps: centred between its two neighbours, or the gap already used in its row.
// Guides show what it snapped to. Toggle in the top bar (Ctrl+Shift+;); press Ctrl once dragging to move freely (Ctrl at
// the press is Ctrl-click: add to the selection).
let snapOn = store.get("snap", true), guides = null;
const SNAP_PX = 6, PAGE = [0, 0, N, N], SNAP_COL = "#ff4f8b";
const lines = (b, i) => [b[i], (b[i] + b[i + 2]) / 2, b[i + 2]];          // low edge, centre, high edge on axis i (0 x, 1 y)
const overlap = (a, b, j) => Math.min(a[j + 2], b[j + 2]) - Math.max(a[j], b[j]);
const snapTargets = () => ({others: items.filter(i => !sel.has(i.id) && !i.hidden && i !== temp).map(i => bounds([i])), b0: bounds(selected())});
function neighbours(B, i, others, tol) {         // the nearest boxes before / after B on axis i, in its row (overlap on the other axis)
  const row = others.filter(o => overlap(o, B, 1 - i) > 0);
  return {row, lo: row.filter(o => o[i + 2] <= B[i] + tol).sort((a, b) => b[i + 2] - a[i + 2])[0],
               hi: row.filter(o => o[i] >= B[i + 2] - tol).sort((a, b) => a[i] - b[i])[0]};
}
function rowGaps(boxes, i) {                     // [a, b, gap] for boxes in a row, one after the other on axis i
  const s = boxes.slice().sort((a, b) => a[i] - b[i]), out = [];
  for (let k = 1; k < s.length; k++) { const g = s[k][i] - s[k - 1][i + 2]; if (g > .5) out.push([s[k - 1], s[k], g]); }
  return out;
}
function snapAxis(B, i, others, T, spacing) {    // the smallest shift on axis i that lands on something, or 0
  let best = null;
  const take = d => { if (Math.abs(d) <= T && (best === null || Math.abs(d) < Math.abs(best))) best = d; };
  for (const box of [PAGE, ...others]) for (const t of lines(box, i)) for (const m of lines(B, i)) take(t - m);
  if (spacing) {
    const {row, lo, hi} = neighbours(B, i, others, T), w = B[i + 2] - B[i];
    if (lo && hi) take((lo[i + 2] + hi[i] - w) / 2 - B[i]);
    for (const [, , g] of rowGaps(row, i)) { if (lo) take(lo[i + 2] + g - B[i]); if (hi) take(hi[i] - g - B[i + 2]); }
  }
  return best ?? 0;
}
function guidesFor(B, others, spacing) {         // what B lines up with now: lines across both boxes, equal gaps
  const out = [], eps = .5, seen = new Set();
  for (const i of [0, 1]) {
    const j = 1 - i;
    for (const box of [PAGE, ...others]) for (const t of lines(box, i)) if (lines(B, i).some(m => Math.abs(m - t) < eps)) {
      const key = `l${i}:${t.toFixed(1)}`;
      const g = out.find(o => o.key === key);
      if (g) { g.from = Math.min(g.from, box[j]); g.to = Math.max(g.to, box[j + 2]); }
      else out.push({key, type: "line", i, at: t, from: Math.min(B[j], box[j]), to: Math.max(B[j + 2], box[j + 2])});
    }
    if (!spacing) continue;
    const {row, lo, hi} = neighbours(B, i, others, eps), gaps = rowGaps([...row, B], i);
    for (const g0 of [lo && B[i] - lo[i + 2], hi && hi[i] - B[i + 2]]) {
      const same = g0 > .5 ? gaps.filter(([, , g]) => Math.abs(g - g0) < eps) : [];
      if (same.length < 2) continue;
      for (const [a, b, g] of same) {
        const key = `g${i}:${a[i + 2].toFixed(1)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({type: "gap", i, a: a[i + 2], b: b[i], at: (Math.max(a[j], b[j]) + Math.min(a[j + 2], b[j + 2])) / 2, g});
      }
    }
  }
  return out;
}
function snapScale(s) {                          // the dragged corner lands on a page / stroke line
  const {anchor: a, c0} = drag, {others} = drag.snap, T = SNAP_PX / view.z;
  let best = null;
  for (const i of [0, 1]) {
    const span = c0[i] - a[i];
    if (Math.abs(span) < 1) continue;
    for (const box of [PAGE, ...others]) for (const t of lines(box, i)) {
      const d = Math.abs(t - (a[i] + span * s));
      if (d <= T && (!best || d < best.d)) best = {d, s: (t - a[i]) / span};
    }
  }
  return best && best.s > .02 ? best.s : s;
}
function drawGuides() {
  if (!guides?.length) return;
  oc.strokeStyle = oc.fillStyle = SNAP_COL; oc.lineWidth = 1;
  oc.font = "600 10.5px 'Segoe UI', system-ui, sans-serif"; oc.textAlign = "center"; oc.textBaseline = "middle";
  const P = (i, along, across) => toScr(i === 0 ? [along, across] : [across, along]);
  for (const g of guides) {
    oc.beginPath();
    if (g.type === "line") {
      const [x0, y0] = P(g.i, g.at, g.from), [x1, y1] = P(g.i, g.at, g.to), c = v => Math.round(v) + .5;
      g.i === 0 ? (oc.moveTo(c(x0), y0), oc.lineTo(c(x1), y1)) : (oc.moveTo(x0, c(y0)), oc.lineTo(x1, c(y1)));
      oc.stroke();
      continue;
    }
    const [ax, ay] = P(g.i, g.a, g.at), [bx, by] = P(g.i, g.b, g.at), t = 4;      // gap: a bar with end ticks + its size
    oc.moveTo(ax, ay); oc.lineTo(bx, by);
    if (g.i === 0) { oc.moveTo(ax, ay - t); oc.lineTo(ax, ay + t); oc.moveTo(bx, by - t); oc.lineTo(bx, by + t); }
    else { oc.moveTo(ax - t, ay); oc.lineTo(ax + t, ay); oc.moveTo(bx - t, by); oc.lineTo(bx + t, by); }
    oc.stroke();
    const label = String(Math.round(g.g)), w = oc.measureText(label).width + 8, mx = (ax + bx) / 2, my = (ay + by) / 2;
    oc.beginPath(); oc.roundRect(mx - w / 2, my - 7.5, w, 15, 4); oc.fill();
    oc.fillStyle = "#fff"; oc.fillText(label, mx, my + .5); oc.fillStyle = SNAP_COL;
  }
}

// ---------------------------------------------------------------- tools
const TOOL_KEYS = {v: "select", a: "node", b: "brush", l: "line", u: "ellipse", p: "pen", e: "eraser", h: "hand"};
const TOOL_HELP = {select: "Move / select: click a stroke, Shift adds, drag empty space to box-select, Alt-drag copies",
  node: "Edit points: drag a point · Alt-click: corner or smooth · double-click: add a point",
  brush: "Brush: drag to draw", line: "Line: drag · Shift snaps to 15°",
  ellipse: "Ellipse: drag · Shift: circle · Alt: from the centre",
  pen: "Pen: click to add points · Alt-click: corner · click the first point to close · Enter: finish",
  eraser: "Eraser: drag over what to erase", hand: "Hand: drag to pan"};
function setTool(t, quiet = false) {
  if (tool === "pen" && t !== "pen") finishPen();
  tool = t;
  $$("[data-tool]").forEach(b => b.setAttribute("aria-pressed", b.dataset.tool === t));
  ov.style.cursor = {select: "default", node: "default", hand: "grab", eraser: "none", brush: "none"}[t] || "crosshair";
  nodeSel = -1;
  refreshOpts();
  drawOverlay();
  if (!quiet) status(TOOL_HELP[t]);
}
$$("[data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
$('[data-tool="hand"]').addEventListener("dblclick", () => userFit());   // Photoshop: double-click the Hand fits
const newVec = (kind, geo) => ({kind, ...geo, width: ST.width, rough: ST.rough, barbs: barbsNow(), taperStart: ST.taperStart, taperEnd: ST.taperEnd,
                                tip: ST.tip, seed: 1 + Math.floor(Math.random() * 2 ** 30)});
function updateTemp() { tempPending = true; invalidate(); }   // the stroke being drawn: updated in the next frame's render
function ellipseGeo(p0, p, shift, alt) {
  let dx = p[0] - p0[0], dy = p[1] - p0[1];
  if (shift) { const r = Math.max(Math.abs(dx), Math.abs(dy)); dx = Math.sign(dx || 1) * r; dy = Math.sign(dy || 1) * r; }
  return alt ? {cx: p0[0], cy: p0[1], rx: Math.abs(dx), ry: Math.abs(dy)}
             : {cx: p0[0] + dx / 2, cy: p0[1] + dy / 2, rx: Math.abs(dx) / 2, ry: Math.abs(dy) / 2};
}
function snapAngle(a, b, on) {
  if (!on) return b;
  const r = Math.hypot(b[0] - a[0], b[1] - a[1]), t = Math.round(Math.atan2(b[1] - a[1], b[0] - a[0]) / (Math.PI / 12)) * Math.PI / 12;
  return [a[0] + r * Math.cos(t), a[1] + r * Math.sin(t)];
}
function finishPen() {
  if (!pen) return;
  const p = pen;
  pen = null;
  items = items.filter(i => i !== temp);
  temp = null;
  if (p.pts.length >= 2) {
    pushUndo();
    const it = vecItem({...newVec("path", {}), pts: p.pts, corner: p.corner, curve: ST.curve, closed: p.closed, seed: p.seed});
    items.push(it); sel = new Set([it.id]);
    status(`Path with ${p.pts.length} points. Press A to edit its points.`, "ok");
  }
  changed();
}
function penPreview() {                        // the pen path so far (+ the cursor) as a live stroke, outside undo
  if (!pen) return;
  const pts = cursor ? [...pen.pts, cursor] : pen.pts, corner = cursor ? [...pen.corner, false] : pen.corner;
  if (pts.length < 2) { items = items.filter(i => i !== temp); temp = null; return invalidate(); }
  const v = {...newVec("path", {}), pts, corner, curve: ST.curve, closed: false, seed: pen.seed};
  if (!temp) { temp = vecItem(v); items.push(temp); } else temp.vec = v;
  updateTemp();
}
function insertNode(it, p) {                   // a new point on the path, in the control segment nearest to p
  const [u, v] = apply(invert(it.m), ...p), P = it.vec.pts, n = P.length, segs = it.vec.closed ? n : n - 1;
  let best = 0, bd = Infinity;
  for (let i = 0; i < segs; i++) {
    const a = P[i], b = P[(i + 1) % n], dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy || 1;
    const t = clamp(((u - a[0]) * dx + (v - a[1]) * dy) / L2, 0, 1), d = Math.hypot(u - a[0] - t * dx, v - a[1] - t * dy);
    if (d < bd) { bd = d; best = i; }
  }
  pushUndo();
  P.splice(best + 1, 0, [u, v]);
  it.vec.corner.splice(best + 1, 0, false);
  nodeSel = best + 1;
  rerender(it); changed();
}
const nodeAt = (it, sx, sy) => it.vec.pts.findIndex(p => { const [x, y] = toScr(apply(it.m, ...p)); return Math.hypot(x - sx, y - sy) <= 8; });
ov.addEventListener("pointerdown", e => {
  vp.focus({preventScroll: true});
  try { ov.setPointerCapture(e.pointerId); } catch { /* a synthetic or ended pointer: drags still work over the canvas */ }
  vpRect = vp.getBoundingClientRect();         // once per press: the options bar may have changed height since the last frame
  const p = toDoc(e), sx = e.clientX - vpRect.left, sy = e.clientY - vpRect.top;
  if (e.button === 1 || tool === "hand" || spaceDown) { e.preventDefault(); drag = {mode: "pan", sx, sy, vx: view.x, vy: view.y}; ov.style.cursor = "grabbing"; return; }
  if (e.button !== 0) return;
  if (tool === "pen") {
    if (!pen) pen = {pts: [], corner: [], seed: 1 + Math.floor(Math.random() * 2 ** 30), closed: false};
    if (pen.pts.length > 2) {
      const [x, y] = toScr(pen.pts[0]);
      if (Math.hypot(x - sx, y - sy) < 10) { pen.closed = true; return finishPen(); }
    }
    if (e.detail >= 2 && pen.pts.length >= 2) return finishPen();
    pen.pts.push(p); pen.corner.push(e.altKey);
    penPreview(); drawOverlay();
    return;
  }
  if (tool === "brush" || tool === "line" || tool === "ellipse") {
    pushUndo();
    const geo = tool === "brush" ? {pts: [p], smooth: ST.smooth} : tool === "line" ? {pts: [p, p], corner: [true, true], curve: 0}
              : ellipseGeo(p, p, e.shiftKey, e.altKey);
    temp = vecItem(newVec(tool === "brush" ? "free" : tool === "line" ? "path" : "ellipse", geo));
    items.push(temp);
    drag = {mode: tool, p0: p, p};
    return invalidate();
  }
  if (tool === "eraser") {
    pushUndo();
    drag = {mode: "eraser", p0: p, p, touched: new Map(), kill: new Set()};
    eraseAt(p, p);
    return;
  }
  if (tool === "node") {
    const it = nodeItem();
    if (it) {
      const k = nodeAt(it, sx, sy);
      if (k >= 0) {
        if (e.altKey) { pushUndo(); it.vec.corner[k] = !it.vec.corner[k]; nodeSel = k; rerender(it); return changed(); }
        nodeSel = k; drag = {mode: "node", it, k}; return drawOverlay();
      }
      if (e.detail >= 2 && hitItem(...p, 6) === it) return insertNode(it, p);
    }
    const h = hitItem(...p);
    sel = h ? new Set([h.id]) : new Set(); nodeSel = -1;
    if (h && !(h.type === "vec" && h.vec.kind === "path")) status("Only lines and pen paths have points. Use Move (V) for this stroke.");
    return changed();
  }
  const h = handles();                         // select tool
  if (h) {
    const ci = h.corners.findIndex(([x, y]) => Math.abs(x - sx) <= 7 && Math.abs(y - sy) <= 7);
    const from = new Map(selected().map(i => [i.id, i.m.slice()]));
    if (ci >= 0) {
      const opp = [[h.b[2], h.b[3]], [h.b[0], h.b[3]], [h.b[0], h.b[1]], [h.b[2], h.b[1]]][ci];
      drag = {mode: "scale", p0: p, p, anchor: e.altKey ? [(h.b[0] + h.b[2]) / 2, (h.b[1] + h.b[3]) / 2] : opp, from,
              c0: [[h.b[0], h.b[1]], [h.b[2], h.b[1]], [h.b[2], h.b[3]], [h.b[0], h.b[3]]][ci]};
      return;
    }
    if (Math.hypot(sx - h.rot[0], sy - h.rot[1]) <= 8) { drag = {mode: "rotate", p0: p, p, c: [(h.b[0] + h.b[2]) / 2, (h.b[1] + h.b[3]) / 2], from}; return; }
  }
  const it = hitItem(...p);
  if (it) {
    if (inGroup && it.g !== inGroup) inGroup = null;               // a click outside the group you went into leaves it
    const u = unitOf(it);
    if (e.shiftKey || e.ctrlKey || e.metaKey) { const on = !sel.has(it.id); for (const i of u) on ? sel.add(i.id) : sel.delete(i.id); return changed(); }
    if (!sel.has(it.id)) sel = new Set(u.map(i => i.id));
    drag = {mode: "move", p0: p, p, alt: e.altKey, from: new Map(selected().map(i => [i.id, i.m.slice()]))};
  } else {
    inGroup = null;
    if (!e.shiftKey) sel.clear();
    drag = {mode: "box", p0: p, p, base: new Set(sel)};
  }
  changed();
});
ov.addEventListener("pointermove", e => {
  const p = toDoc(e);
  cursor = p;
  const xy = `x ${Math.round(p[0])}  y ${Math.round(p[1])}`, co = $("#coords");
  if (co.textContent !== xy) co.textContent = xy;
  if (!drag) {
    if (tool === "select") hover = hitItem(...p);
    if (tool === "pen" && pen) penPreview();
    return drawOverlay();
  }
  drag.p = p;
  const {mode, p0} = drag;
  if (mode === "pan") {
    view.x = drag.vx + (e.clientX - vpRect.left - drag.sx); view.y = drag.vy + (e.clientY - vpRect.top - drag.sy); view.fitted = false;
    return applyView();
  }
  if (mode === "brush") {                      // every sample the mouse sent since the last frame, not just the last one
    const ce = e.getCoalescedEvents?.() ?? [];
    for (const c of ce.length ? ce : [e]) {
      const a = toDoc(c), q = temp.vec.pts.at(-1);
      if (Math.hypot(a[0] - q[0], a[1] - q[1]) >= 1) temp.vec.pts.push(a);
    }
    return updateTemp();
  }
  if (mode === "line") { temp.vec.pts = [p0, snapAngle(p0, p, e.shiftKey)]; return updateTemp(); }
  if (mode === "ellipse") { Object.assign(temp.vec, ellipseGeo(p0, p, e.shiftKey, e.altKey)); return updateTemp(); }
  if (mode === "eraser") { eraseAt(drag.last || p0, p); drag.last = p; return drawOverlay(); }
  if (mode === "node") {
    if (!drag.pushed) { pushUndo(); drag.pushed = true; }
    drag.it.vec.pts[drag.k] = apply(invert(drag.it.m), ...p);
    rerender(drag.it); return changed();
  }
  if (mode === "box") {
    const [x0, x1] = [Math.min(p0[0], p[0]), Math.max(p0[0], p[0])], [y0, y1] = [Math.min(p0[1], p[1]), Math.max(p0[1], p[1])];
    sel = new Set(drag.base);
    for (const it of items) { if (it.hidden || it.locked) continue; const b = bounds([it]); if (b[0] >= x0 && b[2] <= x1 && b[1] >= y0 && b[3] <= y1) for (const u of unitOf(it)) sel.add(u.id); }
    return drawOverlay();
  }
  if (!drag.pushed) {                          // move / scale / rotate: one undo step for the whole drag
    pushUndo();
    drag.pushed = true;
    if (mode === "move" && drag.alt) {         // Alt-drag: the originals stay where they were, copies move
      const s = selected(), copies = copiesOf(s, () => ({}));
      insertAbove(copies, s);
      sel = new Set(copies.map(c => c.id));
      drag.from = new Map(copies.map(c => [c.id, c.m.slice()]));
    }
  }
  const fr = drag.from;
  const snap = snapOn && !e.ctrlKey && !e.metaKey;
  guides = null;
  if (mode === "move") {
    let dx = p[0] - p0[0], dy = p[1] - p0[1];
    if (e.shiftKey) Math.abs(dx) > Math.abs(dy) ? dy = 0 : dx = 0;
    if (snap) {
      const S = drag.snap ??= snapTargets(), T = SNAP_PX / view.z, B = () => [S.b0[0] + dx, S.b0[1] + dy, S.b0[2] + dx, S.b0[3] + dy];
      if (!(e.shiftKey && dx === 0)) dx += snapAxis(B(), 0, S.others, T, true);
      if (!(e.shiftKey && dy === 0)) dy += snapAxis(B(), 1, S.others, T, true);
      guides = guidesFor(B(), S.others, true);
    }
    for (const it of selected()) it.m = mul([1, 0, 0, 1, dx, dy], fr.get(it.id));
  } else if (mode === "scale") {
    const a = drag.anchor, d0 = Math.hypot(p0[0] - a[0], p0[1] - a[1]) || 1;
    let s = Math.max(.02, Math.hypot(p[0] - a[0], p[1] - a[1]) / d0);
    if (snap) { drag.snap ??= snapTargets(); s = snapScale(s); }
    status(`Scale ${Math.round(s * 100)}%`);
    for (const it of selected()) it.m = mul(about(a, [s, 0, 0, s, 0, 0]), fr.get(it.id));
    if (snap) guides = guidesFor(bounds(selected()), drag.snap.others, false);
  } else if (mode === "rotate") {
    const c = drag.c;
    let t = Math.atan2(p[1] - c[1], p[0] - c[0]) - Math.atan2(p0[1] - c[1], p0[0] - c[0]);
    if (e.shiftKey) t = Math.round(t / (Math.PI / 12)) * Math.PI / 12;
    status(`Rotate ${Math.round(t * 180 / Math.PI)}°`);
    for (const it of selected()) it.m = mul(about(c, rot(t)), fr.get(it.id));
  }
  changed();
});
function endDrag() {
  if (!drag) return;
  const d = drag;
  drag = null;
  guides = null;
  if (d.mode === "pan") { ov.style.cursor = tool === "hand" ? "grab" : ""; return; }
  if (["brush", "line", "ellipse"].includes(d.mode)) {
    const it = temp;
    temp = null;
    const tiny = d.mode === "ellipse" ? it.vec.rx < 1 && it.vec.ry < 1 : d.mode === "line" && Math.hypot(d.p[0] - d.p0[0], d.p[1] - d.p0[1]) < 1;
    if (tiny) { items = items.filter(i => i !== it); undoStack.pop(); }
    else { rerender(it); sel = new Set([it.id]); }
  }
  if (d.mode === "eraser") {
    for (const it of d.touched.keys()) it.alpha = alphaOf(it.bmp);
    if (d.kill.size) { items = items.filter(i => !d.kill.has(i.id)); sel.clear(); status(`Deleted ${d.kill.size} stroke${d.kill.size > 1 ? "s" : ""}`); }
    if (!d.touched.size && !d.kill.size) undoStack.pop();
  }
  changed();
}
ov.addEventListener("pointerup", endDrag);
ov.addEventListener("pointercancel", endDrag);
ov.addEventListener("pointerleave", () => { cursor = null; hover = null; $("#coords").textContent = ""; if (pen) penPreview(); drawOverlay(); });
ov.addEventListener("dblclick", e => {
  if (tool === "pen") return finishPen();
  const it = tool === "select" && hitItem(...toDoc(e));
  if (!it?.g) return;
  inGroup = it.g; sel = new Set([it.id]); changed();                // inside a group: its strokes one by one
  hud(`Inside ${GROUPS[it.g].name} · Esc leaves`);
});
function eraseAt(a, b) {                       // eraser segment a -> b: pixels off every stroke it crosses, or whole strokes
  const r = ST.eraser / 2, bx = [Math.min(a[0], b[0]) - r, Math.min(a[1], b[1]) - r, Math.max(a[0], b[0]) + r, Math.max(a[1], b[1]) + r];
  const steps = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 2));
  for (const it of items) {
    if (it.hidden || it.locked) continue;
    const ib = bounds([it]);
    if (ib[2] < bx[0] || ib[0] > bx[2] || ib[3] < bx[1] || ib[1] > bx[3]) continue;
    if (ST.eraseMode === "strokes") {
      for (let k = 0; k <= steps; k++) { const t = k / steps, q = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]; if (hitItem(...q, r) === it) { drag.kill.add(it.id); break; } }
      continue;
    }
    const inv = invert(it.m), la = apply(inv, ...a), lb = apply(inv, ...b), w = ST.eraser / scaleOf(it.m);
    let t = drag.touched.get(it);
    if (!t) {                                 // copy-on-write: the undo snapshot keeps the old bitmap
      t = {pts: [la], w};
      it.erase = [...it.erase, t];
      const c = canvas(it.w, it.h); ctx2d(c).drawImage(it.bmp, 0, 0); it.bmp = c;
      drag.touched.set(it, t);
    }
    t.pts.push(lb);
    const x = ctx2d(it.bmp);
    x.globalCompositeOperation = "destination-out";
    eraseStroke(x, {pts: [la, lb], w}, 1, it.ox, it.oy);
    x.globalCompositeOperation = "source-over";
  }
  if (ST.eraseMode === "strokes") sel = new Set([...drag.kill]);
  invalidate();
}
ov.addEventListener("wheel", e => {
  e.preventDefault();
  const r = vp.getBoundingClientRect();
  if (e.ctrlKey || e.metaKey) zoomAt(Math.exp(-e.deltaY * .0025), e.clientX - r.left, e.clientY - r.top);
  else { view.x -= e.shiftKey ? e.deltaY : e.deltaX; view.y -= e.shiftKey ? 0 : e.deltaY; view.fitted = false; applyView(); }
}, {passive: false});

// ---------------------------------------------------------------- commands
const selCenter = () => { const b = bounds(selected()); return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]; };
function op(M, tag = null) { if (!sel.size) return status("Select strokes first"); pushUndo(tag); const c = selCenter(); for (const it of selected()) it.m = mul(about(c, M), it.m); changed(); }
function translate(dx, dy) { if (!sel.size) return; pushUndo("nudge"); for (const it of selected()) it.m = mul([1, 0, 0, 1, dx, dy], it.m); changed(); }
const cmds = {
  flipH: () => op([-1, 0, 0, 1, 0, 0]), flipV: () => op([1, 0, 0, -1, 0, 0]),
  rotL: () => op(rot(-Math.PI / 12)), rotR: () => op(rot(Math.PI / 12)),
  del: () => { if (!sel.size) return; pushUndo(); items = items.filter(i => !sel.has(i.id)); status(`Deleted ${sel.size}`); sel.clear(); changed(); },
  dup: () => {                                 // copies right above their originals (Photoshop / Figma), offset 12 px
    if (!sel.size) return;
    pushUndo();
    const s = selected(), copies = copiesOf(s, i => ({m: mul([1, 0, 0, 1, 12, 12], i.m)}));
    insertAbove(copies, s); sel = new Set(copies.map(i => i.id)); changed();
  },
  group, ungroup,
  front: () => arrange(1), back: () => arrange(-1),
  second: v => {
    if (!sel.size) return status("Select the strokes for the second colour", "err");
    pushUndo();
    const val = v ?? !selected().every(i => i.second);
    for (const it of selected()) it.second = val;
    if (val && !fieldVal.second) { fieldVal.second = R.presets.find(p => p.name !== preset()).name; refreshFields(); }
    changed();
  },
};
// align / distribute (Figma / Affinity / Photoshop): several strokes line up with their joint box or the page, one
// stroke with the page; spacing evenly keeps the outermost two and makes the gaps between boxes equal
let alignTo = store.get("alignTo", "selection");
const alignRef = () => sel.size > 1 && alignTo === "selection" ? bounds(selected()) : PAGE;
const shift = (it, i, d) => { it.m = mul(i ? [1, 0, 0, 1, 0, d] : [1, 0, 0, 1, d, 0], it.m); };
const ALIGN = {l: [0, 0, "left edges"], cx: [0, 1, "centres"], r: [0, 2, "right edges"], t: [1, 0, "top edges"], cy: [1, 1, "middles"], b: [1, 2, "bottom edges"]};
function align(edge) {
  if (!sel.size) return status("Select strokes to align", "err");
  const [i, at, what] = ALIGN[edge], to = lines(alignRef(), i)[at];
  pushUndo();
  for (const it of selected()) shift(it, i, to - lines(bounds([it]), i)[at]);
  changed();
  hud(`Aligned ${what} to the ${sel.size > 1 && alignTo === "selection" ? "selection" : "page"}`);
}
function distribute(i) {
  const s = selected().map(it => ({it, b: bounds([it])})).sort((a, b) => a.b[i] - b.b[i]);
  if (s.length < 3) return status("Select 3 or more strokes to space evenly", "err");
  const gap = (s.at(-1).b[i + 2] - s[0].b[i] - s.reduce((t, o) => t + o.b[i + 2] - o.b[i], 0)) / (s.length - 1);
  pushUndo();
  let pos = s[0].b[i];
  for (const {it, b} of s) { shift(it, i, pos - b[i]); pos += b[i + 2] - b[i] + gap; }
  changed();
  hud(`Gaps ${Math.round(gap)} px`);
}
function centrePage() {                          // the selection as one block (nothing selected: the whole drawing)
  const s = sel.size ? selected() : items.filter(i => !i.hidden && !i.locked);
  if (!s.length) return;
  const b = bounds(s), dx = N / 2 - (b[0] + b[2]) / 2, dy = N / 2 - (b[1] + b[3]) / 2;
  pushUndo();
  for (const it of s) it.m = mul([1, 0, 0, 1, dx, dy], it.m);
  changed();
  hud(sel.size ? "Selection centred on the page" : "Drawing centred on the page");
}
cmds.centre = centrePage;
function arrange(d) {                          // one step forward / back; +-2 = to the front / back
  if (!sel.size) return;
  pushUndo();
  // strokes inside one group (picked inside it) move among its strokes; otherwise a group moves as one block
  const s = selected(), g0 = s[0].g, inner = g0 && s.every(i => i.g === g0) && !members(g0).every(i => sel.has(i.id));
  const span = inner ? members(g0) : items, a = items.indexOf(span[0]), on = u => u.some(i => sel.has(i.id));
  let units = [];
  for (const it of span) { const last = units.at(-1); if (!inner && it.g && last?.[0].g === it.g) last.push(it); else units.push([it]); }
  if (Math.abs(d) > 1) units = d > 0 ? [...units.filter(u => !on(u)), ...units.filter(on)] : [...units.filter(on), ...units.filter(u => !on(u))];
  else {
    const idx = units.map((u, k) => on(u) ? k : -1).filter(k => k >= 0);
    for (const k of d > 0 ? idx.reverse() : idx) { const j = k + d; if (j < 0 || j >= units.length || on(units[j])) continue; [units[k], units[j]] = [units[j], units[k]]; }
  }
  items.splice(a, span.length, ...units.flat());
  changed();
}

// ---------------------------------------------------------------- options bar (context)
const SLIDERS = {width: ["Width", 2, 60, 1], rough: ["Roughness", 0, 1.5, .05], barbs: ["Thorns", 0, 6, .1], gbarbs: ["Thorns", 0, 6, .1], tip: ["Tip", .05, 1, .01], curve: ["Curve", 0, 1.5, .05],
                 smooth: ["Smoothing", 0, 1, .05], eraser: ["Size", 2, 120, 1]};
const TIPS = {width: "Stroke width at 512 px (the game uses about 14)", rough: "Edge wobble: 0 is smooth, 1 matches the game",
              gbarbs: "Thorns along the edges, per 100 px: higher is thornier, 0 is smooth. Reset keeps the stroke as drawn",
              barbs: "Thorns along the edges, per 100 px: the game's spells use about 3, its actions about 1. Reset follows the icon kind",
              tip: "Width at a tapered end (the game uses about a third)", curve: "0 draws straight segments, 1 a smooth curve",
              smooth: "Steadies freehand strokes", eraser: "Eraser size"};
const PX = new Set(["width", "eraser"]), num = (k, v) => PX.has(k) ? String(Math.round(v)) : (+v).toFixed(2);
const fmt = (k, v) => num(k, v) + (PX.has(k) ? " px" : "");
// a slider = scrubbable name (drag sideways, like Photoshop / Figma / Affinity) + range + a typed value
function slider(k, v) {
  const [lbl, a, b, st] = SLIDERS[k], def = fmt(k, DEF[k]);
  return `<span class="ctl" title="${TIPS[k]}.&#10;Drag the name to adjust (Shift: faster, Alt: finer) · double-click to reset to ${def}">` +
    `<span class="scrub" data-scrub="${k}">${lbl}</span><input type="range" data-k="${k}" min="${a}" max="${b}" step="${st}" value="${v}" aria-label="${lbl}" aria-keyshortcuts="Backspace" aria-description="Backspace resets to ${def}">` +
    `<input class="num${+v === DEF[k] ? "" : " mod"}" data-n="${k}" value="${num(k, v)}" inputmode="decimal" spellcheck="false" aria-label="${lbl} value">${PX.has(k) ? '<span class="unit">px</span>' : ""}</span>`;
}
let restyleQueued = false;
function resetSlider(inp) {
  const k = inp.dataset.k;
  if (k === "gbarbs") {                         // as drawn again
    pushUndo();
    for (const it of selected().filter(i => i.type === "game")) { delete it.barbs; bake(it); }
    changed(); return status("Thorns reset: as drawn");
  }
  inp.value = DEF[k];
  inp.dispatchEvent(new Event("input", {bubbles: true}));
  if (k === "barbs") { ST.barbs = null; store.set("stroke", ST); }   // back to auto (the kind's)
  status(`${SLIDERS[k][0]} reset to ${fmt(k, DEF[k])}`);
}
const check = (k, lbl, v, tip) => `<label class="lbl" title="${tip}"><input type="checkbox" data-k="${k}" ${v ? "checked" : ""}> ${lbl}</label>`;
const ibtn = (cmd, icon, tip, off = false) => `<button class="btn icon" data-cmd="${cmd}" title="${tip}" aria-label="${tip}"${off ? " disabled" : ""}><svg class="i"><use href="#i-${icon}"/></svg></button>`;
const vecSel = () => selected().filter(i => i.type === "vec");
function strokeControls(src, kinds) {
  let h = slider("width", src.width) + slider("rough", src.rough) + slider("barbs", src === ST ? barbsNow() : src.barbs ?? 0) + '<span class="sep"></span>' +
          check("taperStart", "Taper start", src.taperStart, "Narrow the start of the stroke") +
          check("taperEnd", "Taper end", src.taperEnd, "Narrow the end of the stroke") + slider("tip", src.tip);
  if (kinds.has("path")) h += '<span class="sep"></span>' + slider("curve", src.curve ?? ST.curve) +
    (kinds.size === 1 && src.pts ? check("closed", "Closed", !!src.closed, "Join the last point to the first") : "");
  if (kinds.has("free")) h += '<span class="sep"></span>' + slider("smooth", src.smooth ?? ST.smooth);
  return h;
}
// align / space evenly / centre (Affinity's Move tool context toolbar): to the selection's box or the page
const ALIGN_ICON = {l: "al", cx: "ach", r: "ar", t: "at", cy: "acv", b: "ab"};
function alignControls(off) {
  const one = sel.size < 2, toSel = !one && alignTo === "selection";
  return Object.entries(ALIGN).map(([k, [, , what]]) => `<button class="btn icon" data-align="${k}" title="Align ${what} to the ${toSel ? "selection" : "page"}" aria-label="Align ${what}"${off ? " disabled" : ""}><svg class="i"><use href="#i-${ALIGN_ICON[k]}"/></svg></button>`).join("") +
    `<div class="seg sm" role="group" aria-label="Align to" style="margin-left:4px">
      <button class="btn" data-alignto="selection" aria-pressed="${toSel}"${one ? " disabled" : ""} title="Align to the selection: line up the selected strokes with each other">Selection</button>
      <button class="btn" data-alignto="page" aria-pressed="${!toSel}" title="Align to the page">Page</button></div><span class="sep"></span>` +
    `<button class="btn icon" data-dist="0" title="Space evenly across (3 or more strokes)" aria-label="Space evenly across"${sel.size < 3 ? " disabled" : ""}><svg class="i"><use href="#i-dh"/></svg></button>` +
    `<button class="btn icon" data-dist="1" title="Space evenly down (3 or more strokes)" aria-label="Space evenly down"${sel.size < 3 ? " disabled" : ""}><svg class="i"><use href="#i-dv"/></svg></button>` +
    ibtn("centre", "centre", "Centre on the page (the selection, or the whole drawing)");
}
function refreshOpts() {
  const o = $("#opts"), vs = vecSel(), one = vs.length === 1 ? vs[0].vec : null;
  let h;
  if (["brush", "line", "ellipse", "pen"].includes(tool)) {
    h = strokeControls(ST, new Set({brush: ["free"], pen: ["path"]}[tool] || [])) +
        (tool === "pen" ? '<span class="sep"></span><span class="hint">Alt-click: corner point · Enter: finish · Esc: cancel</span>' : "");
  } else if (tool === "eraser") {
    h = slider("eraser", ST.eraser) + `<span class="sep"></span><div class="seg" role="group" aria-label="Eraser mode">
      <button class="btn" data-mode="pixels" aria-pressed="${ST.eraseMode === "pixels"}" title="Erase where you drag">Pixels</button>
      <button class="btn" data-mode="strokes" aria-pressed="${ST.eraseMode === "strokes"}" title="Delete each stroke you touch">Whole strokes</button></div>
      `;
  } else if (tool === "hand") h = '<span class="hint">Drag to pan · Ctrl+wheel zooms · Ctrl+0 fits</span>';
  else if (tool === "node") h = '<span class="hint">Drag a point · Alt-click: corner or smooth · double-click: add a point · Del: remove it</span>' +
      (one && one.kind === "path" ? '<span class="sep"></span>' + strokeControls(one, new Set(["path"])) : "");
  else {
    const off = !sel.size;                     // greyed out until something is selected
    h = ibtn("flipH", "flipH", "Flip horizontally (Shift+H)", off) + ibtn("flipV", "flipV", "Flip vertically (Shift+V)", off) +
        ibtn("rotL", "rotL", "Rotate −15° (Q)", off) + ibtn("rotR", "rotR", "Rotate +15° (W)", off) + '<span class="sep"></span>' +
        ibtn("front", "front", "Bring forward (Ctrl+])", off) + ibtn("back", "back", "Send backward (Ctrl+[)", off) + '<span class="sep"></span>' +
        ibtn("dup", "dup", "Duplicate (Ctrl+J)", off) + ibtn("del", "trash", "Delete (Del)", off) + '<span class="sep"></span>' + alignControls(off);
    if (vs.length) h += '<span class="sep"></span>' + strokeControls(one || {...ST, ...vs[0].vec}, new Set(vs.map(i => i.vec.kind)));
    const gs = selected().filter(i => i.type === "game");    // game / imported strokes: smoother or thornier, as drawn by default
    if (gs.length) h += '<span class="sep"></span>' + slider("gbarbs", gs[0].barbs ?? bodyOf(gs[0]).density);
    else if (!sel.size) h += '<span class="sep"></span><span class="hint">Select strokes to move, scale or rotate them</span>';
  }
  o.innerHTML = h;
}
$("#opts").addEventListener("input", e => {
  const k = e.target.dataset.k;
  if (!k) return;
  const v = e.target.type === "checkbox" ? e.target.checked : +e.target.value;
  if (k === "gbarbs") {                       // selected game strokes restyled (throttled to a frame)
    pushUndo("g:barbs");
    for (const it of selected().filter(i => i.type === "game")) { it.barbs = v; it.barbSeed ??= 1 + Math.floor(Math.random() * 2 ** 30); }
    const nm = $(`input[data-n="gbarbs"]`, $("#opts"));
    if (nm && nm !== document.activeElement) nm.value = num(k, v);
    if (!restyleQueued) { restyleQueued = true; setTimeout(() => { restyleQueued = false; for (const it of selected().filter(i => i.type === "game")) bake(it); under = null; invalidate(); clearTimeout(saveTimer); saveTimer = setTimeout(autosave, 1500); }, 16); }
    return;
  }
  if (k !== "closed") { ST[k] = v; store.set("stroke", ST); }
  const nm = $(`input[data-n="${k}"]`, $("#opts"));
  if (nm) { if (nm !== document.activeElement) nm.value = num(k, v); nm.classList.toggle("mod", v !== DEF[k]); }
  if (tool === "select" || tool === "node") {  // the settings of selected brush strokes change too (retroactive)
    const vs = vecSel().filter(i => k === "curve" || k === "closed" ? i.vec.kind === "path" : k === "smooth" ? i.vec.kind === "free" : k !== "eraser");
    if (vs.length) {                           // not changed(): rebuilding the options bar would drop the slider mid-drag
      pushUndo("vec:" + k); for (const it of vs) { it.vec[k] = v; rerender(it); }
      invalidate(); setTimeout(refreshProps, 30); clearTimeout(saveTimer); saveTimer = setTimeout(autosave, 1500);
    }
  }
  if (pen && k === "curve") penPreview();
  drawOverlay();
});
$("#opts").addEventListener("dblclick", e => {
  const k = e.target.closest("[data-scrub]")?.dataset.scrub ?? (e.target.type === "range" ? e.target.dataset.k : null);
  if (k) resetSlider($(`input[data-k="${k}"]`, $("#opts")));
});
// typed values: Enter / leaving the field applies (clamped to the slider), arrows step (Shift x10), Esc reverts
const rangeOf = nm => $(`input[data-k="${nm.dataset.n}"]`, $("#opts"));
function setRange(r, v) {
  v = clamp(Math.round(v / +r.step) * +r.step, +r.min, +r.max);
  if (+r.value !== v) { r.value = v; r.dispatchEvent(new Event("input", {bubbles: true})); }
  return +r.value;
}
$("#opts").addEventListener("change", e => {
  if (!e.target.dataset.n) return;
  const r = rangeOf(e.target), v = parseFloat(e.target.value.replace(",", "."));
  e.target.value = num(r.dataset.k, Number.isFinite(v) ? setRange(r, v) : +r.value);
});
$("#opts").addEventListener("keydown", e => {
  if (!e.target.dataset.n) return;
  const r = rangeOf(e.target);
  if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    e.preventDefault();
    e.target.value = num(r.dataset.k, setRange(r, +r.value + (e.key === "ArrowUp" ? 1 : -1) * +r.step * (e.shiftKey ? 10 : 1)));
    e.target.select();
  }
  if (e.key === "Enter") e.target.blur();
  if (e.key === "Escape") { e.target.value = num(r.dataset.k, +r.value); e.target.blur(); }
});
$("#opts").addEventListener("focusin", e => { if (e.target.dataset.n) e.target.select(); });
$("#opts").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.cmd) cmds[b.dataset.cmd]();
  if (b.dataset.mode) { ST.eraseMode = b.dataset.mode; store.set("stroke", ST); refreshOpts(); }
  if (b.dataset.align) align(b.dataset.align);
  if (b.dataset.dist) distribute(+b.dataset.dist);
  if (b.dataset.alignto) { alignTo = b.dataset.alignto; store.set("alignTo", alignTo); refreshOpts(); }
});

// ---------------------------------------------------------------- properties
function refreshProps() {
  const p = $("#props"), s = selected();
  if (!s.length) { p.innerHTML = `<div class="muted">Nothing selected. Click a stroke, or drag a box around several.</div>`; return; }
  if (p.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return syncProps();   // typing: values only
  const b = bounds(s), f = v => Math.round(v * 10) / 10;
  const kinds = [...new Set(s.map(i => i.type === "game" ? "game stroke" : "vector stroke"))].join(", ");
  const fld = (k, lbl, v, tip) => `<label title="${tip}"><span class="scrub" data-scrub="${k}">${lbl}</span><input type="number" data-p="${k}" value="${v}" step="1"${k === "w" || k === "h" ? ' min="1"' : ""}></label>`;
  const tip = "Drag the letter to adjust (Shift: faster, Alt: finer) · Enter applies, Esc cancels";
  const grp = s[0].g && s.every(i => i.g === s[0].g) && members(s[0].g).every(i => sel.has(i.id) || i.hidden || i.locked) ? GROUPS[s[0].g].name : "";
  p.innerHTML = `<div class="muted" style="margin-bottom:6px">${grp ? `${esc(grp)} · ${s.length} strokes` : `${s.length} selected (${esc(kinds)})${s.length === 1 ? ` · ${esc(s[0].name)}` : ""}`}</div>
    <div class="xywh">${fld("x", "X", f(b[0]), "Left edge, px. " + tip)}${fld("y", "Y", f(b[1]), "Top edge, px. " + tip)}${fld("w", "W", f(b[2] - b[0]), "Width, px. " + tip)}${fld("h", "H", f(b[3] - b[1]), "Height, px. " + tip)}</div>
    <div class="row" style="margin-top:8px">
      <label class="muted"><input type="checkbox" id="lockRatio" ${store.get("lockRatio", true) ? "checked" : ""}> Keep proportions</label>
      <span class="grow"></span>
      <label class="muted rotf" title="Rotate the selection by this many degrees. ${tip}"><span class="scrub" data-scrub="rot">Rotate</span><input type="number" data-p="rot" value="0" step="1" style="width:58px">°</label>
    </div>
    <label class="f">Colour of the selection</label>
    <div class="seg" role="group" aria-label="Colour of the selection">
      <button class="btn" data-second="0" aria-pressed="${s.every(i => !i.second)}">Main colour</button>
      <button class="btn" data-second="1" aria-pressed="${s.every(i => i.second)}" title="Second colour (X)">Second colour</button>
    </div>`;
}
function applyProp(k, v, tag = null) {        // X / Y / W / H = the selection's box; rot = rotate by v degrees
  if (!sel.size || !Number.isFinite(v)) return;
  const b = bounds(selected()), lock = $("#lockRatio")?.checked;
  if (k === "x") op([1, 0, 0, 1, v - b[0], 0], tag);
  else if (k === "y") op([1, 0, 0, 1, 0, v - b[1]], tag);
  else if (k === "rot") op(rot(v * Math.PI / 180), tag);
  else if (v > 0) {
    const sx = k === "w" ? v / (b[2] - b[0]) : lock ? v / (b[3] - b[1]) : 1, sy = k === "h" ? v / (b[3] - b[1]) : lock ? v / (b[2] - b[0]) : 1;
    pushUndo(tag);
    for (const it of selected()) it.m = mul(about([b[0], b[1]], [sx, 0, 0, sy, 0, 0]), it.m);
    changed();
  }
}
function syncProps() {                         // values of the fields not being typed in, without rebuilding the panel
  if (!sel.size) return;
  const b = bounds(selected()), f = v => Math.round(v * 10) / 10, val = {x: f(b[0]), y: f(b[1]), w: f(b[2] - b[0]), h: f(b[3] - b[1])};
  for (const i of $$("#props input[data-p]")) if (i !== document.activeElement && i.dataset.p in val) i.value = val[i.dataset.p];
}
let rotSoFar = 0;                              // the Rotate field shows what this focus / drag has turned so far
function nudgeProp(inp, d, tag) {
  const k = inp.dataset.p;
  if (k === "rot") { rotSoFar += d; inp.value = rotSoFar; applyProp("rot", d, tag); }
  else { const v = Math.max(k === "w" || k === "h" ? 1 : -Infinity, (+inp.value || 0) + d); inp.value = v; applyProp(k, v, tag); }
  syncProps();
}
$("#props").addEventListener("change", e => {
  const k = e.target.dataset.p;
  if (e.target.id === "lockRatio") return store.set("lockRatio", e.target.checked);
  if (!k || e.target.dataset.cancel) return;
  const v = +e.target.value;
  e.target.blur();
  if (k === "rot") { if (v !== rotSoFar) applyProp("rot", v - rotSoFar); rotSoFar = 0; refreshProps(); }
  else applyProp(k, v);
});
$("#props").addEventListener("keydown", e => {
  const inp = e.target.closest("input[data-p]");
  if (!inp) return;
  if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); nudgeProp(inp, (e.key === "ArrowUp" ? 1 : -1) * (e.shiftKey ? 10 : 1), "nudge:" + inp.dataset.p); }
  if (e.key === "Enter") inp.blur();
  if (e.key === "Escape") { inp.dataset.cancel = "1"; inp.blur(); delete inp.dataset.cancel; syncProps(); }
});
$("#props").addEventListener("focusout", e => { if (e.target.dataset?.p === "rot" && !e.target.matches(":focus")) setTimeout(() => { rotSoFar = 0; refreshProps(); }, 0); });
// scrubby names (Photoshop / Figma / Affinity): drag a control's name sideways; Shift x10, Alt x1/4; one undo step
document.addEventListener("pointerdown", e => {
  const s = e.target.closest?.("[data-scrub]");
  if (!s || e.button !== 0) return;
  const k = s.dataset.scrub, inp = s.closest("#opts") ? $(`input[data-k="${k}"]`, $("#opts")) : $(`#props input[data-p="${k}"]`);
  if (!inp) return;
  e.preventDefault();
  if (document.activeElement?.matches("input.num, #props input")) document.activeElement.blur();   // its value updates again
  try { s.setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
  const x0 = e.clientX, v0 = +inp.value, step = inp.type === "range" ? +inp.step : 1, tag = "scrub:" + k + ":" + performance.now();
  let moved = false, last = 0;
  document.body.classList.add("scrubbing");
  s.onpointermove = ev => {
    const dx = ev.clientX - x0;
    if (!moved && Math.abs(dx) < 3) return;
    moved = true;
    const units = Math.round(dx * (ev.shiftKey ? 10 : ev.altKey ? .25 : 1));
    if (units === last) return;
    if (inp.type === "range") setRange(inp, v0 + units * step);
    else { if (document.activeElement !== inp) inp.focus({preventScroll: true}); nudgeProp(inp, units - last, tag); }
    last = units;
  };
  s.onpointerup = s.onpointercancel = () => {
    s.onpointermove = s.onpointerup = s.onpointercancel = null;
    document.body.classList.remove("scrubbing");
    if (!moved) return inp.focus();
    s.addEventListener("click", ev => ev.preventDefault(), {once: true, capture: true});   // no label click after a drag
    if (inp.type !== "range") inp.blur();
  };
});
$("#props").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.cmd) cmds[b.dataset.cmd]();
  if (b.dataset.second != null) cmds.second(b.dataset.second === "1");
});

// ---------------------------------------------------------------- layers
let dragRow = null;
function refreshLayers() {
  const ul = $("#layers"), list = items.filter(i => i !== temp).reverse(), seen = new Set();
  const eye = (h, nm) => `<button data-act="eye" aria-label="${h ? "Show" : "Hide"} ${esc(nm)}" title="${h ? "Show" : "Hide"}"><svg class="i"><use href="#i-${h ? "eyeoff" : "eye"}"/></svg></button>`;
  const lock = (l, nm) => `<button data-act="lock" aria-label="${l ? "Unlock" : "Lock"} ${esc(nm)}" title="${l ? "Unlock" : "Lock"}"><svg class="i"><use href="#i-${l ? "lock" : "unlock"}"/></svg></button>`;
  const row = (it, sub) => `<li draggable="true" data-id="${it.id}" role="option" aria-selected="${sel.has(it.id)}" class="${it.hidden ? "hid" : ""}${sub ? " sub" : ""}" title="${esc(it.name)}">
    <span class="dot ${it.second ? "second" : ""}" title="${it.second ? "Second colour" : "Main colour"}"></span>${eye(it.hidden, it.name)}
    <canvas class="lt" aria-hidden="true"></canvas><span class="nm">${esc(it.name)}</span>${lock(it.locked, it.name)}</li>`;
  let html = "";
  for (const it of list) {
    if (!it.g) { html += row(it); continue; }
    if (seen.has(it.g)) continue;
    seen.add(it.g);
    const g = GROUPS[it.g], ms = list.filter(i => i.g === it.g), hid = ms.every(i => i.hidden), lk = ms.every(i => i.locked);
    html += `<li draggable="true" data-gid="${it.g}" role="option" aria-selected="${ms.every(i => sel.has(i.id))}" aria-expanded="${!!g.open}" class="grp${hid ? " hid" : ""}${inGroup === it.g ? " inside" : ""}" title="${esc(g.name)}: ${ms.length} strokes&#10;Double-click the name to rename">
      <button data-act="fold" class="fold" aria-label="${g.open ? "Collapse" : "Expand"} ${esc(g.name)}" title="${g.open ? "Collapse" : "Expand"}"><svg class="i"><use href="#i-chev"/></svg></button>${eye(hid, g.name)}
      <svg class="i lt" aria-hidden="true"><use href="#i-group"/></svg><span class="nm">${esc(g.name)}</span><span class="cnt">${ms.length}</span>${lock(lk, g.name)}</li>`;
    if (g.open) html += ms.map(m => row(m, true)).join("");
  }
  ul.innerHTML = html || `<li class="empty"><span class="nm muted">No strokes yet</span></li>`;
  const n = items.filter(i => i !== temp).length;
  $("#layerCount").textContent = n || "";
  // thumbnails (Photoshop's Layers panel): each stroke's own bitmap fitted into the square, so similar names part
  const dpr = devicePixelRatio || 1, S = Math.round(24 * dpr);
  for (const c of $$("canvas.lt", ul)) {
    const it = items.find(i => i.id === +c.parentNode.dataset.id);
    if (!it?.bmp) continue;
    c.width = c.height = S;
    const x = c.getContext("2d"), k = (S - 4 * dpr) / Math.max(it.w, it.h);
    x.imageSmoothingQuality = "high";
    x.drawImage(it.bmp, (S - it.w * k) / 2, (S - it.h * k) / 2, it.w * k, it.h * k);
  }
}
$("#layers").addEventListener("click", e => {
  const gl = e.target.closest("li[data-gid]"), act = e.target.closest("button")?.dataset.act;
  if (gl) {                                    // a group row: fold, eye / lock for all its strokes, or select the group
    const g = +gl.dataset.gid, ms = members(g);
    if (act === "fold") { GROUPS[g].open = !GROUPS[g].open; return refreshLayers(); }
    if (act === "eye") { pushUndo(); const h = !ms.every(i => i.hidden); for (const i of ms) { i.hidden = h; if (h) sel.delete(i.id); } return changed(); }
    if (act === "lock") { pushUndo(); const l = !ms.every(i => i.locked); for (const i of ms) { i.locked = l; if (l) sel.delete(i.id); } return changed(); }
    const ok = ms.filter(i => !i.hidden && !i.locked), on = !ok.every(i => sel.has(i.id));
    if (e.shiftKey || e.ctrlKey || e.metaKey) for (const i of ok) on ? sel.add(i.id) : sel.delete(i.id); else sel = new Set(ok.map(i => i.id));
    inGroup = null;
    if (tool !== "select" && tool !== "node") setTool("select", true);
    return changed();
  }
  const li = e.target.closest("li[data-id]");
  if (!li) return;
  const it = items.find(i => i.id === +li.dataset.id);
  if (act === "eye") { pushUndo(); it.hidden = !it.hidden; if (it.hidden) sel.delete(it.id); return changed(); }
  if (act === "lock") { pushUndo(); it.locked = !it.locked; if (it.locked) sel.delete(it.id); return changed(); }
  if (it.hidden || it.locked) return;
  if (e.shiftKey || e.ctrlKey || e.metaKey) sel.has(it.id) ? sel.delete(it.id) : sel.add(it.id); else sel = new Set([it.id]);
  inGroup = it.g || null;                      // a stroke's row inside a group: you are inside that group
  if (tool !== "select" && tool !== "node") setTool("select", true);
  changed();
});
$("#layers").addEventListener("dblclick", e => {
  const li = e.target.closest("li[data-id], li[data-gid]"), nm = e.target.closest(".nm");
  if (!li || !nm) return;
  const g = li.dataset.gid && GROUPS[+li.dataset.gid], it = !g && items.find(i => i.id === +li.dataset.id), inp = document.createElement("input");
  inp.type = "text"; inp.value = g ? g.name : it.name; inp.style.flex = "1"; inp.setAttribute("aria-label", g ? "Group name" : "Stroke name");
  nm.replaceWith(inp); inp.focus(); inp.select();
  let done = false;
  const finish = ok => { if (done) return; done = true; if (ok && inp.value.trim()) { pushUndo(); (g || it).name = inp.value.trim(); } refreshLayers(); refreshProps(); };
  inp.onkeydown = ev => { if (ev.key === "Enter") finish(true); if (ev.key === "Escape") finish(false); ev.stopPropagation(); };
  inp.onblur = () => finish(true);
});
// drag a row to restack: a stroke dropped among a group's strokes joins that group, dropped elsewhere it leaves its
// group; a group row moves the whole group (never into another group: it lands above or below that group)
$("#layers").addEventListener("dragstart", e => {
  const li = e.target.closest("li");
  dragRow = li?.dataset.gid ? {g: +li.dataset.gid} : {id: +li?.dataset.id};
  e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", "layer");
});
$("#layers").addEventListener("dragover", e => {
  const li = e.target.closest("li[data-id], li[data-gid]");
  if (!li || dragRow == null) return;
  e.preventDefault();
  $$("#layers li").forEach(l => l.classList.remove("drop-before", "drop-after"));
  const r = li.getBoundingClientRect();
  li.classList.add(e.clientY < r.top + r.height / 2 ? "drop-before" : "drop-after");
});
$("#layers").addEventListener("drop", e => {
  const li = e.target.closest("li[data-id], li[data-gid]");
  if (!li || dragRow == null) return;
  e.preventDefault();
  const r = li.getBoundingClientRect(), above = e.clientY < r.top + r.height / 2;   // the list shows the top first: above = later in items
  const blk = dragRow.g ? members(dragRow.g) : items.filter(i => i.id === dragRow.id);
  const tItem = li.dataset.id ? items.find(i => i.id === +li.dataset.id) : null, tG = li.dataset.gid ? +li.dataset.gid : dragRow.g && tItem?.g;
  if (blk.length && !blk.includes(tItem) && !(dragRow.g && dragRow.g === tG)) {
    pushUndo();
    items = items.filter(i => !blk.includes(i));
    let k;
    if (tG) { const ms = members(tG); k = !ms.length ? items.length : above ? items.indexOf(ms.at(-1)) + 1 : items.indexOf(ms[0]); }   // beside the whole group
    else k = items.indexOf(tItem) + (above ? 1 : 0);
    if (!dragRow.g) for (const i of blk) { if (!li.dataset.gid && tItem.g) i.g = tItem.g; else delete i.g; }
    items.splice(k, 0, ...blk);
  }
  dragRow = null;
  changed();
});
$("#layers").addEventListener("dragend", () => { dragRow = null; $$("#layers li").forEach(l => l.classList.remove("drop-before", "drop-after")); });

// ---------------------------------------------------------------- spell fields
const opts = (s, list, first) => s.innerHTML = (first ? `<option value="">${first}</option>` : "") +
  list.map(v => Array.isArray(v) ? `<option value="${esc(v[0])}">${esc(v[1])}</option>` : `<option>${esc(v)}</option>`).join("");
opts(F.intent, R.intents, "(none)");
opts(F.damage, R.damage, "(none)");
opts(F.source, R.sources, "(none)");
// a colour tile = a glowing dot on the hotbar dark: the preset's bright core into its glow colours (it reads like the
// icon it makes, not like a gradient bar); tiles sorted by hue, greys last (sorted by lightness)
const rgba = (h, a) => `rgba(${[1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)).join(",")},${a})`;
const glowDot = p => { const s = PR[p].swatch; return `radial-gradient(circle, ${s[5]} 0 13%, ${s[4]} 22%, ${s[3]} 31%, ${rgba(s[2], .75)} 44%, ${rgba(s[1], .35)} 60%, transparent 74%), var(--dark)`; };
function hueOf(h) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255), mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  if (d < .12) return 400 + (1 - mx) * 100;      // greys after every hue
  const hh = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (hh * 60 + 360 + 20) % 360;             // reds (wrapping round 0) start the list
}
const PREVIEW = "Custom: Preview";              // the custom-colour dialog's live preset (never listed)
let PRESETS_BY_HUE = [];
function applyRecipes(r) {                     // colour data from the server again (a custom colour was made or removed)
  Object.assign(R, r);
  for (const k of Object.keys(PR)) delete PR[k];
  for (const p of R.presets) PR[p.name] = p;
  for (const p of R.presets) if (p.custom) painter.forget(p.name);
  PRESETS_BY_HUE = R.presets.filter(p => p.name !== PREVIEW).map(p => p.name).sort((a, b) => hueOf(PR[a].swatch[4]) - hueOf(PR[b].swatch[4]));
}
applyRecipes(R);
function defaultColour() {                       // grammar.keys + predict: the colour the fields imply (D17)
  const kd = F.kind.value, i = F.intent.value, d = F.damage.value;
  const keys = kd === "Illithid" ? [...(i ? [`Illithid/${i}`] : []), "Illithid"]
             : i === "Damage" && d ? [`damage/${d}`] : i ? [`${kd}/${i}`, `intent/${i}`] : [];
  for (const k of keys) if (R.groups[k]) return R.groups[k].presets[0].preset;
  return KIND_DEFAULT[kd];
}
function swatches(id, first) {
  const v = fieldVal[id], g = $("#" + id);
  g.innerHTML = `<button class="swatch ${id === "colour" ? "auto" : "none"}" data-v="" aria-pressed="${!v}" title="${first}" aria-label="${first}">${id === "colour" ? "A" : "∅"}</button>` +
    PRESETS_BY_HUE.map(n => `<button class="swatch${PR[n].custom ? " cust" : ""}" data-v="${esc(n)}" aria-pressed="${v === n}" title="${esc(n)}${PR[n].custom ? "&#10;Right-click: edit or delete" : ""}" aria-label="${esc(n)}" style="background:${glowDot(n)}"></button>`).join("") +
    `<button class="swatch add" data-add="${id}" title="New colour: one colour or a gradient" aria-label="New colour">+</button>`;
  const shown = id === "colour" ? preset() : v;
  $(`#${id}Bar`).style.background = shown ? glowDot(shown) : "";
  $(`#${id}Bar`).classList.toggle("none", !shown);
  $(`#${id}Name`).textContent = id === "colour" ? (v || `Auto: ${defaultColour()}`) : (v || "None");
}
for (const id of ["colour", "second"]) {
  $("#" + id).onclick = e => {
    const b = e.target.closest(".swatch");
    if (!b) return;
    if (b.dataset.add) return openColourDlg(id);
    fieldVal[id] = b.dataset.v; refreshFields(); changed();
  };
  $("#" + id).addEventListener("contextmenu", e => {   // a custom colour: edit or delete it
    const b = e.target.closest(".swatch.cust");
    if (!b) return;
    e.preventDefault();
    const n = b.dataset.v;
    openMenu(e.clientX, e.clientY, [{head: n}, {label: "Edit…", run: () => openColourDlg(id, n)},
      {label: "Delete", run: async () => {
        try { applyRecipes((await post("/api/presets", {delete: n})).recipes); } catch (err) { return status(err.message, "err"); }
        for (const k of ["colour", "second"]) if (fieldVal[k] === n) fieldVal[k] = "";
        refreshFields(); changed(); status(`Deleted ${n}. Icons that used it are set to Auto`, "ok");
      }}], "Custom colour");
  });
}
// ---------------------------------------------------------------- custom colour dialog (user 7.0h: modders' own colours)
// 1 colour: the game's gradient turned to that hue; 2-4 colours: your gradient from dark to bright. The canvas shows it
// live (a preview preset); Save keeps it in outputs/editor/presets.json for every icon and tab.
const CD = {target: "colour", was: "", stops: ["#3fb8ff"], timer: 0, seq: 0};
function cdRender() {
  $("#cdStops").innerHTML = CD.stops.map((s, i) => `<span class="cdstop"><input type="color" value="${s}" data-i="${i}" aria-label="Colour ${i + 1}">` +
    (CD.stops.length > 1 ? `<button class="x" data-del="${i}" aria-label="Remove colour ${i + 1}" title="Remove">×</button>` : "") + `</span>`).join("") +
    (CD.stops.length < 4 ? `<button class="btn" id="cdAdd" title="Add a colour (up to 4). They are ordered from dark to bright">+ Colour</button>` : "");
  $("#cdHow").textContent = CD.stops.length === 1 ? "One colour: lines stay bright and the glow takes this colour."
    : "Gradient: colours from dark to bright. Each part of the icon takes the colour of its brightness.";
}
async function cdPreview() {
  const seq = ++CD.seq;
  try {
    const r = await post("/api/presets", {stops: CD.stops, preview: true});
    if (seq !== CD.seq) return;
    applyRecipes(r.recipes);
    $("#cdRamp").style.background = `linear-gradient(90deg, ${PR[PREVIEW].swatch.join(", ")})`;
    fieldVal[CD.target] = PREVIEW; refreshFields(); changed();
  } catch (e) { status(e.message, "err"); }
}
const cdQueue = () => { clearTimeout(CD.timer); CD.timer = setTimeout(cdPreview, 120); };
function openColourDlg(target, edit = null) {
  CD.target = target; CD.was = fieldVal[target];
  const p = edit && PR[edit];
  CD.stops = p?.custom?.stops?.slice() || [PR[preset()]?.swatch[4] || "#3fb8ff"];
  $("#cdName").value = edit ? edit.replace(/^Custom: /, "") : "";
  cdRender(); $("#colourDlg").showModal(); cdPreview();
}
$("#cdStops").addEventListener("input", e => { const i = e.target.dataset.i; if (i != null) { CD.stops[+i] = e.target.value; cdQueue(); } });
$("#cdStops").addEventListener("click", e => {
  if (e.target.closest("#cdAdd")) { CD.stops.push(CD.stops.length === 1 ? "#ffffff" : CD.stops.at(-1)); cdRender(); cdQueue(); }
  const d = e.target.closest("[data-del]");
  if (d) { CD.stops.splice(+d.dataset.del, 1); cdRender(); cdQueue(); }
});
$("#cdSave").onclick = async () => {
  const label = $("#cdName").value.trim() || "Colour";
  try {
    const r = await post("/api/presets", {stops: CD.stops, label});
    applyRecipes(r.recipes);
    fieldVal[CD.target] = r.name; refreshFields(); changed();
    $("#colourDlg").close("saved");
    status(`Saved ${r.name}. It's in the colour list of every icon`, "ok");
  } catch (e) { status(e.message, "err"); }
};
$("#colourDlg").addEventListener("close", () => {   // Cancel / Esc: back to the colour it had
  if ($("#colourDlg").returnValue !== "saved") { fieldVal[CD.target] = CD.was; refreshFields(); changed(); }
  $("#colourDlg").returnValue = "";
});
function frameOptions() {                        // D19-D21: the colour's frames first, then every framed background
  const kd = F.kind.value, p = preset();
  if (kd === "Spell") return [];
  const own = kd === "Illithid" ? R.frames_illithid[p] || R.frames_illithid[R.nearest_illithid[p]] || []
                                : R.frames[p] || R.frames[R.nearest[p]] || [];
  const list = [...(kd === "Action" && second() ? R.frame_two_tone : []), ...own];
  if (kd === "Action") for (const bg of R.framed) if (!list.some(e => e[0] === bg && e[3] == null)) list.push([bg, R.gain[bg] ?? .85, 0, null]);
  return list;
}
const frame = () => F.frame.value ? JSON.parse(F.frame.value) : null;
function refreshFields() {
  swatches("colour", "Auto: picked from the kind, intent and damage type");
  swatches("second", "No second colour");
  const v = F.frame.value, L = frameOptions();
  $("#frameBox").style.display = F.kind.value === "Spell" ? "none" : "";
  $("#sourceBox").style.visibility = F.kind.value === "Action" ? "" : "hidden";
  opts(F.frame, L.map(e => [JSON.stringify(e), `${e[0]}${e[3] != null ? " (recoloured)" : ""}${e[2] ? ` · ${Math.round(e[2] * 100)}% of the game's` : ""}`]),
       L.length ? `Auto: ${L[0][0]}${L[0][3] != null ? " (recoloured)" : ""}` : "spell background");
  if ([...F.frame.options].some(o => o.value === v)) F.frame.value = v;
}
for (const k of ["kind", "intent", "damage", "frame", "source"]) F[k].addEventListener("change", () => { refreshFields(); changed(); });
const getFields = () => ({kind: F.kind.value, name: F.name.value, intent: F.intent.value, damage: F.damage.value, source: F.source.value,
                          colour: fieldVal.colour, second: fieldVal.second, frame: F.frame.value, mod: F.mod.value, key: F.key.value});
function setFields(f) {
  for (const k of ["kind", "name", "intent", "damage", "source", "mod"]) if (f[k] != null) F[k].value = f[k];
  F.key.value = f.key || "";
  fieldVal.colour = f.colour || ""; fieldVal.second = f.second || "";
  refreshFields();
  if (f.frame) F.frame.value = f.frame;
}

// ---------------------------------------------------------------- library: game icons, parts, drafts
let tab = store.get("tab", "icons"), showHidden = false, drafts = [], partCat = store.get("partCat", "All"), kindF = store.get("kindF", "");
function moveTo(list, at) {                    // centre a group of new items on a point
  const b = bounds(list), dx = at[0] - (b[0] + b[2]) / 2, dy = at[1] - (b[1] + b[3]) / 2;
  for (const it of list) it.m = mul([1, 0, 0, 1, dx, dy], it.m);
}
async function openIcon(n, add, at = null) {
  status(`Loading ${BYNAME[n]?.t || n}…`);
  const {S} = await strokesOf(n), e = BYNAME[n];
  if (!add && items.length && !GOLDEN) newDoc();   // an icon opens in a tab of its own (the open drawing stays)
  pushUndo();
  if (!add) { items = []; sel.clear(); }
  const sec = new Set(add ? [] : e.sec);
  const fresh = [...S.values()].map(s => gameItem(n, s, {second: sec.has(s.id)}));
  if (at) moveTo(fresh, at);
  items.push(...fresh);
  sel = add ? new Set(fresh.map(i => i.id)) : new Set();
  if (!add) {
    setFields({kind: e.k === "Symbol" ? F.kind.value : e.k, name: e.t, intent: e.i || "", damage: e.d || "", source: e.s || "", colour: e.p,
               second: e.p2 || "", frame: "", key: e.key || ""});
    status(`Opened ${e.t} (${fresh.length} strokes)`, "ok");
  } else status(`Added ${e.t} (${fresh.length} strokes)`, "ok");
  changed();
  if (!add) markSaved();                       // as the game (or the import) has it: nothing to lose yet
}
async function addPart(card, at = null) {
  const {S} = await strokesOf(card.icon);
  pushUndo();
  const fresh = card.labels.filter(l => S.has(l)).map(l => gameItem(card.icon, S.get(l), {name: card.sym ? `${card.sym} symbol · ${l}` : `Shape ${card.id} · ${l}`}));
  if (card.sym) {                              // a damage-type symbol: half size (the game draws them about a third of an icon)
    const b = bounds(fresh), c = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
    for (const it of fresh) it.m = mul(about(c, [.5, 0, 0, .5, 0, 0]), it.m);
    moveTo(fresh, at || [N / 2, N / 2]);
  } else if (at) moveTo(fresh, at);
  items.push(...fresh);
  sel = new Set(fresh.map(i => i.id));
  if (tool !== "select") setTool("select", true);
  let note = "";
  const d = BYNAME[card.icon]?.d;
  if (card.sym && d && !F.damage.value) {      // the symbol's colour: its damage type (Damage intent if none), so Auto matches the card
    F.damage.value = d;
    if (!F.intent.value) F.intent.value = "Damage";
    refreshFields();
    note = ` · damage type set to ${d}`;
  }
  status(`Added ${card.sym ? `the ${card.sym} symbol` : "a shape"}${note}`, "ok");
  changed();
}
// library filters: a search field and one-click chips (one choice; clicking the chosen category again shows all)
const SHORT = {"Damage types": "Damage", "Hands & arms": "Hands", "Skulls & bones": "Skulls", "Elements & nature": "Nature", "Sun, moon & stars": "Sky",
               "Rays & effects": "Rays", "Frames & rings": "Frames", "Symbols & marks": "Marks", "Shapes & lines": "Lines"};
const chips = (label, opts, cur) => `<div class="fchips" role="group" aria-label="${label}">${opts.map(([v, name, n]) =>
  `<button class="fchip" data-v="${esc(v)}" aria-pressed="${v === cur}" title="${esc(name)} (${n})">${esc(SHORT[name] || name)}<span>${n}</span></button>`).join("")}</div>`;
const partText = c => `${catOf(c)} ${c.sym || ""} ${c.icon} ${BYNAME[c.icon]?.t || ""} ${(c.from || []).join(" ")}`.toLowerCase();
const words = id => ($(id)?.value || "").toLowerCase().split(/\s+/).filter(Boolean);
function libTools() {
  const t = $("#libTools");
  if (tab === "icons") {
    const n = k => ICONS.filter(e => !k || e.k === k).length;
    t.innerHTML = `<input id="search" type="text" style="width:100%" placeholder="Search game icons" aria-label="Search game icons" value="${esc(store.get("search", ""))}">` +
      chips("Kind", [["", "All", n("")], ["Spell", "Spells", n("Spell")], ["Action", "Actions", n("Action")], ["Illithid", "Illithid", n("Illithid")], ["Symbol", "Symbols", n("Symbol")]], kindF);
  } else if (tab === "parts") {                // categories (eye-checked, editable by right-click); sections in "All"
    const vis = PARTS.filter(c => showHidden || !HIDDEN[c.key]), count = k => vis.filter(c => catOf(c) === k).length;
    const cats = [...CAT_ORDER, "Other"].filter(count);
    if (partCat !== "All" && !cats.includes(partCat)) partCat = "All";
    t.innerHTML = `<input id="psearch" type="text" style="width:100%" placeholder="Search shapes: glyph, fireball…" aria-label="Search shapes by category or game icon" value="${esc(store.get("psearch", ""))}">` +
      chips("Category", [["All", "All", vis.length], ...cats.map(k => [k, k, count(k)])], partCat) +
      `<label class="muted" style="display:block;margin-top:6px"><input type="checkbox" id="showHidden" ${showHidden ? "checked" : ""}> Show hidden shapes (${PARTS.filter(c => HIDDEN[c.key]).length})</label>`;
  }
  else if (tab === "mine") t.innerHTML = `<div class="row"><button class="btn primary f1" id="impFilesBtn" title="PNG, DDS, TGA, WebP or JPEG. Select several at once. Tooltip and controller files of the same icon are combined"><svg class="i" aria-hidden="true"><use href="#i-new"/></svg>Import files</button>
    <button class="btn f1" id="impDirBtn" title="Every icon in a mod folder (hotbar atlases and low-res copies are skipped)">Import folder</button></div>
    <label class="muted" style="display:block;margin-top:6px" title="Vector strokes stay sharp at large sizes and can be edited, but small details may change. You can also convert strokes later: right-click › Convert to vector strokes"><input type="checkbox" id="impVec" ${store.get("impVec", false) ? "checked" : ""}> Convert to vector strokes</label>`;
  else t.innerHTML = `<div class="row"><input id="draftName" class="f1" type="text" aria-label="Draft name" value="${esc(F.name.value)}">
    <button class="btn primary" id="saveHere"><svg class="i" aria-hidden="true"><use href="#i-save"/></svg>Save</button></div>`;
  $("#gridHint").textContent = {icons: "Click to open in a new tab · Shift-click or drag to add to this icon",
    parts: "Click or drag to add · right-click for options",
    drafts: "Click to open",
    mine: "Click to open in a new tab · drop files or folders here · right-click to remove"}[tab];
  $("#impFilesBtn")?.addEventListener("click", () => $("#impFiles").click());
  $("#impDirBtn")?.addEventListener("click", () => $("#impDir").click());
  $("#impVec")?.addEventListener("change", e => store.set("impVec", e.target.checked));
  $("#search")?.addEventListener("input", e => { store.set("search", e.target.value); fillGrid(); });
  $("#psearch")?.addEventListener("input", e => { store.set("psearch", e.target.value); fillGrid(); });
  $("#showHidden")?.addEventListener("change", e => { showHidden = e.target.checked; libTools(); fillGrid(); });
  for (const b of $$(".fchip", t)) b.onclick = () => {
    const v = b.dataset.v;
    if (tab === "icons") store.set("kindF", kindF = v);
    else store.set("partCat", partCat = v === partCat ? "All" : v);
    for (const c of $$(".fchip", t)) c.setAttribute("aria-pressed", c.dataset.v === (tab === "icons" ? kindF : partCat));
    fillGrid(); $("#grid").scrollTop = 0;
  };
  $("#saveHere")?.addEventListener("click", () => saveDraft($("#draftName").value));
}
function fillGrid() {
  const g = $("#grid");
  let html = "";
  if (tab === "icons") {
    const q = words("#search"), kf = kindF;
    for (const e of ICONS) {
      if (kf && e.k !== kf) continue;
      const hay = (e.t + " " + e.n).toLowerCase();
      if (q.some(w => !hay.includes(w))) continue;
      html += `<button class="cell" draggable="true" data-n="${esc(e.n)}" title="${esc(e.t)}&#10;${esc(e.n)}" aria-label="${esc(e.t)}" role="listitem"><img loading="lazy" src="/data/editor/thumbs/${encodeURIComponent(e.n)}.png" alt=""></button>`;
    }
    html ||= `<div class="muted empty">No game icons match “${esc(q.join(" "))}”${kf ? ` in ${esc(kf)}` : ""}.</div>`;
  } else if (tab === "parts") {
    const q = words("#psearch"), vis = PARTS.filter(c => (showHidden || !HIDDEN[c.key]) && !q.some(w => !partText(c).includes(w)));
    const card = c => {
      const hid = !!HIDDEN[c.key], what = c.sym ? `${c.sym} damage symbol` : `${catOf(c)} · used in ${c.icons} game icon${c.icons === 1 ? "" : "s"}`;
      return `<button class="cell part${hid ? " off" : ""}${c.sym ? " sym" : ""}" draggable="true" data-part="${esc(c.id)}" title="${esc(what)}${hid ? " (hidden)" : ""}&#10;Right-click: hide or change category" aria-label="${esc(what)}${hid ? ", hidden" : ""}" role="listitem"><img loading="lazy" src="/data/editor/parts/${encodeURIComponent(c.id)}.png" alt="">${c.sym ? `<span class="cap">${esc(c.sym)}</span>` : ""}</button>`;
    };
    for (const k of [...CAT_ORDER, "Other"]) {
      if (partCat !== "All" && k !== partCat) continue;
      const cs = vis.filter(c => catOf(c) === k);
      if (!cs.length) continue;
      if (partCat === "All") html += `<div class="sec" role="presentation">${esc(k)}<span>${cs.length}</span></div>`;
      html += cs.map(card).join("");
    }
    html ||= `<div class="muted empty">No shapes ${q.length ? `match “${esc(q.join(" "))}”${partCat !== "All" ? ` in ${esc(partCat)}` : ""}` : "in this category"}.</div>`;
  } else if (tab === "mine") {
    html = MINE.map(e => `<button class="cell${e.note ? " warn" : ""}" draggable="true" data-n="${esc(e.n)}" title="${esc(e.t)} (${esc(e.k)})&#10;${esc(e.used)}&#10;Colour: ${esc(e.p)}${e.custom ? " (taken from the icon)" : ""}${e.note ? "&#10;" + esc(e.note) : ""}" aria-label="${esc(e.t)}" role="listitem"><img loading="lazy" src="/imported/thumbs/${encodeURIComponent(e.n)}.png?v=${e.look}" alt="">${e.custom ? '<span class="cdot" aria-hidden="true"></span>' : ""}</button>`).join("")
      || `<div class="muted empty">No imported icons yet. Import your mod's icons to edit and export them again. They keep their names.</div>`;
  } else {
    html = drafts.map(d => `<button class="cell" data-draft="${esc(d.name)}" title="${esc(d.name)} · ${new Date(d.time * 1000).toLocaleString()}" aria-label="Draft ${esc(d.name)}" role="listitem">
      ${d.thumb ? `<img loading="lazy" src="/drafts/${encodeURIComponent(d.name)}.png?t=${d.time}" alt="">` : ""}<span class="cap">${esc(d.name)}</span></button>`).join("")
      || `<div class="muted empty">No drafts yet. Press Ctrl+S to save one.</div>`;
  }
  g.innerHTML = html;
}
async function setTab(t) {
  tab = t; store.set("tab", t);
  for (const [id, v] of [["#tabIcons", "icons"], ["#tabParts", "parts"], ["#tabMine", "mine"], ["#tabDrafts", "drafts"]]) { $(id).setAttribute("aria-selected", v === t); $(id).tabIndex = v === t ? 0 : -1; }
  libTools();
  if (t === "drafts") await listDrafts();
  fillGrid();
}
$("#tabIcons").onclick = () => setTab("icons"); $("#tabParts").onclick = () => setTab("parts"); $("#tabDrafts").onclick = () => setTab("drafts");
$("#tabMine").onclick = () => setTab("mine");
$(".tabs").addEventListener("keydown", e => {   // tab list keys: arrows move between the tabs, Home / End
  const order = ["icons", "parts", "mine", "drafts"], i = order.indexOf(tab), j = {ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: 3}[e.key];
  if (j == null) return;
  e.preventDefault(); e.stopPropagation();
  const t = order[(j + 4) % 4];
  setTab(t);
  $({icons: "#tabIcons", parts: "#tabParts", mine: "#tabMine", drafts: "#tabDrafts"}[t]).focus();
});
$("#grid").addEventListener("click", e => {
  const b = e.target.closest(".cell");
  if (!b) return;
  if (b.dataset.n) openIcon(b.dataset.n, e.shiftKey).catch(err => status(err.message, "err"));
  else if (b.dataset.part) addPart(partById(b.dataset.part)).catch(err => status(err.message, "err"));
  else if (b.dataset.draft) openDraft(b.dataset.draft);
});
$("#grid").addEventListener("contextmenu", e => {   // a part: hide / show it, or move it to another category (saved in git)
  const b = e.target.closest(".cell[data-part]");
  if (!b) return;
  e.preventDefault();
  const c = partById(b.dataset.part), hid = !!HIDDEN[c.key], cur = catOf(c);
  const save = async (q, msg) => {
    try { ({hidden: HIDDEN, cats: CATS} = await post("/api/parts_hidden", {key: c.key, ...q})); } catch (err) { return status(err.message, "err"); }
    status(msg, "ok"); libTools(); fillGrid();
  };
  openMenu(e.clientX, e.clientY, [
    {label: hid ? "Show this shape" : "Hide this shape", run: () => save({hidden: !hid}, hid ? "Shape shown" : "Shape hidden")},
    null, {head: "Category"},
    ...CAT_ORDER.map(k => ({label: k, checked: k === cur, run: () => save({cat: k}, `Moved to ${k}`)}))], "Shape");
});

// ---------------------------------------------------------------- import (user 7.0h): a modder's icons, in bulk
// Files are grouped by name (an icon's tooltip + controller DDS go together), sent a few icons at a time, converted by
// Python (import_req: joined / faded strokes rebuilt, colour matched or fitted, cut into strokes) and opened in tabs.
const IMG = /\.(png|dds|tga|webp|jpe?g)$/i, OPEN_MAX = 30;
const skipPath = p => /AssetsLowRes|Textures[\\/]Icons[\\/]/i.test(p);   // low-res copies, the hotbar atlas sheet
const asData = f => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => no(r.error); r.readAsDataURL(f); });
async function importFiles(files) {
  const groups = new Map();
  for (const {file, path} of files) {
    if (!IMG.test(file.name) || skipPath(path) || file.size > 32e6) continue;
    const stem = file.name.replace(/\.[^.]+$/, ""), k = stem.toLowerCase();
    if (!groups.has(k)) groups.set(k, {name: stem, files: []});
    groups.get(k).files.push({path, file});
  }
  const list = [...groups.values()];
  if (!list.length) return status("No icons found (PNG, DDS, TGA, WebP or JPEG)", "err");
  const done = [], errors = [];
  for (let i = 0; i < list.length; i += 3) {
    const batch = list.slice(i, i + 3);
    status(`Importing ${i + 1}-${Math.min(i + 3, list.length)} of ${list.length}: ${batch.map(b => b.name).join(", ")}…`);
    try {
      const icons = await Promise.all(batch.map(async b => ({name: b.name, files: await Promise.all(b.files.map(async x => ({path: x.path, data: await asData(x.file)})))})));
      const r = await post("/api/import", {icons});
      done.push(...r.icons); errors.push(...r.errors); applyRecipes(r.recipes);
    } catch (e) { errors.push(`${batch.map(b => b.name).join(", ")}: ${e.message}`); }
  }
  MINE = MINE.filter(e => !done.some(d => d.n === e.n)).concat(done);
  for (const e of done) { BYNAME[e.n] = e; strokeCache.delete(e.n); }
  await setTab("mine");
  let vn = 0, vof = 0;
  for (const e of done.slice(0, OPEN_MAX)) {
    await openIcon(e.n, false);
    if (store.get("impVec", false)) { const r = toVectors(items, true); if (r) { vn += r.n; vof += r.of; undoStack = []; } }
  }
  const custom = done.filter(e => e.custom).length, flagged = done.filter(e => e.note).length;
  status(`Imported ${done.length} of ${list.length} icon${list.length > 1 ? "s" : ""}` + (done.length > OPEN_MAX ? ` (the first ${OPEN_MAX} are open, the rest are under Imported)` : "") +
    (vof ? ` · ${vn} of ${vof} strokes converted to vector strokes` : "") + (custom ? ` · ${custom} with their own colour` : "") + (flagged ? ` · ${flagged} look different (marked)` : "") +
    (errors.length ? ` · ${errors.length} failed: ${errors.slice(0, 2).join("; ")}` : ""), errors.length ? "err" : "ok");
  if (errors.length) console.warn("[import]", errors);
}
const picked = input => importFiles([...input.files].map(f => ({file: f, path: f.webkitRelativePath || f.name}))).finally(() => { input.value = ""; });
$("#impFiles").addEventListener("change", e => picked(e.target));
$("#impDir").addEventListener("change", e => picked(e.target));
async function entryFiles(entry, path = "") {      // a dropped folder, read recursively
  if (entry.isFile) return [{file: await new Promise((ok, no) => entry.file(ok, no)), path: path + entry.name}];
  const r = entry.createReader(), out = [];
  for (let batch; (batch = await new Promise((ok, no) => r.readEntries(ok, no))).length;)
    for (const c of batch) out.push(...await entryFiles(c, path + entry.name + "/"));
  return out;
}
$("#left").addEventListener("dragover", e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } });
$("#left").addEventListener("drop", async e => {
  if (!e.dataTransfer.types.includes("Files")) return;
  e.preventDefault();
  const entries = [...e.dataTransfer.items].map(i => i.webkitGetAsEntry?.()).filter(Boolean);
  const files = entries.length ? (await Promise.all(entries.map(en => entryFiles(en)))).flat() : [...e.dataTransfer.files].map(f => ({file: f, path: f.name}));
  importFiles(files);
});
$("#grid").addEventListener("contextmenu", e => {   // an imported icon: open or remove it
  const b = tab === "mine" && e.target.closest(".cell[data-n]");
  if (!b) return;
  e.preventDefault();
  const n = b.dataset.n;
  openMenu(e.clientX, e.clientY, [{head: BYNAME[n].t}, {label: "Open in a new tab", run: () => openIcon(n, false)},
    {label: "Remove from Imported", run: async () => {
      try { MINE = (await post("/api/imported", {delete: n})).icons; } catch (err) { return status(err.message, "err"); }
      fillGrid(); status(`Removed ${BYNAME[n].t} from Imported`, "ok");
    }}], "Imported icon");
});
$("#grid").addEventListener("dragstart", e => {
  const b = e.target.closest(".cell");
  if (!b || b.dataset.draft) return;
  e.dataTransfer.setData("application/x-bg3icon", JSON.stringify(b.dataset.n ? {n: b.dataset.n} : {part: b.dataset.part}));
  e.dataTransfer.effectAllowed = "copy";
});
vp.addEventListener("dragover", e => { if (e.dataTransfer.types.includes("application/x-bg3icon")) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } });
vp.addEventListener("drop", e => {
  const d = e.dataTransfer.getData("application/x-bg3icon");
  if (!d) return;
  e.preventDefault();
  const q = JSON.parse(d), at = toDoc(e);
  (q.n ? openIcon(q.n, true, at) : addPart(partById(q.part), at)).catch(err => status(err.message, "err"));
});

// ---------------------------------------------------------------- drafts (game strokes by reference, vectors by settings)
const serializeState = s => ({v: 1, fields: s.fields, groups: s.groups, items: s.items.filter(i => i !== temp).map(it => ({
  type: it.type, name: it.name, icon: it.icon, label: it.label, vec: it.vec, m: it.m, erase: it.erase, second: it.second,
  hidden: it.hidden, locked: it.locked, g: it.g, barbs: it.type === "game" ? it.barbs : undefined, barbSeed: it.type === "game" ? it.barbSeed : undefined}))});
const serialize = () => serializeState(saveState());
async function itemsOf(doc) {                    // a saved drawing -> items (game strokes re-read from their icons)
  const out = [];
  for (const d of doc.items) {
    const extra = {name: d.name, m: d.m, erase: d.erase || [], second: !!d.second, hidden: !!d.hidden, locked: !!d.locked, ...(d.g ? {g: d.g} : {}),
                   ...(d.barbs != null ? {barbs: d.barbs, barbSeed: d.barbSeed} : {})};
    if (d.type === "game") { const {S} = await strokesOf(d.icon).catch(() => ({S: new Map()})); if (S.has(d.label)) out.push(gameItem(d.icon, S.get(d.label), extra)); }
    else out.push(vecItem(d.vec, extra));
  }
  return out;
}
async function deserialize(doc) {
  items = await itemsOf(doc); sel = new Set(); nodeSel = -1; GROUPS = structuredClone(doc.groups || {}); inGroup = null;
  setFields({...doc.fields, mod: F.mod.value});
  changed();
}
async function listDrafts() { try { drafts = (await post("/api/drafts", {})).drafts; } catch (e) { status(e.message, "err"); } }
function thumb() { const c = canvas(128); const x = c.getContext("2d"); x.imageSmoothingQuality = "high"; x.drawImage($("#gl"), 0, 0, 128, 128); return c.toDataURL("image/png"); }
async function saveDraft(name) {
  name = (name || F.name.value || "Draft").trim();
  try {
    const r = await post("/api/drafts", {name, doc: serialize(), thumb: thumb()});
    markSaved(cur, r.saved);
    status(`Saved draft "${r.saved}"`, "ok");
    hud(`Saved "${r.saved}"`);
    if (tab === "drafts") { await listDrafts(); fillGrid(); }
    return true;
  } catch (e) { status("Couldn't save: " + e.message, "err"); return false; }
}
async function openDraft(name) {
  try {
    const r = await post("/api/drafts", {name});
    if (!r.doc) return status("Draft not found", "err");
    if (items.length) newDoc(); else pushUndo();              // a tab of its own unless this one is empty
    await deserialize(r.doc); markSaved(cur, name); status(`Opened draft "${name}"`, "ok");
  } catch (e) { status("Couldn't open: " + e.message, "err"); }
}
// the autosave keeps every open tab (v 2) with its saved mark and draft name; a v 1 file is one drawing
const autosaveDoc = () => ({v: 2, cur, docs: docs.map((d, i) => ({...serializeState(i === cur ? saveState() : d.state), saved: d.saved, draft: d.draft}))});
async function autosave() { try { await post("/api/drafts", {name: "Autosave", doc: autosaveDoc()}); } catch { /* the next change retries */ } }

// ---------------------------------------------------------------- tabs: several icons open at once (Photoshop's documents)
// The open tab's drawing lives in the usual globals (items, sel, GROUPS, the fields, undo); the others keep theirs in
// docs[i].state. The mod name is shared by every tab. A tab is unsaved when its drawing differs from the one it was
// opened or last saved with (a hash of the saved form, so undoing back to it counts as saved). Closing asks only then.
let docs = [{state: null, saved: null, draft: null}], cur = 0, tabPick = new Set(), closedDocs = [];
const saveState = () => ({items, sel, groups: GROUPS, inGroup, fields: getFields(), undo: undoStack, redo: redoStack});
const blankFields = () => ({kind: F.kind.value, name: "New Icon", intent: "", damage: "", source: "", colour: "", second: "", frame: ""});
const blankState = (fields = {}) => ({items: [], sel: new Set(), groups: {}, inGroup: null, fields: {...blankFields(), ...fields}, undo: [], redo: []});
const fnv = s => { let h = 0x811c9dc5; for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619); return (h >>> 0).toString(36); };
const docSig = i => fnv(JSON.stringify(serializeState(i === cur ? saveState() : docs[i].state)));
const unsaved = i => docSig(i) !== docs[i].saved;
const docName = i => ((i === cur ? F.name.value : docs[i].state.fields.name) || "New Icon").trim();
const docCount = i => (i === cur ? items : docs[i].state.items).length;
function markSaved(i = cur, draft) { docs[i].saved = docSig(i); if (draft) docs[i].draft = draft; refreshDocTabs(); }
function loadState(s) {
  items = s.items; sel = s.sel; GROUPS = s.groups; inGroup = s.inGroup; undoStack = s.undo; redoStack = s.redo; nodeSel = -1; lastTag = null;
  setFields({...s.fields, mod: F.mod.value});
}
function switchDoc(i) {
  if (i === cur || !docs[i] || drag || pen) return;
  docs[cur].state = saveState();
  cur = i; loadState(docs[i].state); docs[i].state = null;
  changed(); refreshDocTabs();
}
function newDoc(fields = {}) {
  docs[cur].state = saveState();
  docs.push({state: null, saved: null, draft: null}); cur = docs.length - 1;
  loadState(blankState(fields));
  markSaved();                                   // an empty tab has nothing to lose
  changed();
}
// Close tabs: unsaved ones ask once (Save, Don't save, Cancel; with several, which to save). Closed tabs can be
// reopened (Ctrl+Alt+T, the tab menu): the last 10 of this session (in memory).
async function closeDocs(list) {
  list = [...new Set(list)].filter(i => docs[i]).sort((a, b) => a - b);
  if (!list.length || drag || pen) return;
  const dirty = list.filter(unsaved);
  if (dirty.length) {
    const save = await askUnsaved(dirty);
    if (!save) return;
    for (const i of save) if (!await saveDoc(i)) return;
  }
  for (const i of list) closedDocs.push({doc: serializeState(i === cur ? saveState() : docs[i].state), saved: docs[i].saved, draft: docs[i].draft});
  closedDocs = closedDocs.slice(-10);
  const keepCur = !list.includes(cur), curDoc = docs[cur];
  if (keepCur) docs[cur].state = saveState();
  docs = docs.filter((_, i) => !list.includes(i));
  tabPick.clear();
  if (!docs.length) { docs = [{state: null, saved: null, draft: null}]; cur = 0; loadState(blankState()); markSaved(); }
  else {
    cur = keepCur ? docs.indexOf(curDoc) : Math.min(list[0], docs.length - 1);
    loadState(docs[cur].state); docs[cur].state = null;
  }
  changed(); refreshDocTabs();
  status(list.length > 1 ? `Closed ${list.length} tabs · Ctrl+Alt+T reopens them` : "Tab closed · Ctrl+Alt+T reopens it", "ok");
}
const closeDoc = i => closeDocs([i]);
async function reopenDoc() {
  const c = closedDocs.pop();
  if (!c) return status("No closed tabs to reopen", "err");
  docs[cur].state = saveState();
  docs.push({state: {...blankState(c.doc.fields), items: await itemsOf(c.doc), groups: structuredClone(c.doc.groups || {})}, saved: c.saved, draft: c.draft});
  const i = docs.length - 1;
  cur = i; loadState(docs[i].state); docs[i].state = null;
  changed(); refreshDocTabs(); status(`Reopened ${docName(cur)}`, "ok");
}
async function saveDoc(i) {                      // a tab saved as its draft (its own name), then marked saved
  if (i !== cur) { switchDoc(i); render(); }
  return saveDraft(docs[i].draft && docs[i].draft === F.name.value.trim() ? docs[i].draft : undefined);
}
async function saveDocs(list) {
  const start = cur, todo = list.filter(i => docCount(i) || unsaved(i));
  let n = 0;
  for (const i of todo) if (await saveDoc(i)) n++;
  if (docs[start]) switchDoc(start);
  status(n ? `Saved ${n} tab${n > 1 ? "s" : ""} as drafts` : "Nothing to save", n ? "ok" : "");
}
async function duplicateDoc(i) {
  const s = serializeState(i === cur ? saveState() : docs[i].state);
  docs[cur].state = saveState();
  docs.splice(i + 1, 0, {state: {...blankState({...s.fields, name: `${s.fields.name || "New Icon"} copy`}), items: await itemsOf(s), groups: structuredClone(s.groups || {})}, saved: null, draft: null});
  cur = i + 1; loadState(docs[cur].state); docs[cur].state = null;
  changed(); refreshDocTabs();
}
function renameDoc(i) {                          // the tab's title becomes a field: Enter keeps, Esc cancels
  const el = $(`.dtab[data-i="${i}"] .t`);
  if (!el) return;
  const inp = document.createElement("input");
  Object.assign(inp, {type: "text", value: docName(i), className: "dren", spellcheck: false});
  inp.setAttribute("aria-label", "Icon name");
  el.replaceWith(inp); inp.focus(); inp.select();
  let done = false;
  const finish = keep => {
    if (done) return; done = true;
    const v = inp.value.trim();
    if (keep && v) { if (i === cur) { F.name.value = v; F.name.dispatchEvent(new Event("input")); } else docs[i].state.fields.name = v; autosave(); }
    refreshDocTabs();
  };
  inp.addEventListener("keydown", e => { e.stopPropagation(); if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); });
  inp.addEventListener("blur", () => finish(true));
}
function moveDoc(from, to) {                     // drag a tab to reorder
  if (from === to) return;
  const curDoc = docs[cur], [d] = docs.splice(from, 1);
  docs.splice(to, 0, d);
  cur = docs.indexOf(curDoc); tabPick.clear(); refreshDocTabs(); autosave();
}
// one dialog for unsaved tabs: one tab = Save / Don't save / Cancel; several = a ticked list of what to save
function askUnsaved(list) {
  const dlg = $("#unsavedDlg"), one = list.length === 1;
  $("#usTitle").textContent = one ? `Save changes to “${docName(list[0])}”?` : `Save changes to ${list.length} icons?`;
  $("#usText").textContent = one ? "Your changes are lost if you don't save them." : "Ticked icons are saved as drafts. The others lose their changes.";
  $("#usList").innerHTML = one ? "" : list.map(i => `<label class="chk"><input type="checkbox" data-i="${i}" checked><span>${esc(docName(i))}</span></label>`).join("");
  $("#usSave").textContent = one ? "Save" : "Save ticked";
  dlg.showModal();
  return new Promise(ok => {
    const end = v => { dlg.close(); ok(v); };
    $("#usSave").onclick = () => end(one ? list : $$("#usList input", dlg).filter(c => c.checked).map(c => +c.dataset.i));
    $("#usDiscard").onclick = () => end([]);
    $("#usCancel").onclick = () => end(null);
    dlg.oncancel = e => { e.preventDefault(); end(null); };
  });
}
function tabMenu(e, i) {
  e.preventDefault();
  if (!tabPick.has(i)) tabPick = new Set([i]);
  const list = [...tabPick].sort((a, b) => a - b), many = list.length > 1, n = many ? ` ${list.length} tabs` : "";
  const right = docs.map((_, j) => j).filter(j => j > Math.max(...list)), others = docs.map((_, j) => j).filter(j => !tabPick.has(j));
  const saved = docs.map((_, j) => j).filter(j => !unsaved(j));
  refreshDocTabs();
  openMenu(e.clientX, e.clientY, [{head: many ? `${list.length} tabs` : docName(i)},
    {label: `Save${n}`, keys: many ? "" : "Ctrl+S", run: () => saveDocs(list)},
    {label: "Save all tabs", keys: "Ctrl+Alt+S", run: () => saveDocs(docs.map((_, j) => j))},
    null,
    ...(many ? [] : [{label: "Rename", keys: "Double-click", run: () => renameDoc(i)}, {label: "Duplicate", run: () => duplicateDoc(i)}, null]),
    {label: `Close${n}`, keys: many ? "" : "Ctrl+Alt+W", run: () => closeDocs(list)},
    {label: "Close other tabs", off: !others.length, run: () => closeDocs(others)},
    {label: "Close tabs to the right", off: !right.length, run: () => closeDocs(right)},
    {label: "Close saved tabs", off: !saved.length, run: () => closeDocs(saved)},
    {label: "Close all tabs", run: () => closeDocs(docs.map((_, j) => j))},
    null,
    {label: "Reopen closed tab", keys: "Ctrl+Alt+T", off: !closedDocs.length, run: reopenDoc}], "Tab");
}
function refreshDocTabs() {
  $("#docTabs").innerHTML = docs.map((d, i) => {
    const f = i === cur ? null : d.state.fields, name = docName(i), n = docCount(i), c = f ? f.colour : preset(), u = unsaved(i);
    return `<div class="dtab${u ? " unsaved" : ""}${tabPick.has(i) ? " picked" : ""}" role="tab" draggable="true" data-i="${i}" tabindex="${i === cur ? 0 : -1}" aria-selected="${i === cur}" ` +
      `title="${esc(name)}&#10;${n} stroke${n === 1 ? "" : "s"}${u ? " · unsaved changes" : ""}&#10;Double-click: rename · Ctrl-click: select several · right-click: more">` +
      `<span class="dd" style="${c && PR[c] ? `background:${glowDot(c)}` : ""}"></span><span class="t">${esc(name)}</span>` +
      `<button class="x" data-close="${i}" tabindex="-1" aria-label="Close ${esc(name)}${u ? " (unsaved)" : ""}" title="Close (Ctrl+Alt+W)${u ? ": unsaved changes" : ""}">×</button></div>`;
  }).join("") + `<button class="dnew" id="docNew" title="New tab (Ctrl+Alt+N)" aria-label="New tab">+</button>`;
}
$("#docTabs").addEventListener("click", e => {
  const x = e.target.closest("[data-close]");
  if (x) return closeDoc(+x.dataset.close);
  if (e.target.closest("#docNew")) return newDoc();
  const t = e.target.closest(".dtab");
  if (!t || e.target.closest(".dren")) return;
  const i = +t.dataset.i;
  if (e.ctrlKey || e.metaKey) { tabPick.has(i) ? tabPick.delete(i) : tabPick.add(i); tabPick.add(cur); return refreshDocTabs(); }
  if (e.shiftKey) { tabPick = new Set(); for (let j = Math.min(i, cur); j <= Math.max(i, cur); j++) tabPick.add(j); return refreshDocTabs(); }
  tabPick.clear(); switchDoc(i); refreshDocTabs();
});
$("#docTabs").addEventListener("dblclick", e => { const t = e.target.closest(".dtab"); if (t && !e.target.closest("[data-close]")) renameDoc(+t.dataset.i); });
$("#docTabs").addEventListener("contextmenu", e => { const t = e.target.closest(".dtab"); if (t) tabMenu(e, +t.dataset.i); });
$("#docTabs").addEventListener("auxclick", e => { const t = e.target.closest(".dtab"); if (t && e.button === 1) { e.preventDefault(); closeDoc(+t.dataset.i); } });
$("#docTabs").addEventListener("dragstart", e => { const t = e.target.closest(".dtab"); if (t) { e.dataTransfer.setData("text/x-tab", t.dataset.i); e.dataTransfer.effectAllowed = "move"; } });
$("#docTabs").addEventListener("dragover", e => { if (e.dataTransfer.types.includes("text/x-tab")) e.preventDefault(); });
$("#docTabs").addEventListener("drop", e => {
  const from = e.dataTransfer.getData("text/x-tab");
  if (from === "") return;
  e.preventDefault();
  const t = e.target.closest(".dtab");
  moveDoc(+from, t ? +t.dataset.i : docs.length - 1);
});
$("#docTabs").addEventListener("keydown", e => {   // tab list keys: arrows move between the tabs, F2 renames, Delete closes
  if (e.target.closest(".dren")) return;
  if (e.key === "F2") { e.preventDefault(); return renameDoc(cur); }
  if (e.key === "Delete") { e.preventDefault(); return closeDoc(cur); }
  const j = {ArrowRight: cur + 1, ArrowLeft: cur - 1, Home: 0, End: docs.length - 1}[e.key];
  if (j == null) return;
  e.preventDefault(); e.stopPropagation();
  switchDoc((j + docs.length) % docs.length); $(`.dtab[data-i="${cur}"]`)?.focus();
});
F.name.addEventListener("input", refreshDocTabs);
async function restoreDocs(a) {                  // the autosave: every tab of the last session
  const states = [];
  for (const d of a.docs) states.push({state: {...blankState(d.fields), items: await itemsOf(d), groups: structuredClone(d.groups || {})}, saved: d.saved ?? null, draft: d.draft ?? null});
  docs = states;
  cur = clamp(a.cur | 0, 0, docs.length - 1);
  loadState(docs[cur].state); docs[cur].state = null;
  for (const [i, d] of a.docs.entries()) if (d.saved === undefined) docs[i].saved = docSig(i);   // an older autosave: as restored
  changed(); refreshDocTabs();
}

// ---------------------------------------------------------------- export (Python: variants.master, pngs, export)
// A game stroke enlarged for a big export (user 7.0i: vector strokes looked out of place next to game strokes, "due to
// its sharpness"). Smooth enlarging stretches the 512 px edge with the size (×4 at 2048: a 6 px blur), while vectors
// are drawn at full size. So after enlarging, the edge's alpha ramp is made k times steeper about one half: as sharp
// as at 512, like the vectors, the outline the smooth curve through the 512 px pixels. Only where the stroke is solid
// (its 512 px pixels nearby reach alpha .7+): faint and fading strokes stay as enlarged.
const solidNear = new WeakMap();                 // alpha -> its 3 x 3 maximum (the stroke is solid near this pixel)
const padded = new WeakMap();                    // bitmap -> a copy with a clear 1 px border: enlarged, a bitmap cropped to its
function crispUp(it, M, size) {                  // pixels was cut flat at its own edge (a flat-topped dot at 2048)
  let pb = padded.get(it.bmp);
  if (!pb) { pb = canvas(it.bmp.width + 2, it.bmp.height + 2); pb.getContext("2d").drawImage(it.bmp, 1, 1); padded.set(it.bmp, pb); }
  M = mul(M, [1, 0, 0, 1, -1, -1]);              // padded px -> drawing
  const P = [[0, 0], [it.w + 2, 0], [0, it.h + 2], [it.w + 2, it.h + 2]].map(([u, v]) => apply(M, u, v));
  const x0 = Math.max(0, Math.floor(Math.min(...P.map(p => p[0]))) - 2), y0 = Math.max(0, Math.floor(Math.min(...P.map(p => p[1]))) - 2);
  const w = Math.min(size, Math.ceil(Math.max(...P.map(p => p[0]))) + 2) - x0, h = Math.min(size, Math.ceil(Math.max(...P.map(p => p[1]))) + 2) - y0;
  const c = canvas(Math.max(1, w), Math.max(1, h)), x = ctx2d(c);
  if (w < 1 || h < 1) return {canvas: c, x0, y0};
  x.imageSmoothingEnabled = true; x.imageSmoothingQuality = "high";
  x.setTransform(M[0], M[1], M[2], M[3], M[4] - x0, M[5] - y0);
  x.filter = `blur(${(.4 * Math.hypot(M[0], M[1])).toFixed(2)}px)`;   // the 512 px edges are pixel steps (the line art has no soft
  x.drawImage(pb, 0, 0);                         // rim: it's the glow's): a little blur first, so the sharpened outline is a
  x.filter = "none";                             // smooth curve through the pixels, not their staircase (flat-sided dots at 2048)
  let near = solidNear.get(it.alpha);
  if (!near) {
    near = new Uint8Array(it.w * it.h);
    for (let v = 0; v < it.h; v++) for (let u = 0; u < it.w; u++) {
      let m = 0;
      for (let dv = -1; dv <= 1; dv++) for (let du = -1; du <= 1; du++) {
        const uu = u + du, vv = v + dv;
        if (uu >= 0 && vv >= 0 && uu < it.w && vv < it.h && it.alpha[vv * it.w + uu] > m) m = it.alpha[vv * it.w + uu];
      }
      near[v * it.w + u] = m;
    }
    solidNear.set(it.alpha, near);
  }
  const img = x.getImageData(0, 0, w, h), d = img.data, I = invert(M), k = Math.hypot(M[0], M[1]);
  for (let Y = 0; Y < h; Y++) for (let X = 0; X < w; X++) {
    const j = (Y * w + X) * 4, a = d[j + 3] / 255;
    if (a === 0 || a === 1) continue;
    const [u, v] = apply(I, X + x0 + .5, Y + y0 + .5), uu = Math.floor(u) - 1, vv = Math.floor(v) - 1;   // padded -> bitmap px
    if (uu < 0 || vv < 0 || uu >= it.w || vv >= it.h) continue;
    const s = clamp((near[vv * it.w + uu] / 255 - .7) / .25, 0, 1);   // 0 below .7 (faint), 1 from .95 (solid)
    if (!s) continue;
    d[j + 3] = Math.round(255 * (a + (clamp((a - .5) * k + .5, 0, 1) - a) * s));
  }
  x.putImageData(img, 0, 0);
  return {canvas: c, x0, y0};
}
function flatten(size) {                       // the drawing at size px: vectors re-rendered sharp, game strokes enlarged sharp
  const k = size / N, all = canvas(size), sec = second() ? canvas(size) : null;
  const xs = [all.getContext("2d"), sec?.getContext("2d")];
  for (const x of xs) if (x) { x.imageSmoothingEnabled = true; x.imageSmoothingQuality = "high"; x.globalCompositeOperation = "lighten"; }
  for (const it of items) {
    if (it.hidden) continue;
    let bmp, M;
    if (it.type === "vec") {
      const s = k * scaleOf(it.m), r = Brush.render(it.vec, s);
      bmp = r.canvas;
      if (it.erase.length) { const x = ctx2d(bmp); x.globalCompositeOperation = "destination-out"; for (const e of it.erase) eraseStroke(x, e, s, r.x0, r.y0); }
      M = mul([k, 0, 0, k, 0, 0], mul(it.m, [1 / s, 0, 0, 1 / s, r.x0 / s, r.y0 / s]));
    } else {
      M = mul([k, 0, 0, k, 0, 0], effM(it));
      if (k > 1) { const c = crispUp(it, M, size); bmp = c.canvas; M = [1, 0, 0, 1, c.x0, c.y0]; } else bmp = it.bmp;
    }
    for (const [x, on] of [[xs[0], true], [xs[1], it.second]]) if (x && on) { x.setTransform(...M); x.drawImage(bmp, 0, 0); }
  }
  return [all, sec];
}
function exportBody(what) {                    // the open tab's drawing as an /api/export request
  const p2 = second(), size = what.pngs ? +$("#pngSize").value : N;
  const body = {lineart: artAll.toDataURL("image/png"), mask: p2 ? artB.toDataURL("image/png") : null, kind: F.kind.value,
                name: F.name.value, mod: F.mod.value, key: F.key.value.trim(), preset: preset(), second: p2 || null, frame: frame(), what,
                fields: {intent: F.intent.value, damage: F.damage.value, source: F.source.value}};
  if (size > N) { const [a, s] = flatten(size); body.hires = {size, lineart: a.toDataURL("image/png"), mask: s ? s.toDataURL("image/png") : null}; }
  return body;
}
const exportWhat = () => ({mod: $("#xGame").checked, pngs: $("#xPngs").checked, lineart: $("#xLine").checked});
async function exportAll() {                   // every tab with strokes into the mod; the mod files are rebuilt once, at the end
  const what = exportWhat(), todo = docs.map((d, i) => i).filter(i => (i === cur ? items : docs[i].state.items).length);
  if (!what.mod && !what.pngs && !what.lineart) return status("Tick at least one kind of file to export", "err");
  if (!todo.length) return status("Nothing to export yet", "err");
  const names = todo.map(i => ((i === cur ? F.name.value : docs[i].state.fields.name) || "Icon").trim().toLowerCase());
  const dup = names.filter((n, j) => names.indexOf(n) !== j);
  if (dup.length) return status(`Two tabs are named "${dup[0]}". Rename one first`, "err");
  const start = cur;
  $("#exportAll").disabled = $("#export").disabled = true;
  let r, done = 0;
  try {
    for (const i of todo) {
      switchDoc(i); render();
      status(`Exporting ${++done} of ${todo.length}: ${F.name.value}…`);
      r = await post("/api/export", exportBody({...what, mod: what.mod && i === todo.at(-1)}));
    }
    $("#result").innerHTML = `<b>${todo.length} icons</b> → ${esc(r.dir)}${what.mod ? ` (${r.icons} icon${r.icons > 1 ? "s" : ""} in the mod)` : ""}`;
    status(`Exported ${todo.length} icons to ${r.dir}`, "ok"); hud(`Exported ${todo.length}`);
  } catch (e) { status(`Export stopped at ${F.name.value}: ${e.message}`, "err"); }
  switchDoc(start);
  $("#exportAll").disabled = $("#export").disabled = false;
}
$("#exportAll").onclick = exportAll;
async function exportIcon() {                 // the mod files, as ticked in the export dialog
  if (!items.length) return status("Nothing to export yet", "err");
  const what = exportWhat();
  if (!what.mod && !what.pngs && !what.lineart) return status("Tick at least one kind of file to export", "err");
  $("#export").disabled = true;
  status("Exporting…");
  try {
    const r = await post("/api/export", exportBody(what));
    $("#result").innerHTML = `<b>${esc(r.key)}</b> → ${esc(r.dir)}${what.mod ? ` (${r.icons} icon${r.icons > 1 ? "s" : ""} in the mod)` : ""}<br>` +
      `<img src="${r.controller}" width="72" alt="controller"><img src="${r.hotbar}" width="64" style="image-rendering:pixelated" alt="hotbar"><img src="${r.tooltip}" width="95" alt="tooltip"><br>` +
      r.files.slice(0, 8).map(esc).join("<br>") + (r.files.length > 8 ? `<br>… ${r.files.length - 8} more` : "");
    status(`Exported ${r.key}`, "ok");
    hud("Exported");
  } catch (e) { status("Couldn't export: " + e.message, "err"); }
  $("#export").disabled = false;
}
$("#export").onclick = exportIcon;

// ---------------------------------------------------------------- export dialog: one image to share (Photoshop's Export As)
// look x size x background, rendered by Python (the export path: exact, any size) a moment after each change and kept
// as a blob, so Copy writes it inside the click (browsers only allow clipboard images during the user's gesture)
const X = {look: "icon", size: 512, bg: "transparent", fmt: "png", ...store.get("xset", {})};
const XSIZES = [64, 128, 144, 256, 380, 512, 1024, 2048];
let xTimer = 0, xSeq = 0, xBlob = null, xFile = null, xName = "", xArt = null;   // xBlob: PNG (clipboard), xFile: the download
$("#xSizes").innerHTML = XSIZES.map(v => `<button class="btn" data-size="${v}">${v}</button>`).join("");
function xSync() {
  for (const b of $$("#xLook [data-look]")) b.setAttribute("aria-pressed", b.dataset.look === X.look);
  for (const b of $$("#xBg [data-bg]")) b.setAttribute("aria-pressed", b.dataset.bg === X.bg);
  for (const b of $$("#xSizes [data-size]")) b.setAttribute("aria-pressed", +b.dataset.size === X.size);
  for (const b of $$("#xFmt [data-fmt]")) b.setAttribute("aria-pressed", b.dataset.fmt === X.fmt);
  $("#xDownT").textContent = X.fmt === "webp" ? "Download WebP" : "Download PNG";
  $("#xSize").value = X.size;
  if (X.bg.startsWith("#")) $("#xBgC").value = X.bg;
  $("#xDir").textContent = `outputs/editor/${F.mod.value || "MyIcons"}/`;
  store.set("xset", X);
}
function xBody() {                            // the drawing's PNGs are made once per drawing state and size (the server keeps
  const p2 = second();                         // the painted image too: a background or file change only re-encodes)
  if (xArt?.rev !== artRev || xArt.size !== X.size || xArt.p2 !== !!p2) {
    xArt = {rev: artRev, size: X.size, p2: !!p2, lineart: artAll.toDataURL("image/png"), mask: p2 ? artB.toDataURL("image/png") : null};
    if (X.size > N) { const [a, s] = flatten(X.size); xArt.hires = {lineart: a.toDataURL("image/png"), mask: s ? s.toDataURL("image/png") : null}; }
  }
  return {lineart: xArt.lineart, mask: xArt.mask, kind: F.kind.value, name: F.name.value, preset: preset(), second: p2 || null, frame: frame(),
          look: X.look, size: X.size, bg: X.bg, format: X.fmt, hires: X.look !== "hotbar" ? xArt.hires : undefined};
}
async function xMake() {
  const seq = ++xSeq, t0 = performance.now();
  xBlob = xFile = null;
  $("#xCopy").disabled = $("#xDown").disabled = true;
  $("#xInfo").textContent = X.size > N ? `Rendering ${X.size} px…` : "Rendering…";
  try {
    const r = await post("/api/image", xBody());
    if (seq !== xSeq) return;
    xBlob = await (await fetch(r.png)).blob();
    xFile = r.webp ? await (await fetch(r.webp)).blob() : xBlob;
    xName = r.webp ? r.webpName : r.name;
    $("#xPrev").src = r.png;
    $("#xInfo").textContent = `${X.size} × ${X.size} px · ${X.fmt === "webp" ? "WebP" : "PNG"} ${Math.max(1, Math.round(xFile.size / 1024))} KB` +
      (performance.now() - t0 > 1500 ? ` · ${((performance.now() - t0) / 1000).toFixed(1)} s` : "");
    $("#xCopy").disabled = $("#xDown").disabled = false;
  } catch (e) { if (seq === xSeq) $("#xInfo").textContent = "Couldn't render: " + e.message; }
}
const xQueue = () => { xSync(); clearTimeout(xTimer); xTimer = setTimeout(xMake, 250); };
function openExport() {
  if (!items.length) return status("Nothing to export yet", "err");
  xSync();
  const n = docs.filter((d, i) => (i === cur ? items : d.state.items).length).length;
  $("#exportAllT").textContent = `Export all ${n} tabs`; $("#exportAll").hidden = n < 2;
  $("#exportDlg").showModal();
  xMake();
}
$("#exportTop").onclick = openExport;
$("#xLook").onclick = e => { const b = e.target.closest("[data-look]"); if (b) { X.look = b.dataset.look; xQueue(); } };
$("#xBg").onclick = e => { const b = e.target.closest("[data-bg]"); if (b) { X.bg = b.dataset.bg; xQueue(); } };
$("#xBgC").oninput = e => { X.bg = e.target.value; xQueue(); };
$("#xFmt").onclick = e => { const b = e.target.closest("[data-fmt]"); if (b) { X.fmt = b.dataset.fmt; xQueue(); } };
$("#xSizes").onclick = e => { const b = e.target.closest("[data-size]"); if (b) { X.size = +b.dataset.size; xQueue(); } };
$("#xSize").onchange = e => { X.size = clamp(Math.round(+e.target.value || 512), 16, 2048); xQueue(); };
F.mod.addEventListener("input", xSync);
$("#xPngs").onchange = e => { $("#pngSize").disabled = !e.target.checked; };
$("#xCopy").onclick = async () => {
  if (!xBlob) return;
  try { await navigator.clipboard.write([new ClipboardItem({"image/png": xBlob})]); status(`Copied (${X.size} px)`, "ok"); hud("Copied"); }
  catch (e) { status(`Your browser blocked copying (${e.message}). Use Download instead`, "err"); }
};
$("#xDown").onclick = () => {
  if (!xFile) return;
  const a = Object.assign(document.createElement("a"), {href: URL.createObjectURL(xFile), download: xName});
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  status(`Saved ${xName} to your downloads`, "ok");
};

// ---------------------------------------------------------------- tooltips (Photoshop's: name + shortcut + a line)
// Every [title] shows through one styled tip: after 450 ms on hover, at once while moving from one control to the
// next, and on keyboard focus. "Name (Keys): description" is laid out as name, key caps, description. The title moves
// to data-tip on first use, so the browser's own slow, unstyled tooltip never shows.
const tipEl = Object.assign(document.createElement("div"), {id: "tooltip", role: "tooltip"});
document.body.append(tipEl);
let tipTimer = 0, tipWarm = 0, tipFor = null;
const KEY = /^(Ctrl|Shift|Alt|Del|Esc|Enter|Tab|Space|Backspace|Home|End|[A-Z0-9?;]|[\[\]=+\-−]|)$/;
const isKeys = s => s.split(/\s*\/\s*/).every(c => c.split("+").every(t => KEY.test(t)));
const caps = s => s.split(/\s*\/\s*/).map(c => c.split(/\+(?=.)/).map(t => `<kbd>${esc(t)}</kbd>`).join("")).join(" <span class=\"or\">or</span> ");
for (const k of $$("kbd")) k.translate = false;   // keys stay as printed on the keyboard when the browser translates the page
function tipHTML(t) {
  const m = t.match(/^([^(:]{1,40}?)\s*\(([^()]{1,30})\)\s*(?::\s*([\s\S]*))?$/);
  if (m && isKeys(m[2])) return `<b>${esc(m[1])}</b><span class="keys" translate="no">${caps(m[2])}</span>${m[3] ? `<div class="desc">${esc(m[3])}</div>` : ""}`;
  const n = t.match(/^([^:.]{1,28}):\s+([\s\S]+)$/);
  return n ? `<b>${esc(n[1])}</b><div class="desc">${esc(n[2])}</div>` : esc(t);
}
function showTip(el) {
  if (!el.isConnected || !el.dataset.tip) return;
  el.setAttribute("aria-describedby", "tooltip");
  tipEl.innerHTML = tipHTML(el.dataset.tip);
  tipEl.classList.add("on");
  const r = el.getBoundingClientRect(), t = tipEl.getBoundingClientRect(), m = 8;
  let x, y;
  if (el.closest("#rail")) { x = r.right + 8; y = r.top + r.height / 2 - t.height / 2; }   // tool tips to the side
  else { x = r.left + r.width / 2 - t.width / 2; y = r.bottom + 8; if (y + t.height > innerHeight - m) y = r.top - t.height - 8; }
  tipEl.style.left = clamp(x, m, innerWidth - t.width - m) + "px";
  tipEl.style.top = clamp(y, m, innerHeight - t.height - m) + "px";
  tipFor = el;
}
function hideTip() { clearTimeout(tipTimer); if (tipFor) { tipWarm = performance.now(); tipFor.removeAttribute("aria-describedby"); } tipFor = null; tipEl.classList.remove("on"); }
const tipTarget = el => { const t = el?.closest?.("[title], [data-tip]"); if (t?.title) { t.dataset.tip = t.title; t.removeAttribute("title"); } return t; };
document.addEventListener("pointerover", e => {
  const el = tipTarget(e.target);
  if (el === tipFor) return;
  hideTip();
  if (!el || e.buttons) return;
  tipTimer = setTimeout(() => showTip(el), performance.now() - tipWarm < 400 ? 0 : 450);
});
document.addEventListener("pointerout", e => { if (tipFor && !tipFor.contains(e.relatedTarget)) hideTip(); else if (!tipFor) clearTimeout(tipTimer); });
document.addEventListener("focusin", e => { const el = tipTarget(e.target); hideTip(); if (el && e.target.matches(":focus-visible")) showTip(el); });
document.addEventListener("focusout", hideTip);
for (const ev of ["pointerdown", "wheel", "keydown"]) document.addEventListener(ev, e => { if (ev !== "keydown" || e.key === "Escape") hideTip(); }, true);

// ---------------------------------------------------------------- HUD: brush size, zoom, saves on the canvas (Photoshop)
const hudEl = Object.assign(document.createElement("div"), {id: "hud"});
hudEl.setAttribute("aria-hidden", "true");
vp.append(hudEl);
let hudTimer = 0;
function hud(text) { hudEl.textContent = text; hudEl.classList.add("on"); clearTimeout(hudTimer); hudTimer = setTimeout(() => hudEl.classList.remove("on"), 900); }
const userFit = () => { fit(); hud(`Fit · ${Math.round(view.z * 100)}%`); };

// ---------------------------------------------------------------- canvas context menu (right-click, Photoshop / Affinity)
const menuEl = Object.assign(document.createElement("div"), {id: "ctxmenu", hidden: true});
menuEl.setAttribute("role", "menu");
menuEl.setAttribute("aria-label", "Selection");
document.body.append(menuEl);
const selectAll = () => { sel = new Set(items.filter(i => !i.hidden && !i.locked).map(i => i.id)); changed(); };
const MENU = [                                   // [label, keys, action, needs a selection]; null = separator
  ["Duplicate", "Ctrl+J", () => cmds.dup(), 1], ["Delete", "Del", () => cmds.del(), 1], null,
  ["Group", "Ctrl+G", group, 1], ["Ungroup", "Ctrl+Shift+G", ungroup, 1], null,
  ["Convert to vector strokes", "", () => toVectors(), 1],
  ["Flip horizontally", "Shift+H", () => cmds.flipH(), 1], ["Flip vertically", "Shift+V", () => cmds.flipV(), 1],
  ["Rotate −15°", "Q", () => cmds.rotL(), 1], ["Rotate +15°", "W", () => cmds.rotR(), 1], null,
  ["Bring forward", "Ctrl+]", () => arrange(1), 1], ["Send backward", "Ctrl+[", () => arrange(-1), 1],
  ["Bring to front", "Ctrl+Shift+]", () => arrange(2), 1], ["Send to back", "Ctrl+Shift+[", () => arrange(-2), 1], null,
  ["Second colour on / off", "X", () => cmds.second(), 1], ["Centre on page", "", () => centrePage()], null,
  ["Select all", "Ctrl+A", selectAll], ["Deselect", "Ctrl+D", () => { sel.clear(); changed(); }, 1], null,
  ["Fit to window", "Ctrl+0", () => userFit()]];
let menuEntries = [];
const canvasEntries = () => MENU.map(m => m && {label: m[0], keys: m[1], run: m[2], off: m[3] && !sel.size});
function openMenu(x, y, entries = canvasEntries(), label = "Selection") {   // entries: {label, keys, run, off, checked} | {head} | null
  hideTip();
  menuEntries = entries;
  menuEl.setAttribute("aria-label", label);
  menuEl.innerHTML = entries.map((m, i) => !m ? "<hr>" : m.head ? `<div class="mh" role="presentation">${esc(m.head)}</div>` :
    `<button role="${m.checked == null ? "menuitem" : "menuitemradio"}" data-i="${i}"${m.off ? " disabled" : ""}${m.checked == null ? "" : ` aria-checked="${m.checked}"`}>${esc(m.label)}<span class="k" translate="no">${esc(m.keys || "")}</span></button>`).join("");
  menuEl.hidden = false;
  const r = menuEl.getBoundingClientRect();
  menuEl.style.left = clamp(x, 4, innerWidth - r.width - 4) + "px";
  menuEl.style.top = clamp(y, 4, innerHeight - r.height - 4) + "px";
  $("button:not(:disabled)", menuEl)?.focus();
}
function closeMenu(refocus = false) { if (menuEl.hidden) return; menuEl.hidden = true; if (refocus) vp.focus({preventScroll: true}); }
ov.addEventListener("contextmenu", e => {
  e.preventDefault();
  if (drag || pen) return;
  const h = hitItem(...toDoc(e));                // right-click a stroke: it becomes the selection
  if (h && !sel.has(h.id)) { sel = new Set([h.id]); changed(); }
  openMenu(e.clientX, e.clientY);
});
menuEl.addEventListener("click", e => {
  const b = e.target.closest("button:not(:disabled)");
  if (!b) return;
  closeMenu(true);
  menuEntries[+b.dataset.i].run();
});
menuEl.addEventListener("keydown", e => {
  const bs = $$("button:not(:disabled)", menuEl), i = bs.indexOf(document.activeElement);
  const j = {ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: bs.length - 1}[e.key];
  if (j != null) { e.preventDefault(); bs[(j + bs.length) % bs.length]?.focus(); }
  if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); closeMenu(true); }
  e.stopPropagation();                           // no tool / nudge shortcuts while the menu is open
});
document.addEventListener("pointerdown", e => { if (!menuEl.contains(e.target)) closeMenu(); }, true);
addEventListener("blur", () => closeMenu());
addEventListener("resize", () => closeMenu());

// ---------------------------------------------------------------- updates (iconkit/update.py): the newest release,
// downloaded and checked on request, installed by a restart (the open tabs are autosaved first and restored after)
let UPD = null;
async function checkUpdate(online = true) {   // online false: the version only, nothing leaves the computer
  const ask = action => post("/api/update", {action});
  try { UPD = await ask(online ? "check" : "version").catch(() => ask("version")); } catch { return; }   // offline: the version still shows
  $("#verLine").textContent = `Version ${UPD.version}${UPD.dev ? " (development)" : ""}`;
  const vt = $("#verTag");                       // the version, always in sight (user 2026-10-19); click: shortcuts + updates
  vt.hidden = false; vt.textContent = `v${UPD.version}`; vt.classList.toggle("new", !!UPD.newer);
  vt.title = `Version ${UPD.version}${UPD.dev ? " (development)" : ""}: ${UPD.newer ? `${UPD.latest} is available` : "click for updates and shortcuts"}`;
  const ready = UPD.staged || UPD.newer;
  $("#updBtn").hidden = !ready || !UPD.enabled;
  if (ready) $("#updBtnT").textContent = UPD.staged && !UPD.newer ? "Restart to update" : `Update to ${UPD.latest}`;
}
$("#updBtn").onclick = () => {
  if (!UPD) return;
  $("#updTitle").textContent = UPD.latest ? `Version ${UPD.latest} is available` : "Update ready";
  $("#updText").textContent = `You have version ${UPD.version}.`;
  $("#updNotes").textContent = UPD.notes || "";
  $("#updGo").disabled = false;
  $("#updateDlg").showModal();
};
$("#updLater").onclick = () => $("#updateDlg").close();
$("#verTag").onclick = () => UPD?.newer || UPD?.staged ? $("#updBtn").click() : $("#help").showModal();
$("#updGo").onclick = async () => {
  const say = t => $("#updState").textContent = t;
  $("#updGo").disabled = true;
  try {
    if (!UPD.staged || UPD.newer) { say("Downloading and checking the update…"); await post("/api/update", {action: "stage"}); }
    say("Saving your tabs…"); await autosave();
    say("Installing and restarting. The page reloads when it's done…");
    await post("/api/update", {action: "restart"});
    const from = UPD.version, t0 = performance.now();
    while (performance.now() - t0 < 180e3) {         // the server is back on the new version: reload
      await new Promise(r => setTimeout(r, 1500));
      try { const r = await post("/api/update", {action: "check"}); if (r.version !== from) return location.reload(); } catch { /* restarting */ }
    }
    say("The editor didn't come back. Check its window, then reload this page.");
  } catch (e) { say("Couldn't update: " + e.message); $("#updGo").disabled = false; }
};
$("#updAuto").checked = store.get("updates", true);
$("#updAuto").onchange = e => { store.set("updates", e.target.checked); checkUpdate(e.target.checked); };

// ---------------------------------------------------------------- top bar, docks, splitters, keys
$("#undo").onclick = undo; $("#redo").onclick = redo;
$("#newDoc").onclick = () => newDoc();
$("#saveDraft").onclick = () => saveDoc(cur);
$("#zoomIn").onclick = () => zoomAt(1.25); $("#zoomOut").onclick = () => zoomAt(.8); $("#zoomFit").onclick = userFit; $("#zoomv").onclick = userFit;
$("#bg").value = store.get("bg", "dark");
const setBg = v => { stage.className = stage.className.replace(/\bbg-\w+/g, "").trim() + " bg-" + v; store.set("bg", v); };
setBg($("#bg").value);
$("#bg").onchange = e => setBg(e.target.value);
function toggleLine() { lineView = !lineView; stage.classList.toggle("lines", lineView); $("#lineView").setAttribute("aria-pressed", lineView); invalidate(); }
$("#lineView").onclick = toggleLine;
function setSnap(on) { snapOn = on; store.set("snap", on); $("#snapBtn").setAttribute("aria-pressed", on); }
setSnap(snapOn);
$("#snapBtn").onclick = () => { setSnap(!snapOn); hud(snapOn ? "Snapping on" : "Snapping off"); };
$("#helpBtn").onclick = () => $("#help").showModal();
const app = $("#app");
function dock(side, show) {
  app.classList.toggle(side === "left" ? "noleft" : "noright", !show);
  $(side === "left" ? "#togLeft" : "#togRight").setAttribute("aria-pressed", show);
  store.set("dock." + side, show);
}
$("#togLeft").onclick = () => dock("left", app.classList.contains("noleft"));
$("#togRight").onclick = () => dock("right", app.classList.contains("noright"));
dock("left", store.get("dock.left", true)); dock("right", store.get("dock.right", true));
for (const [id, v, lo, hi, sign] of [["#splitL", "--lw", 180, 560, 1], ["#splitR", "--rw", 250, 620, -1]]) {
  const el = $(id), get = () => parseInt(getComputedStyle(app).getPropertyValue(v)),
        set = w => { w = clamp(w, lo, hi); app.style.setProperty(v, w + "px"); el.setAttribute("aria-valuenow", w); store.set(v, w); };
  if (store.get(v)) set(store.get(v));
  el.setAttribute("aria-valuemin", lo); el.setAttribute("aria-valuemax", hi);
  el.addEventListener("pointerdown", e => {
    try { el.setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
    const x0 = e.clientX, w0 = get();
    el.onpointermove = ev => set(w0 + sign * (ev.clientX - x0));
    el.onpointerup = () => { el.onpointermove = null; };
  });
  const reset = () => { app.style.removeProperty(v); store.set(v, null); el.setAttribute("aria-valuenow", get()); };   // the CSS default width
  el.addEventListener("keydown", e => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); set(get() + sign * (e.key === "ArrowRight" ? 16 : -16)); }
    if (e.key === "Backspace" || e.key === "Delete") { e.preventDefault(); e.stopPropagation(); reset(); }
  });
  el.addEventListener("dblclick", reset);
  el.setAttribute("aria-valuenow", get());
}
{                                              // the Layers panel's height: drag the line above it (kept per browser)
  const el = $("#splitLayers"), right = $("#right"), lay = $("#pnLayers");
  const set = h => {
    h = clamp(Math.round(h), 110, Math.max(110, right.getBoundingClientRect().height - 170));
    right.style.setProperty("--lh", h + "px"); store.set("lh", h); el.setAttribute("aria-valuenow", h);
  };
  const reset = () => { right.style.removeProperty("--lh"); store.set("lh", null); };
  if (store.get("lh")) set(store.get("lh"));
  el.addEventListener("pointerdown", e => {
    try { el.setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
    const y0 = e.clientY, h0 = lay.getBoundingClientRect().height;
    el.onpointermove = ev => set(h0 - (ev.clientY - y0));
    el.onpointerup = () => { el.onpointermove = null; };
  });
  el.addEventListener("keydown", e => {
    if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); set(lay.getBoundingClientRect().height + (e.key === "ArrowUp" ? 16 : -16)); }
    if (e.key === "Backspace" || e.key === "Delete") { e.preventDefault(); e.stopPropagation(); reset(); }
  });
  el.addEventListener("dblclick", reset);
}
document.addEventListener("keydown", e => {
  const typing = e.target.closest?.("input, select, textarea") && !["range", "checkbox"].includes(e.target.type);
  const k = e.key.toLowerCase(), ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && k === "s" && !e.altKey) { e.preventDefault(); return saveDoc(cur); }
  if (ctrl && k === "e") { e.preventDefault(); return $("#exportDlg").open ? exportIcon() : openExport(); }
  if (typing || $("#help").open || $("#exportDlg").open || $("#colourDlg").open || $("#unsavedDlg").open || $("#updateDlg").open) return;
  if ((k === "backspace" || k === "delete") && e.target.matches?.("#opts input[type=range]")) { e.preventDefault(); return resetSlider(e.target); }
  if (e.key === " ") { e.preventDefault(); if (!spaceDown) { spaceDown = true; ov.style.cursor = "grab"; } return; }
  if (ctrl && e.shiftKey && e.code === "Semicolon") { e.preventDefault(); return $("#snapBtn").click(); }   // any layout
  if (ctrl) {
    const map = {z: () => e.shiftKey ? redo() : undo(), y: redo, j: cmds.dup, a: selectAll, g: () => e.shiftKey ? ungroup() : group(),
                 d: () => { sel.clear(); changed(); }, l: toggleLine, 0: userFit, 1: () => zoomAt(1 / view.z), "=": () => zoomAt(1.25), "+": () => zoomAt(1.25),
                 "-": () => zoomAt(.8), "]": () => arrange(e.shiftKey ? 2 : 1), "[": () => arrange(e.shiftKey ? -2 : -1),
                 "}": () => arrange(2), "{": () => arrange(-2),             // Shift+] / Shift+[ arrive as } / {
                 ...(e.altKey ? {n: () => newDoc(), w: () => closeDocs(tabPick.size > 1 ? [...tabPick] : [cur]),   // Ctrl+Alt+N / W / T (Ctrl+N / W / T belong to the browser)
                                 t: reopenDoc, s: () => saveDocs(docs.map((_, j) => j)),
                                 arrowleft: () => switchDoc((cur + docs.length - 1) % docs.length), arrowright: () => switchDoc((cur + 1) % docs.length)} : {})};
    if (map[k]) { e.preventDefault(); map[k](); }
    return;
  }
  if (k === "tab") { e.preventDefault(); const show = app.classList.contains("noleft") && app.classList.contains("noright"); dock("left", show); dock("right", show); return; }
  if (e.key === "?") return $("#help").showModal();
  if (k === "delete" || k === "backspace") {
    e.preventDefault();
    if (pen?.pts.length) { pen.pts.pop(); pen.corner.pop(); penPreview(); return drawOverlay(); }
    const np = nodeItem();
    if (np && nodeSel >= 0) {
      if (np.vec.pts.length <= 2) return status("A path needs at least two points", "err");
      pushUndo(); np.vec.pts.splice(nodeSel, 1); np.vec.corner.splice(nodeSel, 1); nodeSel = -1; rerender(np); return changed();
    }
    return cmds.del();
  }
  if (k === "escape") {
    if (pen) { pen = null; items = items.filter(i => i !== temp); temp = null; return changed(); }
    if (inGroup) { const g = inGroup; inGroup = null; sel = new Set(members(g).filter(i => !i.hidden && !i.locked).map(i => i.id)); return changed(); }   // out of the group, the group picked
    sel.clear(); nodeSel = -1; return changed();
  }
  if (k === "enter" && pen) return finishPen();
  const arrows = {arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, -1], arrowdown: [0, 1]};
  if (arrows[k] && sel.size) { e.preventDefault(); const s = e.shiftKey ? 10 : 1; return translate(arrows[k][0] * s, arrows[k][1] * s); }
  if (e.shiftKey && k === "h") return cmds.flipH();
  if (e.shiftKey && k === "v") return cmds.flipV();
  if (k === "q") return cmds.rotL();
  if (k === "w") return cmds.rotR();
  if (k === "x") return cmds.second();
  if (k === "[" || k === "]") {
    const key = tool === "eraser" ? "eraser" : "width", f = k === "]" ? 1.15 : 1 / 1.15;
    const nv = Math.round(ST[key] * f);                   // at least 1 px a press (2 x 1.15 rounds back to 2)
    ST[key] = clamp(nv === ST[key] ? nv + (k === "]" ? 1 : -1) : nv, 2, key === "eraser" ? 120 : 60); store.set("stroke", ST);
    hud(`${key === "eraser" ? "Eraser" : "Width"} ${ST[key]} px`);
    const vs = vecSel();
    if (key === "width" && vs.length && tool === "select") { pushUndo("vec:width"); for (const it of vs) { it.vec.width = ST.width; rerender(it); } invalidate(); }
    refreshOpts(); return drawOverlay();
  }
  if (TOOL_KEYS[k] && !e.shiftKey && !e.altKey) return setTool(TOOL_KEYS[k]);
});
document.addEventListener("keyup", e => { if (e.key === " ") { spaceDown = false; ov.style.cursor = {select: "default", node: "default", hand: "grab", eraser: "none", brush: "none"}[tool] || "crosshair"; } });

// ---------------------------------------------------------------- tests: ?golden (WebGL vs variants.master), ?brushtest
async function golden() {
  const want = +new URLSearchParams(location.search).get("golden") || 0;
  const names = ICONS.filter(e => e.split === "holdout").map(e => e.n).concat(ICONS.filter(e => e.p2).map(e => e.n));
  const list = want ? names.slice(0, want) : names, rows = [];
  for (const n of list) {
    await openIcon(n, false);
    render();
    const {la} = await strokesOf(n), a = artAll.getContext("2d").getImageData(0, 0, N, N).data;
    let off = 0;                                // composed strokes vs the cut line art (alpha exact; grey where opaque)
    for (let i = 0; i < N * N; i++) if (a[i * 4 + 3] !== la[i * 4 + 1] || (la[i * 4 + 1] === 255 && a[i * 4] !== la[i * 4])) off++;
    const p2 = second();
    const r = await post("/api/golden", {icon: n, lineart: artAll.toDataURL("image/png"), mask: p2 ? artB.toDataURL("image/png") : null,
      master: $("#gl").toDataURL("image/png"), kind: F.kind.value, preset: preset(), second: p2 || null, ms: +painter.ms.toFixed(2)});
    rows.push({n, off, two: !!p2, ms: painter.ms, ...r});
    status(`golden ${rows.length}/${list.length}: ${n} L* ${r.L128} (512: ${r.L512}), max ${r.L_max}, strokes off ${off} px`);
  }
  const med = (k, rs) => { const v = rs.map(r => r[k]).sort((a, b) => a - b); return v.length ? v[(v.length - 1) >> 1] : null; };
  const one = rows.filter(r => !r.two), two = rows.filter(r => r.two);
  window.goldenResult = {n: rows.length, one: {n: one.length, L128: med("L128", one), L512: med("L512", one), L_max: Math.max(...one.map(r => r.L_max)), off_max: Math.max(...one.map(r => r.off)), ms: med("ms", one)},
                         two: {n: two.length, L128: med("L128", two), L512: med("L512", two), L_max: Math.max(...two.map(r => r.L_max))}, rows};
  status(`golden done: ${JSON.stringify({one: window.goldenResult.one, two: window.goldenResult.two})}`);
}
// /?barbsheet=ICON,ICON...: per icon as drawn | its strokes' barbs cut | restyled at its kind's barbs | a brush zigzag
// with them; saved to the drafts folder as barbsheet.png (look at barbs by eye against the game's)
async function barbsheet() {
  const names = Q.get("barbsheet").split(",").filter(Boolean), S = 512, sheet = canvas(4 * S, names.length * S), sx = ctx2d(sheet);
  sx.fillStyle = "#000"; sx.fillRect(0, 0, sheet.width, sheet.height);
  const dens = {};   // barbs per 100 px as measured: as drawn, cut, restyled
  for (const [r, n] of names.entries()) {
    const {S: strokes} = await strokesOf(n), its = [...strokes.values()].map(s => gameItem(n, s)), kb = KIND_BARBS[BYNAME[n]?.k] ?? 3.1;
    for (const [c, b] of [[0, null], [1, 0], [2, kb]]) {
      sx.save(); sx.translate(c * S, r * S); sx.beginPath(); sx.rect(0, 0, S, S); sx.clip(); sx.globalCompositeOperation = "lighten";
      for (const it of its) { if (b == null) delete it.barbs; else { it.barbs = b; it.barbSeed = 7; } bake(it); sx.drawImage(it.bmp, it.ox, it.oy); }
      const px = sx.getImageData(c * S, r * S, S, S).data;   // white lines on black: red = alpha
      const big = its.reduce((a, it) => it.baseAlpha.length > a.baseAlpha.length ? it : a);   // and its largest stroke alone
      dens[n] = [...(dens[n] || []), +barbDensity(new Uint8Array(S * S).map((_, i) => px[i * 4]), S, S).toFixed(2) + " / " + barbDensity(big.alpha, big.w, big.h).toFixed(2)];
      sx.restore();
    }
    const zz = Brush.render({kind: "path", pts: [[80, 90], [300, 160], [180, 260], [430, 330], [300, 440]], corner: [false, true, true, true, false], curve: 1, closed: false,
                             width: 14, rough: 1, taperStart: true, taperEnd: true, tip: .32, smooth: .5, seed: 3 + r, barbs: kb});
    sx.save(); sx.globalCompositeOperation = "lighten"; sx.drawImage(zz.canvas, 3 * S + zz.x0, r * S + zz.y0); sx.restore();
  }
  await post("/api/drafts", {name: "barbsheet", doc: {}, thumb: sheet.toDataURL("image/png")});
  window.barbsheetDone = dens;
  status("barbsheet saved");
}
async function brushtest() {                   // the brush on the game's own centre lines, measured like the game (server)
  const {sections} = await post("/api/brush_samples", {}), renders = {};
  const png = r => {                           // opaque RGB: grey, alpha (exact through PNG)
    const c = canvas(r.w, r.h), x = c.getContext("2d"), src = ctx2d(r.canvas).getImageData(0, 0, r.w, r.h).data, img = x.createImageData(r.w, r.h);
    for (let i = 0; i < r.w * r.h; i++) { img.data[i * 4] = src[i * 4]; img.data[i * 4 + 1] = src[i * 4 + 3]; img.data[i * 4 + 3] = 255; }
    x.putImageData(img, 0, 0);
    return c.toDataURL("image/png");
  };
  // smooth, rough (no barbs), and rough with the barbs of the section's icon kind (what a new stroke draws)
  for (const [tag, rough, barbs] of [["smooth", 0, false], ["rough", 1, false], ["barbs", 1, true]]) renders[tag] = sections.map(s => {
    const r = Brush.render({kind: "free", raw: true, pts: s.path, width: s.width, rough, taperStart: false, taperEnd: false, tip: 1, seed: s.i + 1,
                            barbs: barbs ? KIND_BARBS[s.kind] : 0});
    return {i: s.i, png: png(r), x0: r.x0, y0: r.y0};
  });
  window.brushResult = await post("/api/brush_measure", {renders});
  // barbs per 100 px as the game's icons are measured (research/probes/barbs.py, vectorize.barbDensity): closed circles
  // (no ends, whose cut corners would count as barbs), the game's width, 20 seeds per setting
  const circle = (barbs, seed) => ({kind: "path", pts: Array.from({length: 24}, (_, j) => [200 + 120 * Math.cos(j * Math.PI / 12), 200 + 120 * Math.sin(j * Math.PI / 12)]),
    corner: Array(24).fill(false), curve: 1, closed: true, width: 14, rough: 1, taperStart: false, taperEnd: false, tip: .32, seed, barbs});
  const bd = {};
  for (const b of [0, 1, 2, 3.1, 4]) { const v = []; for (let sd = 1; sd <= 20; sd++) { const r = Brush.render(circle(b, sd)); v.push(barbDensity(r.alpha, r.w, r.h)); }
    bd[b] = +(v.reduce((a, c) => a + c, 0) / v.length).toFixed(2); }
  window.brushResult.barb_density = bd;
  status("brushtest: " + JSON.stringify(window.brushResult));
}

const MOUSE_ID = navigator.userAgent.includes("Firefox") ? 0 : 1;   // the mouse's pointerId: Firefox 0, Chromium 1
async function perftest() {                    // ?perftest[=px][&w=width]: a long freehand spiral over Fireball, default brush.
  // Per pointermove: the work until its frame is painted (frames run by hand, so it also works in a hidden tab; the
  // preview ends in gl.finish, the small previews are read back). Result in window.perfResult and the status line.
  await openIcon("Spell_Evocation_Fireball", false);
  render();
  Object.assign(ST, DEF, Q.get("w") ? {width: +Q.get("w")} : {});   // &w=: brush width
  setTool("brush", true);
  const len = +Q.get("perftest") || 5000, step = 4, pts = [];
  for (let s = 0; s <= len; s += step) { const r = 40 + 180 * s / len, t = len / 180 * Math.log(r / 40); pts.push([256 + r * Math.cos(t), 256 + r * Math.sin(t)]); }
  const raf = window.requestAnimationFrame, frames = [];
  window.requestAnimationFrame = cb => frames.push(cb);
  const flush = () => { while (frames.length) frames.shift()(performance.now()); timed("readback", () => $("#ctrl").getContext("2d").getImageData(0, 0, 1, 1)); };
  const r = ov.getBoundingClientRect(), ev = (type, [x, y]) => ov.dispatchEvent(new PointerEvent(type, {bubbles: true, pointerId: MOUSE_ID,
    isPrimary: true, button: 0, buttons: type === "pointerup" ? 0 : 1, clientX: r.left + view.x + x * view.z, clientY: r.top + view.y + y * view.z}));
  const ms = [];
  let up = 0, fastOff = null;
  try {
    ev("pointerdown", pts[0]); flush();
    for (const k in prof) delete prof[k];
    for (const p of pts.slice(1)) { const t = performance.now(); ev("pointermove", p); flush(); ms.push(performance.now() - t); }
    if (liveArt) {                               // the fast path's composite = a whole compose of the same frame
      const px = c => ctx2d(c).getImageData(0, 0, N, N).data, a = px(liveArt), b = px(compose(cpuCanvas(N), [temp], under[0]));
      fastOff = 0;
      for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) fastOff++;
    }
    const t = performance.now(); ev("pointerup", pts.at(-1)); flush(); up = performance.now() - t;
  } finally { window.requestAnimationFrame = raf; }
  const q = (v, f) => { const s = v.slice().sort((a, b) => a - b); return +s[Math.min(s.length - 1, Math.floor(f * s.length))].toFixed(2); };
  const k = Math.round(500 / step);                // first / last 500 px of the stroke
  window.perfResult = {px: len, moves: ms.length, strokes: items.length, p50: q(ms, .5), p90: q(ms, .9), max: q(ms, 1),
                       first500_p50: q(ms.slice(0, k), .5), last500_p50: q(ms.slice(-k), .5), pointerup: +up.toFixed(1), fast_path_bytes_off: fastOff,
                       parts: Object.fromEntries(Object.entries(prof).map(([p, v]) => [p, +(v / (ms.length + 1)).toFixed(2)]))};
  window.perfMs = ms;
  const sum = Object.values(window.perfResult.parts).reduce((a, b) => a + b, 0);
  window.perfResult.parts.other = +(ms.reduce((a, b) => a + b, 0) / ms.length - sum).toFixed(2);   // input handler, overlay events
  status("perftest: " + JSON.stringify(window.perfResult));
}
// &rt: real frames (needs a browser that animates: not a hidden tab). One mouse move per animation frame, like a hand,
// first hovering with the brush, then drawing the same path: frame intervals and main-thread time per frame for both.
// "As smooth as hovering" = the drawing row matches the hovering row.
async function perfRealtime() {
  await openIcon("Spell_Evocation_Fireball", false);
  Object.assign(ST, DEF, Q.get("w") ? {width: +Q.get("w")} : {});
  setTool("brush", true);
  const len = +Q.get("perftest") || 3000, step = 4, pts = [];
  for (let s = 0; s <= len; s += step) { const r = 40 + 180 * s / len, t = len / 180 * Math.log(r / 40); pts.push([256 + r * Math.cos(t), 256 + r * Math.sin(t)]); }
  const frame = () => new Promise(r => requestAnimationFrame(r)), r = ov.getBoundingClientRect();
  const ev = (type, [x, y], down) => ov.dispatchEvent(new PointerEvent(type, {bubbles: true, pointerId: MOUSE_ID, isPrimary: true, button: 0,
    buttons: down ? 1 : 0, clientX: r.left + view.x + x * view.z, clientY: r.top + view.y + y * view.z}));
  for (let i = 0; i < 30; i++) await frame();
  const q = (v, f) => { const s = v.slice().sort((a, b) => a - b); return +s[Math.min(s.length - 1, Math.floor(f * s.length))].toFixed(2); };
  const run = async down => {
    for (const k in prof) delete prof[k];
    if (down) ev("pointerdown", pts[0], true);
    const dt = [];
    let last = await frame();
    for (const p of pts) { ev("pointermove", p, down); const t = await frame(); dt.push(t - last); last = t; }
    const med = q(dt, .5), js = Object.values(prof).reduce((a, b) => a + b, 0) / dt.length;
    let release = null;                        // the frame that shows the release (full repaint, previews)
    if (down) { ev("pointerup", pts.at(-1), false); release = +((await frame()) - last).toFixed(1); }
    return {frames: dt.length, interval_p50: med, p90: q(dt, .9), max: q(dt, 1), slow: dt.filter(v => v > med * 1.5).length, release,
            render_ms: +js.toFixed(2), parts: Object.fromEntries(Object.entries(prof).map(([p, v]) => [p, +(v / dt.length).toFixed(2)]))};
  };
  const hover = await run(false);
  for (let i = 0; i < 30; i++) await frame();
  const draw = await run(true);
  // moving: every stroke selected, dragged along a small circle (the drawing's own render path, not the brush's)
  for (let i = 0; i < 30; i++) await frame();
  setTool("select", true);
  selectAll();
  let grab = null;
  for (let y = 40; y < N && !grab; y += 8) for (let x = 40; x < N && !grab; x += 8) if (hitItem(x, y)) grab = [x, y];
  const path = Array.from({length: 240}, (_, k) => [grab[0] + 30 * Math.sin(k / 20), grab[1] + 30 * (1 - Math.cos(k / 20))]);
  pts.splice(0, pts.length, grab, ...path);
  const move = await run(true);
  window.perfResult = {mode: "realtime", px: len, width: ST.width, hover, draw, move};
  status("perftest rt: " + JSON.stringify({hover: hover.interval_p50, draw: draw.interval_p50, drawSlow: draw.slow, move: move.interval_p50}));
}
const browserName = () => (navigator.userAgent.match(/(Firefox|Edg|Chrome)\/[\d.]+/g) || ["?"]).join(" ");
async function runPerf() {                     // results also go to the server: data/editor/perf.json (headless runs)
  const rt = Q.has("rt");
  try { await (rt ? perfRealtime() : perftest()); post("/api/perf", {mode: rt ? "realtime" : "frames", browser: browserName(), result: window.perfResult}).catch(() => {}); }
  catch (e) { status("perftest: " + e.message, "err"); post("/api/perf", {mode: rt ? "realtime" : "frames", browser: browserName(), error: String(e.stack || e)}).catch(() => {}); }
}

// ---------------------------------------------------------------- start
mark("setup");
refreshFields(); setTool("select", true); refreshLayers(); refreshProps();
await setTab(tab);
mark("ui");
if (GOLDEN) golden().catch(e => status("golden: " + e.message, "err"));
else if (BRUSHTEST) brushtest().catch(e => status("brushtest: " + e.message, "err"));
else if (Q.has("barbsheet")) barbsheet().catch(e => status("barbsheet: " + e.message, "err"));
else if (PERFTEST) runPerf();
else {
  bootStep("Restoring your last session…");
  const a = await post("/api/drafts", {name: "Autosave"}).catch(() => ({}));
  if (a.doc?.v === 2 && a.doc.docs.some(d => d.items.length)) { await restoreDocs(a.doc); status(`Restored your last session (${docs.length} tab${docs.length > 1 ? "s" : ""})`, "ok"); }
  else if (a.doc?.items?.length) { await deserialize(a.doc); undoStack = []; status("Restored your last session", "ok"); }
  else { changed(); markSaved(); status("Ready. Open an icon, add a shape or start drawing. Press ? for shortcuts."); }
  setTimeout(() => checkUpdate(store.get("updates", true)), 2000);
  mark("restored");
  await Promise.race([new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))), new Promise(r => setTimeout(r, 500))]);
  mark("painted");
}
bootDone();
if (!GOLDEN && !BRUSHTEST && !PERFTEST) {
  const nav = performance.getEntriesByType("navigation")[0] || {}, res = performance.getEntriesByType("resource");
  Object.assign(BOOT, {html: Math.round(nav.responseEnd || 0), domready: Math.round(nav.domContentLoadedEventEnd || 0),
    slowest: res.sort((a, b) => b.duration - a.duration).slice(0, 6).map(r => `${r.name.replace(location.origin, "")} ${Math.round(r.startTime)}+${Math.round(r.duration)}`)});
  console.info("[boot] ms since navigation", BOOT);
  post("/api/perf", {mode: "boot", keep: Q.has("boottest") || BOOT.painted > 4000, browser: navigator.userAgent, result: BOOT}).catch(() => {});
}
