"""Dataset review -> data/anomalies.html (self-contained; Larian thumbnails, so it stays local).
Decisions for the user first, then what is already handled, then notes for later phases.
    python -m iconkit.report      (~8 min when masters changed; image checks cached in data/image_checks.npz)"""
from collections import Counter, defaultdict
import numpy as np
from PIL import Image
from . import paths as P
from .page import e, figure, row, page, lede_reply, decision as _decision
from .extract import D, SPELL_LIKE, EXCLUDED, read_jsonl, parse_stats, rgba, resize, icon_fade, log
from .fade import bottom_fade

DECIDED = {1: "A", 2: "A", 3: "A"}                  # user, 2026-10-14 (plan D14-D16); None = still open
rows = read_jsonl(D / "meta.jsonl")
by = {r["icon"]: r for r in rows}
hold = set((D / "holdout.txt").read_text().split())
train = set((D / "train.txt").read_text().split())
masters = [r for r in rows if (D / "masters" / f"{r['icon']}.png").exists()]
v1 = [r for r in masters if r["family"] in SPELL_LIKE]
v1set = {r["icon"] for r in v1}


# ---------- per-master image checks (vignette, controller round trip, border, 24 px vector for twins)
def image_checks():
    names = [r["icon"] for r in masters]
    cache = D / "image_checks.npz"
    newest = max((D / "masters" / f"{n}.png").stat().st_mtime for n in names)
    if cache.exists() and cache.stat().st_mtime > newest:
        z = np.load(cache)
        if list(z["names"]) == names:
            return {n: {k: z[k][i] for k in ("vig", "ctl_err", "border", "vec")} for i, n in enumerate(names)}
    mask, out = bottom_fade(380), defaultdict(list)
    pm = lambda a: np.dstack([a[..., :3] * a[..., 3:], a[..., 3]])
    for i, n in enumerate(names):
        m = Image.open(D / "masters" / f"{n}.png")
        t, c = rgba(P.tooltip(n)), rgba(P.controller(n), 380)
        f, sup = icon_fade(t[..., 3], c[..., 3], mask)[20:150], c[20:150, :, 3] > .3
        out["vig"].append(float(f[sup].mean()) if sup.any() else 1.0)
        o = np.asarray(resize(m, 144)).astype(np.float32) / 255
        out["ctl_err"].append(float(np.abs(pm(o) - pm(rgba(P.controller(n)))).mean() * 255))
        a = np.asarray(m).astype(np.float32)[..., 3] / 255
        out["border"].append(float((np.concatenate([a[:4].ravel(), a[-4:].ravel(), a[:, :4].ravel(), a[:, -4:].ravel()]) > .5).mean()))
        out["vec"].append(pm(np.asarray(resize(m, 24)).astype(np.float32) / 255).ravel())
        if i % 300 == 0:
            log(f"    image checks {i}/{len(names)}")
    np.savez(cache, names=np.array(names), **{k: np.array(v) for k, v in out.items()})
    return {n: {k: out[k][i] for k in out} for i, n in enumerate(names)}


img = image_checks()
st = parse_stats()
log("[report] image checks + stats ready")

# ---------- twins: near-identical art under several names (union-find over RMS < 15/255 at 24 px)
names = list(img)
V = np.stack([img[n]["vec"] for n in names])
sq = (V ** 2).sum(1)
dist = np.sqrt(np.maximum(sq[:, None] + sq[None, :] - 2 * V @ V.T, 0) / V.shape[1])
parent = list(range(len(names)))


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


for i, j in zip(*np.where(np.triu(dist < .06, 1))):
    parent[find(i)] = find(j)
tw = defaultdict(list)
for i, n in enumerate(names):
    tw[find(i)].append(n)
twins = [sorted(g) for g in tw.values() if len(g) > 1 and any(n in v1set for n in g)]
leaks = [g for g in twins if {n in hold for n in g if n in hold or n in train} == {True, False}]  # badge variants are in neither

# ---------- colour groups (damage type for Damage, else intent) and their outliers
BINS = [(15, "red"), (40, "orange"), (65, "gold"), (160, "green"), (200, "cyan"), (250, "blue"),
        (280, "violet"), (330, "magenta"), (345, "pink"), (361, "red")]
hue_name = lambda h: next(nm for lim, nm in BINS if h < lim)
hdist = lambda a, b: abs((a - b + 180) % 360 - 180)
grp = defaultdict(list)
for r in v1:
    k = r["DamageType"] if r["VerbalIntent"] == "Damage" and r["DamageType"] else r["VerbalIntent"]
    if k and r.get("hue") is not None:
        grp[k].append(r)
cgroups = []                                        # (group, mean hue, typical, outliers)
for k, rs in grp.items():
    if len(rs) >= 8:
        h = np.deg2rad([r["hue"] for r in rs])
        mean = float(np.rad2deg(np.arctan2(np.sin(h).mean(), np.cos(h).mean())) % 360)
        off = [r for r in rs if hdist(r["hue"], mean) > 60]
        if off:
            usual = sorted((r for r in rs if r not in off and not r["numeral_badge"]),
                           key=lambda r: (hdist(r["hue"], mean), r["icon"]))[:3]
            cgroups.append((k, mean, usual, off))
cgroups.sort(key=lambda g: -len(g[3]))
colour_out = [r for *_, off in cgroups for r in off]

# ---------- the three decisions
num = [r for r in v1 if r["numeral_badge"]]
chains = defaultdict(list)
for r in num:
    chains[r["variant_group"]].append(r["icon"])
order = {"Spell": 0, "Skill": 1, "Action": 2}
chains = sorted(((g, sorted(vs, key=lambda s: int(s.rsplit("_", 1)[1]))) for g, vs in chains.items() if g in img),
                key=lambda c: (order[c[0].split("_")[0]], c[0]))
recol = sorted((n for n in v1set if img[n]["ctl_err"] > 10), key=lambda n: -img[n]["ctl_err"])
recol_act = [n for n in recol if n.startswith("Action_")]

# ---------- HTML helpers
def fig(n, cap=None, size=64, path=None):
    r = by[n]
    lab = " · ".join(x for x in (r["VerbalIntent"], r["DamageType"]) if x)
    tip = "\n".join(x for x in (n, r["name"], lab, "test set" if n in hold else "") if x)
    return figure(path or D / "masters" / f"{n}.png", cap if cap is not None else r["name"] or n.split("_", 1)[1], tip, size, n in hold)


def grid(icons):
    return f'<div class=grid>{"".join(fig(n) for n in icons)}</div>'


def decision(i, *a, **k):
    return _decision(i, 3, DECIDED.get(i), *a, **k)


# ---------- decision 1: numbered variants
ex1 ="".join(f'<div class=chain>{fig(g, "original")}<span class=arrow>→</span>'
              f'{"".join(fig(v, "#" + v.rsplit("_", 1)[1]) for v in vs[:4])}{"<span class=more>+%d</span>" % (len(vs) - 4) if len(vs) > 4 else ""}</div>'
              for g, vs in chains[:6])
d1 = decision(1, len(num), "Should icons with a painted number badge be used for training?",
              f"{len(num)} icons are an existing icon with a number painted on (II, III, 1 to 6), used for upgraded or "
              "counted versions of a spell. Image models copy details like this, and they draw numbers badly.",
              ex1,
              [("A", "Leave them out", f"All {len(num)} stay out of training and the test set. The model never "
                "adds a badge on its own. If you ever need one, the app can stamp a badge on in code."),
               ("B", "Keep them, captioned", "Captioned as having a numeral badge, so you can ask for one. Risk: badges or "
                "garbled numbers can appear when you did not ask for them.")],
              more=f'<details class=all><summary>Show all {len(num)}</summary>{grid(r["icon"] for r in num)}</details>')

# ---------- decision 2: controller recolour
ex2 = "".join(f'<div class=pair>{fig(n, "PC")}{fig(n, "Controller", path=P.controller(n))}'
              f'<div class=pname>{e(by[n]["name"] or n)}</div></div>' for n in recol)
rest = [by[n]["name"] or n for n in recol if n not in recol_act]
d2 = decision(2, len(recol), "Should controller icons keep the PC colours?",
              f"For {len(recol_act)} actions, mostly weapon attacks, the game ships a white or silver controller icon while the "
              f"PC hotbar and tooltip are red or orange. Also different on controller: {', '.join(rest)}.",
              ex2,
              [("A", "Same colours as PC", "One look on every screen and nothing extra to build. Generated icons will not "
                f"copy the white controller style these {len(recol)} vanilla icons have."),
               ("B", "Copy the game's controller recolour", "Generated weapon actions get a white or silver controller icon. "
                "Needs a rule for which icons get it and a recolour step in the exporter.")],
              note="Training is the same either way: the clean icons keep the PC colours.")

# ---------- decision 3: colour outliers
mix = []
for k, mean, usual, off in cgroups[:2]:
    c = Counter(hue_name(r["hue"]) for r in off)
    mix.append(f"{len(off)} {k} icons ({', '.join(f'{v} {nm}' for nm, v in c.most_common())})")
ex3 = "".join(f'<div class=cgroup><div class=chead><span class=sw style="background:hsl({mean:.0f} 70% 55%)"></span>'
              f'<b>{e(k)}</b><span>usually {hue_name(mean)}</span><span class=off>{len(off)} off-colour</span></div>'
              f'<div class=crow><div class=usual>{"".join(fig(r["icon"], "usual") for r in usual)}</div>'
              f'<div class=offs>{"".join(fig(r["icon"]) for r in off)}</div></div></div>' for k, mean, usual, off in cgroups)
o_tr, n_train = sum(r["icon"] in train for r in colour_out), len(train)
d3 = decision(3, len(colour_out), "Should icons that break the usual colour rule stay in training?",
              "Each kind of spell has a usual colour: " + ", ".join(f"{k} is usually {hue_name(m)}" for k, m, *_ in cgroups[:2])
              + f", and so on. {len(colour_out)} icons are "
              f"more than 60° of hue away from the usual colour of their group, mainly {' and '.join(mix)}.",
              ex3,
              [("A", "Keep them", "They are real game art. Phase 2 looks for what explains them (weapon and physical actions "
                "may be orange whatever their intent) and builds that into the colour rules."),
               ("B", "Drop the ones Phase 2 can't explain", "A stricter colour rule, so picking an intent gives a more "
                f"predictable colour. Loses up to {o_tr} training icons ({100 * o_tr / n_train:.0f}%).")])

# ---------- already handled / for later
vig = sorted((n for n in v1set if img[n]["vig"] < .9), key=lambda n: img[n]["vig"])
conf = [r for r in v1 if len(Counter(st[x].get("VerbalIntent") for x in r["entries"]
                                      if st[x]["_type"] == "SpellData" and st[x].get("VerbalIntent"))) > 1]
dmg = [r["icon"] for r in v1 if r["VerbalIntent"] == "Damage" and not r["DamageType"]]
noname = [r["icon"] for r in v1 if r["entries"] and (not r["name"] or "|" in r["name"])]
nomaster = [r["icon"] for r in rows if r["family"] in SPELL_LIKE and r["icon"] not in img]
handled = "".join([
    row("✓", "Labels taken from unrelated spells", "fixed in extraction",
        "Several spells can share one icon. Names and labels now come from the spell that matches the icon's own name, and "
        "labels only from spells that agree on its intent (Warding Flare was named 'Bomb', Jump was 'Utility · Bludgeoning')."),
    row(len(vig), "Game tooltip uses a vignette", "not copied",
        "The game also dims the top and sides of these tooltips. Ours use the one clean bottom fade.", grid(vig)),
    row(sum(map(len, twins)), "Near-identical twins", "kept" if not leaks else f"{len(leaks)} split across train/test: fix",
        f"{len(twins)} groups of the same art with a small change (bonus-action copies, numbered variants). "
        + ("None is split between training and test." if not leaks else "Some are split between training and test."),
        "".join(f"<div class=twin>{grid(g)}</div>" for g in twins)),
    row(len(conf), "Spells sharing an icon disagree on intent", "majority vote", "e.g. Jump: 26 entries say Utility, 4 say Damage.",
        grid(r["icon"] for r in conf)),
    row(len(dmg), "Damage intent but no damage type", "left empty", "No damage type in the stats and none in the damage formula.", grid(dmg)),
    row(len(noname), "No usable name", "caption by hand", "Stats exist but the display name is empty or debug text.", grid(noname)),
    row(len(nomaster), "No clean icon possible", "skipped",
        f"{sum(not (by[n]['has_tooltip'] or by[n]['has_controller']) for n in nomaster)} exist only as 64 px hotbar art with "
        "the background baked in, the rest lack a tooltip or controller version: " + ", ".join(nomaster) + "."),
])
nostats = [r["icon"] for r in v1 if not r["entries"]]
nointent = [r["icon"] for r in v1 if r["entries"] and not r["VerbalIntent"]]
grey = [r["icon"] for r in v1 if r.get("hue") is None]
dark = [r["icon"] for r in v1 if r["dark_fill"]]
two = [r["icon"] for r in v1 if r["multi_hue"]]
edge = sorted((n for n in v1set if img[n]["border"] > .1), key=lambda n: -img[n]["border"])
thin = Counter({f"{v} ({k})": c for k in ("DamageType", "SpellType") for v, c in Counter(r[k] for r in v1 if r[k]).items() if c < 15})
later = "".join([
    row(len(nostats), "No stats entry", "captions by hand, Phase 4",
        "No spell, status or passive uses these icons, so there is no intent, name or description.", grid(nostats)),
    row(len(nointent), "Stats but no intent", "captions by hand, Phase 4",
        "Mostly reactions, which have no intent field in the game data.", grid(nointent)),
    row(len(grey), "White or grey, no main colour", "own style in Phase 2",
        "Basic actions (Dash, Hide, Shove, Throw) and Perform songs are drawn white or grey.", grid(grey)),
    row(len(dark), "Dark filled shapes", "kept, tagged", "Filled shapes instead of pure glowing strokes.", grid(dark)),
    row(len(edge), "Art touches the edge", "kept", "Full-bleed art: the glyph or glow runs into the frame.", grid(edge)),
    row(len(two), "Two separate colours", "kept, tagged", "A colour 'snap' would break these.", grid(two)),
    row(sum(thin.values()), "Rare labels (under 15 icons)", "colour rules lean on the game's UI palette",
        ", ".join(f"{k}: {v}" for k, v in thin.most_common()) + "."),
])

LEDE, REPLY = lede_reply(DECIDED, 3)
page = page("Dataset review", f"""<p class=lede>{len(v1):,} icons for v1 (spells, actions, skills). {LEDE} Everything below them is already
handled or a note for later. Hover a picture for its file name and labels; a gold outline marks a test-set icon.</p>
{d1}{d2}{d3}
{REPLY}
<h2 class=sec>Already handled</h2><p class=secsub>No action needed. Click a row to see the icons.</p>{handled}
<h2 class=sec>Notes for later phases</h2><p class=secsub>No action needed now.</p>{later}""")
(D / "anomalies.html").write_text(page, encoding="utf-8")
log(f"[report] wrote {D / 'anomalies.html'} ({len(page) / 1e6:.1f} MB): decisions {len(num)} badge / {len(recol)} recolour / "
    f"{len(colour_out)} colour; handled vignette {len(vig)}, twins {sum(map(len, twins))} (leaks {len(leaks)}), conflicts {len(conf)}, "
    f"no-type {len(dmg)}, no-name {len(noname)}, hotbar-only {len(nomaster)}; later no-stats {len(nostats)}, no-intent {len(nointent)}, "
    f"grey {len(grey)}, dark {len(dark)}, edge {len(edge)}, two-hue {len(two)}")
