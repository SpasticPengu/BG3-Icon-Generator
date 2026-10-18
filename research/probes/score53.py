"""5.3 scoring (D39, D29, D40): generate on the distilled FLUX.2-klein-4B (4 steps) with LoRA checkpoints x strengths, then
score what comes out. Prompts are encoded once (Qwen3 on the card, then dropped) and the transformer stays on the card in
fp8 storage (gen's docstring), so a batch costs only its 4 steps (~1.5 s per image).
    .venv/Scripts/python.exe research/probes/score53.py gen OUT SET CONFIG... [--seeds N] [--batch B]   (defaults 2, 2)
        SET = holdout (data/holdout.txt captions) | holdout_nodesc (no game description) | holdout_nomotif (no motif)
              | holdout_srd (no motif, the SRD 5.1 spell text's first paragraph instead: 23 spells)
              | unseen (UNSEEN: objects no motif names)
        CONFIG = none | refs (no LoRA, REFS' line art as klein reference images: D39's control row)
                 | base:CONFIG (the base model the LoRA was trained on: BASE_STEPS steps, guidance 4; tag base...)
                 | STEP:SCALE[,SCALE...] (STEP of RUN's checkpoints, env ICON_RUN; the last step = the final file)
        -> OUT/<none | STEPxSCALE>/<icon>__s<seed>.png + gen.json (seconds per image, peak GB)
    anaconda python research/probes/score53.py score OUT [TAG...]    (~1.5 s per image, 6 processes; TAGs: only those)
        -> OUT/score.json + table. Per config: inverted (black on white: the border is bright), and on the rest: line
           chroma (the model should draw grey, D18), haze (alpha far from any stroke, the VAE's; real line art beside it),
           closest training drawing (relations.kappa on the D40 read-back's master: D29's yardstick is the test set's own
           spread, median .50 / p90 .84, none >= .9; seen_drawing prompts scored apart)
    anaconda python research/probes/score53.py steer REF_DIR OTHER_DIR...   -> kappa to the real drawing / to REF (steer.json)
    anaconda python research/probes/score53.py tells OUT TAG...    -> real vs generated line stats (tells.json)
    python research/probes/score53.py sheet OUT OUT.png TAG...       (any python with Pillow) -> configs x 16 prompts
    anaconda python research/probes/score53.py blind OUT TAG    -> OUT/blind_TAG.png + _key.json (real vs generated pairs)"""
import gc, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
RUN = ROOT / "outputs" / "lora" / os.environ.get("ICON_RUN", "klein4b_all_v1")   # ICON_RUN=klein4b_all_v2 for v2
SIZE, STEPS, BASE_STEPS, K_ALPHA = 512, 4, 28, .8
TRAINSET = ROOT / "outputs" / "trainset_all"
REFS = ("Spell_Evocation_MagicMissile", "Spell_Enchantment_Hex", "Action_Dash", "TadpoleSuperPower_Levitate")  # D39 control
UNSEEN = {   # 5.3: objects in 0 of 1,083 motifs, worded like the captions (kind, source, intent, motif)
    "lantern": "bg3 spell icon, utility, an old lantern with a flame inside, upright, symmetric.",
    "candle": "bg3 spell icon, buff, a lit candle on a small dish with a teardrop flame, upright.",
    "mirror": "bg3 spell icon, utility, an oval hand mirror with an ornate frame and a handle, tilted to the right.",
    "ladder": "bg3 action icon, basic action, a wooden ladder leaning to the right, diagonal.",
    "cauldron": "bg3 spell icon, damage, fire damage, a cauldron with flames rising from it, symmetric.",
    "anvil": "bg3 action icon, weapon action, damage, weapon damage, an anvil struck by a hammer, sparks flying up, diagonal.",
    "clock": "bg3 spell icon, control, a clock face with its hands spinning, cracks across it.",
    "compass": "bg3 spell icon, utility, a round compass with its needle pointing to the upper right.",
    "padlock": "bg3 action icon, basic action, a heavy padlock with its shackle closed, symmetric.",
    "dice": "bg3 spell icon, buff, two six-sided dice tumbling, one tilted to the left.",
    "throne": "bg3 action icon, story, a tall-backed throne seen from the front, symmetric.",
    "mushroom": "bg3 spell icon, healing, a cluster of three mushrooms with spotted caps, upright.",
}


def prompts(which):
    if which == "unseen":
        return dict(UNSEEN)
    hold = set((D / "holdout.txt").read_text(encoding="utf-8").split())
    rows = [json.loads(l) for l in (D / "captions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    P = {r["icon"]: r["caption"] for r in rows if r["icon"] in hold}
    if which == "holdout":
        return P
    meta = {json.loads(l)["icon"]: json.loads(l) for l in (D / "meta.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    srd = {x["index"]: x["text"].split("\n")[0] for x in json.loads((D / "srd_spells.json").read_text(encoding="utf-8"))}
    out = {}
    for r in rows:   # captions = "tags, motif." + " description" (captions.caption): drop or swap one part
        if r["icon"] not in hold:
            continue
        c, m = r["caption"], r["motif"].strip().rstrip(".")
        i = c.index(m)
        pre, desc = c[:i].rstrip(", "), c[i + len(m) + 1:].strip()
        if which == "holdout_nodesc":
            out[r["icon"]] = f"{pre}, {m}."
        elif which == "holdout_nomotif":
            out[r["icon"]] = f"{pre}." + (f" {desc}" if desc else "")
        elif which == "holdout_srd" and meta[r["icon"]].get("srd"):   # SRD 5.1 flavour (CC-BY-4.0) for the motif
            out[r["icon"]] = f"{pre}. {srd[meta[r['icon']]['srd']]}"
    return out


def lora_file(step):
    f = RUN / f"{RUN.name}_{step:09d}.safetensors"
    return f if f.exists() else RUN / f"{RUN.name}.safetensors"     # the last step is saved without its number


def gen(out, which, configs, seeds=2, batch=2):
    """transformer weights stored in fp8, computed in bf16 (diffusers layerwise casting: 3.9 GB on the card, the 8 GB-card
    setting; draws like bf16). bf16 resident + Firefox oversubscribed the 10 GB card (13 s per image). The LoRA is loaded
    first and left out of the casting: peft casts a later-loaded adapter to its base layer's fp8 (no fp8 matmul)."""
    import torch
    from diffusers import Flux2KleinPipeline, Flux2Transformer2DModel
    from PIL import Image
    P = prompts(which)
    keys = sorted(P)
    M = ROOT / "models" / "FLUX.2-klein-4B"
    pipe = Flux2KleinPipeline.from_pretrained(M, dtype=torch.bfloat16)
    t = time.time()
    pipe.text_encoder.to("cuda")
    with torch.no_grad():
        E = torch.cat([pipe.encode_prompt([P[k] for k in keys[i:i + 8]], device="cuda")[0].cpu()
                       for i in range(0, len(keys), 8)])
        NEG = pipe.encode_prompt([""], device="cuda")[0].cpu()        # the base model's CFG negative
    pipe.text_encoder = None
    torch.cuda.empty_cache()
    pipe.vae.to("cuda")
    print(f"[5.3] {len(keys)} {which} prompts encoded in {time.time() - t:.0f} s", flush=True)
    jobs = [(k, s) for k in keys for s in range(seeds)]
    for cfg in configs:
        base = cfg.startswith("base:")          # base:STEP:SCALE = the model the LoRA was trained on, BASE_STEPS steps, CFG 4
        c = cfg[5:] if base else cfg
        step, scales = (None, [0.0]) if c in ("none", "refs") else (int(c.split(":")[0]),
                                                                     [float(x) for x in c.split(":")[1].split(",")])
        tags = [("base" if base else "") + (c if step is None else f"{step}x{sc:g}") for sc in scales]
        refs = [Image.open(next(TRAINSET.glob(f"r*/{n}.png"))).convert("RGB") for n in REFS] if cfg == "refs" else None
        if all((Path(out) / t / "gen.json").exists() for t in tags):
            continue
        if pipe.transformer is not None:   # else the old one stays on the card (layerwise hooks keep a reference)
            pipe.transformer.to("cpu")
        pipe.transformer = None
        gc.collect()
        torch.cuda.empty_cache()
        if base:
            B = ROOT / "models" / "FLUX.2-klein-base-4B"
            pipe.transformer = Flux2Transformer2DModel.from_single_file(
                str(B / "flux-2-klein-base-4b.safetensors"), config=str(B), subfolder="transformer", torch_dtype=torch.bfloat16)
        else:
            pipe.transformer = Flux2Transformer2DModel.from_pretrained(M, subfolder="transformer", torch_dtype=torch.bfloat16)
        pipe.register_to_config(is_distilled=not base)
        if step is not None:
            pipe.load_lora_weights(str(lora_file(step)), adapter_name="icon")
        pipe.transformer.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                                                  skip_modules_pattern=("pos_embed", "patch_embed", "norm", "^proj_in$",
                                                                        "^proj_out$", "lora_"))
        pipe.transformer.to("cuda")
        print(f"[5.3] {cfg}: transformer (fp8) + VAE on the card, {torch.cuda.memory_allocated() / 2**30:.1f} GB", flush=True)
        for sc in scales:
            tag = ("base" if base else "") + (c if step is None else f"{step}x{sc:g}")
            d = Path(out) / tag
            if (d / "gen.json").exists():
                continue
            d.mkdir(parents=True, exist_ok=True)
            if step is not None:
                pipe.set_adapters(["icon"], [sc])
            torch.cuda.reset_peak_memory_stats()
            t, n = time.time(), 0
            for i in range(0, len(jobs), batch):
                b = [j for j in jobs[i:i + batch] if not (d / f"{j[0]}__s{j[1]}.png").exists()]
                if not b:
                    continue
                with torch.no_grad():
                    cfg_kw = {"num_inference_steps": BASE_STEPS, "guidance_scale": 4.0,
                              "negative_prompt_embeds": NEG.repeat(len(b), 1, 1).to("cuda")} if base else \
                             {"num_inference_steps": STEPS, "guidance_scale": 1.0}
                    ims = pipe(prompt_embeds=E[[keys.index(k) for k, _ in b]].to("cuda"), height=SIZE, width=SIZE,
                               image=refs, generator=[torch.Generator("cpu").manual_seed(42 + s) for _, s in b],
                               **cfg_kw).images
                for (k, s), im in zip(b, ims):
                    im.save(d / f"{k}__s{s}.png")
                n += len(b)
            sec = (time.time() - t) / max(n, 1)
            peak = torch.cuda.max_memory_allocated() / 2**30
            (d / "gen.json").write_text(json.dumps({"set": which, "step": step, "scale": sc, "seconds_per_image": round(sec, 2),
                                                    "peak_gb": round(peak, 2), "made": n}), encoding="utf-8")
            print(f"[5.3] {tag}: {n} images, {sec:.2f} s each, peak {peak:.1f} GB", flush=True)


# ---------------------------------------------------------------- scoring (anaconda python: numpy, scipy, iconkit)
BORDER, FAR_PX = 8, 8


def readback(path):
    """generated 8-bit image over black -> D40 line art RGBA float (grey x3, alpha), max-RGB C, Lab chroma per pixel"""
    import numpy as np
    from PIL import Image
    from skimage.color import rgb2lab
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.float64) / 255
    C = rgb.max(2)
    a = np.minimum(1, C / K_ALPHA)
    g = np.where(a > 0, C / np.maximum(a, 1e-6), 0)
    chroma = np.hypot(*rgb2lab(rgb)[..., 1:].transpose(2, 0, 1))
    return np.dstack([g, g, g, a]), C, chroma


def haze(a):
    """mean alpha of pixels more than FAR_PX from any stroke (alpha > .5): VAE haze; 0 for clean line art"""
    import numpy as np
    from scipy import ndimage
    far = ndimage.distance_transform_edt(a <= .5) > FAR_PX
    return float(a[far].mean()) if far.any() else 0.0


def score_job(job):
    path, preset, th = job
    import numpy as np
    from iconkit import relations, variants as V
    la, C, chroma = readback(path)
    ring = np.ones(C.shape, bool)
    ring[BORDER:-BORDER, BORDER:-BORDER] = False
    r = {"path": str(path), "inverted": bool(np.median(C[ring]) > .5)}
    if r["inverted"]:
        return r, None
    drawn = la[..., 3] > .5
    r["chroma"] = round(float(np.median(chroma[drawn])), 2) if drawn.any() else 0.0
    r["haze"] = round(haze(la[..., 3]), 4)
    m = V.master(la, preset, th)
    placed, boxed, _, _ = relations.lines(m)
    return r, (placed, boxed)


def train_lines():
    """line maps (placed, boxed) of every training master, cached in data/score53_train_lines.npz"""
    import numpy as np
    from multiprocessing import Pool
    from iconkit import relations
    f = D / "score53_train_lines.npz"
    if f.exists():
        z = np.load(f)
        return list(z["names"]), z["placed"], z["boxed"]
    names = (D / "train.txt").read_text(encoding="utf-8").split()
    with Pool(6) as pool:
        L = dict(pool.map(relations.job, names, chunksize=20))
    placed, boxed = np.stack([L[n][0] for n in names]), np.stack([L[n][1] for n in names])
    np.savez_compressed(f, names=np.array(names), placed=placed, boxed=boxed)
    return names, placed, boxed


def jobs_for(files):
    """generated files -> score_job inputs: each colours with its hold-out icon's preset, else its kind's commonest"""
    from collections import Counter
    from iconkit import variants as V
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    PR = {p["name"]: p for p in G["presets"]}
    common = {kd: Counter(v["preset"] for v in J["icons"].values() if v["kind"] == kd and v["preset"]).most_common(1)[0][0]
              for kd in ("Spell", "Action", "Illithid")}
    out = []
    for f in files:
        key = f.name.split("__s")[0]
        cap = UNSEEN.get(key, "")
        kd = J["icons"][key]["kind"] if key in J["icons"] else "Spell" if "spell icon" in cap else "Action"
        pn = J["icons"].get(key, {}).get("preset") or common[kd]
        out.append((f, PR[pn], V.recipe(J, kd, pn)))
    return out


def score(out, only=()):
    import numpy as np
    from multiprocessing import Pool
    from iconkit import relations, trainset
    from iconkit.extract import log
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    R = json.loads((D / "relations.json").read_text(encoding="utf-8"))
    seen = set(R["seen_drawing"])
    tn, tp, tb = train_lines()
    log(f"[5.3] {len(tn)} training line maps")
    tags = list(only) or sorted(p.parent.name for p in Path(out).glob("*/gen.json"))
    f = Path(out, "score.json")
    res = json.loads(f.read_text(encoding="utf-8")) if only and f.exists() else {}   # TAGs given: merge into it
    with Pool(6) as pool:
        # the real hold-out line art, scored the same way (haze, chroma): what a perfect model would get
        hold = sorted(n for n in prompts("holdout") if J["icons"].get(n, {}).get("preset"))
        real = pool.map(trainset.image, hold, chunksize=4)
        rh = [haze(np.minimum(1, im[..., 0] / 255 / K_ALPHA)) for _, im in real]
        res["real"] = {"n": len(rh), "haze_median": round(float(np.median(rh)), 4)}
        for tag in tags:
            files = sorted(Path(out, tag).glob("*__s*.png"))
            out_ = pool.map(score_job, jobs_for(files), chunksize=4)
            rows = [r for r, _ in out_]
            ok = [(f, l) for f, (r, l) in zip(files, out_) if l is not None]
            if ok:
                Kp = relations.kappa(np.concatenate([np.stack([l[0] for _, l in ok]), tp]))[:len(ok), len(ok):]
                Kb = relations.kappa(np.concatenate([np.stack([l[1] for _, l in ok]), tb]))[:len(ok), len(ok):]
                K = np.maximum(Kp, Kb)
                for (f, _), k in zip(ok, K):
                    r = next(r for r in rows if r["path"] == str(f))
                    r["nearest"], r["kappa"] = tn[int(k.argmax())], round(float(k.max()), 3)
            fresh = [r for r in rows if "kappa" in r and Path(r["path"]).name.split("__s")[0] not in seen]
            kk = [r["kappa"] for r in fresh]
            g = json.loads(Path(out, tag, "gen.json").read_text(encoding="utf-8"))
            res[tag] = {"n": len(rows), "inverted": sum(r["inverted"] for r in rows),
                        "chroma_median": round(float(np.median([r["chroma"] for r in rows if "chroma" in r] or [0])), 2),
                        "haze_median": round(float(np.median([r["haze"] for r in rows if "haze" in r] or [0])), 4),
                        "kappa_p10_50_90": np.percentile(kk, [10, 50, 90]).round(2).tolist() if kk else None,
                        "copies_090": sum(k >= .9 for k in kk),
                        "seen_drawing": {Path(r["path"]).name: r.get("kappa") for r in rows
                                         if Path(r["path"]).name.split("__s")[0] in seen},
                        "seconds_per_image": g["seconds_per_image"], "peak_gb": g["peak_gb"], "rows": rows}
            s = res[tag]
            log(f"[5.3] {tag:>9}: {s['inverted']:3d} / {s['n']} inverted, chroma {s['chroma_median']:5.2f}, haze "
                f"{s['haze_median']:.4f} (real {res['real']['haze_median']:.4f}), nearest kappa p10/50/90 "
                f"{s['kappa_p10_50_90']} (D29 .36 / .50 / .84), >= .9: {s['copies_090']}, {s['seconds_per_image']} s, "
                f"{s['peak_gb']} GB")
    Path(out, "score.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    log(f"[5.3] -> {Path(out, 'score.json')}")


def steer(ref, others):
    """how much each caption part steers the drawing: every image in REF (full captions) and each OTHER dir (the same
    config on holdout_nodesc / _nomotif / _srd prompts, same seeds) -> kappa to the game's real drawing of that prompt
    (relations.kappa, max of placed / boxed), and each OTHER's kappa to REF's image of the same prompt and seed"""
    import numpy as np
    from multiprocessing import Pool
    from iconkit import relations
    from iconkit.extract import log
    k2 = lambda a, b: max(float(relations.kappa(np.stack([a[0], b[0]]))[0, 1]), float(relations.kappa(np.stack([a[1], b[1]]))[0, 1]))
    with Pool(6) as pool:
        H = dict(pool.map(relations.job, sorted(prompts("holdout")), chunksize=4))
        L = {}
        for d in [ref, *others]:
            files = sorted(Path(d).glob("*__s*.png"))
            L[d] = {f.name: l for f, (r, l) in zip(files, pool.map(score_job, jobs_for(files), chunksize=4)) if l is not None}
    res = {}
    for d in [ref, *others]:
        names = sorted(L[d])
        real = [k2(L[d][f], H[f.split("__s")[0]]) for f in names]
        res[d] = {"n": len(names), "to_real_median": round(float(np.median(real)), 3),
                  "to_real": {f: round(k, 3) for f, k in zip(names, real)}}
        if d != ref:
            both = [f for f in names if f in L[ref]]
            tf = [k2(L[d][f], L[ref][f]) for f in both]
            res[d]["to_full_median"] = round(float(np.median(tf)), 3)
            res[d]["to_full"] = {f: round(k, 3) for f, k in zip(both, tf)}
            res[d]["full_to_real_same_prompts"] = round(float(np.median([k2(L[ref][f], H[f.split("__s")[0]]) for f in both])), 3)
        log(f"[5.3] steer {d}: " + str({k: v for k, v in res[d].items() if not isinstance(v, dict)}))
    Path(ref).parent.joinpath("steer.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


def tell_stats(la):
    """line art RGBA float (512) -> what could give a drawing away: line cover, edge fringe (partial-alpha share of drawn
    pixels), stroke width (2 x median distance to the edge on the skeleton, px at 512), edge roughness (boundary pixels /
    2 x skeleton length: 1 = smooth strokes), grey p10 / p50 / p90 on opaque pixels, parts (>= 20 px), skeleton ends"""
    import numpy as np
    from scipy import ndimage
    from skimage.morphology import skeletonize
    a, g = la[..., 3], la[..., 0]
    m = a > .5
    if m.sum() < 50:
        return None
    sk = skeletonize(m)
    dist = ndimage.distance_transform_edt(m)
    edge = m & ~ndimage.binary_erosion(m)
    lab, n = ndimage.label(m)
    sizes = np.bincount(lab.ravel())[1:]
    nb = ndimage.convolve(sk.astype(int), np.ones((3, 3), int), mode="constant") - 1
    op = a > .9
    q = np.percentile(g[op], [10, 50, 90]) if op.sum() > 20 else [0, 0, 0]
    w, ends = dist[sk], sk & (nb == 1)
    # the user's blind test (21 of 24 told apart): brush strokes taper, outlines stay open, hand-drawn asymmetry
    near_end = ndimage.binary_dilation(ends, iterations=6) & sk
    hl, hn = ndimage.label(~m)
    holes = int((np.bincount(hl.ravel())[1:] >= 20).sum()) - 1          # enclosed background regions (minus the outside)
    return {"cover": float(m.mean()), "fringe": float(((a > .1) & (a < .9)).sum() / max((a > .1).sum(), 1)),
            "width": float(2 * np.median(w)), "rough": float(edge.sum() / max(2 * sk.sum(), 1)),
            "grey10": float(q[0]), "grey50": float(q[1]), "grey90": float(q[2]), "parts": int((sizes >= 20).sum()),
            "ends": int(ends.sum()), "width_cv": float(w.std() / max(w.mean(), 1e-6)),
            "taper": float(np.median(dist[near_end]) / max(np.median(w), 1e-6)) if near_end.any() else 1.0,
            "holes": max(holes, 0), "mirror": float((m & m[:, ::-1]).sum() / max((m | m[:, ::-1]).sum(), 1))}


def tell_job(job):
    kind, x = job
    if kind == "real":
        from iconkit import variants as V
        J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
        G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
        return x, tell_stats(V.build(x, J, G)[1])
    return x, tell_stats(readback(x)[0])


def tells(out, tags):
    """real hold-out line art (true lines) vs generated (seed 0, not inverted) per config: medians of tell_stats
    -> OUT/tells.json + table"""
    import numpy as np
    from multiprocessing import Pool
    from iconkit.extract import log
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    S = json.loads(Path(out, "score.json").read_text(encoding="utf-8"))
    hold = [k for k in sorted(prompts("holdout")) if J["icons"].get(k, {}).get("preset")]
    res = {}
    with Pool(6) as pool:
        rows = {"real": dict(pool.map(tell_job, [("real", k) for k in hold], chunksize=2))}
        for t in tags:
            inv = {Path(r["path"]).name for r in S[t]["rows"] if r["inverted"]}
            fs = [str(Path(out, t, f"{k}__s0.png")) for k in hold if f"{k}__s0.png" not in inv]
            rows[t] = dict(pool.map(tell_job, [("gen", f) for f in fs], chunksize=2))
    keys = ["cover", "fringe", "width", "rough", "grey50", "parts", "ends", "width_cv", "taper", "holes", "mirror"]
    log("[5.3] tells (medians): " + " ".join(f"{k:>7}" for k in keys))
    for t, R in rows.items():
        v = [r for r in R.values() if r]
        res[t] = {k: round(float(np.median([r[k] for r in v])), 3) for k in keys} | {"n": len(v)}
        log(f"[5.3] {t:>9} n={len(v):3d} " + " ".join(f"{res[t][k]:7.3f}" for k in keys))
    Path(out, "tells.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


def sheet(out, png, tags, n=16, tile=128):
    """rows = configs, columns = n hold-out / unseen prompts spread over the sorted keys (seed 0), each config's label"""
    from PIL import Image, ImageDraw
    keys = sorted({f.name.split("__s")[0] for f in Path(out, tags[0]).glob("*__s0.png")})
    m = min(n, len(keys))
    keys = [keys[round(i * (len(keys) - 1) / max(m - 1, 1))] for i in range(m)]
    W = 90
    im = Image.new("RGB", (W + len(keys) * tile, len(tags) * tile), (30, 30, 30))
    dr = ImageDraw.Draw(im)
    for r, t in enumerate(tags):
        dr.text((6, r * tile + tile // 2 - 6), t, fill=(220, 220, 220))
        for c, k in enumerate(keys):
            f = Path(out, t, f"{k}__s0.png")
            if f.exists():
                im.paste(Image.open(f).convert("RGB").resize((tile, tile), Image.LANCZOS), (W + c * tile, r * tile))
    im.save(png)
    print(f"[5.3] sheet {png}: {len(tags)} configs x {len(keys)} prompts: {', '.join(keys)}", flush=True)


def blind(out, tag, n=24, size=160, seed=None):
    """blind review (5.3): n hold-out icons, each as a pair in random order: the game's drawing (its true line art) and the
    generated one (seed 0, D40 read-back), both coloured by the same code (the icon's preset + glow recipe, over the
    hotbar dark), so only the drawing differs. -> OUT/blind_<tag>.png + OUT/blind_<tag>_key.json (which side is generated)"""
    import numpy as np
    from PIL import Image, ImageDraw
    from iconkit import variants as V
    from iconkit.grammar import DARK
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    J = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    PR = {p["name"]: p for p in G["presets"]}
    seen = set(json.loads((D / "relations.json").read_text(encoding="utf-8"))["seen_drawing"])
    rows = {Path(r["path"]).name: r for r in json.loads(Path(out, "score.json").read_text(encoding="utf-8"))[tag]["rows"]}
    used = {v["icon"] for f in Path(out).glob("blind_*_key.json") if f.name != f"blind_{tag}_key.json"
            for v in json.loads(f.read_text(encoding="utf-8")).values()}     # a real drawing seen before gives a pair away
    ok = [k for k in sorted(prompts("holdout")) if J["icons"].get(k, {}).get("preset") and k not in seen | used
          and not rows.get(f"{k}__s0.png", {"inverted": True})["inverted"]]
    rng = np.random.default_rng(seed)
    pick = sorted(rng.choice(ok, size=min(n, len(ok)), replace=False))
    over = lambda m: Image.fromarray(V.u8(m[..., :3] * m[..., 3:] + DARK * (1 - m[..., 3:])), "RGB").resize((size, size), Image.LANCZOS)
    cols, gap = 4, 12
    pw = 2 * size + gap
    im = Image.new("RGB", (cols * (pw + 2 * gap), -(-len(pick) // cols) * (size + 28)), (12, 12, 12))
    dr = ImageDraw.Draw(im)
    key = {}
    for i, k in enumerate(pick):
        kd, pn = J["icons"][k]["kind"], J["icons"][k]["preset"]
        real = V.build(k, J, G)[2]
        gen = V.master(readback(Path(out, tag, f"{k}__s0.png"))[0], PR[pn], V.recipe(J, kd, pn))
        g_right = bool(rng.integers(2))
        x0, y0 = (i % cols) * (pw + 2 * gap) + gap, (i // cols) * (size + 28)
        for j, m in enumerate((real, gen) if g_right else (gen, real)):
            im.paste(over(m), (x0 + j * (size + gap), y0 + 22))
        dr.text((x0, y0 + 4), f"{i + 1}  A | B", fill=(220, 220, 220))
        key[i + 1] = {"icon": k, "generated": "B" if g_right else "A"}
    im.save(Path(out, f"blind_{tag}.png"))
    Path(out, f"blind_{tag}_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"[5.3] blind grid {Path(out, f'blind_{tag}.png')} ({len(pick)} pairs), key beside it", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "gen":
        opt = {a[i]: int(a[i + 1]) for i in range(len(a)) if a[i].startswith("--")}
        pos = [x for i, x in enumerate(a) if not x.startswith("--") and not (i and a[i - 1].startswith("--"))]
        gen(pos[1], pos[2], pos[3:], seeds=opt.get("--seeds", 2), batch=opt.get("--batch", 2))
    elif a[0] == "score":
        score(a[1], a[2:])
    elif a[0] == "steer":
        steer(a[1], a[2:])
    elif a[0] == "tells":
        tells(a[1], a[2:])
    elif a[0] == "sheet":
        sheet(a[1], a[2], a[3:])
    elif a[0] == "blind":
        blind(a[1], a[2])
