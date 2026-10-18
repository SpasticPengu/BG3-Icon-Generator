"""Barbs and thorns on the game's strokes (user 7.0h: "some vanilla examples look like a sort of thorny vine, other
times it's smoother"). The lines (alpha >= .5) are opened with a disc of radius OPEN x the icon's stroke width: what
the opening removes are the protrusions narrower than the stroke. Each removed piece (>= 4 px) is a barb: its length =
the farthest it reaches from the opened body, its base = how many of its pixels touch the body, its lean = the angle
between its axis (base middle -> tip) and the body's outward normal there (0 = straight out). Barbs longer than THORN x
the width are thorns. Per icon: barbs and thorns per 100 px of stroke (the body's skeleton length). Prints the spread,
the smoothest and the thorniest icons, and draws the named ones with every barb / thorn tip marked (check by eye).
args: OUT.png [N icons]"""
import json, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from iconkit.editor import read_strokes, E
from iconkit.lab import skeletonize, disk

OPEN, THORN = .4, 1.0
out, N = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 300
idx = [e for e in json.loads((E / "index.json").read_text(encoding="utf-8"))["icons"] if e["k"] in ("Spell", "Action", "Illithid")]
rng = np.random.default_rng(0)
must = ["Spell_Transmutation_ThornWhip", "Spell_Conjuration_GraspingVine", "Spell_Necromancy_FalseLife", "Spell_Conjuration_Entangled",
        "Spell_Abjuration_ArcaneLock", "Spell_Evocation_Fireball"]
names = list(dict.fromkeys(must + [idx[i]["n"] for i in sorted(rng.choice(len(idx), min(N, len(idx)), replace=False))]))
rows, allb, draw, same = [], [], [], []
for n in names:
    la, _ = read_strokes(n)
    m = la[..., 1] >= 128
    if m.sum() < 500:
        continue
    dt = ndimage.distance_transform_edt(m)
    sk = skeletonize(m)
    W = 2 * float(np.median(dt[sk]))
    body = ndimage.binary_opening(m, disk(max(1, int(round(OPEN * W)))))
    res = m & ~body
    bsk = skeletonize(body)
    length = float(bsk.sum())
    if length < 60:
        continue
    dout = ndimage.distance_transform_edt(~body)                 # distance from the body, outside it
    gy, gx = np.gradient(ndimage.gaussian_filter(dout, 2))
    lab, k = ndimage.label(res, np.ones((3, 3)))
    barbs, thorns, marks, sweeps = 0, 0, [], []
    for j, sl in enumerate(ndimage.find_objects(lab), 1):
        piece = lab[sl] == j
        if piece.sum() < 4:
            continue
        ys, xs = np.nonzero(piece)
        ys, xs = ys + sl[0].start, xs + sl[1].start
        d = dout[ys, xs]
        if d.max() < 2:
            continue
        tip = np.argmax(d)
        base = d <= 1.5
        if not base.any():
            continue
        by, bx = ys[base].mean(), xs[base].mean()
        ax = np.array([ys[tip] - by, xs[tip] - bx]); ax /= np.hypot(*ax) or 1
        nr = np.array([gy[int(by), int(bx)], gx[int(by), int(bx)]]); nr /= np.hypot(*nr) or 1
        lean = float(np.degrees(np.arccos(np.clip(ax @ nr, -1, 1))))
        L = float(d.max())
        thorn = L > THORN * W
        thorns += thorn; barbs += not thorn
        allb.append((L / W, base.sum() / W, lean, thorn))
        marks.append(("thorn" if thorn else "barb", (ys[tip], xs[tip])))
        if not thorn and lean > 10:                           # sweep: which way along the edge the tip leans
            sweeps.append((by, bx, nr, float(nr[0] * ax[1] - nr[1] * ax[0]), W))
    for i, (y1, x1, n1, s1, w1) in enumerate(sweeps):             # neighbours on the same side: same sweep?
        for y2, x2, n2, s2, w2 in sweeps[i + 1:]:
            if np.hypot(y1 - y2, x1 - x2) < 3 * W and n1 @ n2 > .8:
                same.append(np.sign(s1) == np.sign(s2))
    rows.append({"n": n, "W": W, "barbs": 100 * barbs / length, "thorns": 100 * thorns / length})
    if n in must:
        draw.append((n, m, marks))
B = np.array(allb, float)
b = np.array([r["barbs"] for r in rows]); t = np.array([r["thorns"] for r in rows])
small, big = B[B[:, 3] == 0], B[B[:, 3] == 1]
print(f"{len(rows)} icons; {len(small)} barbs, {len(big)} thorns; stroke width median {np.median([r['W'] for r in rows]):.1f} px")
print("barbs per 100 px of stroke, icons p10/25/50/75/90:", np.percentile(b, [10, 25, 50, 75, 90]).round(1).tolist())
print("thorns per 100 px, icons p50/75/90/95:", np.percentile(t, [50, 75, 90, 95]).round(2).tolist())
for name, S in (("barb", small), ("thorn", big)):
    if len(S):
        print(f"{name}: length / width p25/50/75 {np.percentile(S[:, 0], [25, 50, 75]).round(2).tolist()}, base / width "
              f"{np.percentile(S[:, 1], [25, 50, 75]).round(2).tolist()}, lean from the normal (deg) {np.percentile(S[:, 2], [25, 50, 75]).round(0).tolist()}")
print(f"sweep: neighbouring barbs on the same side lean the same way in {np.mean(same):.2f} of {len(same)} pairs (random: .5)")
srt = sorted(rows, key=lambda r: r["barbs"])
print("smoothest:", [(r["n"].split("_", 2)[-1], round(r["barbs"], 1)) for r in srt[:8]])
print("most barbed:", [(r["n"].split("_", 2)[-1], round(r["barbs"], 1)) for r in srt[-8:]])
print("most thorns:", [(r["n"].split("_", 2)[-1], round(r["thorns"], 2)) for r in sorted(rows, key=lambda r: -r["thorns"])[:8]])
KIND = {e["n"]: e["k"] for e in idx}
for kd in ("Spell", "Action", "Illithid"):
    v = np.array([r["barbs"] for r in rows if KIND.get(r["n"]) == kd])
    print(f"{kd}: {len(v)} icons, barbs per 100 px p25/50/75 {np.percentile(v, [25, 50, 75]).round(1).tolist()}, share over 2.5: {(v > 2.5).mean():.2f}")
print("the six named (barbs, thorns /100 px):", [(r["n"].split("_", 2)[-1], round(r["barbs"], 1), round(r["thorns"], 2)) for r in rows if r["n"] in must])
T = 360
im = Image.new("RGB", (3 * (T + 6), 2 * (T + 6)), (30, 30, 30))
for k, (n, mm, marks) in enumerate(draw[:6]):
    tt = Image.fromarray((mm * 170).astype(np.uint8)).convert("RGB")
    dr = ImageDraw.Draw(tt)
    for kind, (y, x) in marks:
        c = (255, 70, 50) if kind == "barb" else (60, 190, 255)
        dr.ellipse((x - 3, y - 3, x + 3, y + 3), outline=c, width=2)
    im.paste(tt.resize((T, T)), ((k % 3) * (T + 6), (k // 3) * (T + 6)))
im.save(out)
print(out, "(red = barb tips, blue = thorn tips)")
