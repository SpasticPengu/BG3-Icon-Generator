"""every training icon whose motif names a figure / silhouette / body / humanoid / man / woman: line art over black,
numbered, -> OUTDIR/figures_N.png (100 per sheet) + figures.txt (D43 evidence; any python with Pillow)
    python research/probes/figure_sheet.py OUTDIR"""
import json, re, sys
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
RX = r"\b(figure|humanoid|person|man|woman|body|silhouette)s?\b"
M = {json.loads(l)["icon"]: json.loads(l)["motif"] for l in (ROOT / "iconkit/motifs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
files = {p.stem: p for p in (ROOT / "outputs/trainset_all").glob("r*/*.png")}
names = sorted(n for n in files if n in M and re.search(RX, M[n].lower()))
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
s, cols = 120, 10
for part in range(0, len(names), 100):
    chunk = names[part:part + 100]
    im = Image.new("RGB", (cols * s, -(-len(chunk) // cols) * s), (0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, n in enumerate(chunk):
        x, y = (i % cols) * s, (i // cols) * s
        im.paste(Image.open(files[n]).convert("RGB").resize((s - 4, s - 4), Image.LANCZOS), (x + 2, y + 2))
        d.text((x + 3, y + 2), str(part + i), fill=(255, 80, 80))
    im.save(out / f"figures_{part // 100}.png")
(out / "figures.txt").write_text("\n".join(f"{i} {n} | {M[n]}" for i, n in enumerate(names)), encoding="utf-8")
print(len(names), "figure icons")
