"""Spell <-> passive/action icon pairs (same name suffix): is the passive the same glyph recoloured?
Shape = alpha IoU (a>0.3) at 144px; colour = dominant hue of each (from icons.csv)."""
import csv, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

G = (Path.home() / r"Documents\BG3 Modding\BG3 Modders Multitool\UnpackedData\GUI\Public\Game\GUI\Assets\ControllerUIIcons\skills_png")
OUT = Path(sys.argv[1])
rows = {r["icon"]: r for r in csv.DictReader(open(OUT / "icons.csv", encoding="utf-8")) if r["has_ctl"] == "True"}
spells = {}
for n in rows:
    if n.startswith("Spell_"):
        parts = n.split("_")
        spells.setdefault("_".join(parts[2:]).lower(), n)  # Spell_<School>_<Name>
pairs = []
for n in rows:
    if n.startswith(("PassiveFeature_", "Action_")):
        key = n.split("_", 1)[1].lower()
        if key in spells:
            pairs.append((spells[key], n))
def a(n): return np.asarray(Image.open(G / f"{n}.DDS").convert("RGBA")).astype(float)[:, :, 3] / 255
print(f"pairs found by name: {len(pairs)}")
ious = []
for s, p in pairs:
    A, B = a(s) > 0.3, a(p) > 0.3
    iou = (A & B).sum() / max(1, (A | B).sum()); ious.append(iou)
    print(f"  {s:42s} {rows[s]['hue_name']:9s} -> {p:42s} {rows[p]['hue_name']:9s} IoU={iou:.2f}")
print("IoU quantiles 25/50/75:", np.percentile(ious, [25, 50, 75]).round(2))
pick = pairs[:12]
sheet = Image.new("RGB", (len(pick) * 150, 300), (15, 15, 15)); d = ImageDraw.Draw(sheet)
for i, (s, p) in enumerate(pick):
    for j, n in enumerate((s, p)):
        im = Image.open(G / f"{n}.DDS").convert("RGBA"); bg = Image.new("RGBA", im.size, (15, 15, 15, 255)); bg.alpha_composite(im)
        sheet.paste(bg.convert("RGB"), (i * 150, j * 150))
sheet.save(OUT / "pairs.png"); print("wrote pairs.png")
