// House brush (D44). A drawn stroke stays a vector object (its path + settings) and is rendered here into grey line art +
// alpha, again whenever a setting or a point changes. The look is measured on the game's own strokes (hold-out checked
// by /?brushtest: the brush drawn on 478 hold-out stroke sections' own centre lines and measured the same way), as shares
// of the median half width, tips excluded: width varies slowly (>15 px) .065, mid scale .035, fine .015; the centre line
// wanders .024 (mid) / .017 (fine). NOISE holds the generator amplitudes that reproduce those (calibrated 2026-10-17,
// again 2026-10-18 for one random stream per noise array: within 6%).
// Tips: .32 of the width at a real stroke end, .95 by 38 px (fit: tip + (1 - tip) (d / 3 widths)^.7, within .03).
// Corners stay sharp (mitred); edges crisp. Roughness scales all of the variation (0 = smooth, 1 = the game's).
// Cross-section grey: .82 at the edge to .975 in the middle (149 icons); core grey varies .03 along the stroke.
export const PROFILE = [[0, .82], [.15, .831], [.25, .843], [.35, .855], [.45, .878], [.55, .91], [.65, .937], [.75, .953],
                        [.85, .965], [.95, .973], [1, .975]];
export const NOISE = {slow: [15, .167], mid: [5, .020], fine: [1, .022], omid: [5, .035], ofine: [1, .026], grey: [10, .03]};
export const DEFAULTS = {width: 14, rough: 1, taperStart: true, taperEnd: true, tip: .32, curve: 1, smooth: .5};
const TIP_LEN = 3, TIP_POW = .7;               // taper length in widths (42 px at 14) and the shape of its curve
const MITRE = 4;                               // longest mitre, in half widths, before a corner is rounded

export function mulberry32(a) {
  return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
                 t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
export function gauss(rnd) { let u = 0; while (!u) u = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rnd()); }
const grow = (a, n) => { if (a.length >= n) return a; const b = new Float32Array(Math.max(n, 2 * a.length, 1024)); b.set(a); return b; };
// white noise blurred by a Gaussian, scaled to standard deviation amp: out[0, n) after ensure(n); extending it later
// draws the next samples of the same stream, so the values are those of one pass of length n
function noiseStream([sigma, amp], rnd) {
  const r = Math.ceil(3 * sigma), k = [];
  for (let x = -r; x <= r; x++) k.push(Math.exp(-x * x / (2 * sigma * sigma)));
  const norm = amp / Math.sqrt(k.reduce((s, v) => s + v * v, 0));
  return {n: 0, w: new Float32Array(0), out: new Float32Array(0), ensure(n) {
    if (n <= this.n) return this;
    const nw = this.n ? this.n + 2 * r : 0;
    this.w = grow(this.w, n + 2 * r);
    for (let i = nw; i < n + 2 * r; i++) this.w[i] = gauss(rnd);
    this.out = grow(this.out, n);
    for (let i = this.n; i < n; i++) { let s = 0; for (let j = 0; j < k.length; j++) s += this.w[i + j] * k[j]; this.out[i] = s * norm; }
    this.n = n;
    return this;
  }};
}
export function greyAt(q) {
  for (let i = 1; i < PROFILE.length; i++) if (q <= PROFILE[i][0]) {
    const [q0, g0] = PROFILE[i - 1], [q1, g1] = PROFILE[i];
    return g0 + (g1 - g0) * (q - q0) / (q1 - q0);
  }
  return PROFILE.at(-1)[1];
}

// ---------------------------------------------------------------- paths
const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
export function resample(P, step = 1) {        // even steps along a polyline, both ends kept
  return P.length < 2 ? P.map(p => p.slice()) : resampleFrom(P, step, null, 1).out;
}
// resample() that can resume: st.len[i] / st.carry[i] = output length and carry before segment P[i-1] -> P[i] (the
// last entry: after the last segment). Redoing segments from i0 on, after points were added, is the same arithmetic
// as one pass over all of them.
function resampleFrom(P, step, st, i0) {
  if (!st) { st = {out: [P[0].slice()], len: [0, 1], carry: [0, 0]}; i0 = 1; }
  const {out, len, carry} = st;
  out.length = len[i0];
  let cr = carry[i0];
  for (let i = i0; i < P.length; i++) {
    len[i] = out.length; carry[i] = cr;
    const a = P[i - 1], b = P[i], L = dist(a, b);
    let t = step - cr;
    while (t <= L) { out.push([a[0] + (b[0] - a[0]) * t / L, a[1] + (b[1] - a[1]) * t / L]); t += step; }
    cr = L - (t - step);
  }
  len[P.length] = out.length; carry[P.length] = cr;
  len.length = carry.length = P.length + 1;
  if (dist(out.at(-1), P.at(-1)) > .25) out.push(P.at(-1).slice());
  return st;
}
const smoothKernel = sigma => { const r = Math.ceil(2.5 * sigma), k = []; for (let x = -r; x <= r; x++) k.push(Math.exp(-x * x / (2 * sigma * sigma))); return k; };
function smoothAt(P, i, k) {                   // Gaussian along the points at i (ends clamped)
  const r = (k.length - 1) / 2;
  let sx = 0, sy = 0, sw = 0;
  for (let j = -r; j <= r; j++) { const q = P[Math.min(P.length - 1, Math.max(0, i + j))], w = k[j + r]; sx += q[0] * w; sy += q[1] * w; sw += w; }
  return [sx / sw, sy / sw];
}
// the freehand centre line: resample at 2 px -> Gaussian smoothing (the stabiliser; ends fixed, needs 5 points) ->
// resample at 1 px. `c` (live drawing) keeps every stage, so a call after points were added redoes only the end.
function freeLine(v, k, c = null) {
  const sigma = .5 + 4 * (v.smooth ?? .5), kern = smoothKernel(sigma), r = (kern.length - 1) / 2;
  c ??= {raw: []};
  const n0 = c.raw.length;
  for (let i = n0; i < v.pts.length; i++) c.raw.push([v.pts[i][0] * k, v.pts[i][1] * k]);
  if (c.raw.length < 2) { c.R = c.S = c.P = null; return [c.raw[0].slice()]; }
  const resume = c.R && n0 >= 2, fr = resume ? c.R.len[n0] : 0;          // first 2 px point that may change
  c.R = resampleFrom(c.raw, 2 * k, resume ? c.R : null, n0);
  const R = c.R.out;
  let is = 0;                                  // first smoothed point that may change
  if (R.length < 5) c.S = null;
  else {
    is = c.S && resume ? Math.max(0, fr - r - 1) : 0;
    const S = is ? c.S : (c.S = []);
    S.length = R.length;
    for (let i = is; i < R.length; i++) S[i] = i === 0 || i === R.length - 1 ? R[i] : smoothAt(R, i, kern);
  }
  const resumeP = !!c.P && is >= 1;
  c.fp = resumeP ? c.P.len[is] : 0;            // first 1 px point that may change
  c.P = resampleFrom(c.S || R, 1, resumeP ? c.P : null, is);
  return c.P.out;
}
// cardinal spline through control points: curve 0 = straight segments, 1 = Catmull-Rom; corner points get no tangent
export function splineSpans(C, corner, curve, closed) {
  const n = C.length, spans = [];
  if (n < 2) return [C.map(p => p.slice())];
  const at = i => C[(i + n) % n];
  const T = C.map((p, i) => {
    if (corner[i] || curve <= 0) return [0, 0];
    const a = !closed && i === 0 ? p : at(i - 1), b = !closed && i === n - 1 ? p : at(i + 1);
    return [curve * (b[0] - a[0]) / 2, curve * (b[1] - a[1]) / 2];
  });
  let span = [C[0].slice()];
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const p0 = C[i], p1 = at(i + 1), t0 = T[i], t1 = T[(i + 1) % n], K = Math.max(8, Math.ceil(dist(p0, p1) / 2));
    for (let k = 1; k <= K; k++) {
      const t = k / K, t2 = t * t, t3 = t2 * t, h00 = 2 * t3 - 3 * t2 + 1, h10 = t3 - 2 * t2 + t, h01 = -2 * t3 + 3 * t2, h11 = t3 - t2;
      span.push([0, 1].map(j => h00 * p0[j] + h10 * t0[j] + h01 * p1[j] + h11 * t1[j]));
    }
    if (corner[(i + 1) % n] || curve <= 0) { spans.push(span); span = [p1.slice()]; }
  }
  if (span.length > 1) spans.push(span);
  return spans;
}
// vector stroke -> spans of the centre line (each smooth; sharp corners between spans) in local px x k
export function geometry(v, k = 1) {
  const sc = P => P.map(p => [p[0] * k, p[1] * k]);
  if (v.kind === "ellipse") {
    const rx = v.rx * k, ry = v.ry * k, n = Math.max(32, Math.ceil(Math.PI * (3 * (rx + ry) - Math.sqrt((3 * rx + ry) * (rx + 3 * ry)))));
    return {spans: [Array.from({length: n + 1}, (_, i) => [v.cx * k + rx * Math.cos(2 * Math.PI * i / n), v.cy * k + ry * Math.sin(2 * Math.PI * i / n)])], closed: true};
  }
  if (v.kind === "free") return {spans: [v.raw ? sc(v.pts) : freeLine(v, k)], closed: false};   // already at 1 px
  return {spans: splineSpans(sc(v.pts), v.corner, v.curve, v.closed), closed: !!v.closed};
}

// ---------------------------------------------------------------- render = paint(prepare(v, k))
const area = q => q.reduce((s, p, i) => { const r = q[(i + 1) % q.length]; return s + p[0] * r[1] - r[0] * p[1]; }, 0);
const orient = (a, b, c) => Math.sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]));
const crosses = (a, b, c, d) => orient(a, b, c) * orient(a, b, d) < 0 && orient(c, d, a) * orient(c, d, b) < 0;
// one stroke segment: a quad, or at a bend tighter than the half width (its two cross-sections cross) four triangles
// through the centre line: a self-crossing quad's negative lobe cancelled its neighbour and left a hole (user 7.0i, seen
// at 2048). Triangles can't cross themselves; addPoly winds every piece the same way.
function segment(polys, P, Lp, Rp, i) {
  const a = Lp[i], b = Lp[i + 1], c = Rp[i + 1], d = Rp[i];
  if (!crosses(a, b, c, d) && !crosses(b, c, d, a)) return polys.push([a, b, c, d]);
  polys.push([P[i], a, b], [P[i], b, P[i + 1]], [P[i], P[i + 1], c], [P[i], c, d]);
}
export function addPoly(ctx, q) {                     // every polygon wound the same way: one nonzero fill = their union
  if (area(q) < 0) q = q.slice().reverse();
  ctx.moveTo(q[0][0], q[0][1]);
  for (let i = 1; i < q.length; i++) ctx.lineTo(q[i][0], q[i][1]);
  ctx.closePath();
}
function intersect(a, ta, b, tb) {             // line a + s ta meets b + u tb
  const d = ta[0] * tb[1] - ta[1] * tb[0];
  if (Math.abs(d) < 1e-6) return null;
  const s = ((b[0] - a[0]) * tb[1] - (b[1] - a[1]) * tb[0]) / d;
  return [a[0] + s * ta[0], a[1] + s * ta[1]];
}
// -> {canvas (grey RGB + alpha), alpha (Uint8Array), x0, y0, w, h} in local px x k (k > 1: the same stroke, drawn
// sharp at a larger size for export; its noise is laid out per px at k = 1, so the shape stays the same): render() below
const NOISE_KEYS = ["slow", "mid", "fine", "omid", "ofine", "grey"];
// The stroke's centre line, half widths, tangents and grey noise. Each noise array has its own random stream, so a
// sample's noise doesn't depend on the stroke's length: while a stroke is drawn (live), its start keeps its look.
// `prev` = the previous prepare of the same freehand stroke while it is drawn (live): its centre line, noise and buffers
// are extended instead of rebuilt; `from`: per-point values only from that point on (live() paints nothing before
// it). So a live frame's cost hardly grows with the stroke; without `prev` the same code runs from scratch.
export function prepare(v, k = 1, prev = null, from = 0) {
  const W = v.width * k, rough = v.rough ?? 1, buf = prev?.buf ?? {}, keep = !!prev;
  const f32 = (key, n) => keep ? (buf[key] = grow(buf[key] ?? new Float32Array(0), n)) : (buf[key] = new Float32Array(n));
  let P, spanOf, first, closed, spans, fp = 0;
  if (v.kind === "free" && !v.raw) {           // one span; resumable centre line
    const c = keep ? prev.line : {raw: []};
    P = freeLine(v, k, c);
    fp = keep ? c.fp ?? 0 : 0;
    buf.line = c;
    spans = [P]; first = [0]; closed = false;
    spanOf = buf.zeros = buf.zeros?.length >= P.length ? buf.zeros : new Uint8Array(Math.max(P.length, 2 * (buf.zeros?.length || 0), 1024));
  } else {
    const g = geometry(v, k);
    closed = g.closed;
    spans = g.spans.map(s => resample(s, 1)).filter(s => s.length);
    P = []; spanOf = []; first = [];
    spans.forEach((s, j) => { first.push(P.length); s.forEach(p => { P.push(p); spanOf.push(j); }); });
  }
  const n = P.length;
  const s = f32("s", n);
  s[0] = 0;
  for (let i = Math.max(1, fp); i < n; i++) s[i] = s[i - 1] + (spanOf[i] === spanOf[i - 1] ? dist(P[i - 1], P[i]) : 0);
  const n1 = Math.ceil(s[n - 1] / k) + 2;
  let nz = prev?.nz;
  if (!nz || prev.seed !== v.seed) nz = NOISE_KEYS.map((key, j) => noiseStream(NOISE[key], mulberry32((v.seed || 1) + j * 0x9E3779B1)));
  const at = (a, key) => {
    const out = f32(key, n);
    for (let j = from; j < n; j++) { const u = s[j] / k, i = Math.min(n1 - 2, Math.floor(u)); out[j] = a[i] + (a[i + 1] - a[i]) * (u - i); }
    return out;
  };
  const N6 = nz.map((z, j) => at(z.ensure(n1).out, "n" + j)), wn = N6.slice(0, 3), on = N6.slice(3, 5), gn = N6[5];
  if (closed && n > 8) {                       // the noise's end runs into its start over the last quarter: no seam
    const m = Math.min(40, n >> 2);
    for (const a of [...wn, ...on, gn]) { const jump = a[0] - a[n - 1]; for (let i = n - m; i < n; i++) a[i] += jump * (i - (n - m) + 1) / m; }
  }
  const L = s[n - 1] || 1, tl = TIP_LEN * W, tip = v.tip ?? .32, bn = (v.barbs ?? 0) > 0 ? BARB_NOISE : {wmid: 1, wfine: 1, omid: 1, ofine: 1};   // barbs carry part of the fine variation
  const hl = f32("hl", n), hr = f32("hr", n), G = f32("G", n), arr = key => keep ? (buf[key] ??= []) : new Array(n);
  const T = arr("T"), Lp = arr("Lp"), Rp = arr("Rp");
  for (let i = from; i < n; i++) {
    let k = 1;
    if (!closed) { if (v.taperStart) k = Math.min(k, s[i] / tl); if (v.taperEnd) k = Math.min(k, (L - s[i]) / tl); }
    const f = tip + (1 - tip) * Math.pow(Math.max(0, k), TIP_POW), w = rough * (wn[0][i] + bn.wmid * wn[1][i] + bn.wfine * wn[2][i]), o = rough * (bn.omid * on[0][i] + bn.ofine * on[1][i]);
    hl[i] = Math.max(.35, W / 2 * f * (1 + w + o));
    hr[i] = Math.max(.35, W / 2 * f * (1 + w - o));
    G[i] = 1 + rough * gn[i];
    const j = spanOf[i], a = P[i > 0 && spanOf[i - 1] === j ? i - 1 : i], b = P[i < n - 1 && spanOf[i + 1] === j ? i + 1 : i];
    let tx = b[0] - a[0], ty = b[1] - a[1];
    const m = Math.hypot(tx, ty) || 1;
    tx /= m; ty /= m;
    T[i] = [tx, ty];
    Lp[i] = [P[i][0] - ty * hl[i], P[i][1] + tx * hl[i]];   // left normal (-ty, tx)
    Rp[i] = [P[i][0] + ty * hr[i], P[i][1] - tx * hr[i]];
  }
  const barbs = barbsOf(v, s, n, L, W, k, closed), ex = f32("ex", n);   // ex: how far past the edge a barb reaches near each point
  ex.fill(0, from);
  for (const b of barbs) {                     // the points a barb's pixels can be nearest to: its base and its swept tip
    const reach = b.len + b.base / 2, span = (b.base / 2 + reach) / (k || 1);
    for (let j = Math.max(from, b.i - Math.ceil(span)); j <= Math.min(n - 1, b.i + Math.ceil(span)); j++) ex[j] = Math.max(ex[j], reach);
  }
  // sharp corners: the last point of a span and the first of the next are the same place, each with its own tangent
  const joins = [];
  for (let j = 1; j < spans.length; j++) joins.push([first[j] - 1, first[j]]);
  if (closed) joins.push([n - 1, 0]);             // also a closed path whose only corner is its start (one span, seam at it)
  // a freehand stroke's points up to this arc length no longer change when points are added (smoothing reach, the end
  // taper, a margin): what live() may paint for good
  const reach = 2 * k * (Math.ceil(2.5 * (.5 + 4 * (v.smooth ?? .5))) + 2) + (v.taperEnd ? tl : 0) + 2;
  return {n, W, P, spanOf, joins, closed, s, hl, hr, T, G, Lp, Rp, nz, buf, line: buf.line, seed: v.seed, barbs,
          stable: v.kind === "free" ? L - reach : -Infinity, ex};
}
// Barbs (user 7.0h: "a sort of thorny vine, other times smoother"): splinters on the edges, measured on 505 game icons
// (research/probes/barbs.py): 0.5 (smooth) to 3.9 (thorny) per 100 px of stroke. Their shape and flow
// (research/probes/barb_shapes.py, 4,999 spell barbs; user: ours "do not follow the flow of the vanilla versions"):
// sawteeth flowing one way along the stroke, not spikes. The free part beyond the edge lies at 25 deg to it (IQR 12-45,
// 2.1 times as long as wide), its tip over the front end (a third hook past it); the tall quarter stand up more (58 deg).
// So a barb = a splinter: it leaves the edge at a shallow angle over `base` (median .8 widths), rises to `len` at its
// front and drops back with a notch under the tip (`hook` of the base). Neighbours point the same way (same side 70%,
// opposite sides 62%): v.sweep = that way (+1 along the drawing, -1 back). v.barbs = per 100 px (0 = none; strokes
// saved before barbs existed have none). Positions come from their own random stream along the arc length, so a
// freehand stroke's barbs stay put while it is drawn; none on the tapered ends.
export const BARB = {len: [.27, .4], base: [.8, .35], hook: [.05, .08], same: .85};
// one barb's shape in px (also used to restyle game strokes)
export function barbShape(rnd, W) {
  const ln = ([m, s], lo, hi) => W * Math.min(hi, Math.max(lo, Math.exp(Math.log(m) + s * gauss(rnd))));
  return {len: ln(BARB.len, .15, .7), base: ln(BARB.base, .45, 2.2), hook: Math.min(.35, Math.max(-.1, BARB.hook[0] + BARB.hook[1] * gauss(rnd))),
          same: rnd() < BARB.same};
}
// the splinter's outline from edge point e, flow direction t (unit, the way it points), outward normal n: hugging the
// edge at the back (height grows with the way along to the power 1.5), the tip at the front, the front foot `hook` back
// under it; the feet sit .3 widths inside the stroke so a curving edge never leaves a gap. Big exports (user 7.0i:
// straight-sided thorns looked like cut paper at 2048) showed the game's are irregular and soft-tipped: the edges wobble
// by up to .04 widths (about the game's half pixel at 512) and the tip is rounded over .08 of the height, invisible at
// 512. The wobble comes from the barb's own size (no extra random numbers: barbs stay where they were). q.tip = the
// tip's index; the last point is the front foot.
const BACK = 10, FRONT = 4, WOB = .04, ROUND = .08;
export function barbPoly(e, t, n, b, W) {
  const at = (u, v) => [e[0] + t[0] * (u - b.base / 2) + n[0] * v, e[1] + t[1] * (u - b.base / 2) + n[1] * v];
  const hn = k => { const x = Math.sin(b.len * 912.7 + b.base * 77.3 + k * 78.233) * 43758.5453; return 2 * (x - Math.floor(x)) - 1; };
  const fu = b.base * (1 - b.hook) - .3 * W * b.hook, r = ROUND * b.len, q = [at(0, -.3 * W)];
  for (let k = 1; k < BACK; k++) { const s = k / BACK; q.push(at(b.base * s, b.len * s ** 1.5 + WOB * W * Math.sin(Math.PI * s) * hn(k))); }
  const back = [b.base * (1 - .12), b.len * .88 ** 1.5], bl = Math.hypot(b.base - back[0], b.len - back[1]) || 1;
  const front = [fu - b.base, -.3 * W - b.len], fl = Math.hypot(...front) || 1;
  q.push(at(b.base + (back[0] - b.base) / bl * r, b.len + (back[1] - b.len) / bl * r));        // the rounded tip
  q.tip = q.length;
  q.push(at(b.base + .3 * r * ((back[0] - b.base) / bl + front[0] / fl), b.len + .3 * r * ((back[1] - b.len) / bl + front[1] / fl)));
  q.push(at(b.base + front[0] / fl * r, b.len + front[1] / fl * r));
  for (let k = 1; k < FRONT; k++) { const s = k / FRONT; q.push(at(b.base + front[0] * s + WOB * W * .6 * Math.sin(Math.PI * s) * hn(20 + k), b.len + front[1] * s)); }
  q.push(at(fu, -.3 * W));
  return q;
}
// v.barbs is barbs per 100 px as the game is measured: on closed circles (no ends) the measure reads .26 from the wobble
// alone and .7 per splinter drawn (neighbours merge at high settings, some come out under 2 px): /?brushtest 2026-10-18
export const BARB_CAL = [.26, .8];
// with barbs the mid / fine width and centre noise is scaled down so barbs + noise measure like the game (/?brushtest
// 2026-10-18: barbs on top raised mid / fine 17-24%; the barbs' variance taken out per scale, mostly mid-scale width);
// strokes without barbs as before
export const BARB_NOISE = {wmid: .25, wfine: .6, omid: .7, ofine: .75};   // wmid: barbs dominate it on these clean runs
function barbsOf(v, s, n, L, W, k, closed) {
  const per = Math.max(0, (v.barbs ?? 0) - BARB_CAL[0]) / BARB_CAL[1] / 200;   // per px of each edge (the measure counts both sides)
  if (per <= 0 || n < 3) return [];
  const out = [], Lk = L / k, dir = v.sweep ?? -1, end = t => closed ? 0 : t ? TIP_LEN * W * .5 : W * .3;   // none on a taper
  for (const side of [1, -1]) {
    const rnd = mulberry32((v.seed || 1) + (side > 0 ? 0x5bd1e995 : 0x27d4eb2f));
    let j = 0;
    for (let pos = -Math.log(1 - rnd()) / per; pos < Lk; pos += -Math.log(1 - rnd()) / per) {
      const {len, base, hook, same} = barbShape(rnd, W), sweep = same ? dir : -dir, sb = pos * k;
      if (sb < end(v.taperStart) || sb > L - end(v.taperEnd)) continue;
      while (j < n - 1 && s[j + 1] <= sb) j++;
      out.push({i: j, s: sb, side, len, base, hook, sweep});
    }
  }
  return out.sort((a, b) => a.i - b.i);
}
function idxAt(s, n, sb, from) {                 // the point at arc length sb, searching out from index `from`
  let i = from;
  while (i > 0 && s[i] > sb) i--;
  while (i < n - 1 && s[i + 1] <= sb) i++;
  return i;
}
let scratch = {best: new Float32Array(0), near: new Int32Array(0)};
// Paints the stroke's points [i0, i1) (default: all); with an own range [o0, o1) only the pixels whose nearest centre
// point lies in it are kept, so pieces painted with overlapping ranges and disjoint own ranges tile the stroke.
export function paint(st, i0 = 0, i1 = st.n, o0 = i0, o1 = i1) {
  const {n, P, spanOf, closed, hl, hr, T, G, Lp, Rp} = st, own = o0 > 0 || o1 < n, polys = [];
  for (let i = i0; i < i1 - 1; i++) if (spanOf[i] === spanOf[i + 1]) segment(polys, P, Lp, Rp, i);
  for (const [a, b] of st.joins) if (a >= i0 && a < i1 && b >= i0 && b < i1) for (const side of [1, -1]) {
    // the join meets the body at its own edge points (an averaged half width left a sliver between them: a faint line
    // across corners at 2048, user 7.0i)
    const E = side > 0 ? Lp : Rp, pa = E[a], pb = E[b], c = P[b], h = side > 0 ? (hl[a] + hl[b]) / 2 : (hr[a] + hr[b]) / 2;
    const na = [-T[a][1] * side, T[a][0] * side], nb = [-T[b][1] * side, T[b][0] * side];
    const m = intersect(pa, T[a], pb, T[b]);
    if (m && dist(m, c) < MITRE * h) { polys.push([c, pa, m, pb]); continue; }
    // too sharp for a mitre: a round join (a bevel left a flat cut across sharp tips, seen at 2048, user 7.0i)
    let a0 = Math.atan2(na[1], na[0]), da = Math.atan2(nb[1], nb[0]) - a0;
    da -= 2 * Math.PI * Math.round(da / (2 * Math.PI));
    const k = Math.max(2, Math.ceil(Math.abs(da) / .3));
    const ha = dist(pa, c), hb = dist(pb, c);
    polys.push([c, pa, ...Array.from({length: k - 1}, (_, j) => { const s = (j + 1) / k, r = ha + (hb - ha) * s; return [c[0] + r * Math.cos(a0 + da * s), c[1] + r * Math.sin(a0 + da * s)]; }), pb]);
  }
  if (!closed && n > 1) for (const [i, d] of [[0, -1], [n - 1, 1]]) if (i >= i0 && i < i1) {   // pointed tips, half a width long
    const h = (hl[i] + hr[i]) / 2;
    polys.push([Lp[i], [P[i][0] + d * T[i][0] * h, P[i][1] + d * T[i][1] * h], Rp[i]]);
  }
  if (n === 1) {                               // a dot: enough sides that no facet shows (sagitta under .2 px; 16 at the usual sizes)
    const sides = Math.max(16, Math.ceil(Math.PI / Math.acos(Math.max(-1, 1 - .2 / hl[0]))));
    polys.push(Array.from({length: sides}, (_, k) => [P[0][0] + hl[0] * Math.cos(2 * k * Math.PI / sides), P[0][1] + hl[0] * Math.sin(2 * k * Math.PI / sides)]));
  }
  for (const b of st.barbs || []) if (b.i >= i0 && b.i < i1) {   // a splinter on the edge, pointing along the flow
    const t = T[b.i], nr = b.side > 0 ? [-t[1], t[0]] : [t[1], -t[0]];
    polys.push(barbPoly((b.side > 0 ? Lp : Rp)[b.i], [t[0] * b.sweep, t[1] * b.sweep], nr, b, st.W));
  }
  let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
  for (const q of polys) for (const [x, y] of q) { bx0 = Math.min(bx0, x); by0 = Math.min(by0, y); bx1 = Math.max(bx1, x); by1 = Math.max(by1, y); }
  const x0 = Math.floor(bx0) - 2, y0 = Math.floor(by0) - 2, w = Math.ceil(bx1) - x0 + 3, h = Math.ceil(by1) - y0 + 3;
  const cv = document.createElement("canvas");
  cv.width = w; cv.height = h;
  const ctx = cv.getContext("2d", {willReadFrequently: true});
  ctx.translate(-x0, -y0);
  ctx.beginPath();
  for (const q of polys) addPoly(ctx, q);
  ctx.fillStyle = "#fff";
  ctx.fill("nonzero");
  const img = ctx.getImageData(0, 0, w, h), d = img.data;
  // the canvas leaves a faint line (alpha ~210) where edges of the path's pieces meet inside the stroke (corners, tight
  // bends; seen at 2048, user 7.0i): a pixel with opaque pixels on both sides (across, down or diagonally) takes their
  // alpha. The outline never has opaque pixels on both sides, so only these lines change
  for (let y = 1, w4 = 4 * w; y < h - 1; y++) for (let q = (y * w + 1) * 4 + 3, qe = q + (w - 2) * 4; q < qe; q += 4) {
    const v = d[q];
    if (v >= 250 || v === 0 || (d[q - 4] < 250 && d[q - w4] < 250 && d[q - w4 - 4] < 250 && d[q - w4 + 4] < 250)) continue;   // no opaque side
    const m = Math.max(Math.min(d[q - 4], d[q + 4]), Math.min(d[q - w4], d[q + w4]), Math.min(d[q - w4 - 4], d[q + w4 + 4]), Math.min(d[q - w4 + 4], d[q + w4 - 4]));
    if (m >= 250) d[q] = m;
  }
  // grey: the cross-section profile at each pixel's nearest centre point (its own side's half width), x the grey noise.
  // Nearest first (squared distances only), the shading once per pixel afterwards. Scratch buffers are reused: a fresh
  // pair per live frame was ~0.4 MB of garbage, and the collections showed up as slow frames.
  if (scratch.best.length < w * h) scratch = {best: new Float32Array(2 * w * h), near: new Int32Array(2 * w * h)};
  const best = scratch.best.fill(Infinity, 0, w * h), near = scratch.near.fill(-1, 0, w * h);
  for (let i = i0; i < i1; i++) {
    const r = Math.max(hl[i], hr[i]) + 2 + (st.ex ? st.ex[i] : 0), cx = P[i][0] - x0, cy = P[i][1] - y0;
    const xa = Math.max(0, Math.floor(cx - r)), xb = Math.min(w - 1, Math.ceil(cx + r));
    for (let y = Math.max(0, Math.floor(cy - r)), yb = Math.min(h - 1, Math.ceil(cy + r)); y <= yb; y++) {
      const py = y + .5 - cy, py2 = py * py;
      for (let x = xa, k = y * w + xa; x <= xb; x++, k++) {
        const px = x + .5 - cx, d2 = px * px + py2;
        if (d2 < best[k]) { best[k] = d2; near[k] = i; }
      }
    }
  }
  const alpha = new Uint8Array(w * h);
  for (let k = 0; k < w * h; k++) {
    const i = near[k], a = own && (i < o0 || i >= o1) ? 0 : d[k * 4 + 3];
    let g = 0;
    if (a) {
      let q = 0, gm = 1;
      if (i >= 0) {
        const x = k % w, px = x + .5 - (P[i][0] - x0), py = (k - x) / w + .5 - (P[i][1] - y0);
        q = 1 - Math.sqrt(best[k]) / (T[i][0] * py - T[i][1] * px > 0 ? hl[i] : hr[i]);
        gm = G[i];
      }
      g = Math.round(255 * Math.min(1, greyAt(Math.max(0, Math.min(1, q))) * gm));
    }
    alpha[k] = d[k * 4 + 3] = a;
    d[k * 4] = d[k * 4 + 1] = d[k * 4 + 2] = g;
  }
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.putImageData(img, 0, 0);
  return {canvas: cv, alpha, x0, y0, w, h};
}

// Freehand strokes are painted in pieces of CHUNK points (a pixel is kept by the piece holding its nearest centre
// point; pieces overlap by `ov` points so each sees every polygon near its pixels). A stroke being drawn (live) paints
// each piece once, as soon as points added later can no longer change it, and every frame only the rest: a frame costs
// the same at 100 px or 10,000 px, and the stroke drawn is the stroke rendered later, pixel for pixel. (One path for
// the whole stroke rasterises its edges slightly differently, up to 10/255 alpha: hence pieces for render() too.)
const CHUNK = 128, overlap = st => Math.ceil(st.W * (st.barbs?.length ? 3 : 1)) + 4;   // barbs reach about 2 widths along
function settle(st, lv, final) {               // paint every whole piece that is settled; -> the last piece
  const ov = overlap(st);
  while (lv.upto + CHUNK + ov < st.n && (final || st.s[lv.upto + CHUNK + ov] < st.stable)) {
    const r = paint(st, Math.max(0, lv.upto - ov), lv.upto + CHUNK + ov, lv.upto, lv.upto + CHUNK);
    lv.pieces.push(r);
    lv.done?.getContext("2d").drawImage(r.canvas, r.x0, r.y0);
    lv.upto += CHUNK;
  }
  return paint(st, Math.max(0, lv.upto - ov), st.n, lv.upto, st.n);
}
function assemble(parts) {                     // pieces -> one canvas over their box (each owns its own pixels)
  if (parts.length === 1) return parts[0];
  const x0 = Math.min(...parts.map(r => r.x0)), y0 = Math.min(...parts.map(r => r.y0));
  const w = Math.max(...parts.map(r => r.x0 + r.w)) - x0, h = Math.max(...parts.map(r => r.y0 + r.h)) - y0;
  const cv = document.createElement("canvas");
  cv.width = w; cv.height = h;
  const ctx = cv.getContext("2d", {willReadFrequently: true});
  for (const r of parts) ctx.drawImage(r.canvas, r.x0 - x0, r.y0 - y0);
  const d = ctx.getImageData(0, 0, w, h).data, alpha = new Uint8Array(w * h);
  for (let k = 0; k < w * h; k++) alpha[k] = d[k * 4 + 3];
  return {canvas: cv, alpha, x0, y0, w, h};
}
export function render(v, k = 1) {
  const st = prepare(v, k);
  if (v.kind !== "free") return paint(st);
  const lv = {pieces: [], upto: 0}, last = settle(st, lv, true);
  return assemble([...lv.pieces, last]);
}
const stateOf = (v, lv) => prepare(v, 1, lv.st, Math.max(0, lv.upto - Math.ceil(v.width) - 4));
// a freehand stroke being drawn: lv.done (size x size, drawing px) + lv.last (its end, own box) show it, with disjoint
// pixels; call again after adding points
export function live(v, lv = null, size = 512) {
  if (!lv) {                                   // a CPU canvas: the editor reads it back each frame (Firefox: no GPU read back)
    const done = Object.assign(document.createElement("canvas"), {width: size, height: size});
    done.getContext("2d", {willReadFrequently: true});
    lv = {done, pieces: [], upto: 0};
  }
  lv.st = stateOf(v, lv);
  lv.last = settle(lv.st, lv, false);
  return lv;
}
// the stroke is finished: = render(v), from the pieces already painted
export function finish(v, lv) {
  const st = stateOf(v, lv), last = settle(st, lv, true);
  return assemble([...lv.pieces, last]);
}
