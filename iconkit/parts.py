"""D43 house-parts library (Phase 5 design round, 2026-10-17: "figures/silhouettes/humanoids have a few limited styles").
Every v1 master's line art (glyph.split line share >= .5 at 512, D38) is cut into connected line parts (4-connected, as
relations.parts_image: what a click in the draft editor picks), parts of MIN_SHARE+ of the icon's lines and MIN_SIDE+ px.
A part whose skeleton is shorter than L_MIN x its box side is a plain stroke (straight or curved line, dot, short arc,
spur): the house brush draws those (D44), they are not library parts. The others ("compound" parts: crossings, closed
shapes, hooks, figures) are compared size-normalised (skeleton centred in its own square box at S px, relations.kappa as
placed and mirrored, so a copy at any size, place or side matches) and grouped by average linkage (mean kappa >= T_PART);
a group needs ICONS_MIN icons. A group in SERIES_MIN+ series (shape.series) is a house part; in fewer it is a series part
(the series' own base or frame: D30 / D36 material). Names: NAMES (written from the sheets, keyed by each group's medoid
part), applied in the report, so a rename needs no rerun.
    python -m iconkit.parts [run]  -> data/parts.json + data/parts.npz (~4 min, POOL processes)
    python -m iconkit.parts report -> data/parts.html (review page, local: Larian art)
    python -m iconkit.parts check  -> self-check on drawn shapes"""
import json, re, sys
from collections import Counter, defaultdict
from functools import lru_cache
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from skimage.morphology import skeletonize, disk
from .extract import D, log
from .glyph import master, split, POOL
from .relations import kappa

S = 32                     # px a part's skeleton is compared at, in its own box (1 px tolerance = 1/32 of the part)
MIN_SHARE, MIN_SIDE = .005, 24          # parts kept: share of the icon's lines (relations.parts_image), box side at 512
L_MIN = 1.6                # skeleton length / box side below this = a plain stroke (straight line ~1, arc ~1.2-1.5)
T_PART, T_COPY = .75, .9   # group cut (mean kappa), an exact copy
ICONS_MIN, SERIES_MIN = 3, 3
GHOST, GHOST_X = 48, 2.0   # px of the context picture, its window in part sides
# whole shapes (user 2026-10-17: "why highlight just the head? I mean more general shapes"). Two rules, both on 8-connected
# strokes, checked by eye on every named family (two independent visual reviews, then mine):
# (B) exact repeats, every group: the strokes other members draw at the same place relative to the repeated part, anywhere
#     in the icon (the medoid's whole icon mapped through each member's part box, R_B cells, lines dilated 1 cell = 4 px):
#     a stroke whose pixels hit SHARE_B+ of the other members' lines and lose DROP+ of that when shifted SHIFT px (so a
#     crowded area, where any shift still hits lines, does not count). Completes frames, rings, ray fans, multi-stroke marks.
# (A) whole object, figure families only (report): the strokes joined to the part and its repeats (gap under GAP px), kept
#     inside the group's usual object size (the Q-th percentile of the members' joined-object boxes relative to the part,
#     + MARGIN), never a stroke that closes round the part (encloses(): a frame, ring or cross the figure stands in),
#     gated on context >= CTX_GROW. A figure's body varies from icon to icon, so only joining reaches it. Tried
#     and dropped: growing into the lines most members draw around the part (dense areas pass: a ring took in each orb's
#     symbol, Heat Metal's daggers the breastplate; a tight tolerance lost Ki Restoration's arms); chance-correcting it by
#     a ring around the stroke or a shift test (lost the varying bodies again); joining for every family (the Divine Strike
#     sword joined the fire flame, a slash arc the sword, the ice cube the snowflake; the median object box left the frontal
#     figure a head, the 75th-percentile box with a 16 px gap let Wild Shape animals into the ally bust). GAP 18: heads
#     float 13-16 px over their shoulders (Soul Catching 15, Wholeness of Body 16, Umbral Shroud 13, the Trickster's hood
#     14), 12 left them heads; the ally bust never grows (context .01), so the animals stay out. SHARE_B .5: the
#     spell-slot star's strokes repeat in .51-.63 of its other icons (points drawn a few px apart)
R_B, SHARE_B, DROP, SHIFT = 128, .5, .3, 16
GAP, Q, MARGIN, IN_BOX, CTX_GROW = 18, 75, .15, .8, .25
DECIDED = {}               # page decisions (user), filled when answered
FIGURE_RX = r"\b(figure|humanoid|person|man|woman|body|silhouette)s?\b"   # research/probes/figure_sheet.py


# ---------------------------------------------------------------- cutting
def norm(part):
    """part mask (its box) -> skeleton, skeleton centred in a square box of the part's longest side, any pixel per cell at
    S px (BOX pooling: thin lines survive)"""
    sk = skeletonize(part)
    h, w = part.shape
    side = max(h, w) + 2
    box = np.zeros((side, side), bool)
    box[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = sk
    return sk, np.asarray(Image.fromarray(box.astype(np.uint8) * 255).resize((S, S), Image.BOX)) > 0


def cut_mask(m):
    """line mask (512, 512) bool -> (labels, rows [(label, top, left, h, w, area, L)], maps (n, S, S) bool), parts of
    MIN_SHARE+ of the lines and MIN_SIDE+ px"""
    lab, k = ndimage.label(m)
    total = max(int(m.sum()), 1)
    size = ndimage.sum(m, lab, range(1, k + 1)) if k else []
    rows, maps = [], []
    for j, sl in enumerate(ndimage.find_objects(lab)):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if size[j] < MIN_SHARE * total or max(h, w) < MIN_SIDE:
            continue
        sk, mp = norm(lab[sl] == j + 1)
        rows.append((j + 1, sl[0].start, sl[1].start, h, w, int(size[j]), round(float(sk.sum() / max(h, w)), 3)))
        maps.append(mp)
    return lab, rows, np.array(maps, bool).reshape(-1, S, S)


def line_mask(n):
    return split(master(n), 512)["AL"] >= .5


def cut_job(n):
    m = line_mask(n)
    _, rows, maps = cut_mask(m)
    return n, np.packbits(m), int(m.sum()), int(ndimage.label(m)[1]), rows, maps


def kappas(M):
    """(n, S, S) bool -> kappa as placed, kappa with one of the two mirrored left-right, both (n, n)"""
    n = len(M)
    K2 = kappa(np.concatenate([M, M[:, :, ::-1]]).astype(np.float32))
    return K2[:n, :n], K2[:n, n:]


def cluster(K, icon):
    """K (n, n) kappa (best of placed / mirrored), icon (n,) -> [(medoid, members one per icon (medoid first, then by kappa
    to it), every member)] for average-linkage groups (mean kappa >= T_PART) in ICONS_MIN+ icons, biggest first"""
    Dm = 1 - np.clip(K, -1, 1)
    np.fill_diagonal(Dm, 0)
    lab = fcluster(linkage(squareform((Dm + Dm.T) / 2, checks=False), "average"), 1 - T_PART, "distance")
    out = []
    for l in np.unique(lab):
        mem = np.where(lab == l)[0]
        if len(set(icon[mem])) < ICONS_MIN:
            continue
        med = int(mem[K[np.ix_(mem, mem)].sum(1).argmax()])
        best = {icon[med]: med}
        for m in mem:
            if icon[m] != icon[med] and (icon[m] not in best or K[med, m] > K[med, best[icon[m]]]):
                best[icon[m]] = int(m)
        out.append((med, sorted(best.values(), key=lambda m: (m != med, -K[med, m])), mem.tolist()))
    return sorted(out, key=lambda o: -len(o[1]))


def unpack(b):
    return np.unpackbits(b)[:512 * 512].reshape(512, 512).astype(bool)


def window(m, top, left, h, w, flip=False):
    """the line mask around a part (GHOST_X part sides, centred on its box) at GHOST px, mirrored if asked"""
    side = max(h, w) * GHOST_X
    cy, cx = top + h / 2, left + w / 2
    im = Image.fromarray(m.astype(np.uint8) * 255).transform((GHOST, GHOST), Image.EXTENT,
                                                             (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2),
                                                             Image.BILINEAR)
    a = np.asarray(im).astype(np.float32) / 255
    return a[:, ::-1] if flip else a


def icon_box(med, part, flip):
    """the medoid icon's square mapped into a member's frame through the two parts' boxes (top, left, h, w): a window that
    lines a member's whole icon up with the medoid's (mirrored members map mirrored)"""
    (t0, l0, h0, w0), (t, l, h, w) = med, part
    s = max(h, w) / max(h0, w0)
    cy0, cx0, cy, cx = t0 + h0 / 2, l0 + w0 / 2, t + h / 2, l + w / 2
    xa, xb = (cx - (512 - cx0) * s, cx + cx0 * s) if flip else (cx - cx0 * s, cx + (512 - cx0) * s)
    return xa, cy - cy0 * s, xb, cy + (512 - cy0) * s


def to_win(a, box, flip=False, r=R_B):
    """mask (512) -> its window box at r px, mirrored if asked"""
    x = np.asarray(Image.fromarray(a.astype(np.uint8) * 255).transform((r, r), Image.EXTENT, box, Image.BILINEAR)) > 60
    return x[:, ::-1] if flip else x


def from_win(c, box, flip=False):
    """window map (bool or float 0-1) -> 512 px float (the inverse of to_win)"""
    c = c[:, ::-1] if flip else c
    x0, y0, x1, y1 = box
    kx, ky = c.shape[1] / (x1 - x0), c.shape[0] / (y1 - y0)
    im = Image.fromarray((np.asarray(c, np.float32) * 255).astype(np.uint8)).transform(
        (512, 512), Image.EXTENT, (-x0 * kx, -y0 * ky, (512 - x0) * kx, (512 - y0) * ky), Image.BILINEAR)
    return np.asarray(im).astype(np.float32) / 255


def strokes(m):
    """line mask -> (8-connected stroke labels, {label: (rows, cols)}, {label: labels within GAP px}); the joining graph is
    built once per icon (a whole-image dilation per joining round took the run past 20 min)"""
    L8 = ndimage.label(m, np.ones((3, 3)))[0]
    px, near = {}, {}
    for j, sl in enumerate(ndimage.find_objects(L8), 1):
        r0, c0 = max(sl[0].start - GAP, 0), max(sl[1].start - GAP, 0)
        sub = L8[r0:min(sl[0].stop + GAP, 512), c0:min(sl[1].stop + GAP, 512)]
        own = sub == j
        rr, cc = np.nonzero(own)
        px[j] = (rr + r0, cc + c0)
        near[j] = set(np.unique(sub[ndimage.binary_dilation(own, structure=disk(GAP))]).tolist()) - {0, j}
    return L8, px, near


def repeats(px, F, keep):
    """(B) strokes (not in keep) whose pixels hit SHARE_B+ of the other members' lines F and lose DROP+ of that when
    shifted SHIFT px, in at least two of 8 directions (a line loses it across itself, both ways; along itself it keeps
    it, so the mean over directions refused the Reapply ring's arcs and long rays; a crowded area keeps it every way)"""
    shifts = [(int(round(SHIFT * np.sin(a))), int(round(SHIFT * np.cos(a)))) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
    out = set()
    for c, (yy, xx) in px.items():
        if c in keep:
            continue
        sup = F[yy, xx].mean()
        if sup >= SHARE_B and sup - np.sort([F[np.clip(yy + dy, 0, 511), np.clip(xx + dx, 0, 511)].mean()
                                             for dy, dx in shifts])[1] >= DROP:
            out.add(int(c))
    return out


def joined(near, labs, allowed=None):
    """strokes within GAP px of the shape so far, repeatedly (only allowed labels if given) -> label set"""
    labs, todo = set(labs), list(labs)
    while todo:
        for c in near.get(todo.pop(), ()):
            if c not in labs and (allowed is None or c in allowed):
                labs.add(c)
                todo.append(c)
    return labs


def encloses(yy, xx, cy, cx):
    """does a stroke (pixel rows, cols) close round the point (cy, cx)? A frame, ring or cross the figure stands in:
    with an 18 px join they lit up with the figure (Hold Person's square, Otiluke's ring, Revivify's cross)"""
    cy, cx = int(round(cy)), int(round(cx))
    if not (yy.min() < cy < yy.max() and xx.min() < cx < xx.max()):
        return False
    m = np.zeros((yy.max() - yy.min() + 1, xx.max() - xx.min() + 1), bool)
    m[yy - yy.min(), xx - xx.min()] = True
    return bool(ndimage.binary_fill_holes(m)[cy - yy.min(), cx - xx.min()] and not m[cy - yy.min(), cx - xx.min()])


def rel_box(px, labs, top, left, h, w, flip=False):
    """the box of some strokes relative to a part's box centre, in part sides (top, left, bottom, right; mirrored if asked)"""
    r = np.concatenate([px[l][0] for l in labs])
    c = np.concatenate([px[l][1] for l in labs])
    side, cy, cx = max(h, w), top + h / 2, left + w / 2
    b = np.array([(r.min() - cy) / side, (c.min() - cx) / side, (r.max() - cy) / side, (c.max() - cx) / side])
    return np.array([b[0], -b[3], b[2], -b[1]]) if flip else b


def whole_shapes(ms, parts, labels, flips, ctx, S=None):
    """one group's members: line masks, part boxes (top, left, h, w), part labels (4-connected), mirrored flags, context,
    optional strokes() of each -> per member (8-connected labels of part + exact repeats (B), labels the whole object
    adds (A), empty under the gate)"""
    S = S or [strokes(x) for x in ms]
    seed = [set(np.unique(L8[ndimage.label(x)[0] == lab]).tolist()) - {0} for (L8, _, _), x, lab in zip(S, ms, labels)]
    boxes = [icon_box(parts[0], p, f) for p, f in zip(parts, flips)]
    W = np.array([ndimage.binary_dilation(to_win(x, b, f)) for x, b, f in zip(ms, boxes, flips)], np.float32)
    tot = W.sum(0)
    B = [s | repeats(px, from_win((tot - W[k]) / max(len(ms) - 1, 1), b, f), s)
         for k, ((_, px, _), s, b, f) in enumerate(zip(S, seed, boxes, flips))]
    if ctx < CTX_GROW:
        return [(sorted(b), []) for b in B]
    RB = np.array([rel_box(px, joined(near, b), *p, f) for (_, px, near), b, p, f in zip(S, B, parts, flips)])
    typ = np.r_[np.percentile(RB[:, :2], 100 - Q, 0), np.percentile(RB[:, 2:], Q, 0)]
    out = []
    for (_, px, near), b, p, f in zip(S, B, parts, flips):
        t = np.array([typ[0], -typ[3], typ[2], -typ[1]]) if f else typ
        pad = MARGIN * (t[2] - t[0] + t[3] - t[1]) / 2
        top, left, h, w = p
        side, cy, cx = max(h, w), top + h / 2, left + w / 2
        r0, r1, c0, c1 = cy + (t[0] - pad) * side, cy + (t[2] + pad) * side, cx + (t[1] - pad) * side, cx + (t[3] + pad) * side
        ok = {c for c, (yy, xx) in px.items() if ((yy >= r0) & (yy <= r1) & (xx >= c0) & (xx <= c1)).mean() >= IN_BOX
              and not encloses(yy, xx, cy, cx)}
        out.append((sorted(b), sorted(joined(near, b, ok) - b)))
    return out


def key(icon, top, left, h, w):
    """a group's name key: its medoid part's icon and box centre (px at 512, to 8 px)"""
    return f"{icon}@{round((top + h / 2) / 8) * 8},{round((left + w / 2) / 8) * 8}"


# ---------------------------------------------------------------- run
def run():
    train, hold = ((D / f).read_text().split() for f in ("train.txt", "holdout.txt"))
    names, hold = train + hold, set(hold)
    Z = np.load(D / "shape.npz")
    ser = {str(n): int(s) for n, s in zip(Z["names"], Z["series"])}
    with Pool(POOL) as pool:
        R = pool.map(cut_job, names, chunksize=8)
    ix = {n: i for i, n in enumerate(names)}
    bits = np.stack([r[1] for r in R])
    lines = np.array([r[2] for r in R])
    P = np.array([(ix[r[0]], *row) for r in R for row in r[4]], dtype=np.float64).reshape(-1, 8)
    M = np.concatenate([r[5] for r in R])
    icon = P[:, 0].astype(int)
    per = np.bincount(icon, minlength=len(names))
    log(f"[parts] {len(names)} masters, {len(P)} parts ({MIN_SHARE:.1%}+ of the lines, {MIN_SIDE}+ px): per icon median "
        f"{np.median(per):.0f} (p10 {np.percentile(per, 10):.0f}, p90 {np.percentile(per, 90):.0f}); all connected bits "
        f"median {np.median([r[3] for r in R]):.0f}")
    comp = np.where(P[:, 7] >= L_MIN)[0]
    log(f"[parts] compound parts (skeleton {L_MIN}+ x box side) {len(comp)} = {P[comp, 6].sum() / lines.sum():.1%} of all "
        f"lines; plain strokes {len(P) - len(comp)} = {(P[:, 6].sum() - P[comp, 6].sum()) / lines.sum():.1%}")
    Kp, Kf = kappas(M[comp])
    K = np.maximum(Kp, Kf)
    ci = icon[comp]
    other = ci[:, None] != ci[None]
    iu = np.triu_indices(len(comp), 1)
    cross = K[iu][other[iu]]
    null = np.percentile(cross, [50, 90, 99, 99.9]).round(3).tolist()
    best = np.full(len(P), np.nan)
    best[comp] = np.where(other, K, -1).max(1)          # each compound part's closest part in another icon
    log(f"[parts] kappa of compound parts in different icons p50/90/99/99.9 {null}")
    groups, gid = [], np.full(len(P), -1)
    shapes = defaultdict(lambda: {"house": set(), "series": set(), "groups": set()})   # icon -> 8-connected stroke labels
    stroke_info = lru_cache(maxsize=256)(lambda i: strokes(unpack(bits[i])))
    CL = cluster(K, ci)
    for gi, (med, mem, every) in enumerate(CL):
        if gi % 50 == 0:
            log(f"[parts] whole shapes: group {gi} of {len(CL)}")
        icons = [int(ci[m]) for m in mem]
        ss = {ser.get(names[i], -1 - i) for i in icons}
        kk = np.array([K[med, m] for m in mem[1:]])
        flips = [bool(Kf[med, m] > Kp[med, m]) for m in mem]
        ms = [unpack(bits[i]) for i in icons]
        # context: lines that sit around the part in half the members (aligned on the part's box, mirrored copies flipped)
        gh = np.mean([window(x, *P[comp[m], 2:6], f) for x, m, f in zip(ms, mem, flips)], 0)
        mp = P[comp[med]]
        own = ndimage.binary_dilation(window(ndimage.label(ms[0])[0] == int(mp[1]), *mp[2:6]) > .3, iterations=2)
        ctx = float(((gh >= .5) & ~own).sum() / max(((gh >= .5) & own).sum(), 1))
        # whole shape per member: part + exact repeats (B, every group), + whole object (A, gated; shown for figures)
        parts = [tuple(int(v) for v in P[comp[m], 2:6]) for m in mem]
        S_ = [stroke_info(i) for i in icons]
        WS = whole_shapes(ms, parts, [int(P[comp[m], 1]) for m in mem], flips, ctx, S_)
        L8 = [s_[0] for s_ in S_]
        g = len(groups)
        kind = "house" if len(ss) >= SERIES_MIN else "series"
        gid[comp[np.array(every)]] = g            # every part of the group counts for coverage, not only one per icon
        Bs = [set(b) for b, _ in WS]
        for m in every:                           # other parts of the group in a member icon join as they are
            j = icons.index(int(P[comp[m], 0]))
            Bs[j] |= set(np.unique(L8[j][ndimage.label(ms[j])[0] == int(P[comp[m], 1])]).tolist()) - {0}
        seedpx = [(ndimage.label(x)[0] == int(P[comp[m], 1])).sum() for x, m in zip(ms, mem)]
        bpx = [np.isin(l, list(b)).sum() for l, b in zip(L8, Bs)]
        wm = [np.isin(l, list(b | set(a))) for l, b, (_, a) in zip(L8, Bs, WS)]
        boxes = [icon_box(parts[0], p, f) for p, f in zip(parts, flips)]
        shk = kappa(np.array([to_win(x, b, f, 64) for x, b, f in zip(wm, boxes, flips)], np.float32))[0, 1:]
        shb = kappa(np.array([to_win(np.isin(l, list(s)), b, f, 64) for l, s, b, f in zip(L8, Bs, boxes, flips)],
                             np.float32))[0, 1:]
        for i, b in zip(icons, Bs):
            shapes[i][kind] |= b
            shapes[i]["groups"].add(g)
        groups.append({"id": g, "key": key(names[int(mp[0])], *mp[2:6]), "kind": kind, "icons": len(icons),
                       "series": len(ss), "parts": len(every), "hold": sum(names[i] in hold for i in icons),
                       "kappa_med": round(float(np.median(kk)), 3), "kappa_p10": round(float(np.percentile(kk, 10)), 3),
                       "exact": round(float((kk >= T_COPY).mean()), 3), "context": round(ctx, 3),
                       "repeats": round(float(np.median(np.array(bpx) / np.maximum(seedpx, 1))), 2),
                       "grown": round(float(np.median([w.sum() / max(s, 1) for w, s in zip(wm, seedpx)])), 2),
                       "shape_kappa": round(float(np.median(shk)), 3),
                       "shape_exact": round(float((shk >= T_COPY).mean()), 3),
                       "repeat_kappa": round(float(np.median(shb)), 3), "repeat_exact": round(float((shb >= T_COPY).mean()), 3),
                       "ghost": (gh * 255).round().astype(np.uint8),
                       "members": [[names[int(P[comp[m], 0])], int(P[comp[m], 1]), *map(int, P[comp[m], 2:6]),
                                    round(float(K[med, m]), 3), f, sorted(b), a]
                                   for m, f, b, (_, a) in zip(mem, flips, Bs, WS)]})
    log(f"[parts] whole shapes: exact repeats add to the part in {sum(g['repeats'] > 1.05 for g in groups)} of "
        f"{len(groups)} groups (median x{np.median([g['repeats'] for g in groups if g['repeats'] > 1.05]):.2f} there); the "
        f"whole object adds more in {sum(g['grown'] > g['repeats'] + .05 for g in groups)} (context >= {CTX_GROW}; the page "
        f"shows it for figures)")
    icons = {}
    for i, n in enumerate(names):
        m = unpack(bits[i])
        L8 = ndimage.label(m, np.ones((3, 3)))[0]
        hm = np.isin(L8, list(shapes[i]["house"]))
        sm = np.isin(L8, list(shapes[i]["series"])) & ~hm
        L4 = ndimage.label(m)[0]
        sel = np.where(icon == i)[0]
        st = np.isin(L4, P[sel[P[sel, 7] < L_MIN], 1]) & ~hm & ~sm
        ow = np.isin(L4, P[sel[P[sel, 7] >= L_MIN], 1]) & ~hm & ~sm
        a = {k: float(v.sum() / max(lines[i], 1)) for k, v in (("house", hm), ("series", sm), ("stroke", st), ("own", ow))}
        icons[n] = {"lines": int(lines[i]), **{k: round(v, 3) for k, v in a.items()},
                    "small": round(1 - sum(a.values()), 3), "groups": sorted(shapes[i]["groups"]),
                    "house_labels": sorted(shapes[i]["house"])}
    h = np.array([v["house"] for v in icons.values()])
    hs = np.array([v["house"] + v["series"] for v in icons.values()])
    ev = {"masters": len(names), "parts": len(P), "per_icon": [int(np.percentile(per, q)) for q in (10, 50, 90)],
          "bits_median": int(np.median([r[3] for r in R])), "compound": len(comp),
          "compound_lines": round(float(P[comp, 6].sum() / lines.sum()), 3),
          "stroke_lines": round(float((P[:, 6].sum() - P[comp, 6].sum()) / lines.sum()), 3),
          "small_lines": round(float(1 - P[:, 6].sum() / lines.sum()), 3), "null": null,
          "groups": len(groups), "house": sum(g["kind"] == "house" for g in groups),
          "house_icons": int((h > 0).sum()), "house_share": [round(float(np.percentile(h, q)), 3) for q in (50, 75, 90)],
          "house_or_series_share": [round(float(np.percentile(hs, q)), 3) for q in (50, 75, 90)],
          "house_half": int((h >= .5).sum())}
    log(f"[parts] {ev['groups']} groups in {ICONS_MIN}+ icons, {ev['house']} house parts ({SERIES_MIN}+ series); icons with a "
        f"house part {ev['house_icons']} of {len(names)}; house share of an icon's lines p50/75/90 {ev['house_share']}, with "
        f"series parts {ev['house_or_series_share']}; half or more house parts: {ev['house_half']}")
    np.savez_compressed(D / "parts.npz", names=np.array(names), bits=bits, P=P, gid=gid, best=best,
                        ghosts=np.stack([g.pop("ghost") for g in groups]) if groups else np.zeros((0, GHOST, GHOST)))
    out = {"notes": "parts = connected line parts (D38 lines at 512, 4-connected); P in parts.npz: icon index, label, top, "
                    "left, h, w, area px, L (skeleton length / box side); groups: kind house (SERIES_MIN+ series) or series, "
                    "members [icon, label, top, left, h, w, kappa to the medoid, mirrored, 8-connected stroke labels of the part + its exact repeats, labels the whole object adds] one per icon, medoid first; repeats / grown = part + repeats / whole shape px over the part's (median), shape_kappa = whole shapes vs the medoid's, icons lined up; "
                    "context = consistent lines around the part (in half the members, GHOST_X sides) / the part's own; "
                    "icons: share of the icon's lines in house / series parts, plain strokes, own compound parts, small bits",
           "params": {"S": S, "MIN_SHARE": MIN_SHARE, "MIN_SIDE": MIN_SIDE, "L_MIN": L_MIN, "T_PART": T_PART,
                      "T_COPY": T_COPY, "ICONS_MIN": ICONS_MIN, "SERIES_MIN": SERIES_MIN},
           "eval": ev, "groups": groups, "icons": icons}
    (D / "parts.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    log(f"[parts] wrote {D / 'parts.json'} + parts.npz")


# ---------------------------------------------------------------- names (D43), written from the group sheets 2026-10-17
CATS = ("figure", "symbol", "sparkle", "body", "weapon", "object", "shape", "frame")
FAMILIES = {   # family -> (category, what it is); the user confirms or renames them on data/parts.html
    "ally bust": ("figure", "round head and squared open shoulders in one outline: the party / ally figure"),
    "frontal figure": ("figure", "a figure seen from the front, round open head on squared shoulders; the arms and body "
                                 "vary (arms crossed, hands together, cross-legged)"),
    "star figure": ("figure", "a figure with arms (and often legs) spread out"),
    "gesture figure": ("figure", "a figure in motion: small open head, one stroke per limb (running, lunging, "
                                 "crouching); two poses recur here, the game's other posed figures are drawn once"),
    "hooded figure": ("figure", "a hooded, cloaked figure with a diamond face opening"),
    "portrait": ("figure", "Disguise Self's portrait template: face outline, hair, ears, neck and shoulders"),
    "fire symbol": ("symbol", "the Fire damage symbol's flame (D28)"),
    "lightning bolt": ("symbol", "a zigzag bolt"),
    "snowflake": ("symbol", "the Cold damage symbol (D28)"),
    "acid bubbles": ("symbol", "the Acid damage symbol's bubbles and drips (D28)"),
    "necrotic skull": ("symbol", "a dripping skull"),
    "healing cross": ("symbol", "a thick plus-shaped cross"),
    "heart": ("symbol", "a heart outline"),
    "drop": ("symbol", "a drop outline, often round a small flame"),
    "hourglass": ("symbol", "an hourglass"),
    "spiral": ("symbol", "a squared spiral"),
    "four-point sparkle": ("sparkle", "a small four-point sparkle with concave sides, scattered round a drawing"),
    "long-point star": ("sparkle", "a large star: four long points, often short diagonal ones between"),
    "spiky spore": ("sparkle", "a ring with short spikes: a spore, a small sun"),
    "burst star": ("sparkle", "a jagged burst star"),
    "skull": ("body", "a front-facing skull: eye holes, triangle nose, often crossbones"),
    "skull in profile": ("body", "a skeleton's skull seen from the side, over its shoulder (turning undead)"),
    "open hand": ("body", "a raised open palm"),
    "pointing hand": ("body", "a hand pointing with the index finger"),
    "beckoning hand": ("body", "the back of a hand, fingers curled forward (Command: Approach)"),
    "gripping fist": ("body", "a fist gripping a weapon's handle (Pact of the Blade)"),
    "slim sword": ("weapon", "a slim straight blade with a simple crossguard, upright or level"),
    "broadsword": ("weapon", "a broad blade with a crossguard, diagonal"),
    "arrowhead": ("weapon", "an arrowhead tip"),
    "shield": ("object", "a heater shield"),
    "orb ring": ("shape", "the rough round border of an orb (Chromatic Orb and the like)"),
    "thunder whirl": ("symbol", "nested crescent arcs whirling round a centre (thunder)"),
    "spell-slot star": ("symbol", "the spell-slot star's top point and ray crown (Arcane Recovery, Pearl of Power; the "
                                  "star's outline is drawn a little differently each time)"),
    "Reapply ring": ("frame", "the Reapply spells' two-arc ring (D35: made in code)"),
    "Divine Strike rays": ("frame", "Divine Strike's ray fan (its melee / critical / ranged series, D30)"),
    "legendary frame": ("frame", "the legendary actions' bracket frame (D36 family)"),
}
_n = lambda fam, *keys: {k: fam for k in keys}
NAMES = {   # group key (its medoid part, key()) -> family
    **_n("ally bust", "Action_KiResonation_Blast@400,256", "Action_WildMagic_Barbarian_ProtectiveLights@256,256"),
    **_n("frontal figure", "Action_Mag_KiRestoration@136,256", "Action_Paladin_GuardTheFaithful@288,256"),
    **_n("star figure", "Spell_Enchantment_HoldPerson@144,248"),
    **_n("gesture figure", "Action_Mag_ZephyrFlash@104,160", "Action_Mag_Soulbreaker@160,120"),
    **_n("portrait", "Spell_Illusion_DisguiseSelf_HalfElf_Strong_Female@88,248"),
    **_n("portrait", "Spell_Illusion_DisguiseSelf_Tiefling_Strong_Female@376,96",
         "Spell_Illusion_DisguiseSelf_Drow_Male@400,112"),
    **_n("fire symbol", "Spell_Transmutation_ElementalWeapon_Fire@168,344", "Action_DivineStrike_Fire_Ranged@416,280"),
    **_n("lightning bolt", "Action_Mag_Hellcrawler@144,224", "Action_WildMagic_Barbarian_Teleport@304,256"),
    **_n("snowflake", "Spell_Evocation_ConeOfCold@144,248"),
    **_n("acid bubbles", "Spell_Evocation_ChromaticOrb_Acid@232,328", "Spell_Abjuration_ProtectionFromEnergy_Acid@200,256",
         "Spell_Abjuration_ProtectionFromEnergy_Acid@320,288", "Spell_Evocation_ChromaticOrb_Acid@320,224",
         "Spell_Abjuration_ProtectionFromEnergy_Acid@304,160", "Spell_Transmutation_ElementalWeapon_Acid@144,240",
         "Spell_Transmutation_ElementalWeapon_Acid@80,272", "Spell_Transmutation_ElementalWeapon_Acid@32,336",
         "Spell_Transmutation_ElementalWeapon_Acid@232,448"),
    **_n("necrotic skull", "Action_DivineStrike_Necrotic_Ranged@400,264"),
    **_n("healing cross", "Action_Paladin_HealingRadiance@192,256"),
    **_n("heart", "Action_TransmuterStone_Constitution@248,256"),
    **_n("drop", "Action_Mag_Bloodfeeding@224,256"),
    **_n("hourglass", "Skill_Sorcerer_Passive_Metamagic_ExtendedSpell@360,256"),
    **_n("spiral", "Action_MantleOfInspiration@256,256"),
    **_n("four-point sparkle", "Action_ArcaneArcher_PiercingArrow@304,216"),
    **_n("long-point star", "Action_Monk_BladeOfTheRime@128,208", "Spell_Abjuration_Counterspell@352,240"),
    **_n("spiky spore", "Action_Glut_PacifyingSpores@448,96", "Action_SymbioticEntity@360,368"),
    **_n("burst star", "Action_Mag_FlashingDawn@328,264"),
    **_n("skull", "Action_MagicItem_PoisonLethality@264,256", "Action_Paladin_DivineSmite_Critical@448,112",
         "Action_DippedPoison_Melee@160,256", "Action_DippedPoison_Melee@168,256",
),
    **_n("skull in profile", "Action_Mag_UndeadTurningAmmunition@296,368"),
    **_n("open hand", "Spell_Enchantment_CommandHalt@264,248"),
    **_n("pointing hand", "Action_Mag_UndeadTurningAmmunition@264,136", "Action_Mag_CommandUndead_Grovel@288,248"),
    **_n("beckoning hand", "Action_Mag_CommandUndead_Approach@192,360"),
    **_n("gripping fist", "Action_PactOfTheBlade_Battleaxe@392,304"),
    **_n("slim sword", "Action_Wolf_InfectiousBite@288,272", "Action_DreadAmbusher_Melee@400,256", "Action_Charger_Attack@224,224"),
    **_n("broadsword", "Action_Paladin_DivineSmite_Critical@272,280", "Action_Mag_PoisonMist@288,224",
         "Action_WildMagic_Enchant@256,248"),
    **_n("arrowhead", "Action_ForcedManeuver@224,112"),
    **_n("shield", "Action_Monster_GortashMachine_ShieldCapacitor@248,256"),
    **_n("orb ring", "Spell_Evocation_ChromaticOrb_Poison@256,256", "Action_EndGameAlly_SteelWatcherSummon@272,256",
         "Action_EndGameAlly_SteelWatcherSummon@384,416"),
    **_n("thunder whirl", "Spell_Evocation_ChromaticOrb_Thunder@248,328", "Spell_Transmutation_ElementalWeapon_Thunder@208,400"),
    **_n("spell-slot star", "Action_Mag_PearlOfPower_SpellSlotRestoration@88,256"),
    **_n("hooded figure", "Action_Cleric_BlessingOfTheTrickster@280,320"),
    **_n("Reapply ring", "Spell_Enchantment_ReapplyHex_Intelligence@272,440"),
    **_n("Divine Strike rays", "Action_DivineStrike_Physical_Critical@272,112"),
    **_n("legendary frame", "Action_Legendary_Defensive@48,112", "Action_Legendary_CrowdControl@104,56"),
}
EXCLUDE = {    # family -> icons whose part has the family's outline but draws something else (two independent visual
    # reviews of the whole-shape sheets + mine, 2026-10-17); left out of the family's cards, counts and names
    "portrait": ("Action_EndGameAlly_SteelWatcherSummon", "Action_Mag_AuraOfLeadership", "Skill_Druid_WildShape_GiantBadger",
                 "Spell_Abjuration_ArcaneLock", "Spell_Abjuration_ArcaneLock_Dismiss",
                 "Spell_Necromancy_BestowCurse_SkipTurn"),            # a gear, an orc, a badger, padlocks, a crescent
    "frontal figure": ("Action_Song_OldTimeBattles", "Action_Paladin_DreadfulAspect",        # music loops; a star figure
                       "Spell_Illusion_DisguiseSelf_HalfOrc_Male", "Spell_Illusion_DisguiseSelf_Human_Strong_Male"),
    "gesture figure": ("Action_Paladin_InquisitorsMight",),                                   # a raised hand, no head
    "slim sword": ("Action_Barbarian_FerociousAppetite", "Action_Mag_DeathWish", "Action_Wolf_InfectiousBite",
               "Spell_Conjuration_HailOfThorns", "Spell_Evocation_Darkvision", "Spell_MagicJar"),
    # a table knife, halos, fangs, a thorn streak, a slit pupil
    "long-point star": ("Action_DragonForm_ScintillatingBreath", "Action_Dragonborn_BreathWeapon_Cold",
                        "Action_Mag_FrigidBlade", "Action_Monk_BladeOfTheRime",
                        "Action_Monster_ElementalWater_WintersBreath", "Spell_Conjuration_IceKnife",
                        "Action_AstralKnowledge", "Spell_Abjuration_Counterspell", "Spell_Evocation_WallOfIce",
                        "Spell_Transmutation_FleshToGold"),           # eight-point glints; tiny + sparkles
    "orb ring": ("Action_Bash", "Action_PrecisionAttack", "Spell_Divination_Identify", "Action_EndGameAlly_SteelWatcherSummon", "Action_Glut_BlackSporeCloud",
             "Action_Glut_GreenSporeCloud", "Action_InspectMoonLantern", "Action_Legendary_PsionicVengeance",
             "Action_Monk_DrunkenTechnique", "Action_Monster_Dilophosaurus_Pounce", "Action_SelunesDream",
             "TadpoleSuperPower_BlackHole"),          # spores, gears, eyes, paws, a necklace, a gourd, a swirl
    "heart": ("Action_EndGameAlly_WatchSummon",),                                             # armour neckline
    "thunder whirl": ("Action_WildShape_Dilophosaurus", "Skill_Druid_WildShape_Bear",
                      "Spell_Abjuration_MagicCircle_Elemental"),                     # feet, a back, a lone crescent
    "skull": ("Action_Paladin_ControlUndead", "Action_Raven_BadOmen", "Spell_Abjuration_ProtectionFromPoison",
              "Spell_Evocation_ChromaticOrb_Poison"),                       # nose only, half a skull
    "four-point sparkle": ("Action_DivineStrike_Radiant_Critical", "Action_DivineStrike_Radiant_Melee",
                           "Action_DivineStrike_Radiant_Ranged", "Action_Mag_CaitiffsRestoration"),   # long-point stars
    "spell-slot star": ("Action_Monster_Duergar_MentalArrow", "Skill_Sorcerer_Passive_Metamagic_QuickenedSpell"),
}
HEAD = {"figure": "Figures", "symbol": "Symbols", "sparkle": "Sparkles and stars", "body": "Skulls and hands",
        "weapon": "Weapons", "object": "Objects", "shape": "Rings and shapes", "frame": "Frame pieces"}
STOP = set("a an the of and with in on at its it to from by over under into round around each two three four five one "
           "upright small large tall left right up down centred centered pointing facing lower upper top bottom".split())


def motif_words(ms):
    """motifs -> Counter of the words and two-word phrases each motif uses (once per motif), stop words left out"""
    c = Counter()
    for m in ms:
        w = re.findall(r"[a-z][a-z-]+", m.lower())
        c.update({x for x in w if x not in STOP} | {f"{a} {b}" for a, b in zip(w, w[1:]) if a not in STOP and b not in STOP})
    return c


def report():
    from .page import e, figure, decision, row, lede_reply, page
    from .extract import read_jsonl
    J = json.loads((D / "parts.json").read_text(encoding="utf-8"))
    Z = np.load(D / "parts.npz")
    names, bits, P, gid, best, ghosts = list(Z["names"]), Z["bits"], Z["P"], Z["gid"], Z["best"], Z["ghosts"]
    ix = {n: i for i, n in enumerate(names)}
    meta = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    mot = {r["icon"]: r["motif"] for r in read_jsonl(D.parent / "iconkit" / "motifs.jsonl")}
    hold = set((D / "holdout.txt").read_text().split())
    SZ = np.load(D / "shape.npz")
    ser = {str(n): int(s) for n, s in zip(SZ["names"], SZ["series"])}
    G, ev, IC = J["groups"], J["eval"], J["icons"]
    keys = {g["key"] for g in G}
    stale = sorted(k for k in NAMES if k not in keys)
    fam_of = {g["id"]: NAMES.get(g["key"]) for g in G}
    fams = defaultdict(list)
    for g in G:
        if fam_of[g["id"]]:
            fams[fam_of[g["id"]]].append(g)
    nm = lambda n: (meta.get(n) or {}).get("name") or n.split("_", 1)[1]
    keep = []

    @lru_cache(maxsize=96)
    def lab(i):
        m = unpack(bits[i])
        return m, ndimage.label(m, np.ones((3, 3)))[0]

    def tile(n, hl):
        """the icon's lines in grey, the strokes with (8-connected) labels hl in amber, over the dark"""
        m, L = lab(ix[n])
        im = np.full((512, 512, 3), 24, np.uint8)
        im[m] = 105
        im[np.isin(L, list(hl))] = (255, 184, 64)
        out = Image.fromarray(im).resize((128, 128), Image.LANCZOS)
        keep.append(out)
        return out

    def fig(n, hl, cap=None, size=64):
        return figure(tile(n, hl), nm(n) if cap is None else cap, n, size, n in hold)

    def ghost(g):
        im = Image.fromarray(ghosts[g]).resize((128, 128), Image.BILINEAR).convert("RGB")
        keep.append(im)
        return figure(im, "around it", "lines around the part, mean of the members, aligned on the part's box", 64)

    def fam_stats(f):
        gs = fams[f]
        fig_ = FAMILIES[f][0] == "figure"       # figures show the whole object (A), the rest part + exact repeats (B)
        hl = defaultdict(set)
        for g in gs:
            for m in g["members"]:
                if m[0] not in EXCLUDE.get(f, ()):
                    hl[m[0]] |= set(m[8]) | (set(m[9]) if fig_ else set())
        icons = sorted(hl)
        w = np.array([g["icons"] - 1 for g in gs], float)      # group medians weighted by their copies
        kk_, ee_ = ("shape_kappa", "shape_exact") if fig_ else ("repeat_kappa", "repeat_exact")
        kap = float(np.average([g[kk_] for g in gs], weights=w)) if w.sum() else 1.0
        exa = float(np.average([g[ee_] for g in gs], weights=w)) if w.sum() else 1.0

        def share(n):
            m, L = lab(ix[n])
            return np.isin(L, list(hl[n])).sum() / max(m.sum(), 1)
        return {"icons": icons, "series": len({ser.get(n, n) for n in icons}), "kappa": kap, "exact": exa,
                "grown": max(g["grown"] for g in gs), "hl": dict(hl),
                "share": float(np.median([share(n) for n in icons])),
                "hold": sum(n in hold for n in icons), "groups": gs,
                "k": {n: max((m[6] if j else 2.0) for g in gs for j, m in enumerate(g["members"]) if m[0] == n)
                      for n in icons if any(m[0] == n for g in gs for m in g["members"])}}
    FS = {f: fam_stats(f) for f in fams}
    base = motif_words(mot.values())
    nb = len(mot)

    def says(f):
        ms = [mot[n] for n in FS[f]["icons"] if n in mot]
        c = motif_words(ms)
        sc = {w: k * np.log((k / len(ms)) / (base[w] / nb)) for w, k in c.items() if k >= 2 and base[w]}
        top = sorted(sc, key=lambda w: -sc[w])[:4]
        return ", ".join(f'"{w}" {c[w]}' for w in top) or "no shared word"

    def card(f, n_show=8):
        s = FS[f]
        cat, what = FAMILIES[f]
        order = sorted(s["icons"], key=lambda n: (n in hold, -s["k"].get(n, 0), n))
        return (f'<div class=cgroup><div class=chead><b>{e(f)}</b><span>{len(s["icons"])} icons, {s["series"]} series</span>'
                f'<span>copies match {s["kappa"]:.2f} ({s["exact"]:.0%} near-identical)</span><span>{s["share"]:.0%} of their lines</span>'
                f'</div><p class=note style="margin:0 0 8px">{e(what)}. Descriptions now say: {e(says(f))}.</p><div class=crow>'
                + "".join(fig(n, s["hl"][n]) for n in order[:n_show]) + "</div></div>")

    named = sorted(fams, key=lambda f: (CATS.index(FAMILIES[f][0]), -len(FS[f]["icons"])))
    by_cat = defaultdict(list)
    for f in named:
        by_cat[FAMILIES[f][0]].append(f)
    N_DEC = 2               # user 2026-10-17: the first 3 cards were confusing; rewritten as 2 questions + defaults
    lede, reply = lede_reply(DECIDED, N_DEC)
    unnamed = [g for g in G if g["kind"] == "house" and not fam_of[g["id"]]]
    kk_named = [m[6] for f in named for g in fams[f] for m in g["members"][1:]]
    head = (f'<p class=lede>{lede} The game copies the same small drawings onto many icons. Every icon\'s line art '
            f'({ev["masters"]} icons) was cut into its strokes and the repeated drawings found by shape: <b>{ev["house"]} '
            f'recur across 3 or more spell families</b>; {len(named)} have a proposed name below, each checked by eye. Copies '
            f'are near exact: {np.median(kk_named):.2f} median on a 0 to 1 line-overlap score (1 = the same lines, '
            f'unrelated drawings {ev["null"][0]:.2f}).</p>')

    ex1 = "".join(f'<h3 style="margin:14px 0 6px;font-size:15px;color:var(--soft)">{e(HEAD[c])}</h3>'
                  + "".join(card(f, 7) for f in by_cat[c]) for c in CATS if by_cat[c])
    d1 = decision(1, N_DEC, DECIDED.get(1), len(named),
                  f"Are the {len(named)} part names right?",
                  f"The game copies the same small drawings onto many icons: a four-point sparkle on "
                  f"{len(FS['four-point sparkle']['icons'])}, a skull on {len(FS['skull']['icons'])}, a slim sword on "
                  f"{len(FS['slim sword']['icons'])}. Step 2 writes each name into the description of every icon that draws "
                  f"that part, and the editor's parts panel lists the part under the same name. Renaming is free now; after "
                  f"the next ~7 h training a rename means training again. Example: Wind Walk, Slayer and Ki Resonation: "
                  f"Blast draw the same small bust, identical on all {len(FS['ally bust']['icons'])} icons that use it, yet "
                  f"today's descriptions mix \"standing\", \"silhouette\" and \"human silhouette\" for it; proposed name "
                  f"\"ally bust\", everywhere. The names also split drawings today's words lump together: the slim "
                  f"straight sword ({len(FS['slim sword']['icons'])} icons) and the diagonal broadsword "
                  f"({len(FS['broadsword']['icons'])}) are both just \"sword\" today. On each "
                  f"card: amber = the whole shape. For figures that is the whole figure (head, shoulders, arms, body: the "
                  f"strokes joined to the repeated piece, up to the figure's usual size, so a cross or frame it touches "
                  f"stays grey); for the rest, the repeated drawing with every stroke the game repeats with it at the same "
                  f"place (a skull with its crossbones, the whole legendary frame, all four arcs of the Reapply ring). Grey "
                  f"= the rest of the icon; \"copies match\" = how alike those whole shapes are from icon to icon (0 to 1 "
                  f"line overlap, median); \"descriptions now say\" = today's words for it.",
                  ex1,
                  [("A", "Keep the names as proposed",
                    "Step 2 starts with these names. Every icon with the bust says \"ally bust\" in its description, and "
                    "the parts panel has an \"ally bust\" piece you can drop into a new icon."),
                   ("B", "Rename some first",
                    "Reply \"1B\" with your changes, e.g. \"ally bust -> party bust\". To merge two cards under one name, "
                    "write \"long-point star = four-point sparkle\". Step 2 then uses your names in the descriptions and "
                    "in the panel.")],
                  note=f"Why A: each name points at one real repeated drawing (copies {np.median(kk_named):.2f}, unrelated "
                       f"drawings {ev['null'][0]:.2f}). Pick B only if a name reads wrong to you.",
                  unit="names")

    # figures (decision 2)
    figs = [f for f in named if FAMILIES[f][0] == "figure"]
    fig_icons = sorted(n for n in names if n in mot and re.search(FIGURE_RX, mot[n].lower()))
    fig_groups = {g["id"] for f in figs for g in fams[f]}
    with_fig = [n for n in fig_icons if set(IC[n]["groups"]) & fig_groups]
    rest = [n for n in fig_icons if n not in with_fig]

    def biggest_best(n):
        sel = np.where((P[:, 0] == ix[n]) & ~np.isnan(best))[0]
        return float(best[sel[P[sel, 6].argmax()]]) if len(sel) else np.nan
    rb = np.array([biggest_best(n) for n in rest])
    rb = rb[~np.isnan(rb)]
    ex_rest = [n for n in rest if re.search(r"\b(running|leaping|kneeling|lunging|striding|crouching|jumping|dancing)\b",
                                            mot[n].lower())][:8]
    ex2 = (card("gesture figure", 8)
           + f'<div class=cgroup><div class=chead><b>figures drawn once</b><span>{len(rest)} figure icons with no copied '
             f'figure piece</span><span>closest match in any other icon: {np.median(rb):.2f} (median)</span></div>'
             f'<p class=note style="margin:0 0 8px">Many are the small posed figure (these: running, leaping, kneeling): '
             f'small open head, one stroke per limb, a new pose each time; the rest are monsters, crowds and one-off '
             f'figures.</p><div class=crow>' + "".join(fig(n, ()) for n in ex_rest) + "</div></div>")
    d2 = decision(2, N_DEC, DECIDED.get(2), len(fig_icons),
                  "Should the parts panel also offer a few whole poses from the game?",
                  f"{len(fig_icons)} icons' descriptions name a figure. {len(with_fig)} of them draw a figure piece the game "
                  f"copies exactly (the ally bust, Hold Person's star figure, Disguise Self's portrait and the others under "
                  f"Figures above): those are named parts and go in the panel either way. The other {len(rest)} draw a "
                  f"figure no other icon copies. Many of them are the small posed figure (running, kneeling, leaping): "
                  f"{len(FS['gesture figure']['icons'])} share the same small open head (the gesture figure card), but the "
                  f"pose is new every time. This question is only about whether whole poses also become ready-made pieces. Example: a new "
                  f"spell with a figure leaping sideways, like Step of the Wind: Disengage. Under A you write \"gesture "
                  f"figure, leaping\", the model draws a fresh pose the way the game draws them, and you fix an arm with the "
                  f"house brush. Under B you can also drag the figure from Hide or Mobile Shot out of the panel as a start, "
                  f"and the model redraws around it.",
                  ex2,
                  [("A", "Model draws each pose",
                    "The panel holds the figures the game copies (ally bust, frontal figure, star figure, hooded figure, "
                    "portrait). You describe "
                    "the pose in words, the model draws a new one, and the house brush fixes limbs. If a whole game icon "
                    "like Hide already fits, the editor starts from that icon anyway (settled)."),
                   ("B", "Also a few game poses",
                    "Same as A, plus a handful of poses cut from game icons (Hide, Hamstring Shot, Riposte) in the panel as "
                    "starting drafts that the model then redraws. New icons may lean toward those few poses.")],
                  note=f"Why A: the game never repeats a posed figure; these {len(rest)} figures' closest match in any other "
                       f"icon is typically {np.median(rb):.2f}, below the {T_PART} that counts as a copy. Ready-made poses "
                       f"would make new icons look more alike than the game's own.",
                  unit="figure icons")

    # defaults: what the old cards asked that Claude can settle (tell me if you disagree)
    sg = [g for g in G if g["kind"] == "series"]
    s_lines = np.median([IC[n]["series"] for n in names if IC[n]["series"] > 0])
    dflt = [("Rare parts", f"Name all {len(named)} parts, also those on only a few icons (star figure "
                           f"{len(FS['star figure']['icons'])}, the gesture figure {len(FS['gesture figure']['icons'])}), "
                           f"not just those on 8 or more: the model only learns a drawing as one thing when every icon that "
                           f"draws it uses the same word."),
            ("Look-alike groups", "Six groups join two different drawings that share an outline (fork and knife, lute neck "
                                  "and arrow shaft, eye and halo arc, small rings, ring arcs, jaws and a lightning zigzag): "
                                  "left unnamed, so the model does not blend them; their icons keep today's words. Single "
                                  "icons inside a named part that draw something else with the same outline (a slit pupil, "
                                  "a halo and fangs among the slim swords; eight-point glints among the long-point stars) are "
                                  "left out of it, listed under each part in Details."),
            ("Drawings one family repeats", f"{len(sg)} groups repeat only inside one or two families (the variants of one "
                                            f"spell or action: Glyph of Warding runes, Mantle of Majesty arcs, Arcane Shot's "
                                            f"arrow). The app already rebuilds those families exactly from their own icons "
                                            f"(Based on series, settled); no new names (about 40 more, most used by one "
                                            f"family). They are {s_lines:.0%} of the lines of the icons that have them. "
                                            f"Disguise Self's portrait and Pact of the Blade's fist are already among the "
                                            f"names."),
            ("Copied figures", "The ally bust, the frontal figure, the star figure, the hooded figure and Disguise Self's "
                               "portrait are named parts in the panel and the descriptions, highlighted whole: this follows "
                               "from the parts library you settled (D43)."),
            ("Word for the posed figure", "Descriptions that draw one say \"gesture figure\" plus the pose (running, "
                                          "kneeling, leaping), under either answer to question 2.")]
    dflt = ('<section class=decision style="border-left-color:var(--line)"><div class=dtag style="color:var(--mute)">'
            'Settled without a question<span class=n>tell me if you disagree</span></div><ul style="margin:6px 0 0;'
            'padding-left:20px;color:var(--soft)">' + "".join(f"<li><b>{e(t)}:</b> {e(x)}</li>" for t, x in dflt)
            + "</ul></section>")

    # rows
    rws = []
    for f in named:
        s = FS[f]
        order = sorted(s["icons"], key=lambda n: (-s["k"].get(n, 0), n))
        tab = ('<div class=tw-x><table class=t><tr><th>Group (middle part)</th><th>Icons</th><th>Series</th><th>Stroke '
               'match p10 / median</th><th>With exact repeats</th><th>Whole object</th><th>Lines around it</th></tr>'
               + "".join(f'<tr><td>{e(g["key"])}</td><td class=num>{g["icons"]}</td><td class=num>{g["series"]}</td>'
                         f'<td class=num>{g["kappa_p10"]:.2f} / {g["kappa_med"]:.2f}</td>'
                         f'<td class=num>{g["repeats"]:.2f}x, match {g["repeat_kappa"]:.2f}</td>'
                         f'<td class=num>{g["grown"]:.2f}x, match {g["shape_kappa"]:.2f}</td>'
                         f'<td class=num>{g["context"]:.2f}</td></tr>' for g in s["groups"]) + "</table></div>")
        ex_ = EXCLUDE.get(f, ())
        rws.append(row(len(s["icons"]), f, f"{FAMILIES[f][0]}, {s['series']} families, copies match {s['kappa']:.2f}",
                       f"{FAMILIES[f][1]}. Every icon that draws it (amber); gold outline = hold-out icon. \"With exact "
                       f"repeats\" = the stroke plus the strokes the game repeats at the same place in most of its icons "
                       f"(size against the stroke, and how well those shapes match); \"whole object\" = also the strokes "
                       f"joined to it, up to the usual size (shown for figures only); \"lines around it\" = lines around "
                       f"the stroke in half its icons, relative to the stroke (objects grow from {CTX_GROW})."
                       + (f" Left out after an eye check (a different drawing with the same outline): "
                          f"{', '.join(nm(n) for n in ex_)}." if ex_ else ""),
                       tab + '<div class=grid>' + "".join(ghost(g["id"]) for g in s["groups"][:4])
                       + "".join(fig(n, s["hl"][n]) for n in order) + "</div>"))
    rws.append(row(len(unnamed), "Unnamed house parts",
                   "name any you want kept",
                   "Groups in 3+ series that got no name: one magic item's drawing reused by its spells, weapon-and-gesture "
                   "pairings, ray fans, claws, and groups that join different drawings sharing an outline (a fork and a "
                   "knife, a lute's neck and an arrow shaft, an eye and a halo arc, small rings, ring arcs). Each shows its middle part's icon and up to 5 more; reply with a name to add one.",
                   "".join(f'<div class=twin><div class=pname style="font-size:12px;color:var(--soft)">{g["icons"]} icons, '
                           f'{g["series"]} series, kappa {g["kappa_med"]:.2f}</div><div class=grid>'
                           + "".join(fig(m[0], set(m[8]), "") for m in g["members"][:6]) + "</div></div>" for g in unnamed)))
    cov = defaultdict(list)
    for n in names:
        cov["Spell" if n.startswith("Spell_") else "Illithid" if n.startswith("TadpoleSuperPower_") else "Action"].append(n)
    ks = ("house", "series", "stroke", "own", "small")
    lab_k = {"house": "house parts", "series": "series parts", "stroke": "plain strokes", "own": "own drawing",
             "small": "tiny bits"}
    tab = ('<div class=tw-x><table class=t><tr><th>Kind</th><th>Icons</th>' + "".join(f"<th>{lab_k[k]}</th>" for k in ks)
           + "<th>Icons with a house part</th></tr>"
           + "".join(f'<tr><td>{k}</td><td class=num>{len(v)}</td>'
                     + "".join(f'<td class=num>{np.mean([IC[n][x] for n in v]):.0%}</td>' for x in ks)
                     + f'<td class=num>{sum(IC[n]["house"] > 0 for n in v)}</td></tr>' for k, v in cov.items())
           + "</table></div>")
    top = sorted(names, key=lambda n: -IC[n]["house"])[:12]
    rws.append(row(f'{ev["house_icons"]}', "Share of each icon's lines that are house parts", "by kind; mean shares",
                   f"Every line pixel of an icon falls in one of five kinds: a house part (a group in 3+ series), a series "
                   f"part, a plain stroke (straight or curved line, dot: the house brush's job, D44), the icon's own drawing "
                   f"(compound parts nobody else draws), or tiny bits (under {MIN_SHARE:.1%} of the lines or {MIN_SIDE} px). "
                   f"{ev['house_icons']} of {ev['masters']} icons draw at least one house part; per icon the house share is "
                   f"{ev['house_share'][0]:.0%} / {ev['house_share'][1]:.0%} / {ev['house_share'][2]:.0%} (median / p75 / "
                   f"p90), with series parts {ev['house_or_series_share'][0]:.0%} / {ev['house_or_series_share'][1]:.0%} / "
                   f"{ev['house_or_series_share'][2]:.0%}. {ev['house_half']} icons are half or more house parts (the most "
                   f"below).", tab + '<div class=grid>' + "".join(
                       fig(n, set(IC[n]["house_labels"]), f'{nm(n)} {IC[n]["house"]:.0%}') for n in top) + "</div>"))
    RJ = json.loads((D / "relations.json").read_text(encoding="utf-8"))["symbols"]["icons"]
    LJ = json.loads((D / "links.json").read_text(encoding="utf-8"))["frames"]
    found = [n for n, v in RJ.items() if v.get("found") and n in ix]
    sym_f = {g["id"] for f in named if FAMILIES[f][0] == "symbol" for g in fams[f]}
    fr_icons = sorted({n for f in LJ for n in f["icons"] if n in ix})
    rws.append(row(len(found), "Damage symbols and frames, cross-check",
                   "D28 / D36 libraries stay as they are",
                   f"The damage-type symbols are matched as whole templates by 2.5 (D28): found in {len(found)} v1 icons; "
                   f"{sum(bool(set(IC[n]['groups']) & sym_f) for n in found)} of them also show here as a named symbol part "
                   f"(symbols drawn as several strokes, Poison's skull and crossbones or Thunder's waves, split into plain "
                   f"strokes and do not group as one part). The {len(LJ)} frame families (D36) hold {len(fr_icons)} icons; "
                   f"{sum(IC[n]['series'] + IC[n]['house'] > 0 for n in fr_icons)} of them carry a grouped part here. Both "
                   f"libraries keep their own exact templates; the names above add the parts they miss."))
    rws.append(row(f'{ev["null"][2]:.2f}', "Method",
                   "how parts are cut, compared and grouped",
                   f"Lines = the training line art (glyph.split line share at 512, D38). Parts = 4-connected line regions "
                   f"(what a click in the editor picks). Plain strokes: skeleton shorter than {L_MIN} x the part's box "
                   f"(a straight stroke scores ~1, an arc 1.2-1.5, a ring ~3); they are {ev['stroke_lines']:.0%} of all lines, "
                   f"compound parts {ev['compound_lines']:.0%}, tiny bits {ev['small_lines']:.0%}. Compound parts are "
                   f"compared as skeletons in their own box at {S} px (any size and place), as drawn and mirrored, by "
                   f"chance-corrected tolerant overlap (relations.kappa, never alpha overlap); parts of different icons at "
                   f"random: median {ev['null'][0]:.2f}, p90 {ev['null'][1]:.2f}, p99 {ev['null'][2]:.2f}. Groups: average "
                   f"linkage cut at mean kappa {T_PART}, 3+ icons; house = 3+ series (shape.series). Whole shapes (your "
                   f"note: not just the head): every group adds the strokes the game repeats at the same place relative "
                   f"to the part in {SHARE_B:.0%}+ of its other icons (lined up on the part, 4 px tolerance, and only if "
                   f"that support drops by {DROP} when the stroke is nudged {SHIFT} px across itself, so crowded areas do "
                   f"not count); figure families also add the strokes joined to the figure (gaps under {GAP} px) up to the "
                   f"family's usual figure size ({Q:.0f}th percentile), leaving out any stroke that closes round the "
                   f"figure (a frame, ring or cross it stands in). Known misses: what a figure holds or touches inside "
                   f"that size can light up with it (Cocoon's web, Rush's lance, Zephyr Flash's wind streaks), and so can "
                   f"a ring drawn as open arcs or a cross joined to the figure (Otiluke's sphere, Revivify); Hold "
                   f"Person's figure is drawn joined to its frame, so only its head and arms light up; a head floating "
                   f"more than {GAP} px over its body stays alone (Invoke Duplicity's hood). "
                   f"Stale names (keys no "
                   f"group has after a rerun): {', '.join(stale) or 'none'}."))
    body = (head + d1 + d2 + dflt + reply
            + '<h2 class=sec>Details</h2><p class=secsub>Every named part with all its icons, then the measures.</p>'
            + "".join(rws))
    (D / "parts.html").write_text(page("House parts (D43)", body), encoding="utf-8")
    log(f"[parts] wrote {D / 'parts.html'}: {len(named)} names, {len(unnamed)} unnamed, stale names {stale}")


# ---------------------------------------------------------------- self-check
def check():
    """drawn shapes: a hook (asymmetric, with a junction) and a four-point star stamped at other sizes, places and sides
    among plain strokes -> strokes stay out, scaled copies match, a mirrored copy matches only mirrored, hook and star
    never group, the groups hold the right icons"""
    hook = [[(0, 1), (0, 0), (.8, 0)], [(0, .5), (.6, .5)]]
    star = [[(.5, 0), (.62, .38), (1, .5), (.62, .62), (.5, 1), (.38, .62), (0, .5), (.38, .38), (.5, 0)]]
    line, arc = [[(0, 0), (1, 1)]], [[(np.cos(a) / 2 + .5, np.sin(a) / 2 + .5) for a in np.linspace(.3, 1.9, 12)]]

    def icon(*items):
        im = Image.new("L", (512, 512))
        d = ImageDraw.Draw(im)
        for shape, x, y, s, flip in items:
            for pl in shape:
                d.line([(x + s * (1 - u if flip else u), y + s * v) for u, v in pl], fill=255, width=14, joint="curve")
        return np.asarray(im) > 127
    xs = [icon((hook, 60, 60, 300, 0), (line, 380, 300, 100, 0)),
          icon((hook, 300, 40, 150, 0), (star, 60, 260, 200, 0)),
          icon((hook, 200, 200, 210, 1), (arc, 20, 20, 160, 0)),
          icon((star, 250, 250, 180, 0), (line, 40, 60, 140, 0)),
          icon((star, 40, 40, 130, 0), (hook, 280, 280, 130, 0))]
    cuts = [cut_mask(m) for m in xs]
    rows = [(i, *r) for i, (_, rs, _) in enumerate(cuts) for r in rs]
    M = np.concatenate([c[2] for c in cuts])
    L = np.array([r[7] for r in rows])
    where = {0: lambda cy, cx: "hook" if cx < 340 else "line", 1: lambda cy, cx: "hook" if cy < 250 else "star",
             2: lambda cy, cx: "hook" if cy > 190 else "arc", 3: lambda cy, cx: "star" if cy > 220 else "line",
             4: lambda cy, cx: "star" if cy < 220 else "hook"}               # the drawn shape, by icon and box centre
    kind = np.array([where[i](top + h / 2, left + w / 2) for i, _, top, left, h, w, _, _ in rows])
    assert sorted(Counter(kind).items()) == [("arc", 1), ("hook", 4), ("line", 2), ("star", 3)], Counter(kind)
    plain, drawn = np.isin(kind, ("line", "arc")), np.isin(kind, ("hook", "star"))
    assert (L[plain] < L_MIN).all() and (L[drawn] >= L_MIN).all(), list(zip(kind, L))
    comp = np.where(L >= L_MIN)[0]
    Kp, Kf = kappas(M[comp])
    k, ic = kind[comp], np.array([r[0] for r in rows])[comp]
    at = lambda s, i: int(np.where((k == s) & (ic == i))[0][0])
    h0, h1, h2, s1, s4 = at("hook", 0), at("hook", 1), at("hook", 2), at("star", 1), at("star", 4)
    assert Kp[h0, h1] >= T_COPY, f"half-size hook {Kp[h0, h1]:.2f}"
    assert Kp[s1, s4] >= T_COPY, f"smaller star {Kp[s1, s4]:.2f}"
    assert Kp[h0, h2] < T_PART <= T_COPY <= Kf[h0, h2], f"mirrored hook as placed {Kp[h0, h2]:.2f}, mirrored {Kf[h0, h2]:.2f}"
    assert max(Kp[h0, s1], Kf[h0, s1]) < T_PART, f"hook vs star {max(Kp[h0, s1], Kf[h0, s1]):.2f}"
    G = cluster(np.maximum(Kp, Kf), ic)
    got = sorted((sorted(set(k[m] for m in every)), sorted(int(ic[m]) for m in mem)) for _, mem, every in G)
    assert got == [(["hook"], [0, 1, 2, 4]), (["star"], [1, 3, 4])], got
    w = window(xs[3], 250, 250, 180, 180)
    assert w[GHOST // 4:3 * GHOST // 4, GHOST // 4:3 * GHOST // 4].sum() > .8 * w.sum() > 0, "window centred on the part"
    # whole shapes: 4 icons, the hook (the repeated part) placed apart; a bar repeated far off at the same place relative
    # to it (B finds it); a body 8 px under the hook at a different angle in each (A takes it); a dense grid shifted per icon
    # (the shift test refuses it); a frame touching the body in one icon (outside the usual object size: A leaves it)
    def ws_icon(k):
        im = Image.new("L", (512, 512))
        d = ImageDraw.Draw(im)
        x, y = 60 + 20 * k, 60 + 10 * k
        for pl in hook:
            d.line([(x + 80 * u, y + 80 * v) for u, v in pl], fill=255, width=14, joint="curve")
        d.line([(x + 300, y + 40), (x + 360, y + 40)], fill=255, width=14)                      # repeated bar
        d.line([(x, y + 88), (x + 30 * (k - 1.5), y + 200 + 10 * k)], fill=255, width=14)  # body: 8 px under the foot, own angle
        for gx in range(300 + 7 * k, 500, 22):                                                    # dense grid
            d.line([(gx, 300), (gx, 500)], fill=255, width=10)
        if k == 3:
            d.rectangle((20, y + 236, 490, 505), outline=255, width=14)                           # touching frame
        return np.asarray(im) > 127, (x, y)
    icons_ = [ws_icon(k) for k in range(4)]
    parts_, labs_ = [], []
    for m, (x, y) in icons_:
        L4 = ndimage.label(m)[0]
        lab_ = int(L4[y + 2, x + 2]) or int(np.bincount(L4[y:y + 82, x:x + 82].ravel())[1:].argmax() + 1)
        r, c = np.nonzero(L4 == lab_)
        parts_.append((int(r.min()), int(c.min()), int(np.ptp(r)) + 1, int(np.ptp(c)) + 1))
        labs_.append(lab_)
    ms_ = [m for m, _ in icons_]
    WS = whole_shapes(ms_, parts_, labs_, [False] * 4, 1.0)
    for k, ((b, a), (m, (x, y))) in enumerate(zip(WS, icons_)):
        L8 = ndimage.label(m, np.ones((3, 3)))[0]
        at = lambda yy, xx: int(L8[yy, xx])
        assert at(y + 40, x + 330) in b, f"icon {k}: repeated bar not found"
        assert not {at(400, gx + 2) for gx in range(300 + 7 * k, 500, 22)} & set(b), f"icon {k}: grid taken as a repeat"
        body = at(y + 130, int(round(x + 30 * (k - 1.5) * 42 / (112 + 10 * k))))
        assert body in a and body not in b, f"icon {k}: body not joined ({body} in B {b}, A {a})"
        if k == 3:
            assert at(504, 250) not in a and at(504, 250) not in b, "touching frame taken into the object"
    assert all(not a for _, a in whole_shapes(ms_, parts_, labs_, [False] * 4, 0.0)), "context gate"
    ring_ = np.zeros((512, 512), bool)
    ImageDraw.Draw(im_ := Image.fromarray(ring_)).ellipse((100, 100, 300, 300), outline=True, width=14)
    yy_, xx_ = np.nonzero(np.asarray(im_))
    assert encloses(yy_, xx_, 200, 200) and not encloses(yy_, xx_, 200, 400) and not encloses(yy_, xx_, 106, 200), \
        "a ring encloses its centre, not a point outside it or on it"
    assert set(NAMES.values()) <= set(FAMILIES), set(NAMES.values()) - set(FAMILIES)
    assert all(f in FAMILIES for f in EXCLUDE), set(EXCLUDE) - set(FAMILIES)
    if (D / "parts.json").exists():          # names written from an earlier run must still find their group
        keys = {g["key"] for g in json.loads((D / "parts.json").read_text(encoding="utf-8"))["groups"]}
        assert set(NAMES) <= keys, f"stale names: {sorted(set(NAMES) - keys)}"
    log(f"[parts] check passed: strokes L {L[plain].round(2).tolist()}, compound {L[drawn].round(2).tolist()}; half-size "
        f"hook {Kp[h0, h1]:.2f}, smaller star {Kp[s1, s4]:.2f}, mirrored hook {Kp[h0, h2]:.2f} as placed / "
        f"{Kf[h0, h2]:.2f} mirrored, hook vs star {max(Kp[h0, s1], Kf[h0, s1]):.2f}; groups {got}; whole shapes: far "
        f"repeat found, shifted grid refused, angled body joined, touching frame left out, context gate holds")


if __name__ == "__main__":
    {"run": run, "report": lambda: report(), "check": check}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
