"""In-app updates for the distributed app (D47: a zip + uv launcher; user 7.0i: "make sure the app can easily be updated
when it's finally distributed").

A release is a zip of the app's code with manifest.json at its root ({version, files: {path: sha256}}), published as a
GitHub release asset of REPO (its SHA-256: the asset's digest, else a <zip>.sha256 asset beside it).
  check     the newest release (one GitHub API request, cached CACHE_H hours in outputs/update/latest.json)
  stage     download the zip, verify its SHA-256 and every file against its manifest, unpack to outputs/update/staged/
            (the app itself is not touched yet)
  apply     at the next start, before the editor runs: back up what the update replaces or removes to
            outputs/update/backup-<old version>/, copy the new files in, remove files the release dropped; any error
            puts the backup back. Never touched: the user's folders (data/, models/, outputs/, .venv/) and data files
            the user changed (.json / .jsonl / .txt kept, the release's copy saved beside them as .new). Code files are
            always replaced (a stale .py beside new ones breaks the app; the old one is in the backup).
  rollback  put the last backup back
  build     a release: manifest.json + the zip + its .sha256 (the release script runs it)
  data      the game data an installed copy downloads once (D10 amended 2026-10-19: the user ships the icons): the
            editor's cut icons, thumbnails, shape cards, fitted colours / recipes and the hotbar backgrounds. They live on
            the orphan branch `data` of REPO (no shared history with the code), each version tagged data-v<DATA_VERSION>;
            the code ships iconkit/data_manifest.json, the SHA-256 of every data file, and `fetch_data` downloads GitHub's
            zip of the tag at the first start (or when DATA_VERSION changes), checks every file and puts it in data/.
            `data` builds the tree, the manifest, the commit, the branch and the tag here (it needs the game unpack); push
            the branch and the tag, then the code
  test      self-check on throwaway folders (stage from a local feed, apply, edits kept, a failed apply undone, rollback)
A git checkout (the developer's) never applies updates: it updates with git.
python -m iconkit.update check | apply | rollback | build OUT_DIR | data OUT_DIR | test"""
import hashlib, json, os, shutil, sys, tempfile, time, urllib.error, urllib.request, zipfile
from pathlib import Path
from . import __version__, DATA_VERSION

ROOT = Path(__file__).resolve().parent.parent
REPO = "SpasticPengu/BG3-Icon-Generator"   # the GitHub repository the releases come from (empty: no update checks)
CACHE_H = 6
SHIP = ["app", "iconkit", "README.md", "LICENSE", "NOTICE.md", "requirements.in", "requirements.lock", "Start.bat", "Start.command", "start.sh"]
SKIP = {"__pycache__", ".pytest_cache"}
DATA_EXT = {".json", ".jsonl", ".txt"}       # a user's change to one of these is kept; code is always replaced


def log(msg):
    print(msg, flush=True)


def ver(s):
    """'v0.10.2' -> (0, 10, 2); unparsable parts count as 0"""
    return tuple(int(p) if p.isdigit() else 0 for p in str(s).lstrip("vV").split("-")[0].split("."))


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def upd(root):
    return root / "outputs" / "update"


def shipped(root=ROOT):
    """the release's files: everything under SHIP, relative posix paths"""
    out = []
    for name in SHIP:
        p = root / name
        if p.is_file():
            out.append(name)
        elif p.is_dir():
            out += [f.relative_to(root).as_posix() for f in sorted(p.rglob("*")) if f.is_file() and not SKIP & set(f.parts)]
    return out


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": f"bg3-icon-generator/{__version__}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check(root=ROOT, feed=None, force=False):
    """-> {version, enabled, latest?, newer?, notes?, url?, zip?, digest?}. feed: a URL or file with GitHub's
    releases/latest JSON (tests; else ICONGEN_UPDATE_FEED, else REPO's)"""
    feed = feed or os.environ.get("ICONGEN_UPDATE_FEED") or (f"https://api.github.com/repos/{REPO}/releases/latest" if REPO else None)
    out = {"version": __version__, "enabled": bool(feed)}
    if not feed:
        return out
    cache = upd(root) / "latest.json"
    if not force and cache.exists() and time.time() - cache.stat().st_mtime < CACHE_H * 3600:
        rel = json.loads(cache.read_text(encoding="utf-8"))
    else:
        try:
            rel = json.loads(fetch(feed if "://" in feed else Path(feed).resolve().as_uri(), 8))
        except urllib.error.HTTPError as e:            # 404: the repository has no release yet, nothing to update to
            if e.code != 404:
                raise
            rel = {}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rel), encoding="utf-8")
    if not str(rel.get("tag_name", "")).startswith("v"):  # only app releases (v<version>): GitHub calls a lone data-v<N>
        rel = {}                                           # release "latest" even when it is marked otherwise
    assets = {a["name"]: a for a in rel.get("assets", [])}
    z = next((a for n, a in assets.items() if n.endswith(".zip")), None)
    latest = rel.get("tag_name", "").lstrip("vV")
    out.update(latest=latest, newer=bool(z) and ver(latest) > ver(__version__), notes=rel.get("body") or "", url=rel.get("html_url"))
    if z:
        side = assets.get(z["name"] + ".sha256")
        out.update(zip=z["browser_download_url"], digest=(z.get("digest") or "").removeprefix("sha256:") or None,
                   digest_url=side["browser_download_url"] if side else None)
    return out


def stage(info, root=ROOT):
    """download and verify the release in info (from check), unpack to outputs/update/staged -> its version"""
    u = upd(root)
    data = fetch(info["zip"], 120)
    want = info.get("digest") or (fetch(info["digest_url"]).decode().split()[0] if info.get("digest_url") else None)
    if not want:
        raise ValueError("the release has no SHA-256 to check the download against")
    if hashlib.sha256(data).hexdigest() != want.lower():
        raise ValueError("the download doesn't match the release's SHA-256: not installed")
    tmp = u / "staging"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    zp = u / "release.zip"
    zp.write_bytes(data)
    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():                         # no absolute paths or ..: nothing lands outside the folder
            if Path(n).is_absolute() or ".." in Path(n).parts:
                raise ValueError(f"unsafe path in the release: {n}")
        z.extractall(tmp)
    zp.unlink()
    man = next(tmp.rglob("manifest.json"), None)
    if not man:
        raise ValueError("the release has no manifest.json")
    base = man.parent
    m = json.loads(man.read_text(encoding="utf-8"))
    for p, h in m["files"].items():
        if not (base / p).is_file() or sha(base / p) != h:
            raise ValueError(f"the release's {p} doesn't match its manifest")
    final = u / "staged"
    shutil.rmtree(final, ignore_errors=True)
    base.rename(final)
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"[update] {m['version']} downloaded and checked: installs at the next start")
    return m["version"]


def staged(root=ROOT):
    return (upd(root) / "staged" / "manifest.json").exists()


def apply(root=ROOT, force=False, _fail_after=None):
    """install the staged release -> {from, to, kept}; puts everything back if a step fails"""
    if (root / ".git").exists() and not force:
        raise RuntimeError("this is a git checkout: update it with git, not the in-app updater")
    u = upd(root)
    src = u / "staged"
    new = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    old = json.loads((root / "manifest.json").read_text(encoding="utf-8")) if (root / "manifest.json").exists() else {"version": __version__, "files": {}}
    bak = u / f"backup-{old['version']}"
    shutil.rmtree(bak, ignore_errors=True)
    bak.mkdir(parents=True)
    added, kept, done = [], [], 0
    record = {"from": old["version"], "to": new["version"], "added": added, "kept": kept}

    def edited(p):                                     # a data file the user changed since the last release
        d = root / p
        return d.suffix in DATA_EXT and d.exists() and p in old["files"] and sha(d) != old["files"][p]

    def save(p):                                       # the current file into the backup
        d = root / p
        if d.exists():
            (bak / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(d, bak / p)
        else:
            added.append(p)
    try:
        if (root / "manifest.json").exists():
            shutil.copy2(root / "manifest.json", bak / "manifest.json")
        for p in new["files"]:
            d = root / p
            if edited(p):
                kept.append(p)
                shutil.copy2(src / p, d.with_name(d.name + ".new"))
                continue
            save(p)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / p, d)
            done += 1
            if _fail_after is not None and done >= _fail_after:
                raise OSError("simulated failure (test)")
        for p in set(old["files"]) - set(new["files"]):
            if (root / p).exists() and not edited(p):
                save(p)
                (root / p).unlink()
        shutil.copy2(src / "manifest.json", root / "manifest.json")
    except Exception:
        (bak / "record.json").write_text(json.dumps(record), encoding="utf-8")
        rollback(root, bak)
        log(f"[update] installing {new['version']} failed: put {old['version']} back")
        raise
    (bak / "record.json").write_text(json.dumps(record), encoding="utf-8")
    shutil.rmtree(src, ignore_errors=True)
    (u / "applied.json").write_text(json.dumps({**record, "time": time.time()}), encoding="utf-8")
    log(f"[update] installed {new['version']} (was {old['version']})" + (f"; kept your edited {', '.join(kept)} (the new copies are .new)" if kept else ""))
    return record


def rollback(root=ROOT, bak=None):
    """put a backup back (default: the newest) -> the version restored"""
    u = upd(root)
    bak = bak or max(u.glob("backup-*"), key=lambda p: p.stat().st_mtime, default=None)
    if not bak:
        raise RuntimeError("no backup to roll back to")
    rec = json.loads((bak / "record.json").read_text(encoding="utf-8"))
    for p in rec["added"]:                             # files the update brought: gone again
        (root / p).unlink(missing_ok=True)
    for f in bak.rglob("*"):
        if f.is_file() and f.name != "record.json":
            d = root / f.relative_to(bak)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, d)
    if not (bak / "manifest.json").exists():
        (root / "manifest.json").unlink(missing_ok=True)
    log(f"[update] rolled back to {rec['from']}")
    return rec["from"]


def build(out, root=ROOT):
    """manifest.json + bg3-icon-generator-<version>.zip + .sha256 into out -> the zip"""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files = shipped(root)
    m = {"version": __version__, "files": {p: sha(root / p) for p in files}}
    zp = out / f"bg3-icon-generator-{__version__}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            if p.endswith((".sh", ".command")):     # executable on macOS / Linux (Windows has no x bit to copy)
                zi = zipfile.ZipInfo.from_file(root / p, p)
                zi.external_attr, zi.compress_type = 0o100755 << 16, zipfile.ZIP_DEFLATED
                z.writestr(zi, (root / p).read_bytes())
            else:
                z.write(root / p, p)
        z.writestr("manifest.json", json.dumps(m, indent=1))
    (out / (zp.name + ".sha256")).write_text(f"{sha(zp)}  {zp.name}\n", encoding="utf-8")
    log(f"[update] built {zp} ({len(files)} files, {zp.stat().st_size / 1e6:.1f} MB)")
    return zp


DATA_FILES = ["data/glyph.json", "data/grammar.json", "data/hotbar.json", "data/links.json", "data/editor/index.json",
              "data/editor/parts.json", "data/editor/icons", "data/editor/thumbs", "data/editor/parts"]
DATA_MANIFEST = Path(__file__).with_name("data_manifest.json")      # shipped with the code: every data file's SHA-256
data_tag = lambda v: f"data-v{v}"
DATA_README = """# Game data for BG3 Icon Generator

This branch holds the editor's game data: Baldur's Gate 3 icons cut into strokes, thumbnails, shape cards, the fitted
colours and recipes, and the hotbar backgrounds. The app downloads it on its first start and checks every file; there's
nothing to do here by hand. The art belongs to Larian Studios: see NOTICE.md on the main branch.
"""


def data_files(root=ROOT, extra=None):
    """{path under the app folder: source file}. extra: more files (default: the 28 hotbar backgrounds from the game
    unpack, as data/backgrounds/)"""
    files = {}
    for name in DATA_FILES:
        p = root / name
        if p.is_file():
            files[name] = p
        elif p.is_dir():
            files.update({f.relative_to(root).as_posix(): f for f in sorted(p.rglob("*")) if f.is_file()})
        else:
            raise FileNotFoundError(f"{name} is missing: cut the editor's data first (python -m iconkit.editor extract / parts)")
    if extra is None:
        from . import paths
        extra = {f"data/backgrounds/{f.name}": f for f in sorted(paths.BACKGROUNDS.glob("*.DDS"))}
        if len(extra) != 28:
            raise FileNotFoundError(f"{len(extra)} hotbar backgrounds in {paths.BACKGROUNDS}, not 28")
    return {**files, **extra}


def build_data(out, root=ROOT, extra=None, manifest=DATA_MANIFEST):
    """the data branch's tree in out/ (data/... + README.md) and the manifest the code ships -> out"""
    out = Path(out)
    shutil.rmtree(out, ignore_errors=True)
    files = data_files(root, extra)
    for k, v in files.items():
        (out / k).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v, out / k)
    (out / "README.md").write_text(DATA_README, encoding="utf-8")
    (out / ".gitattributes").write_text("* -text\n", encoding="utf-8")   # byte for byte: git must never touch line endings
    m = {"data": DATA_VERSION, "files": {k: sha(out / k) for k in sorted(files)}}
    Path(manifest).write_text(json.dumps(m, indent=0), encoding="utf-8")
    log(f"[update] data v{DATA_VERSION}: {len(files)} files in {out}, manifest {manifest}")
    return out


def commit_data(tree, root=ROOT, replace=False):
    """tree as an orphan commit (as this repository's git identity, in UTC), branch `data` and tag data-v<N> -> its sha.
    The files go in byte for byte (no line-ending conversion: core.autocrlf on Windows turned the JSON's CRLF into LF and
    every hash missed). replace: move an existing tag (only for a version no released app uses yet)"""
    import subprocess
    tag = data_tag(DATA_VERSION)
    with tempfile.TemporaryDirectory() as t:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(t) / "index"), "TZ": "UTC"}
        git = lambda *a: subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", *a], cwd=root, env=env,
                                        capture_output=True, text=True, check=True).stdout.strip()
        git(f"--work-tree={tree}", "add", "-A", "-f", ".")
        c = git("commit-tree", git("write-tree"), "-m", f"Game data v{DATA_VERSION} for the editor (see README.md)")
    old = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], cwd=root, capture_output=True, text=True).stdout.strip()
    same = old and subprocess.run(["git", "rev-parse", f"{old}^{{tree}}"], cwd=root, capture_output=True, text=True).stdout.strip() == \
        subprocess.run(["git", "rev-parse", f"{c}^{{tree}}"], cwd=root, capture_output=True, text=True).stdout.strip()
    if old and not same and not replace:
        raise RuntimeError(f"tag {tag} already holds different data: bump DATA_VERSION (iconkit/__init__.py) for new data")
    if not same:
        subprocess.run(["git", "tag", "-f", tag, c], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "branch", "-f", "data", c], cwd=root, check=True)
        old = None
    log(f"[update] {tag} = {old or c}: push with `git push origin data {tag}`, then the code (with iconkit/data_manifest.json)")
    return old or c


def download(url, dest, what):
    """stream url to dest, saying how far it got (every 10%, or every 20 MB when the size isn't known)"""
    req = urllib.request.Request(url, headers={"User-Agent": f"bg3-icon-generator/{__version__}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        size, got, said = int(r.headers.get("Content-Length") or 0), 0, -1
        for b in iter(lambda: r.read(1 << 20), b""):
            f.write(b)
            got += len(b)
            step = got * 10 // size if size else got // 20_000_000
            if step > said:
                said = step
                log(f"[update] {what}: {got / 1e6:.0f}" + (f" of {size / 1e6:.0f} MB" if size else " MB"))


def fetch_data(root=ROOT, url=None, manifest=DATA_MANIFEST):
    """download the game data for this DATA_VERSION (GitHub's zip of its tag), check every file against the manifest
    shipped with the code, put them in data/ -> the number of files"""
    m = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if m["data"] != DATA_VERSION:
        raise ValueError(f"the shipped data manifest is for version {m['data']}, this app needs {DATA_VERSION}")
    url = url or os.environ.get("ICONGEN_DATA_URL") or f"https://github.com/{REPO}/archive/refs/tags/{data_tag(DATA_VERSION)}.zip"
    u = upd(root)
    u.mkdir(parents=True, exist_ok=True)
    zp, tmp = u / "data.zip", u / "data-staging"
    log(f"[update] downloading the game's icons (about 110 MB, once) from {url}")
    download(url, zp, "the game's icons")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zp) as z:
        names = set(z.namelist())
        tops = {n.split("/", 1)[0] for n in names}
        top = tops.pop() + "/" if len(tops) == 1 and not any(n.startswith("data/") for n in names) else ""   # GitHub's archives wrap one folder
        for p, h in m["files"].items():                 # only the manifest's files are read and written
            if top + p not in names:
                raise ValueError(f"{p} is missing from the icons download")
            b = z.read(top + p)
            if hashlib.sha256(b).hexdigest() != h:
                raise ValueError(f"{p} in the icons download doesn't match its SHA-256: not used (start again to retry)")
            (tmp / p).parent.mkdir(parents=True, exist_ok=True)
            (tmp / p).write_bytes(b)
    for p in m["files"]:
        (root / p).parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp / p, root / p)
    shutil.rmtree(tmp, ignore_errors=True)
    zp.unlink()
    log(f"[update] the game's icons are in place ({len(m['files'])} files, each checked)")
    return len(m["files"])


def test():
    """two releases on throwaway folders: stage (hash checked, a tampered one refused), apply (code replaced, a removed
    file gone, a new one added, the user's edited list kept + .new, user folders untouched), a failed apply undone,
    rollback"""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        root, rel = t / "app", t / "release"

        def tree(base, files):
            for p, s in files.items():
                (base / p).parent.mkdir(parents=True, exist_ok=True)
                (base / p).write_text(s, encoding="utf-8")
        v1 = {"iconkit/a.py": "v1", "app/x.js": "v1", "iconkit/list.json": '{"a": 1}', "iconkit/gone.py": "old"}
        v2 = {"iconkit/a.py": "v2", "app/x.js": "v2", "iconkit/list.json": '{"a": 2}', "app/new.js": "new"}
        tree(root, v1)
        (root / "manifest.json").write_text(json.dumps({"version": "1.0.0", "files": {p: sha(root / p) for p in v1}}), encoding="utf-8")
        tree(root, {"iconkit/list.json": '{"a": "mine"}', "outputs/editor/drafts/d.json": "draft", "data/x.bin": "data"})
        tree(rel, v2)
        (rel / "manifest.json").write_text(json.dumps({"version": "2.0.0", "files": {p: sha(rel / p) for p in v2}}), encoding="utf-8")
        zp = t / "r.zip"
        with zipfile.ZipFile(zp, "w") as z:
            for p in [*v2, "manifest.json"]:
                z.write(rel / p, p)
        feed = t / "feed.json"
        good = {"tag_name": "v2.0.0", "body": "notes", "assets": [{"name": "r.zip", "browser_download_url": zp.as_uri(), "digest": "sha256:" + sha(zp)}]}
        feed.write_text(json.dumps({**good, "assets": [{**good["assets"][0], "digest": "sha256:" + "0" * 64}]}), encoding="utf-8")
        info = check(root, feed=str(feed), force=True)
        assert info["latest"] == "2.0.0" and info["newer"] == (ver("2.0.0") > ver(__version__)), info
        try:
            stage(info, root)
            raise AssertionError("a tampered download was installed")
        except ValueError as e:
            assert "SHA-256" in str(e) and not staged(root), e
        feed.write_text(json.dumps(good), encoding="utf-8")
        info = check(root, feed=str(feed), force=True)
        assert info["latest"] == "2.0.0" and info["notes"] == "notes", info
        assert stage(info, root) == "2.0.0" and staged(root)
        try:                                           # a failure half way: everything as before
            apply(root, _fail_after=2)
            raise AssertionError("the simulated failure didn't stop the update")
        except OSError:
            pass
        assert (root / "iconkit/a.py").read_text() == "v1" and (root / "app/x.js").read_text() == "v1" and not (root / "app/new.js").exists()
        assert json.loads((root / "manifest.json").read_text())["version"] == "1.0.0"
        r = apply(root)
        assert r["to"] == "2.0.0" and r["kept"] == ["iconkit/list.json"], r
        assert (root / "iconkit/a.py").read_text() == "v2" and (root / "app/new.js").read_text() == "new"
        assert not (root / "iconkit/gone.py").exists()
        assert (root / "iconkit/list.json").read_text() == '{"a": "mine"}' and (root / "iconkit/list.json.new").read_text() == '{"a": 2}'
        assert (root / "outputs/editor/drafts/d.json").read_text() == "draft" and (root / "data/x.bin").read_text() == "data"
        assert not staged(root)
        assert rollback(root) == "1.0.0"
        assert (root / "iconkit/a.py").read_text() == "v1" and (root / "iconkit/gone.py").read_text() == "old" and not (root / "app/new.js").exists()
        assert json.loads((root / "manifest.json").read_text())["version"] == "1.0.0"
        (root / ".git").mkdir()
        try:
            apply(root)
            raise AssertionError("applied to a git checkout")
        except RuntimeError:
            pass
        zb = build(t / "out", ROOT)                    # the real app builds, and its zip stages
        with zipfile.ZipFile(zb) as z:
            m = json.loads(z.read("manifest.json"))
        assert m["version"] == __version__ and "app/editor.js" in m["files"] and "iconkit/editor.py" in m["files"], list(m["files"])[:5]
        for p in ("Start.bat", "start.sh", "Start.command", "requirements.lock"):
            assert p in m["files"], f"the release lacks {p}"
        with zipfile.ZipFile(zb) as z:
            assert z.getinfo("start.sh").external_attr >> 16 & 0o111, "start.sh isn't executable in the zip"
            assert b"\r\n" in z.read("Start.bat") and b"\r" not in z.read("start.sh"), "launcher line endings"
        pins = {l.split("==")[0] for l in (ROOT / "requirements.lock").read_text().splitlines() if "==" in l and not l.startswith(" ")}
        want = {l.split("#")[0].strip().split(">")[0].split("<")[0].split("=")[0] for l in (ROOT / "requirements.in").read_text().splitlines() if l.split("#")[0].strip()}
        assert want <= pins, f"requirements.lock is missing {want - pins}: compile it again (requirements.in)"
        dev, user = t / "dev", t / "user"              # the game data: built, downloaded, checked, unpacked
        for n in DATA_FILES:
            (dev / n).parent.mkdir(parents=True, exist_ok=True)
            if n.endswith(".json"):
                (dev / n).write_text('{"n": "%s"}' % n, encoding="utf-8")
            else:
                (dev / n).mkdir(exist_ok=True)
                (dev / n / "a.png").write_bytes(n.encode())
        (t / "bg.DDS").write_bytes(b"bg")
        (dev / "data/glyph.json").write_bytes(b'{\r\n"crlf": 1\r\n}\r\n')   # Windows line endings must survive git
        man = t / "data_manifest.json"
        tree_ = build_data(t / "dtree", dev, extra={"data/backgrounds/bg.DDS": t / "bg.DDS"}, manifest=man)
        import subprocess                              # through real git, as commit_data does it: bytes unchanged
        g = t / "g"
        subprocess.run(["git", "init", "-q", str(g)], check=True)
        subprocess.run(["git", "-C", str(g), "config", "core.autocrlf", "true"], check=True)
        subprocess.run(["git", "-C", str(g), "config", "user.name", "test"], check=True)
        subprocess.run(["git", "-C", str(g), "config", "user.email", "test@example.invalid"], check=True)
        dc = commit_data(tree_, g)
        blob = subprocess.run(["git", "-C", str(g), "show", f"{dc}:data/glyph.json"], capture_output=True, check=True).stdout
        assert blob == (dev / "data/glyph.json").read_bytes(), f"git changed the data's bytes: {blob!r}"
        arch = t / "data-v1.zip"                       # the shape of GitHub's zip of a tag: one folder around the tree

        def archive(change=None):
            with zipfile.ZipFile(arch, "w") as z:
                for f in sorted(tree_.rglob("*")):
                    if f.is_file():
                        rel = f.relative_to(tree_).as_posix()
                        z.writestr(f"BG3-Icon-Generator-data-v1/{rel}", b"tampered" if rel == change else f.read_bytes())
        archive()
        (user / "data" / "editor").mkdir(parents=True)
        (user / "outputs" / "editor").mkdir(parents=True)
        (user / "outputs" / "editor" / "draft.json").write_text("mine", encoding="utf-8")
        assert fetch_data(user, arch.as_uri(), man) == len(DATA_FILES) + 1
        assert (user / "data/editor/icons/a.png").read_bytes() == b"data/editor/icons" and (user / "data/backgrounds/bg.DDS").exists()
        assert (user / "outputs/editor/draft.json").read_text() == "mine" and not (user / "README.md").exists()
        archive(change="data/editor/thumbs/a.png")
        try:
            fetch_data(user, arch.as_uri(), man)
            raise AssertionError("a tampered icon file was used")
        except ValueError as e:
            assert "SHA-256" in str(e), e
    log("[update] test passed: check, stage (tampered download refused), apply (code replaced, file removed and added, "
        "your edited list kept + .new, user folders untouched), failed apply undone, rollback, git checkout refused, build (launchers "
        "executable, line endings, lock covers requirements.in), game data (tree + manifest, tag archive downloaded, every file checked; a tampered file refused)")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else "check"
    if cmd == "check":
        log(json.dumps(check(force=True), indent=1))
    elif cmd == "apply":
        apply()
    elif cmd == "rollback":
        rollback()
    elif cmd == "build":
        build(a[1] if len(a) > 1 else ROOT / "outputs" / "release")
    elif cmd == "data":
        commit_data(build_data(a[1] if len(a) > 1 else ROOT / "outputs" / "data-tree"))
    elif cmd == "test":
        test()
    else:
        sys.exit(__doc__)
