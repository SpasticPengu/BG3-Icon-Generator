"""Where does the current hotbar fit still miss, colour by colour? (round-5 pattern: run this before changing the recipe,
to tell a systematic gap from one icon's quirk.) Per kind x colour preset with >= 5 usable icons (train + test), with the
fitted recipes and default frames of data/hotbar.json:
  - game - ours L* by distance from the centre (hotbar.RINGS) for bare stone / soft glow / line rim / line middle
  - glow and line-middle hue (game - ours, degrees, CIELAB) and chroma (game, ours)
  - L* above the bare frame 0-1.5 / 1.5-2.5 / 2.5-4 / 4-7 px outside the lines (game | ours)
  - contrast of the bare frame (slope of L* on the frame's own L*, game | ours)
  - line middle minus line rim L* (game | ours)
Illithid cells are lined up as the fit lines them up (eval.registered). Writes a JSON next to the printout.
    anaconda python research/probes/colour_residuals.py OUT.json   (~5 min)"""
import sys, json, time, warnings
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.filterwarnings("ignore")
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.color import rgb2lab
from iconkit import hotbar as hb
from iconkit.extract import D, read_jsonl

t0 = time.time()
log = lambda *a: print(f"[{time.time() - t0:5.0f} s]", *a, flush=True)
H = json.loads((D / "hotbar.json").read_text(encoding="utf-8"))
G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
pre = {n: v["preset"] for n, v in G["icons"].items()}
rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
train, hold = (set((D / f).read_text().split()) for f in ("train.txt", "holdout.txt"))
odd, reg = H["eval"]["not_same_size"], H["eval"].get("registered", {})
hot, B = hb.atlas(), hb.backgrounds()
names = [n for n in sorted(train | hold) if n in hot and n in rows and n in pre and n not in odd
         and (D / "masters" / f"{n}.png").exists()]
log(f"{len(names)} icons")
DOUT = ((0, 1.5), (1.5, 2.5), (2.5, 4), (4, 7))


def hue(l, m):
    C = np.hypot(l[..., 1], l[..., 2])[m]
    return np.degrees(np.arctan2((l[..., 2][m] * C).sum(), (l[..., 1][m] * C).sum())), float(np.median(C))


acc = defaultdict(lambda: defaultdict(list))
for j, n in enumerate(names):
    m = Image.open(D / "masters" / f"{n}.png").convert("RGBA")
    q = hb.registered(m, reg[n]) if n in reg else hb.down(m)
    p, kd = pre[n], hb.kind(n)
    F = hb.frame_img(B, hb.frame(H, n, p))
    ours, g = hb.glyph_over(q, F, hb.recipe_for(H, n, p)), hot[n]
    Lg, Lo, LF = rgb2lab(np.clip(g, 0, 1)), rgb2lab(np.clip(ours, 0, 1)), rgb2lab(np.clip(F, 0, 1))
    a = q[..., 3]
    line = a > .5
    depth, dist = ndimage.distance_transform_edt(line), ndimage.distance_transform_edt(~line)
    far = hb.far_mask(q)
    kinds = {"stone": far, "glow": (a >= .03) & (a < .5), "rim": line & (depth <= 1.0), "mid": line & (depth >= 2.0)}
    A = acc[(kd, p)]
    A["n"].append(n)
    for k, mk in kinds.items():
        A[f"ring_{k}"].append([float((Lg[..., 0] - Lo[..., 0])[s].mean()) if (s := mk & (hb.RR >= hb.RINGS[i]) & (hb.RR < hb.RINGS[i + 1])).sum() >= 3
                               else np.nan for i in range(len(hb.RINGS) - 1)])
    for k in ("glow", "mid"):
        if kinds[k].sum() >= 10:
            (hg, cg), (ho, co) = hue(Lg, kinds[k]), hue(Lo, kinds[k])
            A[f"hue_{k}"].append(((hg - ho + 180) % 360) - 180)
            A[f"chroma_{k}"].append((cg, co))
    A["out"].append([[float((Lg[..., 0] - LF[..., 0])[s].mean()), float((Lo[..., 0] - LF[..., 0])[s].mean())]
                     if (s := ~line & (dist > d0) & (dist <= d1)).sum() >= 3 else [np.nan, np.nan] for d0, d1 in DOUT])
    if far.sum() > 50:
        A["slope"].append((np.polyfit(LF[..., 0][far], Lg[..., 0][far], 1)[0], np.polyfit(LF[..., 0][far], Lo[..., 0][far], 1)[0]))
    if kinds["rim"].sum() >= 5 and kinds["mid"].sum() >= 5:
        A["cross"].append((Lg[..., 0][kinds["mid"]].mean() - Lg[..., 0][kinds["rim"]].mean(),
                           Lo[..., 0][kinds["mid"]].mean() - Lo[..., 0][kinds["rim"]].mean()))
    if j % 200 == 0:
        log(f"  {j}/{len(names)}")

res = {}
f1 = lambda v: "  n/a" if v != v else f"{v:+5.1f}"
for (kd, p), A in sorted(acc.items(), key=lambda x: (x[0][0], -len(x[1]["n"]))):
    if len(A["n"]) < 5:
        continue
    r = {"n": len(A["n"]), "own_recipe": p in H["recipe"][kd]}
    print(f"\n{kd} / {p}: {r['n']} icons, {'own' if r['own_recipe'] else 'shared'} recipe")
    for k in ("stone", "glow", "rim", "mid"):
        v = np.nanmean(np.array(A[f"ring_{k}"], float), 0)
        r[f"ring_{k}"] = v.round(2).tolist()
        print(f"   game-ours L* by ring {k:5s} " + " ".join(f1(x) for x in v))
    for k in ("glow", "mid"):
        if A[f"hue_{k}"]:
            c = np.array(A[f"chroma_{k}"])
            r[f"hue_{k}"], r[f"chroma_{k}"] = float(np.median(A[f"hue_{k}"])), np.median(c, 0).round(1).tolist()
            print(f"   {k:4s} hue game-ours {r[f'hue_{k}']:+5.1f} deg, chroma game {r[f'chroma_{k}'][0]} ours {r[f'chroma_{k}'][1]}")
    o = np.nanmean(np.array(A["out"], float), 0)
    r["out"] = o.round(2).tolist()
    print("   outside lines L* above frame (game|ours): " + " ".join(f"{d0:g}-{d1:g}px {x[0]:+.1f}|{x[1]:+.1f}" for (d0, d1), x in zip(DOUT, o)))
    for k, lab in (("slope", "bare frame contrast"), ("cross", "line middle - rim L*")):
        if A[k]:
            s = np.median(np.array(A[k]), 0)
            r[k] = s.round(3).tolist()
            print(f"   {lab}: game {s[0]:.2f} ours {s[1]:.2f}")
    res[f"{kd}/{p}"] = r
Path(sys.argv[1]).write_text(json.dumps(res, indent=1), encoding="utf-8")
log(f"wrote {sys.argv[1]}")
