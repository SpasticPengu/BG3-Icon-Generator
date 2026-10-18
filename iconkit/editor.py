"""Phase 7 editor (D46): a local web app. The browser draws (vector canvas, WebGL glow + colour from the JSON recipes);
this module cuts the data it edits once and serves it, and exports through variants (the exact Python path).
Data (data/editor/, gitignored: Larian art from the user's own files, D10; first-run extraction on a user's machine):
  icons/<icon>.png      line art at 512 as opaque RGB (R grey, G alpha): grey = grammar.detint in the icon's preset, alpha
                        = line share x alpha (variants.line_art)
  icons/<icon>.lab.png  stroke ids (R + 256 G): 8-connected parts of the D38 line mask (glyph.split AL >= .5, the labels
                        of parts.strokes), every soft pixel given to its nearest stroke, soft bits with no stroke get ids
                        of their own
  thumbs/<icon>.png     the game master over the hotbar dark, THUMB px
  index.json            icons with name, kind, preset, glow recipe, intent, damage type, source, second-colour strokes
  parts.json, parts/<group>.png   the parts panel: each part group's best copy (parts_panel)
    python -m iconkit.editor [serve] [--port N] [--no-browser]  -> extract once if needed, then serve on 127.0.0.1
    python -m iconkit.editor extract   -> icons, thumbs, index (~3 min, POOL processes)
    python -m iconkit.editor parts     -> parts panel + check sheet data/editor/parts_sheet.png
    python -m iconkit.editor check     -> self-check (labels as parts.strokes, export round trip)"""
import base64, io, json, os, re, sys, threading, time, webbrowser
from collections import Counter
from functools import lru_cache
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from multiprocessing import Pool
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from .extract import D, TWO_TONE, read_jsonl, log
from .glyph import split, master, part_presets, POOL
from .grammar import DARK, detint
from .lab import disk

E = D / "editor"
from . import DATA_VERSION as DATA_V          # the cut data's format (icons, strokes, parts): iconkit/__init__.py
APP = Path(__file__).resolve().parent.parent / "app"
THUMB = 72
EIGHT = np.ones((3, 3))


def u8(x):
    return (np.clip(x, 0, 1) * 255 + .5).astype(np.uint8)


# ---------------------------------------------------------------- per-icon strokes
def icon_job(job):
    """icon -> line art (grey, alpha) u8, stroke ids (512, 512) int, second-colour stroke ids, thumbnail"""
    n, p, p2, two = job
    return (n, *cut(master(n), p, p2, two))


def cut(x, p, p2=None, two=None):
    """master (512,512,4) float -> line art (grey, alpha) u8, stroke ids, second-colour stroke ids, thumbnail"""
    n = "icon"
    ic = split(x, 512)
    m = ic["AL"] >= .5
    al = u8(ic["AL"] * ic["a"])
    g = detint(x, p)
    sec = []
    L8, k = ndimage.label(m, EIGHT)
    if two:                                                   # D26: each stroke set de-tinted in its own colour (build)
        side, ((_, i1, _), (s2, i2, _)) = part_presets(x, two)
        assert (two[i1]["name"], two[i2]["name"]) == (p["name"], p2["name"]), n
        st = np.repeat(np.repeat(side == s2, 2, 0), 2, 1)
        g = np.where(st, detint(x, p2), g)
        sec = [int(c) for c in range(1, k + 1) if st[L8 == c].mean() > .5]
    lab = L8.copy()
    soft = (al > 0) & ~m
    C = ndimage.label(al > 0, EIGHT)[0]
    lone = soft & ~np.isin(C, np.unique(C[m]))                # faint bits joined to no stroke: ids of their own
    _, (iy, ix) = ndimage.distance_transform_edt(~m, return_indices=True)
    lab[soft] = L8[iy, ix][soft]
    if lone.any():
        cl, kl = ndimage.label(lone, EIGHT)
        lab[lone] = cl[lone] + k
    th = x[..., :3] * x[..., 3:] + DARK * (1 - x[..., 3:])
    thumb = Image.fromarray(u8(th)).resize((THUMB, THUMB), Image.LANCZOS)
    return np.dstack([np.where(al > 0, u8(g), 0), al]), lab, sec, thumb


def write_icon(n, la, lab, thumb, base=None):
    """line art as opaque RGB (grey, alpha, 0): browsers decode an opaque PNG exactly (a transparent one goes through
    premultiplied alpha and loses the grey of faint pixels). base: data/editor (game icons) or the imported folder"""
    base = base or E
    Image.fromarray(np.dstack([la, np.zeros_like(la[..., :1])]), "RGB").save(base / "icons" / f"{n}.png", optimize=True)
    Image.fromarray(np.dstack([lab & 255, lab >> 8, np.zeros_like(lab)]).astype(np.uint8), "RGB").save(base / "icons" / f"{n}.lab.png", optimize=True)
    thumb.save(base / "thumbs" / f"{n}.png", optimize=True)


def read_strokes(n):
    """-> line art (512,512,2) u8, stroke ids (512,512) int"""
    la = np.asarray(Image.open(E / "icons" / f"{n}.png").convert("RGB"))[..., :2]
    lb = np.asarray(Image.open(E / "icons" / f"{n}.lab.png").convert("RGB")).astype(int)
    return la, lb[..., 0] + 256 * lb[..., 1]


def extract():
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    L = json.loads((D / "links.json").read_text(encoding="utf-8"))
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    PR = {p["name"]: p for p in G["presets"]}
    for d in ("icons", "thumbs"):
        (E / d).mkdir(parents=True, exist_ok=True)
    jobs, index = [], []
    for n, v in sorted(J["icons"].items()):
        p2 = None
        if n in TWO_TONE:
            (pn, _), (p2, _) = G["two_tone"][n]
        else:
            pn = v["preset"] or G["assigned"][n][0]           # no preset within the fit threshold: the nearest one
        jobs.append((n, PR[pn], p2 and PR[p2], p2 and G["presets"]))
        r = rows[n]
        index.append({"n": n, "t": r["name"] or n.split("_", 1)[1].replace("_", " "), "k": v["kind"], "p": pn,
                      "p2": p2, "g": v["glow_recipe"], "i": r["VerbalIntent"], "d": r["DamageType"],
                      "s": L["sources"].get(n, ""), "split": v["split"]})
    log(f"[editor] cutting {len(jobs)} v1 icons into strokes ({POOL} processes)")
    sec = {}
    with Pool(POOL) as pool:
        for i, (n, la, lab, s, thumb) in enumerate(pool.imap(icon_job, jobs, chunksize=4)):
            write_icon(n, la, lab, thumb)
            sec[n] = s
            if i % 200 == 0:
                log(f"    {i}/{len(jobs)} {n}: {lab.max()} strokes")
    for e in index:
        e["sec"] = sec[e["n"]]
    (E / "index.json").write_text(json.dumps({"icons": index}, separators=(",", ":")), encoding="utf-8")
    log(f"[editor] wrote {E / 'icons'}, {E / 'thumbs'}, {E / 'index.json'}")
    symbols()


# ---------------------------------------------------------------- parts panel (D43 amended: no names, best copies)
PAD, PART_PX, CLUTTER_PX, DUP, SUB = 8, 96, 6, .9, .9


def member_stats(g, fig, excl, strokes_of):
    """one group's members -> per member (icon, stroke ids, box, size, clutter, lined-up window) and typicality. Whole
    shape = part + exact repeats (members[i][8]), + the whole object ([9]) for figure groups. Clutter = other strokes'
    line px inside the shape's footprint (dilated CLUTTER_PX, holes filled) per shape px: what crosses or crowds the copy.
    Typicality = median kappa of the whole shape against the other members', lined up on the part's box (as 5.4)."""
    from .parts import icon_box, to_win
    from .relations import kappa
    mem = [m for m in g["members"] if m[0] not in excl]
    if not mem:
        return []
    ref, rows = tuple(mem[0][2:6]), []
    for n, _, top, left, h, w, _, flip, B, A in mem:
        labs = sorted(set(B) | (set(A) if fig else set()))
        m, L8 = strokes_of(n)
        shape = np.isin(L8, labs)
        rr, cc = np.nonzero(shape)
        box = [int(rr.min()), int(cc.min()), int(np.ptp(rr)) + 1, int(np.ptp(cc)) + 1]
        sl = (slice(max(box[0] - PAD, 0), box[0] + box[2] + PAD), slice(max(box[1] - PAD, 0), box[1] + box[3] + PAD))
        reg = ndimage.binary_fill_holes(ndimage.binary_dilation(shape[sl], disk(CLUTTER_PX)))
        rows.append({"icon": n, "labels": labs, "box": box, "size": max(box[2:]), "part": (top, left, h, w), "flip": bool(flip),
                     "clutter": round(float((m[sl] & ~shape[sl] & reg).sum() / shape.sum()), 3),
                     "win": to_win(shape, icon_box(ref, (top, left, h, w), flip), flip, 64)})
    K = kappa(np.array([r.pop("win") for r in rows], np.float32))
    for i, r in enumerate(rows):
        r["typ"] = round(float(np.median(np.delete(K[i], i))) if len(rows) > 1 else 1.0, 3)
    return rows


MATCH_IOU, COMMON, NEAR_PX, FRAG, SMALL = .4, 2 / 3, 10, 1.5, 160
STRAY_AREA, STRAY_NEAR = .15, .1            # strays: under 15% of the largest stroke, off the main strokes' hull by 10% of the size


def family(n):
    """an icon's spell family: Spell_<School>_<Name> (Arcane Lock and Arcane Lock: Dismiss are one), else the icon"""
    return "_".join(n.split("_")[:3]) if n.startswith("Spell_") else n


def complete(rows, k, strokes_of, prune=False):
    """(user 2026-10-18: parts "don't truly capture all of the common element of an icon") copy k's strokes + every other
    stroke of its icon that the group's other copies draw too: each copy lined up with copy k through the two part
    boxes (mirrored as needed, parts.icon_box), a stroke counts when a stroke of the same place and shape (IoU of the
    3 px dilated masks >= MATCH_IOU) is there in COMMON of the other copies. Shape, not pixel hits: 5.4's rule B tested
    pixels against a 16 px shift, which a dense rune never passes (Glyph of Warding kept a different third of its rune in
    each of its six copies). Then the prune (user 7.0g: "the Arcane Lock frame still has one part of the lock"): when
    other spell families share the group, copy k's own strokes stay only if COMMON of those families draw them (variants
    of one spell share its object: the lock's shackle is in both Arcane Lock icons, not in Arcane Gate's frame); a prune
    that would remove half the part or more is skipped (copies that don't line up). For frames (prune: the group is
    eye-checked "Frames & rings") every such stroke goes: a frame holds a different content per spell. Elsewhere only a
    detached one (`off`: outside the hull of the shared strokes and away from them: False Life's sparkle beside the
    heart); a family's own strokes on or in the drawing are often its own details (a face's features, an arrow's head:
    both pruned when every unshared stroke went). -> sorted labels"""
    from .parts import icon_box, to_win
    P, others = rows[k], [r for i, r in enumerate(rows) if i != k]
    seed, fams = set(P["labels"]), {family(o["icon"]) for o in others} - {family(P["icon"])}
    if len(others) < 2 and not fams:
        return sorted(seed)
    _, LP = strokes_of(P["icon"])
    objs, st = ndimage.find_objects(LP), disk(3)
    cand = [c for c in range(1, len(objs) + 1) if objs[c - 1] is not None and (c not in seed or fams)]
    votes, fvotes = Counter(), {}
    grow = lambda sl, p=6: tuple(slice(max(s.start - p, 0), min(s.stop + p, 512)) for s in sl)
    for o in others:
        fl = o["flip"] != P["flip"]
        W = to_win(strokes_of(o["icon"])[0], icon_box(P["part"], o["part"], fl), fl, 512)    # copy o in copy k's frame
        WL = ndimage.label(W, EIGHT)[0]
        wobjs = ndimage.find_objects(WL)
        for c in cand:
            sl = grow(objs[c - 1])
            for t in set(np.unique(WL[sl][ndimage.binary_dilation(LP[sl] == c, st)]).tolist()) - {0}:
                u = grow(tuple(slice(min(a.start, b.start), max(a.stop, b.stop)) for a, b in zip(objs[c - 1], wobjs[t - 1])))
                S, T = ndimage.binary_dilation(LP[u] == c, st), ndimage.binary_dilation(WL[u] == t, st)
                if (S & T).sum() >= MATCH_IOU * (S | T).sum():
                    votes[c] += 1
                    fvotes.setdefault(c, set()).add(family(o["icon"]))
                    break
    need = max(2, int(np.ceil(COMMON * len(others))))
    add = {c for c, v in votes.items() if v >= need and c not in seed} if len(others) >= 2 else set()
    drop = {c for c in seed if len(fvotes.get(c, set()) & fams) < np.ceil(COMMON * len(fams))} if fams else set()
    if drop and not prune:
        drop = off(LP, seed - drop, drop, seed) if seed - drop else set()
    area = lambda s: np.isin(LP, list(s)).sum()
    if drop and area(seed - drop) < .5 * area(seed):
        drop = set()
    return sorted((seed - drop) | add)


def off(L, main, cand, part):
    """cand strokes outside the convex hull of the main strokes and farther than STRAY_NEAR of the part's size (NEAR_PX
    at least) from them"""
    from scipy.spatial import ConvexHull
    M = np.isin(L, list(main))
    rr, cc = np.nonzero(np.isin(L, list(part)))
    size = max(np.ptp(rr), np.ptp(cc)) + 1
    pts = np.argwhere(M)
    hull = Image.new("1", (512, 512))
    if len(pts) >= 3 and np.ptp(pts, 0).min() > 0:
        ImageDraw.Draw(hull).polygon([(int(x), int(y)) for y, x in pts[ConvexHull(pts).vertices]], fill=1)
    near = (ndimage.distance_transform_edt(~M) <= max(NEAR_PX, STRAY_NEAR * size)) | np.asarray(hull, bool)
    return {l for l in cand if not (near & (L == l)).any()}


def strays(icon, labels, strokes_of):
    """(user 7.0g: "random little bits" on a part) strokes under STRAY_AREA of the part's largest stroke that are off its
    larger strokes (`off`): a creature's eye beside a spew, a dot beside a heart. Drops and dots near or inside the
    drawing stay. -> labels to drop"""
    _, L = strokes_of(icon)
    a = dict(zip(labels, ndimage.sum(np.ones(L.shape), L, labels)))
    big = {l for l in labels if a[l] >= STRAY_AREA * max(a.values())}
    small = set(labels) - big
    return off(L, big, small, labels) if small else set()


def embedded(icon, labels, strokes_of, ignore=()):
    """pixels of the strokes near a shape (within half its size, NEAR_PX at least), per pixel of the shape: above FRAG it is
    a piece of a larger drawing in that copy (a drop shape: Tiger's Bloodlust's nose, a pad of Bear Claws' paw, a rock
    in Boar Kick-up's debris)"""
    m, L = strokes_of(icon)
    shape = np.isin(L, labels)
    rr, cc = np.nonzero(shape)
    r = max(NEAR_PX, int(.5 * max(np.ptp(rr), np.ptp(cc))))
    near = set(np.unique(L[(ndimage.distance_transform_edt(~shape) <= r) & m & ~shape]).tolist()) - {0} - set(ignore)
    return float(np.isin(L, list(near)).sum() / max(shape.sum(), 1)) if near else 0.0


def best(rows):
    """score = size share x (1 - clutter) x typicality share^2: the largest clean copy that still looks like the rest"""
    sz, tp = max(r["size"] for r in rows), max(max(r["typ"] for r in rows), 1e-3)
    for r in rows:
        r["score"] = round(r["size"] / sz * (1 - min(r["clutter"], 1)) * (max(r["typ"], 0) / tp) ** 2, 3)
    return sorted(rows, key=lambda r: -r["score"])


def norm_shape(shape, box, s=64):
    """a whole shape in its own square box at s px (for duplicate cards)"""
    t, l, h, w = box
    side = max(h, w)
    sq = np.zeros((side, side), np.uint8)
    sq[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = shape[t:t + h, l:l + w]
    return np.asarray(Image.fromarray(sq * 255).resize((s, s), Image.BOX)) > 40


# ---------------------------------------------------------------- damage-type symbols (D28) in the library
SYMBOL = "GenericIcon_DamageType_{}"


def symbol_presets(S):
    """element -> preset: the damage type's own colour (grammar group damage/<e>); an element without a group (Physical:
    bludgeoning / piercing / slashing) gets the preset that redraws its game colours best (mean colour error)"""
    from .relations import ELEMENTS
    from .grammar import detint, tint
    from .lab import rgb2lab
    out = {}
    for e in ELEMENTS:
        g = S["grammar"]["groups"].get(f"damage/{e}")
        if g:
            out[e] = g["presets"][0]["preset"]
            continue
        x = master(SYMBOL.format(e))[::4, ::4]
        m, lab = x[..., 3] > .3, rgb2lab(x[..., :3])
        err = {n: float(np.linalg.norm(rgb2lab(tint(detint(x, p), x[..., 3], p)[..., :3])[m] - lab[m], axis=-1).mean())
               for n, p in S["PR"].items()}
        out[e] = min(err, key=err.get)
        log(f"[editor] {e} symbol: closest preset {out[e]} ({err[out[e]]:.1f} dE; next "
            f"{sorted(err.items(), key=lambda kv: kv[1])[1][0]})")
    return out


def symbols():
    """the game's damage-type symbols as library icons: cut into strokes like the v1 icons, listed as kind "Symbol" in
    index.json (read from the user's game files, never shipped: D10)"""
    from .relations import ELEMENTS
    from .extract import DAMAGE_TYPES
    S = state()
    pre = symbol_presets(S)
    p = E / "index.json"
    idx = json.loads(p.read_text(encoding="utf-8"))
    icons = [e for e in idx["icons"] if e["k"] != "Symbol"]
    for e in ELEMENTS:
        n = SYMBOL.format(e)
        _, la, lab, _, thumb = icon_job((n, S["PR"][pre[e]], None, None))
        write_icon(n, la, lab, thumb)
        icons.append({"n": n, "t": f"{e} damage", "k": "Symbol", "p": pre[e], "p2": None, "g": None, "i": "",
                      "d": e if e in DAMAGE_TYPES else "", "s": "", "split": "symbol", "sec": []})
    p.write_text(json.dumps({"icons": icons}, separators=(",", ":")), encoding="utf-8")
    log(f"[editor] {len(ELEMENTS)} damage-type symbols cut into strokes and listed ({', '.join(f'{e} {pre[e]}' for e in ELEMENTS)})")


def part_render(n, labs, box, preset, kind, px=PART_PX, pad=28):
    """a part as it will look in the editor: its strokes alone, glow grown and coloured (variants.master, the export
    path) in its source icon's colour, cropped square around it (room for the glow), RGBA at px"""
    from .extract import resize
    from .variants import master as vmaster, recipe
    S = state()
    la, lab = read_strokes(n)
    keep = np.isin(lab, labs)
    g = la[..., 0] / 255
    line = np.dstack([g, g, g, la[..., 1] / 255 * keep])
    m = vmaster(line, S["PR"][preset], recipe(S["glyph"], kind, preset))
    t, l, h, w = box
    side = max(h, w) + 2 * pad
    y0, x0 = t + h // 2 - side // 2, l + w // 2 - side // 2
    big = np.zeros((side, side, 4))
    ys, xs = slice(max(y0, 0), min(y0 + side, 512)), slice(max(x0, 0), min(x0 + side, 512))
    big[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0] = m[ys, xs]
    return resize(Image.fromarray(u8(big), "RGBA"), px)


def symbol_cards(IX):
    """the damage-type symbols (symbols()) as part cards: the whole symbol, in its damage colour"""
    from .relations import ELEMENTS
    out = []
    for e in ELEMENTS:
        n = SYMBOL.format(e)
        _, lab = read_strokes(n)
        rr, cc = np.nonzero(lab)
        box = [int(rr.min()), int(cc.min()), int(np.ptp(rr)) + 1, int(np.ptp(cc)) + 1]
        labels = [int(v) for v in np.unique(lab) if v]
        part_render(n, labels, box, IX[n]["p"], "Spell").save(E / "parts" / f"dmg-{e}.png", optimize=True)
        out.append({"id": f"dmg-{e}", "key": f"symbol:{e}", "kind": "symbol", "sym": e, "icons": 1, "series": 0, "icon": n,
                    "labels": labels, "box": box, "size": max(box[2:]), "clutter": 0, "typ": 1, "score": 1})
    return out


def part_thumb(n, labs, box, px=PART_PX):
    """the copy's strokes (soft pixels included) cut from the icon's line art, square, grey + alpha at px"""
    from .extract import resize
    la, lab = read_strokes(n)
    keep = np.isin(lab, labs)
    t, l, h, w = box
    side = max(h, w) + 2 * PAD
    y0, x0 = t + h // 2 - side // 2, l + w // 2 - side // 2
    rgba = np.zeros((side, side, 4), np.uint8)
    ys, xs = np.nonzero(keep)
    rgba[ys - y0, xs - x0] = np.c_[la[ys, xs, 0], la[ys, xs, 0], la[ys, xs, 0], la[ys, xs, 1]]
    return resize(Image.fromarray(rgba, "RGBA"), px)


def parts_panel():
    from .parts import NAMES, FAMILIES, EXCLUDE, unpack
    from .relations import kappa
    PJ = json.loads((D / "parts.json").read_text(encoding="utf-8"))
    Z = np.load(D / "parts.npz")
    ix = {str(n): i for i, n in enumerate(Z["names"])}

    @lru_cache(maxsize=128)
    def strokes_of(n):
        m = unpack(Z["bits"][ix[n]])
        return m, ndimage.label(m, EIGHT)[0]
    (E / "parts").mkdir(parents=True, exist_ok=True)
    IX = {e["n"]: e for e in json.loads((E / "index.json").read_text(encoding="utf-8"))["icons"]}

    def colour_of(n, labs):                    # the source icon's colour for these strokes (D26: its 2nd if they are)
        e = IX[n]
        return e["p2"] if e["p2"] and sum(l in e["sec"] for l in labs) > len(labs) / 2 else e["p"], e["k"]
    groups = sorted(PJ["groups"], key=lambda g: (g["kind"] != "house", -g["icons"]))
    frames = read_list(CATS)                   # eye-checked categories (the prune: frames only)
    cards, kept, sheet = [], [], []
    added, frags = [0], []                     # strokes the completion added; groups whose every copy is a fragment
    for g in groups:
        fam = NAMES.get(g["key"])
        rows = member_stats(g, fam is not None and FAMILIES[fam][0] == "figure", EXCLUDE.get(fam, ()), strokes_of)
        if not rows:
            continue
        rows = best(rows)
        tried = []                             # the best copy that stands alone once completed; if none does, a small part is a
        for k in range(len(rows)):             # detail of larger drawings (hidden), a big one keeps its least crowded copy
            labs = complete(rows, k, strokes_of, frames.get(g["key"]) == "Frames & rings")
            whole = set(labs) | set(rows[k]["labels"])        # the part before prune and strays: never its own clutter
            labs = sorted(set(labs) - strays(rows[k]["icon"], labs, strokes_of))
            tried.append((embedded(rows[k]["icon"], labs, strokes_of, whole), k, labs))
            if tried[-1][0] <= FRAG:
                break
        e, k, labs = tried[-1] if tried[-1][0] <= FRAG else min(tried, key=lambda t: t[0])
        frag = e > FRAG and rows[k]["size"] < SMALL
        b = {**rows[k], "labels": [int(v) for v in labs]}
        shape = np.isin(strokes_of(b["icon"])[1], b["labels"])
        rr, cc = np.nonzero(shape)
        b["box"] = [int(rr.min()), int(cc.min()), int(np.ptp(rr)) + 1, int(np.ptp(cc)) + 1]
        b["size"] = max(b["box"][2:])
        added[0] += len(b["labels"]) - len(rows[k]["labels"])
        if frag:
            frags.append(g["key"])
        ns, mem = norm_shape(shape, b["box"]), {r["icon"] for r in rows}
        # near copy (user 7.0g: "a version with a corner missing"): two cards from 2+ of the same icons where one is 60%+ of
        # the other and lies inside it (own boxes, 2 px slack at 64): the larger one stays
        within = lambda a, b_: a.sum() >= .6 * b_.sum() and (a & ndimage.binary_dilation(b_, iterations=2)).sum() >= SUB * a.sum()
        dup = next((c["id"] for c, (n2, s2, ns2, m2) in zip(cards, kept) if
                    (n2 == b["icon"] and (shape & s2).sum() >= .8 * min(shape.sum(), s2.sum()))
                    or kappa(np.array([ns, ns2], np.float32))[0, 1] >= DUP
                    or (len(mem & m2) >= 2 and ns.sum() <= ns2.sum() and within(ns, ns2))), None)
        sheet.append((g, rows, dup))
        if dup is not None:
            continue
        for i in [i for i, (_, _, ns2, m2) in enumerate(kept) if len(mem & m2) >= 2 and ns2.sum() < ns.sum() and within(ns2, ns)][::-1]:
            log(f"[editor] card {cards[i]['id']} is a near copy of {g['id']}: merged")
            (E / "parts" / f"{cards[i]['id']}.png").unlink(missing_ok=True)
            del cards[i], kept[i]
        part_render(b["icon"], b["labels"], b["box"], *colour_of(b["icon"], b["labels"])).save(E / "parts" / f"{g['id']}.png", optimize=True)
        cards.append({"id": g["id"], "key": g["key"], "kind": g["kind"], "icons": g["icons"], "series": g["series"], "icon": b["icon"],
                      "labels": b["labels"], "box": b["box"], "size": b["size"], "clutter": b["clutter"], "typ": b["typ"],
                      "score": b["score"], "from": sorted(mem)})
        kept.append((b["icon"], shape, ns, mem))
    cards = symbol_cards(IX) + cards
    hid = read_list(HIDDEN)
    new = [k for k in frags if k not in hid]
    if new:
        edit_list(HIDDEN, {k: "a fragment of larger drawings in every copy (auto, panel build)" for k in new})
    log(f"[editor] completion added {added[0]} strokes to the picked copies; {len(frags)} groups are fragments in every "
        f"copy ({len(new)} newly hidden)")
    (E / "parts.json").write_text(json.dumps({"parts": cards}, separators=(",", ":")), encoding="utf-8")
    picked_first = [r for _, rows, d in sheet if d is None for r in rows[:1]]
    log(f"[editor] parts panel: {len(cards)} cards from {len(sheet)} groups ({sum(d is not None for *_, d in sheet)} the same "
        f"shape as an earlier card); best copy: size px p10/50/90 "
        f"{np.percentile([r['size'] for r in picked_first], [10, 50, 90]).round().tolist()}, clutter "
        f"{np.percentile([r['clutter'] for r in picked_first], [50, 90]).round(3).tolist()}, typicality "
        f"{np.percentile([r['typ'] for r in picked_first], [10, 50]).round(3).tolist()}; largest member picked in "
        f"{sum(r['size'] == max(x['size'] for x in rows) for _, rows, d in sheet if d is None for r in rows[:1])} of {len(cards)}")
    parts_sheet(sheet, strokes_of)


def parts_sheet(sheet, strokes_of, per=6, tile=112, rows_max=60):
    """check sheet: per group (house first, biggest first) the picked copy (first, amber frame) and the next members by
    score; amber = the whole shape, grey = the rest of the icon; caption size px / clutter / typicality"""
    sel = [s for s in sheet if s[2] is None][:rows_max]
    W, H = 150 + per * (tile + 6), len(sel) * (tile + 22) + 10
    im = Image.new("RGB", (W, H), (24, 22, 20))
    dr = ImageDraw.Draw(im)
    for i, (g, rows, _) in enumerate(sel):
        y = 5 + i * (tile + 22)
        dr.text((6, y + 4), f"group {g['id']} ({g['kind']})\n{g['icons']} icons, {g['series']} series", fill=(220, 210, 190))
        for j, r in enumerate(rows[:per]):
            m, L8 = strokes_of(r["icon"])
            sh = np.isin(L8, r["labels"])
            rgb = np.zeros((512, 512, 3), np.uint8)
            rgb[m] = (90, 90, 90)
            rgb[sh] = (255, 190, 60)
            x = 150 + j * (tile + 6)
            im.paste(Image.fromarray(rgb).resize((tile, tile), Image.BOX), (x, y))
            if j == 0:
                dr.rectangle((x - 2, y - 2, x + tile + 1, y + tile + 1), outline=(255, 190, 60), width=2)
            dr.text((x, y + tile + 2), f"{r['size']} / {r['clutter']:.2f} / {r['typ']:.2f}", fill=(200, 200, 200))
    im.save(E / "parts_sheet.png")
    log(f"[editor] wrote {E / 'parts_sheet.png'} ({len(sel)} groups: picked copy first; size px / clutter / typicality)")


# ---------------------------------------------------------------- house brush (D44): measured against the game
# The brush itself is app/brush.js (rendered in the browser so roughness, taper, width and spline points stay editable).
# Here: the game's strokes measured along their centre line (chains, edges), test sections for the browser harness
# (/?brushtest) and the measure of what it drew (brush_measure: same centre line, same width, same measure).
CHAIN_MIN, CHAIN_CUT, TIP_CUT, WIDTH_OK = 48, 8, 32, (8, 24)   # px: chain length kept, trimmed off each end (TIP_CUT
# next to a real stroke end: the taper is the brush's Tip setting, not edge variation); widths measured


def chains(sk):
    """skeleton -> ordered pixel chains (y, x) between ends and junctions (junction neighbourhoods cut out), each with
    whether its first / last point is a real stroke end (a tip) rather than a cut at a junction"""
    nb = ndimage.convolve(sk.astype(int), np.ones((3, 3), int), mode="constant") - 1
    S = sk & ~ndimage.binary_dilation(sk & (nb >= 3), EIGHT)
    lab, _ = ndimage.label(S, EIGHT)
    out = []
    for sl in ndimage.find_objects(lab):
        if sl is None:
            continue
        ys, xs = np.nonzero(lab[sl] == lab[sl][lab[sl] > 0][0])
        if len(ys) < CHAIN_MIN:
            continue
        pts = set(zip((ys + sl[0].start).tolist(), (xs + sl[1].start).tolist()))
        nbr = lambda p: [(p[0] + dy, p[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx) and (p[0] + dy, p[1] + dx) in pts]
        start = next((p for p in pts if len(nbr(p)) == 1), None)
        if start is None:                                     # a closed loop: no end
            continue
        seq, seen = [start], {start}
        while True:
            nx = [q for q in nbr(seq[-1]) if q not in seen]
            if not nx:
                break
            seq.append(min(nx, key=lambda q: abs(q[0] - seq[-1][0]) + abs(q[1] - seq[-1][1])))   # 4-neighbours first
            seen.add(seq[-1])
        if len(seq) >= CHAIN_MIN:
            out.append((np.array(seq, float), nb[seq[0]] == 1, nb[seq[-1]] == 1))
    return out


def edges(alpha, grey, pts, smooth=2.0):
    """a chain of centre points (y, x) -> per point left / right half width (first alpha < .5 along the normal, linear
    between .25 px steps), core grey, the smoothed points; NaN where no edge within 24 px"""
    p = ndimage.gaussian_filter1d(pts, smooth, axis=0, mode="nearest")
    t = np.gradient(p, axis=0)
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-6)[:, None]
    nl = np.stack([t[:, 1], -t[:, 0]], 1)
    r = np.arange(0, 24, .25)
    out = []
    for n in (nl, -nl):
        yy, xx = p[:, None, 0] + r * n[:, None, 0], p[:, None, 1] + r * n[:, None, 1]
        a = ndimage.map_coordinates(alpha, [yy, xx], order=1, mode="constant")
        k = np.argmax(a < .5, 1)
        ok = (a[np.arange(len(a)), k] < .5) & (k > 0)
        a0, a1 = a[np.arange(len(a)), k - 1], a[np.arange(len(a)), k]
        out.append(np.where(ok, r[k - 1] + .25 * (a0 - .5) / np.maximum(a0 - a1, 1e-6), np.nan))
    g = ndimage.map_coordinates(grey, [p[:, 0], p[:, 1]], order=1)
    return out[0], out[1], g, p


def section_stats(hl, hr):
    """half-width variation by scale over the section's median half width: width (both sides) slow / mid / fine,
    centre wander mid / fine (stroke_scales probe's measure)"""
    g = lambda v, s: ndimage.gaussian_filter1d(v, s, mode="nearest")
    m = np.median(np.r_[hl, hr])
    w, o = (hl + hr) / 2 / m, (hl - hr) / 2 / m
    return {"w_slow": float(np.std(g(w, 15))), "w_mid": float(np.std(g(w, 3) - g(w, 15))), "w_fine": float(np.std(w - g(w, 3))),
            "o_mid": float(np.std(g(o, 3) - g(o, 15))), "o_fine": float(np.std(o - g(o, 3)))}


@lru_cache(maxsize=1)
def brush_sections(k=40):
    """hold-out spells / actions: stroke sections with their centre line (x, y), width and the game's stats; and the
    game's tip taper (width over the section's median at 0, 2, ... 38 px from a real stroke end)"""
    from .lab import skeletonize
    idx = json.loads((E / "index.json").read_text(encoding="utf-8"))["icons"]
    out, tips = [], []
    for e in [e for e in idx if e["split"] == "holdout" and e["k"] != "Illithid"][:k]:
        la, lab = read_strokes(e["n"])
        a, g = la[..., 1] / 255, la[..., 0] / 255
        for pts, ta, tb in chains(skeletonize(a >= .5)):
            hl, hr, _, p = edges(a, g, pts)
            c = slice(TIP_CUT if ta else CHAIN_CUT, len(pts) - (TIP_CUT if tb else CHAIN_CUT))
            if c.stop - c.start < 32 or np.isnan(hl[c]).any() or np.isnan(hr[c]).any() or not WIDTH_OK[0] <= np.median(hl[c] + hr[c]) <= WIDTH_OK[1]:
                continue
            m = np.median(hl[c] + hr[c])
            for tip, h in ((ta, hl + hr), (tb, (hl + hr)[::-1])):
                if tip and len(h) >= 60 and not np.isnan(h[:40]).any():
                    tips.append(h[:40] / m)
            sid = lab[int(pts[len(pts) // 2, 0]), int(pts[len(pts) // 2, 1])]
            out.append({"icon": e["n"], "preset": e["p"], "kind": e["k"], "sid": int(sid), "pts": pts, "cut": [c.start, c.stop],
                        "path": p[:, ::-1].round(2).tolist(), "width": round(float(m), 2), "game": section_stats(hl[c], hr[c])})
    return {"sections": out, "tips": np.median(tips, 0)[::2].round(2).tolist() if tips else []}


def brush_samples_req(q):
    return {"sections": [{"i": i, "path": s["path"], "width": s["width"], "kind": s["kind"]} for i, s in enumerate(brush_sections()["sections"])]}


def brush_measure_req(q):
    """the browser's renders of every test section (tag -> [{i, png, x0, y0}]) -> stats per tag vs the game's (medians)
    and a sheet (game | each tag) data/editor/brush_compare.png"""
    from .variants import paint, recipe
    S, B_, keys = state(), brush_sections(), ("w_slow", "w_mid", "w_fine", "o_mid", "o_fine")
    secs = B_["sections"]
    res, drawn = {"game": [s["game"] for s in secs]}, {}
    for tag, rs in q["renders"].items():
        res[tag] = []
        for r in rs:
            s = secs[r["i"]]
            img = (png_in(r["png"], "RGB") * 255).astype(np.uint8)
            canvas = np.zeros((512, 512, 2))
            x0, y0, (hh, ww) = int(r["x0"]), int(r["y0"]), img.shape[:2]
            ys, xs = slice(max(y0, 0), min(y0 + hh, 512)), slice(max(x0, 0), min(x0 + ww, 512))
            canvas[ys, xs] = img[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0, :2] / 255
            hl, hr, _, _ = edges(canvas[..., 1], canvas[..., 0], s["pts"])
            c = slice(*s["cut"])
            if not (np.isnan(hl[c]).any() or np.isnan(hr[c]).any()):
                res[tag].append(section_stats(hl[c], hr[c]))
            drawn[(tag, r["i"])] = canvas
    out = {tag: {"n": len(rs), **{k: round(float(np.median([x[k] for x in rs])), 4) for k in keys}} for tag, rs in res.items()}
    out["game_tips"] = B_["tips"]
    pick = [i for i, s in enumerate(secs) if len(s["pts"]) > 90][:10]
    T, tags = 160, list(q["renders"])
    im = Image.new("RGB", ((len(tags) + 1) * (T + 6), len(pick) * (T + 6)), (20, 20, 20))
    for row, i in enumerate(pick):
        s = secs[i]
        la, lab = read_strokes(s["icon"])
        game = np.dstack([la[..., 0] / 255, la[..., 1] / 255 * (lab == s["sid"])])
        p, th = S["PR"][s["preset"]], recipe(S["glyph"], s["kind"], s["preset"])
        y0, x0 = (s["pts"].min(0) - 24).clip(0).astype(int)
        side = int(max(np.ptp(s["pts"], 0)) + 48)
        for col, la_ in enumerate([game] + [drawn.get((t, i), np.zeros((512, 512, 2))) for t in tags]):
            m = paint(np.dstack([la_[..., :1].repeat(3, -1), la_[..., 1:]]), p, th)
            over = (m[..., :3] * m[..., 3:] + DARK * (1 - m[..., 3:]))[y0:y0 + side, x0:x0 + side]
            im.paste(Image.fromarray(u8(over)).resize((T, T), Image.LANCZOS), (col * (T + 6), row * (T + 6)))
    im.save(E / "brush_compare.png")
    log(f"[editor] brush vs game (medians over {len(secs)} hold-out sections): {out}; sheet {E / 'brush_compare.png'} "
        f"(game | {' | '.join(tags)})")
    return out


# ---------------------------------------------------------------- server
OUT = D.parent / "outputs" / "editor"
PREFIX = {"Spell": "Spell", "Action": "Action", "Illithid": "TadpoleSuperPower"}   # hotbar.kind reads the name's prefix
INTENTS = ("Damage", "Utility", "Buff", "Control", "Summon", "Debuff", "Healing")
_state, _lock = {}, threading.Lock()
SLOW = 2                                  # s: requests slower than this are logged


def state():
    """recipes, presets, hotbar frames and backgrounds, loaded once (backgrounds come from the user's game files, D10)"""
    with _lock:
        if not _state:
            from . import hotbar
            for k in ("glyph", "grammar", "hotbar", "links"):
                _state[k] = json.loads((D / f"{k}.json").read_text(encoding="utf-8"))
            _state["PR"] = {p["name"]: p for p in _state["grammar"]["presets"]}
            _state["B"] = hotbar.backgrounds()
            for p in json.loads(CUSTOM.read_text(encoding="utf-8")) if CUSTOM.exists() else []:
                register(_state, p)
        return _state


def recipes():
    """what the browser needs to paint and to fill the fields: presets (lq, lut), glow recipes, colour defaults
    (grammar groups), hotbar frames per preset (D19-D21) with each background's typical gain"""
    from .extract import DAMAGE_TYPES
    from .hotbar import FRAMED
    S = state()
    G, H, J = S["grammar"], S["hotbar"], S["glyph"]
    gains = {}
    for fr in (H["frames"], H["frames_illithid"]):
        for es in fr.values():
            for e in es:
                gains.setdefault(e[0], []).append(e[1])
    from .grammar import preset_lab
    from .lab import lab2rgb
    hexes = lambda p: ["#%02x%02x%02x" % tuple(u8(c)) for c in lab2rgb(preset_lab(p, np.linspace(35, 92, 6)))]
    return {"presets": [{"name": p["name"], "lq": p["lq"], "lut": p["lut"], "swatch": hexes(p), **({"custom": p["custom"]} if "custom" in p else {})}
                        for p in G["presets"]],
            "glow": J["glow"], "borrow": J["borrow"], "groups": G["groups"], "dark": DARK.tolist(),
            "frames": H["frames"], "nearest": H["nearest"], "frames_illithid": H["frames_illithid"],
            "nearest_illithid": H["nearest_illithid"], "frame_two_tone": H["frame_two_tone"], "framed": list(FRAMED),
            "gain": {k: round(float(np.median(v)), 3) for k, v in gains.items()},
            "intents": INTENTS, "damage": sorted(DAMAGE_TYPES), "sources": sorted(set(S["links"]["sources"].values()))}


# ---------------------------------------------------------------- custom colours (user 7.0h: modders' own colours)
# A custom colour is a preset like the game's 31 (curve = a*b* per lightness bin, lq = lightness at each grey level, lut =
# a*b* by lightness x opacity x distance from the centre), kept in outputs/editor/presets.json and named "Custom: ...".
# The light ramp (lq) is always a game preset's, so lines stay bright and glows soft as in the game; only the colour is
# the modder's. Glow recipe, hotbar recipe and frames are borrowed from the nearest game preset.
CUSTOM = OUT / "presets.json"


def mid_ab(p):
    c = np.array(p["curve"], float)
    return c[len(c) // 2]


def register(S, p):
    """put a custom preset into the loaded state (in memory only): presets, frames / glow recipes borrowed from the
    game preset nearest in colour"""
    from .hotbar import preset_ab
    base = [q for q in S["grammar"]["presets"] if "custom" not in q]
    G, H, J = S["grammar"], S["hotbar"], S["glyph"]
    G["presets"] = [q for q in G["presets"] if q["name"] != p["name"]] + [p]
    S["PR"][p["name"]] = p
    near = lambda pool: min(pool, key=lambda q: float(np.linalg.norm(preset_ab(S["PR"][q]) - preset_ab(p))))
    H["nearest"][p["name"]] = near([q["name"] for q in base if q["name"] in H["frames"]])
    H["nearest_illithid"][p["name"]] = near([q["name"] for q in base if q["name"] in H["frames_illithid"]])
    for kd in ("Spell", "Action", "Illithid"):
        own = near([q["name"] for q in base if f"{kd}|{q['name']}" in J["glow"]] or [base[0]["name"]])
        if f"{kd}|{own}" in J["glow"]:
            J["borrow"][f"{kd}|{p['name']}"] = f"{kd}|{own}"


def custom_preset(S, label, stops):
    """stops = 1-4 colours (#rrggbb). One colour: the nearest game preset's gradient turned to its hue and chroma (the
    game's shape: chroma by lightness and the glow / core differences in the lut kept). Two or more: their a*b* laid out
    along lightness (each stop at its own L*, clamped at the ends), the same at every opacity and distance."""
    from .grammar import LC
    from .lab import rgb2lab
    lab = rgb2lab(np.array([[int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)] for h in stops], float)[None])[0]
    base = [q for q in S["grammar"]["presets"] if "custom" not in q]
    if len(stops) == 1:
        ab = lab[0, 1:]
        q = min(base, key=lambda q: float(np.linalg.norm(mid_ab(q) - ab)) if np.hypot(*ab) > 6 else float(np.hypot(*mid_ab(q))))
        m = mid_ab(q)
        rot = np.arctan2(ab[1], ab[0]) - np.arctan2(m[1], m[0])
        k = np.clip(np.hypot(*ab) / max(np.hypot(*m), 1e-3), .15, 3)
        R = k * np.array([[np.cos(rot), -np.sin(rot)], [np.sin(rot), np.cos(rot)]])
        turn = lambda a: (np.asarray(a, float) @ R.T).round(2).tolist()
        curve, lut = turn(q["curve"]), turn(q["lut"])
    else:
        o = lab[np.argsort(lab[:, 0])]
        cur = np.stack([np.interp(LC, o[:, 0], o[:, 1]), np.interp(LC, o[:, 0], o[:, 2])], 1)
        q = min(base, key=lambda q: float(np.nanmean(np.linalg.norm(np.array(q["curve"], float) - cur, axis=1))))
        curve = cur.round(2).tolist()
        lut = np.broadcast_to(cur[:, None, None, :], (len(LC), 4, 4, 2)).round(2).tolist()
    name = "Custom: " + (" ".join(str(label or "").split())[:40] or "colour")
    return {"name": name, "curve": curve, "lq": q["lq"], "lut": lut, "custom": {"stops": list(stops), "base": q["name"]}}


def presets_req(q):
    """custom colours: {stops, label} -> made and saved (preview: true -> made, not saved); {delete: name} -> removed.
    -> {preset name, recipes (the browser's whole colour data again)}"""
    S = state()
    saved = json.loads(CUSTOM.read_text(encoding="utf-8")) if CUSTOM.exists() else []
    if q.get("delete"):
        name = q["delete"]
        saved = [p for p in saved if p["name"] != name]
        S["grammar"]["presets"] = [p for p in S["grammar"]["presets"] if p["name"] != name]
        S["PR"].pop(name, None)
        out = None
    else:
        stops = [s for s in q.get("stops", []) if isinstance(s, str) and len(s.lstrip("#")) == 6][:4]
        assert stops, "pick at least one colour"
        p = custom_preset(S, "Preview" if q.get("preview") else q.get("label"), stops)
        register(S, p)
        out = p["name"]
        if not q.get("preview"):
            saved = [s for s in saved if s["name"] != p["name"]] + [p]
    CUSTOM.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM.write_text(json.dumps(saved), encoding="utf-8")
    return {"name": out, "recipes": recipes()}


# ---------------------------------------------------------------- import: modders' own icons (user 7.0h)
# Files come grouped by icon (the file name without extension): a source image (any size; 512 PNGs best), and / or the
# game files a mod ships: the tooltip icon (380 px, GUI/Assets/Tooltips/Icons, faded at the bottom, D13) and the
# controller icon (144 px, ControllerUIIcons/skills_png, not faded). Tooltip + controller are joined: the tooltip's rows
# un-faded where the fade leaves enough, the controller's below. The colour is the nearest game colour when it rebuilds
# the icon about as well as a colour fitted on the icon itself, else that fitted colour is saved as a custom colour (one
# per look: icons of one mod share it). Then the icon is cut into strokes like a game icon.
IMP = OUT / "imported"
IMP_DE = 3.0          # mean dE76 over the hotbar dark: a game colour this much worse than the icon's own is not used


def imp_load(data):
    """base64 / data URL of a PNG, DDS, TGA, WebP or JPEG -> RGBA float"""
    b = base64.b64decode(data.split(",", 1)[-1])
    return np.asarray(Image.open(io.BytesIO(b)).convert("RGBA")).astype(np.float64) / 255


def to512(x):
    """RGBA float any size -> 512, premultiplied Lanczos"""
    if x.shape[0] == 512 and x.shape[1] == 512:
        return x
    pm = np.dstack([x[..., :3] * x[..., 3:], x[..., 3]]).astype(np.float32)
    up = np.dstack([np.asarray(Image.fromarray(pm[..., c], "F").resize((512, 512), Image.LANCZOS)) for c in range(4)]).clip(0, 1)
    a = up[..., 3:]
    return np.dstack([np.where(a > 1e-4, up[..., :3] / np.maximum(a, 1e-4), 0).clip(0, 1), a]).astype(np.float64)


def imp_master(files):
    """[{path, data}] of one icon -> (master 512 RGBA float, what was used, rows from the top that show the icon as it
    is: a rebuilt fade has the strokes but not the glow, so colour and look are scored above it)"""
    from .fade import bottom_fade
    ims = [(f["path"], imp_load(f["data"])) for f in files]
    dds = lambda p: p.lower().endswith(".dds")                # a 380 / 144 px DDS is a game file even without its folder
    tier = lambda p, x: ("tooltip" if "tooltip" in p.lower() or dds(p) and x.shape[0] == 380 else
                         "controller" if "controller" in p.lower() or dds(p) and x.shape[0] == 144 else "source")
    by = {}
    for p, x in sorted(ims, key=lambda t: -t[1].shape[0]):
        by.setdefault(tier(p, x), x)
    if "source" in by and by["source"].shape[0] >= 256 or not ({"tooltip", "controller"} & set(by)):
        return to512(by["source"]), f"From an image ({by['source'].shape[1]} px)", 512
    c = to512(by["controller"]) if "controller" in by else None
    if "tooltip" not in by:
        return c, "From the controller icon (144 px)", 512
    t = to512(by["tooltip"])
    f = bottom_fade(512)[:, :1].astype(np.float64)
    tu = np.dstack([t[..., :3], np.where(f > .05, t[..., 3:] / np.maximum(f, .05), t[..., 3:]).clip(0, 1)])
    x, fit = unfade(by["tooltip"])                   # sharper than joining in the 144 px controller icon (its glow upscaled
    if fit >= UNFADE_FIT:                            # reads as haze lines): the controller only when the colours fail
        return x, f"From the tooltip icon (380 px); faded strokes rebuilt from its colours", int((bottom_fade(512)[:, 0] > .6).sum())
    if c is None:
        return tu, f"From the tooltip icon (380 px); the faded bottom stays faint", int((bottom_fade(512)[:, 0] > .6).sum())
    # the controller icon alone: its lines match the game's as well as the tooltip's (IoU .94 at 512 on 30 hold-out icons)
    # and blending the two doubled strokes where they are a pixel apart (False Life's wreath)
    return c, f"From the controller icon (144 px)", 512


UNFADE_FIT, UNFADE_W = .6, 6.0         # below .6 the colours don't show the lines (premultiplied or flat RGB)


def unfade(t):
    """faded tooltip icon (RGBA float, any size) -> 512 master with its faded strokes rebuilt (user 7.0h: "reconstruct
    them into the non-faded versions ... we would only need to recover the strokes"). The fade only scales alpha: the
    colour channels still draw every stroke (game tooltips: colour dE76 0.8-3.2 vs the unfaded art even at fade < .05),
    while alpha / fade turns the faded rows to haze. So: on the unfaded rows (fade > .6) find the RGB lightness that
    best separates the lines found the usual way; below, line share = a soft ramp around it (alpha / fade where the fade
    is mild). The glow is regrown by the editor and the colour comes from the gradient, so only the strokes matter. 30
    hold-out icons, line IoU vs the game's master: fade < .5 0.26 -> 0.91, < .2 0.11 -> 0.88, < .05 0 -> 0.64 (the controller icon
    0.94). -> (master, IoU of the threshold on the unfaded rows: low = the colours don't carry the lines)"""
    from .fade import bottom_fade
    from .lab import rgb2lab
    F = bottom_fade(512)[:, :1].astype(np.float64)
    x = to512(np.dstack([t[..., :3], np.ones(t.shape[:2])]))
    a = to512(t)[..., 3]
    au = np.where(F > .05, a / np.maximum(F, .05), a).clip(0, 1)
    line = split(np.dstack([x[..., :3], au]), 512)["AL"] > .5
    L, top = rgb2lab(x[..., :3])[..., 0], (F > .6)[:, 0]
    ths = np.arange(20, 100, 1.0)
    iou = [((L > th) & line)[top].sum() / max(((L > th) | line)[top].sum(), 1) for th in ths]
    th = ths[int(np.argmax(iou))]
    share = np.clip((L - th) / UNFADE_W + .5, 0, 1)
    # evidence: a line pixel keeps alpha ~ fade, so where the fade leaves any alpha (>= .05) a colour line needs alpha
    # / fade over .25; in the last rows (alpha all 0) only colour lines that continue a stroke from above count (colour
    # bleeding into transparent border pixels made strips along the edges)
    ok = np.where(F >= .05, au > .25, True)
    C = ndimage.label((share > .5) & ok, EIGHT)[0]
    keep = np.unique(C[((F >= .05) & np.ones_like(share, bool)) & (C > 0)])
    share = share * np.isin(C, keep) * ok
    w = np.broadcast_to(np.clip((F - .3) / .3, 0, 1), a.shape)
    return np.dstack([x[..., :3], w * au + (1 - w) * share]), float(max(iou))


def own_colour(x, name):
    """a preset fitted on one icon (grammar.fit_lut on one member): curve, lq and lut from its own pixels"""
    from .grammar import NB, LC, Q, radius
    from .lab import rgb2lab
    xs = np.asarray(Image.fromarray(u8(x), "RGBA").resize((128, 128), Image.BOX)).astype(np.float64) / 255
    m = xs[..., 3] > .02
    lab, al, R = rgb2lab(xs[..., :3])[m], xs[..., 3][m], radius(128, 128)[m]
    bi = np.clip((lab[:, 0] / 100 * NB).astype(int), 0, NB - 1)
    s, c = np.zeros((NB, 4, 4, 2)), np.zeros((NB, 4, 4))
    idx = (bi, np.digitize(al, [.2, .5, .85]), np.minimum((R * 4).astype(int), 3))
    np.add.at(s, idx, lab[:, 1:]); np.add.at(c, idx, 1)
    s1, c1 = s.sum((1, 2)), c.sum((1, 2))
    ok = c1 > 0
    cur = np.stack([np.interp(LC, LC[ok], s1[ok, j] / c1[ok]) for j in range(2)], 1)
    lut = np.where(c[..., None] >= 20, s / np.maximum(c, 1)[..., None], cur[:, None, None, :])
    return {"name": name, "curve": cur.round(2).tolist(), "lq": np.quantile(lab[:, 0], Q).round(2).tolist(),
            "lut": lut.round(2).tolist(), "custom": {"stops": [], "base": None, "from": "imported icon"}}


def colour_err(x, la, p, th, rows=512):
    """mean dE76 between an icon and its rebuild in preset p, over the hotbar dark, where either shows anything"""
    from .variants import master as vmaster
    from .lab import rgb2lab
    m = vmaster(la, p, th)
    over = lambda z: rgb2lab(z[..., :3] * z[..., 3:] + DARK * (1 - z[..., 3:]))
    vis = (x[..., 3] > .05) | (m[..., 3] > .05)
    vis[rows:] = False
    return float(np.linalg.norm(over(x)[vis] - over(m)[vis], axis=1).mean()), m


def imp_icon(S, name, files):
    """one icon -> index entry (written to outputs/editor/imported)"""
    from .glyph import seen_err
    from .variants import line_art, recipe
    x, used, rows = imp_master(files)
    words = set(re.split(r"[^a-z0-9]+", name.lower()))                     # Mod_Action_Rush, Spell_Fire_X, TadpoleSuperPower_Y
    kd = ("Illithid" if "tadpolesuperpower" in words or "illithid" in words else "Action" if words & {"action", "skill", "attack"} and "spell" not in words
          else "Spell")
    small = np.asarray(Image.fromarray(u8(x), "RGBA").resize((128, 128), Image.BOX)).astype(np.float64) / 255
    games = [p for p in S["grammar"]["presets"] if "custom" not in p]
    # the nearest few game colours by their curve (mean a*b* per lightness bin), then the best rebuild among them
    from .grammar import NB
    from .lab import rgb2lab
    lab = rgb2lab(small[..., :3])[small[..., 3] > .3]
    bi = np.clip((lab[:, 0] / 100 * NB).astype(int), 0, NB - 1)
    cur = np.array([lab[bi == b, 1:].mean(0) if (bi == b).sum() >= 8 else [np.nan, np.nan] for b in range(NB)])
    d = lambda p: float(np.nanmean(np.linalg.norm(np.array(p["curve"], float) - cur, axis=1))) if np.isfinite(cur).any() else 0.0
    cand = sorted(games, key=d)[:3]
    tries = [(colour_err(x, line_art(x, p), p, recipe(S["glyph"], kd, p["name"]), rows)[0], p) for p in cand]
    err, p = min(tries, key=lambda t: t[0])
    own = own_colour(x, "Custom: " + name)
    own_err = colour_err(x, line_art(x, own), own, recipe(S["glyph"], kd, cand[0]["name"]), rows)[0]
    if err > own_err + IMP_DE:                               # no game colour is close: the icon's own colour (or one like it)
        same = [q for q in S["grammar"]["presets"] if "custom" in q and q["custom"].get("from") == "imported icon"]
        reuse = [(colour_err(x, line_art(x, q), q, recipe(S["glyph"], kd, q["name"]), rows)[0], q) for q in same]
        best = min(reuse, key=lambda t: t[0]) if reuse else None
        if best and best[0] <= own_err + IMP_DE / 2:
            err, p = best
        else:
            register(S, own)
            saved = json.loads(CUSTOM.read_text(encoding="utf-8")) if CUSTOM.exists() else []
            CUSTOM.parent.mkdir(parents=True, exist_ok=True)
            CUSTOM.write_text(json.dumps([s for s in saved if s["name"] != own["name"]] + [own]), encoding="utf-8")
            err, p = own_err, own
    la, lab_, sec, thumb = cut(x, p)
    n = "Imp_" + ident(name)
    for sub in ("icons", "thumbs"):
        (IMP / sub).mkdir(parents=True, exist_ok=True)
    write_icon(n, la, lab_, thumb, IMP)
    ic, sm = split(x, 512), split(V_master(la, p, recipe(S["glyph"], kd, p["name"])), 512)
    look = seen_err({k: v[:rows] for k, v in ic.items()}, sm["B"][:rows], sm["a"][:rows])
    lines = float((ic["AL"] > .5).mean())
    note = "" if look < 6 else "Looks different here: painted or textured shading can't be kept"
    return {"n": n, "t": name, "k": kd, "p": p["name"], "p2": None, "g": None, "i": "", "d": "", "s": "", "split": "import",
            "sec": [], "src": "import", "key": name, "used": used, "err": round(err, 2), "look": round(look, 2),
            "lines": round(lines, 3), "custom": "custom" in p, "note": note}


def V_master(la, p, th):
    from .variants import master as vmaster
    return vmaster(np.dstack([la[..., :1].repeat(3, -1), la[..., 1:]]).astype(np.float64) / 255, p, th)


def import_req(q):
    """{icons: [{name, files: [{path, data}]}]} -> {icons: [index entries], recipes} (the imported folder's index.json
    keeps every icon imported so far; a name imported again replaces the old one)"""
    S = state()
    idx_f = IMP / "index.json"
    idx = json.loads(idx_f.read_text(encoding="utf-8"))["icons"] if idx_f.exists() else []
    out, errors = [], []
    for ic in q.get("icons", []):
        name = re.sub(r"[^A-Za-z0-9_]", "_", Path(ic["name"]).stem) or "Icon"   # the icon's own name: the mod's spells use it
        try:
            e = imp_icon(S, name, ic["files"])
        except Exception as ex:                              # one bad file never stops the others
            errors.append(f"{ic['name']}: {type(ex).__name__}: {ex}")
            continue
        idx = [i for i in idx if i["n"] != e["n"]] + [e]
        out.append(e)
        log(f"[editor] imported {name} ({e['used']}): {e['p']}, colour dE {e['err']}, look {e['look']} L*")
    IMP.mkdir(parents=True, exist_ok=True)
    idx_f.write_text(json.dumps({"icons": idx}, separators=(",", ":")), encoding="utf-8")
    return {"icons": out, "errors": errors, "recipes": recipes()}


def imported_req(q):
    """the imported icons so far (index entries); {delete: n} removes one"""
    idx_f = IMP / "index.json"
    idx = json.loads(idx_f.read_text(encoding="utf-8"))["icons"] if idx_f.exists() else []
    if q.get("delete"):
        idx = [i for i in idx if i["n"] != q["delete"]]
        idx_f.write_text(json.dumps({"icons": idx}, separators=(",", ":")), encoding="utf-8")
        for f in (IMP / "icons" / f"{q['delete']}.png", IMP / "icons" / f"{q['delete']}.lab.png", IMP / "thumbs" / f"{q['delete']}.png"):
            f.unlink(missing_ok=True)
    return {"icons": idx}


def png_in(url, mode="RGBA"):
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert(mode)).astype(np.float64) / 255


def png_out(im, fmt="PNG"):
    """PIL image -> data URL. Fully transparent pixels get black RGB first (invisible, and the file shrinks); WEBP =
    lossless WebP (the same pixels, ~40% smaller than PNG; 2048 px in ~2 s)"""
    if im.mode == "RGBA":
        a = np.asarray(im).copy()
        a[a[..., 3] == 0, :3] = 0
        im = Image.fromarray(a, "RGBA")
    b = io.BytesIO()
    im.save(b, fmt, **({"lossless": True, "method": 4, "quality": 50} if fmt == "WEBP" else {}))
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(b.getvalue()).decode()


def paint_req(q):
    """request -> (master RGBA float, preset, second preset, frame entry, kind) through variants.master (export path)"""
    from .variants import master as vmaster, recipe
    S = state()
    la = png_in(q["lineart"])
    la = np.dstack([la[..., :1].repeat(3, -1), la[..., 3]])
    kd, p, p2 = q["kind"], q["preset"], q.get("second") or None
    second = None
    if p2 and q.get("mask"):
        strokes = png_in(q["mask"])[..., 3] > 0
        second = (strokes, S["PR"][p2], recipe(S["glyph"], kd, p2)) if strokes.any() else None
    m = vmaster(la, S["PR"][p], recipe(S["glyph"], kd, p), second)
    return m, p, second and p2, q.get("frame") or None, kd


def hotbar_req(q):
    """the WebGL master -> the 64 px PC hotbar cell (hotbar.compose: the PC recipe is not ported to the GPU)"""
    from .hotbar import compose
    S = state()
    m = png_in(q["master"])
    who = f"{PREFIX[q['kind']]}_Preview"
    cell = compose(u8(m), who, q["preset"], S["hotbar"], S["B"], q.get("frame") or None, second=q.get("second") or None)
    return {"hotbar": png_out(Image.fromarray(u8(cell)))}


def ident(s, camel=False):
    w = "".join(c if c.isalnum() else " " for c in s).split()
    return "".join(x[:1].upper() + x[1:] for x in w) if camel else "_".join(w)


def export_req(q):
    """draft -> master (variants.master) -> PNGs + the whole mod rebuilt from every icon exported to it so far
    (outputs/editor/<Mod>/: icons/ masters + settings, drafts/ line art, png/, mod/ files to merge into the mod)"""
    from .variants import variants, pngs, export
    S = state()
    mod, name = ident(q.get("mod") or "MyIcons", True) or "MyIcons", ident(q.get("name") or "Icon", True) or "Icon"
    m, p, p2, fr, kd = paint_req(q)
    # the icon's name in the game: the tab's own (an imported icon keeps the name its mod's spells use), else Mod_Kind_Name
    key = re.sub(r"[^A-Za-z0-9_]", "", q.get("key") or "") or f"{mod}_{PREFIX[kd]}_{name}"
    who = lambda k, kind: k if k.startswith(PREFIX[kind]) else f"{PREFIX[kind]}_{k}"   # hotbar.kind reads the prefix
    out = OUT / mod
    for d in ("icons", "drafts"):
        (out / d).mkdir(parents=True, exist_ok=True)
    Image.fromarray(u8(m), "RGBA").save(out / "icons" / f"{key}.png")
    (out / "icons" / f"{key}.json").write_text(json.dumps({"preset": p, "second": p2, "frame": fr, "kind": kd,
                                                           "fields": q.get("fields", {})}, indent=1), encoding="utf-8")
    what = {"lineart": True, "pngs": True, "mod": True, **(q.get("what") or {})}   # the dialog's choices (default: all)
    files = []
    if what["lineart"]:
        Image.fromarray(u8(png_in(q["lineart"])), "RGBA").save(out / "drafts" / f"{key}_lineart.png")
        files.append(out / "drafts" / f"{key}_lineart.png")
    if what["pngs"]:
        files += pngs(m, who(key, kd), p, out / "png", key, (512,), S["hotbar"], S["B"], p2, fr)
    hr = q.get("hires") if what["pngs"] else None
    if hr:                                     # the browser flattened the drawing at this size (brush strokes re-rendered
        from .variants import sized            # sharp); the glow is grown at that size (glyph.glow scales its blurs)
        mR = paint_req({**q, "lineart": hr["lineart"], "mask": hr.get("mask")})[0]
        for fade, tag in ((False, ""), (True, "_tooltip")):
            files.append(out / "png" / f"{key}_{mR.shape[0]}{tag}.png")
            sized(mR, mR.shape[0], fade).save(files[-1])
    icons = {}
    for f in sorted((out / "icons").glob("*.json")) if what["mod"] else ():
        meta = json.loads(f.read_text(encoding="utf-8"))
        mm = np.asarray(Image.open(f.with_suffix(".png")).convert("RGBA")).astype(np.float64) / 255
        icons[f.stem] = variants(mm, who(f.stem, meta["kind"]), meta["preset"], S["hotbar"], S["B"], meta["second"], meta["frame"])
    if what["mod"]:
        files += export(icons, mod, out / "mod")
    v = icons.get(key) or variants(m, who(key, kd), p, S["hotbar"], S["B"], p2, fr)
    log(f"[editor] exported {key} -> {out} ({len(icons)} icons in the mod)")
    return {"key": key, "dir": str(out), "icons": len(icons), "files": [str(Path(f).relative_to(out)) for f in files],
            **{t: png_out(v[t]) for t in ("controller", "tooltip", "hotbar")}}


LOOKS = ("icon", "tooltip", "hotbar", "lineart")
_images, _images_lock = {}, threading.Lock()   # the last few painted images: a background or format change skips the paint


def image_req(q):
    """one image to share: look (icon = the master with its glow, tooltip = with the bottom fade, hotbar = the 64 px PC
    cell with its frame, lineart = the grey lines) x size (16-2048) x background (transparent, dark, black, white or
    #rrggbb) -> {png: data URL, name} (+ webp, webpName with q["format"] == "webp": the download as lossless WebP; the
    PNG stays for the clipboard, which takes PNG only). Above 512 the icon / tooltip / line art come from the browser's
    flattening at that size (q["hires"]: brush strokes re-rendered sharp), the glow grown at 512 and enlarged
    (variants.paint); the hotbar cell is fitted at 64 (D24), so it is only scaled (whole multiples by nearest neighbour:
    crisp pixels)."""
    import hashlib
    from .variants import sized, variants
    S = state()
    look, size, bg = q.get("look", "icon"), max(16, min(int(q.get("size") or 512), 2048)), q.get("bg") or "transparent"
    assert look in LOOKS, look
    hr = q.get("hires") if size > 512 and q.get("hires") else None
    src = {**q, "lineart": hr["lineart"], "mask": hr.get("mask")} if hr and look != "hotbar" else q
    key = hashlib.md5(json.dumps([src.get(k) for k in ("lineart", "mask", "kind", "preset", "second", "frame")] + [look, size]).encode()).hexdigest()
    with _images_lock:
        im = _images.get(key)
    if im is None:
        if look == "lineart":
            im = Image.fromarray(u8(png_in(src["lineart"])), "RGBA")
            im = im if im.size[0] == size else im.resize((size, size), Image.LANCZOS)
        else:
            m, p, p2, fr, kd = paint_req(src)
            if look == "hotbar":
                im = variants(m, f"{PREFIX[kd]}_Preview", p, S["hotbar"], S["B"], p2, fr)["hotbar"].convert("RGBA")
                im = im.resize((size, size), Image.NEAREST if size % 64 == 0 else Image.LANCZOS)
            else:
                im = sized(m, size, fade=look == "tooltip").convert("RGBA")
        with _images_lock:
            while len(_images) >= 4:
                _images.pop(next(iter(_images)))
            _images[key] = im
    if bg != "transparent":
        rgb = {"dark": tuple(int(round(v * 255)) for v in np.ravel(DARK)[:3]), "black": (0, 0, 0), "white": (255, 255, 255)}.get(bg)
        if rgb is None:
            h = bg.lstrip("#")
            rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        im = Image.alpha_composite(Image.new("RGBA", im.size, (*rgb, 255)), im).convert("RGB")
    name = ident(q.get("name") or "Icon", True) or "Icon"
    out = {"png": png_out(im), "name": f"{name}_{look}_{size}.png"}
    if q.get("format") == "webp":
        out.update(webp=png_out(im, "WEBP"), webpName=f"{name}_{look}_{size}.webp")
    return out


def golden_req(q):
    """WebGL master vs variants.master on the same line art: mean |L*| over the hotbar dark at 128 px (3.1's measure,
    glyph.seen_err) and at 512, worst pixel. Appended to data/editor/golden.json"""
    from .glyph import seen_err
    from .lab import rgb2lab
    py = paint_req(q)[0]
    gl = png_in(q["master"])
    res = {}
    for s in (128, 512):
        f = 512 // s
        pool = lambda z: z.reshape(s, f, s, f).mean((1, 3))
        BA = [(pool(rgb2lab(x[..., :3])[..., 0] / 100 * x[..., 3]), pool(x[..., 3])) for x in (py, gl)]
        res[f"L{s}"] = round(seen_err({"B": BA[0][0], "a": BA[0][1]}, *BA[1]), 3)
    over = lambda x: rgb2lab(x[..., :3] * x[..., 3:] + DARK * (1 - x[..., 3:]))[..., 0]
    res["L_max"] = round(float(np.abs(over(py) - over(gl)).max()), 2)
    res["alpha_max"] = round(float(np.abs(py[..., 3] - gl[..., 3]).max()), 3)
    p = E / "golden.json"
    allr = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    allr[q["icon"]] = {**res, "two": bool(q.get("second")), "kind": q["kind"], "ms": q.get("ms")}
    p.write_text(json.dumps(allr, indent=1), encoding="utf-8")
    return res


def perf_req(q):
    """/?perftest results (any browser, also headless runs): appended to data/editor/perf.json and logged. Every page
    load reports its start-up times (mode boot): logged, and kept in perf.json when slow or asked for (/?boottest)"""
    if q.get("mode") == "boot":
        r = q["result"]
        log(f"[editor] page ready in {r['painted'] / 1000:.1f} s (data {r['data'] / 1000:.1f}, editor built {r['ui'] / 1000:.1f}, "
            f"session restored {r['restored'] / 1000:.1f}; {q['browser'].split(')')[-1].strip()})")
        if not q.get("keep"):
            return {"ok": True}
    p = E / "perf.json"
    allr = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    allr.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **q})
    p.write_text(json.dumps(allr, indent=1), encoding="utf-8")
    if q.get("mode") != "boot":
        log(f"[editor] perftest {q.get('mode')} {q.get('browser')}: {json.dumps(q.get('result'))}")
    return {"ok": True}


HIDDEN = Path(__file__).with_name("parts_hidden.json")    # panel cards hidden as vague: group key -> why (in git)
CATS = Path(__file__).with_name("parts_categories.json")  # panel categories: group key -> category (eye-checked, in git)
DRAFTS = OUT / "drafts"
# In the developer's git checkout the panel's edits are the shipped lists; in a release they go to the user's own layer
# (outputs/editor/user/, a null hides a shipped entry), so updates replace the shipped lists and keep the user's edits.
DEV = (APP.parent / ".git").exists()
USER = OUT / "user"


def read_list(f):
    """a shipped list with the user's edits on top"""
    base = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    mine = USER / f.name
    if DEV or not mine.exists():
        return base
    return {k: v for k, v in {**base, **json.loads(mine.read_text(encoding="utf-8"))}.items() if v is not None}


def edit_list(f, changes):
    """{key: value | None (remove)} into the shipped list (git checkout) or the user's layer (release)"""
    target = f if DEV else USER / f.name
    d = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    for k, v in changes.items():
        if v is None and DEV:
            d.pop(k, None)
        else:
            d[k] = v
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(d, indent=1), encoding="utf-8")


def hidden_req(q):
    """{key, hidden} and / or {key, cat} -> {hidden, cats}: the hidden-parts list and the part categories, rewritten
    when asked (the panel's right-click). Both files are keyed by group key (stable across part reruns), in git."""
    if q.get("key") and "hidden" in q:
        edit_list(HIDDEN, {q["key"]: (q.get("why") or "hidden in the editor") if q["hidden"] else None})
    if q.get("key") and q.get("cat"):
        edit_list(CATS, {q["key"]: q["cat"]})
    return {"hidden": read_list(HIDDEN), "cats": read_list(CATS)}


def update_req(q):
    """{action: version | check | stage | restart} -> the update state (iconkit.update). restart: the page autosaved; the server
    stops, installs the staged release and starts again (the page reloads when the version changes)"""
    from . import update
    a = q.get("action", "check")
    if a == "version":                        # no network: the page's version line, or when the user turned checks off
        return {"version": update.__version__, "enabled": False, "staged": update.staged(), "dev": DEV}
    if a == "stage":
        info = update.check()
        if not info.get("newer"):
            return {**info, "staged": None}
        return {**info, "staged": update.stage(info)}
    if a == "restart":
        if not update.staged():
            raise ValueError("no downloaded update to install")
        RESTART.set()                          # the main thread installs and restarts once serving stops (a thread
        stop = threading.Timer(.3, SERVER.shutdown)   # started here would be a daemon, like the request's, and die
        stop.daemon = False                    # with the server before it got to the install)
        stop.start()
        return {"restarting": True}
    try:
        info = update.check(force=bool(q.get("force")))
    except Exception as ex:                    # offline, rate-limited: say so, the editor works on
        info = {"version": update.__version__, "enabled": True, "error": f"{type(ex).__name__}: {ex}"}
    return {**info, "staged": update.staged(), "dev": DEV}


SERVER, RESTART = None, threading.Event()


def restart():
    """(main thread, serving stopped) install the staged release, start again in a new process (the launcher's loop,
    exit code 75, when it started us; else this process replaced)"""
    from . import update
    log("[editor] restarting to install the update")
    SERVER.server_close()
    try:
        update.apply()
    except Exception as ex:
        log(f"[editor] update not installed: {ex}")
    if os.environ.get("ICONGEN_LAUNCHER"):
        os._exit(75)
    os.execv(sys.executable, [sys.executable, "-m", "iconkit.editor", *sys.argv[1:]])


def drafts_req(q):
    """list (no name), load ({name}), save ({name, doc, thumb}) editor drafts: outputs/editor/drafts/<name>.json + .png
    (game strokes are kept as icon + stroke id, brush strokes as their vector settings: a draft holds no game art)"""
    DRAFTS.mkdir(parents=True, exist_ok=True)
    name = ident(q.get("name") or "", True)[:60]
    if "doc" in q:
        (DRAFTS / f"{name}.json").write_text(json.dumps(q["doc"]), encoding="utf-8")
        if q.get("thumb"):
            Image.fromarray(u8(png_in(q["thumb"])), "RGBA").save(DRAFTS / f"{name}.png")
        return {"saved": name}
    if name:
        f = DRAFTS / f"{name}.json"
        return {"name": name, "doc": json.loads(f.read_text(encoding="utf-8"))} if f.exists() else {"name": name, "doc": None}
    fs = sorted(DRAFTS.glob("*.json"), key=lambda f: -f.stat().st_mtime)
    return {"drafts": [{"name": f.stem, "time": f.stat().st_mtime, "thumb": f.with_suffix(".png").exists()} for f in fs
                       if not f.stem.startswith("Autosave")]}


class Server(ThreadingHTTPServer):
    request_queue_size, daemon_threads = 64, True       # default backlog 5 refused bursts of preview requests
    # Windows' SO_REUSEADDR (http.server's default) lets a second server bind the same port: requests then reach either
    # one (seen 2026-10-18: a page came from another python http.server on 8765). Bind exclusively, so a taken port
    # raises and serve() moves to a free one.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32":
            import socket
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".json": "application/json",
                      ".png": "image/png", ".html": "text/html", ".css": "text/css"}
    API = {"/api/hotbar": hotbar_req, "/api/export": export_req, "/api/golden": golden_req, "/api/parts_hidden": hidden_req,
           "/api/drafts": drafts_req, "/api/brush_samples": brush_samples_req, "/api/brush_measure": brush_measure_req,
           "/api/perf": perf_req, "/api/image": image_req, "/api/presets": presets_req, "/api/import": import_req,
           "/api/imported": imported_req, "/api/update": update_req}

    def translate_path(self, path):
        """/data/editor/... from data/editor, /drafts/... from outputs/editor/drafts, everything else from app/; nothing
        outside those folders"""
        from urllib.parse import urlsplit, unquote
        path = unquote(urlsplit(path).path)
        base, rel = next(((b, path[len(p):]) for p, b in (("/data/editor/", E), ("/drafts/", DRAFTS), ("/imported/", IMP)) if path.startswith(p)),
                         (APP, path.lstrip("/") or "index.html"))
        p = (base / rel).resolve()
        return str(p) if p.is_relative_to(base.resolve()) else str(APP / "missing")

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def timed(self, fn):
        """run one request; log it when it takes over SLOW s (so a slow start says which request held it)"""
        t = time.time()
        try:
            return fn()
        finally:
            if time.time() - t > SLOW:
                log(f"[editor] slow: {self.command} {self.path} took {time.time() - t:.1f} s")

    def do_GET(self):
        self.timed(lambda: self.send_json(recipes()) if self.path == "/api/recipes" else SimpleHTTPRequestHandler.do_GET(self))

    def do_POST(self):
        fn = self.API.get(self.path)
        if not fn:
            return self.send_json({"error": "unknown"}, 404)
        try:
            self.timed(lambda: self.send_json(fn(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))))
        except Exception as ex:                                # shown in the app's status line and logged here
            import traceback
            traceback.print_exc()
            self.send_json({"error": f"{type(ex).__name__}: {ex}"}, 500)

    def log_message(self, fmt, *a):
        if a and str(a[1])[:1] in "45":
            log(f"[editor] {self.command} {self.path} -> {a[1]}")


def serve(args):
    global DRAFTS, CUSTOM, IMP, SERVER
    if "--drafts" in args:                     # test sessions: their own drafts + autosave, never the user's
        DRAFTS = Path(args[args.index("--drafts") + 1])
        CUSTOM, IMP = DRAFTS / "presets.json", DRAFTS / "imported"
    stamp = E / "data_version.json"            # an update that changes the cut data bumps DATA_V: cut again once
    if (E / "index.json").exists() and not stamp.exists():
        stamp.write_text(json.dumps({"v": DATA_V}), encoding="utf-8")       # data cut before stamps: as current
    old = json.loads(stamp.read_text(encoding="utf-8"))["v"] if stamp.exists() else None
    if not DEV and (not (E / "index.json").exists() or old != DATA_V):
        # an installed copy: the game's icons are a download (D10 amended 2026-10-19), not cut here (that needs the game
        # unpack; 8.3 may read the user's install instead)
        from . import update
        update.fetch_data()
        old = DATA_V
    if not (E / "index.json").exists() or old != DATA_V:
        log("[editor] first run: cutting the game's icons into strokes (~3 min)" if old is None else
            f"[editor] the update changed the editor's data ({old} -> {DATA_V}): cutting the icons again (~11 min, once)")
        extract()
    if not (E / "parts.json").exists() or old != DATA_V:
        parts_panel()
    E.mkdir(parents=True, exist_ok=True)
    stamp.write_text(json.dumps({"v": DATA_V}), encoding="utf-8")
    # the page's layout, tab and filters live in the browser per origin: keep the port stable (8765, else the next free
    # one up to 8775) instead of a random one per run (seen 2026-10-18: another http.server held 8765 all day)
    ports = [int(args[args.index("--port") + 1])] if "--port" in args else list(range(8765, 8776))
    for port in ports + [0]:
        try:
            srv = SERVER = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    url = f"http://127.0.0.1:{srv.server_port}/"
    threading.Thread(target=state, daemon=True).start()               # warm up (backgrounds) while the page loads
    log(f"[editor] open {url}  (Ctrl+C stops)")
    if "--no-browser" not in args:
        threading.Timer(.5, webbrowser.open, (url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    if RESTART.is_set():
        restart()


def check():
    """stroke ids = parts.strokes on the line mask; every drawn pixel has a stroke; the export path (8-bit line art
    through variants.master) rebuilds variants.build's master; export writes the mod; hotbar preview size; no
    scikit-image on the runtime path; the static server never leaves app/ and data/editor/"""
    import tempfile, time
    from .variants import build
    from .glyph import seen_err
    global OUT
    S = state()
    n = "Spell_Evocation_Fireball"
    x, _, ref, p, _ = build(n, S["glyph"], S["grammar"])
    la, _ = read_strokes(n)
    rgba = np.dstack([la[..., :1].repeat(3, -1), la[..., 1:]])
    q = {"lineart": png_out(Image.fromarray(rgba, "RGBA")), "kind": "Spell", "preset": p, "name": "Check", "mod": "CheckMod"}
    m = paint_req(q)[0]
    sm, sr = split(m), split(ref)
    err = seen_err(sr, sm["B"], sm["a"])
    assert err < .2, f"8-bit line art -> master vs variants.build: {err:.3f} L*"
    t = time.time()
    cell = png_in(hotbar_req({"master": png_out(Image.fromarray(u8(m), "RGBA")), "kind": "Spell", "preset": p})["hotbar"])
    hot_ms = (time.time() - t) * 1000
    assert cell.shape == (64, 64, 4), cell.shape
    global DRAFTS, CUSTOM, IMP
    with tempfile.TemporaryDirectory() as tmp:
        OUT, DRAFTS = Path(tmp), Path(tmp) / "drafts"
        r = export_req({**q, "hires": {"size": 1024, "lineart": png_out(Image.fromarray(rgba, "RGBA").resize((1024, 1024), Image.LANCZOS))}})
        assert r["key"] == "CheckMod_Spell_Check" and (OUT / "CheckMod/mod/Public/CheckMod/Assets/Textures/Icons/Icons_CheckMod.DDS").exists()
        assert len(r["files"]) == 1 + 3 + 2 + 3 + 4 + 1, r["files"]       # line art, PNGs, hi-res, hotbar atlas, GUI textures, metadata
        r2 = export_req({**q, "name": "Only PNGs", "what": {"mod": False, "lineart": False}})   # the dialog's choices
        assert [Path(f).parent.name for f in r2["files"]] == ["png"] * 3, r2["files"]
        im = png_in(image_req({**q, "look": "hotbar", "size": 128, "bg": "white"})["png"])   # one image to share
        assert im.shape[:2] == (128, 128), im.shape
        assert Image.open(OUT / "CheckMod/png/CheckMod_Spell_Check_1024.png").size == (1024, 1024), "hi-res PNG"
        doc = {"v": 1, "items": [{"type": "game", "icon": n, "label": 1, "m": [1, 0, 0, 1, 0, 0]}]}
        assert drafts_req({"name": "my draft", "doc": doc})["saved"] == "MyDraft" and drafts_req({"name": "MyDraft"})["doc"] == doc
        assert [d["name"] for d in drafts_req({})["drafts"]] == ["MyDraft"], "draft list"
    meta = hidden_req({})
    assert set(meta) == {"hidden", "cats"} and all(isinstance(v, dict) for v in meta.values())
    PJ = json.loads((E / "parts.json").read_text(encoding="utf-8"))["parts"]
    uncat = [c["id"] for c in PJ if c["key"] not in meta["hidden"] and c["key"] not in meta["cats"]]
    assert not uncat, f"parts without a category (iconkit/parts_categories.json): {uncat}"
    global CUSTOM                                             # a custom colour: made, painted (teal), a hotbar cell, deleted
    from .lab import rgb2lab
    with tempfile.TemporaryDirectory() as tmp:
        CUSTOM = Path(tmp) / "presets.json"
        r = presets_req({"stops": ["#18c8a8"], "label": "Check"})
        assert r["name"] == "Custom: Check" and any(p["name"] == r["name"] for p in r["recipes"]["presets"]), r["name"]
        cm = paint_req({**q, "preset": r["name"]})[0]
        ab = rgb2lab(cm[..., :3])[cm[..., 3] > .5][:, 1:].mean(0)
        assert ab[0] < -10, f"custom teal paints teal: a*b* {ab.round(1)}"
        cell = png_in(hotbar_req({"master": png_out(Image.fromarray(u8(cm), "RGBA")), "kind": "Action", "preset": r["name"]})["hotbar"])
        assert cell.shape == (64, 64, 4)
        presets_req({"delete": r["name"]})
        assert r["name"] not in state()["PR"] and not json.loads(CUSTOM.read_text(encoding="utf-8"))
        global IMP                                            # import: a faded tooltip alone, and an icon in a colour no
        from . import paths as P                              # game gradient has (hue turned 150 degrees)
        from .lab import lab2rgb
        IMP = Path(tmp) / "imported"
        b64 = lambda b: base64.b64encode(b).decode()
        x = master("Spell_Evocation_Fireball")
        lb = rgb2lab(x[..., :3])
        a_, b_, rt = lb[..., 1].copy(), lb[..., 2].copy(), np.radians(150)
        lb[..., 1], lb[..., 2] = a_ * np.cos(rt) - b_ * np.sin(rt), a_ * np.sin(rt) + b_ * np.cos(rt)
        buf = io.BytesIO(); Image.fromarray(u8(np.dstack([lab2rgb(lb), x[..., 3]])), "RGBA").save(buf, "PNG")
        r = import_req({"icons": [{"name": "Chk_Action_Rush", "files": [{"path": "Tooltips/Icons/Chk_Action_Rush.DDS", "data": b64(P.tooltip("Action_Rush").read_bytes())}]},
                                  {"name": "Chk_Spell_Odd.png", "files": [{"path": "Chk_Spell_Odd.png", "data": b64(buf.getvalue())}]}]})
        tip, odd = r["icons"]
        assert not r["errors"] and "rebuilt from its colours" in tip["used"] and tip["k"] == "Action" and tip["key"] == "Chk_Action_Rush", tip
        assert odd["custom"] and odd["look"] < 3 and (IMP / "icons" / f"{odd['n']}.lab.png").exists(), odd
    assert "skimage" not in sys.modules, "scikit-image loaded on the runtime path (D46)"
    from .parts import unpack                                 # offline code from here on (parts imports scikit-image)
    Z = np.load(D / "parts.npz")
    ix = {str(n): i for i, n in enumerate(Z["names"])}
    for n in ("Spell_Evocation_Fireball", "Action_Rush", "Skill_Sorcerer_Passive_Metamagic_QuickenedSpell"):
        la, lab = read_strokes(n)
        m = unpack(Z["bits"][ix[n]])
        assert (lab[m] == ndimage.label(m, EIGHT)[0][m]).all(), f"{n}: stroke ids = parts.strokes"
        assert not ((la[..., 1] > 0) & (lab == 0)).any() and not ((la[..., 1] == 0) & (lab > 0)).any(), f"{n}: ids cover the drawing"
    h = Handler.__new__(Handler)
    assert h.translate_path("/data/editor/../glyph.json").endswith("missing") and h.translate_path("/../iconkit/editor.py").endswith("missing")
    assert Path(h.translate_path("/")).name == "index.html" and Path(h.translate_path("/data/editor/index.json")).exists()
    global DEV, USER                           # a release's lists: the user's edits in their own layer, shipped file untouched
    dev, user = DEV, USER
    with tempfile.TemporaryDirectory() as tl:
        DEV, USER, f = False, Path(tl) / "user", Path(tl) / "list.json"
        f.write_text(json.dumps({"a": "shipped", "b": "shipped"}), encoding="utf-8")
        edit_list(f, {"a": None, "c": "mine"})
        assert read_list(f) == {"b": "shipped", "c": "mine"} and json.loads(f.read_text(encoding="utf-8"))["a"] == "shipped", read_list(f)
    DEV, USER = dev, user
    log(f"[editor] check passed: stroke ids, export path vs variants.build {err:.3f} L*, hotbar preview {hot_ms:.0f} ms, "
        f"mod files, custom colour, import (faded tooltip, own colour), no scikit-image, static paths, user lists")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a and not a[0].startswith("--") else "serve"
    if cmd == "serve" and not DEV:             # an update downloaded last time installs before anything else runs
        from . import update
        if update.staged():
            try:
                update.apply()
                os.execv(sys.executable, [sys.executable, "-m", "iconkit.editor", *a])   # start on the new code
            except Exception as ex:
                log(f"[editor] update not installed: {ex}")
    {"extract": extract, "symbols": symbols, "parts": parts_panel, "check": check, "serve": lambda: serve(a)}[cmd]()
