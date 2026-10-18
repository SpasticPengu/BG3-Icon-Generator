"""Shared HTML for review pages (decision cards first, then collapsed rows). Pages embed Larian
thumbnails, so they are written to data/ and stay local."""
import io, base64, html
from PIL import Image

e = html.escape
_SRC = {}


def src(path, size, lossless=False):
    """path = image file or an in-memory PIL image (keep it alive while the page is built: the cache keys on id)"""
    key = (id(path) if isinstance(path, Image.Image) else path, size, lossless)
    if key not in _SRC:
        b = io.BytesIO()
        im = path if isinstance(path, Image.Image) else Image.open(path)
        im.convert("RGBA").resize((size, size), Image.LANCZOS).save(b, "WEBP", **({"lossless": True} if lossless else {"quality": 82}))
        _SRC[key] = "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()
    return _SRC[key]


def figure(path, cap, tip="", size=64, hold=False):
    return (f'<figure{" class=hold" if hold else ""} title="{e(tip)}"><img src="{src(path, size)}" '
            f'width={size} height={size} alt=""><figcaption>{e(cap)}</figcaption></figure>')


def decision(i, total, got, count, question, what, examples, opts, note="", more="", unit="icons"):
    """opts = [(key, title, text)]; option A is the recommendation; got = chosen key or None."""
    cls = lambda k: " rec" if k == (got or "A") else " dim" if got else ""
    chip = lambda k: "Chosen" if k == got else "Recommended" if k == "A" and not got else ""
    o = "".join(f'<div class="opt{cls(k)}"><h3><span class=k>{k}</span>{e(t)}'
                f'{f"<span class=chip>{chip(k)}</span>" if chip(k) else ""}</h3><p>{e(p)}</p></div>' for k, t, p in opts)
    state = f'<span class=done>Decided: {got}</span>' if got else ""
    return (f'<section class="decision{" decided" if got else ""}" id=d{i}><div class=dtag>Decision {i} of {total}'
            f'<span class=n>{count} {unit}</span>{state}</div>'
            f'<h2>{e(question)}</h2><p class=what>{e(what)}</p><div class=ex>{examples}</div><div class=opts>{o}</div>'
            f'{f"<p class=note>{e(note)}</p>" if note else ""}{more}</section>')


def row(count, title, action, why, body=""):
    return (f'<details class=row><summary><span class=cnt>{count}</span><span class=tt><span class=tw></span>{e(title)}</span>'
            f'<span class=act>{e(action)}</span></summary><div class=body><p>{e(why)}</p>{body}</div></details>')


def lede_reply(decided, n):
    """(lede fragment, reply box) for n decisions with the chosen keys in `decided`."""
    n_open = sum(not decided.get(i) for i in range(1, n + 1))
    lede = (f"<b>{n_open} decision{'s need' if n_open > 1 else ' needs'} you.</b>" if n_open
            else f"<b class=ok>All {n} decision{'s are' if n > 1 else ' is'} made</b> (chosen options in green).")
    eg = " ".join(f"{i}A" for i in range(1, n + 1) if not decided.get(i))
    reply = (f"<div class=reply>Reply in chat with one letter per decision, for example <code>{eg}</code>.</div>"
             if n_open else "")
    return lede, reply


def page(title, body):
    return (f'<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body><main>\n<h1>{e(title)}</h1>\n{body}\n</main></body></html>')


CSS = """
:root{--bg:#14161a;--card:#1d2026;--card2:#24282f;--ink:#e8e6e1;--soft:#c9c7c2;--mute:#8d929b;--line:#2f333b;--accent:#f0b429;--rec:#3fb56b;--link:#4c9bff}
*{box-sizing:border-box}
body{margin:0;padding:28px 16px 64px;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",system-ui,sans-serif}
main{max-width:1080px;margin:0 auto}
h1{font-size:24px;margin:0}
.lede{color:var(--mute);margin:4px 0 24px}.lede b{color:var(--accent)}
.decision{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:12px;padding:20px 22px;margin:0 0 22px}
.dtag{display:flex;gap:12px;align-items:baseline;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.dtag .n{color:var(--mute)}
.decision h2{font-size:21px;line-height:1.3;margin:6px 0}
.what{color:var(--soft);margin:0 0 16px;max-width:80ch}
.ex{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 18px}
.chain,.pair{display:flex;align-items:flex-start;gap:6px;background:var(--card2);border-radius:10px;padding:8px}
.pair{display:grid;grid-template-columns:auto auto;gap:2px 6px}
.pname{grid-column:1/-1;text-align:center;font-size:12px;color:var(--soft)}
.arrow{align-self:center;color:var(--mute);padding:0 2px 18px}
.more{align-self:center;color:var(--mute);font-size:13px;padding-bottom:18px}
.cgroup{width:100%;background:var(--card2);border-radius:10px;padding:10px 12px}
.chead{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:8px;font-size:14px;color:var(--soft)}
.chead b{color:var(--ink)}.chead .off{color:var(--accent)}
.sw{display:inline-block;vertical-align:-2px;width:14px;height:14px;border-radius:4px;flex:none}
.crow{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start}
.usual{display:flex;gap:8px;padding-right:12px;margin-right:4px;border-right:1px dashed var(--line);opacity:.75}
.offs{display:flex;flex-wrap:wrap;gap:8px}
.opts{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.opt{background:var(--card2);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.opt.rec{border-color:var(--rec);box-shadow:inset 0 0 0 1px var(--rec)}
.opt h3{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 6px;font-size:16px}
.opt .k{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--line);font-size:13px}
.opt.rec .k{background:var(--rec);color:#0b1a10}
.chip{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--rec)}
.opt p{margin:0;color:var(--soft);font-size:14px}
.note{color:var(--mute);font-size:13px;margin:12px 0 0}
.opt.dim{opacity:.45}.decision.decided{border-left-color:var(--rec)}.dtag .done{color:var(--rec)}.lede b.ok{color:var(--rec)}
details.all{margin-top:14px}details.all>summary{cursor:pointer;color:var(--link);font-size:14px}
details.all .grid{margin-top:10px}
.reply{border:1px dashed var(--accent);border-radius:12px;padding:14px 18px;margin:0 0 40px}
.reply code{background:var(--card2);color:var(--accent);padding:2px 8px;border-radius:6px;font-size:15px}
h2.sec{font-size:17px;margin:36px 0 2px}.secsub{color:var(--mute);margin:0 0 10px;font-size:14px}
details.row{border-top:1px solid var(--line)}details.row:last-child{border-bottom:1px solid var(--line)}
details.row>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:52px 1fr auto;gap:14px;align-items:baseline;padding:10px 4px}
details.row>summary::-webkit-details-marker{display:none}
details.row>summary:hover{background:var(--card)}
.cnt{text-align:right;font-weight:700;font-variant-numeric:tabular-nums;color:var(--link)}
.tw::before{content:"\\25B8";display:inline-block;width:16px;color:var(--mute)}details[open]>summary .tw::before{content:"\\25BE"}
.act{color:var(--mute);font-size:14px;text-align:right}
.body{padding:0 4px 16px 70px}.body p{margin:0 0 10px;color:var(--soft);max-width:80ch}
.grid{display:flex;flex-wrap:wrap;gap:10px}
.twin{display:inline-block;background:var(--card2);border-radius:10px;padding:8px;margin:0 8px 8px 0;vertical-align:top}
figure{margin:0;width:64px}
figure img{display:block;border-radius:6px;background:repeating-conic-gradient(#45484f 0 25%,#62656d 0 50%) 0 0/12px 12px}
figure.hold img{outline:2px solid #c9a227;outline-offset:1px}
figcaption{margin-top:3px;font-size:11px;line-height:1.25;color:var(--mute);text-align:center;overflow-wrap:anywhere}
table.t{border-collapse:collapse;width:100%;font-size:14px;margin:6px 0 10px}
table.t th,table.t td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:middle}
table.t th{color:var(--mute);font-weight:600}table.t td.num{text-align:right;font-variant-numeric:tabular-nums}
.tw-x{overflow-x:auto}
@media (max-width:640px){details.row>summary{grid-template-columns:44px 1fr}.act{grid-column:2;text-align:left}.body{padding-left:4px}}
"""
