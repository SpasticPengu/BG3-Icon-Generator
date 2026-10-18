"""Side-by-side check sheet: vanilla tooltip | vanilla controller | our master | master alpha, per icon.
    python -m iconkit.sheet OUT.png ICON [ICON ...]        ICON may be @list.txt (one icon per line)
    --cols N   icons per row (default 2)     --size PX   tile size (default 128)
Output holds Larian art: write it to the scratchpad or data/, never into git."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw
from . import paths as P
from .extract import D, checker, read_jsonl, log

COLS = ("tooltip", "controller", "master", "alpha")


def tile(path, size, alpha=False):
    if not path.exists():
        t = Image.new("RGBA", (size, size), (60, 20, 20, 255))
        ImageDraw.Draw(t).text((6, size // 2 - 6), "missing", fill=(255, 160, 160, 255))
        return t
    im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    if alpha:
        return im.getchannel("A").convert("RGBA")
    t = checker(size, max(4, size // 16))
    t.alpha_composite(im)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("icons", nargs="+")
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--size", type=int, default=128)
    a = ap.parse_args()
    icons = [l.strip() for x in a.icons for l in (Path(x[1:]).read_text(encoding="utf-8").splitlines() if x.startswith("@") else [x]) if l.strip()]
    by = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    s, gap, lab = a.size, 4, 34
    bw, bh = 4 * s + 3 * gap, s + lab
    W = a.cols * bw + (a.cols + 1) * 12
    H = 22 + -(-len(icons) // a.cols) * (bh + 12)
    sheet = Image.new("RGBA", (W, H), (20, 21, 24, 255))
    d = ImageDraw.Draw(sheet)
    d.text((12, 5), "   |   ".join(COLS) + "   (per icon, left to right)", fill=(150, 155, 165, 255))
    for i, n in enumerate(icons):
        x, y = 12 + (i % a.cols) * (bw + 12), 22 + (i // a.cols) * (bh + 12)
        r = by.get(n, {})
        d.text((x, y + 2), n[:4 * s // 6], fill=(255, 225, 120, 255))
        labels = " · ".join(v for v in (r.get("name", ""), r.get("VerbalIntent", ""), r.get("DamageType", "")) if v)
        d.text((x, y + 17), labels[:4 * s // 6] or "(not in meta.jsonl)", fill=(200, 200, 205, 255))
        paths = (P.tooltip(n), P.controller(n), D / "masters" / f"{n}.png", D / "masters" / f"{n}.png")
        for j, p in enumerate(paths):
            sheet.alpha_composite(tile(p, s, alpha=j == 3), (x + j * (s + gap), y + lab))
    sheet.save(a.out)
    log(f"[sheet] {a.out}: {len(icons)} icons, {a.cols} per row, {W}x{H}")


if __name__ == "__main__":
    main()
