"""LoRA training set (5.2, Phase 6): each train icon's line art over black, as the model draws it (D25, D40: grey x alpha,
8-bit RGB), with its caption (data/captions.jsonl) in a .txt beside it, sorted into folders by repeat count so the trainer
samples every drawing at its D27 + D33 weight: each distinct drawing of a series of n drawings weighs 1/sqrt(n), a copy
group (relations.json groups) shares one drawing's weight; series = shape.npz series joined with frame families that span
several series (links.json frames). Repeats = round(weight x R), at least 1 (R 6: Disguise Self's 34 icons weigh 5.7 of a
single drawing's 6, the 5.8 D33 gives). Left out: hold-out, Reapply spells (D35; the illithid one stays), dark-line icons
(D25), icons no preset fits (the de-tint needs one).
    python -m iconkit.trainset build OUT [KIND ...]   (anaconda python; default kinds Spell Action Illithid; ~1 min / 100)
-> OUT/r<k>/<icon>.png + .txt and OUT/trainset.json (icon, weight, repeats)"""
import json, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
from PIL import Image
from .extract import D, log
from . import variants as V

R = 6
DARK_LINE = {"Spell_Evocation_Darkness", "Spell_Darkness_SorceryPoints", "Spell_Evocation_Darkvision",
             "Spell_TheThirdEye_Darkvision", "Action_TransmuterStone_Darkvision", "TadpoleSuperPower_InkBlot"}


def weights(names):
    """D27 + D33 weight per icon of names (one drawing = 1)"""
    Z = np.load(D / "shape.npz")
    ser = {str(n): int(s) for n, s in zip(Z["names"], Z["series"])}
    up = {}

    def find(s):
        while up.get(s, s) != s:
            s = up[s]
        return s
    for fam in json.loads((D / "links.json").read_text(encoding="utf-8"))["frames"]:
        ids = sorted({find(ser[n]) for n in fam["icons"] if n in ser})
        for s in ids[1:]:
            up[s] = ids[0]
    copy = {n: i for i, g in enumerate(json.loads((D / "relations.json").read_text(encoding="utf-8"))["groups"]) for n in g}
    names = set(names)
    drawing = {n: f"g{copy[n]}" if n in copy else n for n in names}
    size = {d: sum(1 for n in names if drawing[n] == d) for d in drawing.values()}
    per_series = {}
    for n in names:
        per_series.setdefault(find(ser[n]), set()).add(drawing[n])
    return {n: 1 / np.sqrt(len(per_series[find(ser[n])])) / size[drawing[n]] for n in names}


def picks(kinds):
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))["icons"]
    reapply = {r["reapply"] for r in json.loads((D / "links.json").read_text(encoding="utf-8"))["reapply"]
               if not r["reapply"].startswith("TadpoleSuperPower")}
    train = (D / "train.txt").read_text(encoding="utf-8").split()
    return [n for n in train if n in J and J[n]["kind"] in kinds and J[n]["preset"] and n not in reapply | DARK_LINE]


def image(n):
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    la = V.build(n, J, G)[1]
    return n, V.u8(np.repeat((la[..., 0] * la[..., 3])[..., None], 3, 2))


def build(out, kinds=("Spell", "Action", "Illithid")):
    out = Path(out)
    names = picks(kinds)
    w = weights(names)
    cap = {r["icon"]: r["caption"] for r in map(json.loads, (D / "captions.jsonl").read_text(encoding="utf-8").splitlines())}
    rows = []
    with Pool(6) as pool:
        for i, (n, im) in enumerate(pool.imap_unordered(image, names)):
            r = max(1, round(w[n] * R))
            (out / f"r{r}").mkdir(parents=True, exist_ok=True)
            Image.fromarray(im).save(out / f"r{r}" / f"{n}.png")
            (out / f"r{r}" / f"{n}.txt").write_text(cap[n], encoding="utf-8")
            rows.append({"icon": n, "weight": round(float(w[n]), 4), "repeats": r})
            if i % 50 == 0:
                log(f"    {i}/{len(names)} {n}: weight {w[n]:.2f}, repeats {r}")
    reps = {}
    for r in rows:
        reps[r["repeats"]] = reps.get(r["repeats"], 0) + 1
    log(f"[trainset] {len(rows)} icons of {kinds} -> {out}; icons per repeat count {dict(sorted(reps.items()))}, "
        f"{sum(r['repeats'] for r in rows)} samples per pass")
    (out / "trainset.json").write_text(json.dumps(sorted(rows, key=lambda r: r["icon"]), indent=1), encoding="utf-8")


def check():
    """weights: a lone drawing 1, a copy group (one drawing) sums to 1, Disguise Self's series ~5.5 (D33)"""
    w = weights(["Spell_Evocation_Fireball"])
    assert abs(w["Spell_Evocation_Fireball"] - 1) < 1e-9, w
    g = json.loads((D / "relations.json").read_text(encoding="utf-8"))["groups"][0]
    assert abs(sum(weights(g).values()) - 1) < 1e-9, (g, weights(g))
    ds = [n for n in picks(("Spell",)) if "DisguiseSelf" in n]
    s = sum(weights(ds).values())
    assert 4.5 < s < 6.5, (len(ds), s)
    log(f"[trainset] check ok: lone drawing 1, copy group of {len(g)} sums to 1, Disguise Self {len(ds)} icons weigh {s:.2f}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["build"]:
        build(a[1], tuple(a[2:]) or ("Spell", "Action", "Illithid"))
    elif a[:1] == ["check"]:
        check()
