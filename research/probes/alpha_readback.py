"""5.1 (D39): alpha read-back, before any model exists. The model draws the line art over black: one 8-bit value per pixel,
C = grey x alpha. Read it back to grey + alpha and measure what that costs:
    k     alpha = min(1, C / k), grey = C / alpha (k = 1: plain max-RGB; a pixel dimmer than k is a k-grey line fading out)
    core  the same with k = the brightest value within CORE_R px (the pixel's own stroke core), at least KMIN
k is fitted per kind on train icons (median round-trip L*), then scored on hold-out. Per icon, on the line art: |d alpha| on
drawn pixels, grey error on opaque line pixels (alpha > .9); round trip as seen over the hotbar dark (glyph.seen_err, L*):
read-back master vs the true-line master (what read-back adds) and vs the game master (3.1 gave 1.18 / 2.84 / 1.62).
Two-colour icons are left out (alpha read-back does not depend on colour).
    anaconda python research/probes/alpha_readback.py [TRAIN_STEP]    (every TRAIN_STEP-th train icon, default 6; ~10 min)
-> data/alpha_readback.json + sheet data/alpha_readback.png (worst hold-out icons for the fitted k: game | line art over
black | true-line master | read-back master | |d alpha| x4, all at 512 over the hotbar dark)"""
import sys, json
from multiprocessing import Pool
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from PIL import Image
from scipy import ndimage
from iconkit.extract import D, TWO_TONE, log
from iconkit.grammar import DARK
from iconkit import glyph, variants as V

J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
PR = {p["name"]: p for p in G["presets"]}
KS = [.3, .4, .5, .6, .7, .8, .9, 1.0]
CORE_R, KMIN = 3, .3
KINDS = ("Spell", "Action", "Illithid")


def over_black(la):
    """what the model draws: grey x alpha, 8-bit"""
    return np.round(la[..., 0] * la[..., 3] * 255) / 255


def read_back(C, k):
    a = np.minimum(1, C / k)
    g = C / np.maximum(a, 1e-6)
    return np.dstack([g, g, g, a])


def methods(C):
    core = np.maximum(ndimage.grey_dilation(C, footprint=np.ones((2 * CORE_R + 1,) * 2)), KMIN)
    return [(f"k{k:.1f}", k) for k in KS] + [("core", core)]


def scores(x, la, m, p, th, la2):
    a, a2 = la[..., 3], la2[..., 3]
    drawn, opaque = (a > .02) | (a2 > .02), a > .9
    sm2 = glyph.split(V.master(la2, p, th))
    return {"da": float(np.abs(a2 - a)[drawn].mean()), "dgrey": float(np.abs(la2[..., 0] - la[..., 0])[opaque].mean()),
            "added": glyph.seen_err(glyph.split(m), sm2["B"], sm2["a"]), "game": glyph.seen_err(glyph.split(x), sm2["B"], sm2["a"])}


def job(n):
    x, la, m, p, _ = V.build(n, J, G)
    kd = J["icons"][n]["kind"]
    p, th = PR[p], V.recipe(J, kd, p)
    sm = glyph.split(m)
    C = over_black(la)
    return {"icon": n, "kind": kd, "split": J["icons"][n]["split"], "true_game": glyph.seen_err(glyph.split(x), sm["B"], sm["a"]),
            **{name: scores(x, la, m, p, th, read_back(C, k)) for name, k in methods(C)}}


def med(rs, f):
    return round(float(np.median([f(r) for r in rs])), 3) if rs else None


def sheet(names, k, out):
    over = lambda z: z[..., :3] * z[..., 3:] + DARK * (1 - z[..., 3:])
    rows = []
    for n in names:
        x, la, m, p, _ = V.build(n, J, G)
        kd = J["icons"][n]["kind"]
        la2 = read_back(over_black(la), k[kd])
        m2 = V.master(la2, PR[p], V.recipe(J, kd, p))
        da = np.repeat(np.clip(np.abs(la2[..., 3:] - la[..., 3:]) * 4, 0, 1), 3, 2)
        rows.append(np.hstack([over(x), np.repeat(over_black(la)[..., None], 3, 2), over(m), over(m2), da]))
    Image.fromarray(V.u8(np.vstack(rows))).resize((5 * 256, len(rows) * 256), Image.LANCZOS).save(out)


def main(step=6):
    I = J["icons"]
    ok = lambda n: I[n]["preset"] and n not in TWO_TONE
    train = [n for kd in KINDS for n in sorted(n for n in I if ok(n) and I[n]["split"] == "train" and I[n]["kind"] == kd)[::step]]
    hold = sorted(n for n in I if ok(n) and I[n]["split"] == "holdout")
    log(f"[5.1] {len(train)} train (every {step}th) + {len(hold)} hold-out icons, methods {[n for n, _ in methods(np.zeros((1, 1)))]}")
    with Pool(6) as pool:
        rows = []
        for i, r in enumerate(pool.imap_unordered(job, train + hold)):
            rows.append(r)
            if i % 25 == 0:
                log(f"    {i}/{len(train) + len(hold)} {r['icon']}: k1.0 adds {r['k1.0']['added']:.2f} L*, core {r['core']['added']:.2f}")
    names = [n for n, _ in methods(np.zeros((1, 1)))]
    best = {kd: min(names[:-1], key=lambda nm: med([r for r in rows if r["split"] == "train" and r["kind"] == kd], lambda r: r[nm]["added"]))
            for kd in KINDS}
    log(f"[5.1] fitted k on train (median added L*): {best}")
    summary = {}
    for kd in KINDS:
        rs = [r for r in rows if r["split"] == "holdout" and r["kind"] == kd]
        summary[kd] = {"n": len(rs), "true_game": med(rs, lambda r: r["true_game"]), "fitted": best[kd],
                       **{nm: {s: med(rs, lambda r: r[nm][s]) for s in ("da", "dgrey", "added", "game")} for nm in ("k1.0", best[kd], "core")}}
        s = summary[kd]
        log(f"[5.1] {kd} hold-out ({len(rs)}): game vs true-line master {s['true_game']} L*; " + "; ".join(
            f"{nm}: |da| {s[nm]['da']}, grey {s[nm]['dgrey']}, adds {s[nm]['added']} L*, vs game {s[nm]['game']}" for nm in ("k1.0", best[kd], "core")))
    worst = sorted((r for r in rows if r["split"] == "holdout"), key=lambda r: -r[best[r["kind"]]]["added"])[:8]
    log("[5.1] worst hold-out (fitted k): " + ", ".join(f"{r['icon']} {r[best[r['kind']]]['added']:.2f}" for r in worst))
    (D / "alpha_readback.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1), encoding="utf-8")
    sheet([r["icon"] for r in worst], {kd: float(best[kd][1:]) for kd in KINDS}, D / "alpha_readback.png")
    log(f"[5.1] wrote {D / 'alpha_readback.json'} and sheet {D / 'alpha_readback.png'}")


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:2]))
