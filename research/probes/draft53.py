"""5.3 draft test (D31 / D42): does the model keep the game's drawing when it gets a draft built from game parts?
Hold-out icons with a vanilla start (compose_census.how a-d): (a) D30 element series -> the series rebuilt for the icon's
element from its training members only (relations' symbol swap, done at 512: base + slot found at 128, x4), (b-d) the
closest training drawing among its frame family / series siblings / all training (d = a copy) -> the draft, as the
model's training images look (grey x alpha over black, 512). The start a user would pick by eye, so b-d take the
candidate closest to the real drawing. Then klein 4B distilled + LoRA v2 (12,000 x2, 4 steps, seeds 0 / 1) per config:
ref (draft as klein reference image, from noise), i2i50 / i2i75 (img2img on the draft: the inpaint pipeline with a full
mask, strength .5 / .75 = 2 / 3 of the 4 steps), ref_i2i75 (both); free = score53's text-only images (same seeds).
Score: kappa (relations, max of placed / boxed) of each image to the game's real drawing and to its draft; the draft's
own kappa to the real drawing is the bar; tells (score53.tell_stats) say whether the stroke became the house stroke.
    anaconda python research/probes/draft53.py drafts      -> outputs/draft53/draft/<icon>__s0.png + drafts.json (~3 min)
    .venv/Scripts/python.exe research/probes/draft53.py gen   (env ICON_RUN=klein4b_all_v2) -> outputs/draft53/<config>/
    anaconda python research/probes/draft53.py score       -> outputs/draft53/score.json + table
    anaconda python research/probes/draft53.py sheet OUT.png -> real | draft | free | configs, seed 0"""
import gc, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "probes"))
OUT = ROOT / "outputs" / "draft53"
FREE = ROOT / "outputs" / "score53_v2" / "12000x2"
CONFIGS = {"ref": (1.0, True), "i2i50": (.5, False), "i2i75": (.75, False), "ref_i2i75": (.75, True)}
STEP, SCALE, SEEDS = 12000, 2.0, 2
COLS = ["draft", "free", *CONFIGS]


def k2(a, b):
    import numpy as np
    from iconkit import relations
    return max(float(relations.kappa(np.stack([a[0], b[0]]))[0, 1]), float(relations.kappa(np.stack([a[1], b[1]]))[0, 1]))


def drafts():
    import numpy as np
    from PIL import Image
    from iconkit import relations as R, trainset
    from iconkit.extract import log
    import compose_census as CC
    import score53 as S
    tn, tp, tb = S.train_lines()
    TL = {n: (p, b) for n, p, b in zip(tn, tp, tb)}
    ts = {r["icon"] for r in json.loads((ROOT / "outputs/trainset_all/trainset.json").read_text(encoding="utf-8"))}
    CC.train &= ts                                    # the icons the LoRA saw (no-preset, Reapply, dark-line left out)
    tn = [n for n in tn if n in ts]
    fam_members = {}
    for n, f in CC.fam.items():
        fam_members.setdefault(f, []).append(n)
    T = R.symbol_templates()
    EL = R.element_series(sorted(CC.ser))
    (OUT / "draft").mkdir(parents=True, exist_ok=True)
    rows = {}
    for n in CC.hold:
        how = CC.how(n)
        if how.startswith("e"):
            continue
        real = R.lines(R.master(n))[:2]
        if how.startswith("a"):
            el = R.EL_RE.search(n)[1]
            ser = {e: m for e, m in EL[R.EL_RE.sub("*", n, 1)].items() if m != n and m in CC.train}
            slots = R.series_slots(ser, T)
            src = max(slots, key=lambda e: slots[e][0])
            base = np.kron(R.series_base(list(ser.values())), np.ones((4, 4))) > 0      # 128 -> 512, D30's tolerance
            g = trainset.image(ser[src])[1][..., 0] / 255
            sym = R.symbol_art(el, 512)
            v = sym["AL"] * sym["B"]                     # lines only, like a training image (B alone carries the glow)
            out = R.composite({"AL": g, "B": g, "a": g}, base, tuple(x * 4 for x in slots[src][2]), {"AL": sym["AL"], "B": v, "a": v})
            im, source = np.clip(out["B"], 0, 1), f"{ser[src]} + {el} symbol"
        else:
            cand = ([m for m in fam_members.get(CC.fam.get(n), []) if m in CC.train] if how.startswith("b") else
                    [m for m in CC.by_ser.get(CC.ser.get(n), []) if m != n and m in CC.train] if how.startswith("c") else tn)
            source = max(cand, key=lambda m: k2(real, TL[m]))
            im = trainset.image(source)[1][..., 0] / 255
        f = OUT / "draft" / f"{n}__s0.png"
        Image.fromarray((np.repeat(im[..., None], 3, 2) * 255 + .5).astype(np.uint8)).save(f)
        rows[n] = {"how": how, "source": source}
        log(f"[draft53] {how[:1]} {n}: {source}")
    (OUT / "drafts.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    log(f"[draft53] {len(rows)} drafts -> {OUT / 'draft'}")


def gen():
    """score53.gen's settings: transformer in fp8 storage, the LoRA loaded before the casting and left out of it"""
    import torch
    from diffusers import Flux2KleinInpaintPipeline, Flux2Transformer2DModel
    from PIL import Image
    import score53 as S
    P = S.prompts("holdout")
    keys = sorted(json.loads((OUT / "drafts.json").read_text(encoding="utf-8")))
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
    print(f"[draft53] {len(keys)} prompts, LoRA {S.lora_file(STEP).name} x{SCALE:g}, "
          f"{torch.cuda.memory_allocated() / 2**30:.1f} GB on the card", flush=True)
    mask = Image.new("L", (512, 512), 255)            # repaint everything: img2img
    for cfg, (strength, ref) in CONFIGS.items():
        d = OUT / cfg
        d.mkdir(exist_ok=True)
        t, n = time.time(), 0
        for i, k in enumerate(keys):
            draft = Image.open(OUT / "draft" / f"{k}__s0.png").convert("RGB")
            for s in range(SEEDS):
                f = d / f"{k}__s{s}.png"
                if f.exists():
                    continue
                with torch.no_grad():
                    pipe(prompt_embeds=E[i:i + 1].to("cuda"), image=draft, mask_image=mask,
                         image_reference=[draft] if ref else None, strength=strength, height=512, width=512,
                         num_inference_steps=4, guidance_scale=1.0,
                         generator=torch.Generator("cpu").manual_seed(42 + s)).images[0].save(f)
                n += 1
        print(f"[draft53] {cfg}: {n} images, {(time.time() - t) / max(n, 1):.2f} s each, peak "
              f"{torch.cuda.max_memory_allocated() / 2**30:.1f} GB", flush=True)


def score_icon(job):
    """one icon -> per column and seed: inverted, kappa to real / to draft; tells on seed 0"""
    n, preset_job = job
    from iconkit import relations as R, variants as V
    import score53 as S
    J = json.loads((ROOT / "data" / "glyph.json").read_text(encoding="utf-8"))
    G = json.loads((ROOT / "data" / "grammar.json").read_text(encoding="utf-8"))
    real = R.lines(R.master(n))[:2]
    res = {"real_tells": S.tell_stats(V.build(n, J, G)[1]) if J["icons"][n]["preset"] else None}   # no preset: no line art
    files = {c: [(FREE if c == "free" else OUT / c) / f"{n}__s{s}.png" for s in range(1 if c == "draft" else SEEDS)]
             for c in COLS}
    L = {}
    for c, fs in files.items():
        for f, j in zip(fs, S.jobs_for(fs)):
            r, l = S.score_job(j)
            L[(c, f.name)] = (r, l)
    draft = L[("draft", f"{n}__s0.png")][1]
    for (c, fn), (r, l) in L.items():
        row = {"inverted": r["inverted"]}
        if l is not None:
            row |= {"to_real": round(k2(l, real), 3), "to_draft": round(k2(l, draft), 3)}
        if fn.endswith("__s0.png") and not r["inverted"]:
            row["tells"] = S.tell_stats(S.readback((FREE if c == "free" else OUT / c) / fn)[0])
        res.setdefault(c, {})[fn] = row
    return n, res


def score():
    import numpy as np
    from multiprocessing import Pool
    from iconkit.extract import log
    D = json.loads((OUT / "drafts.json").read_text(encoding="utf-8"))
    with Pool(6) as pool:
        R = dict(pool.map(score_icon, [(n, None) for n in sorted(D)], chunksize=2))
    for n in R:
        R[n]["how"], R[n]["source"] = D[n]["how"], D[n]["source"]
    good = {n for n in R if R[n]["draft"][f"{n}__s0.png"].get("to_real", 0) >= .75}
    groups = {"all": set(R), "draft >= .75 to real": good, "draft < .75": set(R) - good,
              "a D30 rebuild": {n for n in R if R[n]["how"].startswith("a")}}
    TK = ["rough", "taper", "holes", "mirror", "width", "ends"]
    summary = {}
    for g, ns in groups.items():
        log(f"[draft53] {g}: {len(ns)} icons; medians over icons x seeds (inverted left out)")
        for c in COLS:
            rows = [v for n in ns for v in R[n][c].values()]
            ok = [v for v in rows if "to_real" in v]
            t = [v["tells"] for v in rows if v.get("tells")]
            s = {"n": len(rows), "inverted": sum(v["inverted"] for v in rows),
                 "to_real": round(float(np.median([v["to_real"] for v in ok])), 3) if ok else None,
                 "to_draft": round(float(np.median([v["to_draft"] for v in ok])), 3) if ok else None,
                 "tells": {k: round(float(np.median([x[k] for x in t])), 3) for k in TK} if t else None}
            summary.setdefault(g, {})[c] = s
            log(f"[draft53]   {c:>10}: n {s['n']:3d}, inverted {s['inverted']:2d}, to real {s['to_real']}, to draft "
                f"{s['to_draft']}, tells {s['tells']}")
        rt = [R[n]["real_tells"] for n in ns if R[n]["real_tells"]]
        log(f"[draft53]   {'real':>10}: tells " + str({k: round(float(np.median([x[k] for x in rt])), 3) for k in TK}))
    (OUT / "score.json").write_text(json.dumps({"summary": summary, "icons": R}, indent=1), encoding="utf-8")
    log(f"[draft53] -> {OUT / 'score.json'}")


def sheet(png, tile=150):
    """rows = icons (D30 rebuilds first, then by draft kappa to real), columns = real | draft | free | configs (seed 0)"""
    import numpy as np
    from PIL import Image, ImageDraw
    from iconkit import trainset
    S_ =json.loads((OUT / "score.json").read_text(encoding="utf-8"))["icons"]
    names = sorted(S_, key=lambda n: (not S_[n]["how"].startswith("a"), -S_[n]["draft"][f"{n}__s0.png"].get("to_real", 0)))
    W, H = 230, 18
    im = Image.new("RGB", (W + (len(COLS) + 1) * tile, H + len(names) * tile), (30, 30, 30))
    dr = ImageDraw.Draw(im)
    for c, t in enumerate(["real", *COLS]):
        dr.text((W + c * tile + 4, 3), t, fill=(220, 220, 220))
    for r, n in enumerate(names):
        y = H + r * tile
        dr.text((4, y + 4), f"{S_[n]['how'][:1]} {n[:34]}", fill=(220, 220, 220))
        dr.text((4, y + 20), f"from {S_[n]['source'][:32]}", fill=(150, 150, 150))
        for c, col in enumerate(COLS):
            v = S_[n][col].get(f"{n}__s0.png", {})
            dr.text((4, y + 40 + 14 * c), f"{col}: {v.get('to_real', 'inv')}", fill=(170, 170, 170))
        try:
            real = trainset.image(n)[1]
        except KeyError:                                  # no preset: the master's brightness over black instead
            from iconkit import relations as R
            real = (np.repeat(np.clip(R.line_art(R.master(n), 512)["B"], 0, 1)[..., None], 3, 2) * 255).astype(np.uint8)
        im.paste(Image.fromarray(real).resize((tile, tile), Image.LANCZOS), (W, y))
        for c, col in enumerate(COLS, 1):
            f = (FREE if col == "free" else OUT / col) / f"{n}__s0.png"
            im.paste(Image.open(f).convert("RGB").resize((tile, tile), Image.LANCZOS), (W + c * tile, y))
    im.save(png)
    print(f"[draft53] sheet {png}: {len(names)} icons", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    {"drafts": drafts, "gen": gen, "score": score}.get(a[0], lambda: sheet(a[1]))()
