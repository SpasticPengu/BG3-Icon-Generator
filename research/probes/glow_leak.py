"""Glow leaking into the line art (Phase 4 "Found while checking", user notes 4 / 15): per train + holdout icon, the share of
line pixels (AL > .5 at 512) whose master alpha is < .9 (made by glow, not a stroke), and the blob share (line pixels where a
25 px disk fits inside the mask: strokes are p95 20 px wide, so blobs are filled gaps or real filled shapes). Reports the old
split (one global ramp .45-.65 x the icon's p99 brightness) and the current glyph.split side by side, per kind (median, p90,
icons at .15+), the named icons and the worst; -> data/glow_leak.json.
Alpha < .9 over-counts on weapon actions whose lower strokes fade in alpha (Opening Attack, Steady, Hamstring Shot: .35-.39
with clean outlines either way) and on dark-line icons (Darkvision); look at a sheet before trusting a high value.
    anaconda python research/probes/glow_leak.py [ICON ...]          (default: every train + holdout icon, ~2 min)
    anaconda python research/probes/glow_leak.py --sheet OUT ICON ... (512 crops: master over the hotbar dark | old lines
                                                                        | current lines; glow-made line pixels red)"""
import sys, json
from multiprocessing import Pool
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.morphology import disk
from iconkit.extract import D
from iconkit import glyph

NAMED = ["Spell_Evocation_Fireball", "Action_Mag_SilencingBlade", "Action_Mag_GiantSubjugation"]
BLOB = disk(12)


def old_AL(x):
    B = glyph.bright(x)
    return np.clip((B / max(np.percentile(B, 99), 1e-3) - .45) / .2, 0, 1)


def leak(AL, a):
    m = AL > .5
    n = max(m.sum(), 1)
    return float((m & (a < .9)).sum() / n), float(ndimage.binary_opening(m, BLOB).sum() / n), float(m.mean())


def job(n):
    x = glyph.master(n)
    a = x[..., 3]
    o, c = leak(old_AL(x), a), leak(glyph.split(x, 512)["AL"], a)
    return n, {k + s: round(v[i], 4) for s, v in (("old", o), ("new", c)) for i, k in enumerate(("", "blob_", "cover_"))}


def sheet(out, names):
    """per icon one row of three 512 tiles; red = line pixels (AL > .5) with alpha < .9"""
    rows = []
    for n in names:
        x = glyph.master(n)
        a = x[..., 3:]
        over = x[..., :3] * a + glyph.SEEN * (1 - a)
        tiles = [over]
        for AL in (old_AL(x), glyph.split(x, 512)["AL"]):
            t = np.repeat(AL[..., None], 3, 2) * .85
            t[(AL > .5) & (x[..., 3] < .9)] = (1, .15, .1)
            tiles.append(t)
        rows.append(np.concatenate([np.pad(t, ((4, 4), (4, 4), (0, 0)), constant_values=.25) for t in tiles], 1))
    Image.fromarray((np.clip(np.concatenate(rows, 0), 0, 1) * 255).astype(np.uint8)).save(out)
    print(f"wrote {out}: master over the hotbar dark | old lines | current lines (red = AL > .5 with alpha < .9)")


def main(names):
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))["icons"]
    names = names or sorted(J)
    with Pool(glyph.POOL) as pool:
        R = dict(pool.map(job, names, chunksize=8))
    for kd in ("Spell", "Action", "Illithid"):
        ns = [n for n in R if J[n]["kind"] == kd]
        if ns:
            for k in ("old", "new"):
                v, b, c = (np.array([R[n][p + k] for n in ns]) for p in ("", "blob_", "cover_"))
                print(f"{kd:8s} {k}: n {len(v)}, glow-made share median {np.median(v):.3f}, p90 {np.percentile(v, 90):.3f}, "
                      f"{(v >= .15).sum()} at .15+; blob share median {np.median(b):.3f}, p90 {np.percentile(b, 90):.3f}; "
                      f"line cover median {np.median(c):.4f}")
    row = lambda n: (f"  {n:48s} glow-made {R[n]['old']:.3f} -> {R[n]['new']:.3f}, blob {R[n]['blob_old']:.3f} -> "
                     f"{R[n]['blob_new']:.3f}, cover {R[n]['cover_old']:.3f} -> {R[n]['cover_new']:.3f}")
    for n in [n for n in NAMED if n in R]:
        print(row(n))
    for k in ("old", "blob_old"):
        print(f"worst by {k}:")
        for n in sorted(R, key=lambda n: -R[n][k])[:12]:
            print(row(n))
    if len(names) > 100:
        (D / "glow_leak.json").write_text(json.dumps(R, indent=0), encoding="utf-8")
        print(f"wrote {D / 'glow_leak.json'}")


if __name__ == "__main__":
    a = sys.argv[1:]
    sheet(a[1], a[2:]) if a[:1] == ["--sheet"] else main(a)
