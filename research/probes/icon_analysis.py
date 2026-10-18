"""Quick data probe: does BG3 icon colour/background follow stats (VerbalIntent, DamageType, school, type)?
1) parse vanilla stats with `using` inheritance, 2) per controller icon: dominant glyph hue,
3) per hotbar atlas icon: nearest of the 28 icon_bg_png backgrounds, 4) cross-tabs.
Writes icons.csv to the out dir. Logs milestones."""
import re, sys, csv, colorsys
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
from PIL import Image

MT = (Path.home() / r"Documents\BG3 Modding\BG3 Modders Multitool")
U = MT / "UnpackedData"
G = U / "GUI/Public/Game/GUI/Assets"
BR = MT / "UnpackedMods/BaseGameReference"
OUT = Path(sys.argv[1])
STAT_DIRS = [BR / "Shared_BaseGameReference/Public/Shared/Stats/Generated/Data",
             BR / "Shared_BaseGameReference/Public/SharedDev/Stats/Generated/Data",
             BR / "GustavX_BaseGameReference/Public/GustavX/Stats/Generated/Data"]

# ---------- 1) stats ----------
raw = {}
for d in STAT_DIRS:
    for f in sorted(d.glob("*.txt")):
        cur = None
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if m := re.match(r'new entry "([^"]+)"', line):
                cur = raw.setdefault(m.group(1), {"_file": f.name, "_data": {}})
                cur["_file"] = f.name
            elif cur is None:
                continue
            elif m := re.match(r'type "([^"]+)"', line):
                cur["_type"] = m.group(1)
            elif m := re.match(r'using "([^"]+)"', line):
                cur["_using"] = m.group(1)
            elif m := re.match(r'data "([^"]+)" "(.*)"', line):
                cur["_data"][m.group(1)] = m.group(2)

def resolved(name, depth=0):
    e = raw[name]
    base = resolved(e["_using"], depth + 1) if e.get("_using") in raw and depth < 20 else {}
    return {**base, **e["_data"]}

entries = {n: {**resolved(n), "_type": raw[n].get("_type", "?")} for n in raw}
print(f"[1] stats entries: {len(entries)}", Counter(e["_type"] for e in entries.values()).most_common(8))

by_icon = defaultdict(list)
for n, e in entries.items():
    if e.get("Icon"):
        by_icon[e["Icon"]].append(n)

def icon_props(icon):
    """Majority vote over entries using this icon (spells first)."""
    es = [entries[n] for n in by_icon.get(icon, [])]
    es.sort(key=lambda e: e["_type"] != "SpellData")
    pick = lambda k: Counter(e.get(k, "") for e in es if e.get(k)).most_common(1)[0][0] if any(e.get(k) for e in es) else ""
    cost = pick("UseCosts")
    cost = ("Bonus" if "BonusActionPoint" in cost else "Reaction" if "ReactionActionPoint" in cost
            else "Action" if "ActionPoint" in cost else "Other" if cost else "")
    return {"n_entries": len(es), "types": "/".join(sorted({e["_type"] for e in es})),
            "cost": cost, "StyleGroup": pick("SpellStyleGroup"), "IsWeapon": "Weapon" if "IsMelee" in pick("SpellFlags") or "Weapon" in pick("SpellFlags") else "",
            "VerbalIntent": pick("VerbalIntent"), "DamageType": pick("DamageType"),
            "SpellSchool": pick("SpellSchool"), "SpellType": pick("SpellType"),
            "Level": pick("Level"), "example": by_icon[icon][0] if es else ""}

# ---------- 2) glyph hue ----------
def glyph_colour(im):
    a = np.asarray(im.convert("RGBA")).astype(float) / 255
    m = a[:, :, 3] > 0.5
    rgb = a[:, :, :3][m]
    if len(rgb) < 30:
        return None
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in rgb[:: max(1, len(rgb) // 3000)]])
    sat = hsv[(hsv[:, 1] > 0.35) & (hsv[:, 2] > 0.35)]
    white = float(((hsv[:, 1] < 0.2) & (hsv[:, 2] > 0.8)).mean())
    if len(sat) < 20:
        return {"hue": -1, "sat_frac": len(sat) / len(hsv), "white": white}
    hist, _ = np.histogram(sat[:, 0] * 360, bins=24, range=(0, 360), weights=sat[:, 1] * sat[:, 2])
    k = int(hist.argmax())
    return {"hue": k * 15 + 7.5, "sat_frac": len(sat) / len(hsv), "white": white}

def hue_name(h):
    if h < 0: return "achromatic"
    for lim, nm in [(15, "red"), (40, "orange"), (65, "gold"), (160, "green"), (200, "cyan"),
                    (250, "blue"), (280, "violet"), (330, "magenta"), (345, "pink"), (361, "red")]:
        if h < lim: return nm

# ---------- 3) hotbar background class ----------
bgs = {p.stem.replace("_bg", ""): np.asarray(Image.open(p).convert("RGB").resize((64, 64), Image.LANCZOS)).astype(float)
       for p in sorted((G / "ControllerUIIcons/icon_bg_png").glob("*.DDS"))}
maps = {}
for lsx in [U / "GUI/Public/Shared/GUI/Icons_Skills.lsx", U / "GUI/Public/SharedDev/GUI/Icons_Skills.lsx"]:
    t = lsx.read_text(encoding="utf-8")
    dds = U / "Icons" / lsx.parent.parent.relative_to(U / "GUI") / re.search(r'id="Path" type="string" value="([^"]+)"', t).group(1)
    for m in re.finditer(r'MapKey" type="FixedString" value="([^"]+)"/>\s*<attribute id="U1" type="float" value="([^"]+)"/>\s*<attribute id="U2" type="float" value="([^"]+)"/>\s*<attribute id="V1" type="float" value="([^"]+)"/>\s*<attribute id="V2" type="float" value="([^"]+)"', t):
        maps.setdefault(m.group(1), (dds, *map(float, m.groups()[1:])))
atl = {}
def hotbar(icon):
    if icon not in maps: return None
    dds, u1, u2, v1, v2 = maps[icon]
    if dds not in atl: atl[dds] = Image.open(dds).convert("RGB")
    A = atl[dds]
    return A.crop((round(u1 * A.width), round(v1 * A.height), round(u2 * A.width), round(v2 * A.height))).resize((64, 64))

def bg_class(hb, ctl):
    h = np.asarray(hb).astype(float)
    a = np.asarray(ctl.convert("RGBA").resize((64, 64), Image.LANCZOS)).astype(float)[:, :, 3] / 255 if ctl else np.zeros((64, 64))
    ring = np.zeros((64, 64), bool); ring[:8] = ring[-8:] = True; ring[:, :8] = ring[:, -8:] = True
    m = (a < 0.03) & ring  # ponytail: frame ring only - the grey centres of the framed bgs are near-identical
    if m.sum() < 120: m = ring
    d = {k: float(np.abs(h - b)[m].mean()) for k, b in bgs.items()}
    best = sorted(d, key=d.get)
    return best[0], d[best[0]], d[best[1]] - d[best[0]]

# ---------- run ----------
rows = []
ctl_dir = G / "ControllerUIIcons/skills_png"
names = sorted({p.stem for p in ctl_dir.glob("*.DDS")} | set(maps))
print(f"[2] icons to analyse: {len(names)} (controller files {len(list(ctl_dir.glob('*.DDS')))}, atlas keys {len(maps)})")
for i, icon in enumerate(names):
    cp = ctl_dir / f"{icon}.DDS"
    ctl = Image.open(cp) if cp.exists() else None
    col = glyph_colour(ctl) if ctl else None
    hb = hotbar(icon)
    bgc = bg_class(hb, ctl) if hb else ("", -1, -1)
    rows.append({"icon": icon, "prefix": icon.split("_")[0], "has_ctl": bool(ctl), "has_tip": (G / "Tooltips/Icons" / f"{icon}.DDS").exists(),
                 "in_atlas": icon in maps, **icon_props(icon),
                 "hue": col["hue"] if col else "", "hue_name": hue_name(col["hue"]) if col else "",
                 "sat_frac": round(col["sat_frac"], 2) if col else "", "white": round(col["white"], 2) if col else "",
                 "bg": bgc[0], "bg_dist": round(bgc[1], 1), "bg_margin": round(bgc[2], 1)})
    if i % 400 == 0: print(f"    ... {i}/{len(names)}")
with open(OUT / "icons.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
print(f"[3] wrote {OUT / 'icons.csv'} rows={len(rows)}; with stats={sum(1 for r in rows if r['n_entries'])}")

def xtab(rows, rk, ck, title, min_n=3):
    cnt = defaultdict(Counter)
    for r in rows:
        if r[rk] != "" and r[ck] != "": cnt[r[rk]][r[ck]] += 1
    print(f"\n== {title}")
    for k, c in sorted(cnt.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        if n >= min_n:
            print(f"  {k or '(none)':28s} n={n:4d}  " + ", ".join(f"{v} {100*x//n}%" for v, x in c.most_common(5)))

ctl_rows = [r for r in rows if r["has_ctl"] and r["hue_name"]]
xtab([r for r in ctl_rows if r["types"].startswith("SpellData") or "SpellData" in r["types"]], "VerbalIntent", "hue_name", "SPELL icons: VerbalIntent -> glyph hue")
xtab([r for r in ctl_rows if "SpellData" in r["types"] and r["VerbalIntent"] == "Damage"], "DamageType", "hue_name", "DAMAGE spells: DamageType -> glyph hue")
xtab([r for r in ctl_rows if "SpellData" in r["types"]], "SpellSchool", "hue_name", "SPELL icons: SpellSchool -> glyph hue")
xtab(ctl_rows, "prefix", "hue_name", "icon prefix -> glyph hue")
xtab([r for r in rows if r["bg"]], "prefix", "bg", "icon prefix -> hotbar background (nearest of 28)")
xtab([r for r in rows if r["bg"] and r["prefix"] == "PassiveFeature"], "hue_name", "bg", "PASSIVE icons: glyph hue -> hotbar background")
xtab([r for r in rows if r["bg"] and r["prefix"] in ("Action", "Spell")], "VerbalIntent", "bg", "Spell_/Action_ icons: VerbalIntent -> hotbar background")
act = [r for r in rows if r["bg"] and r["prefix"] == "Action"]
xtab(act, "cost", "bg", "Action_ icons: UseCosts -> hotbar background")
xtab(act, "VerbalIntent", "bg", "Action_ icons: VerbalIntent -> hotbar background")
xtab(act, "hue_name", "bg", "Action_ icons: glyph hue -> hotbar background")
xtab([r for r in rows if r["bg"] and r["prefix"] == "Spell"], "cost", "bg", "Spell_ icons: UseCosts -> hotbar background")
print("\nbg margin (2nd best - best) quantiles:", np.percentile([r["bg_margin"] for r in rows if r["bg"]], [5, 25, 50]).round(1))
