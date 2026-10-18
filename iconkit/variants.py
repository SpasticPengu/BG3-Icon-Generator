"""Phase 3 variant exporter, no model: line art -> master -> controller 144, tooltip 380 (bottom fade), hotbar 64 (3.1)
-> DXT5 .DDS (3.2) -> mod files (3.3).
Line art (what the model will draw, D25 + D18) = RGBA float (512,512,4): grey level in RGB (grammar.detint in the colour it
was drawn in), alpha = the lines' share x the master's alpha (glyph.split AL x a). The master grows the colour's glow from
the lines (glyph.glow, data/glyph.json, blurs x4 at 512), puts the lines over it and tints both at once (grammar.tint, D18).
Two-colour icons (D26): each stroke set is painted alone in its colour; every pixel takes the part of its nearest line.
Mod layout (export): hotbar cells in one atlas under Public/<Mod> (map .lsx + TextureBank, the bg3-icons skill); tooltip and
controller art as NEW textures in the mod's own Mods/<Mod>/GUI/Assets (+ AssetsLowRes) + GUI metadata: Larian's Toolkit
guide (docs.baldursgate3.game "Adding Skill and Item Icons"), Patch 8's GustavX and 5eSpells ship them so; deploys loose,
unlike Public/Game, which only matters for replacing vanilla textures (plan D37).
    python -m iconkit.variants check           -> self-check on drawn rings, DDS mip chain, mod files
    python -m iconkit.variants test [names]    -> vanilla lines only -> master + variants vs the game's (test icons +
                                                  metamagic) and sheet data/variants.png
    python -m iconkit.variants png ICON [SIZE ...] [--out DIR]   -> PNGs at any size (default outputs/png, 512)"""
import io, json, struct, sys, uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import quoteattr
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from .extract import D, TWO_TONE, resize, rgba, log
from .fade import bottom_fade
from .glyph import GS, split, glow, master as load_master, part_presets, seen_err
from .grammar import Q, DARK, detint, tint, seen_de
from .dxt import encode
from . import hotbar, paths as P


def recipe(J, kd, p):
    """glow recipe of a kind (Spell / Action / Illithid) in preset p: its own, the one it borrows, else the kind's"""
    k = f"{kd}|{p}"
    return J["glow"].get(k) or J["glow"].get(J["borrow"].get(k, ""), J["glow"][kd])


def line_art(x, p, side=None, p2=None):
    """vanilla master (512,512,4) float -> line art; side (512,512) bool = pixels de-tinted with p2 (two-colour)"""
    ic = split(x, x.shape[0])
    g = detint(x, p) if side is None else np.where(side, detint(x, p2), detint(x, p))
    return np.dstack([g, g, g, ic["AL"] * ic["a"]])


EDGE_FADE = 12.0     # px at 512: the glow fades to nothing over this band at the image edge (app/glow.js EDGE: keep equal).
# User: no sharp cut, but close to the edge (24 px started too far in). The game fades its own glow there too (Aura of
# Protection: alpha .01 / .07 / .16 at 0 / 4 / 8 px; 12 px on the user's drawing: 0 / .12 / .37). Hold-out rebuilds: median seen
# L* vs the game 2.44 -> 2.465 (worst icon +0.16)


def edge_window(n, f=None):
    """(n, n) glow weight: smoothstep of the distance to the nearest left / right and top / bottom edge over the fade band
    (product of the two axes), 1 inside. User 7.0g: the glow must never be cut sharply by the image edge."""
    f = (EDGE_FADE if f is None else f) * n / 512
    if f <= 0:
        return np.ones((n, n))
    d = np.minimum(np.arange(n), np.arange(n)[::-1]) + .5
    t = np.clip(d / f, 0, 1)
    s = t * t * (3 - 2 * t)
    return s[:, None] * s[None, :]


def paint(la, p, th):
    """line art in one colour -> master RGBA float: glow grown from the lines, faded out at the image edge
    (edge_window), lines over it, tinted at the final alpha"""
    al = la[..., 3]
    EL = np.interp(la[..., 0], Q, p["lq"]) / 100 * al
    n = la.shape[0]
    if n > 512:       # hi-res PNGs: the glow is a wide blur, so grown at 512 and enlarged it matches growing it at n (2048 px:
        # 0.003 L* mean, 0.2 max over the hotbar dark) at a fraction of the cost (the whole paint 9-12 s -> 4 s at 2048)
        F = lambda z, s, how: np.asarray(Image.fromarray(z.astype(np.float32), "F").resize((s, s), how)).astype(np.float64)
        Eg, ag = glow({"AL": F(al, 512, Image.BOX), "EL": F(EL, 512, Image.BOX)}, th, scale=512 / GS)
        ag = F(ag, n, Image.BICUBIC).clip(0, 1)
        Eg = np.minimum(F(Eg, n, Image.BICUBIC).clip(0, 1), ag)
    else:
        Eg, ag = glow({"AL": al, "EL": EL}, th, scale=n / GS)
    w = edge_window(n)
    Eg, ag = Eg * w, ag * w
    E, A = EL + (1 - al) * Eg, al + (1 - al) * ag
    return tint(np.interp(100 * E / np.maximum(A, 1e-4), p["lq"], Q), A, p)


def master(la, p, th, second=None):
    """line art -> master RGBA float. second = (strokes (H,W) bool, preset, recipe): those strokes in the second colour"""
    if not second:
        return paint(la, p, th)
    strokes, p2, th2 = second
    _, (iy, ix) = ndimage.distance_transform_edt(la[..., 3] <= .1, return_indices=True)
    near = strokes[iy, ix]                                            # every pixel -> the part of its nearest line
    part = lambda w: np.dstack([la[..., :3], la[..., 3] * w])
    return np.where(near[..., None], paint(part(near), p2, th2), paint(part(~near), p, th))


def u8(x):
    return (np.clip(x, 0, 1) * 255 + .5).astype(np.uint8)


def sized(m, size, fade=False):
    """master RGBA float -> transparent PIL image at any size (premultiplied Lanczos; above 512 it only interpolates: the
    master, and the model, are 512); fade = the tooltip's bottom fade (D13, a function of the row share, any size)"""
    im = resize(Image.fromarray(u8(m), "RGBA"), size)
    if not fade:
        return im
    t = np.asarray(im).astype(np.float32) / 255
    t[..., 3] *= bottom_fade(size)
    return Image.fromarray(u8(t), "RGBA")


def variants(m, who, preset, H=None, B=None, second=None, bg=None):
    """master RGBA float -> {"controller": 144 RGBA (PC colours, D15), "tooltip": 380 RGBA (bottom fade, D13), "hotbar":
    64 RGB (hotbar.compose: frame by family + preset, D19, or bg = a frame entry, the app's Frame field; second = the
    second colour's preset, D26)} PIL images"""
    return {"controller": sized(m, 144), "tooltip": sized(m, 380, fade=True),
            "hotbar": Image.fromarray(u8(hotbar.compose(u8(m), who, preset, H, B, bg, second=second)))}


def pngs(m, who, preset, out, name, sizes=(512,), H=None, B=None, second=None, bg=None):
    """master -> PNGs in out: <name>_<size>.png (transparent art) and <name>_<size>_tooltip.png (bottom fade) per size, plus
    <name>_hotbar_64.png (the PC recipe is fitted at 64 px, D24: other sizes would only resample it). -> paths"""
    out, ps = Path(out), []
    out.mkdir(parents=True, exist_ok=True)
    for s in sizes:
        for fade, tag in ((False, ""), (True, "_tooltip")):
            ps.append(out / f"{name}_{s}{tag}.png")
            sized(m, s, fade).save(ps[-1])
    ps.append(out / f"{name}_hotbar_64.png")
    variants(m, who, preset, H, B, second, bg)["hotbar"].save(ps[-1])
    return ps


# ---------------------------------------------------------------- 3.2 DDS
def blocks(im):
    """PIL image -> its DXT5 blocks (dxt.encode: Pillow's encoder shifts line colours on hotbar cells)"""
    return encode(np.asarray(im.convert("RGBA")))


def dds(im, path=None, mips=False):
    """PIL image -> DXT5 .DDS bytes with the vanilla header (flags 0xA1007, mip count >= 1); mips = full chain to 1 px by
    box filter (the atlas: vanilla Icons_Skills 2048 has 12). Written to path when given."""
    im = im.convert("RGBA")
    lv = [im]
    while mips and max(lv[-1].size) > 1:
        lv.append(lv[-1].resize((max(1, lv[-1].width // 2), max(1, lv[-1].height // 2)), Image.BOX))
    w, h = im.size
    head = struct.pack("<4s7I44x2I4s20x5I", b"DDS ", 124, 0xA1007, h, w, max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * 16, 0,
                       len(lv), 32, 0x4, b"DXT5", 0x401008 if len(lv) > 1 else 0x1000, 0, 0, 0, 0)
    out = head + b"".join(blocks(z) for z in lv)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(out)
    return out


def dds_levels(data):
    """DXT5 .DDS bytes -> its mip levels as PIL images (for checks)"""
    f = struct.unpack_from("<7I", data, 4)
    h, w, n, o, out = f[2], f[3], max(1, f[6]), 128, []
    for _ in range(n):
        size = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * 16
        one = struct.pack("<4s7I44x2I4s20x5I", b"DDS ", 124, 0x81007, h, w, size, 0, 0, 32, 0x4, b"DXT5", 0x1000, 0, 0, 0, 0)
        out.append(Image.open(io.BytesIO(one + data[o:o + size])).convert("RGBA"))
        o, w, h = o + size, max(1, w // 2), max(1, h // 2)
    assert o == len(data), f"DDS length {len(data)} != header + levels {o}"
    return out


# ---------------------------------------------------------------- 3.3 mod files
XML_V = '<version major="4" minor="7" revision="1" build="3" lslib_meta="v1,bswap_guids,lsf_keys_adjacency" />'  # as ASL (in-game verified)
TIP, CTRL = "Tooltips/Icons", "ControllerUIIcons/skills_png"


def attr(i, t, v, ind):
    return f'{chr(9) * ind}<attribute id="{i}" type="{t}" value={quoteattr(str(v))} />'


def save(path, regions):
    """regions: [(region id, root node id, [xml lines at depth 3])] -> LSX file (UTF-8, tabs, as LSLib writes)"""
    body = "".join(f'\t<region id="{r}">\n\t\t<node id="{n}">\n{chr(10).join(ls)}\n\t\t</node>\n\t</region>\n' for r, n, ls in regions)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<save>\n\t{XML_V}\n{body}</save>\n', encoding="utf-8")
    ET.parse(path)                                                   # well-formed


def export(icons, mod, out):
    """{icon name: variants()} -> mod files under out (merge into the mod's own folders; names as the stats' data "Icon",
    e.g. <MOD>_Spell_<Name>). Hotbar: one square atlas, power of two (64 px cells, at most 32 x 32), full mips, map + one
    TextureBank Resource with the atlas map's UUID (uuid5 of the mod: a re-export keeps it; fields as vanilla Icons_Skills).
    Tooltip 380 / controller 144: GUI textures + metadata entries (MapKey Assets/<path>.png, w, h, mipcount), plus the
    half-size AssetsLowRes copies (190 / 72) that every vanilla icon and the Toolkit's UI asset converter have, listed in
    no metadata (Patch 8's GustavX metadata lists only Assets/). -> list of files written"""
    out, names = Path(out), sorted(icons)
    n = 1
    while n * n < len(names):
        n *= 2
    assert n <= 32, "more than 1,024 icons: split them over several atlases"
    sheet = Image.new("RGBA", (64 * n, 64 * n), (0, 0, 0, 0))
    uvs = []
    for i, k in enumerate(names):
        r, c = divmod(i, n)
        sheet.paste(icons[k]["hotbar"].convert("RGBA"), (64 * c, 64 * r))
        uvs += ["\t\t\t\t<node id=\"IconUV\">", attr("MapKey", "FixedString", k, 5)] + [
            attr(a, "float", repr(v / n), 5) for a, v in (("U1", c), ("U2", c + 1), ("V1", r), ("V2", r + 1))] + ["\t\t\t\t</node>"]
    uid, atlas = str(uuid.uuid5(uuid.NAMESPACE_URL, f"bg3-icon-generator/{mod}/atlas")), f"Icons_{mod}"
    pub = out / "Public" / mod
    files = [pub / f"Assets/Textures/Icons/{atlas}.DDS", pub / f"GUI/{atlas}.lsx", pub / "Content/UI/[PAK]_UI/_merged.lsf.lsx"]
    dds(sheet, files[0], mips=True)
    node = lambda nid, *a: [f"\t\t\t\t<node id=\"{nid}\">", *a, "\t\t\t\t</node>"]
    save(files[1], [("TextureAtlasInfo", "root", ["\t\t\t<children>",
         *node("TextureAtlasIconSize", attr("Height", "int32", 64, 5), attr("Width", "int32", 64, 5)),
         *node("TextureAtlasPath", attr("Path", "string", f"Assets/Textures/Icons/{atlas}.DDS", 5), attr("UUID", "FixedString", uid, 5)),
         *node("TextureAtlasTextureSize", attr("Height", "int32", 64 * n, 5), attr("Width", "int32", 64 * n, 5)), "\t\t\t</children>"]),
                    ("IconUVList", "root", ["\t\t\t<children>", *uvs, "\t\t\t</children>"])])
    save(files[2], [("TextureBank", "TextureBank", ["\t\t\t<children>", *node("Resource",
         attr("ID", "FixedString", uid, 5), attr("Localized", "bool", "False", 5), attr("Name", "LSString", atlas, 5),
         attr("SRGB", "bool", "True", 5), attr("SourceFile", "LSString", f"Public/{mod}/Assets/Textures/Icons/{atlas}.DDS", 5),
         attr("Streaming", "bool", "True", 5), attr("Template", "FixedString", "Icons_Items", 5), attr("Type", "int64", 0, 5),
         attr("_OriginalFileVersion_", "int64", 144115188075855912, 5)), "\t\t\t</children>"])])
    gui, meta = out / "Mods" / mod / "GUI", []
    for k in names:
        for sub, tier in ((TIP, "tooltip"), (CTRL, "controller")):
            im = icons[k][tier]
            files += [gui / f"Assets/{sub}/{k}.DDS", gui / f"AssetsLowRes/{sub}/{k}.DDS"]       # low res: half, not in metadata
            dds(im, files[-2])
            dds(resize(im, im.width // 2), files[-1])
            meta += ["\t\t\t\t\t\t<node id=\"Object\">", attr("MapKey", "FixedString", f"Assets/{sub}/{k}.png", 7),
                     "\t\t\t\t\t\t\t<children>", "\t\t\t\t\t\t\t\t<node id=\"entries\">",
                     attr("h", "int16", im.height, 9), attr("mipcount", "int8", 1, 9), attr("w", "int16", im.width, 9),
                     "\t\t\t\t\t\t\t\t</node>", "\t\t\t\t\t\t\t</children>", "\t\t\t\t\t\t</node>"]
    files.append(gui / "metadata.lsf.lsx")
    save(files[-1], [("config", "config", ["\t\t\t<children>", "\t\t\t\t<node id=\"entries\">", "\t\t\t\t\t<children>", *meta,
                                            "\t\t\t\t\t</children>", "\t\t\t\t</node>", "\t\t\t</children>"])])
    return files


def tier_err(ours, game):
    """mean |d| /255 over alpha and premultiplied RGB (extract.master_errors' measure)"""
    o, g = (np.asarray(v.convert("RGBA")).astype(np.float32) / 255 if isinstance(v, Image.Image) else v for v in (ours, game))
    pm = lambda z: np.dstack([z[..., :3] * z[..., 3:], z[..., 3:]])
    return float(np.abs(pm(o) - pm(g)).mean() * 255)


def build(n, J, G):
    """vanilla icon -> (line art, its master rebuilt, preset name, second preset name or None)"""
    PR = {p["name"]: p for p in G["presets"]}
    x, kd = load_master(n), J["icons"][n]["kind"]
    if n in TWO_TONE:
        side, ((_, i1, _), (s2, i2, _)) = part_presets(x, G["presets"])
        p, p2 = G["presets"][i1], G["presets"][i2]
        strokes = np.repeat(np.repeat(side == s2, 2, 0), 2, 1)
        la = line_art(x, p, strokes, p2)
        return x, la, master(la, p, recipe(J, kd, p["name"]), (strokes, p2, recipe(J, kd, p2["name"]))), p["name"], p2["name"]
    p = PR[J["icons"][n]["preset"]]
    la = line_art(x, p)
    return x, la, master(la, p, recipe(J, kd, p["name"])), p["name"], None


def test(names=None):
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    H = json.loads((D / "hotbar.json").read_text(encoding="utf-8"))
    B, cells = hotbar.backgrounds(), hotbar.atlas()
    I = J["icons"]
    names = names or sorted(n for n, v in I.items() if v["split"] == "holdout" and v["preset"]) + [n for n in TWO_TONE if n in I]
    rows, strip = [], []
    for i, n in enumerate(names):
        x, la, m, p, p2 = build(n, J, G)
        ic = split(x)
        sm = split(m)
        game_t, game_c = rgba(P.tooltip(n)), rgba(P.controller(n))
        r = {"icon": n, "kind": I[n]["kind"], "seen_L": seen_err(ic, sm["B"], sm["a"]), "seen_de": seen_de(x, m)[0]}
        for who, mm in (("vanilla", x), ("ours", m)):
            v = variants(mm, n, p, H, B, p2)
            r[f"ctrl_{who}"], r[f"tip_{who}"] = tier_err(v["controller"], game_c), tier_err(v["tooltip"], game_t)
            if n in cells:
                r[f"hot_{who}"] = float(np.abs(np.asarray(v["hotbar"]) / 255 - cells[n]).mean() * 255)
            if who == "ours" and (i % max(1, len(names) // 10) == 0 or n in TWO_TONE[:2]):     # a spread + 2 metamagic
                over = lambda z: Image.fromarray(u8(z[..., :3] * z[..., 3:] + DARK * (1 - z[..., 3:]))).resize((128, 128), Image.LANCZOS)
                strip.append([over(x), over(la), over(m), over(np.asarray(v["tooltip"]) / 255),
                              v["hotbar"].resize((128, 128), Image.NEAREST),
                              Image.fromarray(u8(cells[n])).resize((128, 128), Image.NEAREST) if n in cells else Image.new("RGB", (128, 128))])
        rows.append(r)
        if i % 20 == 0:
            log(f"    {i}/{len(names)} {n}: seen L* {r['seen_L']:.2f}, dE2000 {r['seen_de']:.2f}")
    med = lambda k, rs: round(float(np.median([r[k] for r in rs if k in r])), 2) if any(k in r for r in rs) else None
    for kd in ("Spell", "Action", "Illithid", "two-colour"):
        rs = [r for r in rows if (r["icon"] in TWO_TONE if kd == "two-colour" else r["kind"] == kd and r["icon"] not in TWO_TONE)]
        if rs:
            log(f"[3.1] {kd} ({len(rs)}): master from lines vs game master over the hotbar dark: L* {med('seen_L', rs)}, "
                f"dE2000 {med('seen_de', rs)}; vs game files /255 (from vanilla master -> from lines): controller "
                f"{med('ctrl_vanilla', rs)} -> {med('ctrl_ours', rs)}, tooltip {med('tip_vanilla', rs)} -> {med('tip_ours', rs)}, "
                f"hotbar {med('hot_vanilla', rs)} -> {med('hot_ours', rs)}")
    sheet = Image.new("RGB", (6 * 132, len(strip) * 132), (40, 40, 40))
    for j, ims in enumerate(strip):
        for k, im in enumerate(ims):
            sheet.paste(im, (k * 132, j * 132))
    sheet.save(D / "variants.png")
    (D / "variants.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    log(f"[3.1] wrote {D / 'variants.json'} and sheet {D / 'variants.png'} (game master | line art | ours | our tooltip | "
        f"our hotbar | game hotbar)")


def check():
    """drawn rings: lines keep their lightness, the glow grows next to them only, variants have the game's sizes and the
    tooltip fades at the bottom, a second colour lands on its own strokes"""
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    PR = {p["name"]: p for p in G["presets"]}
    p, p2 = PR["Fire orange"], PR["Cold blue"]
    im = Image.new("L", (512, 512), 0)
    ImageDraw.Draw(im).ellipse((96, 96, 416, 416), outline=255, width=24)
    ImageDraw.Draw(im).ellipse((200, 200, 312, 312), outline=255, width=24)
    a = np.asarray(im) / 255
    la = np.dstack([np.full((512, 512, 3), .8), a])
    m = paint(la, p, recipe(J, "Spell", "Fire orange"))
    from skimage.color import rgb2lab
    L = rgb2lab(m[..., :3])[..., 0]
    assert abs(L[256, 108] - np.interp(.8, Q, p["lq"])) < 3, f"line lightness kept: {L[256, 108]:.1f}"
    assert m[256, 80, 3] > .05 and m[5, 5, 3] < .01, "glow next to the lines, none far"
    side = np.zeros((512, 512)); side[100:412, 12:24] = 1                 # a line 12 px from the left edge
    e = paint(np.dstack([np.full((512, 512, 3), .8), side]), p, recipe(J, "Spell", "Fire orange"))[256, :, 3]
    assert e[0] < .01 < e[4] < e[8] < e[11] and e[40] > .05, f"the glow fades out at the image edge, no cut: {e[[0, 4, 8, 11, 40]].round(2)}"
    two = master(la, p, recipe(J, "Spell", "Fire orange"), (np.hypot(*np.mgrid[:512, :512] - 255.5) < 90, p2, recipe(J, "Spell", "Cold blue")))
    lab = lambda y, x: rgb2lab(two[y, x, :3])
    assert lab(256, 108)[2] > 20 and lab(256, 212)[2] < -10, f"outer ring orange, inner ring blue: {lab(256, 108)}, {lab(256, 212)}"
    v = variants(m, "Spell_Test", "Fire orange")
    assert v["controller"].size == (144, 144) and v["tooltip"].size == (380, 380) and v["hotbar"].size == (64, 64)
    big, small = sized(m, 1024), np.asarray(sized(m, 100, fade=True))[..., 3]
    assert big.size == (1024, 1024) and small.shape == (100, 100) and small[79, 50] < .5 * small[21, 50], "any size, fade scales"
    ta = np.asarray(v["tooltip"])[..., 3]
    assert ta[80, 190] > 200 and ta[300, 190] < .5 * ta[80, 190], f"tooltip fades towards the bottom: {ta[80, 190]} {ta[300, 190]}"
    lv = dds_levels(dds(Image.fromarray(u8(m)).resize((256, 256), Image.LANCZOS), mips=True))
    assert [z.width for z in lv] == [256, 128, 64, 32, 16, 8, 4, 2, 1], "full mip chain"
    ref = Image.fromarray(u8(m)).resize((256, 256), Image.LANCZOS).resize((64, 64), Image.BOX)
    err = tier_err(lv[2], ref)
    assert err < 3, f"mip 2 decodes to the image at a quarter size: premultiplied mean |d| {err:.1f} /255"
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        fs = export({"T_Spell_A": v, "T_Spell_B": v, "T_Spell_C": v}, "TestMod", tmp)
        mp, bank, meta = (ET.parse(f).getroot() for f in (fs[1], fs[2], fs[-1]))
        uid = lambda r, a: r.find(f".//attribute[@id='{a}']").get("value")
        assert uid(mp, "UUID") == uid(bank, "ID"), "TextureBank Resource ID = atlas map UUID"
        assert uid(bank, "SourceFile") == "Public/TestMod/Assets/Textures/Icons/Icons_TestMod.DDS" and fs[0].exists()
        assert dds_levels(fs[0].read_bytes())[0].size == (128, 128), "3 icons -> a 2 x 2 atlas"
        uv = {o.find("attribute[@id='MapKey']").get("value"): [float(o.find(f"attribute[@id='{a}']").get("value"))
              for a in ("U1", "U2", "V1", "V2")] for o in mp.iter("node") if o.get("id") == "IconUV"}
        assert uv["T_Spell_C"] == [0, .5, .5, 1], f"third icon in row 2: {uv}"
        keys = [o.get("value") for o in meta.iter("attribute") if o.get("id") == "MapKey"]
        assert len(keys) == 6 and "Assets/Tooltips/Icons/T_Spell_A.png" in keys and all((Path(tmp) / "Mods/TestMod/GUI" / k.replace(".png", ".DDS")).exists() for k in keys)
        low = Path(tmp) / "Mods/TestMod/GUI/AssetsLowRes"
        assert [dds_levels((low / s / "T_Spell_B.DDS").read_bytes())[0].width for s in (TIP, CTRL)] == [190, 72], "low res = half"
    log("[3.1-3.3] check passed: lines kept, glow next to them, two colours by stroke, variant sizes, bottom fade, DDS mip "
        "chain, atlas map + TextureBank + GUI metadata")


def png_cli(args):
    """png ICON [SIZE ...] [--out DIR]: a vanilla icon rebuilt from its lines only (until the model draws them) -> PNGs"""
    out = Path(args[args.index("--out") + 1]) if "--out" in args else D.parent / "outputs" / "png"
    args = args[:args.index("--out")] if "--out" in args else args
    J, G, H = (json.loads((D / f).read_text(encoding="utf-8")) for f in ("glyph.json", "grammar.json", "hotbar.json"))
    _, _, m, p, p2 = build(args[0], J, G)
    for f in pngs(m, args[0], p, out, args[0], [int(s) for s in args[1:]] or (512,), H, None, p2):
        log(f"    {f}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    {"check": check, "test": lambda: test(sys.argv[2:] or None), "png": lambda: png_cli(sys.argv[2:])}[cmd]()
