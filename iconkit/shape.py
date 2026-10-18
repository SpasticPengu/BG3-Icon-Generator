"""Phase 2.6: do school / SpellType / area (and level, action cost) change how the game draws an icon? Kept in captions
and the app only if they do.
Shape = features of the line art (glyph.split lines): fill, line box, centroid, spread, angular spread, elongation and
orientation, mirror / point / rotational symmetry, strokes (2.4's parts, enclosed share, stroke width); plus the nearest
drawing by relations.kappa. A label changes the drawing if, with ONE icon per series, a cross-validated classifier on the
features or the kappa-nearest drawing guesses it better than when the label is shuffled among icons of the same intent
(so a label that only follows intent does not count). Series = shared base (kappa >= T_BASE), same display name, same
Spell_<School>_<Name> stem or one element series: counted per icon, Disguise Self's 27 faces made Illusion look like
"a face" and Hex's 7 hearts Enchantment like "a heart".
    python -m iconkit.shape [run]  -> data/shape.json + data/shape.npz (~10 min)
    python -m iconkit.shape report -> data/shape.html (review page, local: Larian art)
    python -m iconkit.shape check  -> self-check on drawn shapes"""
import json, re, sys
from collections import Counter
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.sparse.csgraph import connected_components
from .extract import D, ILLITHID_ART, parse_stats, read_jsonl, log, spell_containers
from .glyph import master, split, POOL
from .relations import lines, kappa, name_key, element_series, T_BASE
from .grammar import kind

FEATS = ("fill", "extent", "aspect", "cy", "cx", "spread", "angular", "elong", "diag", "upright", "mirror_lr", "mirror_ud",
         "rot180", "radial", "parts_log", "enclosed", "stroke")
MIN_CLASS, N_PERM, N_PERM_CLF, P_OK = 8, 200, 40, .05
# (label, kind, labels the null keeps): every test but the controls keeps intent, so a label that only follows intent fails
TESTS = (("kind", None, ()), ("intent", "Spell", ()), ("intent", "Action", ()), ("SpellType", "Spell", ("intent",)),
         ("SpellType", "Action", ("intent",)), ("school", "Spell", ("intent",)), ("area", "Spell", ("intent", "SpellType")),
         ("area", "Action", ("intent", "SpellType")), ("level", "Spell", ("intent",)), ("cost", "Spell", ("intent",)),
         ("cost", "Action", ("intent",)))
DECIDED = {1: "A", 2: "A"}                 # user, 2026-10-15 (plan D32, D33)
YY, XX = np.mgrid[:128, :128] - 63.5


def shape(x):
    """master (512,512,4) float -> (features without the 2.4 stroke ones or None if no lines, line map at 64 as placed,
    the same scaled to its line box)"""
    AL = split(x, 128)["AL"]
    placed, boxed, (_, _, h), _ = lines(x)
    m = AL > .5
    if m.sum() < 20:
        return None, placed, boxed
    r, c = np.where(m)
    W = AL.sum()
    cy, cx = (AL * YY).sum() / W, (AL * XX).sum() / W
    dy, dx = YY - cy, XX - cx
    p = np.bincount((((np.arctan2(dy, dx) + np.pi) / (2 * np.pi) * 16).astype(int) % 16).ravel(), AL.ravel(), 16)
    p = p / p.sum()
    ev, vec = np.linalg.eigh(np.array([[(AL * dy * dy).sum(), (AL * dy * dx).sum()],
                                       [(AL * dy * dx).sum(), (AL * dx * dx).sum()]]) / W)
    el, th = 1 - ev[0] / max(ev[1], 1e-6), np.arctan2(-vec[0, 1], vec[1, 1])    # major axis angle, y up
    rot = lambda a: ndimage.rotate(boxed, a, reshape=False, order=1)
    K = kappa(np.stack([boxed, boxed[:, ::-1], boxed[::-1], boxed[::-1, ::-1]] + [rot(a) for a in (30, 60, 90, 120, 150)]))[0]
    f = {"fill": m.mean(), "extent": h / 128, "aspect": (np.ptp(r) + 1) / (np.ptp(c) + 1), "cy": cy / 64, "cx": cx / 64,
         "spread": (AL * np.hypot(dy, dx)).sum() / W / 64, "angular": -(p * np.log(p + 1e-12)).sum() / np.log(16),
         "elong": el, "diag": el * np.sin(2 * th), "upright": -el * np.cos(2 * th), "mirror_lr": K[1], "mirror_ud": K[2],
         "rot180": K[3], "radial": np.median(np.r_[K[3:], K[4:]])}
    return {k: round(float(v), 4) for k, v in f.items()}, placed, boxed


def job(n):
    return n, *shape(master(n))


def area_of(st, r):
    """'area' if the icon's first SpellData is a zone / wall or has an area or explosion radius, else 'single'"""
    es = [st[x] for x in r["entries"] if st[x]["_type"] == "SpellData"]
    if not es:
        return ""
    e = es[0]
    big = e.get("SpellType") in ("Zone", "Wall") or any(float(e.get(k, 0) or 0) > 0 for k in ("AreaRadius", "ExplodeRadius"))
    return "area" if big else "single"


def labels(names, rows, st):
    kd = ["Illithid" if n in ILLITHID_ART else kind(rows[n]) for n in names]
    lv = lambda v: {"": "", "0": "cantrip", "1": "1"}.get(v, "2-3" if v in ("2", "3") else "4-9")
    cost = lambda u: "bonus action" if "BonusActionPoint" in u else "action" if re.search(r"(^|;)ActionPoint", u) else ""
    L = {"kind": kd, "intent": [rows[n]["VerbalIntent"] or "-" for n in names],
         "SpellType": [{"Wall": "Zone", "Rush": "", "Throw": "", "Teleportation": ""}.get(rows[n]["SpellType"], rows[n]["SpellType"])
                       for n in names],
         "school": [rows[n]["SpellSchool"] if k == "Spell" and rows[n]["SpellSchool"] != "None" else "" for n, k in zip(names, kd)],
         "area": [area_of(st, rows[n]) for n in names],
         "level": [lv(rows[n]["Level"]) if k == "Spell" else "" for n, k in zip(names, kd)],
         "cost": [cost(rows[n]["UseCosts"]) for n in names]}
    return {k: np.array(v) for k, v in L.items()}


def series(names, rows, K, flyouts=()):
    """series id per icon: connected by a shared base (kappa >= T_BASE), the same display name (letters, before ':',
    'reapply' dropped: Reapply Hex = Hex in a ring, 2.7), the same Spell_<School>_<Name> stem, one element series
    (relations.element_series) or one spell flyout (extract.spell_containers, 2.7: Ranger's Companion, Perform)"""
    el = {n: p for p, s in element_series(names).items() for n in s.values()}
    fly = {n: f"flyout{i}" for i, s in enumerate(flyouts) for n in s}
    keys = [np.array([(name_key(rows.get(n)) or n).replace("reapply", "") for n in names]),
            np.array(["_".join(n.split("_")[:3]) if n.startswith("Spell_") else n for n in names]),
            np.array([el.get(n, n) for n in names]), np.array([fly.get(n, n) for n in names])]
    link = K >= T_BASE
    for k in keys:
        link |= k[:, None] == k[None]
    return connected_components(link, directed=False)[1]


def clf(X, lab):
    """balanced accuracy of a 5-fold logistic regression on the features (one icon per series: folds need no groups)"""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.metrics import balanced_accuracy_score as bacc
    p = cross_val_predict(LogisticRegression(class_weight="balanced", max_iter=3000, C=.5), X, lab,
                          cv=StratifiedKFold(5, shuffle=True, random_state=0))
    return bacc(lab, p)


def nn(K, lab):
    """balanced accuracy of the kappa-nearest drawing's label (diagonal of K set low)"""
    from sklearn.metrics import balanced_accuracy_score as bacc
    return bacc(lab, lab[K.argmax(1)])


def eta2(X, lab):
    mu = X.mean(0)
    return sum((lab == c).sum() * (X[lab == c].mean(0) - mu) ** 2 for c in np.unique(lab)) / ((X - mu) ** 2).sum(0)


def test(X, K, lab, strata, rng, n_perm=N_PERM, n_clf=N_PERM_CLF):
    """observed scores vs labels shuffled within each stratum (strata = {name: array}) -> dict"""
    c0, n0, e0 = clf(X, lab), nn(K, lab), eta2(X, lab)
    out = {"n": len(lab), "classes": dict(Counter(lab.tolist()).most_common()), "chance": round(1 / len(set(lab)), 3),
           "clf": round(c0, 3), "nn": round(n0, 3), "nulls": {}}
    for sn, s in strata.items():
        C, NN, E = [], [], []
        for i in range(n_perm):
            pl = lab.copy()
            for v in np.unique(s):
                j = np.where(s == v)[0]
                pl[j] = lab[rng.permutation(j)]
            if i < n_clf:
                C.append(clf(X, pl))
            NN.append(nn(K, pl))
            E.append(eta2(X, pl))
        C, NN, E = np.array(C), np.array(NN), np.array(E)
        out["nulls"][sn] = {"clf": round(float(C.mean()), 3), "clf_p95": round(float(np.percentile(C, 95)), 3),
                            "clf_p": round(float(((C >= c0).sum() + 1) / (len(C) + 1)), 3),
                            "nn": round(float(NN.mean()), 3), "nn_p95": round(float(np.percentile(NN, 95)), 3),
                            "nn_p": round(float(((NN >= n0).sum() + 1) / (len(NN) + 1)), 3),
                            "eta2_excess": [round(float(v), 3) for v in e0 - E.mean(0)],
                            "eta2_p": [round(float(v), 3) for v in ((E >= e0).sum(0) + 1) / (len(E) + 1)]}
    out["eta2"] = [round(float(v), 3) for v in e0]
    last = out["nulls"][list(strata)[-1]]
    out["verdict"] = ("no", "weak", "yes")[(last["clf_p"] < P_OK) + (last["nn_p"] < P_OK)]
    return out


def run():
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    names = [n for f in ("train.txt", "holdout.txt") for n in (D / f).read_text().split() if (D / "masters" / f"{n}.png").exists()]
    with Pool(POOL) as pool:
        res = [r for r in pool.map(job, names, chunksize=12) if r[1] is not None]
    names = [r[0] for r in res]
    G = json.loads((D / "glyph.json").read_text(encoding="utf-8"))["icons"]
    for n, f, *_ in res:
        f.update(parts_log=round(float(np.log1p(G[n]["parts"])), 4), enclosed=G[n]["enclosed"], stroke=G[n]["stroke"][1])
    F = np.array([[r[1][k] for k in FEATS] for r in res])
    P, B = (np.stack([r[i] for r in res]) for i in (2, 3))
    log(f"[2.6] shape features for {len(names)} v1 icons")
    K = np.maximum(kappa(P), kappa(B))                                 # as placed / scaled to the line box (2.5)
    np.fill_diagonal(K, -9)
    st = parse_stats()
    ser = series(names, rows, K, spell_containers(st))
    rep = np.zeros(len(names), bool)
    rep[[np.where(ser == s)[0][0] for s in np.unique(ser)]] = True      # first member (alphabetical within a file list)
    copies = {n for g in json.loads((D / "relations.json").read_text(encoding="utf-8"))["groups"] for n in g[1:]}
    each = np.array([n not in copies for n in names])
    big = Counter(ser.tolist()).most_common(10)
    log(f"[2.6] {len(set(ser))} series for {len(names)} icons; biggest: " +
        ", ".join(f"{(rows[names[np.where(ser == s)[0][0]]]['name'] or names[np.where(ser == s)[0][0]])} x{k}" for s, k in big))
    L = labels(names, rows, st)
    Z = (F - F.mean(0)) / (F.std(0) + 1e-9)
    rng = np.random.default_rng(0)
    out = {}
    for lb, kd, keep in TESTS:
        for unit, sel0 in (("series", rep), ("icons", each)):
            sel = sel0 & (L["kind"] == kd if kd else True) & (L[lb] != "")
            cnt = Counter(L[lb][sel].tolist())
            sel &= np.isin(L[lb], [c for c, k in cnt.items() if k >= MIN_CLASS])
            ix = np.where(sel)[0]
            strata = {"nothing": np.zeros(len(ix), int), **{k: L[k][ix] for k in keep}}
            # every icon (D27 copies dropped): the view a per-icon caption gets; fewer shuffles, it is only compared
            t = test(Z[ix], K[np.ix_(ix, ix)], L[lb][ix], strata, rng, *(() if unit == "series" else (60, 20)))
            t["median"] = {c: [round(float(np.median(F[ix][L[lb][ix] == c, j])), 3) for j in range(len(FEATS))] for c in t["classes"]}
            key = f"{lb}|{kd or 'all'}|{unit}"
            out[key] = t
            nl = t["nulls"][list(t["nulls"])[-1]]
            top = np.argsort(-np.array(t["eta2"]))[:4]
            log(f"[2.6] {key}: {t['n']} icons, {len(t['classes'])} classes (chance {t['chance']}); classifier {t['clf']} "
                f"(null keeping {list(t['nulls'])[-1]} {nl['clf']}, p95 {nl['clf_p95']}, p {nl['clf_p']}), nearest drawing "
                f"{t['nn']} ({nl['nn']}, p95 {nl['nn_p95']}, p {nl['nn_p']}) -> {t['verdict']}; eta2 " +
                ", ".join(f"{FEATS[j]} {t['eta2'][j]}" for j in top))
    J = {"notes": "one icon per series (unit 'series') vs every icon but D27 copies ('icons'); clf = balanced accuracy of a "
                  "5-fold logistic regression on the z-scored FEATS, nn = of the kappa-nearest drawing's label; nulls = "
                  "labels shuffled within each value of the kept label (nothing / intent / SpellType); verdict on the last "
                  "null: yes = both p < P_OK, weak = one; median = per class per FEATS",
         "feats": FEATS, "p_ok": P_OK, "tests": out,
         "series": {"n": int(len(set(ser))), "icons": len(names),
                    "biggest": [[names[np.where(ser == s)[0][0]], k] for s, k in big]}}
    (D / "shape.json").write_text(json.dumps(J, indent=1), encoding="utf-8")
    np.savez_compressed(D / "shape.npz", names=np.array(names), F=F, P=P.astype(np.float32), K=K.astype(np.float16),
                        series=ser, rep=rep, each=each,
                        **{f"L_{k}": v for k, v in L.items()})
    log(f"[2.6] wrote {D / 'shape.json'}, {D / 'shape.npz'}")


# ---------------------------------------------------------------- review page (data/shape.html, local: Larian art)
FEAT_TXT = {"fill": "line share of the square", "extent": "line box / square", "aspect": "line box height / width",
            "cy": "centre of the lines, down + (half-widths)", "cx": "centre of the lines, right +",
            "spread": "mean distance of the lines from their centre", "angular": "lines spread round their centre (1 = evenly)",
            "elong": "elongation (0 round, 1 a line)", "diag": "leans / (+) or \\ (-)", "upright": "upright (+) or lying (-)",
            "mirror_lr": "left-right mirror symmetry", "mirror_ud": "top-bottom mirror symmetry",
            "rot180": "same upside down", "radial": "same when turned", "parts_log": "strokes (log)",
            "enclosed": "closed-shape share", "stroke": "stroke width (px at 512)"}
TITLE = {"kind": "Kind (control)", "intent": "Intent", "SpellType": "Spell type", "school": "School", "area": "Area",
         "level": "Spell level", "cost": "Action or bonus action"}


def report():
    from .page import e, figure, decision, row, lede_reply, page
    J = json.loads((D / "shape.json").read_text(encoding="utf-8"))
    Z = np.load(D / "shape.npz")
    names, F, P, ser, rep, each = (Z[k] for k in ("names", "F", "P", "series", "rep", "each"))
    names = names.tolist()
    L = {k[2:]: Z[k] for k in Z.files if k.startswith("L_")}
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    hold = set((D / "holdout.txt").read_text().split())
    T, keep = J["tests"], []
    nm = lambda n: (rows.get(n) or {}).get("name") or n.split("_", 1)[1]
    fig = lambda n, cap=None, size=64: figure(D / "masters" / f"{n}.png", nm(n) if cap is None else cap, n, size, n in hold)

    def mean_fig(ix, cap, size=80):
        m = P[ix].mean(0)
        im = Image.fromarray((m / max(m.max(), 1e-6) * 255).astype(np.uint8))
        keep.append(im)
        return figure(im, cap, f"mean line art of {len(ix)} icons", size)

    def means(lb, kd, sel, order=None):
        cl = order or list(T[f"{lb}|{kd}|series"]["classes"])
        return "".join(mean_fig(ix, f"{c} ({len(ix)})") for c in cl
                       if len(ix := np.where(sel & (L[lb] == c) & (L["kind"] == kd))[0]))

    def typical(lb, kd, c, k=6):
        """icons (one per series) of class c closest to its median on the test's 3 strongest features"""
        t = T[f"{lb}|{kd}|series"]
        js = np.argsort(-np.array(t["eta2"]))[:3]
        ix = np.where(rep & (L[lb] == c) & (L["kind"] == kd))[0]
        z = (F[:, js] - F[rep][:, js].mean(0)) / (F[rep][:, js].std(0) + 1e-9)
        d = np.abs(z[ix] - (np.array(t["median"][c])[js] - F[rep][:, js].mean(0)) / (F[rep][:, js].std(0) + 1e-9)).sum(1)
        return [names[i] for i in ix[np.argsort(d)[:k]]]

    def res(lb, kd, unit="series"):
        t = T[f"{lb}|{kd}|{unit}"]
        k = list(t["nulls"])[-1]
        return t, t["nulls"][k], k

    verdicts = {(lb, kd or "all"): T[f"{lb}|{kd or 'all'}|series"]["verdict"] for lb, kd, _ in TESTS}
    sch, sch_n, _ = res("school", "Spell")
    sch_i, sch_in, _ = res("school", "Spell", "icons")
    sta, sta_n, _ = res("SpellType", "Action")
    sts, sts_n, _ = res("SpellType", "Spell")
    ins, _, _ = res("intent", "Spell")
    cnt = lambda p: sum(n.startswith(p) for n in names)
    j = {f: i for i, f in enumerate(J["feats"])}
    med = lambda lb, kd, c, f: T[f"{lb}|{kd}|series"]["median"][c][j[f]]
    order_sch = list(T["school|Spell|series"]["classes"])
    ex = (f'<div class=cgroup><div class=chead><b>School, every icon</b> (copies of one drawing counted once)</div>'
          f'<div class=crow>{means("school", "Spell", each, order_sch)}</div></div>'
          f'<div class=cgroup><div class=chead><b>School, one icon per series</b></div>'
          f'<div class=crow>{means("school", "Spell", rep, order_sch)}</div></div>'
          f'<div class=cgroup><div class=chead><b>What made the faces and hearts</b>: Disguise Self (Illusion), Hex and '
          f'Command (Enchantment)</div><div class=crow>'
          + "".join(fig(n) for p, k in (("Spell_Illusion_DisguiseSelf", 8), ("Spell_Enchantment_Hex", 4),
                                        ("Spell_Enchantment_Command", 3)) for n in [n for n in names if n.startswith(p)][:k])
          + '</div></div>')
    for c in T["SpellType|Action|series"]["classes"]:
        ex += (f'<div class=cgroup><div class=chead><b>Actions, {e(c)}</b> (typical, one per series)</div><div class=crow>'
               + "".join(fig(n) for n in typical("SpellType", "Action", c)) + '</div></div>')
    vt = lambda lb, kd: {"yes": "changes the drawing", "weak": "a hint only", "no": "no change"}[verdicts[(lb, kd)]]
    parts = lambda c: np.expm1(med("SpellType", "Action", c, "parts_log"))
    d1 = decision(1, 2, DECIDED.get(1), J["series"]["n"],
                  "Which spell fields should shape the drawing (the model's prompt and the app's fields)?",
                  f"Measured on the line art of {J['series']['icons']} icons (symmetry, fill, centre, orientation, strokes, "
                  f"and the most similar drawing by shape). Counted icon by icon, school looks like a drawing rule: Illusion "
                  f"averages to a face, Enchantment to a heart, Abjuration to a ring (first row). That is a few series: "
                  f"Disguise Self draws {cnt('Spell_Illusion_DisguiseSelf_')} faces, Hex {cnt('Spell_Enchantment_Hex')} hearts, "
                  f"Command {cnt('Spell_Enchantment_Command')} hands. Counting each series once (second row), every school "
                  f"averages to the same round blob, and the drawing tells the school no better than the intent alone does "
                  f"(guessed right {sch['clf']:.0%} vs {sch_n['clf']:.0%} from intent, chance {sch['chance']:.0%}). Intent "
                  f"itself does shape the drawing (spells guessed {ins['clf']:.0%}, chance {ins['chance']:.0%}: debuffs are "
                  f"symmetric emblems, damage icons lopsided, mirror symmetry {med('intent', 'Spell', 'Debuff', 'mirror_lr'):.2f} "
                  f"vs {med('intent', 'Spell', 'Damage', 'mirror_lr'):.2f}). Spell type {vt('SpellType', 'Action')} on actions "
                  f"({sta['clf']:.0%} vs {sta_n['clf']:.0%} from intent, chance {sta['chance']:.0%}): cone and zone actions "
                  f"sweep diagonally with more, thinner strokes (median {parts('Zone'):.0f} strokes vs {parts('Target'):.0f} on "
                  f"single targets, {med('SpellType', 'Action', 'Zone', 'stroke'):.1f} vs "
                  f"{med('SpellType', 'Action', 'Target', 'stroke'):.1f} px wide), projectiles draw thinner strokes too (rows "
                  f"below). On spells it adds nothing to intent ({sts['clf']:.0%} vs {sts_n['clf']:.0%}). Area: spells "
                  f"{vt('area', 'Spell')}, actions {vt('area', 'Action')} (the most similar drawing only). Level "
                  f"{vt('level', 'Spell')}; action vs bonus action: spells {vt('cost', 'Spell')}, actions {vt('cost', 'Action')}.",
                  ex,
                  [("A", "The prompt follows the measurement",
                    "Captions keep intent, plus spell type on actions; school, area, level and cost stay out (4.2). The app "
                    "drops the School, Level and Use cost fields (they would change nothing) and shows Spell type for actions "
                    "only. What a drawing shows (a face, a ring, a burst) comes from the motif text (4.1) and your "
                    "description, not from labels."),
                   ("B", "Keep the plan's caption template",
                    "School and spell type in every caption, as 4.2 has it. The model would learn \"illusion\" as Disguise "
                    "Self's face and \"enchantment\" as Hex's heart, and lean that way for any new spell of that school."),
                   ("C", "Intent only",
                    "Spell type out too: the prompt has intent, damage type, motif and description. Loses the spell type "
                    "hint on actions.")],
                  note="Damage type is not tested here: it sets the colour (2.1) and the element symbol (2.5).",
                  unit="series")
    # decision 2: training weights per series (D27 weights only copies of one drawing)
    groups = json.loads((D / "relations.json").read_text(encoding="utf-8"))["groups"]
    g = {n: len(gr) for gr in groups for n in gr}
    wc = np.array([1 / g.get(n, 1) for n in names])
    m = np.array([each[ser == s].sum() for s in ser])                  # distinct drawings in the icon's series
    W = {"C": wc, "A": wc / np.sqrt(m), "B": wc / m}
    ds = np.array([n.startswith("Spell_Illusion_DisguiseSelf") for n in names])
    ut = (L["intent"] == "Utility") & (L["kind"] == "Spell")
    share = {k: w[ds & ut].sum() / w[ut].sum() for k, w in W.items()}
    i_ = lambda lb, kd: T[f"{lb}|{kd}|icons"]
    ex2 = ""
    for n, k in J["series"]["biggest"][:4]:
        ns = [names[i] for i in np.where(ser == ser[names.index(n)])[0]]
        ex2 += (f'<div class=cgroup><div class=chead><b>{e(nm(n).split(":")[0])}</b> ({k} icons, one series)</div>'
                f'<div class=crow>{"".join(fig(x) for x in ns[:12])}</div></div>')
    d2 = decision(2, 2, DECIDED.get(2), J["series"]["n"],
                  "Training: should a series of different drawings weigh less, like copies already do?",
                  f"Counted icon by icon every field looked like it shapes the drawing: school, level, area, even action "
                  f"vs bonus action (the most similar drawing shares the spell's cost {i_('cost', 'Spell')['nn']:.0%} of "
                  f"the time, {i_('cost', 'Spell')['nulls']['intent']['nn']:.0%} by chance). Counted once per series, "
                  f"only intent and the actions' spell type remain. A caption word learns what its training icons have in "
                  f"common, so big series teach words their own drawing: all {int(ds.sum())} Disguise Self icons are utility "
                  f"spells, {share['C']:.0%} of the utility spells' training weight today, so \"utility spell\" partly means "
                  f"\"a face\". D27 counts copies of one drawing (kappa .9+) as one icon, but a series of different drawings "
                  f"counts in full: {J['series']['icons']} icons are {J['series']['n']} series. The biggest below.",
                  ex2,
                  [("A", "A series counts as the square root of its size",
                    f"Each drawing of a series of n weighs 1/sqrt(n) (copies of one drawing still share theirs, D27): "
                    f"Disguise Self's {int(ds.sum())} icons weigh {W['A'][ds].sum():.1f}, {share['A']:.0%} of utility "
                    f"spells. Big series still teach their style (faces, wild magic, familiars) without owning a word. "
                    f"Square-root balancing is the usual middle ground for over-represented groups."),
                   ("B", "A series counts as one icon",
                    f"Each drawing weighs 1/n: Disguise Self weighs one icon ({share['B']:.0%} of utility spells). Series "
                    f"of distinct drawings (wild magic surges, familiars, pact weapons) are then barely seen."),
                   ("C", "Keep D27 as is",
                    f"Only copies of one drawing are down-weighted; series count in full ({share['C']:.0%} of utility "
                    f"spells are Disguise Self).")],
                  note="Series = a shared base drawing (kappa .75+), the same display name before ':', the same "
                       "Spell_School_Name file, or one element series. Every icon stays in training either way; only "
                       "its weight changes (Phase 6). Gold outline = test set.", unit="series")
    lede, reply = lede_reply(DECIDED, 2)
    tr = lambda lb, kd: (lambda s, si: f'<tr><td>{e(TITLE[lb])}</td><td>{e(kd)}</td><td class=num>{s["n"]}</td>'
                         f'<td class=num>{s["chance"]:.2f}</td><td class=num>{si["clf"]:.2f} / {si["nn"]:.2f}</td>'
                         f'<td class=num>{s["clf"]:.2f} / {s["nn"]:.2f}</td><td>{e(list(s["nulls"])[-1])}</td>'
                         f'<td class=num>{s["nulls"][list(s["nulls"])[-1]]["clf"]:.2f} / {s["nulls"][list(s["nulls"])[-1]]["nn"]:.2f}</td>'
                         f'<td>{s["verdict"]}</td></tr>')(T[f"{lb}|{kd}|series"], T[f"{lb}|{kd}|icons"])
    table = ('<div class=tw-x><table class=t><tr><th>Field</th><th>Kind</th><th>Series</th><th>Chance</th>'
             '<th>Every icon</th><th>One per series</th><th>Shuffled within</th><th>Shuffled</th><th>Verdict</th></tr>'
             + "".join(tr(lb, kd or "all") for lb, kd, _ in TESTS) + '</table></div>')

    def feat_tab(lb, kd):
        t = T[f"{lb}|{kd}|series"]
        js = np.argsort(-np.array(t["eta2"]))[:4]
        return (f'<div class=tw-x><table class=t><tr><th>{e(TITLE[lb])}, {e(kd)}</th>'
                + "".join(f'<th>{e(FEAT_TXT[J["feats"][i]])} <span class=m>({t["eta2"][i]:.2f})</span></th>' for i in js) + '</tr>'
                + "".join(f'<tr><td>{e(c)} ({k})</td>' + "".join(f'<td class=num>{t["median"][c][i]:.2f}</td>' for i in js)
                          + '</tr>' for c, k in t["classes"].items()) + '</table></div>')
    notes = "".join([
        row(len(TESTS), "Every test", "table",
            "Balanced accuracy (1 = always right) of two guesses at the field from the drawing: a classifier on the shape "
            "numbers (5-fold cross-validated) / the field of the most similar drawing (relations.kappa). Every icon = all "
            "v1 icons but copies of one drawing; one per series = the first icon of each series. Shuffled = the same "
            "guesses with the field shuffled among icons of the same intent (or spell type for area), so a field that "
            "only follows intent scores the same. Verdict: yes = both guesses beat that (p < .05), weak = one.", table),
        row(J["series"]["n"], "Series", "unit of counting",
            f"Icons linked by a shared base drawing (kappa .75+), the same display name (before ':'), the same "
            f"Spell_School_Name file stem, or one element series (2.5): {J['series']['n']} series for "
            f"{J['series']['icons']} icons. Biggest: " + ", ".join(f"{e(nm(n))} {k}" for n, k in J["series"]["biggest"]) + "."),
        row(len(TESTS), "Which shape numbers differ", "per test",
            "The four shape numbers that differ most between the field's values (share of their spread the field "
            "explains in brackets), median per value, one icon per series.",
            "".join(feat_tab(lb, kd or "all") for lb, kd, _ in TESTS)),
        row(3, "Centre and fill", "app check",
            "No field moves the drawing off centre: the lines' centre sits within a few hundredths of the middle for "
            "every value. Fill (line share of the square) varies little: illithid powers draw less, spells slightly "
            "more than actions. 2.4's ranges (stroke, extent, margin) stay the app's check on a generated glyph.")])
    body = (f'<style>.m{{color:var(--mute);font-size:12px}}.crow figure{{width:80px}}</style>'
            f'<p class=lede>Phase 2.6: does a spell\'s school, spell type or area (and level, cost) change how the game '
            f'draws its icon? {lede}</p>{d1}{d2}{reply}<h2 class=sec>Reference</h2><p class=secsub>Click a row to open it.</p>{notes}')
    (D / "shape.html").write_text(page("Shape and spell fields", body), encoding="utf-8")
    log(f"[2.6] wrote {D / 'shape.html'}")


def check():
    """drawn shapes: a ring is symmetric every way, a diagonal bar is long, diagonal and point- but not mirror-symmetric, an
    upper-left ring sits up and left; a label tied to the drawing beats the shuffle, a random one does not; same name =
    one series"""
    W = (255, 230, 200, 255)

    def draw(f, dx=0, dy=0, s=1.0):
        im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        f(ImageDraw.Draw(im), lambda *p: [256 + (v - 256) * s + (dx if i % 2 == 0 else dy) for i, v in enumerate(p)])
        return np.asarray(im).astype(np.float64) / 255
    ring = lambda d, t: d.ellipse(t(110, 110, 402, 402), outline=W, width=22)
    bar = lambda d, t: d.line(t(100, 412, 412, 100), fill=W, width=40)
    r, _, _ = shape(draw(ring))
    b, _, _ = shape(draw(bar))
    u, _, _ = shape(draw(ring, -120, -120, .4))
    assert min(r["mirror_lr"], r["mirror_ud"], r["rot180"], r["radial"]) > .8 and r["elong"] < .1 and r["angular"] > .95, r
    assert b["elong"] > .8 and b["diag"] > .8 and b["rot180"] > .8 and b["mirror_lr"] < .3, b
    assert u["cy"] < -.3 and u["cx"] < -.3 and abs(r["cy"]) < .02, (u, r)
    rng = np.random.default_rng(1)
    xs = [draw(ring if i % 2 else bar, *rng.integers(-30, 30, 2), rng.uniform(.7, 1)) for i in range(24)]
    S = [shape(x) for x in xs]
    X = np.array([[f[k] for k in FEATS[:14]] for f, _, _ in S])
    X = (X - X.mean(0)) / (X.std(0) + 1e-9)
    K = np.maximum(kappa(np.stack([p for _, p, _ in S])), kappa(np.stack([q for *_, q in S])))
    np.fill_diagonal(K, -9)
    tied = np.array(["ring" if i % 2 else "bar" for i in range(24)])
    one = {"nothing": np.zeros(24, int)}
    t1, t0 = test(X, K, tied, one, rng, 30, 30), test(X, K, rng.permutation(np.repeat(["a", "b"], 12)), one, rng, 30, 30)
    assert t1["verdict"] == "yes" and t1["clf"] > .9 and t1["nn"] > .9, t1
    assert t0["verdict"] == "no", t0
    rows = {n: {"name": nm} for n, nm in (("A_x", "Hex (Wisdom)"), ("A_y", "Hex"), ("A_z", "Bless"), ("A_w", "Reapply Hex"),
                                          ("A_v", "Aid"))}
    assert series(list(rows), rows, np.zeros((5, 5)), [{"A_z", "A_v"}]).tolist() == [0, 0, 1, 0, 1], "name, reapply, flyout"
    log(f"[2.6] check passed: ring symmetry {r['mirror_lr']:.2f}/{r['rot180']:.2f}/{r['radial']:.2f}, bar elong "
        f"{b['elong']:.2f} diag {b['diag']:.2f} mirror {b['mirror_lr']:.2f}, corner ring at ({u['cy']:.2f}, {u['cx']:.2f}); "
        f"tied label {t1['clf']}/{t1['nn']} -> {t1['verdict']}, random {t0['clf']}/{t0['nn']} -> {t0['verdict']}")


if __name__ == "__main__":
    {"run": run, "report": lambda: report(), "check": lambda: check()}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
