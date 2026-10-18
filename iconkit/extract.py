"""Phase 1 dataset. Run with the anaconda python from the repo root:
    python -m iconkit.extract meta | masters | srd | tags | holdout | sheet | all | fadefit
(fadefit = diagnostic, not in `all`: re-measures the vanilla fade vs iconkit/fade.py)
(meta rewrites meta.jsonl: re-run srd/tags/holdout after it; srd needs data/srd/5e-SRD-Spells.json)
Writes into data/ (gitignored). Each step logs its milestones and counts."""
import re, sys, json, html, random, colorsys
from collections import Counter, defaultdict
import numpy as np
from PIL import Image, ImageDraw
from . import paths as P
from .fade import bottom_fade

D = P.DATA
SPELL_LIKE = ("Spell", "Action", "Skill", "TadpoleSuperPower")   # v1 families (D12; illithid powers D23)
EXCLUDED = ("Surface", "statIcons")
ILLITHID_ART = ("Action_Mag_Illithid_MindTax",)   # outside the TadpoleSuperPower family but drawn as an illithid power
# two colours by stroke (D26): exactly what glyph.colour_split finds (glyph.run warns if that changes)
TWO_TONE = tuple(f"Skill_Sorcerer_Passive_Metamagic_{s}Spell" for s in
                 ("Careful", "Distant", "Empowered", "Extended", "Heightened", "Quickened", "Subtle", "Twinned"))
BADGE_IOU = .3                                    # a numbered icon is a badge copy only if it shares its base's art
DAMAGE_TYPES = {"Acid", "Bludgeoning", "Cold", "Fire", "Force", "Lightning", "Necrotic", "Piercing", "Poison",
                "Psychic", "Radiant", "Slashing", "Thunder", "Weapon"}
FIELDS = ("VerbalIntent", "DamageType", "SpellSchool", "SpellType", "Level", "SpellFlags", "UseCosts")


def log(*a):
    print(*a, flush=True)


def read_jsonl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(p, rows):
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


# ---------------------------------------------------------------- 1.1 meta
def parse_stats():
    raw = {}
    for d in P.STAT_DIRS:
        for f in sorted(d.glob("*.txt")):
            cur = None
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if m := re.match(r'new entry "([^"]+)"', line):
                    # a later dir redefines with `using "<itself>"`: fields merge onto the earlier entry
                    name = m.group(1)
                    cur = raw.setdefault(name, {"type": "?", "using": None, "data": {}})
                elif cur is None:
                    continue
                elif m := re.match(r'type "([^"]+)"', line):
                    cur["type"] = m.group(1)
                elif m := re.match(r'using "([^"]+)"', line):
                    if m.group(1) != name:
                        cur["using"] = m.group(1)
                elif m := re.match(r'data "([^"]+)" "(.*)"', line):
                    cur["data"][m.group(1)] = m.group(2)

    def resolved(n, depth=0):
        e = raw[n]
        base = resolved(e["using"], depth + 1) if e["using"] in raw and depth < 30 else {}
        return {**base, **e["data"]}

    return {n: {**resolved(n), "_type": raw[n]["type"], "_using": raw[n]["using"]} for n in raw}


def parse_loca():
    t = P.LOCA.read_text(encoding="utf-8")
    return {m.group(1): html.unescape(m.group(2))
            for m in re.finditer(r'<content contentuid="([^"]+)"[^>]*>(.*?)</content>', t, re.S)}


def text(loca, handle):
    s = loca.get((handle or "").split(";")[0], "")
    # ponytail: [1]-style DescriptionParams placeholders kept as-is; captions are written by hand (Phase 4)
    s = re.sub(r"^%+\s*", "", re.sub(r"<[^>]+>", "", s).strip())      # Larian marks unfinished strings "%%% "
    return "" if s.upper() == "EMPTY" else s


# family / entry-type / school words that say nothing about which entry an icon was drawn for
STOP = {"spell", "action", "skill", "passive", "feature", "target", "projectile", "shout", "zone", "rush", "throw",
        "wall", "teleportation", "multistrike", "cone", "interrupt", "status", "generic", "icon", "abjuration",
        "conjuration", "divination", "enchantment", "evocation", "illusion", "necromancy", "transmutation"}


TYPE_RANK = {"SpellData": 0, "InterruptData": 1, "PassiveData": 2, "StatusData": 3}


def tokens(s):
    """Spell_Evocation_FireBolt -> {fire, bolt}"""
    return {t.lower() for t in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", s)} - STOP


def damage_type(e):
    t = e.get("DamageType", "")
    if not t:
        src = " ".join(e.get(k, "") for k in ("TooltipDamageList", "SpellSuccess", "SpellProperties", "SpellFail"))
        # one-level ( ... ) groups, unambiguous (CodeQL py/redos: the old form backtracked exponentially on ")(" runs);
        # same first match as before on all 3,234 DealDamage lines of the game stats (2026-10-19)
        m = re.search(r"DealDamage\((?:[^(),]|\((?:[^()]|\([^()]*\))*\))+,\s*(\w+)", src)
        t = m.group(1) if m else ""
    t = "Weapon" if "Weapon" in t else t           # MainMeleeWeaponDamageType etc. = whatever is wielded
    return t if t in DAMAGE_TYPES else ""


def spell_containers(st):
    """flyout families (2.7): icon sets of a container spell and its options (ContainerSpells / SpellContainerID), merged
    when they share an icon (Hex's six upcast containers are one flyout)"""
    sd = {n: e for n, e in st.items() if e["_type"] == "SpellData"}
    kids = defaultdict(set)
    for n, e in sd.items():
        kids[n] |= {c.strip() for c in re.split(r"[;,]", e.get("ContainerSpells", "")) if c.strip() in sd}
        if e.get("SpellContainerID") in sd:
            kids[e["SpellContainerID"]].add(n)
    fams = []
    for p, cs in kids.items():
        s = {sd[x].get("Icon", "") for x in cs | {p}} - {""}
        for f in [f for f in fams if f & s]:
            fams.remove(f)
            s |= f
        if len(s) > 1:
            fams.append(s)
    return fams


def icon_names():
    names = {p.stem for d in P.TOOLTIP_DIRS + P.CONTROLLER_DIRS for p in d.glob("*.DDS")}
    for lsx in P.ATLAS_MAPS:
        names |= set(re.findall(r'MapKey" type="FixedString" value="([^"]+)"', lsx.read_text(encoding="utf-8")))
    return sorted(names)


def step_meta():
    st = parse_stats()
    log(f"[1.1] stats entries {len(st)}:", Counter(e["_type"] for e in st.values()).most_common(6))
    loca = parse_loca()
    log(f"[1.1] loca strings {len(loca)}")
    by_icon = defaultdict(list)
    for n, e in st.items():
        if e.get("Icon"):
            by_icon[e["Icon"]].append(n)
    linkable = {n for n, e in st.items() if e["_type"] in ("StatusData", "PassiveData")}

    rows = []
    for icon in icon_names():
        # primary entry: among entries sharing a name word with the icon (Warding Flare, not the bombs reusing it),
        # spells first (statuses name the condition: "Banished"), then best name match, roots, shortest.
        # Spells beat name match: vanilla's FireShield_Warm file (snowflake art) belongs to "Fire Shield: Chill".
        it = tokens(icon)
        ens = sorted(by_icon.get(icon, []), key=lambda n: (not it & tokens(n), TYPE_RANK.get(st[n]["_type"], 9),
                                                          -len(it & tokens(n)), st[n]["_using"] is not None, len(n), n))
        es = [st[n] for n in ens]

        def vote(k, pool, get=lambda e, k: e.get(k, "")):
            c = Counter(v for e in pool if (v := get(e, k)))
            return c.most_common(1)[0][0] if c else ""

        intent = vote("VerbalIntent", es)
        agree = [e for e in es if e.get("VerbalIntent") == intent] or es   # other labels only from entries that agree
        links = sorted({tok for e in es for v in e.values() if isinstance(v, str)
                        for tok in re.findall(r"\w+", v) if tok in linkable} - set(ens))
        prim = es[0] if es else {}
        row = {
            "icon": icon, "family": icon.split("_")[0],
            "has_tooltip": P.tooltip(icon).exists(), "has_controller": P.controller(icon).exists(),
            "entries": ens, "types": sorted({e["_type"] for e in es}),
            "VerbalIntent": intent, **{k: vote(k, agree) for k in FIELDS if k not in ("VerbalIntent", "DamageType")},
            "DamageType": vote("DamageType", agree, lambda e, k: damage_type(e)),
            "name": text(loca, prim.get("DisplayName")), "description": text(loca, prim.get("Description")),
            "linked": [{"entry": n, "type": st[n]["_type"], "icon": st[n].get("Icon", "")} for n in links],
        }
        if m := re.fullmatch(r"GenericIcon_(DamageType|Intent)_(\w+)", icon):
            # fallback icons reused by random monster spells: the name is the true label, their text is not
            row.update({"VerbalIntent": "Damage", "DamageType": m[2]} if m[1] == "DamageType"
                       else {"VerbalIntent": m[2], "DamageType": ""})
            row.update(name="", description="")
        rows.append(row)
    write_jsonl(D / "meta.jsonl", rows)
    fam = Counter(r["family"] for r in rows if r["has_tooltip"])
    log(f"[1.1] wrote meta.jsonl: {len(rows)} icons, {sum(1 for r in rows if r['entries'])} with stats, "
        f"{sum(1 for r in rows if r['name'])} named; tooltip families:", fam.most_common(12))


# ---------------------------------------------------------------- 1.2 masters
def rgba(p, size=None):
    im = Image.open(p).convert("RGBA")
    if size and im.size != (size, size):
        im = resize(im, size)
    return np.asarray(im).astype(np.float32) / 255


def resize(im, size):
    """Premultiplied resize so transparent pixels' colour does not bleed into edges."""
    a = np.asarray(im.convert("RGBA")).astype(np.float32) / 255
    pm = np.dstack([a[..., :3] * a[..., 3:], a[..., 3]])
    out = np.dstack([np.asarray(Image.fromarray(pm[..., i]).resize((size, size), Image.LANCZOS)) for i in range(4)]).clip(0, 1)
    rgb = np.where(out[..., 3:] > 1e-4, out[..., :3] / np.maximum(out[..., 3:], 1e-4), 0).clip(0, 1)
    return Image.fromarray((np.dstack([rgb, out[..., 3]]) * 255 + .5).astype(np.uint8), "RGBA")


def step_fadefit():
    """Re-measure the vanilla fade (after a game patch) and compare it with fade.bottom_fade."""
    icons = [r["icon"] for r in read_jsonl(D / "meta.jsonl") if r["has_tooltip"] and r["has_controller"] and r["family"] not in EXCLUDED]
    mask, _ = fit_fade(icons)
    np.save(D / "fade_measured.npy", mask)
    prof, ours = np.median(mask[:, 60:320], axis=1), bottom_fade(380)[:, 0]
    d = (ours - prof)[19:]                          # rows 0-18: transparent top edge in vanilla
    log(f"[fadefit] {len(icons)} icons; formula vs measured row profile: RMSE {np.sqrt((d ** 2).mean()) * 255:.1f}/255, "
        f"max {np.abs(d).max() * 255:.1f}/255")
    log("   measured:", " ".join(f"{y}:{prof[y]:.2f}" for y in range(19, 380, 38)))
    log("   formula: ", " ".join(f"{y}:{ours[y]:.2f}" for y in range(19, 380, 38)))


def fit_fade(icons):
    """Measured 2D fade: per-pixel median of tooltip alpha / controller alpha."""
    ratios = np.full((len(icons), 380, 380), np.nan, np.float32)
    for i, n in enumerate(icons):
        t = rgba(P.tooltip(n))[..., 3]
        c = rgba(P.controller(n), 380)[..., 3]
        ratios[i] = np.where(c > .5, t / np.maximum(c, 1e-3), np.nan)
        if i % 300 == 0:
            log(f"    fade fit {i}/{len(icons)}")
    cnt = np.isfinite(ratios).sum(0)
    med = np.nanmedian(ratios, axis=0)
    rowmed = np.nanmedian(np.where(cnt >= 20, med, np.nan), axis=1)
    mask = np.where(cnt >= 20, med, rowmed[:, None]).clip(0, 1)  # sparse corners fall back to the row median
    return mask.astype(np.float32), cnt


def icon_fade(t, c, mask, sigma=12):
    """Per-icon smooth fade field: some tooltips add side vignettes / dim tops on top of the global
    bottom fade. Normalised convolution of tooltip/controller alpha where the controller is opaque
    enough, falling back to the global mask where there is no support."""
    from scipy import ndimage                       # = cv2.GaussianBlur(x, (0, 0), sigma) to 4e-7 (mirrored edges, 4 sigma): no OpenCV
    blur = lambda x: ndimage.gaussian_filter(x, sigma, mode="mirror", truncate=4.0)
    w = (c > .3).astype(np.float32)
    r = np.where(w > 0, t / np.maximum(c, 1e-3), 0).clip(0, 1.2).astype(np.float32)
    num, den = blur(r * w), blur(w)
    k = (den / .2).clip(0, 1)                       # support weight
    return (k * num / np.maximum(den, 1e-4) + (1 - k) * mask).clip(0, 1)


def make_master(n, mask):
    t = rgba(P.tooltip(n))
    c = rgba(P.controller(n), 380)
    f = icon_fade(t[..., 3], c[..., 3], mask)
    w = ((f - .2) / .2).clip(0, 1)                  # soft hand-over to controller alpha in the deep fade
    a = w * (t[..., 3] / np.maximum(f, 1e-3)).clip(0, 1) + (1 - w) * c[..., 3]
    # tooltip RGB is undefined where its alpha is ~0 (BC7 blocks): take the controller's colour there
    k = (t[..., 3:] / .05).clip(0, 1)
    rgb = k * t[..., :3] + (1 - k) * c[..., :3]
    m = Image.fromarray((np.dstack([rgb, a]) * 255 + .5).astype(np.uint8), "RGBA")
    return resize(m, 512)


def master_errors(n, mask):
    """Rebuild vanilla tiers from the master; mean |d| in /255 over alpha and premultiplied RGB."""
    m = Image.open(D / "masters" / f"{n}.png")

    def err(ours, ref):
        o, r = ours.copy(), ref.copy()
        o[..., :3] *= o[..., 3:]
        r[..., :3] *= r[..., 3:]
        return float(np.abs(o - r).mean() * 255)

    vt, vc = rgba(P.tooltip(n)), rgba(P.controller(n), 380)
    f = icon_fade(vt[..., 3], vc[..., 3], mask)[20:150]
    vignette = bool(f[vc[20:150, :, 3] > .3].mean() < .9)  # vanilla fades the top too: not our bottom-only fade
    t = np.asarray(resize(m, 380)).astype(np.float32) / 255
    t[..., 3] *= mask
    return err(t, vt), err(np.asarray(resize(m, 144)).astype(np.float32) / 255, rgba(P.controller(n))), vignette


def step_masters():
    rows = read_jsonl(D / "meta.jsonl")
    icons = [r["icon"] for r in rows if r["has_tooltip"] and r["has_controller"] and r["family"] not in EXCLUDED]
    log(f"[1.2] icons with tooltip + controller (excl. {EXCLUDED}): {len(icons)}")
    mask = bottom_fade(380)
    (D / "masters").mkdir(exist_ok=True)
    for i, n in enumerate(icons):
        make_master(n, mask).save(D / "masters" / f"{n}.png")
        if i % 300 == 0:
            log(f"    masters {i}/{len(icons)}")
    random.seed(1)
    errs = np.array([master_errors(n, mask) for n in random.sample(icons, 200)], dtype=np.float32)
    bf = errs[errs[:, 2] == 0]
    log(f"[1.2] wrote {len(icons)} masters. 200-icon check, mean |d|/255: controller {errs[:, 1].mean():.2f} "
        f"(p95 {np.percentile(errs[:, 1], 95):.2f}, target <=8, the gate); tooltip on {len(bf)} bottom-fade icons "
        f"{bf[:, 0].mean():.2f} (p95 {np.percentile(bf[:, 0], 95):.2f}, target <=3); "
        f"{len(errs) - len(bf)} vignette icons (vanilla quirk, not reproduced) {errs[errs[:, 2] == 1, 0].mean():.2f}")


# ---------------------------------------------------------------- 1.3 SRD 5.1
SRD_ALIAS = {"blindness": "blindnessdeafness", "createwater": "createordestroywater",
             "destroywater": "createordestroywater", "enlarge": "enlargereduce", "reduce": "enlargereduce",
             "conjureminorelemental": "conjureminorelementals", "conjurewoodlandbeing": "conjurewoodlandbeings",
             # Enhance Ability options after the owner strip: Bear's Endurance -> endurance
             **dict.fromkeys(("endurance", "strength", "grace", "splendor", "cunning", "wisdom"), "enhanceability")}


def norm_spell(n):
    n = n.strip().lower()
    n = re.sub(r"\s*(:.*|\(.*\))$", "", n)            # sub-options: "Hex (Strength)", "Chromatic Orb: Fire"
    n = re.sub(r"^(reapply|recast|activate|dismiss) ", "", n)
    n = re.sub(r"^\w+'s ", "", n)                    # SRD drops owners: Melf's Acid Arrow -> Acid Arrow
    n = re.sub(r"our\b", "or", n)                    # BG3 is British: Armour, Colour, Favour, Splendour
    n = re.sub(r"[^a-z]", "", n)
    return SRD_ALIAS.get(n, n)


def step_srd():
    """data/srd/5e-SRD-Spells.json (5e-bits/5e-database, src/2014/en; SRD 5.1, CC-BY-4.0) ->
    data/srd_spells.json + an `srd` key on matching meta rows."""
    src = json.loads((D / "srd/5e-SRD-Spells.json").read_text(encoding="utf-8"))
    spells = [{"index": s["index"], "name": s["name"], "level": s["level"], "school": s["school"]["name"],
               "damage_type": ", ".join(d.get("damage_type", {}).get("name", "") for d in s.get("damage") or []),
               "casting_time": s["casting_time"], "concentration": s["concentration"],
               "classes": [c["name"] for c in s.get("classes", [])],
               "text": "\n".join(s["desc"]), "higher_level": "\n".join(s.get("higher_level", []))} for s in src]
    (D / "srd_spells.json").write_text(json.dumps(spells, ensure_ascii=False, indent=1), encoding="utf-8")
    by = {norm_spell(s["name"]): s["index"] for s in spells}
    rows = read_jsonl(D / "meta.jsonl")
    for r in rows:
        r["srd"] = by.get(norm_spell(r["name"]), "") if r["name"] and r["family"] in SPELL_LIKE else ""
    write_jsonl(D / "meta.jsonl", rows)
    hit = {r["srd"] for r in rows if r["srd"]}
    log(f"[1.3] SRD spells {len(spells)}; matched {sum(1 for r in rows if r['srd'])} spell-like icons "
        f"({sum(1 for r in rows if r['srd'] and r['family'] == 'Spell')} Spell_) to {len(hit)} SRD spells; "
        f"SRD spells with no BG3 icon: {len(spells) - len(hit)}")


# ---------------------------------------------------------------- 1.4 tags
def colour_tags(p):
    a = rgba(p)
    px = a[..., :3][a[..., 3] > .5]
    if len(px) < 50:
        return {"multi_hue": False, "dark_fill": False, "hue": None}
    dark = float((px.max(1) < .35).mean())
    hsv = np.array([colorsys.rgb_to_hsv(*q) for q in px[:: max(1, len(px) // 3000)]])
    sat = hsv[(hsv[:, 1] > .35) & (hsv[:, 2] > .35)]
    if len(sat) < 20:
        return {"multi_hue": False, "dark_fill": dark > .1, "hue": None}
    h, _ = np.histogram(sat[:, 0] * 360, bins=24, range=(0, 360), weights=sat[:, 1] * sat[:, 2])
    k = int(h.argmax())
    far = [i for i in range(24) if min(abs(i - k), 24 - abs(i - k)) >= 3]  # >= 45 deg away from the main peak
    return {"multi_hue": bool(h[far].max() > .35 * h[k]), "dark_fill": dark > .1, "hue": k * 15 + 7.5}


def same_art(n, base):
    """alpha IoU at 64 px of two masters (None when either is missing)"""
    ps = [D / "masters" / f"{x}.png" for x in (n, base)]
    if not all(p.exists() for p in ps):
        return None
    a, b = (np.asarray(Image.open(p).convert("RGBA").resize((64, 64), Image.BOX))[..., 3] > 100 for p in ps)
    return float((a & b).sum() / max((a | b).sum(), 1))


def step_tags():
    rows = read_jsonl(D / "meta.jsonl")
    for r in rows:
        r["excluded"] = r["family"] in EXCLUDED
        r["variant_group"] = re.sub(r"_\d+$", "", r["icon"])
        # numbered name = badge copy (base art + a painted numeral, D14), unless its art differs from the base's: the
        # illithid powers Force Tunnel / Repulsor / Stage Fright _2 are new drawings (IoU 0.12-0.17; badge copies >= 0.42)
        iou = same_art(r["icon"], r["variant_group"]) if r["variant_group"] != r["icon"] else None
        r["numeral_badge"] = r["variant_group"] != r["icon"] and (iou is None or iou >= BADGE_IOU)
        if not r["numeral_badge"]:
            r["variant_group"] = r["icon"]
        mp = D / "masters" / f"{r['icon']}.png"
        r.update(colour_tags(mp) if mp.exists() else {"multi_hue": None, "dark_fill": None, "hue": None})
    write_jsonl(D / "meta.jsonl", rows)
    m = [r for r in rows if r["multi_hue"] is not None]
    log(f"[1.4] tagged {len(rows)}: excluded {sum(r['excluded'] for r in rows)}, numeral_badge {sum(r['numeral_badge'] for r in rows)}, "
        f"of {len(m)} masters multi_hue {sum(r['multi_hue'] for r in m)}, dark_fill {sum(r['dark_fill'] for r in m)}")


# ---------------------------------------------------------------- 1.5 hold-out
def step_holdout():
    """data/holdout.txt + data/train.txt: v1 icons with a master, numbered badge variants left out of both (D14)."""
    allv1 = [r for r in read_jsonl(D / "meta.jsonl") if r["family"] in SPELL_LIKE and (D / "masters" / f"{r['icon']}.png").exists()]
    rows = [r for r in allv1 if not r["numeral_badge"]]
    groups = defaultdict(list)                      # keep numbered variants together (no leakage)
    for r in rows:
        groups[r["variant_group"]].append(r)
    strata = defaultdict(list)
    for g, rs in groups.items():
        strata[(rs[0]["family"], rs[0]["VerbalIntent"], rs[0]["DamageType"])].append(g)
    # icons already split keep their side, so numbers stay comparable when the game adds icons (Patch 8, 2026-10-14);
    # new groups top each stratum up to 10%
    old = {f: set((D / f"{f}.txt").read_text().split()) if (D / f"{f}.txt").exists() else set() for f in ("holdout", "train")}
    rng = random.Random(0)
    hold = []
    for k in sorted(strata):
        gs = sorted(strata[k])
        rng.shuffle(gs)
        was = lambda g, f: any(r["icon"] in old[f] for r in groups[g])
        keep = [g for g in gs if was(g, "holdout")]
        new = [g for g in gs if not was(g, "holdout") and not was(g, "train")]
        hold += keep + new[: max(0, round(len(gs) * .1) - len(keep))]
    icons = sorted(r["icon"] for g in hold for r in groups[g])
    train = sorted({r["icon"] for r in rows} - set(icons))
    (D / "holdout.txt").write_text("\n".join(icons) + "\n", encoding="utf-8")
    (D / "train.txt").write_text("\n".join(train) + "\n", encoding="utf-8")
    log(f"[1.5] {len(allv1)} v1 icons, {len(allv1) - len(rows)} badge variants left out (D14): train {len(train)}, "
        f"hold-out {len(icons)} ({len(strata)} strata):", Counter(i.split("_")[0] for i in icons).most_common())


# ---------------------------------------------------------------- contact sheet
def checker(s, k=16):
    y, x = np.mgrid[:s, :s]
    v = np.where((x // k + y // k) % 2, 140, 90).astype(np.uint8)
    return Image.fromarray(np.dstack([v, v, v, np.full_like(v, 255)]), "RGBA")


def step_sheet():
    rows = [r for r in read_jsonl(D / "meta.jsonl") if (D / "masters" / f"{r['icon']}.png").exists()]
    rng = random.Random(3)
    pick = []
    for fam, n in (("Spell", 10), ("Action", 8), ("Skill", 2), ("PassiveFeature", 2)):
        pick += rng.sample([r for r in rows if r["family"] == fam], n)
    pick += rng.sample([r for r in rows if r["numeral_badge"]], 1) + rng.sample([r for r in rows if r["multi_hue"]], 1)
    C, cols = 256, 6
    sheet = Image.new("RGBA", (cols * (C + 8), (len(pick) + cols - 1) // cols * (C + 58)), (25, 25, 28, 255))
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(pick):
        x, y = i % cols * (C + 8), i // cols * (C + 58)
        tile = checker(C)
        tile.alpha_composite(Image.open(D / "masters" / f"{r['icon']}.png").resize((C, C), Image.LANCZOS))
        sheet.alpha_composite(tile, (x, y + 52))
        tags = " ".join(t for t in ("badge", "multi_hue", "dark_fill") if r.get(t if t != "badge" else "numeral_badge"))
        d.text((x + 3, y + 3), r["icon"][:40], fill=(255, 230, 120, 255))
        d.text((x + 3, y + 17), f"{r['name'][:38]}", fill=(230, 230, 230, 255))
        d.text((x + 3, y + 31), f"{r['VerbalIntent']} {r['DamageType']} {r['SpellSchool']} {tags}"[:42], fill=(150, 200, 255, 255))
    sheet.save(D / "contact_sheet.png")
    log(f"[sheet] wrote {D / 'contact_sheet.png'} ({len(pick)} icons)")


STEPS = {"meta": step_meta, "fadefit": step_fadefit, "masters": step_masters, "srd": step_srd, "tags": step_tags, "holdout": step_holdout, "sheet": step_sheet}

if __name__ == "__main__":
    D.mkdir(exist_ok=True)
    for s in ([k for k in STEPS if k != "fadefit"] if sys.argv[1] == "all" else sys.argv[1:]):
        STEPS[s]()
