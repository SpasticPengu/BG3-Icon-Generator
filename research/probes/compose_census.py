"""How would the app make each hold-out icon? (a) D30 element series with a training sibling, (b) D36 frame family with a
training member, (c) another series with a training sibling (a "Based on" start exists), (d) copy of a training drawing
(seen_drawing), else (e) free generation; also the blind grids by the same classes (D42 evidence: 9 / 4 / 26 / 5 / 48).
    anaconda python research/probes/compose_census.py"""
import json, sys
from collections import Counter
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from iconkit import relations

D = ROOT / "data"
z = np.load(D / "shape.npz", allow_pickle=True)
ser = dict(zip(z["names"], z["series"]))
train = set((D / "train.txt").read_text().split())
hold = (D / "holdout.txt").read_text().split()
L = json.loads((D / "links.json").read_text(encoding="utf-8"))
R = json.loads((D / "relations.json").read_text(encoding="utf-8"))
seen = set(R["seen_drawing"])
el_icons = {n for v in relations.element_series(sorted(ser)).values() for n in v.values()}   # {pattern: {element: icon}}
fam = {n: f["family"] for f in L["frames"] for n in f["icons"]}
fam_train = {f["family"] for f in L["frames"] if any(n in train for n in f["icons"])}
by_ser = {}
for n, s in ser.items():
    by_ser.setdefault(s, []).append(n)


def how(n):
    sib = [m for m in by_ser.get(ser.get(n), []) if m != n and m in train]
    if n in el_icons and sib:
        return "a D30 element series"
    if fam.get(n) in fam_train:
        return "b D36 frame family"
    if n in seen:
        return "d copy of a training drawing"
    if sib:
        return "c other series, sibling in training"
    return "e free generation"


C = Counter(how(n) for n in hold)
print(f"hold-out {len(hold)}:", dict(sorted(C.items())))
for g in ("blind_2500x2", "blind_base2500x1"):
    K = json.loads((ROOT / f"outputs/score53/{g}_key.json").read_text(encoding="utf-8"))
    print(g, dict(sorted(Counter(how(v["icon"]) for v in K.values()).items())))
    print("   ", {i: how(v["icon"])[0] for i, v in K.items()})
