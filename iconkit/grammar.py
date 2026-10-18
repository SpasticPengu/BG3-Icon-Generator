"""Phase 2.1 colour grammar. Every vanilla icon is a monochrome glyph run through one colour preset, a gradient map
(a pixel's colour is a function of its lightness: 0.55 dE2000 median residual). Presets are found by clustering
per-icon colour curves of data/train.txt; each kind of icon (intent / damage type) maps to its usual preset;
scored on data/holdout.txt. detint()/tint() move a glyph between presets.
    python -m iconkit.grammar [report]   -> data/grammar.json + data/grammar.html (review page)
    python -m iconkit.grammar fit        -> data/grammar.json only (~2 min)
    python -m iconkit.grammar features   -> data/colour_features.json (~1 min; cached, redone when a master is newer)"""
import json, re, sys, warnings
from collections import Counter
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial.distance import squareform
from .lab import rgb2lab, lab2rgb, deltaE_ciede2000
from .extract import D, ILLITHID_ART, SPELL_LIKE, TWO_TONE, read_jsonl, log

warnings.filterwarnings("ignore", message=".*negative Z values.*")     # lab2rgb clips out-of-gamut colours: fine here
NB = 20                                          # lightness bins of a colour curve (5 L* each)
LC = (np.arange(NB) + .5) * 100 / NB             # bin centres
Q = np.linspace(0, 1, 201)                       # grey-level grid of de-tint / re-tint
T_PRESET = 3.0                                   # CIEDE2000, average linkage: icons closer than this share a preset
MODE_SHARE = .12                                 # a group's alternative presets need this share


def hsv(rgb):
    """Vectorised RGB (N,3 in 0..1) -> H degrees, S, V."""
    mx, mn = rgb.max(1), rgb.min(1)
    c = mx - mn
    r, g, b = rgb.T
    safe = np.where(c > 0, c, 1)
    h = np.where(mx == r, (g - b) / safe % 6, np.where(mx == g, (b - r) / safe + 2, (r - g) / safe + 4)) * 60
    return np.where(c > 0, h, 0), np.where(mx > 0, c / np.where(mx > 0, mx, 1), 0), mx


def circ_mean(h, w):
    t = np.deg2rad(h)
    return float(np.rad2deg(np.arctan2((np.sin(t) * w).sum(), (np.cos(t) * w).sum())) % 360)


hdist = lambda a, b: abs((a - b + 180) % 360 - 180)


def icon_features(path):
    """Glow = saturated, lit pixels (hue carrier); core = near-white lit pixels; dark = opaque but unlit.
    curve = mean (a*, b*) per lightness bin of the opaque pixels (the icon's gradient map); lhist = lightness histogram."""
    a = np.asarray(Image.open(path).convert("RGBA").resize((256, 256), Image.BOX)).reshape(-1, 4).astype(np.float32) / 255
    a = a[a[:, 3] > .1]
    if len(a) < 50:
        return None
    h, s, v = hsv(a[:, :3])
    w = a[:, 3]
    glow, core, dark, lit, op = (s > .35) & (v > .35), (s < .2) & (v > .8), v < .3, v > .35, w > .3
    tot = w.sum()
    lab = rgb2lab(a[:, :3])
    L, idx = lab[op, 0], np.clip((lab[op, 0] / 100 * NB).astype(int), 0, NB - 1)
    f = {"cover": float(len(a)) / 65536, "glow": float(w[glow].sum() / tot), "core": float(w[core].sum() / tot),
         "dark": float(w[dark].sum() / tot), "hue": None,
         "lab": (lab[lit].T @ w[lit] / w[lit].sum()).round(2).tolist() if w[lit].sum() > 30 else None,
         "curve": [lab[op][idx == i, 1:].mean(0).round(2).tolist() if (idx == i).sum() >= 8 else None for i in range(NB)],
         "lhist": np.histogram(L, bins=50, range=(0, 100))[0].tolist()}
    if w[glow].sum() > 30:                                                        # >= ~30 opaque glow pixels at 256 px
        hg, wg = h[glow], (w * s * v)[glow]
        hist, _ = np.histogram(hg, bins=72, range=(0, 360), weights=wg)
        hist = np.convolve(np.r_[hist[-2:], hist, hist[:2]], np.ones(5) / 5, "valid")  # 25 deg circular smoothing
        peak = int(hist.argmax()) * 5 + 2.5
        near = hdist(hg, peak) < 30
        f["hue"] = circ_mean(hg[near], wg[near])
        f["peak_share"] = float(wg[near].sum() / wg.sum())                     # how single-hued the glow is
        far = hdist(hg, peak) >= 45
        f["hue2"] = circ_mean(hg[far], wg[far]) if wg[far].sum() > .25 * wg[near].sum() else None
        f["sat"] = float(np.average(s[glow], weights=w[glow]))
        f["val"] = float(np.average(v[glow], weights=w[glow]))
    return f


def features():
    cache = D / "colour_features.json"
    rows = [r for r in read_jsonl(D / "meta.jsonl") if r["family"] in SPELL_LIKE and (D / "masters" / f"{r['icon']}.png").exists()]
    newest = max((D / "masters" / f"{r['icon']}.png").stat().st_mtime for r in rows)
    if cache.exists() and cache.stat().st_mtime > newest:
        out = json.loads(cache.read_text(encoding="utf-8"))
        if len(out) == len(rows) and all(v is None or "curve" in v for v in out.values()):
            return out
    out = {}
    for i, r in enumerate(rows):
        out[r["icon"]] = icon_features(D / "masters" / f"{r['icon']}.png")
        if i % 200 == 0:
            log(f"    colour features {i}/{len(rows)}")
    cache.write_text(json.dumps(out), encoding="utf-8")
    log(f"[2.1] colour features: {len(out)} icons, {sum(v is not None and v['hue'] is not None for v in out.values())} with a glow hue")
    return out


# ---------------------------------------------------------------- presets (gradient maps)
kind = lambda r: {"Spell": "Spell", "TadpoleSuperPower": "Illithid"}.get(r["family"], "Action")  # Skill_ = actions


def keys(r):
    """Most specific first. Damage colour follows the damage type, whatever the family; otherwise kind x intent.
    Illithid powers keep their own colours whatever the damage (Mind Blast is red, not psychic pink)."""
    i, d = r["VerbalIntent"], r["DamageType"]
    if kind(r) == "Illithid":
        return ([f"Illithid/{i}"] if i else []) + ["Illithid"]
    if i == "Damage" and d:
        return [f"damage/{d}"]
    return [f"{kind(r)}/{i}", f"intent/{i}"] if i else []


def curve_arr(c):
    return np.array([[np.nan, np.nan] if b is None else b for b in c], float)


def to_lab(ab):
    """(..., NB, 2) a*b* per bin -> (..., NB, 3) Lab with the bin-centre lightness"""
    return np.concatenate([np.broadcast_to(LC[:, None], ab.shape[:-1] + (1,)), ab], -1)


def curve_dist(c, cs):
    """Median CIEDE2000 over the lightness bins two curves share: c (NB,2) vs cs (M,NB,2) -> (M,). < 4 shared bins = 50."""
    a, b = np.broadcast_arrays(c[None], cs)
    ok = ~np.isnan(a[..., 0]) & ~np.isnan(b[..., 0])
    d = np.where(ok, deltaE_ciede2000(to_lab(np.nan_to_num(a)), to_lab(np.nan_to_num(b))), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(d, 1)
    return np.where(ok.sum(1) >= 4, med, 50.0)


has_curve = lambda f: bool(f and f["curve"] and sum(b is not None for b in f["curve"]) >= 4)


def fit_presets(names, F):
    """Average-linkage clusters of icon curves; clusters of >= 3 icons are presets: median curve + lightness quantiles."""
    names = [n for n in names if has_curve(F.get(n))]
    C = np.stack([curve_arr(F[n]["curve"]) for n in names])
    Dm = np.stack([curve_dist(C[i], C) for i in range(len(names))])
    Dm = (Dm + Dm.T) / 2
    np.fill_diagonal(Dm, 0)
    lab = fcluster(linkage(squareform(Dm, checks=False), "average"), T_PRESET, "distance")
    P = []
    for c, m in Counter(lab).most_common():
        if m < 3:
            break
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            cv = np.nanmedian(C[lab == c], 0)
        ok = ~np.isnan(cv[:, 0])
        P.append({"curve": np.stack([np.interp(LC, LC[ok], cv[ok, j]) for j in range(2)], 1).round(2).tolist(),
                  "span": [float(LC[ok][0]), float(LC[ok][-1])], **fit_lut(list(np.array(names)[lab == c]))})
    return P


# Tint table: a*b* over lightness x opacity x distance from the centre. Opacity separates the emitted glow from the
# lines (Legendary: gold lines, orange glow); distance gives radial hotspots (End-game ally: yellow centre, pink rim).
AC, RC = np.array([.1, .35, .7, .95]), np.array([.125, .375, .625, .875])     # cell centres
S_LUT = 128
radius =lambda h, w: np.hypot(*np.mgrid[:h, :w][::-1] - np.array([(w - 1) / 2, (h - 1) / 2])[:, None, None]) / (w / 2)


def fit_lut(members):
    """Pixels with alpha > .02 (glow included) of up to 60 members -> lq (lightness at grey levels Q) and lut
    (NB x 4 x 4 x a*b*); cells with < 20 px take the lightness-only mean."""
    s, c, Ls = np.zeros((NB, 4, 4, 2)), np.zeros((NB, 4, 4)), []
    R = radius(S_LUT, S_LUT)
    for n in members[:60]:
        x = load(n, S_LUT)
        m = x[..., 3] > .02
        lab = rgb2lab(x[..., :3])[m]
        idx = (np.clip((lab[:, 0] / 100 * NB).astype(int), 0, NB - 1), np.digitize(x[..., 3][m], [.2, .5, .85]),
               np.minimum((R[m] * 4).astype(int), 3))
        np.add.at(s, idx, lab[:, 1:])
        np.add.at(c, idx, 1)
        Ls.append(lab[:, 0])
    s1, c1 = s.sum((1, 2)), c.sum((1, 2))
    ok = c1 > 0
    f1 = np.stack([np.interp(LC, LC[ok], s1[ok, j] / c1[ok]) for j in range(2)], 1)
    lut = np.where(c[..., None] >= 20, s / np.maximum(c, 1)[..., None], f1[:, None, None, :])
    return {"lq": np.quantile(np.concatenate(Ls), Q).round(2).tolist(), "lut": lut.round(2).tolist()}


# Colour words are read off the rendered ramps (2026-10-14); the key is the preset's most common icon group.
NAMES = {"Spell/Summon": "Summon amber", "Action/Summon": "Summon amber", "damage/Bludgeoning": "Bludgeoning amber",
         "Spell/Buff": "Buff gold", "Action/Buff": "Buff gold", "damage/Weapon": "Weapon red",
         "Spell/Utility": "Spell utility cyan", "Action/Utility": "Action utility steel", "Spell/Control": "Control rose",
         "Action/Control": "Control rose", "Spell/Debuff": "Debuff magenta", "Action/Debuff": "Debuff magenta",
         "damage/Fire": "Fire orange", "damage/Cold": "Cold blue", "damage/Lightning": "Lightning blue",
         "damage/Thunder": "Thunder violet", "damage/Radiant": "Radiant gold", "damage/Psychic": "Psychic pink",
         "damage/Acid": "Acid yellow", "damage/Necrotic": "Necrotic green", "damage/Poison": "Poison lime",
         "damage/Force": "Force red", "damage/Piercing": "Piercing red", "damage/Slashing": "Slashing red",
         "Spell/Healing": "Spell healing turquoise", "Action/Healing": "Action healing green"}
FAMILIES = {"Mag": "Magic item", "Glut": "Glut spores", "Sorcerer": "Metamagic", "EndGameAlly": "End-game ally"}
HUES = [(15, "red"), (40, "orange"), (65, "gold"), (95, "lime"), (160, "green"), (200, "cyan"), (250, "blue"),
        (280, "violet"), (330, "magenta"), (345, "pink"), (361, "red")]
gkey = lambda r: (keys(r) or ["none"])[0]


def colour_word(p):
    """'white' when the gradient is near-grey (median chroma < 10), else the hue name at mid lightness"""
    lab = preset_lab(p, np.linspace(*p["span"], 9))
    if np.median(np.hypot(lab[:, 1], lab[:, 2])) < 10:
        return "white"
    h = hsv(np.clip(lab2rgb(preset_lab(p, 60)[None, None]), 0, 1)[0])[0][0]
    return next(nm for lim, nm in HUES if h < lim)


def name_presets(P, rows, A):
    """Grey gradients = basic actions; one Action family owning half a preset names it (Wild Magic, Magic item);
    otherwise its most common group does. Illithid powers only name a preset of their own ("Illithid <colour>")."""
    used = Counter()
    for i, p in enumerate(P):
        mem = [n for n, (j, d) in A.items() if j == i]
        named = [n for n in mem if kind(rows[n]) != "Illithid" and n not in ILLITHID_ART] or mem
        g = Counter(gkey(rows[n]) for n in named)
        fam = Counter(n.split("_")[1] for n in mem if not n.startswith("Spell_") and n.count("_") >= 2).most_common(1)
        dom = next((k for k, _ in g.most_common() if k != "none"), None)
        word = colour_word(p)
        if word == "white":
            base = "Basic action white"
        elif dom and dom.startswith("Illithid"):
            base = f"Illithid {word}"
        elif fam and fam[0][1] >= .5 * len(mem) and fam[0][0] != "Monster":
            base = f'{FAMILIES.get(fam[0][0], re.sub(r"(?<=[a-z])(?=[A-Z])", " ", fam[0][0]))} {word}'
        else:
            base = NAMES.get(dom, dom or "Unlabelled")
        used[base] += 1
        p.update(name=base if used[base] == 1 else f"{base} {used[base]}", n=len(mem), groups=g.most_common(5))


def assign(names, F, P):
    """icon -> (preset index, curve distance)"""
    PC = np.stack([np.array(p["curve"]) for p in P])
    out = {}
    for n in names:
        if has_curve(F.get(n)):
            d = curve_dist(curve_arr(F[n]["curve"]), PC)
            out[n] = (int(d.argmin()), round(float(d.min()), 2))
    return out


def fit_groups(train, A, P):
    """kind of icon -> its presets by share among training icons (first = default)"""
    g = {}
    for r in train:
        if r["icon"] in A and A[r["icon"]][1] <= T_PRESET:
            for k in keys(r):
                g.setdefault(k, []).append(A[r["icon"]][0])
    G = {}
    for k, v in g.items():
        if len(v) >= 5:
            c = Counter(v).most_common()
            G[k] = {"n": len(v), "presets": [{"preset": P[i]["name"], "share": round(m / len(v), 3)}
                                             for j, (i, m) in enumerate(c) if j == 0 or m / len(v) >= MODE_SHARE]}
    return G


def predict(G, r):
    """-> (group key, [preset names], default first) or (None, []) when the fields say nothing about colour (no intent)."""
    for k in keys(r):
        if k in G:
            return k, [p["preset"] for p in G[k]["presets"]]
    return None, []


def preset_lab(p, L):
    cv = np.array(p["curve"])
    L = np.asarray(L, float)
    return np.stack([L, np.interp(L, LC, cv[:, 0]), np.interp(L, LC, cv[:, 1])], -1)


def detint(rgba, p):
    """RGBA float (H,W,4) drawn in preset p -> grey level in [0,1]: the glyph before its gradient map."""
    return np.interp(rgb2lab(rgba[..., :3])[..., 0], p["lq"], Q)


def tint(g, alpha, p, rad=None):
    """grey level (H,W) + alpha -> RGBA float in preset p. Colour = trilinear lookup over lightness, opacity and
    distance from the centre (interpolated, so smooth glows get no seams). Above 512 x 512 px (hi-res PNGs) it runs in
    row bands on threads (numpy releases the GIL): the same numbers, 2048 px 3.6 -> 0.9 s"""
    if rad is None and g.size > 512 * 512:      # a band passes its rows' radius, so it never splits again
        from concurrent.futures import ThreadPoolExecutor
        R = radius(*g.shape)
        with ThreadPoolExecutor(8) as ex:
            return np.concatenate(list(ex.map(lambda r: tint(g[r], alpha[r], p, R[r]), np.array_split(np.arange(len(g)), 8))), 0)
    rad = radius(*g.shape) if rad is None else rad
    L = np.interp(g, Q, p["lq"])
    pts = np.stack([np.clip(L, LC[0], LC[-1]), np.clip(alpha, AC[0], AC[-1]), np.clip(rad, RC[0], RC[-1])], -1)
    ab = RegularGridInterpolator((LC, AC, RC), np.array(p["lut"]))(pts)
    rgb = np.clip(lab2rgb(np.concatenate([L[..., None], ab], -1)), 0, 1)
    return np.concatenate([rgb, alpha[..., None]], -1)


def load(n, s=128):
    return np.asarray(Image.open(D / "masters" / f"{n}.png").convert("RGBA").resize((s, s), Image.BOX)).astype(np.float64) / 255


def de(x, y):
    """median CIEDE2000 between two RGBA float images where both are opaque"""
    m = (x[..., 3] > .3) & (y[..., 3] > .3)
    return float(np.median(deltaE_ciede2000(rgb2lab(x[..., :3][m]), rgb2lab(y[..., :3][m]))))


DARK = np.array([.13, .12, .11])                 # ~ the hotbar's dark stone, for "as seen in game" comparisons


def seen_de(x, y, bg=DARK):
    """CIEDE2000 between two RGBA images composited on bg, over every visible pixel (glow included) -> median, p95"""
    m = x[..., 3] > .02
    comp = lambda c: c[..., :3] * c[..., 3:] + bg * (1 - c[..., 3:])
    d = deltaE_ciede2000(rgb2lab(comp(x)[m]), rgb2lab(comp(y)[m]))
    return [round(float(np.median(d)), 2), round(float(np.percentile(d, 95)), 2)]


def glow_style(x):
    """core_gain: L* gained from a line's edge to its centre (bright-core lines vs flat, metallic ones).
    glow_px: how far the emitted glow reaches past the lines (px at 512) before opacity drops under 5%."""
    a, s = x[..., 3], 512 / x.shape[0]
    m = a > .6
    L = rgb2lab(x[..., :3])[..., 0]
    din, dout = ndimage.distance_transform_edt(m), ndimage.distance_transform_edt(~m)
    inner, edge = m & (din >= 2.5), m & (din < 1.5)
    gain = round(float(np.median(L[inner]) - np.median(L[edge])), 1) if inner.sum() > 20 and edge.sum() > 20 else None
    ring = lambda d: a[(dout > d - 1) & (dout <= d)]
    reach = next((d for d in range(1, 41) if ring(d).size and np.median(ring(d)) < .05), 40)
    return {"core_gain": gain, "glow_px": round(reach * s)}


def run():
    F = features()
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    split = lambda f: [rows[n] for n in (D / f).read_text().split() if n in rows]
    train, hold = split("train.txt"), split("holdout.txt")
    # illithid powers (D23) are drawn in the game's own presets (Force red, a silver basic-action white): clustered with
    # the rest, 30 red ones renamed Force red "Illithid" and split the basic actions. So presets come from the other
    # icons, and only illithid powers no preset fits form their own (house) presets, appended. Two-colour icons (D26,
    # metamagic) stay out: their mixed red + silver curves formed "Metamagic red"; each of their parts gets a preset below
    P = fit_presets([r["icon"] for r in train if kind(r) != "Illithid" and r["icon"] not in TWO_TONE], F)
    far = assign([r["icon"] for r in train if kind(r) == "Illithid"], F, P)
    P += fit_presets([n for n, (i, d) in far.items() if d > T_PRESET], F)
    A = assign([r["icon"] for r in train + hold if r["icon"] not in TWO_TONE], F, P)
    name_presets(P, rows, {n: a for n, a in A.items() if n in {r["icon"] for r in train} and a[1] <= T_PRESET})
    G = fit_groups(train, A, P)
    log(f"[2.1] {len(P)} presets from {len(train)} training icons: " + ", ".join(f"{p['name']} {p['n']}" for p in P))
    from .glyph import master, part_presets                   # glyph imports this module: import at call time
    two = {n: [[P[i]["name"], round(d, 2)] for _, i, d in part_presets(master(n), P)[1]]
           for n in TWO_TONE if (D / "masters" / f"{n}.png").exists()}
    log(f"[2.1] two-colour icons (D26), parts: " + "; ".join(f"{n.split('_')[-1]} {a[0]} {a[1]} + {b[0]} {b[1]}" for n, (a, b) in two.items()))
    ev = {}
    for name, rs in (("train", train), ("holdout", hold)):
        res = []
        for r in rs:
            k, ps = predict(G, r)
            if ps and r["icon"] in A:
                got = P[A[r["icon"]][0]]["name"]
                res.append({"icon": r["icon"], "kind": kind(r), "key": k, "got": got, "main": got == ps[0], "any": got in ps})
        for kd in ("Spell", "Action", "Illithid"):
            e = [x for x in res if x["kind"] == kd]
            ev[f"{name}/{kd}"] = {"n": len(e), "main": round(float(np.mean([x["main"] for x in e])), 3),
                                  "any": round(float(np.mean([x["any"] for x in e])), 3)}
            log(f"[2.1] {name} {kd}: {len(e)} predictable, default preset right {ev[f'{name}/{kd}']['main']:.1%}, "
                f"one of its presets {ev[f'{name}/{kd}']['any']:.1%}")
        ev[f"{name}/misses"] = [x["icon"] for x in res if not x["main"]]
    near = [r["icon"] for r in hold if r["icon"] in A]
    cover = float(np.mean([A[n][1] <= T_PRESET for n in near]))
    icons = {}                                   # every icon a preset fits: round trip as seen in game + glow style
    for j, (n, (i, d)) in enumerate(A.items()):
        if d <= T_PRESET:
            x = load(n, 256)
            icons[n] = {"preset": P[i]["name"], "dist": d, "roundtrip": seen_de(x, tint(detint(x, P[i]), x[..., 3], P[i])),
                        **glow_style(x)}
        if j % 300 == 0:
            log(f"    round trip + glow style {j}/{len(A)}")
    med = lambda v: round(float(np.median(v)), 1) if len(v) else None
    for p in P:
        st = [v for v in icons.values() if v["preset"] == p["name"]]
        p["style"] = {k: med([v[k] for v in st if v[k] is not None]) for k in ("core_gain", "glow_px")}
    hrt = [icons[n]["roundtrip"] for n in near if n in icons]
    ev["holdout/covered"] = round(cover, 3)
    ev["holdout/roundtrip_seen"] = [med([r[0] for r in hrt]), med([r[1] for r in hrt])]
    ev["not_one_gradient"] = sorted(n for n, v in icons.items() if v["roundtrip"][1] > 10)
    log(f"[2.1] hold-out icons within dE {T_PRESET} of a preset: {cover:.1%}; de-tint + re-tint round trip seen on the "
        f"hotbar dark, glow included: median {ev['holdout/roundtrip_seen'][0]} dE2000, per-icon p95 {ev['holdout/roundtrip_seen'][1]}; "
        f"not one gradient (p95 > 10): {ev['not_one_gradient']}")
    out = {"fitted_on": f"data/train.txt ({len(train)} icons)", "threshold_de2000": T_PRESET, "presets": P, "groups": G, "eval": ev,
           "assigned": {n: [P[i]["name"], d] for n, (i, d) in A.items()}, "icons": icons, "two_tone": two,
           "notes": "preset = gradient map: curve = a*,b* per lightness bin of the lines (centres LC; identity, swatches), "
                    "lq = lightness at grey levels Q (0..1, 201 steps, glow included), lut = a*,b* over lightness LC x opacity AC "
                    "x distance from centre RC (used by tint). style = median core_gain (L*) and glow_px of its icons. group key: damage/<DamageType> when VerbalIntent is Damage, else <Spell|Action>/<intent>, "
                    "then intent/<intent>; presets listed by share among training icons, default first. two_tone: icon -> [[preset, dE2000] of "
                    "its first part (the metamagic drop), of its second], parts by stroke (glyph.part_presets, D26)."}
    (D / "grammar.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    log(f"[2.1] wrote {D / 'grammar.json'}: {len(P)} presets, {len(G)} groups")
    return F, rows, P, A, G, ev, train, hold


# ---------------------------------------------------------------- review page (data/grammar.html, local: Larian thumbnails)
DECIDED = {1: "A", 2: "A"}                        # user, 2026-10-14 (plan D17, D18)
# UI damage-type text colours, GUI/Public/Game/GUI/Theme/DefaultTheme.Colours.xaml L153-165
UI_PALETTE = {"Acid": "#f7ff09", "Thunder": "#7e46ae", "Necrotic": "#a5f280", "Fire": "#ff6600", "Lightning": "#427DE3",
              "Cold": "#44AED4", "Psychic": "#efacdf", "Poison": "#c8f000", "Radiant": "#ffc000", "Force": "#dc1c24"}
# Why icons leave their group's usual colour: read off the per-group outlier lists + check sheets (2026-10-14).
WHY = {
    "Spell/Utility": "Protection and weapon enchantments are drawn like buffs (Shield, Death Ward, Globe of "
                     "Invulnerability, Elemental Weapon). Spells that hold a target are drawn like control "
                     "(Telekinesis, Otiluke's Resilient Sphere, Banishment).",
    "Spell/Buff": "Movement spells are drawn like utility (Blink, Fly, Enhance Leap, Wind Walk).",
    "Spell/Control": "Area and terrain effects keep a material colour (Web, Grease, Magic Circle, Stinking Cloud); "
                     "Ensnaring Strike is weapon red.",
    "Spell/Debuff": "Petrify, sleep and panic are drawn like control (Flesh to Stone, Eyebite).",
    "Action/Utility": "Monster and pet abilities default to amber (Djinni, Displacer Beast, Imp, Quasit, cat); "
                      "weapon-style moves are red (Deflect Missiles, Enraged Throw).",
    "Action/Buff": "Every Wild Magic surge has its own pale aqua whatever it does; Monk and Fighter defences use the "
                   "action utility steel; Fiendish Resilience is magenta.",
    "Action/Control": "Monster abilities default to amber (Web, Net, Pounce, Scare); weapon moves are red (Bash, Topple).",
    "Action/Summon": "Wild Magic and ice/moonbeam summons are aqua or blue.",
    "damage/Bludgeoning": "Water attacks are blue (Water Whip, Water Elemental Slam); spore attacks grey-green.",
    "damage/Poison": "Mixed: insects and arrows red, gases yellow or green.",
}


def report():
    from .page import e, figure, row, page, lede_reply, decision
    F, rows, P, A, G, ev, train, hold = run()
    holdset = {r["icon"] for r in hold}
    pi = {p["name"]: i for i, p in enumerate(P)}
    pname = lambda n: P[A[n][0]]["name"] if n in A and A[n][1] <= T_PRESET else "no preset"
    hexl = lambda lab: "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in np.clip(lab2rgb(np.asarray(lab, float)[None, None])[0, 0], 0, 1))
    ramp = lambda p: "linear-gradient(90deg," + ",".join(hexl(preset_lab(p, L)) for L in np.linspace(*p["span"], 9)) + ")"
    bar = lambda p, w=150: f'<span class=sw style="width:{w}px;height:16px;background:{ramp(p)}"></span>'
    img = lambda a: Image.fromarray((np.clip(a, 0, 1) * 255).round().astype(np.uint8), "RGBA")

    def fig(n, cap=None, im=None):
        r = rows[n]
        tip = "\n".join(x for x in (n, r["name"], " · ".join(x for x in (r["VerbalIntent"], r["DamageType"]) if x),
                                    pname(n), "test set" if n in holdset else "") if x)
        return figure(im if im is not None else D / "masters" / f"{n}.png",
                      cap if cap is not None else r["name"] or n.split("_", 1)[1], tip, 64, n in holdset)

    grid = lambda ns: f'<div class=grid>{"".join(fig(n) for n in ns)}</div>'

    # same glyph, different preset: vanilla's own recolours are the ground truth for tint()
    names = [n for n, (i, d) in A.items() if d <= T_PRESET]
    al = np.stack([(load(n, 64)[..., 3] > .3).ravel() for n in names]).astype(np.float32)
    inter = al @ al.T
    iou = inter / (al.sum(1)[:, None] + al.sum(1)[None] - inter + 1e-6)
    pairs = sorted(((float(iou[i, j]), names[i], names[j]) for i, j in zip(*np.where(np.triu(iou > .9, 1)))
                    if A[names[i]][0] != A[names[j]][0]), reverse=True)
    moved = {(x, y): tint(detint(load(x), P[A[x][0]]), load(x)[..., 3], P[A[y][0]]) for _, x, y in pairs}
    cross = [de(z, load(y)) for (x, y), z in moved.items()]
    seen, ex2 = set(), []
    for _, x, y in pairs:                                  # one example per glyph family, coloured presets only
        fam = x.split("_")[1]
        if fam not in seen and "white" not in pname(x) + pname(y) and len(ex2) < 5:
            seen.add(fam)
            ex2.append(f'<div class=chain>{fig(x, pname(x))}<span class=arrow>→</span>{fig(x, "code: " + pname(y), img(moved[x, y]))}'
                       f'<span class=arrow>=</span>{fig(y, "game: " + pname(y))}</div>')
    log(f"[2.1] same-glyph pairs across presets: {len(pairs)}, recoloured in code vs game icon median dE2000 "
        f"{np.median(cross):.2f} (p90 {np.percentile(cross, 90):.2f}; includes shape differences)")

    hs = ev["holdout/Spell"]
    ex = ["Spell_Transmutation_Blink", "Spell_Transmutation_Fly", "Spell_Shield", "Spell_Abjuration_DeathWard",
          "Spell_Evocation_OtilukesResilientSphere", "Spell_Transmutation_FleshToStone", "Spell_Conjuration_Web",
          "Action_WildMagic_Barbarian_Teleport"]
    ex1 = "".join(f'<div class=pair>{fig(n, "")}<div class=pname>{e(rows[n]["name"])}<br><span style="color:var(--mute)">'
                  f'{e(rows[n]["VerbalIntent"])} → usually {e(predict(G, rows[n])[1][0])}, drawn {e(pname(n))}</span></div></div>'
                  for n in ex if n in A and predict(G, rows[n])[1])
    d1 = decision(1, 2, DECIDED[1], f"{100 - 100 * hs['main']:.0f}% of test spells",
                  "How should the app choose an icon's colour?",
                  f"The intent and damage type pick the game's colour preset for {hs['main']:.0%} of test-set spells. "
                  "The rest is the artist's call: movement buffs drawn like utility, protection spells like buffs, petrify like "
                  "control. Matching words in the description made it worse (below).",
                  ex1,
                  [("A", "Colour is its own field",
                    "The app pre-selects the usual colour for the intent and damage type, and you can pick any preset below. "
                    "Training captions name each icon's real colour, so the model learns to follow the colour you pick. "
                    "The 90% test moves to Phase 5: generated colour matches the requested one."),
                   ("B", "Colour follows the intent only",
                    "No colour field and no colour words in captions. The model picks up the intent habits, exceptions "
                    "included, and you cannot ask for another colour.")],
                  unit="drawn off their usual colour")
    rt = ev["holdout/roundtrip_seen"]
    thin = sum(p["n"] < 12 for p in P)
    d2 = decision(2, 2, DECIDED[2], f"{len(pairs)} vanilla recolours",
                  "Should the model learn colour, or should code apply it?",
                  f"Every game icon is a one-colour glyph run through one of {len(P)} colour gradients: given a pixel's "
                  f"brightness its colour is fixed, to an error the eye cannot see. Code can take the colour off a glyph, "
                  f"keeping its brightness and transparency (bright-core lines, the glow it emits, bright spots), and put any "
                  f"gradient back on: round trip on test icons as seen on the hotbar's dark background, glow included, median "
                  f"{rt[0]} ΔE2000. The glow's own tint and radial hotspots come from where a pixel sits (glow or line, centre "
                  f"or rim), which the gradient also stores. Larian already does this: "
                  f"{len(pairs)} pairs of game icons are the same glyph in two gradients, and moving one into the other's "
                  "gradient in code matches the game's own icon (left: game icon; middle: recoloured in code; right: the real "
                  "game icon in that colour).",
                  "".join(ex2),
                  [("A", "Model draws a grey glyph, code colours it",
                    "Training images have their colour taken off; the colour you pick is put on after generation, exactly. "
                    "Colour can never come out wrong, the elemental series (Divine Strike, Dragonborn breath, Glyph of Warding) "
                    "become one glyph instead of near-copies, and captions spend their words on shape. This replaces the "
                    "'captions name the colour' part of decision 1."),
                   ("B", "Model draws in colour",
                    f"Captions name each icon's gradient, as decision 1 planned. The model has to learn {len(P)} gradients, "
                    f"{thin} of them from fewer than 12 icons; a hue snap afterwards fixes the hue but not the exact gradient.")],
                  note="Either way the app's colour field from decision 1 stays. Shapes still differ inside some pairs "
                       "(different element symbol), which is why the match is close rather than exact.",
                  unit="")

    # palette
    trs = []
    for i, p in enumerate(P):
        mem = sorted((n for n, (j, d) in A.items() if j == i and d <= T_PRESET), key=lambda n: (A[n][1], n))[:5]
        used = ", ".join(f"{k.replace('/', ' ')} {v}" for k, v in p["groups"][:3])
        st = p["style"]
        trs.append(f'<tr><td><b>{e(p["name"])}</b><br>{bar(p)}</td><td class=num>{p["n"]}</td><td>{e(used)}</td>'
                   f'<td class=num>{st["core_gain"]:+.0f}</td><td class=num>{st["glow_px"]:.0f}</td><td>{grid(mem)}</td></tr>')
    table = ('<div class=tw-x><table class=t><tr><th>Preset (dark → light)</th><th>Icons</th><th>Mostly used for</th>'
             '<th title="L* gained from a line\'s edge to its centre">Line core</th><th title="px at 512 the glow reaches past '
             'the lines">Glow</th><th>Closest examples</th></tr>' + "".join(trs) + "</table></div>")

    # why rows: icons whose preset is not their group's usual one
    why = []
    for k, g in sorted(G.items(), key=lambda x: -x[1]["n"]):
        if k.startswith("intent/"):
            continue
        usual = g["presets"][0]["preset"]
        off = [r["icon"] for r in train + hold if r["icon"] in A and A[r["icon"]][1] <= T_PRESET
               and predict(G, r)[0] == k and pname(r["icon"]) != usual]
        if off:
            cnt = Counter(pname(n) for n in off)
            why.append(row(len(off), f"{k.replace('/', ' · ')}: usually {usual}",
                           ", ".join(f"{v} {c}" for c, v in cnt.most_common(3)) + (" …" if len(cnt) > 3 else ""),
                           WHY.get(k, "Scattered; no shared cause."), grid(off)))

    def ui_cmp(d):
        k = f"damage/{d}"
        if k not in G:
            return "none"
        p = P[pi[G[k]["presets"][0]["preset"]]]
        rgb = np.clip(lab2rgb(preset_lab(p, 60)[None, None]), 0, 1)[0]
        return f'{hsv(rgb)[0][0]:.0f}° {bar(p, 60)}'
    ui_hue = lambda hx: hsv(np.array([[int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]]))[0][0]
    ui_rows = "".join(f'<tr><td>{d}</td><td class=num>{ui_hue(hx):.0f}° <span class=sw style="background:{hx}"></span></td>'
                      f'<td class=num>{ui_cmp(d)}</td></tr>' for d, hx in UI_PALETTE.items())
    unassigned = sorted(n for n, (i, d) in A.items() if d > T_PRESET)
    two = json.loads((D / "grammar.json").read_text(encoding="utf-8"))["two_tone"]
    notes = "".join([
        row(len(UI_PALETTE), "The game's UI damage colours match the icons", "UI colour is a usable fallback",
            "Hue of each damage type's usual preset (at mid lightness) next to its text colour in DefaultTheme.Colours.xaml.",
            f'<div class=tw-x><table class=t><tr><th>Type</th><th>UI text</th><th>Icon preset</th></tr>{ui_rows}</table></div>'),
        row(8, "Description keyword rules", "tried, dropped",
            "Rules like 'teleport/fly/jump → utility colour' or 'restrain/petrify → control colour' were scored on the training "
            "set against the plain intent rule (by hue, before presets). Movement 15 vs 19 right, restrain 6 vs 11, protection "
            "23 vs 25, charm/fear 9 vs 14: all worse. Only 'Wild Magic' helped (18 vs 8), and that is a game-only family."),
        row(10, "Mechanics from the stats", "one rule worth keeping",
            "Effects read from each spell's functors and the boosts of the statuses it applies, tried as overrides of the "
            "intent rule (by hue, before presets). 'Restrains or incapacitates the target → control colour' fixed 3 and broke "
            "1 training spell and fixed 2 test spells. Every other effect broke more than it fixed (penalty → debuff colour: "
            "+1 / −17; empower → buff: +5 / −19)."),
        row(len(P), "Glow is drawn differently per preset", "style words in captions (Phase 4)",
            "Line core = how much brighter a line's centre is than its edge (L*); glow = how far the emitted glow reaches past "
            "the lines (px at 512). Spells mostly have bright-core lines (+20 to +30) and a ~30 px glow; weapon and magic-item "
            "actions have a wide glow (~50 px); basic actions (Dash, Shove, Perform) have flat, metallic lines (about 0) and no "
            "bright core. Since D25 the model draws line art only and code grows each colour's glow (2.4, data/glyph.json)."),
        row(len(two), "Two colours by stroke (metamagic)", "second colour per stroke (D26)",
            "Each stroke is one colour; parts and their presets (dE2000): " + "; ".join(
                f"{rows[n]['name'].replace('Metamagic: ', '')}: {a[0]} {a[1]} + {b[0]} {b[1]}" for n, (a, b) in two.items())
            + ". Left out of preset fitting (their mixed curves had formed 'Metamagic red').", grid(two)),
        row(len(ev["not_one_gradient"]), "Round trip above 10 dE2000", "one colour, kept",
            "Their lines fit one gradient (2.4); the miss is in the glow.", grid(ev["not_one_gradient"])),
        row(len(unassigned), "Icons no preset fits", "kept as they are",
            f"Further than ΔE {T_PRESET} from every preset: white basic actions and one-offs.", grid(unassigned)),
        row(len(ev["holdout/misses"]), "Test-set icons off their usual preset", "explained above",
            "Their kind usually gets another preset.", grid(ev["holdout/misses"])),
    ])
    lede, reply = lede_reply(DECIDED, 2)
    body = (f'<p class=lede>Phase 2.1: the colours the game draws icons in, measured on the {len(train)} training icons and '
            f'checked on the {len(hold)} test icons. {lede} Hover a picture for its file name, labels and preset; a gold '
            f'outline marks a test-set icon.</p>{d2}{d1}{reply}'
            f'<h2 class=sec>The {len(P)} colour presets</h2><p class=secsub>Each is a gradient from the glyph\'s darkest to its '
            f'lightest pixels. {ev["holdout/covered"]:.0%} of test icons are within ΔE {T_PRESET:g} of one of them.</p>{table}'
            f'<h2 class=sec>Why icons break the rule</h2><p class=secsub>Icons not in their kind\'s usual preset. Click a row '
            f'to see them.</p>{"".join(why)}'
            f'<h2 class=sec>Notes</h2><p class=secsub>No action needed.</p>{notes}')
    (D / "grammar.html").write_text(page("Icon colour rules", body), encoding="utf-8")
    log(f"[2.1] wrote {D / 'grammar.html'}")


if __name__ == "__main__":
    {"features": features, "fit": run, "report": report}[sys.argv[1] if len(sys.argv) > 1 else "report"]()
