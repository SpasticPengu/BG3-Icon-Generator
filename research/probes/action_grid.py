"""Grid of hotbar atlas crops for a prefix, labelled with stats + guessed bg. Visual check of bg rules."""
import csv, re, sys, random
from pathlib import Path
from PIL import Image, ImageDraw

U = (Path.home() / r"Documents\BG3 Modding\BG3 Modders Multitool\UnpackedData")
OUT = Path(sys.argv[1]); prefix = sys.argv[2]; n = int(sys.argv[3])
rows = [r for r in csv.DictReader(open(OUT / "icons.csv", encoding="utf-8")) if r["prefix"] == prefix and r["in_atlas"] == "True"]
random.seed(1); rows = random.sample(rows, min(n, len(rows)))
maps = {}
for lsx in [U / "GUI/Public/Shared/GUI/Icons_Skills.lsx", U / "GUI/Public/SharedDev/GUI/Icons_Skills.lsx"]:
    t = lsx.read_text(encoding="utf-8")
    dds = U / "Icons" / lsx.parent.parent.relative_to(U / "GUI") / re.search(r'id="Path" type="string" value="([^"]+)"', t).group(1)
    for m in re.finditer(r'MapKey" type="FixedString" value="([^"]+)"/>\s*<attribute id="U1" type="float" value="([^"]+)"/>\s*<attribute id="U2" type="float" value="([^"]+)"/>\s*<attribute id="V1" type="float" value="([^"]+)"/>\s*<attribute id="V2" type="float" value="([^"]+)"', t):
        maps.setdefault(m.group(1), (dds, *map(float, m.groups()[1:])))
atl = {}
C, cols = 128, 8
sheet = Image.new("RGB", (cols * (C + 8), ((len(rows) + cols - 1) // cols) * (C + 40)), (25, 25, 25))
d = ImageDraw.Draw(sheet)
for i, r in enumerate(rows):
    dds, u1, u2, v1, v2 = maps[r["icon"]]
    if dds not in atl: atl[dds] = Image.open(dds).convert("RGB")
    A = atl[dds]
    im = A.crop((round(u1 * A.width), round(v1 * A.height), round(u2 * A.width), round(v2 * A.height))).resize((C, C), Image.LANCZOS)
    x, y = (i % cols) * (C + 8), (i // cols) * (C + 40)
    sheet.paste(im, (x, y))
    d.text((x + 2, y + C + 1), r["icon"].replace(prefix + "_", "")[:22], fill=(255, 255, 255))
    d.text((x + 2, y + C + 13), f"{r['VerbalIntent'][:7]} {r['cost'][:6]} {r['DamageType'][:6]}", fill=(255, 220, 0))
    d.text((x + 2, y + C + 25), f"bg?{r['bg'][:14]} {r['hue_name']}", fill=(120, 200, 255))
sheet.save(OUT / f"grid_{prefix}.png"); print("wrote", OUT / f"grid_{prefix}.png", len(rows))
