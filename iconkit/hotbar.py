"""Phase 2.2 hotbar (64 px PC) recipe, fitted on the vanilla Icons_Skills atlas against our masters.
- Spells sit on `spell_bg`. Actions/skills sit on one of the controller framed backgrounds, darkened, chosen by the
  icon's colour preset (Summon amber -> summon, Weapon red -> weaponAction, ...): `frames` in data/hotbar.json. Frames
  are compared by colour as seen (CIEDE2000); colours no frame matches get a framed background hue-shifted to them.
- Glyph: master premultiplied, Lanczos to 64, soft glow thinned; behind it a dark halo shaped like the glyph's own glow,
  and inside the glyph's closed shapes a faint tint in its own colour (the game's interiors are lit, not dark); then the
  finished icon is sharpened darken-only around the glyph (crisp dark rim, line cores not brightened). Numbers per colour
  preset where it has enough icons.
    python -m iconkit.hotbar          -> data/hotbar.json + data/hotbar.png (hold-out check sheet: vanilla | ours | |diff|x3)
    python -m iconkit.hotbar report   -> data/hotbar.html (review page, needs hotbar.json; ~1 min)
compose(master, family, preset) is what Phase 3 calls."""
import json, re, sys
from collections import Counter, defaultdict
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, optimize
from .lab import rgb2lab, lab2rgb, deltaE_ciede2000
from . import paths as P
from .extract import D, ILLITHID_ART, TWO_TONE, read_jsonl, log

S = 64
MODE_SHARE = .12                       # a preset's alternative frames need this share of its training icons
# the backgrounds with a frame: the only ones an action sits on. The frameless ones (*Passive, tadpole) mean passives,
# conditions and illithid powers (user, 2026-10-14); spell = the spells' stone. A hue shift recolours these.
FRAMED = ("control", "utility", "summon", "buff", "heal", "radiance", "fireDamage", "monster", "lightening", "action",
          "weaponAction", "bonusAction", "weaponBonusAction", "metaMagic")
SHIFT_MIN = 2.0                        # a hue-shifted frame becomes a preset's default only if this much closer (median dE2000)
KEYS = ("bg_gain", "sharpen", "sharpen_px", "line_from", "halo", "halo_px", "halo_gamma", "glow_kept", "glow_kept_curve",
        "fill", "glow_thin", "cover", "light", "light_px", "light_edge", "light_add", "unsharp",
        "frame_light", "frame_light_px", "frame_light_add", "line_contrast", "line_sat", "line_lift", "glow_sat", "hue",
        "bloom", "bloom_px")
V4 = 11                                # v4 recipes stop after glow_thin; parts() pads them with NEUTRAL
NEUTRAL = [1., 0., 15., 0., 0., 0., 0., 15., 0., 1., 1., 0., 1., 0., 0., 6.]   # v5/v6 keys off: glow covers by its
                                                                 # opacity, no lights, no glyph unsharp, glyph colours as drawn, no bloom
padded = lambda x: list(x) + NEUTRAL[len(x) - V4:]   # a stored recipe with the keys it lacks switched off
# v5/v6 keys start small but non-zero: Nelder-Mead's first step from an exact 0 is 0.00025, so such a key never moves
V5_START = [1., .05, 20., -.02, .01, 0., .1, 20., .02, 1.05, .95, .01, 1.05, 1., .05, 6.]
# Powell line-search step per key (round 5): Nelder-Mead's first simplex steps are 5% of each start value, so keys that
# start small barely move (hue 1 deg -> 1.007, light .07 -> .08 in 300 iterations); Powell searches each key along a step
# of its own scale (Radiant gold: loss 38.0 -> 32.4 vs Nelder-Mead 33.5 at 300 evaluations, light .07 -> .55)
STEP = {"hue": 3., "light_px": 3., "frame_light_px": 3., "bloom_px": 2., "halo_px": .3, "sharpen_px": .2}
step_of = lambda k, v: STEP.get(k, max(.05, .2 * abs(v)))
MIN_BLOOM_PX = 1.5                     # the bloom's blur never narrower than this (px at 64)
START = {"spell": [.99, 1.05, .78, .93, .15, 1.58, .6, 1., 2.77, .13, .85] + V5_START,      # v4 fits 2026-10-14
         "action": [1.03, 1.34, .63, .47, 1.21, .73, .27, .32, .27, .29, .86] + V5_START}
START["illithid"] = START["action"]
LUMA = np.array([.2126, .7152, .0722])
DARK_FLOOR = .2                        # the darken-only sharpening never takes a pixel below this share of its brightness
UNSHARP_PX = 1.3                       # radius of the soft recipe's glyph unsharp mask (last page's: 1.46 actions, 1.08 spells)
R2 = (np.mgrid[:S, :S] - (S - 1) / 2) ** 2
R2 = R2[0] + R2[1]                     # squared distance from the icon's centre (px at 64), for the centre light
PLAIN = [1, 0, 1, .5, 0, 1, 1, 1, 1, 0, 1] + NEUTRAL   # plain alpha-over: no sharpening, halo, fill, thinning or light
# refit per colour preset (>= MIN_PRESET training icons of the kind): the game's dark edge differs by colour, e.g. 1 px
# outside the lines Summon amber -13 L*, Weapon red -1 (its red glow stays; user, 2026-10-14: "dark red glow too big")
# line colours too: the game's lines lose colourfulness very differently by colour (Summon amber chroma 31 -> 19, Weapon
# red 55 -> 38, Control rose 24 -> 11, Debuff magenta 40 -> 17; round 4)
# round 5: + the light's edge and the stone light (the game's centre light differs by colour: stone 0.3-0.55 half-widths
# from the centre, game - ours, Weapon red +12 L*, Summon amber +9, Control rose -4) and the glow colour keys (hue offsets
# differ by colour, e.g. Control rose +7 deg, Fire orange -5)
PER_PRESET = ("bg_gain", "sharpen", "halo", "halo_px", "glow_kept", "fill", "glow_thin", "cover", "light", "unsharp",
              "line_sat", "line_contrast", "light_edge", "frame_light", "glow_sat", "hue", "bloom", "bloom_px")
# colours with MIN_SMALL..MIN_PRESET-1 training icons of a kind (round 5; before they all took the shared recipe): fewer keys,
# the kind's default style only. Radiant gold actions (user's Divine Strike Radiant Ranged, Dazzling Breath: "the glyph is
# emitting light") are drawn without the dark edge and with a strong centre light: game - ours +17 L* on the glow at the centre
SMALL_KEYS = ("bg_gain", "halo", "glow_kept", "glow_thin", "cover", "light", "frame_light", "line_contrast", "line_sat",
              "glow_sat", "hue", "bloom", "bloom_px")
MIN_SMALL = 5
SOFT = {"sharpen": 0., "glow_thin": 1., "unsharp": .3}   # D22 (3A): the soft style's start; crisp starts at unsharp 0
PINS = {"crisp": ("unsharp",), "soft": ("sharpen", "sharpen_px")}   # what each D22 style holds fixed
free = lambda style, keys: [k for k in keys if k not in PINS[style]]
V5_KEYS = ("cover", "light", "light_px", "light_edge", "light_add", "frame_light", "frame_light_px", "frame_light_add",
           "line_contrast", "line_sat", "line_lift")
# illithid powers are fitted freely like the others. Tried (round 4): the action glyph recipe with only background and glow
# keys refit: training MAE 15.4 -> 20.3 and saturated red lines where the game's are pale pink; the free fit is closer by
# eye too (its line ramp is flatter than the game's white cores: 23 cells that line up less well, correlation ~.6-.7)
MIN_LIGHT_PX = 8                       # a light narrower than this is a dot, not the measured centre light (sigma 14-19 px)
MIN_PRESET = 15
HIST_W = 10.                           # weight of the (L*, chroma) histogram distance: how much of the icon is pale line core,
HIST_L = (0, 15, 25, 35, 45, 55, 65, 75, 85, 101)   # bright glow, saturated dark glow, stone... (what the eye sees; MAE
HIST_C = (0, 10, 20, 35, 50, 300)                   # alone gave Weapon red 20% fatter cores and 60% more dark-red glow)
PROFILE_W = .5                         # weight of the brightness mismatch next to the lines (L*, 1-4 px) in the recipe fit,
                                       # open space and closed shapes each: MAE alone let the halo spread 3-5 px past the
                                       # lines and darken the inside of closed shapes, where the game has a lit tint
EDGE_W = 10.                           # weight of |log(our edge contrast / the game's)|: MAE alone keeps lines soft
FILL_CLOSE = 8                         # px at 512: gaps this narrow count as closed when finding the glyph's closed shapes
GATE = {"spell": 18.1, "action": 18.1, "illithid": 18.1}  # hold-out median MAE /255; Phase 0's spell recomposite range was 11.7-18.1


KINDS = ("spell", "action", "illithid")


def kind(n):
    """icon name or family -> spell | illithid (illithid powers, D23: vein background) | action (actions and skills)"""
    return ("spell" if n.startswith("Spell") else "illithid" if n.startswith("TadpoleSuperPower") or n in ILLITHID_ART
            else "action")


def backgrounds():
    return {p.stem.replace("_bg", ""): np.asarray(Image.open(p).convert("RGB").resize((S, S), Image.LANCZOS)).astype(float) / 255
            for p in sorted(P.BACKGROUNDS.glob("*.DDS"))}


def atlas():
    """vanilla hotbar cells {icon: (64,64,3) float}. UVs are inset half a texel: snap to the 64 px cell holding the centre."""
    out, img = {}, {}
    for lsx in P.ATLAS_MAPS:
        t = lsx.read_text(encoding="utf-8")
        dds = P.UNPACKED / "Icons" / lsx.parent.parent.relative_to(P.UNPACKED / "GUI") / re.search(r'id="Path" type="string" value="([^"]+)"', t).group(1)
        A = img.setdefault(dds, Image.open(dds).convert("RGB"))
        for m in re.finditer(r'MapKey" type="FixedString" value="([^"]+)"/>\s*<attribute id="U1" type="float" value="([^"]+)"/>\s*'
                             r'<attribute id="U2" type="float" value="([^"]+)"/>\s*<attribute id="V1" type="float" value="([^"]+)"/>\s*'
                             r'<attribute id="V2" type="float" value="([^"]+)"', t):
            u1, u2, v1, v2 = map(float, m.groups()[1:])
            x, y = int((u1 + u2) / 2 * A.width) // S * S, int((v1 + v2) / 2 * A.height) // S * S
            out.setdefault(m.group(1), np.asarray(A.crop((x, y, x + S, y + S))).astype(float) / 255)
    return out


def down(master):
    """(512,512,4) uint8 straight alpha -> (64,64,5) float: premultiplied RGBA + the share of each pixel inside the
    glyph's closed shapes (lines = alpha > .5 at 512, gaps up to FILL_CLOSE px closed first)"""
    m = np.asarray(master).astype(np.float32) / 255
    pm = np.concatenate([m[..., :3] * m[..., 3:], m[..., 3:]], -1)
    core = m[..., 3] > .5
    shut = ndimage.binary_closing(core, ndimage.iterate_structure(ndimage.generate_binary_structure(2, 1), FILL_CLOSE)) | core
    f = m.shape[0] // S
    hole = (ndimage.binary_fill_holes(shut) & ~core).reshape(S, f, S, f).mean((1, 3))
    return np.dstack([np.stack([np.asarray(Image.fromarray(pm[..., k], "F").resize((S, S), Image.LANCZOS)) for k in range(4)], -1),
                      hole]).astype(float)


ZOOMS = (1.1, 1.2, 1.3)
KIND_BG = {"spell": "spell", "action": "action", "illithid": "tadpole"}   # a typical background, for same_size()


def same_size(master, g, bg):
    """Is the game's cell g (64,64,3) the master's drawing at the same size? L* correlation of g with a plain overlay of
    the master on bg (64,64,3) at size 1 vs the master enlarged about its centre (ZOOMS). Round 4: 16 of 41 illithid powers'
    PC cells enlarge the drawing 10-20% (Black Hole 0.31 -> 0.92 at x1.2) and Levitate is redrawn; every spell and action
    matches at size 1. Such cells say nothing about the recipe. -> (same, corr at size 1, best zoom)"""
    Lg = rgb2lab(np.clip(g, 0, 1))[..., 0].ravel()

    def corr(m):
        q = down(m)
        return float(np.corrcoef(Lg, rgb2lab(np.clip(bg * (1 - q[..., 3:4]) + q[..., :3], 0, 1))[..., 0].ravel())[0, 1])

    def zoom(s):
        w = round(master.width * s)
        o = (w - master.width) // 2
        return master.resize((w, w), Image.LANCZOS).crop((o, o, o + master.width, o + master.width))
    c1 = corr(master)
    cz = {s: corr(zoom(s)) for s in ZOOMS}
    s = max(cz, key=cz.get)
    return c1 >= .5 and cz[s] - c1 <= .05, round(c1, 3), (s if cz[s] > c1 else 1.0)


REG_ZOOMS = tuple(float(v) for v in np.round(np.arange(.95, 1.301, .025), 3))
REG_SHIFTS = np.arange(-1, 1.01, .25)
REG_MIN = .85      # an illithid cell is fitting data only when it lines up this well after register() (L* correlation)


def quick_down(master):
    """(512,512,4) uint8 -> (64,64,4) premultiplied, without the closed-shape channel (for the registration search)"""
    m = np.asarray(master).astype(np.float32) / 255
    pm = np.concatenate([m[..., :3] * m[..., 3:], m[..., 3:]], -1)
    return np.stack([np.asarray(Image.fromarray(pm[..., k], "F").resize((S, S), Image.LANCZOS)) for k in range(4)], -1).astype(float)


def zoomed(master, s):
    """master scaled by s about its centre on the same canvas (cropped when s > 1, padded when s < 1)"""
    if s == 1:
        return master
    w = round(master.width * s)
    big = master.resize((w, w), Image.LANCZOS)
    if w >= master.width:
        o = (w - master.width) // 2
        return big.crop((o, o, o + master.width, o + master.width))
    out = Image.new("RGBA", master.size, (0, 0, 0, 0))
    out.paste(big, ((master.width - w) // 2,) * 2)
    return out


def register(master, g, bg):
    """zoom and sub-pixel shift lining the master up with the game's cell g (round 5: 25 of 41 illithid PC cells enlarge
    the drawing x0.95-1.25 and/or shift it up to 1 px; L* correlation as is .70 median, lined up .91; spells and actions
    all line up at (1, 0, 0)). L* correlation of g with a plain overlay on bg over REG_ZOOMS x a coarse shift grid, then
    fine shifts (REG_SHIFTS) at the best zoom -> (zoom, dy, dx, corr as is, corr lined up)"""
    Lg = rgb2lab(np.clip(g, 0, 1))[..., 0].ravel()
    corr = lambda q: float(np.corrcoef(Lg, rgb2lab(np.clip(bg * (1 - q[..., 3:4]) + q[..., :3], 0, 1))[..., 0].ravel())[0, 1])
    sh = lambda q, dy, dx: q if dy == dx == 0 else ndimage.shift(q, (dy, dx, 0), order=3, mode="constant")
    qs = {s: quick_down(zoomed(master, s)) for s in REG_ZOOMS}
    c0 = corr(qs[1.0])
    coarse = (-1., -.5, 0., .5, 1.)
    best = max((corr(sh(qs[s], dy, dx)), s, dy, dx) for s in REG_ZOOMS for dy in coarse for dx in coarse)
    s = best[1]
    best = max((corr(sh(qs[s], dy, dx)), s, float(dy), float(dx)) for dy in REG_SHIFTS for dx in REG_SHIFTS)
    return best[1], best[2], best[3], round(c0, 3), round(best[0], 3)


def registered(master, reg):
    """down() of the master zoomed and shifted as reg = (zoom, dy, dx, ...) from register() says"""
    q = down(zoomed(master, reg[0]))
    return q if reg[1] == reg[2] == 0 else ndimage.shift(q, (reg[1], reg[2], 0), order=3, mode="constant")


CACHE = D / "hotbar_cache.npz"         # data/ (gitignored): masters at 64 px as fitted + same_size / register results
CACHE_V = "r5-1"                       # bump when down(), same_size() or register() change


def load_masters(names, hot, B):
    """-> Q {icon: (64,64,5) master at 64 px as fitted}, odd {icon: (corr, zoom) left out}, reg {icon: register() result}.
    From CACHE where the master file, the game cell and CACHE_V are unchanged, else computed and cached (round 5: down()
    plus same_size's four sizes took ~10 min of every fit for 1,082 icons). float32 either way, so a cached run equals a
    fresh one."""
    import hashlib
    old, Qold = {}, None
    if CACHE.exists():
        z = np.load(CACHE, allow_pickle=False)
        old, Qold = json.loads(str(z["meta"])), z["Q"]
    Q, odd, reg, meta, arr, fresh = {}, {}, {}, {}, [], 0
    for j, n in enumerate(names):
        p = D / "masters" / f"{n}.png"
        s = f"{CACHE_V}|{p.stat().st_mtime_ns}|{p.stat().st_size}|{hashlib.md5(hot[n].tobytes()).hexdigest()}"
        if n in old and old[n]["stamp"] == s:
            q, v = Qold[old[n]["i"]], old[n]
        else:
            fresh += 1
            m = Image.open(p).convert("RGBA")
            if kind(n) == "illithid":
                # illithid cells are lined up (zoom + sub-pixel shift) before fitting; round 4 left 18 of 41 out and fitted the
                # rest as they were (median L* correlation .70), which flattened the recipe's lines (user, round 5: Mind Tax)
                r = register(m, hot[n], B[KIND_BG["illithid"]])
                q, v = (registered(m, r) if r[4] >= REG_MIN else down(m)), {"reg": list(r)}
            else:
                q, v = down(m), {"same": list(same_size(m, hot[n], B[KIND_BG[kind(n)]]))}
            q = q.astype(np.float32)
        meta[n] = {**{k: x for k, x in v.items() if k in ("reg", "same")}, "stamp": s, "i": len(arr)}
        arr.append(q)
        Q[n] = q.astype(float)
        if "reg" in v:
            if v["reg"][4] >= REG_MIN:
                reg[n] = v["reg"]
            else:
                odd[n] = (v["reg"][4], v["reg"][0])
        elif not v["same"][0]:
            odd[n] = tuple(v["same"][1:])
        if j % 300 == 0:
            log(f"    masters {j}/{len(names)}")
    if fresh:
        np.savez_compressed(CACHE, Q=np.stack(arr), meta=json.dumps(meta))
    log(f"[2.2] masters at 64 px: {len(names) - fresh} from the cache, {fresh} computed")
    return Q, odd, reg


def far_mask(q):
    return ndimage.gaussian_filter(q[..., 3], 2) < .03          # pixels the glyph and its glow leave alone


def parts(q, bg, x):
    """glyph q (64,64,5 from down()) over background bg (64,64,3) with recipe x (see KEYS), step by step.
    The soft glow is thinned (opacity -> opacity^glow_thin; the game's 64 px glow is tighter than its large art's).
    Inside the glyph's closed shapes the frame takes a tint of the glyph's own colour (opacity `fill`): the game lights
    them (+6 L*, glyph hue; user, 2026-10-14: our dark glow "reduced contrast within the lines"). Then the halo, a dark
    glow grown from the line cores (opacity above line_from), spread like the lines' own glow but dark. The soft glow keeps
    glow_kept of its colour, rising to all of it on the lines. Last, the finished icon is sharpened darken-only around the
    glyph, by scaling colour (hue kept): a crisp dark rim against the lines without brightening their cores (glyph-only unsharp made Weapon red cores
    20% fatter than the game's). glyph = thinned glyph (premultiplied), shaded = frame after tint and halo, flat = before
    the sharpening.
    Round 4 (user: glow hides the stone, icons dull next to the game's): the soft glow covers the frame only by
    opacity^cover (the game shows ~half the stone's texture through a half-opaque glow, a plain overlay ~a quarter), and
    two lights centred on the square (PC version only: the controller art's lines are equally bright from centre to edge).
    One light over the finished icon could not fit both: the bare stone wants +10 L* at the centre on actions and nothing
    on spells, the lines +4 / +7 at the centre and darker corners (spells -19). So the stone gets frame x (1 + frame_light
    x fspot) + frame_light_add x fspot, fspot = Gaussian of frame_light_px px, and the glyph its own: gain 1 + light_edge +
    light x spot plus light_add x spot (scaled by opacity), spot = Gaussian of light_px px. unsharp = the soft recipe's
    glyph unsharp mask (D22, 3A: soft or crisp per colour). Line colours (user, round 4: the game's ramp is steeper, cores
    whiter, deep parts darker, less saturated): the glyph's straight colour keeps line_sat of its chroma (around its luma)
    and its luma maps to .5 + line_contrast x (luma - .5) + line_lift. glyph = after line colours and light.
    Round 5 (user: Mantle of Inspiration's glow deeper red, ours pink-ish): the PC glow is more colourful than the lines
    (game chroma 20-45% above ours on glow pixels for most colours, while our lines were already too colourful) and some
    colours are drawn at another hue on the PC hotbar (Control rose actions +7 deg, Cold blue actions +14 / +28): the
    colourfulness scale runs from line_sat on opaque pixels to line_sat x glow_sat on transparent ones, and the glyph's
    straight colour turns by `hue` degrees about the grey axis.
    Bloom (user, round 5: Divine Strike Radiant Ranged and Dazzling Breath, "the glyph is emitting light"; Mantle's deep red
    glow): the game's stone next to the glyph is brighter and takes the glyph's colour (Radiant gold, stone near the
    glyph: L* 28 vs ours 24, chroma 36 vs 21). The glyph's colour, blurred by bloom_px, is screened over the icon at
    strength `bloom` before the sharpening."""
    x = list(x)
    (gb, amt, r, th, s, sig, gam, c, k, t, pw, cov, A, lpx, le, ad, us, fl, fpx, fa, lc, ls, ll, gs, hu, bl, bpx) = \
        (x + NEUTRAL[len(x) - V4:])[:len(KEYS)]
    q, hole = q[..., :4], q[..., 4]
    if us:
        q = q + us * (q - ndimage.gaussian_filter(q, (UNSHARP_PX, UNSHARP_PX, 0)))
    q = q * q[..., 3:].clip(1e-4, 1) ** (min(max(pw, .5), 4) - 1)
    a = q[..., 3:].clip(0, 1)
    if (lc, ls, ll, gs, hu) != (1, 1, 0, 1, 0):
        st = (q[..., :3] / np.maximum(a, 1e-4)).clip(0, 1)
        if hu:
            st = st @ hue_turn(hu).T
        Y = (st @ LUMA)[..., None]
        # glow colourfulness never below 0 (round 5: Basic action white fitted -1.28, flipping its near-grey glow's faint
        # tint; clamped, its 22 icons' MAE 8.636 -> 8.635, at most 4/255 per pixel)
        st = Y + ls * (1 + (max(gs, 0) - 1) * (1 - a)) * (st - Y) + (.5 + lc * (Y - .5) + ll - Y)
        q = np.concatenate([st.clip(0, 1) * a, q[..., 3:]], -1)
    c = min(max(c, 0), 1)
    p = np.minimum(q[..., :3].clip(0, 1), a) * (c + (1 - c) * a ** abs(k))
    if (A, le, ad) != (0, 0, 0):
        spot = np.exp(-R2 / (2 * max(abs(lpx), MIN_LIGHT_PX) ** 2))[..., None]
        p = np.minimum((p * (1 + le + A * spot) + ad * spot * a).clip(0, None), a)
    core = np.clip((q[..., 3] - th) / max(1 - th, 1e-3), 0, 1)
    halo = np.clip(abs(s) * ndimage.gaussian_filter(core, abs(sig) + .01), 0, 1) ** abs(gam)
    lines = q[..., 3] > .6
    col = q[..., :3][lines].sum(0) / max(q[..., 3][lines].sum(), 1e-6)          # the glyph's main colour (straight)
    w = np.clip(abs(t) * hole, 0, 1)[..., None]
    fspot = np.exp(-R2 / (2 * max(abs(fpx), MIN_LIGHT_PX) ** 2))[..., None]
    shaded = ((bg * gb * (1 + fl * fspot) + fa * fspot) * (1 - w) + col * w) * (1 - halo[..., None])
    flat = (shaded * (1 - a ** min(max(cov, .3), 5)) + p).clip(0, 1)
    if bl:
        # in the glyph's own glow colour (straight colour of its soft glow, saturated), not its pale line colour: a blur
        # of the lines screened pale light over Radiant gold's stone where the game's is saturated gold (chroma 36)
        gm = (a[..., 0] >= GLOW_A[0]) & (a[..., 0] < GLOW_A[1])
        bc = q[..., :3][gm].sum(0) / max(q[..., 3][gm].sum(), 1e-6) if gm.sum() >= 5 else col
        glow = bc.clip(0, 1) * ndimage.gaussian_filter(a[..., 0], max(abs(bpx), MIN_BLOOM_PX))[..., None]
        flat = 1 - (1 - flat) * (1 - np.clip(abs(bl) * glow, 0, 1))
    near = np.clip(ndimage.gaussian_filter(a[..., 0], 1.5) * 4, 0, 1)                # only around the glyph: stone stays smooth
    Y = flat @ LUMA
    dY = Y - ndimage.gaussian_filter(Y, abs(r) + .05)
    # darkening scales each pixel's colour (hue kept: the game's rim is dark red, not black; subtracting gave black rims)
    f = np.clip(1 + abs(amt) * near * np.minimum(dY, 0) / np.maximum(Y, .02), DARK_FLOOR, 1)
    return {"glyph": np.concatenate([p, a], -1), "halo": halo, "fill": w[..., 0], "shaded": shaded, "flat": flat,
            "out": flat * f[..., None]}


def hue_turn(deg):
    """3x3 rotation of RGB about the grey axis by deg degrees (Rodrigues): turns hue, keeps grey grey"""
    k = np.ones(3) / np.sqrt(3)
    th = np.radians(deg)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.cos(th) * np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * np.outer(k, k)


def hist(im):
    """share of the icon's pixels per (L*, chroma) cell: pale line core, bright glow, saturated dark glow, stone..."""
    L = rgb2lab(np.clip(im, 0, 1))
    h, _, _ = np.histogram2d(L[..., 0].ravel(), np.hypot(L[..., 1], L[..., 2]).ravel(), bins=(HIST_L, HIST_C))
    return h / h.sum()


def glyph_over(q, bg, x):
    return parts(q, bg, x)["out"]


def frame(H, who, preset, second=None):
    """who = icon name or family -> frame entry [background, gain, share, hue or None(, chroma)]: spell_bg for spells,
    else the preset's default frame for the kind (actions: framed backgrounds; illithid powers: the veins); an action with
    a second colour (D26: two-colour, metamagic) has the two-colour frame"""
    k = kind(who)
    if k == "spell":
        return ["spell", 1.0, 1.0, None]
    if second and k == "action" and "frame_two_tone" in H:
        return H["frame_two_tone"][0]
    fr, near = (H["frames_illithid"], H["nearest_illithid"]) if k == "illithid" else (H["frames"], H["nearest"])
    return (fr.get(preset) or fr[near[preset]])[0]


def shift(bg, hue, chroma=1.0):
    """frame recoloured: rotate every pixel's a*b* so the frame's chroma-weighted hue lands on `hue` (degrees, CIELAB),
    chroma scaled by `chroma` (the silver illithid powers' blue-grey veins: the red veins at ~0.3 of their chroma)"""
    lab = rgb2lab(bg)
    a, b = lab[..., 1].copy(), lab[..., 2].copy()
    w = np.hypot(a, b)
    d = np.radians(hue) - np.arctan2((b * w).sum(), (a * w).sum())
    lab[..., 1], lab[..., 2] = chroma * (a * np.cos(d) - b * np.sin(d)), chroma * (a * np.sin(d) + b * np.cos(d))
    return np.clip(lab2rgb(lab), 0, 1)


def frame_img(B, f):
    """frame entry -> (64,64,3) image"""
    bg, gain, _, hue, *ch = f
    return (B[bg] if hue is None else shift(B[bg], hue, ch[0] if ch and ch[0] is not None else 1.0)) * gain


def recipe_for(H, who, preset):
    """the preset's own recipe when it has one, else the kind's default (who = icon name or family)"""
    r = H["recipe"][kind(who)]
    return r.get(preset) or r["default"]


def compose(master, family, preset, H=None, B=None, bg=None, second=None):
    """master (512,512,4) uint8 coloured glyph -> (64,64,3) float hotbar icon. bg = a frame entry (the app's Frame
    field) overrides the preset's default; second = the second colour of a two-colour icon (D26: its frame; the recipe
    follows the first colour)"""
    H = H or json.loads((D / "hotbar.json").read_text(encoding="utf-8"))
    B = B or backgrounds()
    return glyph_over(down(master), frame_img(B, bg or frame(H, family, preset, second)), recipe_for(H, family, preset))


def preset_ab(p):
    """a*, b* of a preset at mid lightness (from its curve), to find the nearest preset"""
    c = np.array(p["curve"])
    return c[len(c) // 2]


def preset_hue(p):
    """hue (degrees, CIELAB) of a preset at its most saturated lightness"""
    c = np.array(p["curve"])
    i = int(np.argmax(np.hypot(c[:, 0], c[:, 1])))
    return float(np.degrees(np.arctan2(c[i, 1], c[i, 0])))


def closest(h, cands):
    """glyph-free pixels h (n,3) vs candidate frames (k,n,3): per candidate its least-squares gain and the median
    CIEDE2000 after that gain (colour as seen; plain RGB differences picked pink for Weapon red where the eye sees violet)"""
    g = (cands * h).sum((1, 2)) / (cands * cands).sum((1, 2))
    lh = rgb2lab(h)
    return g, np.array([np.median(deltaE_ciede2000(lh, rgb2lab(np.clip(c * gi, 0, 1)))) for c, gi in zip(cands, g)])


# ---------------------------------------------------------------- fit machinery
TEX_B = (.03, .1, .2, .35, .5, .7)     # master opacity bins of the soft glow, for the stone-texture term
TEX_W = 10.                            # weight of mean |our stone-detail slope - the game's| over the TEX_B bins: MAE alone
                                       # hides the stone under the glow (round 4: at opacity .5 the game shows ~half the
                                       # stone's detail, v4 a quarter; fit cover stayed ~1 without this term)
LINE_W = .1                            # per L* unit: |mean L*| + |spread of L*| + |mean chroma| differences of the opaque
                                       # lines (user, round 4: flatter ramp, cores less white, too colourful); MAE barely
                                       # sees them (lines are a small share of the icon, and a half-pixel offset hides colour)
                                       # round 5: + |mean a*| + |mean b*| of the lines and |mean L*, a*, b*| of the soft glow
                                       # (GLOW_A opacity): hue and colourfulness, which MAE and the (L*, chroma) mix miss
GLOW_A = (.1, .5)                      # master opacity of the soft glow pixels for the glow colour term
hp = lambda x: x - ndimage.gaussian_filter(x, 1.2)       # fine stone detail


class Ref:
    """One icon's fixed fitting data, computed once (the fit renders each icon thousands of times): master at 64 px (q),
    frame image (F), the game's cell (g) and the game's side of every structure measure (game)."""

    def __init__(s, n, q, F, g):
        s.n, s.q, s.F, s.g = n, q, F, g
        line = q[..., 3] > .6
        d = ndimage.distance_transform_edt(~line).round().astype(int)
        reg = regions(q)
        s.cells = {(rg, i): m for rg in REGIONS for i, dd in enumerate(DISTS[:4]) if line.sum() >= 10
                   and (m := (d == dd) & reg[rg]).sum() >= 3}
        s.LF = rgb2lab(np.clip(F, 0, 1))[..., 0]
        s.near = ndimage.binary_dilation(q[..., 3] > .5, iterations=2)
        s.fh = hp(F @ LUMA)
        s.bins = [(d >= 2) & (q[..., 3] >= lo) & (q[..., 3] < hi) for lo, hi in zip(TEX_B, TEX_B[1:])]
        s.den = np.array([(s.fh[m] ** 2).sum() if m.sum() >= 8 else 0. for m in s.bins])
        s.lines = q[..., 3] > .9 if (q[..., 3] > .9).sum() >= 10 else None
        gl = (q[..., 3] >= GLOW_A[0]) & (q[..., 3] < GLOW_A[1])
        s.glow = gl if gl.sum() >= 10 else None
        s.game = s.measure(g)

    def measure(s, im):
        """a render's structure: L* above the bare frame per (region, distance) cell (as line_profile), (L*, chroma)
        histogram (as hist), edge contrast (as edge), stone detail carried per glow-opacity bin (sum of frame detail x ours),
        opaque lines' mean L*, spread of L*, mean chroma, mean a*, mean b* (hue and colourfulness, round 5), soft glow's
        mean L*, a*, b*"""
        lab = rgb2lab(np.clip(im, 0, 1))
        dl = lab[..., 0] - s.LF
        C = np.hypot(lab[..., 1], lab[..., 2])
        h, _, _ = np.histogram2d(lab[..., 0].ravel(), C.ravel(), bins=(HIST_L, HIST_C))
        ih = hp(np.clip(im, 0, 1) @ LUMA)
        L = lab[s.lines] if s.lines is not None else None
        return {"prof": {k: float(dl[m].mean()) for k, m in s.cells.items()}, "hist": h / h.sum(),
                "edge": float(np.abs(ndimage.laplace(lab[..., 0]))[s.near].mean()),
                "tex": np.array([(s.fh[m] * ih[m]).sum() if s.den[i] else 0. for i, m in enumerate(s.bins)]),
                "line": None if L is None else np.array([L[:, 0].mean(), L[:, 0].std(), C[s.lines].mean(), L[:, 1].mean(), L[:, 2].mean()]),
                "glow": None if s.glow is None else lab[s.glow].mean(0)}


def slopes(refs, tex):
    """stone-detail slope per glow-opacity bin, pooled over icons: 1 = the frame's detail shows fully, 0 = hidden"""
    den = sum(r.den for r in refs)
    return np.where(den > 0, sum(tex) / np.maximum(den, 1e-12), 0.)


def objective(ms, ps, render=lambda r, x: glyph_over(r.q, r.F, x)):
    """-> terms(x): mean 64 px MAE over refs ms; over refs ps: brightness mismatch next to the lines (per region, mean over
    1-4 px, cells with >= 5 icons), median edge-contrast ratio, mean (L*, chroma) histogram L1, mean |stone-detail slope
    ours - game|; and loss(x), their weighted sum. The game's side is pooled once here."""
    key = sorted({k for r in ps for k in r.game["prof"]})
    have = {k: [i for i, r in enumerate(ps) if k in r.game["prof"]] for k in key}
    key = [k for k in key if len(have[k]) >= 5]
    gprof = {k: np.mean([ps[i].game["prof"][k] for i in have[k]]) for k in key}
    gsl = slopes(ps, [r.game["tex"] for r in ps])
    union = list({id(r): r for r in ms + ps}.values())

    def terms(x):
        out = {id(r): render(r, x) for r in union}
        M = [r.measure(out[id(r)]) for r in ps]
        mis = 0.
        for rg in REGIONS:
            v = [abs(gprof[k] - np.mean([M[i]["prof"][k] for i in have[k]])) for k in key if k[0] == rg]
            mis += float(np.mean(v)) if v else 0.
        osl = slopes(ps, [m["tex"] for m in M])
        ln = [np.abs(m["line"] - r.game["line"]) for m, r in zip(M, ps) if m["line"] is not None]
        gw = [np.abs(m["glow"] - r.game["glow"]) for m, r in zip(M, ps) if m["glow"] is not None]
        return {"mae": float(np.mean([np.abs(out[id(r)] - r.g).mean() * 255 for r in ms])), "profile": mis,
                "edge": float(np.median([m["edge"] / r.game["edge"] for m, r in zip(M, ps)])),
                "hist": float(np.mean([np.abs(m["hist"] - r.game["hist"]).sum() for m, r in zip(M, ps)])),
                "tex": float(np.mean(np.abs(osl - gsl))), "slopes": (osl.round(2).tolist(), gsl.round(2).tolist()),
                "lines": float(np.mean(ln, 0).sum()) if ln else 0., "line_parts": np.mean(ln, 0).round(1).tolist() if ln else [],
                "glow": float(np.mean(gw, 0).sum()) if gw else 0., "glow_parts": np.mean(gw, 0).round(1).tolist() if gw else []}

    def loss(x):
        t = terms(x)
        return (t["mae"] + PROFILE_W * t["profile"] + EDGE_W * abs(np.log(t["edge"])) + HIST_W * t["hist"] + TEX_W * t["tex"]
                + LINE_W * (t["lines"] + t["glow"]))
    return terms, loss


def nm(loss, x0, free, maxiter):
    """Nelder-Mead over the keys named in `free`, the others held at x0 -> (x, loss)"""
    idx = [KEYS.index(k) for k in free]
    put = lambda v: [float(v[idx.index(i)]) if i in idx else float(x0[i]) for i in range(len(KEYS))]
    r = optimize.minimize(lambda v: loss(put(v)), [x0[i] for i in idx], method="Nelder-Mead",
                          options={"maxiter": maxiter, "xatol": 1e-3, "fatol": 1e-3, "adaptive": len(idx) > 8})
    return [round(v, 4) for v in put(r.x)], float(r.fun)


PW_PRESET, PW_SMALL = 800, 500         # Powell evaluations per colour refit (MIN_PRESET+ icons / MIN_SMALL+ icons)
POOL = 6                               # processes for the colour refits (8 cores here; ~250 MB each)


def preset_job(job):
    """one colour's refit (runs in a worker process): job = (kind, preset, refs, {style: start}, keys, evaluations, shared
    recipe) -> (kind, preset, {style: x}, {style: training MAE}, {style: loss}, loss of the shared recipe)"""
    kd, pn, rs, starts, keys, n, base = job
    _, lp = objective(rs, rs[::2] if len(rs) > 40 else rs)
    cand = {s: pw(lp, x, free(s, keys), n)[0] for s, x in starts.items()}
    mae = lambda x: float(np.mean([np.abs(glyph_over(r.q, r.F, x) - r.g).mean() * 255 for r in rs]))
    return kd, pn, cand, {s: mae(x) for s, x in cand.items()}, {s: lp(x) for s, x in cand.items()}, lp(base)


def pw(loss, x0, free, maxfev):
    """Powell over the keys named in `free` (line searches along each key at its own step, STEP), the others held at x0
    -> (x, loss)"""
    idx = [KEYS.index(k) for k in free]
    put = lambda v: [float(v[idx.index(i)]) if i in idx else float(x0[i]) for i in range(len(KEYS))]
    r = optimize.minimize(lambda v: loss(put(v)), [x0[i] for i in idx], method="Powell",
                          options={"maxfev": maxfev, "xtol": 1e-3, "ftol": 1e-4,
                                   "direc": np.diag([step_of(k, x0[i]) for k, i in zip(free, idx)])})
    return [round(v, 4) for v in put(r.x)], float(r.fun)


# ---------------------------------------------------------------- fit
def fit():
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    pre = {n: v["preset"] for n, v in G["icons"].items()}
    train, hold = (set((D / f).read_text().split()) for f in ("train.txt", "holdout.txt"))
    hot, B = atlas(), backgrounds()
    names = [n for n in sorted(train | hold) if n in hot and (D / "masters" / f"{n}.png").exists() and n in rows]
    log(f"[2.2] {len(hot)} atlas cells; {len(names)} train/hold-out icons with a cell and a master")
    Q, odd, reg = load_masters(names, hot, B)
    # a PC cell that is not the master's drawing at the same size says nothing about the recipe: no frames, fit or test
    names = [n for n in names if n not in odd]
    log(f"[2.2] PC cells not the master's drawing at its size (left out): {len(odd)}: "
        + ", ".join(f"{n} (corr {c:.2f}, best x{z})" for n, (c, z) in sorted(odd.items())))
    log(f"[2.2] illithid cells lined up: {len(reg)} (zoom != 1 or shifted: "
        f"{sum(1 for r in reg.values() if r[:3] != [1.0, 0.0, 0.0])}; L* correlation median as is "
        f"{np.median([r[3] for r in reg.values()]):.2f} -> {np.median([r[4] for r in reg.values()]):.2f})")

    # 1. frame per action icon: the framed background (x one gain) closest in colour as seen where the glyph leaves it alone
    K = list(FRAMED); BB = np.stack([B[k] for k in K])
    far, best = {}, {}
    for j, n in enumerate(names):
        if kind(n) == "action" and (m := far_mask(Q[n])).sum() >= 120:
            far[n] = m
            g, e = closest(hot[n][m], BB[:, m])
            k = int(np.argmin(e))
            best[n] = (K[k], float(g[k]), float(e[k]))
        if j % 300 == 0:
            log(f"    frames {j}/{len(names)}")
    ct, gains = defaultdict(Counter), defaultdict(list)
    for n, (k, g, _) in best.items():
        if n in train and n in pre:
            ct[pre[n]][k] += 1; gains[(pre[n], k)].append(g)
    frames = {p: [[k, round(float(np.median(gains[(p, k)])), 3), round(c / sum(cn.values()), 2), None]
                  for k, c in cn.most_common() if c / sum(cn.values()) >= MODE_SHARE or k == cn.most_common(1)[0][0]]
              for p, cn in ct.items()}
    # colours no frame matches (the game drew its own: grey stone with a magenta / violet / gold glow): try every framed
    # background hue-shifted to the preset's colour; it becomes the default only when clearly closer
    for p in frames:
        ns = [n for n in best if n in train and pre.get(n) == p]
        hue = preset_hue(next(x for x in G["presets"] if x["name"] == p))
        real = B[frames[p][0][0]]
        e_real = [closest(hot[n][far[n]], real[far[n]][None])[1][0] for n in ns]
        sh = {}
        for k in FRAMED:
            im = shift(B[k], hue)
            ge = [closest(hot[n][far[n]], im[far[n]][None]) for n in ns]
            sh[k] = ([float(g[0]) for g, _ in ge], [float(e[0]) for _, e in ge])
        k = min(sh, key=lambda k: np.median(sh[k][1]))
        if np.median(e_real) - np.median(sh[k][1]) >= SHIFT_MIN:
            share = float(np.mean(np.array(sh[k][1]) < np.array(e_real)))
            frames[p].insert(0, [k, round(float(np.median(sh[k][0])), 3), round(share, 2), round(hue, 1)])
            log(f"    {p}: no frame matches (median dE2000 {np.median(e_real):.1f}); {k} hue-shifted to {hue:.0f} deg: "
                f"{np.median(sh[k][1]):.1f}, closer for {share:.0%} of its {len(ns)} training actions")
    for p, f in sorted(frames.items(), key=lambda x: -sum(ct[x[0]].values())):
        log(f"    {p:26s} {sum(ct[p].values()):3d} icons -> " + ", ".join(
            f"{k}{'' if h is None else f'@{h:.0f}'} x{g} ({s:.0%})" for k, g, s, h in f))
    lab = {p["name"]: preset_ab(p) for p in G["presets"]}
    nearest = {p: min(frames, key=lambda q: np.linalg.norm(lab[q] - lab[p])) for p in lab if p not in frames}
    H = {"frames": frames, "nearest": nearest}
    # two-colour icons (D26, metamagic) have no one preset: their frame is their own (the game: metaMagic for all 8)
    tt = Counter(best[n][0] for n in best if n in train and n in TWO_TONE)
    if tt:
        k = tt.most_common(1)[0][0]
        H["frame_two_tone"] = [[k, round(float(np.median([best[n][1] for n in best if n in train and n in TWO_TONE
                                                            and best[n][0] == k])), 3), round(tt[k] / sum(tt.values()), 2), None]]
        log(f"    two-colour icons: {H['frame_two_tone']}")
    rule_e, best_e, hit = [], [], []
    for n in best:
        if n in hold and n in pre:
            f = frame(H, "Action", pre[n]); m = far[n]
            rule_e.append(float(np.median(deltaE_ciede2000(rgb2lab(hot[n][m]), rgb2lab(np.clip(frame_img(B, f)[m], 0, 1))))))
            best_e.append(best[n][2]); hit.append(f[3] is None and f[0] == best[n][0])
    ev = {"frame_far_de2000": {"holdout_rule": round(float(np.median(rule_e)), 2), "holdout_best_real": round(float(np.median(best_e)), 2),
                               "holdout_rule_is_best_real": round(float(np.mean(hit)), 3)},
          "not_same_size": {n: list(v) for n, v in sorted(odd.items())}, "registered": dict(sorted(reg.items()))}
    log(f"[2.2] action frame from preset, hold-out: default = per-icon best real frame {np.mean(hit):.0%}; glyph-free "
        f"pixels median dE2000 default {np.median(rule_e):.2f} (with its fixed gain) vs best real frame {np.median(best_e):.2f} (own gain)")

    # 1b. illithid powers (D23) sit on the veins (`tadpole`): as they are (red powers) or recoloured to the hue and chroma the
    #     game shows on the glyph-free pixels (silver powers: blue-grey veins, no such file exists), per colour preset; the
    #     recolour is the default only when SHIFT_MIN closer, like the actions' recoloured frames
    T, fi = B["tadpole"], {}
    ill = defaultdict(list)
    for n in names:
        if kind(n) == "illithid" and n in train and n in pre and (m := far_mask(Q[n])).sum() >= 60:
            ill[pre[n]].append((n, m))
    for p, its in sorted(ill.items(), key=lambda x: -len(x[1])):
        lg = rgb2lab(np.concatenate([hot[n][m] for n, m in its]))
        lt = rgb2lab(np.concatenate([T[m] for n, m in its]))
        cg, ct = np.hypot(lg[:, 1], lg[:, 2]), np.hypot(lt[:, 1], lt[:, 2])
        hue = float(np.degrees(np.arctan2((lg[:, 2] * cg).sum(), (lg[:, 1] * cg).sum())))
        chroma = float(np.median(cg) / np.median(ct))
        R = shift(T, hue, chroma)
        ge = {k: [closest(hot[n][m], im[m][None]) for n, m in its] for k, im in (("real", T), ("rec", R))}
        e = {k: np.array([float(v[1][0]) for v in ge[k]]) for k in ge}
        g = {k: round(float(np.median([v[0][0] for v in ge[k]])), 3) for k in ge}
        share = {"rec": round(float(np.mean(e["rec"] < e["real"])), 2)}
        share["real"] = round(1 - share["rec"], 2)
        opt = {"real": ["tadpole", g["real"], share["real"], None], "rec": ["tadpole", g["rec"], share["rec"], round(hue, 1), round(chroma, 2)]}
        first = "rec" if np.median(e["real"]) - np.median(e["rec"]) >= SHIFT_MIN else "real"
        other = "real" if first == "rec" else "rec"
        fi[p] = [opt[first]] + ([opt[other]] if share[other] >= MODE_SHARE else [])
        log(f"    illithid {p:22s} {len(its):2d} icons: veins as they are x{g['real']} median dE2000 {np.median(e['real']):.1f}; "
            f"recoloured to {hue:.0f} deg, chroma x{chroma:.2f}, x{g['rec']}: {np.median(e['rec']):.1f} (closer for "
            f"{share['rec']:.0%}) -> default {'recoloured' if first == 'rec' else 'as they are'}")
    H |= {"frames_illithid": fi, "nearest_illithid": {p: min(fi, key=lambda q: np.linalg.norm(lab[q] - lab[p])) for p in lab if p not in fi}}

    # 2. glyph recipe per kind, on training icons (every 3rd for MAE, every 6th for structure; all of a small kind):
    #    objective() = 64 px MAE + brightness next to the lines per region + edge contrast + (L*, chroma) mix + stone
    #    detail through the glow + line and glow colour. Shared recipe: the v5/v6 keys first (v4 numbers held), then every
    #    key, once per D22 style (crisp: darken-only sharpening; soft: glyph unsharp); the kind's default = the style with
    #    the lower training MAE. Then each colour preset with MIN_PRESET training icons refits PER_PRESET from the kind's
    #    recipe of each style, keeping the lower MAE on its icons (D22, 3A); colours with MIN_SMALL..MIN_PRESET-1 icons refit
    #    SMALL_KEYS in the kind's style and keep them only when their loss drops. Searches: Powell (`pw`, round 5;
    #    Nelder-Mead left keys that start small where they started); the colours run in parallel processes (`POOL`).
    recipe, styles = {}, {}
    its = (lambda n: 3) if "quick" in sys.argv else (lambda n: n)   # `hotbar fit quick`: smoke test of fit + page, minutes
    # `hotbar fit illithid` (any kinds named): refit only those, keep the others' recipes and numbers from hotbar.json.
    # `hotbar fit presets` (round 5): keep every kind's shared recipe and style from hotbar.json, refit the colours only, each
    # in the style it kept (from its own numbers, or the shared ones for colours new to their own): about a third of the time
    only = [a for a in sys.argv[2:] if a in KINDS]
    keep = "presets" in sys.argv[2:]
    old = json.loads((D / "hotbar.json").read_text(encoding="utf-8")) if only or keep else {}
    full = lambda x: list(x) + NEUTRAL[len(x) - V4:]                # a stored recipe with the keys it lacks switched off
    ctx, jobs = {}, []
    for kd in KINDS:
        if only and kd not in only:
            recipe[kd], styles[kd] = old["recipe"][kd], old["recipe_style"][kd]
            ev |= {k: v for k, v in old["eval"].items() if k.endswith(f"/{kd}")}
            log(f"[2.2] {kd}: kept from hotbar.json")
            continue
        R = {n: Ref(n, Q[n], frame_img(B, frame(H, n, pre.get(n, ""))), hot[n]) for n in names
             if kind(n) == kd and (kd == "spell" or n in pre)}
        tr = [R[n] for n in R if n in train]
        st = 3 if len(tr) > 150 else 1
        terms, loss = objective(tr[::st], tr[::2 * st])
        maes = lambda rs, x: [np.abs(glyph_over(r.q, r.F, x(r.n) if callable(x) else x) - r.g).mean() * 255 for r in rs]
        if keep:
            ds = old["recipe_style"][kd]["default"]
            base = full(old["recipe"][kd]["default"])
            xs, m = {ds: base}, {ds: float(np.mean(maes(tr, base)))}
            log(f"[2.2] {kd}: {len(tr)} training icons; shared recipe kept from hotbar.json ({ds}), loss {loss(base):.2f}")
        else:
            x0 = START[kd] + V5_START[len(START[kd]) - V4:]
            xa, la = pw(loss, x0, V5_KEYS + ("glow_sat", "hue", "bloom", "bloom_px"), its(400))
            log(f"[2.2] {kd}: {len(tr)} training icons; loss v4 {loss(START[kd][:V4]):.2f} -> v5/v6 keys only {la:.2f}")
            xs = {"crisp": pw(loss, xa, free("crisp", KEYS), its(1200))[0]}
            xs["soft"] = pw(loss, [SOFT.get(k, v) for k, v in zip(KEYS, xs["crisp"])], free("soft", KEYS), its(800))[0]
            m = {s: float(np.mean(maes(tr, x))) for s, x in xs.items()}
            ds = min(m, key=m.get)
            base = xs[ds]
        log(f"[2.2] {kd} shared recipe, training MAE " + ", ".join(f"{s} {v:.2f}" for s, v in m.items()) + f" -> {ds}: "
            + ", ".join(f"{k} {v:.3f}" for k, v in zip(KEYS, base)))
        t = terms(base)
        ps = [r.n for r in tr[::2 * st]]
        p = line_profile(ps, Q.get, lambda n: R[n].F, {"game": lambda n, q, F: hot[n], "ours": lambda n, q, F: glyph_over(q, F, base)})
        for rg in REGIONS:
            log(f"[2.2] {kd} brightness above the bare frame 1-4 px outside the lines, {rg}: game "
                f"{[round(v, 1) for v in p[rg]['game'][:4]]}, ours {[round(v, 1) for v in p[rg]['ours'][:4]]}")
        ev[f"edge_ratio/{kd}"] = round(t["edge"], 3)
        ev[f"stone_slopes/{kd}"] = {"ours": t["slopes"][0], "game": t["slopes"][1], "bins": TEX_B}
        log(f"[2.2] {kd} edge contrast ours / game {t['edge']:.2f}; stone detail through the glow by opacity bin "
            f"{TEX_B}, ours {t['slopes'][0]}, game {t['slopes'][1]}")
        ev[f"styles/{kd}"] = {"default": {"n": len(tr), **{s: round(v, 2) for s, v in m.items()}, "pick": ds}}
        by = defaultdict(list)
        for r in tr:
            by[pre.get(r.n)].append(r)
        for pn, rs in by.items():
            if pn is None or len(rs) < MIN_SMALL:
                continue
            big = len(rs) >= MIN_PRESET
            if keep:          # each colour in the style it kept, from its own numbers (or the shared ones when new)
                s0 = old["recipe_style"][kd].get(pn, ds)
                starts = {s0: full(old["recipe"][kd][pn]) if pn in old["recipe"][kd] else base}
            else:
                starts = xs if big else {ds: base}
            jobs.append((kd, pn, rs, starts, PER_PRESET if big else SMALL_KEYS, its(PW_PRESET if big else PW_SMALL), base))
        ctx[kd] = (R, tr, base, ds, maes)

    # colours in parallel (round 5): one process per colour, biggest first; numpy single-threaded in each
    done = {}
    if jobs:
        import os
        from concurrent.futures import ProcessPoolExecutor
        os.environ.update({k: "1" for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")})
        jobs.sort(key=lambda j: -len(j[2]))
        log(f"[2.2] {len(jobs)} colour refits on {min(POOL, len(jobs))} processes: "
            + ", ".join(f"{kd}/{pn} ({len(rs)})" for kd, pn, rs, *_ in jobs))
        with ProcessPoolExecutor(min(POOL, len(jobs))) as ex:
            for kd, pn, cand, mp, lf, l0 in ex.map(preset_job, jobs):
                done[(kd, pn)] = (cand, mp, lf, l0)
                log(f"    done {kd}/{pn}")
    for kd, (R, tr, base, ds, maes) in ctx.items():
        rk, sk = {"default": base}, {"default": ds}
        for (k2, pn), (cand, mp, lf, l0) in done.items():          # biggest colours first (jobs order)
            if k2 != kd:
                continue
            rs = [r for r in tr if pre.get(r.n) == pn]
            s = min(mp, key=mp.get)
            big = len(rs) >= MIN_PRESET
            shared = float(np.mean(maes(rs, base)))
            if not big and lf[s] >= l0:           # a small colour keeps its own numbers only when they help
                log(f"    {kd} {pn:24s} {len(rs):3d} icons: own numbers did not lower the loss ({lf[s]:.2f} vs shared "
                    f"{l0:.2f}): shared recipe")
                continue
            rk[pn], sk[pn] = cand[s], s
            ev[f"styles/{kd}"][pn] = {"n": len(rs), **{k: round(v, 2) for k, v in mp.items()}, "pick": s,
                                      "shared": round(shared, 2), "small": not big}
            log(f"    {kd} {pn:24s} {len(rs):3d} icons{' (small)' if not big else ''}: MAE shared {shared:.2f} -> "
                + ", ".join(f"{k} {v:.2f}" for k, v in mp.items()) + f" ({s}); loss {l0:.2f} -> {lf[s]:.2f}; "
                + ", ".join(f"{k} {rk[pn][KEYS.index(k)]:.2f}" for k in (PER_PRESET if big else SMALL_KEYS)))
        recipe[kd], styles[kd] = rk, sk
        rx = lambda n: rk.get(pre.get(n)) or base
        for split, ss in (("train", train), ("holdout", hold)):
            rs = [R[n] for n in R if n in ss]
            outs = {r.n: glyph_over(r.q, r.F, rx(r.n)) for r in rs}
            e = [np.abs(outs[r.n] - r.g).mean() * 255 for r in rs]
            hd = [np.abs(hist(outs[r.n]) - r.game["hist"]).sum() for r in rs]
            e1, e0 = maes(rs, base), maes(rs, PLAIN)
            ev[f"{split}/{kd}"] = {"n": len(rs), "mae": round(float(np.median(e)), 2), "p90": round(float(np.percentile(e, 90)), 2),
                                   "default_only": round(float(np.median(e1)), 2), "plain_over": round(float(np.median(e0)), 2),
                                   "hist": round(float(np.median(hd)), 3)}
            log(f"[2.2] {split} {kd}: {len(rs)} icons, 64 px MAE median {np.median(e):.2f} p90 {np.percentile(e, 90):.2f} /255 "
                f"(default recipe only {np.median(e1):.2f}, plain alpha-over {np.median(e0):.2f}); (L*, chroma) histogram "
                f"distance median {np.median(hd):.3f}")
        if ev[f"holdout/{kd}"]["n"] >= 5:                # illithid powers: 1 test icon after same_size, no gate
            assert ev[f"holdout/{kd}"]["mae"] <= GATE[kd], f"{kd} hold-out MAE {ev[f'holdout/{kd}']['mae']} over the gate {GATE[kd]}"
        else:
            log(f"[2.2] {kd}: {ev[f'holdout/{kd}']['n']} test icon(s), too few for the gate (training MAE above)")
    H |= {"recipe": recipe, "recipe_style": styles, "recipe_keys": KEYS, "eval": ev, "fitted_on": f"data/train.txt ({len(train)} icons)",
          "notes": "frames[preset] = [[background, gain, share of the preset's training actions, hue or null], ...], default "
                   "first; hue = the background hue-shifted to that CIELAB hue (degrees; see shift()), used where no frame matches; "
                   "nearest[preset] = preset whose frames a preset without action icons borrows (closest mid-lightness a*b*). "
                   "frames_illithid / nearest_illithid: the same for illithid powers, always the veins (tadpole), entries may "
                   "carry a 5th field, the chroma scale of the recolour. "
                   "recipe[spell|action|illithid][default|preset] = KEYS (see parts()): background gain; darken-only sharpening "
                   "(amount, radius px at 64); dark glow from the line cores (from, strength, blur, curve); glow colour kept and "
                   "its curve; closed-shape tint; glow thinning; glow cover; light over everything (gain, px, edge, add); glyph "
                   "unsharp; frame light under the glyph (gain, px, add); line colours (contrast, colourfulness, lift); glow "
                   "colourfulness over the lines'; hue turn (degrees); bloom in the glyph's glow colour (strength, px). Shorter "
                   "recipes lack the later keys (off: NEUTRAL). recipe_style = D22 style per entry: crisp (darken-only "
                   "sharpening, no glyph unsharp) or soft (glyph unsharp, no darken-only sharpening). A preset with its own entry "
                   "refit PER_PRESET (SMALL_KEYS under MIN_PRESET icons) on its training icons (recipe_for). Spells: spell_bg. "
                   "Actions: framed backgrounds only. eval.registered[icon] = illithid cell lined up: zoom, dy, dx, L* "
                   "correlation as is, lined up (register())."}
    (D / "hotbar.json").write_text(json.dumps(H, indent=1), encoding="utf-8")
    log(f"[2.2] wrote {D / 'hotbar.json'}")

    # 3. check sheet: hold-out icons, vanilla | ours | |diff| x3
    hs = [n for n in names if n in hold and (kind(n) == "spell" or n in pre)]
    C = 128
    sheet = Image.new("RGB", (2 * 3 * (C + 4) + 12, ((len(hs) + 1) // 2) * (C + 14)), (30, 30, 30)); d = ImageDraw.Draw(sheet)
    for j, n in enumerate(hs):
        f = frame(H, n, pre.get(n, ""))
        k = f[0] if f[3] is None else f"{f[0]}@{f[3]:.0f}"
        ours = glyph_over(Q[n], frame_img(B, f), recipe_for(H, n, pre.get(n, "")))
        x0, y0 = (j % 2) * (3 * (C + 4) + 12), (j // 2) * (C + 14)
        for c, im in enumerate((hot[n], ours, np.abs(ours - hot[n]) * 3)):
            sheet.paste(Image.fromarray((im.clip(0, 1) * 255).astype(np.uint8)).resize((C, C), Image.NEAREST), (x0 + c * (C + 4), y0 + 12))
        d.text((x0 + 2, y0), f"{n[:34]} {k} {np.abs(ours - hot[n]).mean() * 255:.1f}", fill=(255, 220, 0))
    sheet.save(D / "hotbar.png")
    log(f"[2.2] wrote {D / 'hotbar.png'} ({len(hs)} hold-out icons)")


# ---------------------------------------------------------------- review page (data/hotbar.html, local: Larian art)
# 1 = D19 frame field, 2 = D20 recoloured frames, 3 = D22 crisp or soft per colour, 4 = D23 illithid powers (user, 2026-10-14)
DECIDED = {1: "A", 2: "A", 3: "A", 4: "A"}      # 5 (round 5: next step, 2.4 or another hotbar round) open
# round 5 page text, filled in from the fit's log and the page's numbers (2026-10-15)
GAPS = ("Maiming Strike's bright middle (Weapon red kept nearly the same light); Mantle's glow, closer but still pinker "
        "than the game's (part of it is the pink default frame); the saturated gold stone around Radiant gold glyphs; Mind "
        "Tax's red glow; spell corners still 14-17 L* too bright (were 17-22).")
TIMES = (("Load the 1,082 masters at 64 px and check each against its game cell", "≈10 min, every run",
          "13 min once (now also lining up the illithid cells), then seconds from a cache"),
         ("Shared recipe per kind (spells, actions, illithid)", "≈40 min",
          "kept for spells and actions; illithid refit from scratch: 7 min"),
         ("Each colour's own numbers", "≈20 min, one colour at a time, 17 colours",
          "10 min for spells and actions, 6 colours at a time, 39 colours"),
         ("Whole fit", "≈65 min", "33 min this round; a colours-only refit next time: about 10 min"))
# what each frame looks like on screen (the user decides by look, not by file name)
LOOK = {"control": "pink", "weaponAction": "violet, red base", "summon": "amber", "utility": "steel blue",
        "buff": "grey, gold base", "heal": "grey, teal base", "action": "plum", "bonusAction": "slate blue",
        "lightening": "deep blue", "radiance": "grey, yellow base", "fireDamage": "grey, orange base",
        "monster": "grey, green base", "metaMagic": "grey circle", "weaponBonusAction": "slate blue, red base",
        "actionPassive": "dark amber, no frame", "buffPassive": "dark amber, no frame", "tadpole": "red veins, no frame",
        "spell": "brown stone", "debuffPassive": "purple glow, no frame", "fireDamagePassive": "dark orange glow, no frame",
        "damagePassive": "dark red glow, no frame", "utilityPassive": "dark blue glow, no frame"}
STEP_EX = ("Action_GiantBadger_Claws", "Spell_Conjuration_DimensionDoor")
# the user's round-4 and round-5 notes (6 pairs): Maiming Strike, Mantle of Inspiration, Dimension Door, Divine Strike Radiant Ranged,
# Dazzling Breath, Mind Tax. Chart colours: dataviz categorical dark slots (game #3987e5, now #d95926, round 4 #c98500)
PAIRS = ("Action_CripplingStrike", "Action_MantleOfInspiration", "Spell_Conjuration_DimensionDoor",
         "Action_DivineStrike_Radiant_Ranged", "Action_DragonForm_ScintillatingBreath", "Action_Mag_Illithid_MindTax")
DISTS = range(1, 7)                              # px at 64 outside the lines, for the brightness profile


REGIONS = ("open", "gap", "closed")
REGION_NAMES = {"open": "open space", "gap": "narrow spaces between lines", "closed": "inside closed shapes"}


def regions(q):
    """where each pixel outside the lines sits: inside the glyph's closed shapes (q[..., 4]), in a narrow space between
    lines (up to ~6 px wide: what a 3 px closing of the lines fills) or in open space"""
    line = q[..., 3] > .5
    closed = q[..., 4] > .5
    gap = (ndimage.binary_closing(line, ndimage.iterate_structure(ndimage.generate_binary_structure(2, 1), 3)) | line) & ~line & ~closed
    return {"open": ~closed & ~gap, "gap": gap, "closed": closed}


def line_profile(ns, Q, fr, renders):
    """mean L* above the bare frame at each distance outside the glyph's lines (opacity > .6), per render(n, q, frame) and
    region (see regions()) -> {region: {render: [per distance]}} (nan: no pixels there)"""
    acc = {(rg, k): [[] for _ in DISTS] for rg in REGIONS for k in renders}
    for n in ns:
        q, F = Q(n), fr(n)
        line = q[..., 3] > .6
        if line.sum() < 10:
            continue
        d = ndimage.distance_transform_edt(~line).round().astype(int)
        reg = regions(q)
        LF = rgb2lab(np.clip(F, 0, 1))[..., 0]
        for k, fn in renders.items():
            dl = rgb2lab(np.clip(fn(n, q, F), 0, 1))[..., 0] - LF
            for rg in REGIONS:
                for i, dd in enumerate(DISTS):
                    if (s := (d == dd) & reg[rg]).sum() >= 3:
                        acc[(rg, k)][i].append(float(dl[s].mean()))
    return {rg: {k: [float(np.mean(v)) if len(v) >= 5 else float("nan") for v in acc[(rg, k)]] for k in renders} for rg in REGIONS}


RINGS = (0, .3, .55, .8, 1.05, 1.5)      # distance from the icon's centre in half-widths (corners reach 1.41)
RR = np.sqrt(R2) / (S / 2)


def rings(items, render):
    """L* of the game minus a render by distance from the centre, over every pixel, the bare frame (far_mask) and the
    opaque lines (master opacity > .9 at 64 px). items = [(n, q, F, game)], render(n, q, F) -> {kind of pixel: [per ring]}"""
    acc = {k: [[] for _ in RINGS[1:]] for k in ("all", "frame", "lines")}
    for n, q, F, g in items:
        dL = rgb2lab(np.clip(g, 0, 1))[..., 0] - rgb2lab(np.clip(render(n, q, F), 0, 1))[..., 0]
        for k, m in (("all", np.ones((S, S), bool)), ("frame", far_mask(q)), ("lines", q[..., 3] > .9)):
            for i in range(len(RINGS) - 1):
                if (s := m & (RR >= RINGS[i]) & (RR < RINGS[i + 1])).sum() >= 5:
                    acc[k][i].append(float(dL[s].mean()))
    return {k: [float(np.mean(v)) if len(v) >= 5 else float("nan") for v in vs] for k, vs in acc.items()}


def line_stats(items, render):
    """opaque line pixels (master opacity > .9 at 64 px) of a render: median L*, median chroma"""
    px = []
    for n, q, F, g in items:
        if (o := q[..., 3] > .9).sum() >= 10:
            lab = rgb2lab(np.clip(render(n, q, F), 0, 1))[o]
            px.append(np.stack([lab[:, 0], np.hypot(lab[:, 1], lab[:, 2])], 1))
    px = np.concatenate(px)
    return [round(float(np.median(px[:, 0])), 1), round(float(np.median(px[:, 1])), 1)]


def glow_colour(items, render):
    """soft glow pixels (master opacity GLOW_A) of a render: per icon the chroma-weighted hue (degrees, CIELAB) and median
    chroma -> [(hue, chroma)]"""
    out = []
    for n, q, F, g in items:
        if (m := (q[..., 3] >= GLOW_A[0]) & (q[..., 3] < GLOW_A[1])).sum() >= 10:
            lab = rgb2lab(np.clip(render(n, q, F), 0, 1))[m]
            C = np.hypot(lab[:, 1], lab[:, 2])
            out.append((float(np.degrees(np.arctan2((lab[:, 2] * C).sum(), (lab[:, 1] * C).sum()))), float(np.median(C))))
    return out


def cross(items, render):
    """line middle minus line rim, L*, per icon (middle = 2+ px inside the master's lines, rim = their outer pixel; opacity
    > .5 at 64 px): the white core the user missed on Mind Tax (round 5)"""
    out = []
    for n, q, F, g in items:
        line = q[..., 3] > .5
        dp = ndimage.distance_transform_edt(line)
        mid, rim = line & (dp >= 2), line & (dp <= 1)
        if mid.sum() >= 5 and rim.sum() >= 5:
            L = rgb2lab(np.clip(render(n, q, F), 0, 1))[..., 0]
            out.append(float(L[mid].mean() - L[rim].mean()))
    return out


def stone_slope(items, render):
    """contrast of the bare background: slope of a render's L* on the frame's own L* where the glyph leaves it alone
    (far_mask), per icon (1 = the frame's own contrast; the game's illithid veins are contrastier than ours, round 5)"""
    out = []
    for n, q, F, g in items:
        if (m := far_mask(q)).sum() > 50:
            out.append(float(np.polyfit(rgb2lab(np.clip(F, 0, 1))[..., 0][m], rgb2lab(np.clip(render(n, q, F), 0, 1))[..., 0][m], 1)[0]))
    return out


def edge(im, q):
    """edge contrast: mean |Laplacian of L*| within 2 px of the glyph's lines (the game's 64 px lines are crisper)"""
    near = ndimage.binary_dilation(q[..., 3] > .5, iterations=2)
    return float(np.abs(ndimage.laplace(rgb2lab(np.clip(im, 0, 1))[..., 0]))[near].mean())


def chart(title, xs, series, lo, hi, yticks, xlab, fx, fy, head):
    """small line chart (inline SVG) with a hover / arrow-key readout of every series at the nearest x.
    series = [(label, colour, ys)], nan = no value (the line skips it); fx, fy format the axes and values; head(x) = the
    readout's first line"""
    from .page import e
    W, Hh, L, R, T, Bm = 460, 250, 46, 14, 12, 44
    X = lambda v: L + (v - xs[0]) / (xs[-1] - xs[0]) * (W - L - R)
    Y = lambda v: T + (hi - v) / (hi - lo) * (Hh - T - Bm)
    pts = lambda ys: [(x, y) for x, y in zip(xs, ys) if y == y]
    grid = "".join(f'<line x1={L} x2={W - R} y1={Y(v):.1f} y2={Y(v):.1f} class="gl{" z" if v == 0 else ""}" />'
                   f'<text x={L - 8} y={Y(v) + 4:.1f} class=yt>{fy(v)}</text>' for v in yticks)
    xt = "".join(f'<text x={X(v):.1f} y={Hh - Bm + 17} class=xt>{fx(v)}</text>' for v in xs)
    lines = "".join(f'<polyline points="{" ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts(ys))}" stroke="{c}" class=ln />'
                    for _, c, ys in series)
    dots = "".join(f'<circle cx={X(p[0][0]):.1f} cy={Y(p[0][1]):.1f} r=4 fill="{c}" class=dot />' for _, c, ys in series if (p := pts(ys)))
    data = e(json.dumps({"px": [round(X(v), 1) for v in xs], "h": [head(v) for v in xs],
                         "s": [[lab, c, [fy(y) for y in ys]] for lab, c, ys in series]}))
    return (f'<div class=cw><div class=ct>{e(title)}</div><svg class=chart viewBox="0 0 {W} {Hh}" role=img tabindex=0 '
            f'aria-label="{e(title)}" data-d="{data}" data-w="{W}">{grid}{xt}'
            f'<text x={(L + W - R) / 2:.0f} y={Hh - 6} class=xl>{e(xlab)}</text>'
            f'<line class=cross x1=0 x2=0 y1={T} y2={Hh - Bm} />{lines}{dots}</svg><div class=tip></div></div>')


def report():
    import warnings
    from skimage.color import lab2rgb
    warnings.filterwarnings("ignore", message=".*negative Z values.*")     # lab2rgb clips out-of-gamut swatches: fine
    from .page import e, src, decision, row, page, lede_reply
    H = json.loads((D / "hotbar.json").read_text(encoding="utf-8"))
    H0 = json.loads((D / "hotbar.r4.json").read_text(encoding="utf-8"))   # round 4: the page the user's round-5 notes are on
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    G0 = json.loads((D / "grammar.r4.json").read_text(encoding="utf-8"))
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    pre = {n: v["preset"] for n, v in G["icons"].items()}
    pre0 = {n: v["preset"] for n, v in G0["icons"].items()}
    train, hold = (set((D / f).read_text().split()) for f in ("train.txt", "holdout.txt"))
    hot, B = atlas(), backgrounds()
    X, ev = H["recipe"], H["eval"]
    rx = lambda n: recipe_for(H, n, pre.get(n, ""))
    cache, keep = {}, []
    reg = ev.get("registered", {})

    def Q(n):
        """the master at 64 px as fitted: illithid cells lined up with the game's (zoom + shift, register())"""
        if n not in cache:
            m = Image.open(D / "masters" / f"{n}.png").convert("RGBA")
            cache[n] = registered(m, reg[n]) if n in reg else down(m)
        return cache[n]

    odd = ev.get("not_same_size", {})
    drawn = lambda n: n in hot and n in rows and (D / "masters" / f"{n}.png").exists() and (kind(n) == "spell" or n in pre)
    usable = lambda n: drawn(n) and n not in odd
    fk = lambda n: frame(H, n, pre.get(n, ""))
    fr = lambda n: frame_img(B, fk(n))
    name = lambda n: rows[n]["name"] or re.sub(r"(?<=[a-z])(?=[A-Z])", " ", re.sub(r"^(Mag|Monster)_", "", n.split("_", 1)[1])).replace("_", " ")
    mae = lambda a, b: float(np.abs(np.clip(a, 0, 1) - b).mean() * 255)

    def to_img(x, alpha=None):
        rgb = (np.clip(x, 0, 1) * 255).round().astype(np.uint8)
        if alpha is None:
            return Image.fromarray(rgb)
        return Image.fromarray(np.dstack([rgb, (np.clip(alpha, 0, 1) * 255).round().astype(np.uint8)]), "RGBA")

    def straight(q):
        a = q[..., 3:4].clip(0, 1)
        return to_img(np.where(a > 1e-3, q[..., :3] / np.maximum(a, 1e-3), 0), a[..., 0])

    def img(im, px, cls="px", tip=""):
        keep.append(im)                                   # page.src caches by id(): keep every image alive
        return f'<img class="{cls}" src="{src(im, im.width, lossless=True)}" width={px} height={px} alt="{e(tip)}" title="{e(tip)}">'

    panel = lambda h, cap: f'<div class=panel>{h}<span>{e(cap)}</span></div>'

    def swatch(pname):
        c = np.array(next(p for p in G["presets"] if p["name"] == pname)["curve"])
        i = int(np.argmax(np.hypot(c[:, 0], c[:, 1])))              # the preset's most saturated lightness bin
        rgb = lab2rgb(np.array([[[(i + .5) * 100 / len(c), *c[i]]]]))[0, 0]
        return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in np.clip(rgb, 0, 1))

    def fname(f):
        if f[3] is None:
            return LOOK.get(f[0], f[0])
        ch = f[4] if len(f) > 4 and f[4] is not None else 1.0
        return f"{LOOK.get(f[0], f[0])} recoloured to {f[3]:.0f}°" + (f", {ch:.0%} of its colourfulness" if ch != 1 else "")
    fthumb = lambda f: img(to_img(frame_img(B, f)), 20, cls="px th")
    now = lambda n: glyph_over(Q(n), fr(n), rx(n))

    def before(n, q=None):
        """round 4's render: its frames and recipes. q = None: the master as round 4 drew it (illithid cells not lined up);
        measures pass the lined-up q, so they compare recipes, not alignment"""
        p = pre0.get(n) or pre.get(n, "")
        if q is None:
            q = down(Image.open(D / "masters" / f"{n}.png").convert("RGBA")) if n in reg else Q(n)
        return glyph_over(q, frame_img(B, frame(H0, n, p)), recipe_for(H0, n, p))

    def zoom(a_img, b_img, w=16):
        d = ndimage.uniform_filter(np.abs(a_img - b_img).mean(-1), w)[w // 2:S - w // 2 + 1, w // 2:S - w // 2 + 1]
        y, x = np.unravel_index(np.argmax(d), d.shape)
        return int(min(y, S - w)), int(min(x, S - w))

    sig = lambda v: "n/a" if v != v else f"{v:+.1f}".replace("-", "−")
    kname = {"action": "Actions", "spell": "Spells", "illithid": "Illithid powers"}
    sets = {kd: [n for n in sorted(hold) if usable(n) and kind(n) == kd] +
                [n for n in sorted(train) if usable(n) and kind(n) == kd][::4] for kd in KINDS}
    items = lambda ns: [(n, Q(n), fr(n), hot[n]) for n in ns]
    R_NOW, R_BEFORE = (lambda n, q, F: glyph_over(q, F, rx(n))), (lambda n, q, F: before(n, q))
    R_GAME = lambda n, q, F: hot[n]
    two = ("action", "spell")
    log(f"[2.2] page: {', '.join(f'{len(v)} {k}' for k, v in sets.items())} icons for the measures")

    # ---- the user's six pairs: game | round 4 | now, zoomed where they differ most
    strips, pmae = [], {}
    for i, n in enumerate([n for n in PAIRS if usable(n)]):
        old, new = before(n), now(n)
        pmae[n] = (mae(old, hot[n]), mae(new, hot[n]))
        y0, x0 = zoom(hot[n], old)
        sc = 128 / S
        box = f'<span class=zb style="left:{x0 * sc:.0f}px;top:{y0 * sc:.0f}px;width:{16 * sc:.0f}px;height:{16 * sc:.0f}px"></span>'
        crop = lambda im: img(to_img(im[y0:y0 + 16, x0:x0 + 16]), 96)
        strips.append(
            f'<div class=strip><div class=sname>{e(name(n))} <span>· {e(kname[kind(n)].lower()[:-1])}, '
            f'{e(fname(fk(n)) if kind(n) != "spell" else "brown stone")}{" frame" if kind(n) == "action" else ""}</span></div>'
            + panel(f'<span class=zw>{img(to_img(hot[n]), 128, tip=n)}{box}</span>', "Game (yellow box: zoomed)")
            + panel(img(to_img(old), 128), f"Round 4 · {pmae[n][0]:.1f}")
            + panel(img(to_img(new), 128), f"Now · {pmae[n][1]:.1f}") + '<div class=sep></div>'
            + panel(crop(hot[n]), "Game") + panel(crop(old), "Round 4") + panel(crop(new), "Now") + '</div>')
    pairs_sec = (f'<h2 class=sec>Your six icons</h2><p class=secsub>The game\'s hotbar icon, round 4\'s rebuild (the page you '
                 f'wrote your notes on) and today\'s, then the 16 px square where round 4 differed most, enlarged. Numbers: mean '
                 f'difference to the game per pixel (/255, lower = closer).</p>{"".join(strips)}')

    # ---- round 5 notes (user, 2026-10-15), one section per note: measures on the page sets, round 4 vs now
    rl = [f"{a:g}-{b:g}" for a, b in zip(RINGS, RINGS[1:])]
    xs = list(range(len(rl)))
    byp = defaultdict(list)
    for kd in KINDS:
        for n in sets[kd]:
            if n in pre:
                byp[(kd, pre[n])].append(n)
    legend = ('<div class=legend><span><i style="background:#c98500"></i>Round 4</span>'
              '<span><i style="background:#d95926"></i>Now</span></div>')

    def rchart(title, rg, px):
        ys = [v for k in ("before", "now") for v in rg[k][px] if v == v] or [0]
        lo, hi = min(-10, 5 * np.floor(min(ys) / 5)), max(10, 5 * np.ceil(max(ys) / 5))
        return chart(title, xs, [("Round 4", "#c98500", rg["before"][px]), ("Now", "#d95926", rg["now"][px])],
                     lo, hi, tuple(range(int(lo), int(hi) + 1, 5)), "distance from the centre (half-widths)", lambda i: rl[i],
                     sig, lambda i: f"{rl[i]} half-widths from the centre: game minus ours (L*)")
    rset = lambda ns: {k: rings(items(ns), fn) for k, fn in (("before", R_BEFORE), ("now", R_NOW))}
    rec_now = lambda kd, pn: dict(zip(KEYS, padded(X[kd].get(pn) or X[kd]["default"])))
    rec_old = lambda kd, pn: dict(zip(KEYS, padded(H0["recipe"][kd].get(pn) or H0["recipe"][kd]["default"])))
    lt = lambda x: (f"glyph ×{1 + x['light_edge'] + x['light']:.2f} at the centre, ×{1 + x['light_edge']:.2f} at the edges; "
                    f"stone ×{1 + x['frame_light']:.2f} at the centre")
    pm = lambda n: (f"{e(name(n))} {pmae[n][0]:.1f} → {pmae[n][1]:.1f}" if n in pmae else "")
    med = lambda v: float(np.median(v)) if len(v) else float("nan")
    WR, SU, CR = ("action", "Weapon red"), ("spell", "Spell utility cyan"), ("action", "Control rose")

    # 1 + 3: the bright middle (Maiming Strike = Weapon red action, Dimension Door = Spell utility cyan spell)
    R1 = {k: rset(byp[k]) for k in (WR, SU)}
    RA = {kd: rset(sets[kd]) for kd in ("action", "spell")}
    note1 = (f'<h2 class=sec>1 and 3. The bright middle (Maiming Strike, Dimension Door)</h2><p class=secsub>Measured over every '
             f'icon of each colour, the game minus round 4 by distance from the centre: on actions the glow and line edges near '
             f'the centre were 3-9 L* too dark while the opaque cores were already a little too bright; on spells the lines were '
             f'3-10 L* too dark in the middle and 17-22 too bright in the corners; Weapon red\'s stone near the middle 12 L* too dark. '
             f'Round 4 had one light per kind (spells, actions), and its search (Nelder-Mead) barely moved it from where it started. '
             f'Now every colour fits its own light, its edge and the stone light, with a search (Powell) that tries each number at a '
             f'step of its own size. Spell utility cyan: round 4 {lt(rec_old(*SU))}; now {lt(rec_now(*SU))}: Dimension Door\'s '
             f'middle is brighter and its corners darker, like the game\'s; {pm("Spell_Conjuration_DimensionDoor")} (/255). '
             f'Maiming Strike is not fixed: Weapon red\'s fit kept nearly the same light (round 4 {lt(rec_old(*WR))}; now '
             f'{lt(rec_now(*WR))}), because a stronger one made the colour\'s other icons worse. The game is still about 4 L* '
             f'brighter on Weapon red lines in the middle, and Maiming Strike about 11, its dark axe drawn lighter on the PC '
             f'icon than in the controller art; {pm("Action_CripplingStrike")} (/255). The charts show what is left, 0 = '
             f'matched, positive = ours too dark.</p>{legend}<div class=charts>'
             + rchart("Weapon red actions: opaque lines", R1[WR], "lines") + rchart("Weapon red actions: bare stone", R1[WR], "frame")
             + rchart("Spell utility cyan spells: opaque lines", R1[SU], "lines") + rchart("All spells: opaque lines", RA["spell"], "lines")
             + rchart("All actions: opaque lines", RA["action"], "lines") + rchart("All actions: bare stone", RA["action"], "frame")
             + '</div>')

    # 2: Mantle of Inspiration's deeper red glow (Control rose action)
    grow = []
    for (kd, pn), ns in sorted(byp.items(), key=lambda x: -len(x[1])):
        if len(ns) < 8 or kd == "illithid":
            continue
        its = items(ns)
        g, b, o = (glow_colour(its, fn) for fn in (R_GAME, R_BEFORE, R_NOW))
        if not g:
            continue
        dh = lambda u: med([((x[0] - y[0] + 180) % 360) - 180 for x, y in zip(g, u)])
        x = rec_now(kd, pn)
        grow.append(f'<tr><td><span class=sw style="background:{swatch(pn)}"></span> {e(pn)}</td><td>{kd}</td>'
                    f'<td class=num>{sig(dh(b))}° → {sig(dh(o))}°</td><td class=num>{med([v[1] for v in g]):.0f}</td>'
                    f'<td class=num>{med([v[1] for v in b]):.0f} → {med([v[1] for v in o]):.0f}</td>'
                    f'<td class=num>×{x["glow_sat"]:.2f}, {sig(x["hue"])}°</td></tr>')
    xc = rec_now(*CR)
    note2 = (f'<h2 class=sec>2. A deeper red glow (Mantle of Inspiration)</h2><p class=secsub>Measured on the soft glow around the '
             f'lines: for most colours the game\'s glow is 20-45% more colourful than round 4\'s, while round 4\'s lines were '
             f'already a little too colourful, and some colours sit at another hue on the PC hotbar (Control rose actions about '
             f'7° redder; Mantle\'s pink was the controller art\'s hue). Round 4 had one colourfulness for the whole glyph and no '
             f'hue at all, and its fit never looked at hue. Now the glow has a colourfulness of its own, every colour can turn its '
             f'hue (PC only: the masters keep the art\'s), and the fit scores the colour of the lines and of the glow. Control rose '
             f'actions now: glow ×{xc["glow_sat"]:.2f} over the lines\' colourfulness, hue {sig(xc["hue"])}°. '
             f'{pm("Action_MantleOfInspiration")} (/255). Part of the pink is the frame: around Mantle the game\'s stone is nearly '
             f'grey (chroma 2.5) where the Control rose default, the pink frame, has 10; 44% of Control rose icons sit on another '
             f'frame in the game, which the app\'s Frame field picks (decision 1).</p>'
             + row(len(grow), "Glow colour by colour", "colours with 8+ icons on this page",
                   "Glow hue, the game minus ours (positive = the game\'s is further towards yellow), and glow colourfulness "
                   "(chroma), the game and ours; last column the fitted glow colourfulness and hue turn.",
                   '<table class=t><tr><th>Colour</th><th>Kind</th><th>Hue gap, round 4 → now</th><th>Game chroma</th>'
                   '<th>Our chroma, round 4 → now</th><th>Glow ×, hue</th></tr>' + "".join(grow) + '</table>'))

    # 4: light from the glyph (Divine Strike Radiant Ranged, Dazzling Breath = Radiant gold actions): small colours, bloom
    small = [(kd, pn, v) for kd in KINDS for pn, v in ev.get(f"styles/{kd}", {}).items() if v.get("small")]
    hold_mae = lambda kd, pn, rec: med([mae(glyph_over(Q(n), fr(n), rec), hot[n]) for n in sorted(hold) if usable(n)
                                        and kind(n) == kd and pre.get(n) == pn])
    srows = "".join(
        f'<tr><td><span class=sw style="background:{swatch(pn)}"></span> {e(pn)}</td><td>{kd}</td><td class=num>{v["n"]}</td>'
        f'<td class=num>{v["shared"]:.1f} → {v[v["pick"]]:.1f}</td>'
        f'<td class=num>{(lambda a, b: "n/a" if a != a else f"{a:.1f} → {b:.1f}")(hold_mae(kd, pn, X[kd]["default"]), hold_mae(kd, pn, X[kd][pn]))}</td>'
        f'<td class=num>×{1 + rec_now(kd, pn)["light_edge"] + rec_now(kd, pn)["light"]:.2f}</td>'
        f'<td class=num>{abs(rec_now(kd, pn)["bloom"]):.2f}</td></tr>' for kd, pn, v in small)
    xr = rec_now("action", "Radiant gold")
    note4 = (f'<h2 class=sec>4. Light from the glyph (Divine Strike Radiant Ranged, Dazzling Breath)</h2><p class=secsub>Both are '
             f'Radiant gold actions. That colour has 12 icons, under the 15 a colour needed for numbers of its own, so round 4 drew '
             f'it with the shared action recipe: a dark edge around the lines and a weak middle, where the game draws a strong '
             f'light (the game minus round 4: +17 L* on the glow at the centre) and lights the stone around the glyph in its '
             f'colour. Nineteen colours were in the same spot. Now colours with 5 to 14 icons fit 13 numbers of their own and keep '
             f'them only when the fit\'s score improves ({len(small)} kept them; on their test icons 12 of 13 got closer, the '
             f'table). Radiant gold now: {lt(xr)}, dark edge {abs(xr["halo"]):.2f} (shared {abs(rec_now("action", "")["halo"]):.2f}). '
             f'The lit stone comes from the stone light; a new bloom step (the glyph\'s glow colour, blurred, laid over the icon '
             f'like light) went unused ({abs(xr["bloom"]):.2f}), and the game\'s stone around the glyph stays a more saturated '
             f'gold than ours. {pm("Action_DivineStrike_Radiant_Ranged")}; {pm("Action_DragonForm_ScintillatingBreath")} (/255).</p>'
             + row(len(small), "Colours that now have their own numbers", "5 to 14 training icons",
                   "Mean difference per pixel (/255), the shared recipe → the colour\'s own: on its training icons (what the fit "
                   "saw) and its test icons (never seen; n/a = none); then its centre light and bloom.",
                   '<table class=t><tr><th>Colour</th><th>Kind</th><th>Icons</th><th>Training</th><th>Test</th>'
                   '<th>Centre light</th><th>Bloom</th></tr>' + srows + '</table>'))

    # 5: Mind Tax: illithid lines and veins
    ins = sets["illithid"]
    ci = {k: cross(items(ins), fn) for k, fn in (("game", R_GAME), ("before", R_BEFORE), ("now", R_NOW))}
    si = {k: stone_slope(items(ins), fn) for k, fn in (("game", R_GAME), ("before", R_BEFORE), ("now", R_NOW))}
    rr = list(reg.values())
    moved = sum(1 for r in rr if r[:3] != [1.0, 0.0, 0.0])
    zs = [r[0] for r in rr if r[0] != 1.0]
    note5 = (f'<h2 class=sec>5. Mind Tax: white cores and darker gaps between the veins</h2><p class=secsub>The game\'s PC '
             f'illithid icons are often the drawing enlarged (×{min(zs, default=1):.2f}-{max(zs, default=1):.2f}) or shifted by up '
             f'to a pixel ({moved} of the {len(rr)} cells used now). Round 4 left the 18 worst out and fitted the rest as they '
             f'were, and a fit on cells that do not line up prefers flat, blurred colour: that is the missing contrast you saw. '
             f'Now each cell is lined up with the drawing first: their brightness patterns match {med([r[3] for r in rr]):.2f} as '
             f'they are and {med([r[4] for r in rr]):.2f} lined up (1 = identical). {len(rr)} cells are used (round 4: 23), the '
             f'{len([n for n in odd if kind(n) == "illithid"])} that still do not match are left out, and the illithid recipe was '
             f'refit from scratch. Line middle minus line rim '
             f'(L*): game {med(ci["game"]):+.0f}, round 4 {med(ci["before"]):+.0f}, now {med(ci["now"]):+.0f}. Contrast of the '
             f'veins (1 = the vein file\'s own): game {med(si["game"]):.2f}, round 4 {med(si["before"]):.2f}, now '
             f'{med(si["now"]):.2f}. Mind Tax itself got the white cores (+28 against the game\'s +25) and a glow as dark as '
             f'the game\'s, but its glow is less red than the game\'s (chroma 39 against 43), so its difference per pixel rose: '
             f'{pm("Action_Mag_Illithid_MindTax")} (/255); the silver illithid powers went 16.0 → 13.5 on the same lined-up '
             f'cells. On this page illithid icons are drawn lined up like the game\'s cells so they compare fairly; the app draws '
             f'the master at its own size.</p>')

    # 6: where the time goes (user: "what exactly are you spending so much time on / training on?")
    trow = "".join(f'<tr><td>{e(a)}</td><td class=num>{e(b)}</td><td class=num>{e(c)}</td></tr>' for a, b, c in TIMES)
    note6 = (f'<h2 class=sec>Where the time goes</h2><p class=secsub>No model is being trained yet (that is Phase 6, after captions '
             f'and the base-model bake-off). The long runs are the hotbar fit: a search for the recipe\'s numbers (glow, dark edge, '
             f'light, colours, sharpening; about 25 per colour). Every try re-renders 100-190 training icons at 64 px and scores '
             f'them against the game\'s own cells on seven measures, about half a second per try, and a fit makes thousands of '
             f'tries. This round made that cheaper:</p><table class=t><tr><th>Step</th><th>Round 4</th><th>Round 5</th></tr>{trow}'
             f'</table>')

    # ---- decision 3 (decided 3A): crisp or soft per colour
    stl = {kd: ev.get(f"styles/{kd}", {}) for kd in KINDS}
    srow = "".join(f'<tr><td>{"<b>Shared recipe</b>" if pn == "default" else f"<span class=sw style=background:{swatch(pn)}></span> {e(pn)}"}'
                   f'</td><td>{kd}</td><td class=num>{v["n"]}</td>'
                   + "".join(f'<td class=num>{v[s]:.2f}</td>' if s in v else '<td class=num>n/a</td>' for s in ("crisp", "soft"))
                   + f'<td><b>{v["pick"]}</b></td></tr>'
                   for kd in KINDS for pn, v in stl[kd].items())
    ex3 = []
    for s in ("crisp", "soft"):
        ns = [n for kd in two for pn, v in stl[kd].items() if v["pick"] == s and pn != "default"
              for n in sets[kd] if pre.get(n) == pn][:4]
        ex3.append(f'<div class=cgroup><div class=chead><b>{"Crisp" if s == "crisp" else "Soft"}</b> colours, game next to ours</div>'
                   f'<div class=crow>' + "".join(f'<div class=strip2><div class=sname>{e(name(n))}</div>'
                                                + panel(img(to_img(hot[n]), 80, tip=n), "Game")
                                                + panel(img(to_img(now(n)), 80), f"Now · {mae(now(n), hot[n]):.1f}") + '</div>' for n in ns)
                   + '</div></div>')
    n3 = sum(v["n"] for kd in KINDS for pn, v in stl[kd].items() if pn != "default")
    d3 = decision(3, 5, DECIDED.get(3), n3, "Crisp or soft hotbar recipe, per colour?",
                  "Done as you chose: every colour with enough icons was fitted both ways, crisp (thin pale lines, a darken-only "
                  "sharpening rim) and soft (the glyph sharpened before it goes on the frame), and keeps the one closer to the "
                  "game per pixel on its training icons. Mean difference per pixel (/255):",
                  '<table class=t><tr><th>Colour</th><th>Kind</th><th>Icons</th><th>Crisp</th><th>Soft</th><th>Kept</th></tr>'
                  + srow + '</table>' + "".join(ex3),
                  [("A", "Per colour, whichever is closer", "Crisp where it wins, soft elsewhere."),
                   ("B", "Crisp everywhere", "Thin lines and a tight glow on every icon.")], unit="icons in fitted colours")

    # ---- decision 4 (decided A): illithid powers in v1, on the veins
    ill = [n for n in sorted(train | hold) if usable(n) and kind(n) == "illithid"]
    fil = H.get("frames_illithid", {})
    frows = "".join(f'<tr><td><span class=sw style="background:{swatch(p)}"></span> {e(p)}</td><td>'
                    + " &nbsp; ".join(f'<span class=fc>{fthumb(f)} {e(fname(f))}, {f[1]:.0%} brightness, closer for {f[2]:.0%}</span>' for f in fs)
                    + '</td></tr>' for p, fs in fil.items())
    grid4 = "".join(f'<div class=pair><div class=pname>{e(name(n))} · {mae(now(n), hot[n]):.1f}</div>'
                    f'{panel(img(to_img(hot[n]), 80, tip=n), "game")}{panel(img(to_img(now(n)), 80), "ours")}</div>' for n in ill)
    out4 = sorted(n for n in hot if (n.startswith("TadpoleSuperPower") or n in ILLITHID_ART) and (D / "masters" / f"{n}.png").exists()
                  and n in rows and not rows[n].get("numeral_badge") and n not in pre)
    big = [n for n in sorted(odd) if drawn(n)]
    grid4b = "".join(f'<div class=pair><div class=pname>{e(name(n))} · ×{odd[n][1]:g}</div>'
                     f'{panel(img(to_img(hot[n]), 80, tip=n), "game")}{panel(img(to_img(now(n)), 80), "ours")}</div>' for n in big)
    d4 = decision(4, 5, DECIDED.get(4), len(ill) + len(big), "Make illithid powers in v1?",
                  f"Done as you chose: the illithid powers joined the dataset (training and test sets), with their own kind on the "
                  f"PC hotbar: the vein background, as it is for the red powers and recoloured blue-grey for the silver ones (no such "
                  f"file exists in the game). Most are drawn in the game's existing colours (Force red, the silver basic-action "
                  f"white); five share a red of their own, now the colour Illithid red. Left out: {', '.join(name(n) for n in out4) or 'none'} "
                  f"(no colour preset fits them). The game's PC illithid cells often enlarge or shift the drawing; since round 5 "
                  f"each is lined up with the drawing before fitting ({len(reg)} used, note 5) and the {len(big)} that still do "
                  f"not match are left out of fitting and the test numbers (last row). Ours keeps the size of the drawing it is "
                  f"given; on this page illithid icons are drawn lined up like the game's cells.",
                  f'<table class=t><tr><th>Colour</th><th>Vein background (default first)</th></tr>{frows}</table>'
                  f'<div class=grid>{grid4}</div>'
                  + (row(len(big), "Not the same drawing on the PC hotbar", "left out of fitting",
                         "The game's PC icon next to ours; the number is the enlargement that lines them up best, which still "
                         "leaves them too far apart to fit on.", f'<div class=grid>{grid4b}</div>') if big else ""),
                  [("A", "Yes, in v1", "Illithid powers can be made from day one."),
                   ("B", "Later", "Wait for the passives phase.")], unit="illithid icons")

    # ---- earlier decisions, kept for reference: 1 = D19 Frame field, 2 = D20 recoloured frames
    rec = [(p, f) for p, f in H["frames"].items() if f[0][3] is not None]
    rows2 = []
    for p, f in rec:
        ns = [n for n in sorted(train | hold) if usable(n) and kind(n) == "action" and pre.get(n) == p][:3]
        rows2.append(f'<div class=cgroup><div class=chead><span class=sw style="background:{swatch(p)}"></span><b>{e(p)}</b> '
                     f'{e(LOOK.get(f[0][0], f[0][0]))} frame recoloured to the glyph</div><div class=crow>'
                     + "".join(f'<div class=strip2><div class=sname>{e(name(n))}</div>' + panel(img(to_img(hot[n]), 80, tip=n), "Game")
                               + panel(img(to_img(now(n)), 80), "Ours") + '</div>' for n in ns) + '</div></div>')
    wdef = frame(H, "Action", "Weapon red")
    d1 = decision(1, 5, DECIDED.get(1), sum(1 for n in train | hold if n in pre and kind(n) == "action"),
                  "Should action icons get a Frame field, pre-filled from the colour?",
                  f"The app fills the frame in from the colour and lets you change it; Weapon red goes on the "
                  f"{fname(wdef)} frame.", "", [("A", "Frame field, pre-filled from the colour", "One click to change it."),
                                                ("B", "No frame field", "The colour decides.")], unit="action icons")
    d2 = decision(2, 5, DECIDED.get(2), sum(1 for n in train | hold if pre.get(n) in dict(rec) and kind(n) == "action"),
                  "When no frame matches the colour, recolour one?",
                  f"For {len(rec)} colours ({', '.join(p for p, _ in rec)}) the game draws a frame none of its backgrounds has; a "
                  f"framed background recoloured to the glyph comes closest.", "".join(rows2),
                  [("A", "Recoloured frame for these colours", "Closest to the game; code applied to the game's own backgrounds."),
                   ("B", "Closest real frame only", "Frames stay exactly the game's files.")], unit="game icons")

    # ---- how "ours" is made: the steps, one action and one spell
    ex2 = [n for n in STEP_EX if usable(n)]
    st = {n: parts(Q(n), fr(n), rx(n)) for n in ex2}
    ra, rs = dict(zip(KEYS, padded(rx(ex2[0])))), dict(zip(KEYS, padded(rx(ex2[-1]))))
    lc = lambda x: (f"contrast ×{x['line_contrast']:.2f}, colourfulness ×{x['line_sat']:.2f} (glow ×{x['glow_sat']:.2f} more), "
                    f"{'+' if x['line_lift'] >= 0 else '−'}{abs(x['line_lift']) * 100:.0f}% brightness, hue {sig(x['hue'])}°")
    sty = lambda n: (H.get("recipe_style", {}).get(kind(n), {}).get(pre.get(n, "")) or
                     H.get("recipe_style", {}).get(kind(n), {}).get("default", "crisp"))
    steps = [
        ("1. Master", lambda n: img(Image.open(D / "masters" / f"{n}.png").convert("RGBA").resize((128, 128), Image.LANCZOS), 128, "ck"),
         "Our full-size transparent glyph (512 px) on a checkerboard: here the game's own art, so every difference below comes "
         "from the recipe. In the app it will be the model's grey glyph after colouring (D18)."),
        ("2. Shrink to 64 px", lambda n: img(straight(Q(n)), 128, "px ck"),
         "Lanczos downscale on colour multiplied by opacity, so soft glow edges don't go dark."),
        ("3. Thin the glow, line colours, glyph light", lambda n: img(straight(st[n]["glyph"]), 128, "px ck"),
         f"Glow opacity raised to the power {ra['glow_thin']:.2f} (action), {rs['glow_thin']:.2f} (spell); line colours: "
         f"action {lc(ra)}; spell {lc(rs)}; the glyph's light: centre ×{1 + ra['light_edge'] + ra['light']:.2f}, edges "
         f"×{1 + ra['light_edge']:.2f} (action), centre ×{1 + rs['light_edge'] + rs['light']:.2f}, edges "
         f"×{1 + rs['light_edge']:.2f} (spell). Soft colours also sharpen the glyph here."),
        ("4. Frame", lambda n: img(to_img(fr(n) * rx(n)[0]), 128),
         f"Actions: the framed background the colour picks ({pre.get(ex2[0], '?')}: {fname(fk(ex2[0]))}), shrunk whole and "
         f"darkened. Spells: the brown stone. Illithid powers: the veins."),
        ("5. Stone light, tint and dark edge", lambda n: img(to_img(st[n]["shaded"]), 128),
         f"The light on the stone (centre ×{1 + ra['frame_light']:.2f} action, ×{1 + rs['frame_light']:.2f} spell); inside "
         f"closed shapes a {abs(ra['fill']):.0%} tint of the glyph's colour; a dark edge grown from the line cores."),
        ("6. Glyph on top, bloom", lambda n: img(to_img(st[n]["flat"]), 128),
         f"The glyph over the prepared frame; its glow covers the stone by opacity to the power {abs(ra['cover']):.2f} "
         f"(action), {abs(rs['cover']):.2f} (spell). Then the bloom: the glyph's glow colour, blurred, laid over the icon like "
         f"light ({abs(ra['bloom']):.2f} action, {abs(rs['bloom']):.2f} spell)."),
        ("7. Sharpen = ours", lambda n: img(to_img(st[n]["out"]), 128),
         f"Crisp colours: darken-only sharpening around the glyph (a crisp dark rim). These two are {sty(ex2[0])} "
         f"and {sty(ex2[-1])}. This is the icon the exporter writes."),
        ("8. Game", lambda n: img(to_img(hot[n]), 128, tip=n), "The game's own hotbar icon."),
        ("9. Difference ×3", lambda n: img(to_img(np.abs(st[n]["out"] - hot[n]) * 3), 128),
         f"|ours − game| × 3, black = identical: {mae(st[ex2[0]]['out'], hot[ex2[0]]):.1f} and "
         f"{mae(st[ex2[-1]]['out'], hot[ex2[-1]]):.1f} out of 255."),
    ]
    steps_html = (f'<table class="t steps"><tr><th>Step</th>' + "".join(f'<th>{e(name(n))}<br><span class=mu>{kind(n)}</span></th>' for n in ex2)
                  + '<th>What happens</th></tr>'
                  + "".join(f'<tr><td class=stp>{e(s)}</td>' + "".join(f'<td>{f(n)}</td>' for n in ex2) + f'<td>{e(t)}</td></tr>'
                            for s, f, t in steps) + '</table>')
    def before_test(kd):
        """round 4's test number, flagged when its test set differs (illithid: 1 icon, not lined up, round 4)"""
        h = H0["eval"].get(f"holdout/{kd}")
        if not h:
            return "n/a"
        return str(h["mae"]) if h["n"] == ev[f"holdout/{kd}"]["n"] else f'{h["mae"]} ({h["n"]} icon{"s" if h["n"] > 1 else ""}, other set)'
    mrow = "".join(f'<tr><td>{kname[kd]}</td><td class=num>{ev[f"holdout/{kd}"]["n"]}</td><td class=num>{ev[f"holdout/{kd}"]["mae"]}</td>'
                   f'<td class=num>{ev[f"holdout/{kd}"]["default_only"]}</td><td class=num>{ev[f"holdout/{kd}"]["plain_over"]}</td>'
                   f'<td class=num>{before_test(kd)}</td></tr>' for kd in KINDS if f"holdout/{kd}" in ev)
    own = [(kd, pn, dict(zip(KEYS, padded(v)))) for kd in KINDS for pn, v in X[kd].items() if pn != "default"]
    ptab = ('<table class=t><tr><th>Test icons</th><th>Icons</th><th>Mean difference /255</th><th>Shared recipe only</th>'
            f'<th>Plain overlay</th><th>Round 4</th></tr>{mrow}</table>'
            + row(len(own), "Colours with their own numbers", "the shared recipe for the rest",
                  f"Every colour with at least {MIN_PRESET} training icons of a kind refits its frame brightness, dark edge, glow, "
                  f"sharpening, tint, glow cover, lights, line and glow colours, hue and bloom on its own icons, in the style it "
                  f"kept (decision 3); colours with {MIN_SMALL} to {MIN_PRESET - 1} fit fewer numbers and keep them only when "
                  f"they help (note 4).",
                  '<table class=t><tr><th>Colour</th><th>Kind</th><th>Style</th><th>Frame</th><th>Dark edge</th><th>Glow kept</th>'
                  '<th>Glow cover</th><th>Light</th><th>Line colourfulness</th><th>Glow ×</th><th>Hue</th><th>Bloom</th></tr>'
                  + "".join(f'<tr><td><span class=sw style="background:{swatch(pn)}"></span> {e(pn)}</td><td>{kd}</td>'
                            f'<td>{H.get("recipe_style", {}).get(kd, {}).get(pn, "")}</td><td class=num>{v["bg_gain"]:.2f}</td>'
                            f'<td class=num>{v["halo"]:.2f}</td><td class=num>{min(max(v["glow_kept"], 0), 1):.0%}</td>'
                            f'<td class=num>{abs(v["cover"]):.2f}</td><td class=num>×{1 + v["light_edge"] + v["light"]:.2f}</td>'
                            f'<td class=num>×{v["line_sat"]:.2f}</td><td class=num>×{v["glow_sat"]:.2f}</td>'
                            f'<td class=num>{sig(v["hue"])}°</td><td class=num>{abs(v["bloom"]):.2f}</td></tr>'
                            for kd, pn, v in own) + '</table>'))
    ours = (f'<h2 class=sec>How "ours" is made</h2><p class=secsub>The same code the exporter will run (<code>hotbar.compose</code>). '
            f'Left an action, right a spell, both from the test set.</p>{steps_html}<p class=secsub>In one line:</p>'
            f'<div class=formula>icon = sharpen( bloom over ( (frame × stone light × (1 − tint) + colour × tint) × (1 − dark '
            f'edge) × (1 − glow opacity<sup>cover</sup>) + glyph in its line and glow colours, hue turned × glyph light × glow '
            f'kept ) ), glow thinned first</div>{ptab}'
            f'<p class=secsub>Every number was fitted to bring our rebuild close to the game\'s icons (difference per pixel, the '
            f'brightness next to the lines, edge crispness, the mix of pale core / glow / stone, the stone showing through '
            f'the glow, the colour of lines and glow) on the {ev["train/action"]["n"]} training actions, {ev["train/spell"]["n"]} spells and '
            f'{ev.get("train/illithid", {}).get("n", 0)} illithid powers; test icons were never used for fitting.</p>')

    # ---- reference rows: every test icon; every preset's frame
    hs = [n for n in sorted(hold) if usable(n)]
    pairs = "".join(f'<div class=pair><div class=pname>{e(name(n))} · {mae(o, hot[n]):.1f}</div>'
                    f'{panel(img(to_img(hot[n]), 80, tip=n), "game")}{panel(img(to_img(o), 80), "ours")}</div>'
                    for n in hs for o in [now(n)])
    ptr = []
    for p in G["presets"]:
        fs = H["frames"].get(p["name"])
        cell = (" &nbsp; ".join(f'<span class=fc>{img(to_img(frame_img(B, f)), 28, cls="px th")} {e(fname(f))}, '
                                f'{f[1]:.0%} brightness, {f[2]:.0%} of its actions</span>' for f in fs) if fs
                else f'borrows the frames of {e(H["nearest"][p["name"]])} (no action icons in this colour)')
        ptr.append(f'<tr><td><span class=sw style="background:{swatch(p["name"])}"></span> {e(p["name"])}</td><td>{cell}</td></tr>')
    notes = "".join([
        row(len(hs), "Test icons: game next to ours", "for checking",
            "Every test-set icon, the game's hotbar icon left, our rebuild right, with the mean difference (/255).",
            f'<div class=grid>{pairs}</div>'),
        row(len(G["presets"]), "Colour presets and the frame each one pre-fills", "D19, D20",
            "The framed background the game uses for each colour's action icons, recoloured where none matches; colours "
            "with no action icons borrow the closest colour's frames. Illithid powers: decision 4.",
            f'<table class=t><tr><th>Colour</th><th>Frame (default first)</th></tr>{"".join(ptr)}</table>')])
    # ---- decision 5 (round 5): next step
    ex5 = "".join(f'<div class=pair><div class=pname>{e(name(n))} · {pmae[n][0]:.1f} → {pmae[n][1]:.1f}</div>'
                  f'{panel(img(to_img(hot[n]), 80, tip=n), "game")}{panel(img(to_img(now(n)), 80), "now")}</div>' for n in pmae)
    d5 = decision(5, 5, DECIDED.get(5), len(pmae), "Next: move on to the glyph, or another hotbar round?",
                  f"Five rounds in, your six icons are closer again (round 4 → now, /255, above each pair). The glyph is the "
                  f"product and the PC background is secondary (your priority, ModernUI plays it down), so A moves on to 2.4, "
                  f"the glyph's structure (white cores, dark fills, stroke width), which the model's training builds on. Known "
                  f"gaps stay listed in the plan: {GAPS} Notes on this page can still go into a later hotbar round.",
                  f'<div class=grid>{ex5}</div>',
                  [("A", "Move on to the glyph (2.4)", "The hotbar recipe stays as it is; small notes are still welcome."),
                   ("B", "One more hotbar round", "On your notes from this page, before 2.4.")], unit="of your icons")
    lede, reply = lede_reply(DECIDED, 5)
    earlier = row(4, "Decisions 1 to 4", "decided", "Made (your 1A, 2A, 3A and 4A), kept for reference.", d3 + d4 + d1 + d2)
    body = (f'<style>{CSS}</style><p class=lede>Phase 2.2, round 5: your notes on the round-4 page (the bright middle, a '
            f'deeper red glow, light from the glyph, Mind Tax\'s contrast) and where the time goes. {lede}</p>{d5}{reply}'
            f'{pairs_sec}{note1}{note2}{note4}{note5}{note6}<h2 class=sec>Earlier decisions</h2>{earlier}'
            f'{ours}<h2 class=sec>Reference</h2><p class=secsub>Click a row to open it.</p>{notes}<script>{JS}</script>')
    (D / "hotbar.html").write_text(page("Hotbar icons", body), encoding="utf-8")
    log(f"[2.2] wrote {D / 'hotbar.html'}")


CSS = """
.px{image-rendering:pixelated;border-radius:6px;display:block}.px.th{display:inline-block;vertical-align:middle;border-radius:4px}
.ck{background:repeating-conic-gradient(#45484f 0 25%,#62656d 0 50%) 0 0/12px 12px;border-radius:6px;display:block}
.panel{display:flex;flex-direction:column;gap:4px;width:min-content}.panel>span{font-size:12px;line-height:1.3;color:var(--mute)}
.strip{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:0 0 14px}
.strip2{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start;padding-right:14px;border-right:1px dashed var(--line)}.strip2:last-child{border:0}
.sname{width:100%;font-size:14px;color:var(--ink)}.sname span{color:var(--mute)}
.zw{position:relative;display:block}.zb{position:absolute;border:2px solid var(--accent);border-radius:3px;pointer-events:none}
.sep{width:1px;align-self:stretch;background:var(--line);margin:0 4px}
.legend{display:flex;flex-wrap:wrap;gap:18px;font-size:13px;color:var(--soft);margin:6px 0 8px}
.legend i{display:inline-block;width:16px;height:2px;border-radius:1px;vertical-align:middle;margin-right:6px}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.cw{position:relative;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.ct{font-size:14px;color:var(--ink);margin-bottom:4px}
svg.chart{width:100%;height:auto;display:block;outline:none}svg.chart:focus-visible{outline:2px solid var(--link);border-radius:6px}
svg .gl{stroke:#2f333b;stroke-width:1}svg .gl.z{stroke:#5a606b}svg .yt,svg .xt,svg .xl{fill:#8d929b;font-size:11px}svg .yt{text-anchor:end}
svg .xt,svg .xl{text-anchor:middle}svg .xl{font-size:12px}
svg .ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}svg .dot{stroke:#1d2026;stroke-width:2}
svg .cross{stroke:#8d929b;stroke-width:1;opacity:0}
.tip{position:absolute;top:30px;pointer-events:none;opacity:0;background:var(--card2);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12px;min-width:140px}
.tip .th{color:var(--mute);margin-bottom:2px}.tip .tr{display:flex;gap:8px;align-items:center;color:var(--soft)}
.tip .tk{width:12px;height:2px;border-radius:1px}.tip b{color:var(--ink);min-width:32px;text-align:right}
h3.tt3{font-size:14px;margin:12px 0 0;color:var(--soft)}
.mocks{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}
.mock{background:#181b20;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.mtag{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin-bottom:10px}
.mrow{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap}
.form{flex:1;min-width:220px;display:grid;grid-template-columns:52px 1fr;gap:8px 10px;align-items:center;font-size:14px}
.form label{color:var(--mute);font-size:13px}
.sel{display:flex;align-items:center;gap:8px;background:#14161a;border:1px solid #3a3f48;border-radius:8px;padding:5px 8px}
.sel .caret{margin-left:auto;color:var(--mute)}
.auto{font-size:11px;color:var(--rec);border:1px solid var(--rec);border-radius:999px;padding:0 6px;white-space:nowrap}
.menu{grid-column:2;list-style:none;margin:-4px 0 0;padding:4px;background:#14161a;border:1px solid #3a3f48;border-radius:8px}
.menu li{display:flex;align-items:center;gap:8px;padding:4px 6px;border-radius:6px;font-size:13px}
.menu li.on{background:var(--card2)}.menu small{margin-left:auto;color:var(--mute);white-space:nowrap}.menu li.all{color:var(--link)}
.fixed{color:var(--soft);font-size:13px}
.prev{display:flex;flex-direction:column;align-items:center;gap:4px;font-size:12px;color:var(--mute)}
.why{font-size:12px;color:var(--mute);margin:10px 0 0}
.formula{font-family:Consolas,monospace;font-size:14px;background:var(--card2);border-radius:8px;padding:8px 12px;display:inline-block;margin:0 0 12px}
table.steps td{vertical-align:top}table.steps td.stp{font-weight:600;white-space:nowrap}.mu{color:var(--mute);font-weight:400;font-size:12px}
.fc{white-space:nowrap;display:inline-flex;align-items:center;gap:6px}
.pair figure,.pair .panel{width:auto}
"""

JS = """
document.querySelectorAll('svg.chart').forEach(svg => {
  const d = JSON.parse(svg.dataset.d), W = Number(svg.dataset.w);
  const tip = svg.parentNode.querySelector('.tip'), cross = svg.querySelector('.cross');
  let cur = 0;
  const show = i => {
    cur = i;
    cross.setAttribute('x1', d.px[i]); cross.setAttribute('x2', d.px[i]); cross.style.opacity = 1;
    tip.replaceChildren();
    const h = document.createElement('div'); h.className = 'th'; h.textContent = d.h[i]; tip.append(h);
    d.s.forEach(([lab, c, ys]) => {
      const r = document.createElement('div'); r.className = 'tr';
      const k = document.createElement('span'); k.className = 'tk'; k.style.background = c;
      const v = document.createElement('b'); v.textContent = ys[i];
      const n = document.createElement('span'); n.textContent = lab;
      r.append(k, v, n); tip.append(r);
    });
    const r = svg.getBoundingClientRect(), px = d.px[i] * r.width / W;
    tip.style.left = Math.max(8, Math.min(px + 14, r.width - 180)) + 'px'; tip.style.opacity = 1;
  };
  svg.addEventListener('pointermove', ev => {
    const r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) * W / r.width;
    let i = 0;
    d.px.forEach((v, j) => { if (Math.abs(v - x) < Math.abs(d.px[i] - x)) i = j; });
    show(i);
  });
  const hide = () => { cross.style.opacity = 0; tip.style.opacity = 0; };
  svg.addEventListener('pointerleave', hide); svg.addEventListener('blur', hide);
  svg.addEventListener('focus', () => show(cur));
  svg.addEventListener('keydown', ev => {
    if (ev.key === 'ArrowLeft') show(Math.max(0, cur - 1));
    else if (ev.key === 'ArrowRight') show(Math.min(d.px.length - 1, cur + 1));
  });
});
"""


def check():
    """self-check of the closed-shape and region logic on a drawn ring and a bar (python -m iconkit.hotbar check)"""
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((96, 96, 352, 352), outline=(255, 200, 80, 255), width=24)            # ring: its inside is a closed shape
    d.rectangle((400, 40, 424, 470), fill=(255, 200, 80, 255))                       # bar: open space on both sides
    q = down(im)
    reg = regions(q)
    assert q[28, 28, 4] > .9 and q[5, 5, 4] == 0 and q[32, 58, 4] == 0, "closed-shape channel"
    assert reg["closed"][28, 28] and reg["open"][5, 5] and not reg["closed"][32, 58], "regions"
    H = {"recipe": {"action": {"default": PLAIN, "Weapon red": START["action"]}}}
    assert recipe_for(H, "Action", "Weapon red") == START["action"] and recipe_for(H, "Skill", "Other") == PLAIN
    F = {"frames": {"X": [["control", 1, 1, None]]}, "nearest": {}, "frame_two_tone": [["metaMagic", 1, 1, None]]}
    assert frame(F, "Skill", "X", "Y")[0] == "metaMagic" and frame(F, "Skill", "X")[0] == "control", "two-colour frame (D26)"
    out = glyph_over(q, np.full((S, S, 3), .3), START["action"])
    assert out.shape == (S, S, 3) and out[28, 28].mean() > .3, "closed shape tinted brighter than the frame"
    log("[2.2] check passed: closed shapes, regions, recipe_for, tint")


if __name__ == "__main__":
    {"fit": fit, "report": report, "check": check}[sys.argv[1] if len(sys.argv) > 1 else "fit"]()
