"""Prototype a hotbar recipe change on 1/5 of train before the ~1 h full fit (round-4 pattern).
Fits the kind's shared recipe on every 5th training icon and scores it on another 5th against the current
data/hotbar.json (its per-colour recipes). Stage A: only the named keys (default hotbar.V5_KEYS), the rest held at the
current shared recipe; stage B: every key but `unsharp` (crisp style). Keys new to hotbar.KEYS start from V5_START
(never exactly 0). Scores: MAE, colour mix, edge ratio, brightness profile, line errors (mean L*, spread, chroma), stone
detail through the glow per opacity bin, game - ours L* by ring for all pixels / bare stone / opaque lines, line L*/C*.
    anaconda python research/probes/recipe_proto.py action|spell|illithid [key ...]   (-> data/proto_<kind>.json)"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from PIL import Image
from iconkit import hotbar as hb
from iconkit.extract import D

KD, KEYS_A = sys.argv[1], sys.argv[2:] or list(hb.V5_KEYS)
H = json.loads((D / "hotbar.json").read_text(encoding="utf-8"))
G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
pre = {n: v["preset"] for n, v in G["icons"].items()}
train = set((D / "train.txt").read_text().split())
odd = H["eval"].get("not_same_size", {})
hot, B = hb.atlas(), hb.backgrounds()
t0 = time.time()
log = lambda *a: print(f"[{time.time() - t0:5.0f} s]", *a, flush=True)


def ref(n):
    q = hb.down(Image.open(D / "masters" / f"{n}.png").convert("RGBA"))
    r = hb.Ref(n, q, hb.frame_img(B, hb.frame(H, n, pre[n])), hot[n])
    r.now = hb.recipe_for(H, n, pre[n])
    return r


def score(tag, refs, x=None):
    """x = one recipe for all, None = each icon's current recipe"""
    rec = (lambda r: r.now) if x is None else (lambda r: x)
    render = lambda r, _: hb.glyph_over(r.q, r.F, rec(r))
    terms, loss = hb.objective(refs, refs, render)
    t = terms(None)
    items, byn = [(r.n, r.q, r.F, r.g) for r in refs], {r.n: r for r in refs}
    ours = lambda n, q, F: hb.glyph_over(q, F, rec(byn[n]))
    rg = hb.rings(items, ours)
    rs = lambda k: " ".join("n/a" if v != v else f"{v:+.1f}" for v in rg[k])
    lo = hb.line_stats(items, ours)
    lg = hb.line_stats(items, lambda n, q, F: hot[n])
    log(f"  {tag:9s} MAE {t['mae']:.2f}  colour mix {t['hist']:.3f}  edge {t['edge']:.2f}  profile {t['profile']:.2f}  "
        f"lines dL/dsd/dC {t['line_parts']}  stone ours/game " + " ".join(f"{a:.2f}/{b:.2f}" for a, b in zip(*t["slopes"]))
        + f"\n            game - ours L* by ring: all {rs('all')} | stone {rs('frame')} | lines {rs('lines')}"
        f"  | lines L*/C* ours {lo} game {lg}  loss {loss(None):.2f}")


ns = [n for n in sorted(train) if n in hot and n in pre and n not in odd and hb.kind(n) == KD
      and (D / "masters" / f"{n}.png").exists()]
fitset, scoreset = [ref(n) for n in ns[::5]], [ref(n) for n in ns[2::5]]
log(f"{KD}: fit {len(fitset)} (structure {len(fitset[::2])}), score {len(scoreset)}; stage A keys {KEYS_A}")
score("now", scoreset)
_, loss = hb.objective(fitset, fitset[::2])
cur = list(H["recipe"][KD]["default"])
x0 = cur + hb.V5_START[len(cur) - hb.V4:]
xa, fa = hb.nm(loss, x0, KEYS_A, 600)
log(f"  stage A loss {loss(x0):.3f} -> {fa:.3f}: " + ", ".join(f"{k} {xa[hb.KEYS.index(k)]:.3f}" for k in KEYS_A))
score("stage A", scoreset, xa)
xb, fb = hb.nm(loss, xa, hb.free("crisp", hb.KEYS), 1500)
log(f"  stage B loss {fb:.3f}: " + ", ".join(f"{k} {v:.3f}" for k, v in zip(hb.KEYS, xb)))
score("stage B", scoreset, xb)
(D / f"proto_{KD}.json").write_text(json.dumps({"keys": hb.KEYS, "stage_A": xa, "stage_B": xb}), encoding="utf-8")
