// Bitmap stroke -> brush strokes (user 7.0h: imported strokes "into the vector version if it doesn't change the look").
// A game "stroke" is a connected piece of the drawing, often several brush marks that touch (a spiral and its flicks).
// Its mask (alpha >= 128) is thinned to a centre line (Zhang-Suen), short spurs are pruned, and the line's graph is split
// into marks: at each junction the two branches that run on most straight (angle > 120 deg) continue each other, the
// rest end there. Each mark becomes a path through points every ~0.8 of its width, with its median width and a taper at
// a free end that thins out; a dot becomes a round dab. The caller renders them and keeps them only when together they
// cover the same pixels (match()).
const OFF = [[-1, -1], [0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0]];   // clockwise from the top left

function thin(m, w, h) {                       // Zhang-Suen thinning, in place on a 0/1 Uint8Array
  const at = (x, y) => x >= 0 && y >= 0 && x < w && y < h ? m[y * w + x] : 0;
  const NB = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]];   // P2..P9
  for (let changed = true; changed;) {
    changed = false;
    for (const step of [0, 1]) {
      const del = [];
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        if (!m[y * w + x]) continue;
        const p = NB.map(([dx, dy]) => at(x + dx, y + dy)), [p2, , p4, , p6, , p8] = p;
        const b = p.reduce((s, v) => s + v, 0);
        if (b < 2 || b > 6) continue;
        let a = 0;
        for (let i = 0; i < 8; i++) if (!p[i] && p[(i + 1) % 8]) a++;
        if (a !== 1) continue;
        if (step === 0 ? p2 * p4 * p6 || p4 * p6 * p8 : p2 * p4 * p8 || p2 * p6 * p8) continue;
        del.push(y * w + x);
      }
      for (const i of del) m[i] = 0;
      if (del.length) changed = true;
    }
  }
  return m;
}
function spare(s, w, h) {                       // drop line pixels whose neighbours stay connected without them (the
  for (let i = 0; i < w * h; i++) {              // staircase corners Zhang-Suen leaves): a line one pixel wide throughout
    if (!s[i]) continue;
    const nb = nbrs(s, w, h, i);
    if (nb.length < 2) continue;
    const seen = new Set([nb[0]]), q = [nb[0]];
    while (q.length) { const a = q.pop(); for (const b of nb) if (!seen.has(b) && adj(a, b, w)) { seen.add(b); q.push(b); } }
    if (seen.size === nb.length) s[i] = 0;
  }
  return s;
}
// distance of each pixel of m to the nearest pixel outside it (outside the image counts as outside): exact Euclidean,
// Felzenszwalb & Huttenlocher's two 1-D passes (scipy's distance_transform_edt with a border of zeros). The 3-4 chamfer
// used before overestimated widths ~8% and opened with an octagon (barb counts .55-.6 of the probe's)
function edt1(f, n, d, v, z) {                   // squared distance transform of one line (in place into d)
  let k = 0; v[0] = 0; z[0] = -Infinity; z[1] = Infinity;
  for (let q = 1; q < n; q++) {
    let s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]);
    while (s <= z[k]) { k--; s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]); }
    k++; v[k] = q; z[k] = s; z[k + 1] = Infinity;
  }
  k = 0;
  for (let q = 0; q < n; q++) { while (z[k + 1] < q) k++; d[q] = (q - v[k]) * (q - v[k]) + f[v[k]]; }
}
function chamfer(m, w, h, edge = true) {        // (kept name) exact distance to the outside; edge: beyond the image counts
  const W = w + 2, H = h + 2, INF = 1e12, g = new Float64Array(W * H).fill(edge ? 0 : INF);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) g[(y + 1) * W + x + 1] = m[y * w + x] ? INF : 0;
  const n = Math.max(W, H), f = new Float64Array(n), d = new Float64Array(n), v = new Int32Array(n), z = new Float64Array(n + 1);
  for (let x = 0; x < W; x++) { for (let y = 0; y < H; y++) f[y] = g[y * W + x]; edt1(f, H, d, v, z); for (let y = 0; y < H; y++) g[y * W + x] = d[y]; }
  for (let y = 0; y < H; y++) { for (let x = 0; x < W; x++) f[x] = g[y * W + x]; edt1(f, W, d, v, z); for (let x = 0; x < W; x++) g[y * W + x] = d[x]; }
  const out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) out[y * w + x] = Math.sqrt(g[(y + 1) * W + x + 1]);
  return out;
}
const nbrs = (s, w, h, i) => { const x = i % w, y = (i / w) | 0, out = [];
  for (const [dx, dy] of OFF) { const X = x + dx, Y = y + dy; if (X >= 0 && Y >= 0 && X < w && Y < h && s[Y * w + X]) out.push(Y * w + X); }
  return out; };
const adj = (a, b, w) => Math.abs(a % w - b % w) <= 1 && Math.abs(((a / w) | 0) - ((b / w) | 0)) <= 1;
// crossing number: 1 = a line end, 2 = on a line (staircase corners of the thinning included), 3+ = a junction
const cross = (s, w, h, i) => { const x = i % w, y = (i / w) | 0;
  const p = OFF.map(([dx, dy]) => { const X = x + dx, Y = y + dy; return X >= 0 && Y >= 0 && X < w && Y < h ? s[Y * w + X] : 0; });
  let c = 0; for (let k = 0; k < 8; k++) if (!p[k] && p[(k + 1) % 8]) c++;
  return c; };

// the centre line as a graph: nodes = junction clusters and ends, edges = the pixel runs between them (loops too)
function graph(s, w, h) {
  const px = []; for (let i = 0; i < w * h; i++) if (s[i]) px.push(i);
  const kind = new Map(px.map(i => [i, nbrs(s, w, h, i).length]));   // neighbours (spares removed): 1 end, 2 line, 3+ junction
  const node = new Map();                        // junction pixel -> node id (touching junction pixels: one node)
  let nid = 0;
  for (const i of px) if (kind.get(i) >= 3 && !node.has(i)) {
    const q = [i]; node.set(i, nid);
    while (q.length) for (const j of nbrs(s, w, h, q.pop())) if (kind.get(j) >= 3 && !node.has(j)) { node.set(j, nid); q.push(j); }
    nid++;
  }
  for (const i of px) if (kind.get(i) <= 1 && !node.has(i)) node.set(i, nid++);   // ends (and lone pixels)
  const used = new Set(), edges = [];
  const run = (from, first) => {                 // from a node pixel along the line until the next node pixel
    const path = [from, first]; used.add(first);
    for (let cur = first, prev = from; !node.has(cur);) {
      const nx = nbrs(s, w, h, cur).filter(j => j !== prev && !used.has(j) && !(node.has(j) && node.get(j) === node.get(from) && path.length < 3));
      if (!nx.length) break;
      nx.sort((a, b) => (node.has(b) ? 1 : 0) - (node.has(a) ? 1 : 0));   // a node within reach ends the run
      for (const j of nx.slice(1)) if (!node.has(j) && adj(j, nx[0], w)) used.add(j);   // a staircase corner's spare pixel
      prev = cur; cur = nx[0];
      if (!node.has(cur)) used.add(cur);
      path.push(cur);
    }
    return path;
  };
  for (const [i, n] of node) for (const j of nbrs(s, w, h, i)) if (!node.has(j) && !used.has(j)) {
    const p = run(i, j), last = p[p.length - 1];
    edges.push({a: n, b: node.has(last) ? node.get(last) : -1, path: p});
  }
  for (const i of px) if (!node.has(i) && !used.has(i)) {   // a loop with no junction or end
    used.add(i);
    const p = [i];
    for (let cur = i; ;) {
      const nx = nbrs(s, w, h, cur).filter(j => !used.has(j));
      if (!nx.length) break;
      for (const j of nx.slice(1)) if (adj(j, nx[0], w)) used.add(j);
      cur = nx[0]; used.add(cur); p.push(cur);
    }
    if (p.length >= 8) edges.push({a: -2, b: -2, path: p, loop: true});   // shorter: spare pixels, not a ring
  }
  return {edges, kind, node};
}
const xy = (i, w) => [i % w + .5, ((i / w) | 0) + .5];
function dirAt(path, atStart, w, reach) {        // unit direction pointing away from the node along the edge
  const k = Math.min(path.length - 1, reach), p0 = xy(atStart ? path[0] : path[path.length - 1], w), p1 = xy(atStart ? path[k] : path[path.length - 1 - k], w);
  const d = [p1[0] - p0[0], p1[1] - p0[1]], L = Math.hypot(...d) || 1;
  return [d[0] / L, d[1] / L];
}

export function vectorize(alpha, w, h) {       // -> {marks: [{pts, closed, width, taperStart, taperEnd}]} | {fail}
  const m = new Uint8Array(w * h);
  let area = 0, sx = 0, sy = 0;
  for (let i = 0; i < w * h; i++) if (alpha[i] >= 128) { m[i] = 1; area++; sx += i % w; sy += (i / w) | 0; }
  if (!area) return {fail: "too faint to trace"};
  const dt = chamfer(m, w, h);
  let dmax = 0; for (let i = 0; i < w * h; i++) dmax = Math.max(dmax, dt[i]);
  const dab = () => { const c = [sx / area + .5, sy / area + .5], d = Math.max(2, 2 * Math.sqrt(area / Math.PI));
    return {marks: [{pts: [c, [c[0] + .01, c[1]]], closed: false, width: Math.round(d * 10) / 10, taperStart: false, taperEnd: false, dab: true}]}; };
  const s = spare(thin(m.slice(), w, h), w, h);
  const skel = []; for (let i = 0; i < w * h; i++) if (s[i]) skel.push(i);
  const half = skel.map(i => dt[i]).sort((a, b) => a - b);
  const W = Math.max(2, 2 * (half[half.length >> 1] || dmax));
  let len = 0; for (let i = 0; i < w * h; i++) if (s[i]) len++;
  if (len < 1.5 * W) return dab();               // a dot or a short blob: one round dab
  for (let pass = 0; pass < 6; pass++) {         // spurs shorter than a width, from an end to a junction, go
    const {edges, kind} = graph(s, w, h);
    let cut = false;
    for (const e of edges) if (!e.loop && e.path.length < W && (kind.get(e.path[0]) === 1) !== (kind.get(e.path[e.path.length - 1]) === 1)) {
      for (const p of e.path) if (kind.get(p) <= 2) { s[p] = 0; cut = true; }
    }
    if (!cut) break;
  }
  let {edges, kind} = graph(s, w, h);
  if (!edges.length) return dab();
  // two junctions joined by a run shorter than the width are one crossing (thinning splits an X into two Ys)
  const root = new Map(), find = n => { while (root.has(n)) n = root.get(n); return n; };
  edges = edges.filter(e => {
    if (e.loop || e.a < 0 || e.b < 0 || e.a === e.b || e.path.length >= W || kind.get(e.path[0]) < 3 || kind.get(e.path[e.path.length - 1]) < 3) return true;
    const a = find(e.a), b = find(e.b);
    if (a !== b) root.set(b, a);
    return false;
  });
  for (const e of edges) if (!e.loop) { e.a = find(e.a); if (e.b >= 0) e.b = find(e.b); }
  // pair the edges at each junction: the straightest continuations (> 120 deg apart), greedily
  const ends = new Map();                         // node -> [{e, atStart}]
  edges.forEach((e, k) => { if (e.loop) return; ends.set(e.a, [...(ends.get(e.a) || []), {k, atStart: true}]); if (e.b >= 0) ends.set(e.b, [...(ends.get(e.b) || []), {k, atStart: false}]); });
  const link = new Map();                         // "k:start|end" -> the end it continues into
  const key = (k, atStart) => `${k}:${atStart ? 0 : 1}`;
  for (const [, list] of ends) {
    if (list.length < 2) continue;
    // a sharp tip (a crescent's): two branches leave the junction at an acute angle and a short spur runs on to the
    // tip's point. Pairing the spur with one branch left the other ending beside it, two caps making a creased beak (user
    // 7.0i, seen at 2048): the two branches join at a corner instead, the spur stays a mark of its own (the tip's point:
    // a dot or a short tapered stroke)
    if (list.length === 3) {
      const dir = e => dirAt(edges[e.k].path, e.atStart, w, Math.ceil(W));
      const spur = list.find(e => { const p = edges[e.k].path, far = e.atStart ? p[p.length - 1] : p[0]; return p.length < 2 * W && kind.get(far) === 1; });
      const [A, B] = list.filter(e => e !== spur);
      if (spur && A.k !== B.k) {
        const da = dir(A), db = dir(B), ds = dir(spur);
        if (da[0] * db[0] + da[1] * db[1] > .2 && ds[0] * (da[0] + db[0]) + ds[1] * (da[1] + db[1]) < 0) {
          link.set(key(A.k, A.atStart), {...B, corner: true}); link.set(key(B.k, B.atStart), {...A, corner: true});
          continue;
        }
      }
    }
    const pairs = [];
    for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
      if (list[i].k === list[j].k) continue;
      const di = dirAt(edges[list[i].k].path, list[i].atStart, w, Math.ceil(W)), dj = dirAt(edges[list[j].k].path, list[j].atStart, w, Math.ceil(W));
      const cos = di[0] * dj[0] + di[1] * dj[1];
      if (cos < -.5) pairs.push([cos, list[i], list[j]]);
    }
    pairs.sort((a, b) => a[0] - b[0]);
    const taken = new Set();
    for (const [, a, b] of pairs) {
      const ka = key(a.k, a.atStart), kb = key(b.k, b.atStart);
      if (taken.has(ka) || taken.has(kb)) continue;
      taken.add(ka); taken.add(kb); link.set(ka, b); link.set(kb, a);
    }
    // two ends left over meet at a sharp corner (a crescent's tips: its outer and inner arc), so they join there
    // instead of ending side by side, each with its own cap (a box at 2048, user 7.0i)
    const left = list.filter(e => !taken.has(key(e.k, e.atStart)));
    if (left.length === 2 && left[0].k !== left[1].k) {
      link.set(key(left[0].k, left[0].atStart), {...left[1], corner: true});
      link.set(key(left[1].k, left[1].atStart), {...left[0], corner: true});
    }
  }
  // chain edges through the links into marks
  const done = new Set(), marks = [];
  const pathOf = (k, forward) => forward ? edges[k].path : edges[k].path.slice().reverse();
  for (let k0 = 0; k0 < edges.length; k0++) {
    if (done.has(k0)) continue;
    if (edges[k0].loop) { done.add(k0); marks.push({px: edges[k0].path, closed: true, free: [false, false]}); continue; }
    // walk back to the chain's start: follow links out of the start end
    let k = k0, fwd = true;
    for (let guard = 0; guard < edges.length; guard++) {
      const l = link.get(key(k, fwd));            // what continues before this edge's start
      if (!l || l.k === k0 && guard) break;
      k = l.k; fwd = !l.atStart;                  // entering edge l.k at its far end means traversing it forward from its other end
      if (k === k0) break;
    }
    const px = [], corners = new Set();         // corners: indices into px where a corner link joins two edges
    let free0 = null, closed = false, last = null;
    for (let guard = 0; guard <= edges.length; guard++) {
      if (done.has(k)) { closed = true; if (last?.corner) corners.add(0); break; }
      done.add(k);
      const p = pathOf(k, fwd);
      if (free0 === null) free0 = kind.get(p[0]) === 1;
      if (last?.corner && px.length) corners.add(px.length - 1);
      px.push(...(px.length ? p.slice(1) : p));
      const l = last = link.get(key(k, !fwd));    // what continues after this edge's end
      if (!l) break;
      k = l.k; fwd = l.atStart;
    }
    marks.push({px, closed, corners, free: [!!free0, kind.get(px[px.length - 1]) === 1]});
  }
  const out = [];
  for (const mk of marks) {
    const ws = mk.px.map(i => 2 * dt[i]).sort((a, b) => a - b), Wm = Math.max(2, ws[ws.length >> 1] || W);
    // big exports showed two kinds of boxy pieces (user 7.0i): a run about as long as it is wide (two pointed caps make
    // a box: a round dab is what it looks like), and a loop whose two ends meet at a sharp corner the junction didn't
    // pair (the crescent's tip: two caps side by side): closed, with a corner where the ends meet
    if (!mk.closed && mk.px.length < 1.2 * Wm) {
      const c = xy(mk.px[mk.px.length >> 1], w);
      out.push({pts: [c, [c[0] + .01, c[1]]], closed: false, width: Math.round(Wm * 10) / 10, taperStart: false, taperEnd: false, dab: true});
      continue;
    }
    const [e0, e1] = [xy(mk.px[0], w), xy(mk.px[mk.px.length - 1], w)];
    if (!mk.closed && mk.px.length > 4 * Wm && Math.hypot(e0[0] - e1[0], e0[1] - e1[1]) < .75 * Wm) { mk.closed = true; mk.corner0 = true; }
    const step = Math.max(4, .8 * Wm), pts = [xy(mk.px[0], w)], cn = [!!mk.corners?.has(0)];
    let acc = 0;
    for (let k = 1; k < mk.px.length; k++) {
      const a = xy(mk.px[k - 1], w), b = xy(mk.px[k], w), c = !!mk.corners?.has(k);
      acc += Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (acc >= step || c || k === mk.px.length - 1) { pts.push(b); cn.push(c); acc = 0; }   // a corner is always a point
    }
    if (mk.closed && pts.length > 3) { pts.pop(); cn.pop(); }
    if (cn.some(Boolean)) mk.cn = cn;
    if (mk.corner0) pts[0] = [(e0[0] + e1[0]) / 2, (e0[1] + e1[1]) / 2];   // the ends' meeting point, a corner
    if (pts.length < 2) { pts.push([pts[0][0] + .01, pts[0][1]]); }
    const endW = first => { const seg = (first ? mk.px.slice(0, Math.max(2, mk.px.length >> 3)) : mk.px.slice(-Math.max(2, mk.px.length >> 3))).map(i => 2 * dt[i]);
      return seg.reduce((a, b) => a + b, 0) / seg.length / Wm; };
    if (!mk.closed) for (const [a, b, free] of [[0, 1, mk.free[0]], [pts.length - 1, pts.length - 2, mk.free[1]]]) {
      const d = [pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]], L = Math.hypot(...d) || 1, ext = Wm * (free ? .35 : .5);   // reach the end / into the junction
      pts[a] = [pts[a][0] + d[0] / L * ext, pts[a][1] + d[1] / L * ext];
    }
    out.push({pts, closed: mk.closed && pts.length > 2, width: Math.round(Wm * 10) / 10,
              ...(mk.corner0 || mk.cn ? {corner: pts.map((_, i) => (mk.corner0 && i === 0) || !!mk.cn?.[i])} : {}),
              taperStart: !mk.closed && mk.free[0] && endW(true) < .8, taperEnd: !mk.closed && mk.free[1] && endW(false) < .8});
  }
  return {marks: out};
}
// a bitmap stroke's barbs per 100 px of stroke (research/probes/barbs.py's measure): the mask opened with a disc of .4
// widths, the removed pieces that reach 2 px or more out of the opened body and at most a width (longer: thorns)
export function barbDensity(alpha, w, h) { return barbs(alpha, w, h).density; }
// -> {density, body (0/1: the stroke without its barbs), fromBody (distance to it), W (width), blen (its length)}
export function barbs(alpha, w, h) {
  const m = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) m[i] = alpha[i] >= 128 ? 1 : 0;
  const dt = chamfer(m, w, h), sk = thin(m.slice(), w, h);   // the plain thinning, as skimage's skeletonize
  const half = []; let len = 0;
  for (let i = 0; i < w * h; i++) if (sk[i]) { half.push(dt[i]); len++; }
  if (len < 20) return {density: 0, body: m, fromBody: new Float32Array(w * h), W: 2, blen: len};
  half.sort((a, b) => a - b);
  const W = 2 * half[half.length >> 1], r = Math.max(1, Math.round(.4 * W));   // an integer disc, as the probe's disk()
  const notCore = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) notCore[i] = dt[i] > r ? 0 : 1;
  const toCore = chamfer(notCore, w, h, false), body = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) body[i] = !notCore[i] || toCore[i] <= r ? 1 : 0;
  const notBody = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) notBody[i] = body[i] ? 0 : 1;
  const fromBody = chamfer(notBody, w, h, false), seen = new Uint8Array(w * h);
  let n = 0;
  for (let i = 0; i < w * h; i++) {
    if (!m[i] || body[i] || seen[i]) continue;
    let reach = 0, size = 0;
    const q = [i]; seen[i] = 1;
    while (q.length) {
      const p = q.pop(); size++; reach = Math.max(reach, fromBody[p]);
      for (const j of nbrs(m, w, h, p)) if (!body[j] && !seen[j]) { seen[j] = 1; q.push(j); }
    }
    if (size >= 4 && reach >= 2 && reach <= W) n++;   // longer: a thorn (the probe's THORN = 1 width)
  }
  let blen = 0; const bs = spare(thin(body.slice(), w, h), w, h); for (let i = 0; i < w * h; i++) blen += bs[i];   // as the probe: the barb-free body's length
  barbDensity.last = {W, r, n, blen};               // for the offline comparison with the probe
  return {density: blen < 20 ? 0 : 100 * n / blen, body, fromBody, inBody: chamfer(body, w, h), W, blen};
}
// how well renders cover a bitmap: IoU of the two masks, a pixel counted as covered when the other mask is within 1 px
// (the brush's own edge wobble is not a change of look). b = [{alpha, x0, y0, w, h}] (their union)
export function match(a, ax, ay, aw, ah, bs) {
  let x0 = ax, y0 = ay, x1 = ax + aw, y1 = ay + ah;
  for (const b of bs) { x0 = Math.min(x0, b.x0); y0 = Math.min(y0, b.y0); x1 = Math.max(x1, b.x0 + b.w); y1 = Math.max(y1, b.y0 + b.h); }
  const W = x1 - x0, H = y1 - y0, A = new Uint8Array(W * H), B = new Uint8Array(W * H);
  for (let y = 0; y < ah; y++) for (let x = 0; x < aw; x++) if (a[y * aw + x] >= 128) A[(y + ay - y0) * W + x + ax - x0] = 1;
  for (const b of bs) for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) if (b.alpha[y * b.w + x] >= 128) B[(y + b.y0 - y0) * W + x + b.x0 - x0] = 1;
  const grow = M => { const o = M.slice(); for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (M[y * W + x]) for (const [dx, dy] of OFF) { const X = x + dx, Y = y + dy; if (X >= 0 && Y >= 0 && X < W && Y < H) o[Y * W + X] = 1; } return o; };
  const Ag = grow(A), Bg = grow(B);
  let inter = 0, uni = 0;
  for (let i = 0; i < W * H; i++) if (A[i] || B[i]) { uni++; if ((A[i] && Bg[i]) || (B[i] && Ag[i])) inter++; }
  return uni ? inter / uni : 0;
}
// The tapered eraser (user 2026-10-19: "the part(s) that remain have a proper end / taper"): what a cut leaves narrows
// towards the cut like a brush stroke's end (brush.js: width × tip + (1 - tip)·(d / len widths)^pow). before / after:
// the stroke's alpha (0-255) before and after the eraser -> a factor (0-1) for after's alpha. d is the distance along
// the stroke from the cut (geodesic within the stroke: a stroke that only passes near the eraser keeps its width);
// widths come from the stroke before the cut (its sides, not the cut face).
export function taperCut(before, after, w, h, tip = .32, len = 3, pow = .7) {
  const n = w * h, mb = new Uint8Array(n), out = new Float32Array(n).fill(1);
  for (let i = 0; i < n; i++) mb[i] = before[i] >= 128 ? 1 : 0;
  const e = chamfer(mb, w, h, false);           // distance to the stroke's own sides (the bitmap's edge isn't a side)
  let top = 0;
  for (let i = 0; i < n; i++) if (mb[i]) top = Math.max(top, e[i]);
  // half-width: the largest side distance nearby, so an edge pixel knows the width of the stroke it lies on
  const R = Math.max(1, Math.ceil(top)), H = new Float32Array(n), t = new Float32Array(n);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let m = 0; for (let k = Math.max(0, x - R); k <= Math.min(w - 1, x + R); k++) m = Math.max(m, e[y * w + k]); t[y * w + x] = m; }
  for (let x = 0; x < w; x++) for (let y = 0; y < h; y++) { let m = 0; for (let k = Math.max(0, y - R); k <= Math.min(h - 1, y + R); k++) m = Math.max(m, t[k * w + x]); H[y * w + x] = m; }
  // distance along the stroke from the cut: Dijkstra (1, √2 steps) through what is left, from the pixels next to the cut
  const D = new Float64Array(n).fill(Infinity), heap = [], far = len * 2 * top;   // 64-bit: the heap compares in 64
  const push = (d, i) => { heap.push([d, i]); let c = heap.length - 1; while (c) { const p = (c - 1) >> 1; if (heap[p][0] <= heap[c][0]) break; [heap[p], heap[c]] = [heap[c], heap[p]]; c = p; } };
  const pop = () => { const r = heap[0], l = heap.pop(); if (heap.length) { heap[0] = l; let c = 0; for (;;) { const a = 2 * c + 1, b = a + 1; let s = c;
    if (a < heap.length && heap[a][0] < heap[s][0]) s = a; if (b < heap.length && heap[b][0] < heap[s][0]) s = b; if (s === c) break; [heap[s], heap[c]] = [heap[c], heap[s]]; c = s; } } return r; };
  const left = i => after[i] >= 128, cut = i => mb[i] && !left(i);
  for (let i = 0; i < n; i++) {
    if (!left(i)) continue;
    const x = i % w, y = (i / w) | 0;
    for (const [dx, dy] of OFF) { const X = x + dx, Y = y + dy; if (X >= 0 && Y >= 0 && X < w && Y < h && cut(Y * w + X)) { D[i] = 0; push(0, i); break; } }
  }
  while (heap.length) {
    const [d, i] = pop();
    if (d > D[i] || d > far) continue;
    const x = i % w, y = (i / w) | 0;
    for (const [dx, dy] of OFF) {
      const X = x + dx, Y = y + dy, j = Y * w + X, nd = d + (dx && dy ? Math.SQRT2 : 1);
      if (X >= 0 && Y >= 0 && X < w && Y < h && after[j] > 0 && nd < D[j]) { D[j] = nd; push(nd, j); }
    }
  }
  for (let i = 0; i < n; i++) {
    if (D[i] === Infinity || !H[i]) continue;
    const tl = len * 2 * H[i];
    if (D[i] >= tl) continue;
    const f = tip + (1 - tip) * Math.pow(D[i] / tl, pow);
    out[i] = Math.max(0, Math.min(1, e[i] - H[i] * (1 - f) + .5));   // keep what lies within f × the half-width of the centre
  }
  return out;
}
// the separate pieces of a bitmap (alpha > 0, 8 neighbours): a label per pixel (0 = empty) and per piece its size,
// peak alpha and the peak's pixel (a stroke's centre: the seed that finds the piece again at any scale)
export function pieces(alpha, w, h) {
  const lab = new Int32Array(w * h), q = new Int32Array(w * h), list = [];
  for (let i = 0; i < w * h; i++) {
    if (!alpha[i] || lab[i]) continue;
    const p = {n: 0, peak: 0, at: i}, id = list.push(p);
    let qh = 0, qt = 0;
    q[qt++] = i; lab[i] = id;
    while (qh < qt) {
      const c = q[qh++], x = c % w, y = (c / w) | 0;
      p.n++;
      if (alpha[c] > p.peak) { p.peak = alpha[c]; p.at = c; }
      for (const [dx, dy] of OFF) { const X = x + dx, Y = y + dy, j = Y * w + X; if (X >= 0 && Y >= 0 && X < w && Y < h && alpha[j] && !lab[j]) { lab[j] = id; q[qt++] = j; } }
    }
  }
  return {lab, list};
}
export const _internal = {thin, spare, chamfer, graph, cross};   // for offline tests
