// node app/vectorize.check.mjs: vectorize() on drawn shapes (no browser needed; the page's "To vector strokes" also
// checks each result against the bitmap with match()).
import {vectorize, match, barbDensity, taperCut, pieces} from "./vectorize.js";

function draw(w, h, f) { const a = new Uint8Array(w * h); for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (f(x, y)) a[y * w + x] = 255; return a; }
const seg = (x, y, ax, ay, bx, by, r) => { const dx = bx - ax, dy = by - ay, t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(x - ax - t * dx, y - ay - t * dy) <= r; };
const ok = (c, msg) => { if (!c) { console.error("FAIL", msg); process.exit(1); } };

const line = vectorize(draw(120, 40, (x, y) => seg(x, y, 10, 20, 110, 20, 6)), 120, 40);
ok(line.marks?.length === 1 && Math.abs(line.marks[0].width - 13) < 3, `a line: 1 mark of width ~13, got ${JSON.stringify(line.marks?.map(m => m.width))}`);
const cross = vectorize(draw(120, 120, (x, y) => seg(x, y, 10, 10, 110, 110, 6) || seg(x, y, 110, 10, 10, 110, 6)), 120, 120);
ok(cross.marks?.length === 2, `a cross: 2 marks running straight through, got ${cross.marks?.length}`);
const dot = vectorize(draw(20, 20, (x, y) => Math.hypot(x - 10, y - 10) <= 4), 20, 20);
ok(dot.marks?.length === 1 && dot.marks[0].dab, "a dot: one round dab");
const ring = vectorize(draw(100, 100, (x, y) => Math.abs(Math.hypot(x - 50, y - 50) - 35) <= 5), 100, 100);
ok(ring.marks?.length === 1 && ring.marks[0].closed, `a ring: one closed path, got ${JSON.stringify(ring.marks?.map(m => m.closed))}`);
const gap = vectorize(draw(100, 100, (x, y) => Math.abs(Math.hypot(x - 50, y - 50) - 35) <= 5 && !(x > 70 && Math.abs(y - 50) < 2)), 100, 100);   // a 3 px cut through a 10 px ring
ok(gap.marks?.length === 1 && !gap.marks[0].closed, "a ring cut through: a visible gap stays open");
// a crescent's outline (the edge band of a crescent): its outer and inner arc meet at two sharp tips
const inC = (x, y) => Math.hypot(x - 80, y - 80) <= 40 && Math.hypot(x - 94, y - 80) >= 32;
const band = (x, y) => { let i = 0, o = 0; for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) if (dx * dx + dy * dy <= 16) inC(x + dx, y + dy) ? i++ : o++; return i && o; };
const cres = vectorize(draw(160, 160, band), 160, 160), loop = cres.marks?.find(m => m.closed);
ok(loop && loop.corner?.filter(Boolean).length === 2,
   `a crescent: one closed path with a corner at each tip (not two arcs capped side by side), got ${JSON.stringify(cres.marks?.map(m => [m.closed, m.corner?.filter(Boolean).length ?? 0, m.pts.length]))}`);
const a = draw(50, 50, (x, y) => seg(x, y, 5, 25, 45, 25, 5)), b = draw(50, 50, (x, y) => seg(x, y, 5, 26, 45, 26, 5));
ok(match(a, 0, 0, 50, 50, [{alpha: b, x0: 0, y0: 0, w: 50, h: 50}]) > .95, "match: a 1 px shift is the same look");
const spikes = (x, y) => seg(x, y, 10, 40, 210, 40, 6) || [30, 60, 90, 120, 150, 180].some(c => seg(x, y, c, 33, c + 6, 25, 1.6));
const plain = barbDensity(draw(220, 80, (x, y) => seg(x, y, 10, 40, 210, 40, 6)), 220, 80), thorny = barbDensity(draw(220, 80, spikes), 220, 80);
ok(plain < .6 && thorny > 2, `barbs per 100 px: a plain line ${plain.toFixed(2)} (~0), six spikes on 200 px ${thorny.toFixed(2)} (~3)`);
// tapered eraser: a 13 px bar cut by a disc narrows to ~.32 of its width at the cut and is whole 3 widths away; a bar
// that only passes near the eraser keeps its width
const bars = (x, y) => seg(x, y, 10, 20, 190, 20, 6) || seg(x, y, 10, 45, 190, 45, 6), hole = (x, y) => Math.hypot(x - 100, y - 20) <= 8;
const tb = draw(200, 60, bars), ta = draw(200, 60, (x, y) => bars(x, y) && !hole(x, y)), tf = taperCut(tb, ta, 200, 60);
const wide = (x, y0, y1) => { let c = 0; for (let y = y0; y < y1; y++) if (ta[y * 200 + x] * tf[y * 200 + x] >= 128) c++; return c; };
const [atCut, mid, far, other] = [wide(91, 0, 33), wide(72, 0, 33), wide(50, 0, 33), Math.min(...[60, 80, 91, 100, 120].map(x => wide(x, 33, 60)))];
ok(atCut >= 3 && atCut <= 6 && mid > atCut && mid < 13 && far === 13 && other === 13,
   `tapered cut: width 13 bar -> ${atCut} at the cut (~4), ${mid} halfway (~10), ${far} 3 widths away (13); the uncut bar ${other} (13)`);
// pieces: the tapered cut above leaves 4 (two halves of the cut bar, the whole bar, nothing else); each seed is bright
const pc = pieces(ta.map((v, i) => Math.round(v * tf[i])), 200, 60).list;
ok(pc.length === 3 && pc.every(p => p.peak === 255 && p.n > 300), `pieces after a cut: 3 bright pieces, got ${JSON.stringify(pc.map(p => [p.n, p.peak]))}`);
console.log("vectorize check passed: line, cross (2 marks), dot (dab), ring (closed), a cut ring (open), crescent (closed, corners at the tips), match tolerance, barb measure, tapered cut, pieces");
