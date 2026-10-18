"""AI Toolkit samples -> one sheet: a row per saved step (step 0 = the base model, no LoRA), a column per sample prompt.
    python train/samples_sheet.py RUN_DIR OUT.png [SIZE]        (any python with Pillow; SIZE per tile, default 192)"""
import re, sys
from pathlib import Path
from PIL import Image, ImageDraw


def main(run, out, size=192):
    grid = {}
    for f in Path(run, "samples").glob("*.jpg"):
        m = re.match(r"\d+__(\d+)_(\d+)\.jpg$", f.name)
        if m:
            grid.setdefault(int(m[1]), {})[int(m[2])] = f
    steps, cols = sorted(grid), 1 + max(i for row in grid.values() for i in row)
    sheet = Image.new("RGB", (60 + cols * size, len(steps) * size), "#202020")
    d = ImageDraw.Draw(sheet)
    for r, s in enumerate(steps):
        d.text((6, r * size + size // 2), str(s), fill="white")
        for c, f in grid[s].items():
            sheet.paste(Image.open(f).convert("RGB").resize((size, size), Image.LANCZOS), (60 + c * size, r * size))
    sheet.save(out)
    print(f"{out}: steps {steps}, {cols} prompts")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(int(a) for a in sys.argv[3:4]))
