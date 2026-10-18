"""Barb shape and flow (user 7.0h: our barbs "do not look good or follow the flow of the vanilla versions"). Same
barbs as barbs.py (opening by a disc of .4 x the stroke width; removed pieces of >= 4 px reaching 2 px .. 1 width). Each
barb in its own frame: v = distance out of the body, u = along the body's edge (tangent at the base), signed so the
tip lies at u >= the base middle; both in stroke widths. Prints per kind: base span, height, where the tip sits over
the base (0 = over the back end, .5 = middle, 1 = over the front end, > 1 = hooked past it), and whether neighbours
point the same way along the stroke (same side and opposite sides). Draws the mean silhouette (u right, v up) and the
24 tallest barbs of one icon per kind, in their frame. args: OUT.png [N icons]"""
import json, sys
import numpy as np
from PIL import Image
from scipy import ndimage
from iconkit.editor import read_strokes, E
from iconkit.lab import skeletonize, disk

OPEN, G = .4, 64                                 # grid: u in [-1.5, 1.5] W, v in [0, 1.5] W
out, N = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 200
idx = [e for e in json.loads((E / "index.json").read_text(encoding="utf-8"))["icons"] if e["k"] in ("Spell", "Action", "Illithid")]
rng = np.random.default_rng(0)
pick = [idx[i] for i in sorted(rng.choice(len(idx), min(N, len(idx)), replace=False))]
stats = {k: [] for k in ("Spell", "Action", "Illithid")}
mean = {k: np.zeros((G, 2 * G)) for k in stats}
pairs = {k: {"same": [], "opp": []} for k in stats}
crops = {}
for e in pick:
    n, kd = e["n"], e["k"]
    la, _ = read_strokes(n)
    m = la[..., 1] >= 128
    if m.sum() < 500:
        continue
    dt = ndimage.distance_transform_edt(m)
    W = 2 * float(np.median(dt[skeletonize(m)]))
    body = ndimage.binary_opening(m, disk(max(1, int(round(OPEN * W)))))
    dout = ndimage.distance_transform_edt(~body)
    gy, gx = np.gradient(ndimage.gaussian_filter(dout, 2))
    lab, _ = ndimage.label(m & ~body, np.ones((3, 3)))
    found = []
    for j, sl in enumerate(ndimage.find_objects(lab), 1):
        piece = lab[sl] == j
        if piece.sum() < 4:
            continue
        ys, xs = np.nonzero(piece)
        ys, xs = ys + sl[0].start, xs + sl[1].start
        d = dout[ys, xs]
        if d.max() < 2 or d.max() > W:
            continue
        base = d <= 1.5
        if base.sum() < 2:
            continue
        by, bx = ys[base].mean(), xs[base].mean()
        nr = np.array([gy[int(by), int(bx)], gx[int(by), int(bx)]]); nr /= np.hypot(*nr) or 1
        t = np.array([-nr[1], nr[0]])
        tip = np.argmax(d)
        u = (ys - by) * t[0] + (xs - bx) * t[1]
        if u[tip] < 0:
            t, u = -t, -u
        ub = u[base]
        span = ub.max() - ub.min()
        f = (u[tip] - ub.min()) / span if span > 0 else .5
        vv = (ys - by) * nr[0] + (xs - bx) * nr[1]               # the piece's own axis: angle to the edge, length
        cu, cv = u - u.mean(), vv - vv.mean()
        ev, evec = np.linalg.eigh(np.cov(np.stack([cu, cv])) + 1e-6 * np.eye(2))
        ang = float(np.degrees(np.arctan2(abs(evec[1, 1]), abs(evec[0, 1]))))   # 0 = along the edge, 90 = straight out
        stats[kd].append((span / W, d.max() / W, f, piece.sum() / W ** 2, ang, 4 * np.sqrt(ev[1]) / W, np.sqrt(ev[1] / max(ev[0], 1e-6))))
        gu = np.clip(((u / W + 1.5) / 3 * 2 * G).astype(int), 0, 2 * G - 1)
        gv = np.clip((d / W / 1.5 * G).astype(int), 0, G - 1)
        mean[kd][G - 1 - gv, gu] += 1 / len(ys)
        found.append((by, bx, nr, t, d.max(), (ys, xs, u, d)))
    for i, (y1, x1, n1, t1, *_ ) in enumerate(found):
        for y2, x2, n2, t2, *_ in found[i + 1:]:
            if np.hypot(y1 - y2, x1 - x2) < 3 * W:
                if n1 @ n2 > .8:
                    pairs[kd]["same"].append(t1 @ t2 > 0)
                elif n1 @ n2 < -.5:
                    pairs[kd]["opp"].append(t1 @ t2 > 0)
    if len(found) >= 24 and kd not in crops:
        crops[kd] = (n, W, sorted(found, key=lambda f: -f[4])[:24])
for kd, S in stats.items():
    S = np.array(S)
    if not len(S):
        continue
    p = lambda c: np.percentile(S[:, c], [25, 50, 75]).round(2).tolist()
    print(f"{kd}: {len(S)} barbs; base span / W {p(0)}, height / W {p(1)}, tip over the base (0 back, 1 front) {p(2)}, "
          f"share hooked past the front {(S[:, 2] > 1).mean():.2f}, area / W^2 {p(3)}")
    print(f"   own axis: angle to the edge (deg, 0 = along) {p(4)}, length / W {p(5)}, elongation {p(6)}; "
          f"tallest quarter: angle {np.percentile(S[S[:, 1] > np.percentile(S[:, 1], 75), 4], [25, 50, 75]).round(0).tolist()}")
    ps = pairs[kd]
    print(f"   neighbours point the same way: same side {np.mean(ps['same']):.2f} of {len(ps['same'])}, "
          f"opposite sides {np.mean(ps['opp']) if ps['opp'] else float('nan'):.2f} of {len(ps['opp'])}")
C = 96
im = Image.new("L", (2 * G * 3 + 12, G + 6 + 4 * C), 20)
for k, kd in enumerate(stats):
    a = mean[kd] / max(mean[kd].max(), 1e-9)
    im.paste(Image.fromarray((a * 255).astype(np.uint8)), (k * (2 * G + 6), 0))
for k, (kd, (n, W, fs)) in enumerate(crops.items()):
    print("crops:", kd, n, f"W {W:.1f}")
    for i, (*_, (ys, xs, u, d)) in enumerate(fs[:8]):
        c = np.zeros((C // 2, C), np.uint8)
        s = C / 3 / W
        c[np.clip((C // 2 - 1 - d * s).astype(int), 0, C // 2 - 1), np.clip((C / 2 + u * s).astype(int), 0, C - 1)] = 255
        c = ndimage.grey_dilation(c, size=(2, 2))
        im.paste(Image.fromarray(c), (i % 2 * (C + 4) + k * (2 * C + 12) % (2 * G * 3), G + 6 + (i // 2) * (C // 2 + 4)))
im.save(out)
print(out, "(top: mean silhouette per kind, u right / v up; below: tallest barbs of one icon per kind)")
