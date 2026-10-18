"""Phase 2.5 relations: icons that share a drawing, found by the shape of their line art (glyph.split lines), not by name.
Shape score kappa = chance-corrected tolerant overlap of the lines at S px: the share of each icon's line pixels within 1 px
of the other's lines, both ways, minus what the same amount of line at random places would score; the max of the icons as
placed and each scaled to its own line box (re-placed or rescaled copies). Random pairs: median .20, 99.9th percentile .65.
>= T_SAME the same drawing (recolours, re-placed copies, a small symbol swapped); T_BASE..T_SAME a shared base (frame or
figure) mixed with look-alikes (dense bursts vs stripes): eyes needed. Plain tolerant overlap without the chance term put
such look-alikes at .84 (dilated dense lines cover most of the canvas), in the same-drawing range; kappa .76.
Element symbols (user note): the game's damage-type symbol (GenericIcon_DamageType_*) searched by a sliding, scaled,
chance-corrected skeleton match in every icon of a series named by element and in every v1 icon with that damage type.
    python -m iconkit.relations [run]  -> data/relations.json (~2 min, POOL processes)
    python -m iconkit.relations report -> data/relations.html (review page, local: Larian art)
    python -m iconkit.relations check  -> self-check on drawn shapes"""
import json, re, sys
from collections import Counter, defaultdict
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, signal
from scipy.sparse.csgraph import connected_components
from skimage.morphology import skeletonize
from .extract import D, SPELL_LIKE, parse_stats, read_jsonl, log
from .glyph import master, split, structure, POOL
from .grammar import icon_features, assign, detint, tint, load, de

S = 64                                     # px the line maps are compared at (1 px tolerance = 8 px at 512, half a stroke)
T_SAME, T_BASE = .9, .75
DECIDED = {1: "A", 2: "A", 3: "A", 4: "A", 5: "A"}   # user, 2026-10-15 (plan D27, D4, D28 + D29, D30, D31)
RANK = {"Spell": 0, "Skill": 1, "Action": 1, "TadpoleSuperPower": 1, "PassiveAction": 2, "PassiveFeature": 3}   # source first
fam = lambda n: n.split("_")[0]


def lines(x):
    """master (512,512,4) float -> line share at S px as placed, the same scaled to its line box (centred square), the
    box (cy, cx, size) in px at 128, alpha > .3 at S px (2.1's same-glyph test)"""
    placed = split(x, S)["AL"]
    al = split(x, 128)["AL"]
    a = x[..., 3].reshape(S, 512 // S, S, 512 // S).mean((1, 3)) > .3
    m = al > .5
    if m.sum() < 5:
        return placed, np.zeros_like(placed), (64., 64., 0.), a
    r, c = np.where(m)
    cy, cx, h = (r.min() + r.max()) / 2, (c.min() + c.max()) / 2, max(np.ptp(r), np.ptp(c)) + 1
    box = (cx - h / 2 - 1, cy - h / 2 - 1, cx + h / 2 + 1, cy + h / 2 + 1)
    im = Image.fromarray((al * 255).astype(np.uint8)).transform((S, S), Image.EXTENT, box, Image.BILINEAR)
    return placed, np.asarray(im).astype(np.float64) / 255, (float(cy), float(cx), float(h)), a


def kappa(M):
    """(n, S, S) line shares -> (n, n) chance-corrected tolerant overlap of the lines (1 = same lines, 0 = chance)"""
    A = (M > .5).reshape(len(M), -1).astype(np.float32)
    near = np.stack([ndimage.binary_dilation(m > .5) for m in M]).reshape(len(M), -1).astype(np.float32)
    hit = A @ near.T                                   # line pixels of i within 1 px of j's lines
    a, p = A.sum(1), near.mean(1)
    n = np.maximum(a[:, None] + a[None], 1)
    F = (hit + hit.T) / n
    E = (a[:, None] * p[None] + a[None] * p[:, None]) / n          # F of the same lines at random places
    return (F - E) / np.maximum(1 - E, 1e-3)


def groups(names, K, t):
    """connected groups (2+) of names whose kappa >= t; K indexed like names"""
    lab = connected_components(K >= t, directed=False)[1]
    g = defaultdict(list)
    for n, l in zip(names, lab):
        g[l].append(n)
    return sorted((sorted(v) for v in g.values() if len(v) > 1), key=lambda v: (-len(v), v))


def name_key(r):
    """display name without options in brackets, letters only ('Hex (Charisma)' -> 'hex')"""
    return re.sub(r"[^a-z]", "", re.sub(r"\(.*?\)|:.*", "", (r or {}).get("name", "").lower()))


def job(n):
    return n, lines(master(n))


# element symbols (user, 2026-10-15: "cold = snowflake, poison = skull + crossbones"): series of icons named by damage type
ELEMENTS = ("Acid", "Cold", "Fire", "Force", "Lightning", "Necrotic", "Physical", "Poison", "Psychic", "Radiant", "Thunder")
EL_RE = re.compile(r"(?<=_)(" + "|".join(ELEMENTS) + r")(?=_|$)")
SYM_PX = 128                               # symbols are searched at this size (a Divine Strike symbol is ~1/3 of the icon)
SYM_SCALES = tuple(float(s) for s in np.round(np.arange(.25, 1.01, .05), 2))   # symbol size / its game icon's line box
SYM_FOUND = .75                            # the own element's symbol is drawn: best match and at least this score
# Tried first and dropped: cutting the symbol out as the lines a series does not share. Frames inside the cut (Chromatic
# Orb's circle, Protection from Energy's shield) spoiled it: own element closest 28 of 64. Plain normalised correlation of
# templates degenerates at small sizes (1.00 anywhere).


def element_series(names):
    """{series pattern ('Action_DivineStrike_*_Melee'): {element: icon}} for patterns with 2+ elements"""
    out = defaultdict(dict)
    for n in names:
        if m := EL_RE.search(n):
            out[EL_RE.sub("*", n, 1)][m[1]] = n
    return {k: v for k, v in sorted(out.items()) if len(v) > 1}


def template(x):
    """a symbol's master -> {scale: stroke skeleton of its line art cropped to its box, at SYM_SCALES of SYM_PX}"""
    al = split(x, SYM_PX)["AL"]
    r, c = np.where(al > .5)
    crop = Image.fromarray((al[r.min():r.max() + 1, c.min():c.max() + 1] * 255).astype(np.uint8))
    return {s: skeletonize(np.asarray(crop.resize((max(round(crop.width * s), 8), max(round(crop.height * s), 8)),
                                                  Image.BILINEAR)) > 127).astype(np.float32) for s in SYM_SCALES}


def symbol_templates():
    """the game's damage-type symbols (GenericIcon_DamageType_*), read from the masters (never shipped, D10)"""
    return {e: template(master(f"GenericIcon_DamageType_{e}")) for e in ELEMENTS}


def find_symbol(x, T):
    """master -> {element: (score, scale, slot)}: each symbol slid over the icon's stroke skeleton (1 px tolerance) at
    every scale; score = share of the symbol's skeleton on the icon's strokes minus the icon's stroke density in that
    window, over 1 - density (so a dense patch does not match everything); the best window and scale per element;
    slot = (top, left, height, width) of that window in px at SYM_PX"""
    near = np.pad(ndimage.binary_dilation(skeletonize(split(x, SYM_PX)["AL"] > .5)).astype(np.float32), 4)
    out = {}
    for e, ts in T.items():
        best = (-1.0, None, None)
        for s, t in ts.items():
            if t.shape[0] >= near.shape[0] or t.shape[1] >= near.shape[1]:
                continue
            hit = signal.correlate(near, t, mode="valid", method="fft") / max(t.sum(), 1)
            den = signal.correlate(near, np.ones_like(t), mode="valid", method="fft") / t.size
            k = (hit - den) / np.maximum(1 - den, 1e-3)
            r, c = np.unravel_index(int(k.argmax()), k.shape)
            best = max(best, (round(float(k[r, c]), 3), s, (int(r) - 4, int(c) - 4, *t.shape)))
        out[e] = best
    return out


# ---------------------------------------------------------------- series composites (user note: "Divine Strike, psychic")
BASE_SHARE = .8          # a series' base = lines in this share of its members (symbols differ, so they never reach it)
NO_SLOT = ("Spell_Abjuration_GlyphOfWarding_ExplosiveRunes_*", "Action_Dragonborn_BreathWeapon_*")   # colour only / no symbol


def line_art(x, s=SYM_PX):
    """master -> line art at s px: line share AL, brightness over black B, alpha a (2.4's lines, D25)"""
    ic = split(x, s)
    return {k: ic[k] for k in ("AL", "B", "a")}


def crop(la):
    """line art cropped to its lines' box"""
    r, c = np.where(la["AL"] > .5)
    return {k: v[r.min():r.max() + 1, c.min():c.max() + 1] for k, v in la.items()}


def symbol_art(e, s=SYM_PX):
    """the game's damage-type symbol as line art cropped to its lines' box"""
    return crop(line_art(master(f"GenericIcon_DamageType_{e}"), s))


def composite(src, base, slot, art):
    """src line art with its symbol swapped: inside the slot window (grown 2 px) only the series' base lines stay, then the
    new symbol art is scaled to fit the window (aspect kept, centred) and drawn over -> line art"""
    out = {k: v.copy() for k, v in src.items()}
    t, l, h, w = slot
    S_ = src["AL"].shape[0]
    t0, l0, t1, l1 = max(t - 2, 0), max(l - 2, 0), min(t + h + 2, S_), min(l + w + 2, S_)
    keep = base[t0:t1, l0:l1]
    for k in out:
        out[k][t0:t1, l0:l1] *= keep
    f = min(h / art["AL"].shape[0], w / art["AL"].shape[1])
    hh, ww = max(round(art["AL"].shape[0] * f), 1), max(round(art["AL"].shape[1] * f), 1)
    r0, c0 = t + (h - hh) // 2, l + (w - ww) // 2
    ys, xs = slice(max(r0, 0), min(r0 + hh, S_)), slice(max(c0, 0), min(c0 + ww, S_))
    for k in out:
        v = np.asarray(Image.fromarray(art[k].astype(np.float32), "F").resize((ww, hh), Image.BILINEAR))
        v = v[ys.start - r0:ys.stop - r0, xs.start - c0:xs.stop - c0]
        cur = out[k][ys, xs]
        out[k][ys, xs] = np.where(v > cur, v, cur) if k == "AL" else np.where(art_on(v, k), v, cur)
    return out


art_on = lambda v, k: v > (.02 if k == "a" else .01)       # where the placed symbol has anything to say


def series_base(icons):
    """lines (AL > .5 at SYM_PX) in BASE_SHARE of a series' members"""
    return sum((line_art(master(n))["AL"] > .5).astype(int) for n in icons) >= BASE_SHARE * len(icons)


pool64 = lambda al: al.reshape(S, al.shape[0] // S, S, al.shape[1] // S).mean((1, 3))


def series_slots(ser, T):
    """{element: (score, scale, slot)} of each member's own symbol"""
    return {e: find_symbol(master(n), {e: T[e]})[e] for e, n in ser.items()}


def compose_job(job):
    """leave-one-out: rebuild every member b from each sibling a whose symbol was found (score >= .6) -> rows
    (series, a, b, kappa(composite, b), kappa(a, b))"""
    pat, ser, T = job
    la = {e: line_art(master(n)) for e, n in ser.items()}
    base, slots, rows = series_base(list(ser.values())), series_slots(ser, T), []
    for a, sa in slots.items():
        for b in (b for b in ser if b != a and sa[0] >= .6):
            K = kappa(np.stack([pool64(composite(la[a], base, sa[2], symbol_art(b))["AL"]), pool64(la[b]["AL"]),
                                pool64(la[a]["AL"])]))
            rows.append([pat, a, b, round(float(K[0, 1]), 3), round(float(K[2, 1]), 3)])
    return rows


def compose(ser, element, T):
    """a series member for a new element: the sibling whose own symbol is found best, its symbol swapped -> (line art,
    source element)"""
    slots = series_slots(ser, T)
    src = max(slots, key=lambda e: slots[e][0])
    return composite(line_art(master(ser[src])), series_base(list(ser.values())), slots[src][2], symbol_art(element)), src


def series_colour(G, ser, element):
    """one preset for the whole series (Protection from Energy: Buff gold) or the element's damage colour (Divine Strike)"""
    ps = {G["assigned"][n][0] for n in ser.values() if n in G["assigned"]}
    return ps.pop() if len(ps) == 1 else G["groups"][f"damage/{element}"]["presets"][0]["preset"]


def paint(la, preset, recipe):
    """line art -> RGB over the hotbar dark: the colour's glow grown from the lines (D25), tinted with the preset (D18)"""
    from .glyph import rebuild
    from .grammar import Q, DARK
    E, A = rebuild({"AL": la["AL"], "a": la["a"], "EL": la["B"] * la["AL"]}, recipe, scale=la["AL"].shape[0] / 128)
    L = np.clip(100 * E / np.maximum(A, 1e-4), 0, 100)
    rgba = tint(np.interp(L, preset["lq"], Q), A, preset)
    return np.clip(rgba[..., :3] * rgba[..., 3:] + DARK * (1 - rgba[..., 3:]), 0, 1)


def symbol_job(job):
    n, T = job
    return n, find_symbol(master(n), T)


def element_symbols(names, rows, v1, pool, whole):
    """is each damage type one symbol design? The game's damage-type symbol searched in every icon of a series named by
    element, and in every v1 icon with that damage type (how often a plain damage spell shows its element's symbol).
    whole(n, e) = icon n is the symbol's own drawing (kappa >= T_SAME): Lightning Bolt is the game's bolt, but at full
    size a 5% scale step moves a thin skeleton's ends past the 1 px tolerance (2 px blurs elements: other-element median
    .50 -> .73, Eldritch Blast 'finds' lightning)"""
    series = {p: s for p, s in element_series(names).items() if not p.startswith("GenericIcon")}
    T = symbol_templates()
    el = {n: e for s in series.values() for e, n in s.items()}
    el.update({n: rows[n]["DamageType"] for n in v1 if n not in el and rows[n]["DamageType"] in ELEMENTS})
    sc = dict(pool.map(symbol_job, [(n, T) for n in sorted(el)], chunksize=4))
    out = {}
    for n, e in el.items():
        s = sc[n]
        top = max(s, key=lambda k: s[k][0])
        out[n] = {"element": e, "own": s[e][0], "scale": s[e][1], "closest": top,
                  "rival": max(v[0] for k, v in s.items() if k != e),
                  "found": bool(top == e and s[e][0] >= SYM_FOUND or whole(n, e)),
                  "series": next((p for p, m in series.items() if n in m.values()), None)}
    ser = [v for v in out.values() if v["series"]]
    plain = defaultdict(list)
    for n, v in out.items():
        if not v["series"]:
            plain[v["element"]].append(n)
    shows = {e: sorted(n for n in ns if out[n]["found"]) for e, ns in plain.items()}
    log(f"[2.5] element symbols: own symbol the best match in {sum(v['closest'] == v['element'] for v in ser)} of "
        f"{len(ser)} series icons ({len(series)} series), found (>= {SYM_FOUND}) in {sum(v['found'] for v in ser)}; "
        f"plain v1 damage icons showing their symbol: " + ", ".join(f"{e} {len(shows[e])}/{len(plain[e])}" for e in sorted(plain)))
    return {"series": series, "icons": out, "plain": {e: len(ns) for e, ns in plain.items()}, "shows": shows}


def parts_image(n, s=128):
    """the icon's line art coloured by connected stroke (what a click in a draft editor would pick), parts >= 0.5% of
    the lines, over the dark"""
    m = split(master(n), 512)["AL"] >= .5
    lab, k = ndimage.label(m)
    size = ndimage.sum(m, lab, range(1, k + 1))
    pal = (np.random.default_rng(3).uniform(.35, 1, (64, 3)) * 255).astype(np.uint8)
    im = np.full((512, 512, 3), 30, np.uint8)
    for j, i in enumerate(i for i in np.argsort(-size) if size[i] >= .005 * m.sum()):
        im[lab == i + 1] = pal[j % 64]
    return Image.fromarray(im).resize((s, s), Image.LANCZOS)


def status_icons(K, ix):
    """statuses a v1 spell/action applies (ApplyStatus in any SpellData field) -> which icon each shows"""
    st = parse_stats()
    status = {n for n, e in st.items() if e["_type"] == "StatusData"}
    res, ex, seen = Counter(), defaultdict(list), set()
    for e in st.values():
        icon = e.get("Icon", "")
        if e["_type"] != "SpellData" or fam(icon) not in SPELL_LIKE:
            continue
        for v in e.values():
            for args in re.findall(r"ApplyStatus\(([^)]*)\)", v) if isinstance(v, str) else ():
                for s in (x.strip() for x in args.split(",")):
                    if s not in status or (icon, s) in seen:
                        continue
                    seen.add((icon, s))
                    si = st[s].get("Icon", "")
                    k = ("hidden, no icon" if not si else "the spell's own icon" if si == icon else
                         "another icon, same drawing" if si in ix and icon in ix and K[ix[si], ix[icon]] >= T_SAME else
                         f"a condition icon ({fam(si)}_)" if fam(si) in ("Status", "statIcons", "GenericIcon") else
                         "another spell / action / passive icon")
                    res[k] += 1
                    ex[k].append([icon, s, si])
    return {"counts": dict(res.most_common()), "examples": {k: v[:12] for k, v in ex.items()}}


def run():
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    PN = [p["name"] for p in G["presets"]]
    pre = {n: v[0] for n, v in G["assigned"].items() if v[1] <= G["threshold_de2000"]}
    train, hold = (set((D / f).read_text().split()) for f in ("train.txt", "holdout.txt"))
    names = sorted(p.stem for p in (D / "masters").glob("*.png"))
    ix = {n: i for i, n in enumerate(names)}
    with Pool(POOL) as pool:
        L = dict(pool.map(job, names, chunksize=20))
    log(f"[2.5] line maps for {len(names)} masters")
    Kp = kappa(np.stack([L[n][0] for n in names]))
    Kb = kappa(np.stack([L[n][1] for n in names]))
    K = np.maximum(Kp, Kb)
    np.fill_diagonal(K, 0)
    iu = np.triu_indices(len(names), 1)
    q = np.percentile(K[iu], [50, 90, 99, 99.9]).round(3).tolist()
    log(f"[2.5] kappa over all {len(iu[0])} pairs p50/p90/p99/p99.9 {q}; >= {T_SAME}: {(K[iu] >= T_SAME).sum()}, "
        f"{T_BASE}-{T_SAME}: {((K[iu] >= T_BASE) & (K[iu] < T_SAME)).sum()}")

    def pair(a, b):
        i, j = ix[a], ix[b]
        (cy1, cx1, h1), (cy2, cx2, h2) = L[a][2], L[b][2]
        return {"a": a, "b": b, "kappa": round(float(K[i, j]), 3), "placed": round(float(Kp[i, j]), 3),
                "boxed": round(float(Kb[i, j]), 3), "scale": round(h2 / max(h1, 1), 3),
                "shift": round(float(np.hypot(cy2 - cy1, cx2 - cx1)) / 128, 3)}

    order = lambda a, b: (a, b) if (RANK.get(fam(a), 5), a) <= (RANK.get(fam(b), 5), b) else (b, a)
    pairs = [pair(*order(names[i], names[j])) for i, j in zip(*iu) if K[i, j] >= T_BASE]

    # v1 training material: the same drawing under several names (Phase 6), test icons whose drawing is in training
    v1 = [n for n in names if n in train or n in hold]
    vi = [ix[n] for n in v1]
    same = groups(v1, K[np.ix_(vi, vi)], T_SAME)
    seen = sorted(n for g in same if any(m in train for m in g) for n in g if n in hold)
    tight = [g for g in same if min(K[ix[a], ix[b]] for a in g for b in g if a != b) >= .97]
    log(f"[2.5] v1: {len(same)} same-drawing groups, {sum(map(len, same))} icons ({len(tight)} groups all >= .97, "
        f"recolours of one drawing); one per group would drop {sum(len(g) - 1 for g in same)} of {len(v1)}; "
        f"test icons whose drawing is in training: {seen}")
    # how new a new game icon is (D29): each test icon's closest training drawing; the yardstick for generated icons
    ti = [ix[n] for n in names if n in train]
    near = {n: (names[ti[int(K[ix[n], ti].argmax())]], round(float(K[ix[n], ti].max()), 3)) for n in v1 if n in hold}
    nn = [k for n, (_, k) in near.items() if n not in seen]
    nov = {"p10_50_90": np.percentile(nn, [10, 50, 90]).round(2).tolist(), "base": int(sum(k >= T_BASE for k in nn)),
           "n": len(nn), "nearest": near}
    log(f"[2.5] new game icons (test set without the {len(seen)} copies): closest training drawing kappa p10/50/90 "
        f"{nov['p10_50_90']}, {nov['base']} of {len(nn)} at {T_BASE}+ (shared base)")

    # across families: what the game does to a related icon (colour, size, place, stroke weight)
    cross = [p for p in pairs if fam(p["a"]) != fam(p["b"])]
    feats = {n: icon_features(D / "masters" / f"{n}.png") for p in cross for n in (p["a"], p["b"]) if n not in pre}
    for n, (k, d) in assign(list(feats), feats, G["presets"]).items():
        if d <= G["threshold_de2000"]:
            pre[n] = PN[k]
    stroke = {n: (structure(master(n)) or {}).get("stroke", [0, 0, 0])[1] for p in cross for n in (p["a"], p["b"])}
    for p in cross:
        p.update(colour=[pre.get(p["a"]), pre.get(p["b"])], stroke=round(stroke[p["b"]] / max(stroke[p["a"]], 1e-3), 2),
                 same_name=bool(name_key(rows.get(p["a"])) and name_key(rows.get(p["a"])) == name_key(rows.get(p["b"]))))
    cs = [p for p in cross if p["kappa"] >= T_SAME]
    ev = {"masters": len(names), "kappa_all_pairs": q, "cross_same": len(cs), "cross_base": len(cross) - len(cs),
          "cross_recoloured": sum(p["colour"][0] != p["colour"][1] for p in cs),
          "cross_same_size": sum(abs(np.log(p["scale"])) <= .05 for p in cs),
          "cross_scale_p10_50_90": np.percentile([p["scale"] for p in cs], [10, 50, 90]).round(2).tolist(),
          "cross_stroke_p10_50_90": np.percentile([p["stroke"] for p in cs], [10, 50, 90]).round(2).tolist(),
          "cross_same_name": sum(p["same_name"] for p in cs)}
    log(f"[2.5] across families: {len(cs)} same-drawing pairs ({ev['cross_recoloured']} recoloured, {ev['cross_same_size']} "
        f"within 5% of the size, scale p10/50/90 {ev['cross_scale_p10_50_90']}, stroke ratio {ev['cross_stroke_p10_50_90']}, "
        f"{ev['cross_same_name']} share a name); {ev['cross_base']} shared-base pairs")

    # by name only: cross-family icons with the same display name, and whether they share a drawing
    by_name = defaultdict(list)
    for n in names:
        if fam(n) in RANK and name_key(rows.get(n)):
            by_name[name_key(rows[n])].append(n)
    named = [(*order(a, b), round(float(K[ix[a], ix[b]]), 3)) for ns in by_name.values() for a in ns for b in ns
             if a < b and fam(a) != fam(b)]
    ev["name_pairs"] = len(named)
    ev["name_pairs_same"] = sum(k >= T_SAME for *_, k in named)
    log(f"[2.5] same display name across families: {len(named)} pairs, {ev['name_pairs_same']} the same drawing")

    # continuity: 2.1's alpha-IoU same-glyph pairs (alpha > .3 at 64 px, IoU > .9, different presets)
    an = [n for n in names if n in pre and n in G["assigned"]]
    al = np.stack([L[n][3].ravel() for n in an]).astype(np.float32)
    inter = al @ al.T
    iou = inter / (al.sum(1)[:, None] + al.sum(1)[None] - inter + 1e-6)
    old = [(an[i], an[j]) for i, j in zip(*np.where(np.triu(iou > .9, 1))) if pre[an[i]] != pre[an[j]]]
    ev["alpha_pairs"] = len(old)
    ok = np.array([K[ix[a], ix[b]] for a, b in old])
    ev["alpha_pairs_same"], ev["alpha_pairs_base"] = int((ok >= T_SAME).sum()), int(((ok >= T_BASE) & (ok < T_SAME)).sum())
    log(f"[2.5] 2.1's alpha-IoU same-glyph pairs: {len(old)}, by lines {ev['alpha_pairs_same']} the same drawing, "
        f"{ev['alpha_pairs_base']} a shared base, kappa p10/50/90 {np.percentile(ok, [10, 50, 90]).round(2).tolist()}")

    stat = status_icons(K, ix)
    log(f"[2.5] statuses applied by v1 spells/actions: {stat['counts']}")
    with Pool(POOL) as pool:
        sym = element_symbols(names, rows, v1, pool, lambda n, e: K[ix[n], ix[f"GenericIcon_DamageType_{e}"]] >= T_SAME)
        T = symbol_templates()
        comp = [r for rs in pool.map(compose_job, [(p, s, T) for p, s in sym["series"].items() if p not in NO_SLOT],
                                     chunksize=1) for r in rs]
    c, s0 = np.array([r[3] for r in comp]), np.array([r[4] for r in comp])
    sym["compose"] = {"rows": comp, "median": round(float(np.median(c)), 3), "p10": round(float(np.percentile(c, 10)), 3),
                      "source_median": round(float(np.median(s0)), 3), "better": int((c > s0).sum()), "n": len(comp),
                      "by_series": {p: [round(float(np.median([r[3] for r in comp if r[0] == p])), 3),
                                        round(float(np.median([r[4] for r in comp if r[0] == p])), 3)]
                                    for p in dict.fromkeys(r[0] for r in comp)}}
    log(f"[2.5] series composites (user note): member rebuilt from a sibling with its symbol swapped, kappa vs the real "
        f"member median {sym['compose']['median']} (p10 {sym['compose']['p10']}), the sibling as is "
        f"{sym['compose']['source_median']}; better {sym['compose']['better']} of {len(comp)}; by series "
        f"{sym['compose']['by_series']}")
    out = {"notes": "kappa = chance-corrected tolerant line overlap at 64 px, max of as placed / scaled to the line box; "
                    "pairs: kappa >= T_BASE, a = source (spell before action/skill before passive), scale = b's line box / "
                    "a's, shift in widths; groups = v1 icons with the same drawing (kappa >= T_SAME, connected); seen_drawing "
                    "= test icons whose drawing is in training; cross = pairs across families with colour presets "
                    "[a, b] and stroke = b's median stroke / a's",
           "thresholds": {"same": T_SAME, "base": T_BASE}, "eval": ev, "groups": same, "seen_drawing": seen, "novelty": nov,
           "cross": cross, "named": named, "statuses": stat, "symbols": sym, "pairs": pairs}
    (D / "relations.json").write_text(json.dumps(out, indent=1, default=lambda o: o.item()), encoding="utf-8")
    log(f"[2.5] wrote {D / 'relations.json'}: {len(pairs)} pairs >= {T_BASE}")


# ---------------------------------------------------------------- review page (data/relations.html, local: Larian art)
def report():
    from .page import e, figure, decision, row, lede_reply, page
    J = json.loads((D / "relations.json").read_text(encoding="utf-8"))
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    P = {p["name"]: p for p in G["presets"]}
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    hold = set((D / "holdout.txt").read_text().split())
    ev, keep = J["eval"], []
    nm = lambda n: (rows.get(n) or {}).get("name") or n.split("_", 1)[1]
    fig = lambda n, cap=None, size=64: figure(D / "masters" / f"{n}.png", nm(n) if cap is None else cap, n, size, n in hold)
    grid = lambda ns: f'<div class=grid>{"".join(fig(n) for n in ns)}</div>'

    def chain(p):
        """source -> source line art recoloured in code into the related icon's colour -> the game's related icon"""
        a, b = p["a"], p["b"]
        ca, cb = p["colour"]
        x = load(a)
        im = Image.fromarray((np.clip(tint(detint(x, P[ca]), x[..., 3], P[cb]), 0, 1) * 255).round().astype(np.uint8), "RGBA")
        keep.append(im)
        return (f'<div class=chain>{fig(a, f"{fam(a)}: {nm(a)}")}<span class=arrow>→</span>'
                f'{figure(im, "code: " + cb, a)}<span class=arrow>≈</span>{fig(b, f"game {fam(b)}")}</div>')

    cs = sorted((p for p in J["cross"] if p["kappa"] >= T_SAME), key=lambda p: -p["kappa"])
    show = [p for p in cs if all(p["colour"]) and p["colour"][0] != p["colour"][1] and fam(p["a"]) != "GenericIcon"][:8]
    d1 = decision(1, 5, DECIDED.get(1), sum(map(len, J["groups"])),
                  "The same drawing under several names: how much should training see it?",
                  f"{len(J['groups'])} groups of v1 icons ({sum(map(len, J['groups']))} icons) share one drawing: element "
                  f"series (Glyph of Warding, Divine Strike), monster variants, Disguise Self races, bonus-action copies. "
                  f"The model learns grey line art (D18, D25), so recoloured copies become the same training image. Keeping "
                  f"one per group drops {sum(len(g) - 1 for g in J['groups'])} of the training icons and the small differences "
                  f"inside a group (the element symbol, the rune). {len(J['seen_drawing'])} test icons have their drawing in "
                  f"training ({', '.join(nm(n) for n in J['seen_drawing'])}): a model would score well on them by memory.",
                  "".join(f'<div class=twin>{grid(g)}</div>' for g in J["groups"][:8]),
                  [("A", "Keep all, each group counts as one icon",
                    "Every icon stays in training with weight 1/(group size), so a 6-icon series weighs what one icon does "
                    "but its element symbols are still seen (captions name them, Phase 4). Test icons whose drawing is in "
                    "training are scored apart in Phases 5-6, not moved, so earlier numbers stay comparable."),
                   ("B", "Keep one icon per group (plan as written)",
                    "The simplest training set. The other members' symbols and small changes are lost."),
                   ("C", "Keep all at full weight",
                    "Series weigh as many icons as they have members: the model leans towards drawings the game repeats.")],
                  note="Groups are the same drawing by line shape (kappa >= .9), any colour; numbered badge variants are "
                       "already out (D14). Gold outline = test set.", unit="icons")
    d2 = decision(2, 5, DECIDED.get(2), len(cs),
                  "How should the app make a related action or passive from a spell?",
                  f"The game's related icons across families are the same drawing: {len(cs)} pairs share their lines "
                  f"(kappa >= .9), {ev['cross_recoloured']} of them recoloured into the related icon's own colour, "
                  f"{ev['cross_same_size']} at the same size within 5% (scale p10/50/90 "
                  f"{' / '.join(map(str, ev['cross_scale_p10_50_90']))}), stroke weight kept (ratio "
                  f"{ev['cross_stroke_p10_50_90'][1]}). Only {ev['cross_same_name']} of them share a display name: Blade of "
                  f"the Rime is Ice Knife, the Djinni's attack is Thunderwave, Wild Magic's gas cloud is Fog Cloud. Each "
                  f"example: the game's spell, its drawing recoloured in code, the game's related icon.",
                  "".join(chain(p) for p in show),
                  [("A", "The same line art, recoloured in code",
                    "Make related = copy the spell's line art, pick the related icon's colour (pre-set from its intent, D17), "
                    "grow that colour's glow (D25) and export the variants. No model run, instant, always the same drawing, "
                    "as the game does. Settles D4 without the variation."),
                   ("B", "Same, plus an optional model variation",
                    "Adds an img2img pass that redraws the copy with small changes. The game does not do this; small "
                    "symbol swaps (Reapply Hex, Regain HP's star) are its nearest case.")],
                  note="Passives come in Phase 9; v1 offers related actions and skills (7.3).", unit="pairs")
    Y = J["symbols"]
    SI, ser = Y["icons"], [v for v in Y["icons"].values() if v["series"]]
    best = sum(v["closest"] == v["element"] for v in ser)
    pc = lambda vs: f"{np.median(vs):.2f}"
    plain_n, shows = sum(Y["plain"].values()), sorted(n for ns in Y["shows"].values() for n in ns)
    els = [e for e in ELEMENTS if f"GenericIcon_DamageType_{e}" in rows]
    cell = lambda n: (f'<td>{fig(n, ("%.2f" % SI[n]["own"]) + (" ✓" if SI[n]["closest"] == SI[n]["element"] else ""), 56)}</td>'
                      if n in SI else f'<td>{fig(n, "game symbol", 56)}</td>' if n else "<td></td>")
    sgrid = (f'<div class=tw-x><table class="t sg"><tr><th></th>{"".join(f"<th>{e}</th>" for e in els)}</tr>'
             + "".join(f'<tr><td class=m>{e(p.replace("_*", " *").replace("_", " "))}</td>'
                       + "".join(cell(s.get(x)) for x in els) + "</tr>"
                       for p, s in [("GenericIcon_DamageType_*", {x: f"GenericIcon_DamageType_{x}" for x in els})]
                       + list(Y["series"].items())) + "</table></div>")
    d3 = decision(3, 5, DECIDED.get(3), len(ser),
                  "Each damage type has its own symbol: reuse one design for it?",
                  f"Your note, measured: the game draws a damage type with one symbol and reuses it. The snowflake, S-shaped "
                  f"flame, bolt, dripping skull, skull and crossbones, four-point star, sound arcs and bubbling drops of its "
                  f"damage-type icons (top row) come back inside Divine Strike, Chromatic Orb, Elemental Adept, Protection "
                  f"from Energy, Elemental Weapon and more. Searched by shape (the symbol slid over each icon at every size), "
                  f"an icon's own element is the best match in {best} of {len(ser)} series icons (median score "
                  f"{pc([v['own'] for v in ser if v['closest'] == v['element']])}; the best other element "
                  f"{pc([v['rival'] for v in ser])}; ✓ = own element best). The misses: Glyph of Warding changes only "
                  f"the colour, Dragonborn breath draws the breath, Divine Strike's physical has its own emblem, and very "
                  f"small symbols. As you say, it is optional: of the {plain_n} other damage icons the search finds it in "
                  f"{len(shows)} ({', '.join(nm(n) for n in shows)}), by eye also Poison Spray's skull and crossbones; Cone "
                  f"of Cold and Ray of Frost draw snowflakes of their own.",
                  sgrid,
                  [("A", "A symbol library, stamped in code, optional per icon",
                    "The app reads the 11 damage-type symbols from your game files as line art (like the backgrounds: never "
                    "shipped, D10). An Element symbol field, off by default and set to the damage type when ticked, places "
                    "the symbol on the generated line art at a size and spot you pick (presets: centred, low centre as on "
                    "Divine Strike, inside a frame), clears the lines under it, then glow and colour follow as usual. The "
                    "same symbol every time, as the game does."),
                   ("B", "The model draws symbols itself",
                    "No app work: captions name the symbol where the game draws one (Phase 4) and prompts can ask for it. "
                    "The model's snowflake will vary from icon to icon, and small symbols may smudge at 64 px.")],
                  note="Either way training keeps the series icons and captions name their symbol (4.2). Your note with "
                       "3A: symbols stay exact, the rest of the icon is a new drawing by the model (row below: how that "
                       "is checked). Gold outline = test set.", unit="series icons")
    from .grammar import kind, DARK
    GL = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    C, T = Y["compose"], symbol_templates()

    def recipe(n, p):
        k = f"{kind(rows[n])}|{p}"
        return GL["glow"][k if k in GL["glow"] else GL["borrow"].get(k, kind(rows[n]))]

    def pil(rgb):
        im = Image.fromarray((rgb * 255).round().astype(np.uint8))
        keep.append(im)
        return im

    def game(n):
        x = master(n).reshape(128, 4, 128, 4, 4).mean((1, 3))
        return pil(np.clip(x[..., :3] * x[..., 3:] + DARK * (1 - x[..., 3:]), 0, 1))

    demo = ""
    for pat, new in (("Action_DivineStrike_*_Melee", ["Psychic", "Force", "Acid"]),
                     ("Spell_Evocation_ChromaticOrb_*", ["Psychic", "Necrotic", "Radiant", "Force"])):
        ser = Y["series"][pat]
        cells = [figure(game(n), f"game: {x}", n, 72) for x, n in ser.items()]
        for x in new:
            la, src = compose(ser, x, T)
            p = series_colour(G, ser, x)
            cells.append(figure(pil(paint(la, P[p], recipe(ser[src], p))), f"NEW: {x}", f"code, from {src}, {p}", 72))
        demo += f'<div class=cgroup><div class=chead><b>{e(nm(next(iter(ser.values()))).split(":")[0])}</b></div><div class=crow>{"".join(cells)}</div></div>'
    ds = Y["series"]["Action_DivineStrike_*_Melee"]
    la = composite(line_art(master(ds["Fire"])), series_base(list(ds.values())), series_slots(ds, T)["Fire"][2], symbol_art("Cold"))
    demo += (f'<div class=chain>{figure(game(ds["Fire"]), "game: Fire", ds["Fire"], 72)}<span class=arrow>→</span>'
             f'{figure(pil(paint(la, P["Cold blue"], recipe(ds["Cold"], "Cold blue"))), "code: Cold", "", 72)}'
             f'<span class=arrow>≈</span>{figure(game(ds["Cold"]), "game: Cold", ds["Cold"], 72)}</div>')
    weak = min(C["by_series"], key=lambda p: C["by_series"][p][0])
    d4 = decision(4, 5, DECIDED.get(4), C["n"],
                  "An icon that fits a game series: build it from the series in code?",
                  f"Your note (Divine Strike with psychic damage). Most element series keep one drawing and swap the damage "
                  f"symbol in the same spot, so code can do that: take a sibling, keep the series' shared lines, put the "
                  f"new element's game symbol in the old symbol's place at its size, then grow the glow and colour as usual. "
                  f"Rebuilding every real member from a sibling this way matches it at a median {C['median']} (1 = same "
                  f"lines; the sibling unchanged {C['source_median']}; better in {C['better']} of {C['n']}). Weakest: "
                  f"{e(nm(next(iter(Y['series'][weak].values()))).split(':')[0])} ({C['by_series'][weak][0]}), whose symbols are "
                  f"its own drawings. Colour follows the series: Divine Strike and Chromatic Orb take the element's colour, "
                  f"Protection from Energy stays gold. Below: the game's members, then new ones made in code (NEW), and a "
                  f"check: Fire rebuilt as Cold next to the game's Cold.",
                  demo,
                  [("A", "Series composites in code",
                    "A Based on field lists the game's element series (Divine Strike, Chromatic Orb, Elemental Adept, "
                    "Protection from Energy, Elemental Weapon...). Typing a name like \"Divine Strike: Psychic\" suggests it. "
                    "Pick a damage type and code builds the icon, exact, instantly, no model run; the result can still be "
                    "edited (decision 5)."),
                   ("B", "The model draws series variants",
                    "Captions name the series and its symbol; the model draws \"Divine Strike, psychic\" itself. Less "
                    "exact: the sword, rays and symbol would be redrawn each time.")],
                  note="Series that change only colour (Glyph of Warding) or draw the effect (Dragonborn breath) are "
                       "recoloured or drawn by the model instead.", unit="rebuilds tested")
    gi = json.loads((D / "glyph.json").read_text(encoding="utf-8"))["icons"]
    pp = np.array([v["parts"] for v in gi.values() if "parts" in v])
    EXP = ["Action_DivineStrike_Fire_Melee", "Spell_Evocation_ChromaticOrb_Fire", "Spell_Abjuration_ProtectionFromEnergy_Cold",
           "Action_Rush", "Spell_Conjuration_IceKnife", "Spell_Enchantment_Hex"]
    parts = "".join(f'<div class="pair trip"><div class=pname>{e(nm(n))}</div>{fig(n, "game", 96)}'
                    f'{figure(keep.append(im := parts_image(n)) or im, "strokes", n, 96)}</div>' for n in EXP)
    d5 = decision(5, 5, DECIDED.get(5), len(pp),
                  "A draft editor: assemble game parts into a reference for the model?",
                  f"Your idea. The game's icons are drawn as separate strokes (median {np.median(pp):.0f} connected parts "
                  f"per icon, {(pp >= 3).mean():.0%} have 3 or more), so clicking a stroke picks a meaningful part: Divine "
                  f"Strike's sword, a ray, the symbol (its three flame strokes take three clicks or a box), a frame. Some "
                  f"drawings are one connected net (Hex's heart, below) and need an eraser. The same canvas already serves "
                  f"the symbol stamp (decision 3) and series composites (decision 4). A draft can be used two ways: as the "
                  f"line art itself (exact, no model) or as a guide the model redraws in the game's style (img2img on the "
                  f"grey lines, or line-art conditioning, with a follow-the-draft slider). Which guide works is a Phase 5 "
                  f"test. Each example: game icon, its strokes coloured one per part.",
                  parts,
                  [("A", "Editor in v1, minimal tools",
                    "Add a game icon by name, pick strokes (click, shift-click, box), move, scale, rotate, flip, delete, "
                    "stamp symbols, erase. Use the draft as the final line art or as the model's guide. Parts come from "
                    "your game files (D10). Freehand drawing later."),
                   ("B", "After v1",
                    "v1 ships the symbol stamp and series composites only; the editor follows once the model works."),
                   ("C", "No editor",
                    "Prompts and fields only.")],
                  note="A guided icon is close to its parts on purpose, so the new-vs-copy check (row below) is shown, "
                       "not enforced, when a draft is used.", unit="icons split")
    lede, reply = lede_reply(DECIDED, 5)
    tr = lambda p: (f'<tr><td>{e(nm(p["a"]))}<br><span class=m>{e(p["a"])}</span></td><td>{e(nm(p["b"]))}<br>'
                    f'<span class=m>{e(p["b"])}</span></td><td class=num>{p["kappa"]:.2f}</td><td class=num>{p["placed"]:.2f}</td>'
                    f'<td class=num>{p["scale"]:.2f}</td><td class=num>{p["stroke"]:.2f}</td><td>{e(p["colour"][0] or "-")} → '
                    f'{e(p["colour"][1] or "-")}</td></tr>')
    table = lambda ps: (f'<div class=tw-x><table class=t><tr><th>Source</th><th>Related</th><th>Shape</th><th>As placed</th>'
                        f'<th>Size</th><th>Stroke</th><th>Colour</th></tr>{"".join(map(tr, ps))}</table></div>')
    pairgrid = lambda ps: "".join(f'<div class=twin><div class=grid>{fig(p["a"], "%.2f" % p["kappa"])}{fig(p["b"], "")}'
                                  f'</div></div>' for p in ps)
    base = sorted((p for p in J["cross"] if p["kappa"] < T_SAME), key=lambda p: -p["kappa"])
    st = J["statuses"]
    shown = sum(v for k, v in st["counts"].items() if k != "hidden, no icon")
    own = st["counts"].get("the spell's own icon", 0)
    stat_tab = "".join(f'<tr><td>{e(k)}</td><td class=num>{v}</td><td>{e(", ".join(f"{s} → {i or chr(8212)}" for _, s, i in st["examples"][k][:3]))}</td></tr>'
                       for k, v in st["counts"].items())
    named_off = sorted((x for x in J["named"] if x[2] < T_SAME), key=lambda x: x[2])
    nv = J["novelty"]
    fresh = sorted(((k, n, m) for n, (m, k) in nv["nearest"].items() if n not in J["seen_drawing"]), reverse=True)
    pick = [fresh[int(q * (len(fresh) - 1))] for q in (0, .1, .2, .5, .6, .9)]
    notes = "".join([
        row(nv["n"], "New drawings, not copies (your note on 3A)", "Phase 5 check",
            f"The model's job is new icons in the game's style; only fixed parts (the damage-type symbols, decision 3) and "
            f"related copies of your own icon (decision 2) are reused exactly. Yardstick: each new game icon (the test set, "
            f"without its {len(J['seen_drawing'])} copies) against its closest training drawing scores a median "
            f"{nv['p10_50_90'][1]} (p10 {nv['p10_50_90'][0]}, p90 {nv['p10_50_90'][2]}); {nv['base']} of {nv['n']} are "
            f"0.75+, all series siblings (Divine Strike elements, Hex abilities, Disguise Self races, Flesh to Stone / "
            f"Gold). Phase 5 scores generated icons the same way: their closest training drawing should look like this "
            f"spread, never 0.9+ (a copy) unless a series variant was asked for. Pairs: test icon, its closest training "
            f"icon, from the closest down.",
            pairgrid([{"a": n, "b": m, "kappa": k} for k, n, m in pick])),
        row(len(cs), "Related icons across families", "table",
            "Every cross-family pair with the same drawing. Shape = kappa (1 = same lines); As placed = kappa without "
            "re-placing, low when the game moved or rescaled the copy; Size = related line box / source's; Stroke = median "
            "stroke width ratio; colour = closest preset (- = none within 3 dE2000).", table(cs)),
        row(len(base), "Shared base, or a look-alike (kappa .75-.9)", "eyes needed",
            "A frame or figure in common with a swapped symbol (Hex's attribute marks, Regain HP's star, the Armour of "
            "Agathys shield), or two dense drawings that only resemble each other (a sunburst and an eye, stripes and a "
            "burst). Dark-line icons (Darkvision) score here against unrelated bursts: their line map is the fill.",
            pairgrid(base)),
        row(own, "Statuses reuse the spell's icon", "export default",
            f"Of the statuses a vanilla spell or action applies and shows, {own / shown:.0%} use the spell's own icon; the "
            f"rest a sibling's icon (Horde Breaker ranged shows the melee one) or the game's condition icons (Burning, "
            f"Frightened). Statuses without an icon are hidden ones (DisablePortraitIndicator). So the mod export (3.3) gives "
            f"a new status the spell's icon unless it applies a standard condition.",
            f'<table class=t><tr><th>Status shows</th><th>n</th><th>Examples (status → icon)</th></tr>{stat_tab}</table>'),
        row(len(named_off), "Same name, different drawing", "by name only",
            f"{ev['name_pairs']} cross-family pairs share a display name; {ev['name_pairs_same']} are the same drawing. The "
            f"rest are drawn anew or are dark-line icons. Name matching alone would miss {ev['cross_same'] - ev['cross_same_name']} "
            f"of the {ev['cross_same']} same-drawing pairs.",
            pairgrid([{"a": a, "b": b, "kappa": k} for a, b, k in named_off[:24]])),
        row(len(J["seen_drawing"]), "Test icons whose drawing is in training", "scored apart",
            "Their group's other members are training icons (another colour or a bonus copy).",
            "".join(f'<div class=twin>{grid(g)}</div>' for g in J["groups"] if set(g) & set(J["seen_drawing"]))),
        row(len(J["groups"]), "Every same-drawing group", "for checking", "Gold outline = test set.",
            "".join(f'<div class=twin>{grid(g)}</div>' for g in J["groups"])),
        row(4, "How the shape score works", "method",
            f"Line art per icon (2.4's line mask) at 64 px. Score = share of each icon's line pixels within 1 px (half a "
            f"stroke) of the other's, both ways, minus what the same amount of line at random places scores, scaled so "
            f"1 = same lines and 0 = chance; the higher of the two icons as placed and each scaled to its own line box. "
            f"All pairs of the {ev['masters']} icons: median {ev['kappa_all_pairs'][0]}, 99.9th percentile {ev['kappa_all_pairs'][3]}. "
            f"2.1's {ev['alpha_pairs']} same-glyph pairs (transparency overlap > .9): {ev['alpha_pairs_same']} are the same "
            f"drawing by lines; transparency overlaps wherever two big glows do.")])
    body = (f'<style>.m{{color:var(--mute);font-size:12px}}table.sg td{{padding:3px;border:0}}table.sg figure{{width:56px}}.trip figure{{width:auto}}.chain figure,.crow figure{{width:72px}}'
            f'</style><p class=lede>Phase 2.5: which icons share a drawing, found by the shape of their line art across all '
            f'{ev["masters"]} icons with art. {lede}</p>{d4}{d5}{reply}<h2 class=sec>Earlier decisions</h2>'
            + "".join(row(1, f"Decision {i}: {t}", "decided", f"Made (your {i}A), kept for reference.", d)
                      for i, t, d in ((1, "copies in training", d1), (2, "make related", d2), (3, "element symbols", d3)))
            + f'<h2 class=sec>Reference</h2><p class=secsub>Click a row to open it.</p>{notes}')
    (D / "relations.html").write_text(page("Icon relations", body), encoding="utf-8")
    log(f"[2.5] wrote {D / 'relations.html'}")


def check():
    """drawn shapes: a moved or rescaled copy scores as the same drawing, a different drawing does not, dense stripes vs a
    dense burst stay under the same-drawing threshold"""
    def draw(f, s=1.0, dx=0):
        im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        f(ImageDraw.Draw(im), lambda *p: [256 + (v - 256) * s + dx * (i % 2 == 0) for i, v in enumerate(p)])
        return np.asarray(im).astype(np.float64) / 255
    W = (255, 230, 200, 255)
    ring = lambda d, t: (d.ellipse(t(110, 110, 402, 402), outline=W, width=20), d.line(t(256, 150, 256, 362), fill=W, width=20))
    cross = lambda d, t: (d.line(t(120, 120, 392, 392), fill=W, width=20), d.line(t(120, 392, 392, 120), fill=W, width=20))
    stripes = lambda d, t: [d.line(t(60, y, 452, y), fill=W, width=16) for y in range(70, 450, 40)]
    burst = lambda d, t: [d.line(t(256, 256, 256 + 200 * np.cos(a), 256 + 200 * np.sin(a)), fill=W, width=16)
                          for a in np.linspace(0, 2 * np.pi, 28, endpoint=False)]
    xs = [draw(ring), draw(ring, dx=24), draw(ring, s=.8), draw(cross), draw(stripes), draw(burst)]
    L = [lines(x) for x in xs]
    K = np.maximum(kappa(np.stack([l[0] for l in L])), kappa(np.stack([l[1] for l in L])))
    assert K[0, 1] >= T_SAME, f"moved copy {K[0, 1]:.2f}"
    assert K[0, 2] >= T_SAME, f"rescaled copy {K[0, 2]:.2f}"
    assert K[0, 3] < .5, f"ring vs cross {K[0, 3]:.2f}"
    assert K[4, 5] < T_BASE, f"stripes vs burst {K[4, 5]:.2f}"
    assert abs(L[2][2][2] / L[0][2][2] - .8) < .05, "line box follows the scale"
    assert groups(["a", "b", "c"], np.array([[0, .95, 0], [.95, 0, 0], [0, 0, 0]]), T_SAME) == [["a", "b"]]
    # a symbol drawn at half size inside a frame is found, and beats a different symbol and a dense burst
    frame = lambda d, t: d.rectangle(t(60, 60, 452, 452), outline=W, width=20)
    small = lambda f: lambda d, t: (frame(d, t), f(d, lambda *p: t(*[256 + (v - 256) * .5 for v in p])))
    T = {"cross": template(draw(cross)), "burst": template(draw(burst)), "ring": template(draw(ring))}
    f = find_symbol(draw(small(cross)), T)
    assert max(f, key=lambda k: f[k][0]) == "cross" and f["cross"][0] >= SYM_FOUND and abs(f["cross"][1] - .5) <= .1, f
    # series composite: the framed cross becomes the framed circle by swapping the symbol in its slot
    circle = lambda d, t: d.ellipse(t(130, 130, 382, 382), outline=W, width=20)
    la_a, la_b = line_art(draw(small(cross))), line_art(draw(small(circle)))
    base = (la_a["AL"] > .5) & (la_b["AL"] > .5)
    comp = composite(la_a, base, f["cross"][2], crop(line_art(draw(circle))))
    K2 = kappa(np.stack([pool64(comp["AL"]), pool64(la_b["AL"]), pool64(la_a["AL"])]))
    assert K2[0, 1] >= T_SAME and K2[0, 1] > K2[2, 1] + .1, f"composite {K2[0, 1]:.2f} vs source {K2[2, 1]:.2f}"
    log(f"[2.5] check passed: moved {K[0, 1]:.2f}, rescaled {K[0, 2]:.2f}, ring vs cross {K[0, 3]:.2f}, "
        f"stripes vs burst {K[4, 5]:.2f}; half-size cross in a frame found {f['cross'][:2]}, burst {f['burst'][0]}, ring "
        f"{f['ring'][0]}; composite cross -> circle {K2[0, 1]:.2f} (source as is {K2[2, 1]:.2f})")


if __name__ == "__main__":
    {"run": run, "report": report, "check": check}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
