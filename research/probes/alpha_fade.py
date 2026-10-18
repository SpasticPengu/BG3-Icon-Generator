"""(a) Can alpha be recovered from an over-black render? (emissive-glow test)
(b) Tooltip bottom-fade profile: median alpha_tooltip / alpha_controller per row.
(c) StatusData icon reuse. (d) Pillow DDS write support."""
import sys, csv, re, random
from pathlib import Path
from collections import Counter
import numpy as np
from PIL import Image

U = (Path.home() / r"Documents\BG3 Modding\BG3 Modders Multitool\UnpackedData")
G = U / "GUI/Public/Game/GUI/Assets"
OUT = Path(sys.argv[1])
rows = [r for r in csv.DictReader(open(OUT / "icons.csv", encoding="utf-8")) if r["has_ctl"] == "True" and r["has_tip"] == "True"]
random.seed(0); sample = random.sample(rows, 300)

# (a) over-black: I = rgb*a. Reconstruct a' = max(I)/255 scaled; measure error and dark-opaque fraction.
errs, dark, by_prefix = [], [], {}
for r in sample:
    c = np.asarray(Image.open(G / "ControllerUIIcons/skills_png" / f"{r['icon']}.DDS").convert("RGBA")).astype(float) / 255
    a = c[:, :, 3]; I = c[:, :, :3] * a[:, :, None]
    a2 = I.max(axis=2)
    e = np.abs(a2 - a)[a > 0.02].mean()
    dk = ((a > 0.8) & (c[:, :, :3].max(axis=2) < 0.35)).sum() / max(1, (a > 0.8).sum())
    errs.append(e); dark.append(dk); by_prefix.setdefault(r["prefix"], []).append((e, dk))
print(f"(a) alpha-from-max(RGB) on over-black render: mean |da| = {np.mean(errs):.3f}, median {np.median(errs):.3f}")
print(f"    dark-opaque pixel share (a>0.8 & max<0.35) median {np.median(dark):.3f}, icons with >10%: {sum(d > .10 for d in dark)}/{len(dark)}")
for p, v in by_prefix.items():
    print(f"    {p:16s} n={len(v):3d} mean|da|={np.mean([x[0] for x in v]):.3f} dark>10%: {sum(x[1] > .1 for x in v)}")

# (b) fade profile
prof = []
for r in sample[:150]:
    t = np.asarray(Image.open(G / "Tooltips/Icons" / f"{r['icon']}.DDS").convert("RGBA")).astype(float)[:, :, 3] / 255
    c = np.asarray(Image.open(G / "ControllerUIIcons/skills_png" / f"{r['icon']}.DDS").convert("RGBA").resize((380, 380), Image.BICUBIC)).astype(float)[:, :, 3] / 255
    ratio = np.where(c > 0.5, t / np.maximum(c, 1e-3), np.nan)
    prof.append(np.nanmedian(ratio, axis=1))
prof = np.nanmedian(np.array(prof), axis=0)
print("(b) tooltip/controller alpha ratio by row (every 19 rows, 380 total):")
print("   ", " ".join(f"{y}:{prof[y]:.2f}" for y in range(0, 380, 19)))
cols = []
for r in sample[:150]:
    t = np.asarray(Image.open(G / "Tooltips/Icons" / f"{r['icon']}.DDS").convert("RGBA")).astype(float)[:, :, 3] / 255
    c = np.asarray(Image.open(G / "ControllerUIIcons/skills_png" / f"{r['icon']}.DDS").convert("RGBA").resize((380, 380), Image.BICUBIC)).astype(float)[:, :, 3] / 255
    band = slice(300, 340)
    rr = np.where(c[band] > 0.5, t[band] / np.maximum(c[band], 1e-3), np.nan)
    cols.append(np.nanmedian(rr, axis=0))
cols = np.nanmedian(np.array(cols), axis=0)
print("    horizontal check rows 300-340 (every 38 cols):", " ".join(f"{x}:{cols[x]:.2f}" for x in range(0, 380, 38)))

# (c) statuses: which icons do StatusData entries use?
BR = (Path.home() / r"Documents\BG3 Modding\BG3 Modders Multitool\UnpackedMods\BaseGameReference")
cnt = Counter(); ex = {}
for f in BR.glob("**/Stats/Generated/Data/Status_*.txt"):
    for m in re.finditer(r'data "Icon" "([^"]+)"', f.read_text(encoding="utf-8", errors="replace")):
        k = m.group(1).split("_")[0]; cnt[k] += 1; ex.setdefault(k, m.group(1))
print("(c) StatusData icon prefixes:", ", ".join(f"{k} {v} (e.g. {ex[k]})" for k, v in cnt.most_common(10)))

# (d) Pillow DDS write
try:
    im = Image.new("RGBA", (64, 64), (255, 0, 0, 128))
    for fmt in ("DXT1", "DXT5", "BC5", "BC7"):
        try:
            im.save(OUT / f"t_{fmt}.dds", pixel_format=fmt); back = Image.open(OUT / f"t_{fmt}.dds"); back.load()
            print(f"(d) Pillow writes {fmt}: ok ({(OUT / f't_{fmt}.dds').stat().st_size} B)")
        except Exception as e:
            print(f"(d) Pillow writes {fmt}: NO ({e})")
except Exception as e:
    print("(d) failed", e)
