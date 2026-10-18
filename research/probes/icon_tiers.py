"""Compare BG3 icon tiers for sample spells: hotbar atlas crop, controller 144, tooltip 380.
Prints DDS header formats + alpha statistics, writes contact sheets to the scratchpad."""
import struct, sys, re, os
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

U = (Path.home() / r"Documents\BG3 Modding\BG3 Modders Multitool\UnpackedData")
G = U / "GUI/Public/Game/GUI/Assets"
OUT = Path(sys.argv[1])
NAMES = sys.argv[2].split(",")

DXGI = {71: "BC1", 74: "BC2", 77: "BC3", 80: "BC4", 83: "BC5", 95: "BC6H", 98: "BC7", 28: "RGBA8", 87: "BGRA8"}

def dds_info(p):
    b = open(p, "rb").read(148)
    h, w, mips = struct.unpack_from("<I", b, 12)[0], struct.unpack_from("<I", b, 16)[0], struct.unpack_from("<I", b, 28)[0]
    fourcc = b[84:88].decode("latin1")
    fmt = fourcc
    if fourcc == "DX10":
        fmt = DXGI.get(struct.unpack_from("<I", b, 128)[0], f"dxgi{struct.unpack_from('<I', b, 128)[0]}")
    elif fourcc == "DXT5":
        fmt = "BC3(DXT5)"
    elif fourcc == "DXT1":
        fmt = "BC1(DXT1)"
    return f"{w}x{h} {fmt} mips={mips}"

def load(p):
    return Image.open(p).convert("RGBA")

def atlas_maps():
    maps = {}
    for lsx in [U / "GUI/Public/Shared/GUI/Icons_Skills.lsx", U / "GUI/Public/SharedDev/GUI/Icons_Skills.lsx"]:
        t = lsx.read_text(encoding="utf-8")
        path = re.search(r'id="Path" type="string" value="([^"]+)"', t).group(1)
        dds = U / "Icons" / lsx.parent.parent.relative_to(U / "GUI") / path
        for m in re.finditer(r'MapKey" type="FixedString" value="([^"]+)"/>\s*<attribute id="U1" type="float" value="([^"]+)"/>\s*<attribute id="U2" type="float" value="([^"]+)"/>\s*<attribute id="V1" type="float" value="([^"]+)"/>\s*<attribute id="V2" type="float" value="([^"]+)"', t):
            maps.setdefault(m.group(1), (dds, *map(float, m.groups()[1:])))
    return maps

def checker(w, h, s=8):
    im = Image.new("RGBA", (w, h), (90, 90, 90, 255))
    d = ImageDraw.Draw(im)
    for y in range(0, h, s):
        for x in range(0, w, s):
            if (x // s + y // s) % 2:
                d.rectangle([x, y, x + s - 1, y + s - 1], fill=(140, 140, 140, 255))
    return im

def on_checker(im):
    bg = checker(*im.size)
    bg.alpha_composite(im)
    return bg

def alpha_profile(im, bands=8):
    a = np.asarray(im)[:, :, 3].astype(float) / 255
    hgt = a.shape[0]
    return " ".join(f"{a[i*hgt//bands:(i+1)*hgt//bands].mean():.2f}" for i in range(bands))

maps = atlas_maps()
atlases = {}
print(f"atlas keys: {len(maps)}")
for p in sorted({v[0] for v in maps.values()}):
    print("atlas", p.relative_to(U), dds_info(p))

CELL = 380
sheet = Image.new("RGBA", (CELL * 4 + 50, (CELL + 30) * len(NAMES)), (30, 30, 30, 255))
dr = ImageDraw.Draw(sheet)
for i, n in enumerate(NAMES):
    y = i * (CELL + 30)
    tip, ctl = G / "Tooltips/Icons" / f"{n}.DDS", G / "ControllerUIIcons/skills_png" / f"{n}.DDS"
    row = []
    if n in maps:
        dds, u1, u2, v1, v2 = maps[n]
        if dds not in atlases:
            atlases[dds] = load(dds)
        A = atlases[dds]
        box = (round(u1 * A.width), round(v1 * A.height), round(u2 * A.width), round(v2 * A.height))
        hb = A.crop(box)
        row.append(("hotbar " + f"{hb.width}px", hb))
        print(f"{n}: hotbar {hb.size} alpha bands: {alpha_profile(hb)}")
    for label, p in (("controller", ctl), ("tooltip", tip)):
        if p.exists():
            im = load(p)
            row.append((f"{label} {dds_info(p)}", im))
            print(f"{n}: {label} {dds_info(p)} alpha bands(top->bottom): {alpha_profile(im)}")
    # tooltip vs controller: same art? compare tooltip downscaled to 144 with controller (RGB where both opaque)
    if tip.exists() and ctl.exists():
        t = np.asarray(load(tip).resize((144, 144), Image.LANCZOS)).astype(float)
        c = np.asarray(load(ctl)).astype(float)
        m = (t[:, :, 3] > 200) & (c[:, :, 3] > 200)
        diff = np.abs(t[:, :, :3] - c[:, :, :3])[m].mean() if m.any() else -1
        print(f"{n}: tooltip(->144) vs controller mean RGB diff on co-opaque px = {diff:.1f}; co-opaque px={m.sum()}")
    x = 0
    for label, im in row:
        disp = im.resize((CELL, CELL), Image.NEAREST if im.width <= 64 else Image.LANCZOS) if im.width != CELL else im
        sheet.alpha_composite(on_checker(disp), (x, y + 25))
        dr.text((x + 4, y + 6), f"{n} | {label}", fill=(255, 255, 0, 255))
        x += CELL + 10
    # alpha channel of tooltip as grayscale
    if tip.exists():
        a = load(tip).getchannel("A").convert("RGBA")
        sheet.alpha_composite(a, (x, y + 25))
        dr.text((x + 4, y + 6), "tooltip alpha", fill=(255, 255, 0, 255))
sheet.save(OUT / "tiers.png")

# backgrounds grid
bgd = G / "ControllerUIIcons/icon_bg_png"
bgs = sorted(bgd.glob("*.DDS"))
print("backgrounds:", dds_info(bgs[0]))
cols = 7
gs = Image.new("RGBA", (cols * 160, ((len(bgs) + cols - 1) // cols) * 175), (30, 30, 30, 255))
d2 = ImageDraw.Draw(gs)
for k, p in enumerate(bgs):
    im = load(p)
    arr = np.asarray(im).astype(float)
    cx = arr[60:84, 60:84, :3].mean(axis=(0, 1))
    print(f"  {p.stem:40s} {dds_info(p)}  center RGB={cx.round().astype(int)} alpha min/max={arr[:,:,3].min():.0f}/{arr[:,:,3].max():.0f}")
    gx, gy = (k % cols) * 160, (k // cols) * 175
    gs.alpha_composite(on_checker(im), (gx + 8, gy + 25))
    d2.text((gx + 4, gy + 6), p.stem.replace("_bg", ""), fill=(255, 255, 0, 255))
gs.save(OUT / "backgrounds.png")
print("wrote", OUT / "tiers.png", OUT / "backgrounds.png")
