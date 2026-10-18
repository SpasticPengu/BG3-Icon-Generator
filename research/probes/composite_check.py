"""Is hotbar64 == background ⊕ controller-icon (alpha over)? Per icon: best bg + residual; and the
un-composited background estimate (what sits under the glyph). Rows: hotbar | pred | |diff|x4 | bg-estimate."""
import re, sys, csv
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

U = (Path.home() / r"Documents\BG3 Modding\BG3 Modders Multitool\UnpackedData")
G = U / "GUI/Public/Game/GUI/Assets"
OUT = Path(sys.argv[1]); NAMES = sys.argv[2].split(",")
maps = {}
for lsx in [U / "GUI/Public/Shared/GUI/Icons_Skills.lsx", U / "GUI/Public/SharedDev/GUI/Icons_Skills.lsx"]:
    t = lsx.read_text(encoding="utf-8")
    dds = U / "Icons" / lsx.parent.parent.relative_to(U / "GUI") / re.search(r'id="Path" type="string" value="([^"]+)"', t).group(1)
    for m in re.finditer(r'MapKey" type="FixedString" value="([^"]+)"/>\s*<attribute id="U1" type="float" value="([^"]+)"/>\s*<attribute id="U2" type="float" value="([^"]+)"/>\s*<attribute id="V1" type="float" value="([^"]+)"/>\s*<attribute id="V2" type="float" value="([^"]+)"', t):
        maps.setdefault(m.group(1), (dds, *map(float, m.groups()[1:])))
bgs = {p.stem.replace("_bg", ""): np.asarray(Image.open(p).convert("RGB").resize((64, 64), Image.LANCZOS)).astype(float)
       for p in sorted((G / "ControllerUIIcons/icon_bg_png").glob("*.DDS"))}
atl = {}
def hotbar(icon):
    dds, u1, u2, v1, v2 = maps[icon]
    if dds not in atl: atl[dds] = Image.open(dds).convert("RGB")
    A = atl[dds]
    return np.asarray(A.crop((round(u1 * A.width), round(v1 * A.height), round(u2 * A.width), round(v2 * A.height))).resize((64, 64), Image.LANCZOS)).astype(float)

S = 144
sheet = Image.new("RGB", (5 * (S + 6), len(NAMES) * (S + 18)), (20, 20, 20)); d = ImageDraw.Draw(sheet)
for i, n in enumerate(NAMES):
    h = hotbar(n)
    c = np.asarray(Image.open(G / "ControllerUIIcons/skills_png" / f"{n}.DDS").convert("RGBA").resize((64, 64), Image.LANCZOS)).astype(float)
    a = c[:, :, 3:4] / 255; rgb = c[:, :, :3]
    # premultiplied-safe over: pred = rgb*a + bg*(1-a)
    res = {k: np.abs(rgb * a + b * (1 - a) - h).mean() for k, b in bgs.items()}
    best = min(res, key=res.get)
    pred = rgb * a + bgs[best] * (1 - a)
    with np.errstate(divide="ignore", invalid="ignore"):
        est = np.where(a < 0.85, (h - rgb * a) / np.maximum(1 - a, 1e-3), 0).clip(0, 255)
    y = i * (S + 18)
    for j, im in enumerate([h, pred, np.abs(pred - h) * 4, est]):
        sheet.paste(Image.fromarray(im.clip(0, 255).astype(np.uint8)).resize((S, S), Image.NEAREST), (j * (S + 6), y + 16))
    sheet.paste(Image.fromarray(bgs[best].astype(np.uint8)).resize((S, S)), (4 * (S + 6), y + 16))
    top3 = sorted(res, key=res.get)[:3]
    d.text((2, y + 2), f"{n}  best={best} err={res[best]:.1f}  next: " + ", ".join(f"{k} {res[k]:.1f}" for k in top3[1:]), fill=(255, 255, 0))
    print(f"{n:45s} best={best:30s} err={res[best]:5.1f}  2nd={top3[1]} {res[top3[1]]:.1f}")
sheet.save(OUT / "composite_check.png"); print("wrote composite_check.png")
