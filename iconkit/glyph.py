"""Phase 2.4 glyph structure, measured on the masters (512 px, straight alpha).
Lines = the drawn strokes: brightness over black (B = L*/100 x alpha) from LINE_T of the icon's p99 (ramp LINE_W wide) and
above the local midpoint between the floor (local min) and the peak (local max) around it (threshold): a painted glow
between or around close strokes sits on a floor and stays out (before: one global ramp, glow filled the gaps). Glow = the rest. Tested here: the glow grown from the lines in code, per colour preset: light E_g = light1 G(blur1) * lines'
light + light2 G(blur2) * lines' light; coverage a_g = (cover1 G(blur1) * line share + cover2 G(blur2) * ...)^gamma (dark
glows included: coverage without light). Settled before 2.4 (2.1): one gradient per icon (0.55 dE2000), white cores.
Two-colour icons (metamagic only): the lines miss a one-gradient fit by p95 > TWO_TONE_DE and every stroke (connected line
part) takes one side of a 2-means split on a*, b* (colour_split).
    python -m iconkit.glyph [fit]   -> data/glyph.json (~10 min, POOL processes: per-icon numbers, glow recipes, scores)
    python -m iconkit.glyph report  -> data/glyph.html (review page, local: Larian art)
    python -m iconkit.glyph check   -> self-check on a drawn ring"""
import json, sys
from collections import defaultdict
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, optimize
from scipy.cluster.vq import kmeans2
from .lab import rgb2lab, lab2rgb, deltaE_ciede2000
from .lab import disk, skeletonize
from .extract import D, ILLITHID_ART, TWO_TONE, read_jsonl, log
from .grammar import kind, tint, Q, DARK, NB, curve_arr, curve_dist

GS = 128                                   # px the glow is fitted at (blurs are in px at GS; x4 at 512)
LINE_T, LINE_W = .45, .2                   # lines: B / p99(B) ramps from LINE_T to LINE_T + LINE_W
FLOOR_R, PEAK_R, FLOOR_CAP, MID = 12, 20, .5, .5   # local test, px at 512 (strokes p95 20 px wide): floor = min within
                                           # FLOOR_R capped at FLOOR_CAP x p99 (wide bright fills stay lines), peak = max
                                           # within PEAK_R; MID .55 cut the dark side of shaded illithid strokes (probe glow_leak)
KEYS = ("blur1", "blur2", "light1", "light2", "cover1", "cover2", "gamma")
START = (2.0, 8.0, .8, .3, 1.5, .6, 1.0)
MIN_GLOW, FIT_N, FIT_KIND_N, MAXITER = 8, 24, 60, 6     # own recipe from 8 training icons; icons per fit; Powell sweeps
POOL = 6
SEEN = .12                                 # the hotbar's dark stone as L*/100 (grammar.DARK)
TWO_TONE_DE, TWO_TONE_PURE = 10, .9        # metamagic 13-34 dE2000, strokes 1.00 one-sided; next icon 14.2 but .63 (one hue)
DECIDED = {1: "A", 2: "A"}                 # user, 2026-10-15 (plan D25, D26)
YY, XX = np.mgrid[:512, :512]
R = np.hypot(YY - 255.5, XX - 255.5) / 256


def master(n):
    return np.asarray(Image.open(D / "masters" / f"{n}.png").convert("RGBA")).astype(np.float64) / 255


def bright(x):
    return rgb2lab(x[..., :3])[..., 0] / 100 * x[..., 3]


def threshold(B):
    """B (512 px) -> local line threshold (B units): halfway between the floor and the peak around each pixel. Over black
    the floor is 0 and it stays under the global ramp; glow filling a gap or hugging a stroke sits on a floor and falls
    below it"""
    fl = np.minimum(ndimage.grey_erosion(B, footprint=disk(FLOOR_R)), FLOOR_CAP * np.percentile(B, 99))
    return fl + MID * (ndimage.grey_dilation(B, footprint=disk(PEAK_R)) - fl)


def split(x, s=GS):
    """master (512,512,4) float -> at s px: alpha a, brightness over black B, soft line share AL (the global ramp and the
    local test, the stricter of the two, at 512 and pooled: the share of the line art that ships), the lines' light EL,
    premultiplied colour pm"""
    f = x.shape[0] // s
    pool = lambda z: z.reshape(s, f, s, f, *z.shape[2:]).mean((1, 3))
    B = bright(x)
    p = max(np.percentile(B, 99), 1e-3)
    AL = np.clip(np.minimum((B / p - LINE_T) / LINE_W, (B - threshold(B)) / p / LINE_W + .5), 0, 1)
    return {"a": pool(x[..., 3]), "B": pool(B), "AL": pool(AL), "EL": pool(B * AL), "pm": pool(x[..., :3] * x[..., 3:])}


def clean(th):
    b1, b2, l1, l2, c1, c2, g = th
    return [round(float(v), 4) for v in (max(b1, .3), max(b2, .3), max(l1, 0), max(l2, 0), max(c1, 0), max(c2, 0), max(g, .1))]


def glow(ic, th, scale=1.0):
    """the glow grown from the lines -> light over black E_g, coverage a_g (E_g <= a_g)"""
    b1, b2, l1, l2, c1, c2, g = clean(th)
    G = lambda z, s: ndimage.gaussian_filter(z, s * scale, mode="constant")
    ag = np.clip(c1 * G(ic["AL"], b1) + c2 * G(ic["AL"], b2), 0, 1) ** g
    return np.minimum(l1 * G(ic["EL"], b1) + l2 * G(ic["EL"], b2), ag), ag


def rebuild(ic, th, scale=1.0):
    """lines as drawn + the code glow under them -> (B, a), composed as variants.paint does (what ships): the line art's
    alpha al = line share x alpha grows the glow's coverage and the glow fills 1 - al (with AL alone the fit favoured
    recipes that ship worse: 3.1 spells 1.38 vs 1.14 L*). scale = px / GS"""
    al = ic["AL"] * ic["a"]
    Eg, ag = glow({"AL": al, "EL": ic["EL"]}, th, scale)
    return ic["EL"] + (1 - al) * Eg, al + (1 - al) * ag


def loss(ic, th):
    E, A = rebuild(ic, th)
    return np.abs(E - ic["B"]).mean() + np.abs(A - ic["a"]).mean()


def seen_err(ic, E, A):
    """mean |brightness difference| as seen over the hotbar dark (L* units) where either image shows anything"""
    m = (ic["a"] > .02) | (A > .02)
    return float(100 * np.abs(E + SEEN * (1 - A) - ic["B"] - SEEN * (1 - ic["a"]))[m].mean())


def structure(x):
    """stroke widths (px at 512, skeleton of the hard line mask), placement, cover; None if there are no lines"""
    ic = split(x, 512)
    a, B, m = ic["a"], ic["B"], ic["AL"] >= .5
    p99 = np.percentile(B, 99)
    if m.sum() < 50:
        return None
    wd = 2 * ndimage.distance_transform_edt(m)[skeletonize(m)]
    r_, c_ = np.where(m)
    filled = ndimage.binary_fill_holes(m)
    o = {"stroke": np.percentile(wd, [10, 50, 90]).round(1).tolist(), "thin": (wd < 8).mean(), "lines": m.mean(),
         "glow": (a > .05).mean(), "margin": min(r_.min(), c_.min(), 511 - r_.max(), 511 - c_.max()),
         "extent": max(np.ptp(r_), np.ptp(c_)) / 512,
         "off_centre": np.hypot((B * YY).sum() / B.sum() - 255.5, (B * XX).sum() / B.sum() - 255.5) / 256,
         "reach": np.percentile(R[m], 90), "parts": ndimage.label(m)[1], "enclosed": (filled & ~m).sum() / filled.sum(),
         "p99": p99}
    return {k: v if isinstance(v, list) else round(float(v), 4) for k, v in o.items()}


def colour_split(x, s=256):
    """lines vs one gradient (a*, b* per 5-L* bin) -> (p95 residual dE2000, stroke purity or None, side map or None).
    Above TWO_TONE_DE: 2-means on the lines' a*, b*; purity = share of line pixels on their stroke's majority side; side
    map (s, s) = whole strokes to their majority side, every other pixel to the side of its nearest line pixel"""
    f = x.shape[0] // s
    xs = x.reshape(s, f, s, f, 4).mean((1, 3))
    lab, a = rgb2lab(xs[..., :3]), xs[..., 3]
    line = split(x, s)["AL"] >= .5
    m = line & (a > .5)
    bi = np.clip((lab[m, 0] / (100 / NB)).astype(int), 0, NB - 1)
    mean = np.zeros((NB, 2))
    for b in np.unique(bi):
        mean[b] = lab[m, 1:][bi == b].mean(0)
    p95 = float(np.percentile(deltaE_ciede2000(lab[m], np.concatenate([lab[m, :1], mean[bi]], 1)), 95))
    if p95 <= TWO_TONE_DE:
        return p95, None, None
    side = np.zeros(line.shape, int)
    side[m] = kmeans2(lab[m, 1:], 2, seed=1, minit="++")[1]
    comp, k = ndimage.label(line)
    major = 0
    for c in range(1, k + 1):
        cm = (comp == c) & m
        if cm.any():
            cnt = np.bincount(side[cm], minlength=2)
            major += cnt.max()
            side[comp == c] = cnt.argmax()
    _, (iy, ix) = ndimage.distance_transform_edt(~line, return_indices=True)
    return p95, major / m.sum(), side[iy, ix]


def part_presets(x, presets, s=256):
    """two-colour icon -> (side map at s, [(side, preset index, dE2000)] for its two stroke sets, the redder first: hue
    nearest 12 degrees, the metamagic drop). A part's colour curve = a*, b* per lightness bin of its pixels with alpha > .3"""
    side = colour_split(x, s)[2]
    f = x.shape[0] // s
    xs = x.reshape(s, f, s, f, 4).mean((1, 3))
    lab, a = rgb2lab(xs[..., :3]), xs[..., 3]
    cs = np.stack([curve_arr(p["curve"]) for p in presets])
    out = []
    for sd in (0, 1):
        m = (side == sd) & (a > .3)
        bi = np.clip((lab[m, 0] / (100 / NB)).astype(int), 0, NB - 1)
        cur = np.array([lab[m, 1:][bi == b].mean(0) if (bi == b).sum() >= 8 else [np.nan] * 2 for b in range(NB)])
        d = curve_dist(cur, cs)
        mab = lab[m, 1:].mean(0)
        out.append((abs((np.degrees(np.arctan2(mab[1], mab[0])) - 12 + 180) % 360 - 180), sd, int(np.argmin(d)), float(np.min(d))))
    return side, [o[1:] for o in sorted(out)]


def measure_job(n):
    x = master(n)
    st = structure(x)
    p95, pure, _ = colour_split(x)
    return n, st and {**st, "gradient_p95": round(p95, 2), **({"stroke_purity": round(pure, 3)} if pure is not None else {})}


def fit_job(job):
    key, names = job
    ics = [split(master(n)) for n in names]
    r = optimize.minimize(lambda th: float(np.mean([loss(ic, th) for ic in ics])), START, method="Powell",
                          options={"maxiter": MAXITER, "xtol": 1e-3, "ftol": 1e-5})
    return key, clean(r.x), round(float(r.fun), 5), len(names)


def score_job(job):
    n, th = job
    ic = split(master(n))
    return n, {"seen_code": round(seen_err(ic, *rebuild(ic, th)), 2),
               "seen_lines": round(seen_err(ic, ic["EL"], ic["AL"] * ic["a"]), 2)}


def spread(ns, k):
    return ns[::max(1, len(ns) // k)][:k]


def borrow_job(job):
    """a colour with too few icons for its own recipe -> the existing recipe of its kind that fits its training icons best
    (Basic action white 2 actions: the kind's average glow is bright, theirs a dark shadow; the closest gradient curve,
    Action utility steel, glows too)"""
    key, names, cands = job
    ics = [split(master(n)) for n in names]
    return key, min(cands, key=lambda k: np.mean([loss(ic, cands[k]) for ic in ics]))


def run():
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    pre = {n: v[0] for n, v in G["assigned"].items() if v[1] <= G["threshold_de2000"]}
    train, hold = ([n for n in (D / f).read_text().split() if (D / "masters" / f"{n}.png").exists()]
                   for f in ("train.txt", "holdout.txt"))
    names, kinds = train + hold, ("Spell", "Action", "Illithid")
    kd_of = lambda n: "Illithid" if n in ILLITHID_ART else kind(rows[n])        # Mind Tax: an action drawn as a power
    with Pool(POOL) as pool:
        st = dict(pool.map(measure_job, names, chunksize=8))
        log(f"[2.4] measured {len(st)} masters ({sum(v is None for v in st.values())} without lines)")
        by = defaultdict(list)
        for n in train:
            by[(kd_of(n), pre.get(n))].append(n)
        jobs = [(kd, spread([n for n in train if kd_of(n) == kd], FIT_KIND_N)) for kd in kinds]
        jobs += [(f"{kd}|{p}", spread(ns, FIT_N)) for (kd, p), ns in by.items() if p and len(ns) >= MIN_GLOW]
        log(f"[2.4] fitting {len(jobs)} glow recipes ({len(kinds)} kinds + colours with {MIN_GLOW}+ training icons)")
        fits = pool.map(fit_job, sorted(jobs, key=lambda j: -len(j[1])), chunksize=1)
        R_ = {k: th for k, th, _, _ in fits}
        for k, th, l, m in sorted(fits):
            log(f"    {k:36s} {m:3d} icons, loss {l:.4f}: " + ", ".join(f"{a} {b}" for a, b in zip(KEYS, th)))
        small = [(f"{kd}|{p}", spread(ns, FIT_N), {k: th for k, th in R_.items() if k.split("|")[0] == kd})
                 for (kd, p), ns in by.items() if p and len(ns) < MIN_GLOW]
        borrow = dict(pool.map(borrow_job, small, chunksize=1))
        log(f"[2.4] {len(borrow)} small colours borrow a recipe: " + ", ".join(f"{k} <- {v}" for k, v in sorted(borrow.items())))
        own_key = lambda kd, p: f"{kd}|{p}" if f"{kd}|{p}" in R_ else borrow.get(f"{kd}|{p}", kd)
        key = lambda n: own_key(kd_of(n), pre.get(n))
        sc = dict(pool.map(score_job, [(n, R_[key(n)]) for n in names], chunksize=8))
    trs = set(train)
    icons = {n: {"kind": kd_of(n), "preset": pre.get(n), "split": "train" if n in trs else "holdout",
                 "glow_recipe": key(n), **(st[n] or {}), **sc[n]} for n in names}
    med = lambda v: round(float(np.median(v)), 2) if len(v) else None
    pc = lambda v, q: round(float(np.percentile(v, q)), 3) if len(v) else None
    ev, ranges = {}, {}
    for kd in kinds:
        for sp in ("train", "holdout"):
            vs = [v for v in icons.values() if v["kind"] == kd and v["split"] == sp]
            ev[f"{sp}/{kd}"] = {"n": len(vs), "seen_code": med([v["seen_code"] for v in vs]),
                                "seen_lines": med([v["seen_lines"] for v in vs]),
                                "seen_code_p90": pc([v["seen_code"] for v in vs], 90)}
            log(f"[2.4] {sp} {kd}: {len(vs)} icons, brightness error over the hotbar dark (L*): lines + code glow "
                f"{ev[f'{sp}/{kd}']['seen_code']} (p90 {ev[f'{sp}/{kd}']['seen_code_p90']}), lines only {ev[f'{sp}/{kd}']['seen_lines']}")
        vs = [v for v in icons.values() if v["kind"] == kd and "stroke" in v]
        ranges[kd] = {k: [pc(a, 5), pc(a, 50), pc(a, 95)] for k, a in
                      (("stroke_px", [v["stroke"][1] for v in vs]), ("extent", [v["extent"] for v in vs]),
                       ("margin_px", [v["margin"] for v in vs]), ("off_centre", [v["off_centre"] for v in vs]),
                       ("lines", [v["lines"] for v in vs]), ("glow", [v["glow"] for v in vs]))}
        log(f"[2.4] {kd} ranges p5/p50/p95: {ranges[kd]}")
    two = sorted(n for n, v in icons.items() if v.get("gradient_p95", 0) > TWO_TONE_DE and v.get("stroke_purity", 0) >= TWO_TONE_PURE)
    ev["two_tone"] = two
    ev["two_tone_next"] = max(((v["gradient_p95"], v.get("stroke_purity"), n) for n, v in icons.items()
                               if n not in two and "gradient_p95" in v), default=None)
    log(f"[2.4] two-colour icons (strokes one colour each): {two}; next highest one-gradient miss: {ev['two_tone_next']}")
    if set(two) != {n for n in TWO_TONE if n in icons}:
        log(f"[2.4] WARNING: the two-colour icons found differ from extract.TWO_TONE (D26): update it and refit grammar")
    out = {"notes": "lines = B/p99(B) ramp LINE_T..LINE_T+LINE_W (B = L*/100 x alpha) and B above the local midpoint MID "
                    "between floor (min within FLOOR_R px at 512, capped at FLOOR_CAP x p99) and peak (max within PEAK_R) "
                    "('local': FLOOR_R, PEAK_R, FLOOR_CAP, MID); glow recipes per kind and per "
                    "kind|colour (KEYS, blurs in px at 128); stroke = p10/p50/p90 width at 512 px; margin px at 512; "
                    "extent = line box / 512; off_centre / reach in half-widths; seen_* = mean |L*| difference over the "
                    "hotbar dark where either shows anything (code glow vs lines alone)",
           "line": [LINE_T, LINE_W], "local": [FLOOR_R, PEAK_R, FLOOR_CAP, MID], "keys": KEYS, "glow": R_, "borrow": borrow, "fit_loss": {k: l for k, _, l, _ in fits}, "eval": ev,
           "ranges": ranges, "icons": icons}
    (D / "glyph.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    log(f"[2.4] wrote {D / 'glyph.json'}")


# ---------------------------------------------------------------- review page (data/glyph.html, local: Larian art)
def colour(ic, th, p):
    """(game art, lines only, lines + code glow) as RGB over the hotbar dark, at GS; p = colour preset or None"""
    AL, pm, a = ic["AL"], ic["pm"], ic["a"]
    al = AL * a
    Eg, ag = glow({"AL": al, "EL": ic["EL"]}, th)
    L = np.clip(100 * Eg / np.maximum(ag, 1e-4), 0, 100)
    rgb = (tint(np.interp(L, p["lq"], Q), ag, p)[..., :3] if p else
           lab2rgb(np.stack([L, 0 * L, 0 * L], -1)))
    over = lambda c, w: np.clip(c + DARK * (1 - w[..., None]), 0, 1)
    return (over(pm, a), over(AL[..., None] * pm, al),
            over(AL[..., None] * pm + ((1 - al) * ag)[..., None] * rgb, al + (1 - al) * ag))


def report():
    from .page import e, figure, decision, row, lede_reply, page
    from . import paths as P_
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    P = {p["name"]: p for p in G["presets"]}
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    I, ev, keep = J["icons"], J["eval"], []
    name = lambda n: rows[n].get("name") or n

    def trip(n, size=128):
        v = I[n]
        ims = [Image.fromarray((c * 255).round().astype(np.uint8)) for c in colour(split(master(n)), J["glow"][v["glow_recipe"]], P.get(v["preset"]))]
        keep.extend(ims)
        caps = ("game art", "lines only", "lines + code glow")
        return (f'<div class="pair trip"><div class=pname>{e(name(n))} · {v["seen_code"]:.1f} (lines only {v["seen_lines"]:.1f})</div>'
                + "".join(figure(im, c, n, size) for im, c in zip(ims, caps)) + '</div>')

    EX = ["Spell_Evocation_Fireball", "Spell_Abjuration_DispelMagic", "Action_ArcaneArcher_BurstingArrow", "Action_Rush",
          "Action_CripplingStrike", "Action_Bear_Claws", "Action_Dash", "TadpoleSuperPower_BlackHole"]
    worst = sorted((n for n in I if "seen_code" in I[n]), key=lambda n: -I[n]["seen_code"])[:8]
    t = lambda kd: ev[f"holdout/{kd}"]
    d1 = decision(1, 1, DECIDED.get(1), len(I), "Who draws the glow: the model, or code from the lines?",
                  f"Every vanilla glyph is drawn lines plus a glow (bright on spells, dark and smoky on basic actions). A glow "
                  f"grown from the lines in code, with one recipe per colour, rebuilds the game's on test icons to a mean "
                  f"brightness error of {t('Spell')['seen_code']} L* on spells, {t('Action')['seen_code']} on actions and "
                  f"{t('Illithid')['seen_code']} on illithid powers (lines alone: {t('Spell')['seen_lines']} / "
                  f"{t('Action')['seen_lines']} / {t('Illithid')['seen_lines']}), seen over the hotbar's dark stone. On "
                  f"average it matches the game's glow at every distance from the lines (Weapon red actions within 4 L* and "
                  f"5 chroma), but not each icon's painting: in the game Rush's red pools under the figure and Dash's shadow "
                  f"sits off to one side; code draws an even halo. Each example: game art, lines only, lines + code glow; "
                  f"the number is that icon's error, L*.",
                  "".join(trip(n) for n in EX),
                  [("A", "The model draws line art, code adds the glow",
                    "Training images become the lines only: crisp edges, nearly no soft transparency, so recovering the "
                    "glow's transparency (Phase 5's hardest part: a dark glow is invisible on black) mostly goes away. Every "
                    "glow matches its colour, the app can offer a glow strength control, captions need no glow words. "
                    "Painted glow detail (smoke, Dash's offset shadow) becomes a smooth halo; dark-line icons (Darkness, "
                    "Darkvision, Ink Blot) cannot be made this way."),
                   ("B", "The model draws the glyph with its glow (plan as is, D18)",
                    "Keeps each icon's painted glow. Phase 5 has to recover soft transparency, dark glows included, and "
                    "captions carry glow-style words (Phase 4).")],
                  note="Either way the colour stays code (D18) and the hotbar recipe stays (D24).", unit="icons measured")
    def parts(n, size=96):
        """game art, then each colour's strokes (and the glow nearest them) over the hotbar dark, labelled with the closest
        colour preset (part_presets: the drop first)"""
        x = master(n)
        side, pp = part_presets(x, G["presets"])
        xs = x.reshape(256, 2, 256, 2, 4).mean((1, 3))
        a = xs[..., 3]
        over = lambda w: Image.fromarray((np.clip(xs[..., :3] * (a * w)[..., None] + DARK * (1 - (a * w)[..., None]), 0, 1) * 255).astype(np.uint8))
        ims = [over(np.ones_like(a))] + [over((side == s) * 1.0) for s, _, _ in pp]
        keep.extend(ims)
        caps = ["game art"] + [f"{G['presets'][i]['name']} {d:.1f}" for _, i, d in pp]
        return (f'<div class="pair trip"><div class=pname>{e(name(n).replace("Metamagic: ", ""))} · one-gradient miss '
                f'{I[n]["gradient_p95"]:.0f}</div>' + "".join(figure(im, c, n, size) for im, c in zip(ims, caps)) + '</div>')

    two, nxt = ev["two_tone"], ev["two_tone_next"]
    d2 = decision(2, 2, DECIDED.get(2), len(two), "Metamagic icons have two colours: offer a second colour in v1?",
                  f"Only the {len(two)} metamagic icons are drawn in two colours: their lines miss a one-colour gradient by "
                  f"{min(I[n]['gradient_p95'] for n in two):.0f}-{max(I[n]['gradient_p95'] for n in two):.0f} dE2000 (p95). The "
                  f"next icon misses by {nxt[0]:.0f}, but that is one hue at two strengths inside the same strokes, which the "
                  f"colour presets already cover. Each metamagic stroke is entirely one colour, so the two parts split "
                  f"without painting, and each part is an existing colour: the red drop is Control rose, the symbol Action "
                  f"utility steel, Basic action white 2, Buff gold or Debuff magenta. Each example: game art, then each "
                  f"colour's strokes with their glow, labelled with the closest colour preset and its distance (dE2000).",
                  "".join(parts(n) for n in two),
                  [("A", "Yes: a second colour, picked per stroke",
                    "The app gets a Second colour field and you click the strokes that take it (a stroke = one separate line "
                    "of the drawing). Each part grows its own colour's glow. Real metamagic icons become possible, for "
                    "homebrew sorcerer options too."),
                   ("B", "Not in v1: one colour per icon",
                    "A generated metamagic icon comes out in one colour (the red drop and symbol alike). A second colour can "
                    "be added later as app work only: the model does not change.")],
                  note="Either way training splits these icons and de-tints each part with its own colour, so the model "
                       "learns clean grey line art, and Metamagic red (a colour fitted on their mixed red and silver) is "
                       "retired: the drop is Control rose.", unit="icons")
    lede, reply = lede_reply(DECIDED, 2)
    rg = J["ranges"]
    rtab = "".join(f'<tr><td>{kd}</td>' + "".join(f'<td class=num>{a} / <b>{b}</b> / {c}</td>' for a, b, c in
                                                 (rg[kd][k] for k in ("stroke_px", "extent", "margin_px", "off_centre")))
                   + '</tr>' for kd in rg)
    gtab = "".join(f'<tr><td>{e(k)}</td>' + "".join(f'<td class=num>{v * (4 if i < 2 else 1):.2f}</td>' for i, v in enumerate(th))
                   + f'<td class=num>{J["fit_loss"][k]:.4f}</td></tr>' for k, th in sorted(J["glow"].items()))
    hold = sorted(n for n in I if I[n]["split"] == "holdout" and "seen_code" in I[n])
    ratio = {kd: np.median([v["glow"] / v["lines"] for v in I.values() if v["kind"] == kd]) for kd in rg}
    ill = [n for n in I if I[n]["kind"] == "Illithid"]
    game = "".join(f'<div class="pair trip"><div class=pname>{e(name(n))}</div>'
                   + "".join(figure(p, c, n, 96) for p, c in ((P_.tooltip(n), "game tooltip"), (P_.controller(n), "game controller")))
                   + '</div>' for n in ("TadpoleSuperPower_BlackHole", "TadpoleSuperPower_Charm", "Spell_Evocation_Fireball"))
    notes = "".join([
        row(len(ill), "Illithid powers have no glow (your note on Nebulous Black Hole)", "measured",
            f"The game draws illithid powers as shaded lines with crisp edges and no glow, in the tooltip and the controller "
            f"art alike: everything visible covers {ratio['Illithid']:.2f}x the lines' area (spells {ratio['Spell']:.1f}x, "
            f"actions {ratio['Action']:.1f}x), and their fitted glow is a 2 px fringe. So there is little glow to see in "
            f"the game art, the lines-only image or ours; their lit look on the PC hotbar comes from the hotbar recipe (2.2). "
            f"Fireball for contrast.", f'<div class=grid>{game}</div>'),
        row(len(I), "Line weight is one house constant", "app check",
            "Median stroke width at 512 px per icon (skeleton of the lines): 90% of icons between the 5th and 95th "
            "percentiles below, about 2 px on the 64 px hotbar; illithid powers draw thinner. Placement: the lines' box "
            "(share of the square), margin to the edge (px at 512) and how far the light's centre sits off the middle "
            "(half-widths). These ranges become the app's check on a generated glyph (warn outside p5-p95).",
            f'<table class=t><tr><th>Kind</th><th>Stroke px p5 / p50 / p95</th><th>Extent</th><th>Margin px</th>'
            f'<th>Off centre</th></tr>{rtab}</table>'),
        row(len(worst), "Where code glow does worst", "known gap",
            "Highest error with the code glow: dark-line icons (black lines on a lit fill: the light is in the fill, not "
            "the lines) and icons whose glow is painted rather than grown.",
            f'<div class=grid>{"".join(trip(n, 96) for n in worst)}</div>'),
        row(2, "Settled before 2.4", "2.1",
            "Single-hue share: every icon is one glyph run through one gradient map (0.55 dE2000), 6 two-tone exceptions. "
            "White cores: the de-tint round trip keeps them (0.5 dE2000 hold-out), per-colour core gain in grammar.json."),
        row(len(J["glow"]), "Glow recipe per colour", "fitted",
            "Blurs in px at 512; light = glow brightness per unit of line light; cover = glow opacity per unit of line; "
            f"gamma shapes the falloff. Colours with fewer than {MIN_GLOW} training icons borrow the recipe of their kind "
            f"that fits their icons best: " + ", ".join(f"{k} from {v}" for k, v in sorted(J["borrow"].items())) + ".",
            f'<div class=tw-x><table class=t><tr><th>Recipe</th>{"".join(f"<th>{k}</th>" for k in KEYS)}<th>loss</th></tr>'
            f'{gtab}</table></div>'),
        row(len(hold), "Every test icon", "for checking", "Game art, lines only, lines + code glow.",
            f'<div class=grid>{"".join(trip(n, 96) for n in hold)}</div>')])
    body = (f'<style>.trip figure{{width:auto}}.trip{{grid-template-columns:auto auto auto}}</style>'
            f'<p class=lede>Phase 2.4: how a vanilla glyph is built (lines, glow, line weight, placement), measured on '
            f'{len(I)} masters. {lede}</p>{d2}{reply}<h2 class=sec>Earlier decisions</h2>{row(1, "Decision 1: who draws the glow", "decided", "Made (your 1A), kept for reference.", d1)}<h2 class=sec>Reference</h2><p class=secsub>Click a row to open it.</p>{notes}')
    (D / "glyph.html").write_text(page("Glyph structure", body), encoding="utf-8")
    log(f"[2.4] wrote {D / 'glyph.html'}")


def check():
    """a drawn ring: lines found where drawn, stroke width = the pen, the code glow grows next to the lines only"""
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((96, 96, 416, 416), outline=(255, 230, 200, 255), width=24)
    x = np.asarray(im).astype(np.float64) / 255
    s = structure(x)
    assert 20 <= s["stroke"][1] <= 28, f"stroke {s['stroke']}"
    assert s["enclosed"] > .5 and s["parts"] == 1, "ring encloses its middle, one part"
    ic = split(x)
    assert ic["AL"][GS // 2, 26] > .9 and ic["AL"][GS // 2, GS // 2] == 0, "line share on the ring, none in the middle"
    Eg, ag = glow(ic, START)
    assert ag[GS // 2, 20] > ag[GS // 2, 4] and ag[2, 2] < .01, "glow next to the line, none far"
    assert (Eg <= ag + 1e-9).all(), "glow light never exceeds its coverage"
    E, A = rebuild(ic, START)
    assert np.allclose(E[ic["AL"] == 1], ic["B"][ic["AL"] == 1]), "lines kept as drawn"
    assert colour_split(x)[1] is None, "one colour: no split"
    im3 = Image.new("L", (512, 512), 0)
    for y in (200, 230, 400):                                  # two strokes 14 px apart, a lone one far below
        ImageDraw.Draw(im3).line((96, y, 416, y), fill=255, width=16)
    L = np.asarray(im3) / 255
    g = np.clip(3 * ndimage.gaussian_filter(L * (YY < 300), 8), 0, 1) * (1 - L)       # painted glow on the pair only
    a3 = L + g
    x3 = np.dstack([(L[..., None] * (1, .9, .8) + g[..., None] * (.75, .55, .4)) / np.maximum(a3, 1e-6)[..., None], a3])
    AL3, B3 = split(x3, 512)["AL"], bright(x3)
    old = (B3 / np.percentile(B3, 99) - LINE_T) / LINE_W
    assert old[215, 256] > .5 and AL3[215, 256] < .5, f"glow between close strokes: old {old[215, 256]:.2f}, now {AL3[215, 256]:.2f}"
    assert AL3[200, 256] > .9 and AL3[230, 256] > .9, "both strokes kept"
    assert ((AL3 >= .5) == (old >= .5))[350:450].all(), "a stroke over black keeps the global ramp"
    im2 = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(im2).ellipse((96, 96, 416, 416), outline=(220, 50, 50, 255), width=24)        # red ring, L* 49.2
    ImageDraw.Draw(im2).ellipse((200, 200, 312, 312), outline=(80, 105, 215, 255), width=24)     # blue ring, L* 47.9 (same bin)
    p95, pure, side = colour_split(np.asarray(im2).astype(np.float64) / 255)
    assert p95 > TWO_TONE_DE and pure > .99 and side[128, 54] != side[128, 106], f"two colours by stroke: {p95:.1f} {pure}"
    log(f"[2.4] check passed: stroke {s['stroke']}, ring found, glow grows next to the lines")


if __name__ == "__main__":
    {"fit": run, "report": report, "check": check}[sys.argv[1] if len(sys.argv) > 1 else "fit"]()
