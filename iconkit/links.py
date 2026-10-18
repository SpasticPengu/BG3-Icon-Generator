"""Phase 2.7 connections audit (user, 2026-10-15: "go through the spells/wiki ... any other connections between icons that
would affect how we train or if it can be done programmatically"). Links beyond 2.5's shared drawings and 2.6's series:
- spell flyouts (extract.spell_containers: container spell + its options) join shape.series (D33 weights)
- each action's source: class / subclass / race (Progressions + SpellLists + PassiveLists + passives' UnlockSpell), the
  items that unlock it (MAG_ = magic item, plain weapons = weapon action), monster / end-game ally / legendary / magic item /
  wild magic by name, Battle Master manoeuvres from bg3.wiki; tested like 2.6 (shape.test: one icon per series, shuffled
  within intent)
- Reapply spells = the base drawing shrunk + a two-arc ring: rebuilt in code with the ring of the OTHER pairs
- frame families: a frame drawn in every member and a symbol swapped (leave-one-out frame recall and share)
Checked, not found: a motif library beyond the damage symbols (bears, wolves, greatswords, elements are redrawn per
series); `using` inheritance is game mechanics, not drawings.
    python -m iconkit.links [run]  -> data/links.json (~3 min; needs data/shape.npz)
    python -m iconkit.links report -> data/links.html (review page, local: Larian art)
    python -m iconkit.links check  -> self-check on drawn shapes"""
import json, re, sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from .extract import D, ILLITHID_ART, parse_stats, read_jsonl, log, spell_containers
from . import paths as PA
from .glyph import master, POOL
from .relations import line_art, kappa, pool64, element_series, paint
from .shape import test, FEATS

DECIDED = {1: "A", 2: "A", 3: "A"}         # user, 2026-10-15 (plan D34, D35, D36)
S = 128                                    # px the line art is compared at
# frame = lines in 80% of the other members; EVERY member draws 90%+ of it (a median let loose families in: Pact of the
# Blade's gripping hand, scattered rocks) and it is 15%+ of the member's lines
FRAME_MIN, FRAME_RECALL, FRAME_SHARE = .8, .9, .15
# bg3.wiki/wiki/Battle_Master (2026-10-15): the manoeuvres (their stats come through subclass choices the lists miss)
WIKI = {**{m: "Fighter" for m in ("CommandersStrike", "DisarmingAttack", "DistractingStrike", "EvasiveFootwork",
                                   "FeintingAttack", "GoadingAttack", "ManeuveringAttack", "MenacingAttack",
                                   "PrecisionAttack", "PushingAttack", "Rally", "Riposte", "SweepingAttack", "TripAttack")},
        "DivineStrike": "Cleric", "DivineIntervention": "Cleric"}
NAMED = {"Monster": "Monster", "EndGameAlly": "End-game ally", "EndGame": "End-game ally", "Legendary": "Legendary",
         "Mag": "Magic item", "MagicItem": "Magic item", "WildMagic": "Wild Magic"}
BEASTS = {"Bear", "Boar", "Cat", "Wolf", "DireWolf", "Spider", "Raven", "Panther", "SaberTooth", "Dilophosaurus",
          "DeepRothe", "Owlbear", "Badger", "Crab", "Rat", "Bat", "Myrmidon", "Elk", "Tiger"}
# Phase 4: actions the game data cannot place (checked on contact sheets + stats, 2026-10-15). Basic actions = every
# character's (Perform: the "Perform" passive every hero has; Dip's dipped attacks; Dismiss Summon), summons = the
# summoner's class if one class brings them (Pact of the Chain imp / quasit, the Hexblade's Accursed Specter), else
# Monster (Find Familiar's frog; Right Behind You / Splinter Shadow: Hexblade specter and Shadow sorcerer hound), Story =
# origin and quest actions. Unused icons (no stats) by name and drawing style; the ones neither tells stay ''
_h = lambda lab, s: {f"Action_{n}": lab for n in s.split()}
HAND = {**_h("Basic action", "Dash Disengage Dip DippedFire_Melee DippedFire_Ranged DippedPoison_Melee DippedPoison_Ranged "
                             "Help Hide_Regular Jump Shove Throw ImprovisedWeapon UnarmedAttack KnockOut RegainHP "
                             "DismissSummon Perform_Voice Song_BardDance Song_OldTimeBattles Song_ThePower "
                             "Song_OfDivinityAndSin Song_PlayTheSpidersLyre Song_SingForMe Song_TheQueensHighSeas "
                             "TossACoin Sprint ThrowWeapon "
                             "Perform_Drum Perform_Flute Perform_Lute Perform_Lyre Perform_Violin"),   # any instrument
        **_h("Weapon action", "Sweep Trip"),
        **_h("Feat", "InspiringLeader ShieldShove Charger_Push"),
        **_h("Warlock", "AccursedSpecter_SoulDevour AccursedSpecter_SoulPluck AccursedSpecter_SoulReaping "
                        "AccursedSpecter_SoulSeize Imp_Claws Imp_Invisibility Quasit_Claws Quasit_Invisibility Quasit_Scare"),
        **_h("Wild Shape beast", "GiantBadger_Bite GiantBadger_Burrow GiantBadger_Claws DireWolfPack_Howl"),
        "Action_WildShape_Bat": "Druid",                # drawn as the Druid's other Wild Shape forms (beast + human)
        **_h("Monster", "Frog_Bufotoxin Glut_BlackSporeCloud Glut_GreenSporeCloud Glut_HallucinationSpores Glut_MultiAttack "
                        "Glut_PacifyingSpores Glut_RaiseDeadViaSpores Glut_WhiteSporeCloud Healer_Heal HookHorror_Hook "
                        "HookHorror_Multiattack Pounce_HookHorror IronboundPursuit Singing Slam Zombie_Slam VampireBite "
                        "Flurry RightBehindYou SplinterShadows ExhaleFire ElementalWarp"),
        "Skill_Shout_StaticOverdrive_Automaton": "Monster", "Action_BelmsBonusAttack": "Magic item",   # Belm, the scimitar
        "Action_BenignTransposition_Swap": "Wizard",                                                 # Conjuration school
        "Action_SightOfTheSeelie_BestialCommunion_Wildshape": "Magic item",                      # a cursed tome's power
        "Action_ForcedManeuver": "Fighter",                        # the Manoeuvring Attack's ally move (Battle Master)
        **_h("Story", "AbsolutePower ContactMizora DarkUrge KarsusCompulsion SacrificeToLoviatar SelunesDream TalkToAmulet "
                      "InspectMoonLantern SoulBranding")}
unlock = lambda s: [x.strip() for x in re.findall(r"UnlockSpell\(([^,)]+)", s or "")]


def lsx_nodes(pattern, kind):
    """attribute dicts of every <node id=kind> in the BaseGameReference files named pattern"""
    return [{a.get("id"): a.get("value") for a in nd.findall("attribute")}
            for f in sorted(PA.BASEREF.rglob(pattern)) for nd in ET.parse(f).iter("node") if nd.get("id") == kind]


def unlocks(st):
    """stat entry -> the entries it hands on: UnlockSpell targets, statuses it applies, a status's Passives, a flyout's
    options (Phase 4: Dread Ambusher's status, Bladesong's passives, Starry Form's statuses, Elemental Cleaver's options)"""
    out = defaultdict(set)
    for n, e in st.items():
        txt = ";".join(v for k, v in e.items() if isinstance(v, str) and not k.startswith("_"))
        out[n] |= set(unlock(txt))
        out[n] |= {s for a in re.findall(r"ApplyStatus\(([^)]*)\)", txt) for s in re.split(r"\s*,\s*", a) if s in st}
        out[n] |= {p.strip() for p in re.split(r"[;,]", e.get("Passives") or "") if p.strip() in st}
        out[n] |= {c.strip() for c in re.split(r"[;,]", e.get("ContainerSpells") or "") if c.strip() in st}
        if e.get("SpellContainerID") in st:
            out[e["SpellContainerID"]].add(n)
    return out


def sources(names, rows, st):
    """icon -> where the game gives it: a class (subclasses folded into their class), 'Race', 'Feat', 'Weapon action',
    'Magic item', 'Monster', 'End-game ally', 'Legendary', 'Wild Magic', 'Wild Shape beast', 'Illithid', 'several classes'
    or a hand label (HAND: basic actions, summons, story actions the data cannot reach)"""
    split = lambda s: [x.strip() for x in re.split(r"[;,]", s or "") if x.strip()]     # PassiveLists use commas too
    lists = {a.get("UUID"): split(a.get("Spells")) for a in lsx_nodes("SpellLists.lsx", "SpellList")}
    plists = {a.get("UUID"): split(a.get("Passives")) for a in lsx_nodes("PassiveLists.lsx", "PassiveList")}
    cls = lsx_nodes("ClassDescriptions.lsx", "ClassDescription")
    by_uuid = {a.get("UUID"): a.get("Name") for a in cls}
    parent = {a.get("Name"): by_uuid.get(a.get("ParentGuid"), a.get("Name")) for a in cls}
    pas = {n: unlock(e.get("Boosts")) for n, e in st.items() if e["_type"] == "PassiveData"}
    nxt = unlocks(st)
    grant, deep = defaultdict(set), defaultdict(set)
    rows_ = [(a, a.get("Name") or "", a.get("ProgressionType") or "0") for a in lsx_nodes("Progressions.lsx", "Progression")]
    rows_ += [(a, "Feat", "feat") for a in lsx_nodes("Feats.lsx", "Feat")]
    for a, who, ty in rows_:
        sel = a.get("Selectors") or ""
        sp = set(unlock(a.get("Boosts")))
        sp |= {s for u in re.findall(r"(?:AddSpells|SelectSpells)\(([0-9a-f-]{36})", sel) for s in lists.get(u, [])}
        ps = split(a.get("PassivesAdded"))
        ps += [p for u in re.findall(r"(?:AddPassives|SelectPassives)\(([0-9a-f-]{36})", sel) for p in plists.get(u, [])]
        sp |= {s for p in ps for s in pas.get(p, [])}
        for s in sp:
            grant[s.strip()].add((who, ty))
        seen, front = set(), set(sp) | set(ps)          # what the granted spells / passives hand on, 4 steps deep
        for _ in range(4):
            front = {y for x in front for y in nxt.get(x, ())} - seen
            seen |= front
        for s in seen:
            deep[s].add((who, ty))
    item = defaultdict(set)
    for n, e in st.items():
        if e["_type"] in ("Weapon", "Armor", "Object"):
            for v in e.values():
                for s in unlock(v) if isinstance(v, str) else ():
                    item[s].add("Magic item" if n.startswith(("MAG_", "UNI_")) or "_MAG_" in n else "Weapon action")
    classes = set(parent.values())

    wa = {n for n, e in st.items() if "IsDefaultWeaponAction" in (e.get("SpellFlags") or "")}

    def one(n):
        t = n.split("_") + [""]
        if n in HAND:
            return HAND[n]
        if t[0] == "TadpoleSuperPower" or n in ILLITHID_ART:
            return "Illithid"
        for d in (WIKI, NAMED):
            if t[1] in d:
                return d[t[1]]
        if t[1] in classes:
            return t[1]
        if t[1] in BEASTS:
            return "Wild Shape beast"
        for gr in (grant, deep):                    # what a progression grants first, then what that hands on
            g = {x for e in rows[n]["entries"] for x in gr.get(e, ())}
            if g:
                top = {parent.get(nm, nm) for nm, ty in g if ty != "2"}
                return "Race" if not top else top.pop() if len(top) == 1 else "several classes"
        it = {x for e in rows[n]["entries"] for x in item.get(e, ())}
        if it:
            return "Weapon action" if "Weapon action" in it else "Magic item"
        return "Weapon action" if wa & set(rows[n]["entries"]) else ""          # Bash, Slash, Smash, Pin Down
    return {n: one(n) for n in names}


# ---------------------------------------------------------------- Reapply = base shrunk + ring
def reapply_pairs(names):
    """(base, reapply) icons: Spell_Enchantment_ReapplyHex_Wisdom -> Spell_Enchantment_Hex_Wisdom, X_Reapply -> X"""
    ns = set(names)
    out = []
    for r in sorted(n for n in names if "Reapply" in n):
        b = r[:-len("_Reapply")] if r.endswith("_Reapply") else r.replace("Reapply", "")
        if b in ns:
            out.append((b, r))
    return out


def shrink(la, s, dy=0):
    """line art (dict of S x S channels) scaled by s about the centre and moved dy px down"""
    n, w = la["AL"].shape[0], max(round(la["AL"].shape[0] * s), 1)
    out = {}
    for k, v in la.items():
        im = Image.new("F", (n, n), 0.0)
        im.paste(Image.fromarray(v.astype(np.float32), "F").resize((w, w), Image.BILINEAR), ((n - w) // 2, (n - w) // 2 + dy))
        out[k] = np.asarray(im).astype(np.float64)
    return out


k2 = lambda a, b: float(kappa(np.stack([pool64(a), pool64(b)]))[0, 1])


def reapply_fit(base, re_):
    """(scale, dy, ring): the shrink whose lines lie on the reapply icon's lines best (line pixels within 1 px of them minus
    those not: the largest shrink that still fits; scoring only the reapply's lines near the shrunk base rewarded
    shrinking too far), and the reapply's lines it does not explain (the ring), as line art"""
    near = ndimage.binary_dilation(re_["AL"] > .5)
    fit = lambda m: int((m & near).sum()) - int((m & ~near).sum())
    best = max(((fit(shrink(base, s, dy)["AL"] > .5), s, dy) for s in np.arange(.55, .96, .025) for dy in (-4, -2, 0, 2, 4)),
               key=lambda t: t[0])
    sb = shrink(base, best[1], best[2])
    off = ndimage.binary_dilation(sb["AL"] > .5, iterations=2)
    return float(best[1]), int(best[2]), {k: np.where(off, 0, v) for k, v in re_.items()}


def reapply(base, s, dy, ring):
    """the reapply icon in code: base shrunk + ring drawn over (line art)"""
    sb = shrink(base, s, dy)
    top = ring["AL"] > sb["AL"]
    return {k: np.where(top, ring[k], sb[k]) for k in sb}


def la_job(n):
    return n, line_art(master(n), S)


# ---------------------------------------------------------------- frame families
def frame_stats(icons, A):
    """leave-one-out over a family: frame = lines in FRAME_MIN of the other members (as placed); recall = share of the frame
    the member draws (1 px tolerance), share = that / the member's lines -> (median recall, min recall, median share)"""
    rec, sh = [], []
    for n in icons:
        fr = np.mean([A[m] for m in icons if m != n], 0) >= FRAME_MIN
        hit = (fr & ndimage.binary_dilation(A[n])).sum() if fr.sum() >= 30 else 0
        rec.append(hit / max(fr.sum(), 1))
        sh.append(hit / max(A[n].sum(), 1))
    return float(np.median(rec)), float(np.min(rec)), float(np.median(sh))


def families(names, ser, flyouts):
    """candidate families (3+ icons): flyouts, 2.6 series, and name families (same Family_Token1 prefix, and the same plus
    the first word of Token2: Action_Paladin_Aura*); identical sets kept once"""
    fams = {f"flyout: {min(s, key=len)}": sorted(s) for s in flyouts}
    by = defaultdict(list)
    for n, s in zip(names, ser):
        by[s].append(n)
    fams.update({f"series: {v[0]}": sorted(v) for v in by.values()})
    pre = defaultdict(list)
    for n in names:
        t = n.split("_")
        if len(t) > 2:
            pre["_".join(t[:2])].append(n)
            pre["_".join(t[:2]) + "_" + re.match(r"[A-Z]?[a-z0-9]*", t[2]).group()].append(n)
    fams.update({f"name: {k}*": sorted(v) for k, v in pre.items()})
    seen, out = set(), {}
    for k, v in fams.items():
        if len(v) >= 3 and tuple(v) not in seen:
            seen.add(tuple(v))
            out[k] = v
    return out


def run():
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    st = parse_stats()
    Z = np.load(D / "shape.npz")
    names = Z["names"].tolist()
    ix = {n: i for i, n in enumerate(names)}
    K = Z["K"].astype(np.float64)
    ser, rep, kd, intent = Z["series"], Z["rep"], Z["L_kind"], Z["L_intent"]

    # 1 source of every icon; does it change the drawing (actions; spells sit on several class lists)?
    src = sources(names, rows, st)
    sa = np.array([src[n] for n in names])
    log(f"[2.7] sources of v1 actions: {Counter(sa[kd == 'Action'].tolist()).most_common()}")
    F = Z["F"]
    Zf = (F - F.mean(0)) / (F.std(0) + 1e-9)
    sel = rep & (kd == "Action") & ~np.isin(sa, ["", "several classes"])
    c = Counter(sa[sel].tolist())
    sel &= np.isin(sa, [x for x, v in c.items() if v >= 8])
    si = np.where(sel)[0]
    Ks = K[np.ix_(si, si)].copy()
    np.fill_diagonal(Ks, -9)
    t = test(Zf[si], Ks, sa[si], {"nothing": np.zeros(len(si), int), "intent": intent[si]}, np.random.default_rng(0))
    lab = sa[si]
    hit = lab[Ks.argmax(1)] == lab
    t["nearest_same"] = {g: [round(float(hit[lab == g].mean()), 3), round(float((lab == g).mean()), 3)] for g in t["classes"]}
    t["median"] = {g: [round(float(v), 3) for v in np.median(F[si][lab == g], 0)] for g in t["classes"]}
    nl = t["nulls"]["intent"]
    log(f"[2.7] source vs drawing, actions one per series ({t['n']}, {len(t['classes'])} sources, chance {t['chance']}): "
        f"classifier {t['clf']} (shuffled in intent {nl['clf']}, p95 {nl['clf_p95']}), nearest drawing {t['nn']} "
        f"({nl['nn']}, p95 {nl['nn_p95']}) -> {t['verdict']}; nearest drawing from the same source / chance: "
        + ", ".join(f"{g} {a}/{b}" for g, (a, b) in t["nearest_same"].items()))

    # 2 flyouts (now part of shape.series) and other stats links
    fly = [sorted(s & set(names)) for s in spell_containers(st)]
    fly = [s for s in fly if len(s) > 1]
    using = defaultdict(set)
    for n, e in st.items():
        if e["_type"] == "SpellData" and e["_using"] in st and e.get("Icon") in ix:
            using[e["_using"]].add(e["Icon"])
    within = lambda s: np.median([K[ix[a], ix[b]] for a in s for b in s if a < b])
    uk = [within(s) for s in using.values() if len(s) > 1]
    fk = [within(s) for s in fly]
    iu = np.triu_indices(len(names), 1)
    ranged = [(n.replace("_Ranged", "_Melee"), n) for n in names if "_Ranged" in n and n.replace("_Ranged", "_Melee") in ix]
    rk = [K[ix[a], ix[b]] for a, b in ranged]
    links = {"flyouts": fly, "flyout_kappa": round(float(np.median(fk)), 3), "using_groups": len(uk),
             "using_kappa": round(float(np.median(uk)), 3), "random_kappa": round(float(np.median(K[iu])), 3),
             "ranged": ranged, "ranged_kappa": round(float(np.median(rk)), 3)}
    log(f"[2.7] within-group kappa medians: flyouts {links['flyout_kappa']} ({len(fly)}), `using` children "
        f"{links['using_kappa']} ({len(uk)} groups), ranged/melee pairs {links['ranged_kappa']} ({len(ranged)}), random pairs "
        f"{links['random_kappa']}")

    # 3 Reapply = base shrunk + ring; 4 frame families
    with Pool(POOL) as pool:
        LA = dict(pool.map(la_job, names, chunksize=12))
    pairs = reapply_pairs(names)
    fit = {r: reapply_fit(LA[b], LA[r]) for b, r in pairs}
    rows_r = []
    for b, r in pairs:
        s, dy, _ = fit[r]
        rings = [fit[x][2] for y, x in pairs if ser[ix[y]] != ser[ix[b]]]          # the ring of unrelated pairs
        ring = {k: np.median(np.stack([g[k] for g in rings]), 0) for k in LA[b]}
        rows_r.append({"base": b, "reapply": r, "scale": round(s, 3), "dy": dy,
                       "code": round(k2(reapply(LA[b], s, dy, ring)["AL"], LA[r]["AL"]), 3),
                       "base_as_is": round(k2(LA[b]["AL"], LA[r]["AL"]), 3)})
        log(f"[2.7] {r}: scale {s:.3f} dy {dy:+d}, code {rows_r[-1]['code']} (base as is {rows_r[-1]['base_as_is']})")
    A = {n: v["AL"] > .5 for n, v in LA.items()}
    fams = families(names, ser, fly)
    el = {n for p, s in element_series(names).items() for n in s.values()}
    fr = []
    for k, v in fams.items():
        rm, rmin, sh = frame_stats(v, A)
        if rmin >= FRAME_RECALL and sh >= FRAME_SHARE:
            fr.append({"family": k, "icons": v, "recall": round(rm, 3), "recall_min": round(rmin, 3), "share": round(sh, 3),
                       "element": bool(sum(n in el for n in v) >= len(v) / 2), "series": len({int(ser[ix[n]]) for n in v})})
    fr.sort(key=lambda f: (-f["recall"], -len(f["icons"])))
    keep = []
    for f in fr:                                   # a family inside a bigger frame family adds nothing
        if not any(set(f["icons"]) < set(g["icons"]) for g in fr):
            keep.append(f)
    log(f"[2.7] frame families (frame in {FRAME_MIN:.0%} of the others, every member draws {FRAME_RECALL:.0%}+ of it, "
        f"{FRAME_SHARE:.0%}+ of its lines): {len(keep)} of {len(fams)} candidates, {sum(len(f['icons']) for f in keep)} icons; element series "
        f"among them {sum(f['element'] for f in keep)}; spread over 2+ series {sum(f['series'] > 1 for f in keep)}")
    for f in keep[:50]:
        log(f"    {f['recall']:.2f} ({f['recall_min']:.2f}) share {f['share']:.2f} n{len(f['icons'])} series {f['series']}"
            f"{' element' if f['element'] else ''}  {f['family']}")
    J = {"notes": "sources: icon -> source label; source_test: shape.test on actions one per series (nulls: nothing, intent), "
                  "nearest_same = [share whose kappa-nearest drawing has the same source, share of that source]; links: "
                  "within-group kappa medians; reapply: shrink + ring of unrelated pairs, kappa vs the game's; frames: "
                  "leave-one-out frame recall / share per family",
         "sources": src, "source_test": t, "links": links, "reapply": rows_r,
         "reapply_scale": [round(float(np.median([r["scale"] for r in rows_r if r["reapply"].startswith("Spell")])), 3),
                           int(np.median([r["dy"] for r in rows_r if r["reapply"].startswith("Spell")]))],
         "frames": keep, "frame_candidates": len(fams)}
    (D / "links.json").write_text(json.dumps(J, indent=1), encoding="utf-8")
    log(f"[2.7] wrote {D / 'links.json'}")


# ---------------------------------------------------------------- review page (data/links.html, local: Larian art)
def report():
    from .page import e, figure, decision, row, lede_reply, page
    from .grammar import kind, DARK
    J = json.loads((D / "links.json").read_text(encoding="utf-8"))
    SJ = json.loads((D / "shape.json").read_text(encoding="utf-8"))
    OLD = json.loads((D / "shape.d33.json").read_text(encoding="utf-8"))        # 2.6 as decided (series without flyouts)
    G = json.loads((D / "grammar.json").read_text(encoding="utf-8"))
    GL = json.loads((D / "glyph.json").read_text(encoding="utf-8"))
    P = {p["name"]: p for p in G["presets"]}
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    hold = set((D / "holdout.txt").read_text().split())
    Z = np.load(D / "shape.npz")
    names, rep = Z["names"].tolist(), Z["rep"]
    src, T, keep = J["sources"], J["source_test"], []
    nm = lambda n: (rows.get(n) or {}).get("name") or n.split("_", 1)[1]
    fig = lambda n, cap=None, size=64: figure(D / "masters" / f"{n}.png", nm(n) if cap is None else cap, n, size, n in hold)

    def pil(a):
        im = Image.fromarray((np.clip(a, 0, 1) * 255).round().astype(np.uint8))
        keep.append(im)
        return im

    def game(n):
        x = master(n).reshape(S, 512 // S, S, 512 // S, 4).mean((1, 3))
        return pil(x[..., :3] * x[..., 3:] + DARK * (1 - x[..., 3:]))

    def recipe(n, p):
        k = f"{kind(rows[n])}|{p}"
        return GL["glow"][k if k in GL["glow"] else GL["borrow"].get(k, kind(rows[n]))]

    nl = T["nulls"]["intent"]
    ns = T["nearest_same"]
    old, new = (lambda j, k: j["tests"][k]), SJ["tests"]
    st_old, st_new = OLD["tests"]["SpellType|Action|series"], new["SpellType|Action|series"]
    sc_new = new["school|Spell|series"]
    vt = {"yes": "changes the drawing", "weak": "a hint only (one of the two tests)", "no": "no change"}
    style = [g for g in T["classes"] if ns[g][0] >= 2 * ns[g][1] + .05]
    plain = [g for g in T["classes"] if g not in style]
    ex1 = "".join(f'<div class=cgroup><div class=chead><b>{e(g)}</b> (nearest drawing from the same source {ns[g][0]:.0%}, '
                  f'chance {ns[g][1]:.0%})</div><div class=crow>'
                  + "".join(fig(n) for n in [n for n, r in zip(names, rep) if r and src[n] == g][:9]) + '</div></div>'
                  for g in style[:7] + plain[:2])
    sn = st_new["nulls"]["intent"]
    cmp_ = ('<div class=tw-x><table class=t><tr><th>Option</th><th>Source</th><th>Spell type (actions)</th>'
            '<th>Caption for Aura of Courage (Paladin, buff, shout)</th><th>App field for actions</th></tr>'
            + "".join(f'<tr><td>{k}</td><td>{a}</td><td>{b}</td><td><code>{e(c)}</code></td><td>{e(f)}</td></tr>' for k, a, b, c, f in (
                ("A", "in", "out", "bg3 action icon, paladin, buff, <motif>. <description>", "+ Source"),
                ("B", "in", "in", "bg3 action icon, paladin, buff, shout, <motif>. <description>", "+ Source, Spell type"),
                ("C (D32 now)", "out", "in", "bg3 action icon, buff, shout, <motif>. <description>", "+ Spell type")))
            + '</table></div>')
    d1 = decision(1, 3, DECIDED.get(1), T["n"], "Action prompts: add where an action comes from? Keep its spell type?",
                  f"Two questions about the words that describe an action to the model (its caption in training, its prompt "
                  f"in the app), and so about the app's fields for actions. Both are tested as 2.6 tested school: guess the "
                  f"field from the drawing's shape alone, then again with the field shuffled among icons of the same intent "
                  f"(what knowing only the intent gets you); one icon per series. If the drawing beats intent, the field "
                  f"tells the model something new. 1. Source (new): where the game gives the action: a class feature, a "
                  f"monster, an end-game ally, a legendary action, a magic item, a weapon (from the game's progression "
                  f"tables and items; bg3.wiki for the Battle Master manoeuvres). The drawing gives it away {T['clf']:.0%} of "
                  f"the time, intent only {nl['clf']:.0%} (chance {T['chance']:.0%}): a clear yes. Rows below: legendary "
                  f"actions all sit in one gold frame, end-game allies share a crest style, Paladin, Bard and Barbarian "
                  f"features have house styles; manoeuvres and weapon actions do not. 2. Spell type on actions (kept by "
                  f"D32): 2.6 measured {st_old['clf']:.0%} vs {st_old['nulls']['intent']['clf']:.0%}. Arcane Shot's 8 arrows "
                  f"and the breath weapons had counted as separate drawings and made \"projectile\" and \"zone\" look like "
                  f"drawing rules; counting each flyout family once, it is {st_new['clf']:.0%} vs {sn['clf']:.0%}, within "
                  f"noise (the shuffle alone reaches {sn['clf_p95']:.0%} one time in twenty). A weak hint, the same as "
                  f"school, which D32 left out.",
                  cmp_ + ex1,
                  [("A", "Source in, spell type out",
                    "Every action's caption names its source (\"paladin\", \"monster\", \"legendary action\", \"magic "
                    "item\"...); the app gets a Source field for actions, pre-set when you start from a game action. Spell "
                    "type leaves captions and the app, as school did (D32's rule: only fields that change the drawing); a "
                    "cone's diagonal sweep is still described by the motif text (4.1)."),
                   ("B", "Source in, spell type stays",
                    "As A, and spell type stays on actions as D32 settled it: one more field for a hint within noise."),
                   ("C", "No source (D32 as settled)",
                    "Captions keep intent and spell type on actions; the plan's four source tags stay (wild magic, monster "
                    "ability, magic item, basic action). Legendary frames and ally styles are learned from motif text only.")],
                  note="Spells get no source: 186 of 233 sit on several class lists, so a spell has no single source to "
                       "name.", unit="actions")
    # decision 2: Reapply
    pairs = [(r["base"], r["reapply"]) for r in J["reapply"] if r["reapply"].startswith("Spell_")]
    LA = {n: line_art(master(n), S) for p in pairs for n in p}
    fits = {r: reapply_fit(LA[b], LA[r]) for b, r in pairs}
    ring = {k: np.median(np.stack([f[2][k] for f in fits.values()]), 0) for k in ("AL", "B", "a")}
    sc, dy = J["reapply_scale"]
    sp = [r for r in J["reapply"] if r["reapply"].startswith("Spell_")]
    chains = ""
    for b, r in [p for i, p in enumerate(pairs) if i in (0, 3, len(pairs) - 2, len(pairs) - 1)]:
        p = G["assigned"].get(b, [None])[0]
        code = paint(reapply(LA[b], *fits[r][:2], ring), P[p], recipe(b, p)) if p in P else None
        chains += (f'<div class=chain>{figure(game(b), "game", b, 72)}<span class=arrow>→</span>'
                   + (figure(pil(code), "code", r, 72) if code is not None else "")
                   + f'<span class=arrow>≈</span>{figure(game(r), "game reapply", r, 72)}</div>')
    d2 = decision(2, 3, DECIDED.get(2), len(sp), "Reapply icons: build them in code from the base drawing?",
                  f"The {len(sp)} Reapply spells (Hex and its six abilities, Hunter's Mark, Heat Metal) are the base drawing "
                  f"shrunk to about {sc:.0%} and nudged down, inside a two-arc ring. Code rebuilds each from its base with "
                  f"the ring taken from the other pairs: median {np.median([r['code'] for r in sp]):.2f} (1 = same lines; the "
                  f"base as is {np.median([r['base_as_is'] for r in sp]):.2f}). Like the numbered badges (D14), the model "
                  f"would otherwise learn rings around unrelated drawings. The illithid Reapply Imperil uses corner sparkles "
                  f"instead and stays as is. Each example: game base, code, game Reapply.",
                  chains,
                  [("A", "In code, out of training",
                    "The Reapply spells leave training (like D14's badges). Make related (7.3) gets a Reapply variant: "
                    "your icon shrunk, nudged down, the game's ring around it (read from your game files, D10), then "
                    "glow and colour as usual."),
                   ("B", "Keep them in training",
                    "Captions say \"reapply\"; the model learns to draw the ring on request, less exactly.")],
                  unit="icons")
    # decision 3: frame families
    F_ = J["frames"]
    A = {}
    show = [f for f in F_ if not f["element"]][:6]
    ex3 = ""
    for f in show:
        for n in f["icons"]:
            if n not in A:
                A[n] = line_art(master(n), S)["AL"] > .5
        frame = np.mean([A[n] for n in f["icons"]], 0) >= FRAME_MIN
        ex3 += (f'<div class=cgroup><div class=chead><b>{e(nm(f["icons"][0]).split(":")[0])}</b> ({len(f["icons"])} icons, '
                f'frame drawn in {f["recall"]:.0%}, {f["share"]:.0%} of the lines)</div><div class=crow>'
                + figure(pil(np.repeat(frame[..., None] * .85, 3, -1)), "the frame", f["family"], 64)
                + "".join(fig(n) for n in f["icons"][:9]) + '</div></div>')
    ne = [f for f in F_ if not f["element"]]
    d3 = decision(3, 3, DECIDED.get(3), len(F_), "Families that keep a frame and swap a symbol: build new members in code?",
                  f"{len(F_)} families draw the same frame in every member and change only what is inside it (each member, "
                  f"left out, draws at least {FRAME_RECALL:.0%} of the frame its siblings share; median "
                  f"{np.median([f['recall'] for f in F_]):.0%}). "
                  f"{len(F_) - len(ne)} vary by element and are D30's series composites already; {len(ne)} more vary "
                  f"something else: legendary actions, Paladin auras, Arcane Shot arrows, Magic Circle's creature types, "
                  f"Contagion's diseases, Eyebite's curses, Mantle of Majesty's commands. Each row: the frame code would keep "
                  f"(lines in {FRAME_MIN:.0%} of the members), then the game's members.",
                  ex3,
                  [("A", "Every frame family in Based on series",
                    "7.5's Based on field lists all frame families. Code keeps the frame exactly (from your game files); "
                    "the new symbol comes from the damage-type library where the family varies by element (D30), else the "
                    "model draws only the inside (inpainting, tested in 5.3), or you draw or stamp it in the editor (D31)."),
                   ("B", "Element series only (D30 as is)",
                    "Other frame families are made by hand in the editor: load a game icon, erase its symbol, draw.")],
                  note=f"Either way the {sum(f['series'] > 1 for f in F_)} frame families split over several series join one "
                       f"series for the training weights (D33, Phase 6): the {lg} legendary actions are {lg} series today, so "
                       f"their frame would be learned {lg} times over."
                       if (lg := next((len(f['icons']) for f in F_ if 'Legendary' in f['family']), 0)) else "", unit="families")
    lede, reply = lede_reply(DECIDED, 3)
    L_ = J["links"]
    grid = lambda ns_: f'<div class=grid>{"".join(fig(n) for n in ns_)}</div>'
    srows = "".join(f'<tr><td>{e(g)}</td><td class=num>{T["classes"][g]}</td><td class=num>{a:.0%}</td><td class=num>{b:.0%}</td></tr>'
                    for g, (a, b) in ns.items())
    motifs = ["Action_Barbarian_Rage_BearTotem", "Spell_Transmutation_EnhanceAbility_BearsEndurance", "Skill_Druid_WildShape_Bear",
              "Action_Ranger_RangersCompanion_Bear", "Action_PactOfTheBlade_Greatsword", "Spell_Evocation_SpiritualWeapon_Greatsword",
              "Spell_Conjuration_ConjureElemental_Fire", "Action_ElementalWildShape_Myrmidon_Fire"]
    dismiss = [n for n in names if re.search(r"Dismiss|_Dismissal", n)]
    cmd = [(f"Spell_Enchantment_Command{c}", f"Action_MantleOfMajesty_{c}") for c in ("Approach", "Drop", "Flee", "Grovel", "Halt")]
    notes = "".join([
        row(len(L_["flyouts"]), "Spell flyouts now count as series", "D33 weights",
            f"A container spell and its options (the flyout: Chromatic Orb's elements, Ranger's Companion's beasts, Perform's "
            f"instruments, Wild Shape's forms) come straight from the stats. Their drawings are related (kappa median "
            f"{L_['flyout_kappa']} vs {L_['random_kappa']} for random pairs), but name and shape links left some split: "
            f"series {OLD['series']['n']} → {SJ['series']['n']} for {SJ['series']['icons']} icons, Reapply X now joins X. "
            f"2.6's tests rerun on the new series: spell type on actions {st_old['verdict']} → {st_new['verdict']}, school "
            f"{old(OLD, 'school|Spell|series')['verdict']} → {sc_new['verdict']}; intent, area, level, cost unchanged."),
        row(len(ns), "Every action source", "table",
            "Nearest drawing from the same source vs that source's share (chance), one icon per series.",
            f'<table class=t><tr><th>Source</th><th>Icons</th><th>Nearest same</th><th>Chance</th></tr>{srows}</table>'),
        row(len(L_["ranged"]), "Ranged twins: the weapon becomes a bow", "caption word",
            f"Every melee / ranged pair is the same composition with the weapon swapped for a bow or arrows (kappa median "
            f"{L_['ranged_kappa']}; one series each, D33). Captions say \"ranged\" (4.2); the editor (D31) can swap the "
            f"weapon strokes by hand.", "".join(f'<div class=twin>{grid([a, b])}</div>' for a, b in L_["ranged"][:10])),
        row(len(dismiss), "Dismiss icons: the thing dissolving into sparkles", "caption word",
            "A convention, not a stamp (each draws its own subject): captions say \"dismiss\".", grid(dismiss)),
        row(len(motifs), "No shared motifs beyond damage symbols", "checked",
            "Animals, weapons and elements are redrawn for every series: four different bears (Rage totem, Enhance Ability, "
            "Wild Shape, Ranger's Companion), two greatswords, two fire elementals. Only the damage-type symbols repeat "
            "(D28).", grid(motifs)),
        row(L_["using_groups"], "Stat inheritance is mechanics", "checked",
            f"Spells built on the same template (`using`) are drawn alike only by chance (kappa median {L_['using_kappa']}, "
            f"random {L_['random_kappa']}): Target_MainHandAttack carries Divine Strike, manoeuvres and dipped weapons."),
        row(len(cmd), "Same effect, new drawing", "checked",
            "The Command spell and the Bard's Mantle of Majesty give the same commands but are drawn anew.",
            "".join(f'<div class=twin>{grid([a, b])}</div>' for a, b in cmd)),
        row(2, "Sources: game data first, wiki second", "method",
            "Class and subclass: Progressions.lsx (spell lists, passive lists, passives' UnlockSpell). Items: weapons "
            "and gear that unlock an action (MAG_ = magic item, plain weapons = weapon action). Names: Monster, EndGameAlly, "
            "Legendary, Mag, WildMagic, class names, wild-shape beasts. bg3.wiki (Battle_Master): the 21 manoeuvres, whose "
            "subclass choices the lists miss. Legendary actions are boss abilities (several only in Honour mode) and share "
            "one gold frame.")])
    body = (f'<style>.m{{color:var(--mute);font-size:12px}}.chain figure,.crow figure{{width:72px}}</style>'
            f'<p class=lede>Phase 2.7 (your request): connections between icons beyond shared drawings (2.5) and series '
            f'(2.6), from the game\'s own data (spell flyouts, class progressions, item unlocks, stat inheritance) and '
            f'bg3.wiki. {lede}</p>{d1}{d2}{d3}{reply}<h2 class=sec>Reference</h2><p class=secsub>Click a row to open it.</p>{notes}')
    (D / "links.html").write_text(page("Icon connections", body), encoding="utf-8")
    log(f"[2.7] wrote {D / 'links.html'}")


def check():
    """drawn shapes: a 'reapply' (shape shrunk to .72 + two arcs) is found at its scale and rebuilt from ANOTHER pair's
    ring; a frame + swapped symbols is a frame family, unrelated drawings are not; reapply names pair up"""
    W = (255, 230, 200, 255)

    def draw(*fs, s=1.0):
        im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for f in fs:
            f(d, lambda *p: [256 + (v - 256) * s for v in p])
        return np.asarray(im).astype(np.float64) / 255
    cross = lambda d, t: (d.line(t(150, 150, 362, 362), fill=W, width=24), d.line(t(150, 362, 362, 150), fill=W, width=24))
    tri = lambda d, t: d.polygon(t(256, 120, 400, 380, 112, 380), outline=W, width=24)
    arcs = lambda d, t: (d.arc((40, 40, 472, 472), 120, 240, fill=W, width=22), d.arc((40, 40, 472, 472), -60, 60, fill=W, width=22))
    la = lambda x: line_art(x, S)
    pairs = [(la(draw(f)), la(draw(lambda d, t, f=f: f(d, lambda *p: t(*[256 + (v - 256) * .72 for v in p])), arcs)))
             for f in (cross, tri)]
    fits = [reapply_fit(b, r) for b, r in pairs]
    assert all(abs(s - .72) <= .05 for s, _, _ in fits), [f[:2] for f in fits]
    s, dy, _ = fits[0]
    code = reapply(pairs[0][0], s, dy, fits[1][2])                 # cross rebuilt with the triangle pair's ring
    kc, kb = k2(code["AL"], pairs[0][1]["AL"]), k2(pairs[0][0]["AL"], pairs[0][1]["AL"])
    assert kc >= .85 and kc > kb + .3, (kc, kb)
    box = lambda d, t: d.rectangle((60, 60, 452, 452), outline=W, width=22)
    syms = [cross, tri, lambda d, t: d.ellipse(t(170, 170, 342, 342), outline=W, width=22),
            lambda d, t: d.line(t(256, 140, 256, 372), fill=W, width=24)]
    fam = {i: line_art(draw(box, f, s=.6), S)["AL"] > .5 for i, f in enumerate(syms)}
    odd = {i: line_art(draw(f), S)["AL"] > .5 for i, f in enumerate(syms)}
    fr, un = frame_stats(list(fam), fam), frame_stats(list(odd), odd)
    assert fr[0] >= .95 and FRAME_SHARE <= fr[2] <= .9 and un[0] < .5, (fr, un)
    assert reapply_pairs(["Spell_A_ReapplyHex", "Spell_A_Hex", "Spell_B_X_Reapply", "Spell_B_X", "Spell_C_Reapply"]) == \
        [("Spell_A_Hex", "Spell_A_ReapplyHex"), ("Spell_B_X", "Spell_B_X_Reapply")]
    log(f"[2.7] check passed: reapply scales {[round(f[0], 3) for f in fits]}, cross rebuilt with the triangle's ring "
        f"{kc:.2f} (as is {kb:.2f}); frame family recall {fr[0]:.2f} share {fr[2]:.2f}, unrelated {un[0]:.2f}")


if __name__ == "__main__":
    {"run": run, "report": lambda: report(), "check": lambda: check()}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
