"""Count DDS size/format/mips per vanilla icon folder (header only, fast). Usage: dds_census.py"""
import struct
from collections import Counter
from pathlib import Path

G = (Path.home() / r"Documents\BG3 Modding\BG3 Modders Multitool\UnpackedData\GUI\Public\Game\GUI\Assets")
DXGI = {71: "BC1", 72: "BC1_SRGB", 77: "BC3", 78: "BC3_SRGB", 98: "BC7", 99: "BC7_SRGB"}
for sub in ["Tooltips/Icons", "ControllerUIIcons/skills_png", "ControllerUIIcons/icon_bg_png", "Tooltips/ItemIcons",
            "ControllerUIIcons/items_png", "ClassIcons"]:
    c = Counter()
    for p in (G / sub).rglob("*.DDS"):
        b = p.open("rb").read(148)
        h, w, mips, fcc = *struct.unpack_from("<III", b, 12)[:2], struct.unpack_from("<I", b, 28)[0], b[84:88].decode("latin1")
        fmt = DXGI.get(struct.unpack_from("<I", b, 128)[0], "dxgi?") if fcc == "DX10" else fcc
        c[f"{w}x{h} {fmt} mips={mips}"] += 1
    print(f"{sub}: " + "; ".join(f"{v} x {k}" for k, v in c.most_common()))
