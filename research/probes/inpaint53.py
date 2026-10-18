"""5.3 masked inpainting (D36 / D42): keep what a series or frame family shares in the game, the model draws the rest from
the prompt. Hold-out icons with (a) a D30 element series, (b) a D36 frame family or (c) a series, each with 2+ training
members (the LoRA's training set): base = lines in BASE_SHARE (.8, D30) of those members at 128 (relations.series_base),
x4 to 512, cut from the closest member's training image (draft53's source, the start a user picks); kept only when the
base holds 15-85% of the real drawing's lines (else nothing or everything is left to draw). The klein inpaint pipeline
(LoRA v2 12,000 x2, 4 steps, seeds 0 / 1) repaints outside the base (mask = not the base dilated KEEP_PX), from noise;
"inp_ref" also gives the base as klein reference image. Code then puts the exact base back on top (max), like D36.
Score (kappa, relations): the whole drawing to the game's, and the inside (outside the kept region, placed at 64 px) to the
game's inside; bars: base alone, the sibling as is (draft53 draft), free text-only (score53_v2 12000x2), and for (a) the
code's symbol swap (draft53 draft).
    anaconda python research/probes/inpaint53.py prep        -> outputs/inpaint53/base, mask, sets.json
    .venv/Scripts/python.exe research/probes/inpaint53.py gen   (env ICON_RUN=klein4b_all_v2) -> outputs/inpaint53/<config>/
    anaconda python research/probes/inpaint53.py score       -> outputs/inpaint53/score.json + table
    anaconda python research/probes/inpaint53.py sheet OUT.png"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "probes"))
from draft53 import k2, STEP, SCALE, SEEDS, FREE, OUT as DRAFT

OUT = ROOT / "outputs" / "inpaint53"
CONFIGS = {"inp": False, "inp_ref": True}
KEEP_PX, SHARE, MIN_PART = 6, (.15, .85), 200       # MIN_PART: base pieces under 200 px at 512 are chance dots
COLS = ["base", "sibling", "free", *CONFIGS]


def prep():
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    from iconkit import relations as R, trainset
    from iconkit.extract import log
    import compose_census as CC
    ts = {r["icon"] for r in json.loads((ROOT / "outputs/trainset_all/trainset.json").read_text(encoding="utf-8"))}
    D = json.loads((DRAFT / "drafts.json").read_text(encoding="utf-8"))
    EL = R.element_series(sorted(CC.ser))
    fam = {}
    for n, f in CC.fam.items():
        fam.setdefault(f, []).append(n)
    for d in ("base", "mask"):
        (OUT / d).mkdir(parents=True, exist_ok=True)
    rows, skipped = {}, {}
    for n, v in sorted(D.items()):
        how = v["how"][:1]
        members = ([m for m in EL[R.EL_RE.sub("*", n, 1)].values()] if how == "a" else
                   fam.get(CC.fam.get(n), []) if how == "b" else CC.by_ser.get(CC.ser.get(n), []) if how == "c" else [])
        members = [m for m in members if m != n and m in ts]
        if len(members) < 2:
            skipped[n] = f"{how}: {len(members)} training members"
            continue
        b128 = R.series_base(members)
        real = R.line_art(R.master(n))["AL"] > .5
        share = float((real & ndimage.binary_dilation(b128)).sum() / max(real.sum(), 1))
        if not SHARE[0] <= share <= SHARE[1]:
            skipped[n] = f"{how}: base holds {share:.2f} of the real lines"
            continue
        src = v["source"].split(" + ")[0]
        g = trainset.image(src)[1][..., 0]
        b512 = ndimage.binary_dilation(np.kron(b128, np.ones((4, 4), bool)), iterations=2)
        base = np.where(b512, g, 0).astype(np.uint8)
        lab, k = ndimage.label(base > 64)                 # chance overlaps of the members' insides leave dots: drop them
        small = np.isin(lab, 1 + np.flatnonzero(np.bincount(lab.ravel())[1:] < MIN_PART))
        base[ndimage.binary_dilation(small, iterations=2)] = 0
        keep = ndimage.binary_dilation(base > 64, iterations=KEEP_PX)
        Image.fromarray(np.repeat(base[..., None], 3, 2)).save(OUT / "base" / f"{n}__s0.png")
        Image.fromarray(np.where(keep, 0, 255).astype(np.uint8)).save(OUT / "mask" / f"{n}.png")
        rows[n] = {"how": v["how"], "source": src, "members": len(members), "base_share": round(share, 3)}
        log(f"[inpaint53] {how} {n}: base of {len(members)} members holds {share:.2f} of the real lines, cut from {src}")
    for n, why in skipped.items():
        log(f"[inpaint53] skipped {n}: {why}")
    (OUT / "sets.json").write_text(json.dumps({"icons": rows, "skipped": skipped}, indent=1), encoding="utf-8")
    log(f"[inpaint53] {len(rows)} icons, {len(skipped)} skipped")


def gen():
    import gc
    import numpy as np
    import torch
    from diffusers import Flux2KleinInpaintPipeline, Flux2Transformer2DModel
    from PIL import Image
    import score53 as S
    P = S.prompts("holdout")
    keys = sorted(json.loads((OUT / "sets.json").read_text(encoding="utf-8"))["icons"])
    M = ROOT / "models" / "FLUX.2-klein-4B"
    pipe = Flux2KleinInpaintPipeline.from_pretrained(M, dtype=torch.bfloat16)
    pipe.text_encoder.to("cuda")
    with torch.no_grad():
        E = torch.cat([pipe.encode_prompt([P[k] for k in keys[i:i + 8]], device="cuda")[0].cpu() for i in range(0, len(keys), 8)])
    pipe.text_encoder = None
    torch.cuda.empty_cache()
    pipe.vae.to("cuda")
    pipe.transformer = None
    gc.collect()
    pipe.transformer = Flux2Transformer2DModel.from_pretrained(M, subfolder="transformer", torch_dtype=torch.bfloat16)
    pipe.register_to_config(is_distilled=True)
    pipe.load_lora_weights(str(S.lora_file(STEP)), adapter_name="icon")
    pipe.set_adapters(["icon"], [SCALE])
    pipe.transformer.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                                              skip_modules_pattern=("pos_embed", "patch_embed", "norm", "^proj_in$",
                                                                    "^proj_out$", "lora_"))
    pipe.transformer.to("cuda")
    torch.cuda.reset_peak_memory_stats()
    print(f"[inpaint53] {len(keys)} prompts, LoRA {S.lora_file(STEP).name} x{SCALE:g}", flush=True)
    for cfg, ref in CONFIGS.items():
        for d in (OUT / cfg, OUT / f"{cfg}_raw"):
            d.mkdir(exist_ok=True)
        t, n = time.time(), 0
        for i, k in enumerate(keys):
            base = Image.open(OUT / "base" / f"{k}__s0.png").convert("RGB")
            mask = Image.open(OUT / "mask" / f"{k}.png").convert("L")
            for s in range(SEEDS):
                f = OUT / cfg / f"{k}__s{s}.png"
                if f.exists():
                    continue
                with torch.no_grad():
                    im = pipe(prompt_embeds=E[i:i + 1].to("cuda"), image=base, mask_image=mask,
                              image_reference=[base] if ref else None, strength=1.0, height=512, width=512,
                              num_inference_steps=4, guidance_scale=1.0,
                              generator=torch.Generator("cpu").manual_seed(42 + s)).images[0]
                im.save(OUT / f"{cfg}_raw" / f.name)
                Image.fromarray(np.maximum(np.asarray(im.convert("RGB")), np.asarray(base))).save(f)   # exact base on top
                n += 1
        print(f"[inpaint53] {cfg}: {n} images, {(time.time() - t) / max(n, 1):.2f} s each, peak "
              f"{torch.cuda.max_memory_allocated() / 2**30:.1f} GB (generation only)", flush=True)


def files(n, c):
    d = {"base": OUT / "base", "sibling": DRAFT / "draft", "free": FREE}.get(c, OUT / c)
    return [d / f"{n}__s{s}.png" for s in range(1 if c in ("base", "sibling") else SEEDS)]


def score_icon(n):
    import numpy as np
    from PIL import Image
    from iconkit import relations as R
    import score53 as S
    real = R.lines(R.master(n))[:2]
    keep = np.asarray(Image.open(OUT / "mask" / f"{n}.png").resize((R.S, R.S), Image.BOX)) < 128     # kept region at 64
    ins = lambda l: l[0] * ~keep
    kin = lambda a, b: float(R.kappa(np.stack([ins(a), ins(b)]))[0, 1])
    res = {}
    for c in COLS:
        fs = files(n, c)
        for f, j in zip(fs, S.jobs_for(fs)):
            r, l = S.score_job(j)
            row = {"inverted": r["inverted"]}
            if l is not None:
                row |= {"to_real": round(k2(l, real), 3), "inside": round(kin(l, real), 3)}
                if c in CONFIGS and f.name.endswith("__s0.png"):
                    row["tells"] = S.tell_stats(S.readback(OUT / f"{c}_raw" / f.name)[0])
            res.setdefault(c, {})[f.name] = row
    return n, res


def score():
    import numpy as np
    from multiprocessing import Pool
    from iconkit.extract import log
    sets = json.loads((OUT / "sets.json").read_text(encoding="utf-8"))["icons"]
    with Pool(6) as pool:
        R = dict(pool.map(score_icon, sorted(sets), chunksize=1))
    for n in R:
        R[n] |= sets[n]
    groups = {"all": set(R)} | {f"{h} {w}": {n for n in R if R[n]["how"].startswith(h)} for h, w in
                                 (("a", "element series"), ("b", "frame family"), ("c", "series"))}
    summary = {}
    for g, ns in groups.items():
        if not ns:
            continue
        log(f"[inpaint53] {g}: {len(ns)} icons; medians over icons x seeds (inverted left out)")
        for c in COLS:
            rows = [v for n in ns for v in R[n][c].values()]
            ok = [v for v in rows if "to_real" in v]
            s = {"n": len(rows), "inverted": sum(v["inverted"] for v in rows),
                 "to_real": round(float(np.median([v["to_real"] for v in ok])), 3),
                 "inside": round(float(np.median([v["inside"] for v in ok])), 3)}
            summary.setdefault(g, {})[c] = s
            log(f"[inpaint53]   {c:>8}: n {s['n']:3d}, inverted {s['inverted']}, whole to real {s['to_real']}, inside {s['inside']}")
    (OUT / "score.json").write_text(json.dumps({"summary": summary, "icons": R}, indent=1), encoding="utf-8")
    log(f"[inpaint53] -> {OUT / 'score.json'}")


def sheet(png, tile=150):
    """rows = icons by class, columns = real | base | sibling | free | configs (seed 0), the kept region outlined on base"""
    import numpy as np
    from PIL import Image, ImageDraw
    from iconkit import trainset
    S_ = json.loads((OUT / "score.json").read_text(encoding="utf-8"))["icons"]
    names = sorted(S_, key=lambda n: (S_[n]["how"], n))
    W, H = 230, 18
    im = Image.new("RGB", (W + (len(COLS) + 1) * tile, H + len(names) * tile), (30, 30, 30))
    dr = ImageDraw.Draw(im)
    for c, t in enumerate(["real", *COLS]):
        dr.text((W + c * tile + 4, 3), t, fill=(220, 220, 220))
    for r, n in enumerate(names):
        y = H + r * tile
        dr.text((4, y + 4), f"{S_[n]['how'][:1]} {n[:34]}", fill=(220, 220, 220))
        dr.text((4, y + 20), f"base {S_[n]['base_share']} of lines, {S_[n]['members']} members", fill=(150, 150, 150))
        for c, col in enumerate(COLS):
            v = S_[n][col].get(f"{n}__s0.png", {})
            dr.text((4, y + 40 + 14 * c), f"{col}: {v.get('to_real', 'inv')} / inside {v.get('inside', '-')}", fill=(170, 170, 170))
        try:
            real = trainset.image(n)[1]
        except KeyError:                                  # no preset: the master's brightness over black instead
            from iconkit import relations as R
            real = (np.repeat(np.clip(R.line_art(R.master(n), 512)["B"], 0, 1)[..., None], 3, 2) * 255).astype(np.uint8)
        im.paste(Image.fromarray(real).resize((tile, tile), Image.LANCZOS), (W, y))
        for c, col in enumerate(COLS, 1):
            t = Image.open(files(n, col)[0]).convert("RGB")
            if col == "base":                             # the repainted region in dark blue
                m = np.asarray(Image.open(OUT / "mask" / f"{n}.png")) > 127
                a = np.asarray(t).copy()
                a[m & (a.max(2) < 30)] = (20, 30, 70)
                t = Image.fromarray(a)
            im.paste(t.resize((tile, tile), Image.LANCZOS), (W + c * tile, y))
    im.save(png)
    print(f"[inpaint53] sheet {png}: {len(names)} icons", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    {"prep": prep, "gen": gen, "score": score}.get(a[0], lambda: sheet(a[1]))()
