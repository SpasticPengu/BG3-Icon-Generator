"""5.3 planner test (user idea 2026-10-17, D42 + D48 automated): a small language model (klein's own text encoder, the full
Qwen3-4B chat model) reads an icon's caption and writes a composition plan: named game parts with boxes, plus regions with
something new to draw. Code places the parts (exemplars cut from training icons only); the image model (klein 4B
distilled + LoRA v2 12,000 x2) draws the new regions two ways: "sprite" (each region's object generated alone, its lines
cropped and fitted into the box) and "inpaint" (one inpaint pass over the regions with the full caption, parts kept).
Catalogue = parts.FAMILIES (named house parts, EXCLUDE respected), the 11 damage-type symbols (D28), the D36 frame
families (base lines of their training members, as inpaint53). Boxes are [left, top, right, bottom] in % of the icon.
    anaconda python research/probes/planner53.py catalogue  -> outputs/planner53/catalogue/*.png + catalogue.json
    anaconda python research/probes/planner53.py fewshot    -> the example icons' measured layouts (to write EXAMPLES)
    .venv/Scripts/python.exe research/probes/planner53.py plan     -> plans.json (Qwen3-4B, greedy, JSON checked)
    .venv/Scripts/python.exe research/probes/planner53.py gen      (env ICON_RUN=klein4b_all_v2) -> sprite/, inpaint/
    anaconda python research/probes/planner53.py score | sheet OUT.png"""
import json, re, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "probes"))
OUT = ROOT / "outputs" / "planner53"
CAT = OUT / "catalogue"
FREE = ROOT / "outputs" / "score53_v2" / "12000x2"
STEP, SCALE, SEEDS = 12000, 2.0, 2
SKIP_FAMILIES = {"fire symbol", "snowflake", "acid bubbles", "necrotic skull", "thunder whirl", "lightning bolt",  # D28 has them
                 "Reapply ring", "Divine Strike rays",                                   # code-made (D35) / a D30 series
                 "portrait", "spell-slot star"}         # cut as hair alone / one point of the star: not usable alone
SINGLE = {"sparkle"}               # categories cut as the one part (its repeats are other copies of it)
FRAMES = {   # D36 frame family (links.json) -> catalogue name
    "name: Action_Legendary*": "legendary frame", "name: Action_Paladin_Aura*": "paladin aura frame",
    "series: Action_ArcaneArcher_BanishingArrow": "arcane shot frame", "flyout: Action_MantleOfMajesty": "mantle of majesty frame",
    "flyout: Action_DivineIntervention_Heal": "divine intervention frame", "name: Action_Mag_Command*": "command frame",
    "flyout: Spell_Abjuration_MagicCircle": "magic circle frame", "flyout: Spell_Transmutation_EnhanceAbility": "enhance ability frame",
    "flyout: Spell_Abjuration_ProtectionFromEnergy": "protection from energy shield", "flyout: Spell_Eyebite_Asleep": "eyebite frame",
    "flyout: Action_TransmuterStone_Speed": "transmuter's stone frame", "flyout: Spell_Necromancy_Contagion_Seizure": "contagion frame",
    "name: Action_Dragonborn*": "dragonborn breath frame", "flyout: Action_Paladin_LayOnHands_Cure": "lay on hands frame",
}
ELEMENTS = ("Acid", "Cold", "Fire", "Force", "Lightning", "Necrotic", "Physical", "Poison", "Psychic", "Radiant", "Thunder")


def ts_icons():
    return {r["icon"] for r in json.loads((ROOT / "outputs/trainset_all/trainset.json").read_text(encoding="utf-8"))}


def bbox(m):
    import numpy as np
    r, c = np.where(m)
    return int(r.min()), int(c.min()), int(r.max()) + 1, int(c.max()) + 1


def cut(icon, labels, L8=None):
    """an icon's strokes (8-connected labels) -> (grey crop uint8, box top, left, bottom, right at 512)"""
    import numpy as np
    from scipy import ndimage
    from iconkit import parts as PT, trainset
    if L8 is None:
        L8 = ndimage.label(PT.line_mask(icon), np.ones((3, 3)))[0]
    keep = np.isin(L8, list(labels))
    t, l, b, r = bbox(keep)
    g = trainset.image(icon)[1][..., 0]
    return np.where(ndimage.binary_dilation(keep, iterations=2), g, 0)[t:b, l:r].astype(np.uint8), (t, l, b, r)


def catalogue():
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    from iconkit import parts as PT, relations as R, trainset
    from iconkit.extract import log
    ts, hold = ts_icons(), set((ROOT / "data/holdout.txt").read_text().split())
    P = json.loads((ROOT / "data/parts.json").read_text(encoding="utf-8"))
    CAT.mkdir(parents=True, exist_ok=True)
    entries, L8s = {}, {}
    pct = lambda box: [round(100 * v / 512, 1) for v in (box[1], box[0], box[3], box[2])]       # -> left, top, right, bottom %
    for g in P["groups"]:
        fam = PT.NAMES.get(g["key"])
        if not fam or fam in SKIP_FAMILIES:
            continue
        cat_, what = PT.FAMILIES[fam]
        e = entries.setdefault(fam, {"name": fam, "category": cat_, "what": what, "files": [], "boxes": []})
        for m in g["members"]:
            icon, lab, top, left, h, w, k, flip, B, A = m
            if icon not in ts or icon in hold or icon in PT.EXCLUDE.get(fam, ()):
                continue
            if icon not in L8s:
                lm = PT.line_mask(icon)
                L8s[icon] = ndimage.label(lm)[0], ndimage.label(lm, np.ones((3, 3)))[0]
            L4, L8 = L8s[icon]
            # objects: the part's own strokes. B (exact repeats) pulled in whatever a series always draws beside them
            # (the skull beside the pointing hand, Divine Smite's rays round the broadsword, the axe in the gripping
            # fist). Figures: whole shape (B + A), their part alone is often just the head
            own = set(np.unique(L8[L4 == lab]).tolist()) - {0}
            labels = own | set(B) | set(A) if cat_ == "figure" else own
            crop, box = cut(icon, labels, L8)
            e["boxes"].append(pct(box))
            loose = cat_ != "figure" and crop.size > 2.5 * h * w                   # far more than the part's box
            if not loose and min(crop.shape) >= 12 and len(e.setdefault("_cand", [])) < 4:
                e["_cand"].append(crop)
    for fam, e in entries.items():          # exemplars: the 2 largest of the first 4 (a fragment is the smaller cut)
        for i, crop in enumerate(sorted(e.pop("_cand", []), key=lambda c: -c.size)[:2]):
            f = CAT / f"{re.sub(r'[^a-z0-9]+', '_', fam.lower())}_{i}.png"
            Image.fromarray(crop).save(f)
            e["files"].append(f.name)
    for el in ELEMENTS:                                                               # D28 symbols: the game's own design
        s = R.symbol_art(el, 512)
        v = np.clip(s["AL"] * s["B"], 0, 1)
        f = CAT / f"{el.lower()}_symbol_0.png"
        Image.fromarray((v * 255 + .5).astype(np.uint8)).save(f)
        entries[f"{el.lower()} symbol"] = {"name": f"{el.lower()} symbol", "category": "symbol",
                                           "what": f"the game's {el} damage-type symbol (D28)", "files": [f.name], "boxes": []}
    L = json.loads((ROOT / "data/links.json").read_text(encoding="utf-8"))
    for fr in L["frames"]:
        name = FRAMES.get(fr["family"])
        mem = [n for n in fr["icons"] if n in ts and n not in hold]
        if not name or len(mem) < 2:
            continue
        base = np.kron(R.series_base(mem), np.ones((4, 4), bool))
        g = trainset.image(mem[0])[1][..., 0]
        im = np.where(ndimage.binary_dilation(base, iterations=2), g, 0).astype(np.uint8)
        lab, k = ndimage.label(im > 64)
        im[np.isin(lab, 1 + np.flatnonzero(np.bincount(lab.ravel())[1:] < 200))] = 0      # chance dots (inpaint53)
        if (im > 64).sum() < 500:
            continue
        box = bbox(im > 64)
        f = CAT / f"{re.sub(r'[^a-z0-9]+', '_', name)}_0.png"
        Image.fromarray(im[box[0]:box[2], box[1]:box[3]]).save(f)
        entries[name] = {"name": name, "category": "frame", "what": f"the frame the game's {', '.join(mem[:3])} share (D36)",
                         "files": [f.name], "boxes": [pct(box)], "members": mem}
    for e in entries.values():                                       # usual size and place, for the planner's list
        if e["boxes"]:
            b = np.array(e["boxes"])
            e["size"] = round(float(np.median(np.maximum(b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]))))
            e["n"] = len(b)
    entries = {k: v for k, v in entries.items() if v["files"]}
    (OUT / "catalogue.json").write_text(json.dumps(entries, indent=1), encoding="utf-8")
    log(f"[planner53] catalogue: {len(entries)} entries -> {CAT}")
    for e in entries.values():
        log(f"[planner53]   {e['category']:>7} {e['name']}: {len(e['files'])} exemplar(s), usual size {e.get('size', '-')}%, n {e.get('n', '-')}")


FEWSHOT = ("Action_PactOfTheBlade_Maul", "Action_TurnTheTide", "Spell_Abjuration_BladeWard", "Action_Paladin_DivineSmite_Critical",
           "Action_HaloOfSpores", "Action_AbsolutePower", "Spell_Evocation_ChromaticOrb_Acid")


def fewshot():
    """the example icons' named parts (family, box %) and the box of the lines no named part covers -> stdout, a sheet"""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    from iconkit import parts as PT, trainset
    P = json.loads((ROOT / "data/parts.json").read_text(encoding="utf-8"))
    G = {g["id"]: g for g in P["groups"]}
    caps = {json.loads(l)["icon"]: json.loads(l)["caption"] for l in (ROOT / "data/captions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    pct = lambda t, l, b, r: [round(100 * v / 512) for v in (l, t, r, b)]
    for n in FEWSHOT:
        m = PT.line_mask(n)
        L4, L8 = ndimage.label(m)[0], ndimage.label(m, np.ones((3, 3)))[0]
        used = np.zeros_like(m)
        print(f"{n}: {caps[n]}")
        for gid in P["icons"][n]["groups"]:
            fam = PT.NAMES.get(G[gid]["key"])
            if not fam or n in PT.EXCLUDE.get(fam, ()):
                continue
            for mem in (x for x in G[gid]["members"] if x[0] == n):
                own = np.isin(L8, list(set(np.unique(L8[L4 == mem[1]]).tolist()) - {0}))
                used |= own
                print(f"    part {fam}: {pct(*bbox(own))}")
        rest = m & ~ndimage.binary_dilation(used, iterations=3)
        if rest.sum() > 300:
            print(f"    rest ({rest.sum() / m.sum():.2f} of the lines): {pct(*bbox(rest))}")
    ims = [Image.fromarray(trainset.image(n)[1]).resize((200, 200)) for n in FEWSHOT]
    sheet = Image.new("RGB", (200 * len(ims), 200))
    for i, im in enumerate(ims):
        sheet.paste(im, (200 * i, 0))
    sheet.save(OUT / "fewshot.png")


BAD_EXEMPLARS = {"frontal_figure_0.png", "star_figure_0.png"}   # by eye: Ki Resonation's wings + burst; Revivify's cross
EXAMPLES = [   # FEWSHOT icons, boxes measured by fewshot() (parts) and read off the icon (draw); captions from captions.jsonl
    ("Action_PactOfTheBlade_Maul",
     {"parts": [{"part": "gripping fist", "box": [38, 58, 80, 96]}, {"part": "four-point sparkle", "box": [70, 8, 82, 20]},
                {"part": "four-point sparkle", "box": [72, 46, 86, 60]}, {"part": "four-point sparkle", "box": [4, 56, 16, 68]}],
      "draw": [{"draw": "a maul head with a square end and a curved spike, on an upright handle", "box": [10, 4, 70, 62]}]}),
    ("Action_TurnTheTide",
     {"parts": [{"part": "healing cross", "box": [25, 4, 86, 69]}],
      "draw": [{"draw": "a figure reaching up with one arm", "box": [14, 30, 56, 98]},
               {"draw": "short straight rays spreading outwards", "box": [3, 3, 98, 96]}]}),
    ("Spell_Abjuration_BladeWard",
     {"parts": [{"part": "orb ring", "box": [9, 8, 88, 87]}, {"part": "open hand", "box": [26, 15, 68, 95]}], "draw": []}),
    ("Action_Paladin_DivineSmite_Critical",
     {"parts": [{"part": "broadsword", "box": [26, 18, 84, 89]}, {"part": "skull", "box": [9, 65, 35, 98]}],
      "draw": [{"draw": "a dense burst of sharp straight rays", "box": [1, 2, 97, 99]}]}),
    ("Action_HaloOfSpores",
     {"parts": [{"part": "ally bust", "box": [28, 40, 72, 98]}, {"part": "spiky spore", "box": [38, 2, 62, 26]},
                {"part": "spiky spore", "box": [14, 22, 34, 42]}, {"part": "spiky spore", "box": [66, 22, 86, 42]},
                {"part": "spiky spore", "box": [20, 48, 34, 62]}, {"part": "spiky spore", "box": [66, 48, 80, 62]}], "draw": []}),
    ("Action_AbsolutePower",
     {"parts": [], "draw": [{"draw": "an upright ornate hammer with a square patterned head", "box": [22, 10, 78, 98]},
                            {"draw": "straight rays radiating all around", "box": [1, 1, 99, 99]}]}),
    ("Spell_Evocation_ChromaticOrb_Acid",
     {"parts": [{"part": "orb ring", "box": [12, 12, 90, 91]}, {"part": "acid symbol", "box": [26, 22, 76, 76]}], "draw": []}),
]
SYSTEM = """You lay out Baldur's Gate 3 spell and action icons. An icon is white line art on black, 100 x 100 units.
You get the icon's caption (kind, class, intent, damage, then what the icon shows). Reply with JSON only:
{"parts": [...], "draw": [...]}
"parts": drawings from the game's PART LIST, placed exactly as they are: {"part": NAME, "box": [left, top, right, bottom]},
add "flip": true to mirror it left-right. Use a part only when the caption shows that thing (a figure, a hand, a skull, a
sword, a ring, a frame, a damage symbol...). A damage symbol only when the caption names that element's symbol or flame.
"draw": everything else the caption shows that no part covers, one object per entry, in a few plain words:
{"draw": WHAT, "box": [left, top, right, bottom]}. Effects (rays, swirls, speed strokes) are their own entries.
Boxes may overlap. Lay it out like the game: the main object large (60-95 units), small extras (sparkles, small skulls)
10-25 units, the caption's directions and places respected (at the left, pointing up-right, symmetric...).
PART LIST (name: what it is, usual size in units):
"""


def load_catalogue():
    C = json.loads((OUT / "catalogue.json").read_text(encoding="utf-8"))
    for e in C.values():
        e["files"] = [f for f in e["files"] if f not in BAD_EXEMPLARS]
    return {k: v for k, v in C.items() if v["files"]}


def part_list(C):
    clean = lambda s: re.sub(r"\s*\(D\d+\)", "", s).replace("damage-type", "damage")
    return "\n".join(f"- {n}: {clean(e['what'])}" + (f" ({e['size']})" if e.get("size") else "") for n, e in C.items())


def captions():
    return {json.loads(l)["icon"]: json.loads(l) for l in (ROOT / "data/captions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}


def check_plan(text, C):
    """model reply -> (plan, problems): the first {...} block, known part names only, boxes clipped to 0-100 and ordered"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None, ["no JSON"]
    try:
        p = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return None, [f"JSON: {e}"]
    low, out, bad = {k.lower(): k for k in C}, {"parts": [], "draw": []}, []
    def box(b):
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b)):
            return None
        l, t, r, b_ = (min(max(float(v), 0), 100) for v in b)
        return [min(l, r), min(t, b_), max(l, r), max(t, b_)] if abs(r - l) >= 3 and abs(b_ - t) >= 3 else None
    for x in p.get("parts", []) or []:
        name, b = low.get(str(x.get("part", "")).lower()), box(x.get("box"))
        if name and b:
            out["parts"].append({"part": name, "box": b, "flip": bool(x.get("flip", False))})
        else:
            bad.append(f"part {x}")
    for x in p.get("draw", []) or []:
        b = box(x.get("box"))
        if str(x.get("draw", "")).strip() and b:
            out["draw"].append({"draw": str(x["draw"]).strip(), "box": b})
        else:
            bad.append(f"draw {x}")
    return (out if out["parts"] or out["draw"] else None), bad


def plan():
    """Qwen3-4B (models/qwen3-4b = klein's text encoder, the full chat model), weights stored fp8 / computed bf16 so it fits
    beside the desktop on the 10 GB card, greedy; a reply that fails check_plan is retried twice with sampling"""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from diffusers.hooks import apply_layerwise_casting
    C, caps = load_catalogue(), captions()
    hold = (ROOT / "data/holdout.txt").read_text().split()
    M = ROOT / "models" / "qwen3-4b"
    tok = AutoTokenizer.from_pretrained(M)
    llm = AutoModelForCausalLM.from_pretrained(M, torch_dtype=torch.bfloat16)
    apply_layerwise_casting(llm, storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                            skip_modules_pattern=("embed_tokens", "norm", "lm_head", "rotary"))
    llm.to("cuda").eval()
    print(f"[planner53] Qwen3-4B on the card: {torch.cuda.memory_allocated() / 2**30:.1f} GB; {len(C)} catalogue entries", flush=True)
    msgs = [{"role": "system", "content": SYSTEM + part_list(C)}]
    for n, p in EXAMPLES:
        msgs += [{"role": "user", "content": f"Caption: {caps[n]['caption']}"}, {"role": "assistant", "content": json.dumps(p)}]
    f = OUT / "plans.json"
    plans = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    for i, n in enumerate(hold):
        if n in plans:
            continue
        ids = tok.apply_chat_template(msgs + [{"role": "user", "content": f"Caption: {caps[n]['caption']}"}],
                                      add_generation_prompt=True, enable_thinking=False, return_tensors="pt",
                                      return_dict=True)["input_ids"].to("cuda")
        t, p, tries = time.time(), None, []
        for k in range(3):
            g = torch.Generator("cuda").manual_seed(k)
            with torch.no_grad():
                o = llm.generate(ids, max_new_tokens=500, do_sample=k > 0, temperature=.7, top_p=.9,
                                 pad_token_id=tok.eos_token_id)
            text = tok.decode(o[0, ids.shape[1]:], skip_special_tokens=True)
            p, bad = check_plan(text, C)
            tries.append({"text": text, "problems": bad})
            if p:
                break
        plans[n] = {"plan": p, "tries": tries, "seconds": round(time.time() - t, 1), "prompt_tokens": int(ids.shape[1])}
        print(f"[planner53] {i + 1}/{len(hold)} {n}: {len(p['parts']) if p else '-'} parts, {len(p['draw']) if p else '-'} draw, "
              f"{len(tries)} tries, {time.time() - t:.0f} s", flush=True)
        f.write_text(json.dumps(plans, indent=1), encoding="utf-8")


FIG = r"figure|humanoid|person|man|woman|body|silhouette|warrior|monk|knight"
GUARD = {   # catalogue entry (or category) -> what the motif must say for the part to stay (the 4B planner put a
    # "frontal figure" on a howling wolf's arm and on a kicking boot)
    "figure": FIG, "hooded figure": r"hood", "skull": r"skull", "skull in profile": r"skull|skeleton",
    "open hand": r"hand|palm", "pointing hand": r"hand|finger|point", "beckoning hand": r"hand|finger|beckon",
    "gripping fist": r"fist|gripping|hand", "slim sword": r"sword|blade", "broadsword": r"sword|blade",
    "arrowhead": r"arrow", "orb ring": r"ring|orb|circle", "shield": r"shield", "healing cross": r"cross",
    "heart": r"heart", "drop": r"drop|blood", "spiral": r"spiral", "hourglass": r"hourglass",
    "sparkle": r"sparkle|star|glint|twinkle", "spiky spore": r"spore|sun", "burst star": r"star|burst",
    "frame": r"frame|ring|octagon|border|bracket|circle|shield",
    "acid symbol": r"acid", "cold symbol": r"cold|frost|ice|snowflake", "fire symbol": r"fire|flame",
    "force symbol": r"force", "lightning symbol": r"lightning|bolt", "necrotic symbol": r"necrotic|dripping skull",
    "physical symbol": r"physical|claw marks|slash", "poison symbol": r"poison|crossbones",
    "psychic symbol": r"psychic|eye", "radiant symbol": r"radiant|holy|sun", "thunder symbol": r"thunder|sound",
}


def guarded(p, C, motif):
    """drop the parts whose thing the motif never names (GUARD, by entry name, else its category) -> (plan, dropped)"""
    keep, drop = [], []
    for x in p["parts"]:
        rx = GUARD.get(x["part"]) or GUARD.get(C[x["part"]]["category"])
        (keep if rx is None or re.search(rf"\b({rx})", motif.lower()) else drop).append(x)
    return {"parts": keep, "draw": p["draw"]}, drop


def place(canvas, crop, box, flip=False):
    """paste a grey crop (uint8) into a box (% of 512), aspect kept, centred, union by max"""
    import numpy as np
    from PIL import Image
    l, t, r, b = (round(v * 5.12) for v in box)
    h, w = crop.shape
    s = min((r - l) / w, (b - t) / h)
    nw, nh = max(round(w * s), 1), max(round(h * s), 1)
    im = np.asarray(Image.fromarray(crop[:, ::-1] if flip else crop).resize((nw, nh), Image.LANCZOS))
    y, x = t + (b - t - nh) // 2, l + (r - l - nw) // 2
    canvas[y:y + nh, x:x + nw] = np.maximum(canvas[y:y + nh, x:x + nw], im[:max(0, 512 - y), :max(0, 512 - x)])


def parts_canvas(p, C):
    import numpy as np
    from PIL import Image
    cv = np.zeros((512, 512), np.uint8)
    for x in p["parts"]:
        place(cv, np.asarray(Image.open(CAT / C[x["part"]]["files"][0]).convert("L")), x["box"], x["flip"])
    return cv


def gen():
    """per hold-out plan: parts placed by code; then "sprite" (each draw entry generated alone: the caption's tags + the
    entry, its lines cropped and fitted into the box) and "inpaint" (the draw boxes, less the parts, repainted with the full
    caption, parts back on top). One klein inpaint pipeline does both (a full mask from noise = text to image)."""
    import gc
    import numpy as np
    import torch
    from diffusers import Flux2KleinInpaintPipeline, Flux2Transformer2DModel
    from PIL import Image
    from scipy import ndimage
    import score53 as S
    C, caps = load_catalogue(), captions()
    plans = {n: guarded(v["plan"], C, caps[n]["motif"])[0]
             for n, v in json.loads((OUT / "plans.json").read_text(encoding="utf-8")).items() if v["plan"]}
    plans = {n: p for n, p in plans.items() if p["parts"] or p["draw"]}
    keys = sorted(plans)
    tags = {n: caps[n]["caption"][:caps[n]["caption"].index(caps[n]["motif"].strip().rstrip("."))].rstrip(", ") for n in keys}
    texts = sorted({caps[n]["caption"] for n in keys} | {f"{tags[n]}, {d['draw']}." for n in keys for d in plans[n]["draw"]})
    M = ROOT / "models" / "FLUX.2-klein-4B"
    pipe = Flux2KleinInpaintPipeline.from_pretrained(M, dtype=torch.bfloat16)
    pipe.text_encoder.to("cuda")
    with torch.no_grad():
        E = dict(zip(texts, torch.cat([pipe.encode_prompt(texts[i:i + 8], device="cuda")[0].cpu() for i in range(0, len(texts), 8)])))
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
    print(f"[planner53] {len(keys)} plans, {len(texts)} prompts encoded", flush=True)
    full, black = Image.new("L", (512, 512), 255), Image.new("RGB", (512, 512))
    run = lambda text, image, mask, s: pipe(prompt_embeds=E[text][None].to("cuda"), image=image, mask_image=mask,
                                            strength=1.0, height=512, width=512, num_inference_steps=4, guidance_scale=1.0,
                                            generator=torch.Generator("cpu").manual_seed(42 + s)).images[0]
    for d in ("parts", "sprite", "sprite_raw", "inpaint"):
        (OUT / d).mkdir(exist_ok=True)
    t, n_s, n_i, inv = time.time(), 0, 0, 0
    for k in keys:
        p = plans[k]
        pc = parts_canvas(p, C)
        Image.fromarray(np.repeat(pc[..., None], 3, 2)).save(OUT / "parts" / f"{k}__s0.png")
        for s in range(SEEDS):
            f = OUT / "sprite" / f"{k}__s{s}.png"
            if not f.exists():
                cv = pc.copy()
                for j, d in enumerate(p["draw"]):
                    with torch.no_grad():
                        im = run(f"{tags[k]}, {d['draw']}.", black, full, s)
                    im.save(OUT / "sprite_raw" / f"{k}__d{j}__s{s}.png")
                    g = np.asarray(im.convert("RGB")).max(2)
                    ring = np.ones_like(g, bool)
                    ring[8:-8, 8:-8] = False
                    if np.median(g[ring]) > 127:                       # inverted (black on white): leave it out
                        inv += 1
                        continue
                    m = g > 64
                    if m.sum() < 50:
                        continue
                    r0, c0, r1, c1 = bbox(m)
                    place(cv, g[r0:r1, c0:c1], d["box"])
                    n_s += 1
                Image.fromarray(np.repeat(cv[..., None], 3, 2)).save(f)
            f = OUT / "inpaint" / f"{k}__s{s}.png"
            if not f.exists():
                if p["draw"]:
                    m = np.zeros((512, 512), bool)
                    for d in p["draw"]:
                        l, t_, r, b = (round(v * 5.12) for v in d["box"])
                        m[t_:b, l:r] = True
                    m &= ~ndimage.binary_dilation(pc > 64, iterations=6)
                    im = run(caps[k]["caption"], Image.fromarray(np.repeat(pc[..., None], 3, 2)),
                             Image.fromarray((m * 255).astype(np.uint8)), s)
                    out = np.maximum(np.asarray(im.convert("RGB")), pc[..., None])
                    n_i += 1
                else:
                    out = np.repeat(pc[..., None], 3, 2)
                Image.fromarray(out.astype(np.uint8)).save(f)
    print(f"[planner53] {n_s} sprites ({inv} inverted, left out), {n_i} inpaints in {time.time() - t:.0f} s, peak "
          f"{torch.cuda.max_memory_allocated() / 2**30:.1f} GB", flush=True)


COLS = ["parts", "sprite", "inpaint", "free"]


def score_icon(n):
    from iconkit import relations as R
    import score53 as S
    from draft53 import k2
    real = R.lines(R.master(n))[:2]
    res = {}
    for c in COLS:
        d = FREE if c == "free" else OUT / c
        fs = [d / f"{n}__s{s}.png" for s in range(1 if c == "parts" else SEEDS)]
        for f, j in zip(fs, S.jobs_for(fs)):
            r, l = S.score_job(j)
            row = {"inverted": r["inverted"]}
            if l is not None:
                row["to_real"] = round(k2(l, real), 3)
                if f.name.endswith("__s0.png") and not r["inverted"]:
                    row["tells"] = S.tell_stats(S.readback(f)[0])
            res.setdefault(c, {})[f.name] = row
    return n, res


def score():
    import numpy as np
    from multiprocessing import Pool
    from iconkit.extract import log
    import compose_census as CC
    plans = json.loads((OUT / "plans.json").read_text(encoding="utf-8"))
    C, caps = load_catalogue(), captions()
    Gd = {n: guarded(v["plan"], C, caps[n]["motif"]) for n, v in plans.items() if v["plan"]}
    names = sorted(n for n, (p, _) in Gd.items() if p["parts"] or p["draw"])
    with Pool(6) as pool:
        R_ = dict(pool.map(score_icon, names, chunksize=1))
    for n in R_:
        R_[n]["how"] = CC.how(n)
        R_[n]["plan"], R_[n]["dropped"] = Gd[n][0], [x["part"] for x in Gd[n][1]]
    raw = sum(len(v["plan"]["parts"]) for v in plans.values() if v["plan"])
    drop = [d for n in R_ for d in R_[n]["dropped"]]
    log(f"[planner53] guard: {len(drop)} of {raw} planned parts dropped (motif never names them): "
        + ", ".join(f"{k} {v}" for k, v in sorted(Counter(drop).items(), key=lambda kv: -kv[1])))
    plans = {n: {**plans[n], "plan": Gd[n][0]} for n in names}
    groups = {"all": set(R_)} | {f"{h}": {n for n in R_ if R_[n]["how"].startswith(h[0])} for h in
                                  ("a element series", "b frame family", "c series sibling", "d copy", "e nothing to start from")}
    TK = ["rough", "taper", "holes", "mirror", "parts", "ends"]
    summary = {}
    failed = sorted(set(caps) & set((ROOT / "data/holdout.txt").read_text().split()) - set(names))
    log(f"[planner53] {len(names)} plans scored, {len(failed)} without a valid plan: {failed}")
    log(f"[planner53] plans: parts per icon median {np.median([len(plans[n]['plan']['parts']) for n in names]):.0f}, draw "
        f"{np.median([len(plans[n]['plan']['draw']) for n in names]):.0f}; no part {sum(not plans[n]['plan']['parts'] for n in names)}, "
        f"no draw {sum(not plans[n]['plan']['draw'] for n in names)}; {np.median([plans[n]['seconds'] for n in names]):.0f} s per plan")
    for g, ns in groups.items():
        if not ns:
            continue
        log(f"[planner53] {g}: {len(ns)} icons; kappa to the game's drawing, medians over icons x seeds")
        for c in COLS:
            rows = [v for n in ns for v in R_[n][c].values()]
            ok = [v["to_real"] for v in rows if "to_real" in v]
            t = [v["tells"] for v in rows if v.get("tells")]
            s = {"n": len(rows), "inverted": sum(v["inverted"] for v in rows), "to_real": round(float(np.median(ok)), 3) if ok else None,
                 "tells": {k: round(float(np.median([x[k] for x in t])), 3) for k in TK} if t else None}
            summary.setdefault(g, {})[c] = s
            log(f"[planner53]   {c:>8}: n {s['n']:3d}, inverted {s['inverted']}, to real {s['to_real']}, tells {s['tells']}")
    (OUT / "score.json").write_text(json.dumps({"summary": summary, "icons": R_}, indent=1), encoding="utf-8")


def sheet(png, tile=128, only=None):
    """rows = icons, columns = real | plan (parts + draw boxes) | sprite | inpaint | free (seed 0); the plan text beside"""
    import numpy as np
    from PIL import Image, ImageDraw
    from iconkit import relations as R, trainset
    S_ = json.loads((OUT / "score.json").read_text(encoding="utf-8"))["icons"]
    names = [n for n in sorted(S_, key=lambda n: (S_[n]["how"], n)) if not only or n in only]
    W, H = 300, 18
    im = Image.new("RGB", (W + 5 * tile, H + len(names) * tile), (30, 30, 30))
    dr = ImageDraw.Draw(im)
    for c, t in enumerate(["real", "plan", "sprite", "inpaint", "free"]):
        dr.text((W + c * tile + 4, 3), t, fill=(220, 220, 220))
    for r, n in enumerate(names):
        y, p = H + r * tile, S_[n]["plan"]
        dr.text((4, y + 2), f"{S_[n]['how'][:1]} {n[:44]}", fill=(220, 220, 220))
        lines = [f"part {x['part']}" for x in p["parts"]] + [f"draw {x['draw'][:40]}" for x in p["draw"]]
        for i, s in enumerate(lines[:6]):
            dr.text((4, y + 16 + 12 * i), s, fill=(150, 150, 150))
        dr.text((4, y + 16 + 12 * 6), " / ".join(f"{c} {S_[n][c].get(n + '__s0.png', {}).get('to_real', 'inv')}"
                                                 for c in ("sprite", "inpaint", "free")), fill=(170, 170, 170))
        try:
            real = trainset.image(n)[1]
        except KeyError:
            real = (np.repeat(np.clip(R.line_art(R.master(n), 512)["B"], 0, 1)[..., None], 3, 2) * 255).astype(np.uint8)
        pl = Image.open(OUT / "parts" / f"{n}__s0.png").convert("RGB")
        d2 = ImageDraw.Draw(pl)
        for x in p["draw"]:
            d2.rectangle([v * 5.12 for v in x["box"]], outline=(80, 140, 255), width=4)
        for c, t in enumerate([Image.fromarray(real), pl] + [Image.open((FREE if c == "free" else OUT / c) / f"{n}__s0.png").convert("RGB")
                                                            for c in ("sprite", "inpaint", "free")]):
            im.paste(t.resize((tile, tile), Image.LANCZOS), (W + c * tile, y))
    im.save(png)
    print(f"[planner53] sheet {png}: {len(names)} icons", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    globals()[a[0]](*a[1:])
