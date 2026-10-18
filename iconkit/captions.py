"""Phase 4 captions. 4.1: 16-icon contact sheets (the master over the hotbar dark | the line art the model learns, D25:
the lines' light over black, glyph.split EL) -> Claude writes each icon's motif (what is drawn, layout; no colour, glow,
school, spell type, level or cost words) into iconkit/motifs.jsonl (in git: hand work, no Larian art). 4.2: the template
    bg3 <family> icon, <source (actions)>, <ranged | dismiss>, <intent>, <damage type> damage, <motif>. <description>
(D32, D34; empty fields left out) -> data/captions.jsonl (the game's descriptions are Larian text: data/, not git).
    python -m iconkit.captions sheets [OUT_DIR] [@list.txt | ICON ...]  -> OUT_DIR/NNN.png + index.txt (default: every
                                                    train + holdout icon by name, into the scratchpad; Larian art, no git)
    python -m iconkit.captions build   -> data/captions.jsonl (every train + holdout icon needs a motif)
    python -m iconkit.captions report  -> data/captions.html (30 captions to spot-check, local: Larian art)
    python -m iconkit.captions check   -> self-check of the template on made-up rows"""
import json, re, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from .extract import D, read_jsonl, write_jsonl, log
from .glyph import master, split
from .grammar import DARK
from .hotbar import kind

T, COLS, PER = 176, 4, 16                  # tile px, icons per row, icons per sheet
MOTIFS = Path(__file__).with_name("motifs.jsonl")
FAMILY = {"spell": "spell", "action": "action", "illithid": "illithid power"}
SOURCE = {"Legendary": "legendary action", "several classes": "", "Illithid": ""}   # else the label in lower case
# words D18 / D25 / D32 / D34 keep out of captions: colour, glow, school, level, cost. A description sentence holding one
# is dropped whole (deleting the word leaves broken grammar); the motifs are written without them and checked here too
BANNED = re.compile(r"\b(red|green|blue|yellow|orange|purple|violet|pink|white|black|gold|golden|silver|crimson|grey|gray|"
                    r"glow\w*|shin\w*|bright\w*|luminous|colou?r\w*|abjuration|conjuration|divination|enchantment|evocation|"
                    r"illusion|necromancy|transmutation|school|cantrip|level|slot|bonus action|reaction|concentration|"
                    r"ritual|projectile|shout|zone)\b", re.I)          # "cone" stays: a drawn sweep is shape (2.7)


def describe(s):
    """the game's description: sentences with a banned word or a number placeholder ([1]: cutting it out left "and has.")
    dropped"""
    keep = [x for x in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", s or "").strip())
            if x and not BANNED.search(x) and not re.search(r"\[\d+\]|\d+d\d+", x)]
    return " ".join(keep)


def caption(n, motif, r, src, ranged=False):
    """one icon -> its caption (the 4.2 template, empty fields left out)"""
    k = kind(n)
    s = SOURCE.get(src, src.lower()) if k == "action" else ""
    dt = r.get("DamageType", "")
    tags = [f"bg3 {FAMILY[k]} icon", s, "ranged" if ranged else "", "dismiss" if re.search(r"Dismiss", n) else "",
            (r.get("VerbalIntent") or "").lower(), f"{dt.lower()} damage" if dt else "", motif.strip().rstrip(".")]
    d = describe(r.get("description"))
    return ", ".join(t for t in tags if t) + "." + (f" {d}" if d else "")


def build():
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    L = json.loads((D / "links.json").read_text(encoding="utf-8"))
    ranged = {b for _, b in L["links"]["ranged"]}
    mot = {r["icon"]: r["motif"] for r in read_jsonl(MOTIFS)}
    names = sorted(set((D / "train.txt").read_text().split()) | set((D / "holdout.txt").read_text().split()))
    miss = [n for n in names if n not in mot]
    bad = {n: m for n, m in mot.items() if BANNED.search(m)}
    assert not miss and not bad, (f"{len(miss)} icons without a motif: {miss[:8]}", bad)
    out = [{"icon": n, "motif": mot[n], "caption": caption(n, mot[n], rows[n], L["sources"].get(n, ""), n in ranged)}
           for n in names]
    write_jsonl(D / "captions.jsonl", out)
    w = [len(o["caption"].split()) for o in out]
    log(f"[4.2] {len(out)} captions -> {D / 'captions.jsonl'} (words: median {int(np.median(w))}, max {max(w)})")


def report(n=30):
    """spot-check page data/captions.html (local: Larian art): n captions drawn by kind (seed 0), each beside its icon and
    the line art the model learns from"""
    import random
    from .page import e, src, page
    C = read_jsonl(D / "captions.jsonl")
    hold = set((D / "holdout.txt").read_text().split())
    rng, pick = random.Random(0), []
    for k, m in (("action", 16), ("spell", 11), ("illithid", 3)):
        pick += rng.sample([c for c in C if kind(c["icon"]) == k], m)
    keep, rows = [], ""
    for i, c in enumerate(pick, 1):
        a, b = tiles(c["icon"])
        keep += [a, b]
        rows += (f'<div class=cap><span class=no>{i}</span><img src="{src(a, 128)}" width=128 height=128 alt="">'
                 f'<img src="{src(b, 128)}" width=128 height=128 alt=""><div><div class=nm>{e(c["icon"])}'
                 f'{" · test set" if c["icon"] in hold else ""}</div><p>{e(c["caption"])}</p></div></div>')
    css = ('<style>.cap{display:grid;grid-template-columns:32px 128px 128px 1fr;gap:12px;align-items:start;background:var(--card);'
           'border:1px solid var(--line);border-radius:10px;padding:10px;margin:0 0 10px}.cap img{border-radius:6px}'
           '.no{font-weight:700;color:var(--accent);font-size:18px;text-align:right}.nm{color:var(--mute);font-size:12px}'
           '.cap p{margin:4px 0 0}@media (max-width:640px){.cap{grid-template-columns:28px 1fr 1fr}.cap>div{grid-column:1/-1}}</style>')
    body = (f'{css}<p class=lede>Phase 4: {len(pick)} of {len(C)} captions, drawn at random (16 actions, 11 spells, 3 illithid '
            f'powers). Each: the icon over the hotbar dark, the grey line art the model learns from, then its caption. Template: '
            f'<code>bg3 &lt;family&gt; icon, &lt;source (actions)&gt;, &lt;intent&gt;, &lt;damage type&gt; damage, &lt;motif&gt;. '
            f'&lt;game description&gt;</code>; no colour, glow, school, spell type, level or cost words.</p>{rows}'
            f'<div class=reply>Reply in chat with the numbers that read wrong and what is off, for example '
            f'<code>4: it is a mace, not a hammer</code>, or <code>all fine</code>.</div>')
    (D / "captions.html").write_text(page("Caption spot-check", body), encoding="utf-8")
    log(f"[4.2] wrote {D / 'captions.html'}")


def check():
    r = {"VerbalIntent": "Damage", "DamageType": "Fire",
         "description": "Hurl a mote of fire. It deals [1] and has [2]. Costs a spell slot."}
    c = caption("Action_X_Ranged", "a flaming arrow", r, "Ranger", ranged=True)
    assert c == "bg3 action icon, ranger, ranged, damage, fire damage, a flaming arrow. Hurl a mote of fire.", c
    c = caption("Spell_Evocation_Y", "a sun. ", {"description": "A bright light."}, "Wizard")
    assert c == "bg3 spell icon, a sun.", c                      # spells name no source; banned sentence dropped
    assert caption("Action_Z_Dismiss", "m", {}, "several classes") == "bg3 action icon, dismiss, m."
    assert caption("TadpoleSuperPower_W", "m", {}, "Illithid").startswith("bg3 illithid power icon, m")
    log("[4.2] check passed")


def tiles(n):
    """icon -> (master over the hotbar dark, line art as grey over black) PIL tiles"""
    x = master(n)
    m = x[..., :3] * x[..., 3:] + DARK * (1 - x[..., 3:])
    la = np.clip(split(x, 512)["EL"], 0, 1)
    im = lambda a: Image.fromarray((a * 255 + .5).astype(np.uint8)).resize((T, T), Image.LANCZOS)
    return im(m), im(la)


def sheet(icons, out, start=0):
    """icons (<= PER) -> one labelled sheet: number, icon name, then display name · intent · damage · source"""
    rows = {r["icon"]: r for r in read_jsonl(D / "meta.jsonl")}
    src = json.loads((D / "links.json").read_text(encoding="utf-8"))["sources"]
    cw, lab = 2 * T + 6, 30
    S = Image.new("RGB", (COLS * cw + (COLS + 1) * 10, -(-len(icons) // COLS) * (T + lab + 10) + 10), (24, 25, 28))
    d = ImageDraw.Draw(S)
    for i, n in enumerate(icons):
        x, y = 10 + (i % COLS) * (cw + 10), 10 + (i // COLS) * (T + lab + 10)
        r = rows.get(n, {})
        d.text((x, y), f"{start + i + 1}. {n}"[:60], fill=(255, 225, 120))
        d.text((x, y + 13), " · ".join(v for v in (r.get("name"), r.get("VerbalIntent"), r.get("DamageType"),
                                                    src.get(n)) if v)[:60], fill=(200, 200, 205))
        a, b = tiles(n)
        S.paste(a, (x, y + lab))
        S.paste(b, (x + T + 6, y + lab))
    S.save(out)


def sheets(out, icons):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    idx = []
    for k in range(0, len(icons), PER):
        sheet(icons[k:k + PER], out / f"{k // PER:03d}.png", k)
        idx += [f"{k // PER:03d} {k + j + 1} {n}" for j, n in enumerate(icons[k:k + PER])]
    (out / "index.txt").write_text("\n".join(idx) + "\n", encoding="utf-8")
    log(f"[4.1] {len(icons)} icons -> {-(-len(icons) // PER)} sheets in {out}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["sheets"]:
        names = [l.strip() for x in a[2:] for l in (Path(x[1:]).read_text(encoding="utf-8").splitlines()
                                                      if x.startswith("@") else [x]) if l.strip()]
        names = names or sorted(set((D / "train.txt").read_text().split()) | set((D / "holdout.txt").read_text().split()))
        sheets(a[1] if len(a) > 1 else D.parent / "outputs" / "sheets", names)
    else:
        {"build": build, "check": check, "report": report}[a[0]]()
