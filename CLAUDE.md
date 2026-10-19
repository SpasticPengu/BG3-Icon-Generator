# BG3 Icon Generator

Local app that generates Baldur's Gate 3 icons from structured fields, then builds every game
variant (controller / tooltip / hotbar, DDS, mod files) deterministically. v1 = spells + actions/
skills + illithid powers (D23); passives, class/subclass and item icons later. Public release (D10, amended 2026-10-19):
the editor's game data ships as a separate `data-v<N>` download with `NOTICE.md` (free, unofficial); the training
dataset, models and outputs stay private.
The glyph (controller/tooltip art) is the product; the PC hotbar background is secondary (the user's ModernUI plays it
down): PC-only effects (centre light, frames) stay in the hotbar recipe, never in masters or training.

- **State lives in `implementation-plan.md`** (Status, Decisions with reasons, phases, log).
  Read its Status + Decisions + current phase before anything else. After every step: update
  its Status log and `plan-overview.html` (same phase names, same commit hash), then commit on
  the feature branch. No end-of-chat handoff needed.
- Python with numpy/torch/gradio: `~\anaconda3\python.exe`. The default
  `python` (3.14) has Pillow but no numpy. Anaconda's torch is the conda **CPU-only** build (and needs conda's
  `Library\bin` on PATH to import): anything on the GPU (diffusers, FLUX.2 klein, LoRA) runs in the project's uv env
  `.venv\Scripts\python.exe` (CUDA torch cu128, diffusers 0.41; gitignored). Weights in `models/` (gitignored).
- `data/`, `models/`, `outputs/` are gitignored: they hold extracted Larian assets, weights
  and generations. Never commit them; the only shipped part is the editor's data zip (`python -m iconkit.update data`).
- Phase 0 probes (`research/probes/*.py`, args in docstrings) reproduce every "Verified fact"
  in the plan; re-run them after a game patch re-unpack.
- Dataset: `python -m iconkit.extract all` (~6 min, needs `data/srd/5e-SRD-Spells.json`) → `data/`;
  anomaly report: `python -m iconkit.report` (~8 min) → `data/anomalies.html`. The tooltip fade is
  the formula in `iconkit/fade.py` (bottom-only, D13), never a measured mask. Colour = 31 preset
  gradient maps (+ 8 two-colour metamagic icons, two presets by stroke, `extract.TWO_TONE`, D26): `python -m iconkit.grammar` (~3 min) → `data/grammar.json` + review page `data/grammar.html`;
  `grammar.detint/tint` move a glyph between presets. Hotbar 64 px: `python -m iconkit.hotbar` (~45 min: shared recipe
  + per-colour refits, needs grammar.json) → `data/hotbar.json` + check sheet `data/hotbar.png`, `... hotbar report` →
  review page `data/hotbar.html`, `... hotbar check` = self-check; `hotbar.compose` builds one (`recipe_for` picks the
  colour's own numbers). Controller backgrounds are used whole (144 → 64): cropping them breaks the frame match. Actions
  only use framed backgrounds (D21). Judge hotbar look by pixel classes / histograms and zoomed crops, not MAE alone.
  Before blaming the recipe for a look difference, compare the PC cell with the game's controller art directly on opaque
  line pixels (alpha > .9 at 64 px: no recipe or background involved).
- Recipe fits use **Powell** (`pw(loss, x0, free_keys, maxfev)`, steps per key in `STEP` / `step_of`), not Nelder-Mead:
  NM's first simplex is 5% of each start value (0.00025 from an exact 0), so keys that start small barely move (round 5:
  hue 1° → 1.007, light .07 → .08 in 300 iterations; Powell beat it at equal evaluations on every colour tried). `nm()`
  stays for old probes; if you use it, never start a key at 0. To hold a key fixed, leave it out of the free list (D22
  styles do this via `PINS`).
- Fit modes: `python -m iconkit.hotbar fit presets [kinds]` keeps each kind's shared recipe from `hotbar.json` and refits
  the colours only (each in the D22 style it kept), `fit <kind>` refits that kind fully, `fit` all. Colour refits run in
  `POOL` (6) processes; masters at 64 px + same_size / register results are cached in `data/hotbar_cache.npz` (bump
  `CACHE_V` when `down()`, `same_size()` or `register()` change; first run ~13 min, then seconds). Round 5 timing: `fit
  illithid` 23 min (13 of it building the cache), `fit presets spell action` see the plan's Status log.
- Colours with `MIN_SMALL` (5) to `MIN_PRESET - 1` training icons fit `SMALL_KEYS` and keep them only when the loss drops
  (round 4 drew 19 such colours, Radiant gold among them, with the shared recipe). Before changing the recipe, run
  `research/probes/colour_residuals.py` (per colour: game - ours by ring and pixel kind, glow / line hue and chroma) to tell
  a systematic gap from one icon's quirk.
- The recipe fit renders thousands of times: per-icon fixed data (game side of every measure) lives in `hotbar.Ref`,
  `objective(ms, ps)` pools the game's side once. Smoke-test fit + page in minutes with `python -m iconkit.hotbar fit
  quick` (3 iterations per search) before a full fit (~1 h). Prototype a recipe change on 1/5 of train first:
  `research/probes/recipe_proto.py <kind> [keys]` (MAE, colour mix, edge, stone slopes, line stats, residual by ring for
  stone / lines). A whole review round (user notes on a page -> measure, prototype, fit, page, plan): skill
  `icongen-review-round`.
- A new family must not reshape the colour presets: `grammar.run` fits presets on the non-illithid training icons and
  appends house presets only for illithid powers no preset fits (Illithid red). Check every refit against a copy of the
  previous `grammar.json` (preset names, curves, which earlier icons moved).
- Review-page "before" = the previous round's files kept as `data/hotbar.rN.json` / `data/grammar.rN.json` (round 5 page:
  `.r4`); keep the pre-fit copies the same way each round.
- A game cell is only fitting data if it shows the master's drawing at the same size and place. Spells and actions line up
  exactly (best sub-pixel shift (0, 0) for 99%+; `same_size()` checks them). Illithid PC cells often enlarge (×0.95-1.25)
  and/or shift (up to 1 px) the drawing: `register()` lines each up first (L* correlation .70 → .91), cells under
  `REG_MIN` .85 are left out (`eval.registered` / `eval.not_same_size`), and the page draws them lined up. Misaligned
  cells make every fit prefer flat, blurred colour (round 4's flat illithid lines). Check any new kind or icon source with
  both (zoom and shift) first.
- Refit one kind without redoing the hour-long rest: `python -m iconkit.hotbar fit illithid` (any of `KINDS`; the others
  are kept from `hotbar.json`). The fit is deterministic, so a kept kind equals a refit one.
- Patch 8 icon art lives outside the Multitool unpack (`UnpackedData\Gustav_Textures`, from Gustav_Textures.pak; command
  in `iconkit/paths.py`); `paths.tooltip(n)` / `paths.controller(n)` search both sources.
  Review pages share `iconkit/page.py` (decision cards first, then collapsed rows).
- Glyph structure (2.4): `python -m iconkit.glyph fit` (~13.5 min) → `data/glyph.json`, `... report` → `data/glyph.html`,
  `... check`. Lines = brightness over black (L*/100 × alpha) above .55 × the icon's p99 **and** above the local midpoint
  between floor and peak (`glyph.threshold`, D38: else painted glow between close strokes becomes line), never alpha
  alone: action masters carry an opaque dark glow (alpha ~.9, L* < 30) around their lines, and weapon actions draw strokes
  that fade in alpha. Glow leak probe: `research/probes/glow_leak.py` (`--sheet` to look). Any code that grows the glow
  composes via `glyph.rebuild` (= `variants.paint`); a fit on a different composition picks recipes that ship worse.
  Score glows as seen over the hotbar dark, not over mid grey (a glow of L* 50 vanishes over grey .5).
- Relations (2.5): `python -m iconkit.relations run` (~12 min since D38: the local line test costs 0.5 s per master) → `data/relations.json`, `... report` → `data/relations.html`.
  Compare drawings with `relations.kappa` on line art (chance-corrected; ≥ .9 same drawing), never alpha IoU (glows
  overlap: only 30 of 2.1's 124 alpha "same-glyph" pairs are the same drawing) or plain dilated overlap (dense icons match).
- Shape vs spell fields (2.6): `python -m iconkit.shape run` (~10 min) → `data/shape.json` + `data/shape.npz`, `... report`
  → `data/shape.html`, `... check`. Test any label-to-drawing link with **one icon per series** (`shape.series`: kappa .75+,
  same display name, same Spell stem, element series), never per icon: D27's copy groups miss series of different
  drawings (Disguise Self's 33 faces made "Illusion" look like "a face"); shuffle the label within intent for the null.
  Series also join spell flyouts (`extract.spell_containers`) and Reapply X with X; leaving flyouts split once turned spell
  type on actions from "weak" into "yes".
- Connections (2.7): `python -m iconkit.links run` (~4 min, needs `data/shape.npz`) → `data/links.json`, `... report` →
  `data/links.html`, `... check`. Action sources come from game data first (Progressions + SpellLists + PassiveLists +
  passives' UnlockSpell, item unlocks, name tokens), bg3.wiki only for gaps (Battle Master manoeuvres). Frame families
  need EVERY member to draw the frame (a median let a gripping hand count as a frame).
- Exporter (3.1): `python -m iconkit.variants test` (~2 min) → `data/variants.json` + sheet `data/variants.png`, `... check`.
  Line art = RGBA 512, grey level (`grammar.detint`) in RGB, alpha = line share × alpha; `variants.master()` grows the glow
  and tints lines + glow once at the final alpha (never tint the layers apart: the presets were fitted on the composite).
  DDS via `variants.dds` (own encoder `iconkit/dxt.py`; never Pillow's DXT5: it shifts line colours), mod files via
  `variants.export` (D37), PNGs at any size via `variants.pngs` / `python -m iconkit.variants png ICON [SIZE ...]`.
  In-game test mod: `research/probes/ingame_test.py` → `outputs/IconGenTest`; deploy loose (`Build-Mod.ps1 -All`), no pak.
- Captions (Phase 4): motifs are hand-written in `iconkit/motifs.jsonl` (in git), one per train + holdout icon; contact
  sheets `python -m iconkit.captions sheets DIR` (to the scratchpad); `... build` → `data/captions.jsonl` (template
  `captions.caption`, `captions.BANNED` = words D18/D25/D32/D34 keep out, also enforced on motifs), `... report` →
  spot-check page `data/captions.html`, `... check`. Action sources = `links.sources` (game data, then `links.HAND` for
  basic actions, summons, story actions); rerun `python -m iconkit.links run` after changing either. Motif direction
  = where the tip / point faces (user's definition); read weapons at 300 px or more: at 176 px a third of the sword
  directions came out backwards (Larian's diagonal slash swords mostly point up-left / up-right, hilt at a lower corner).
- Model (Phase 5, D39-D41): LoRA training = AI Toolkit (`train/run_aitk.py CONFIG`, logs memory at each device switch);
  generation + scoring = `research/probes/score53.py` (gen in `.venv`, score / steer / blind in anaconda). On the 10 GB
  card keep the transformer in fp8 storage (`enable_layerwise_casting`, ~3.9 GB): bf16 resident oversubscribes it next
  to Firefox and Windows pages to shared memory (seconds become a minute; check `Get-Counter '\GPU Process
  Memory(*)\Dedicated Usage'`, PyTorch's own numbers miss it). Load the LoRA BEFORE the casting and skip `lora_`
  (peft casts later adapters to fp8: "addmm_cuda not implemented for Float8"); move an old transformer `.to("cpu")` +
  `gc.collect()` before loading the next. Count inverted outputs (black on white: bright border) as failures.
- House parts (5.4, D43): `python -m iconkit.parts run` (~3 min) → `data/parts.json` + `data/parts.npz`, `... report` →
  `data/parts.html`, `... check`. Names live in `parts.FAMILIES` / `NAMES` (keyed by each group's medoid part) and are
  applied by the report, so a rename needs no rerun; `check` flags names whose group vanished after a rerun. Plain strokes
  (skeleton < 1.6 × box side) never group: size-normalised, every straight line or arc matches every other.
  The user means whole shapes (a whole figure, not its head): `whole_shapes` adds exact repeats (B, every group:
  shift-tested, so dense areas never count) and, for figure families, joined strokes up to the usual figure size (A).
  A lone stroke can't tell a dagger blade from a slit pupil (kappa .9+), so families carry an eye-checked `EXCLUDE`;
  look at the whole-shape sheets (two independent visual reviews worked well) before trusting a family.
- Editor (Phase 7, D46): `python -m iconkit.editor` (first run cuts `data/editor/`: strokes ~3 min + parts panel ~8 min,
  `... editor parts` alone; serves `http://127.0.0.1:8765/`, `--no-browser`), `... editor check`, GPU golden test = page `/?golden`, brush vs the
  game's strokes = page `/?brushtest` (recalibrate `app/brush.js` NOISE if the brush or the measure changes), freehand frame time = page
  `/?perftest[=px][&w=width]` (5,000 px stroke, `window.perfResult` with ms per frame part; 2026-10-18: p50 1.9 ms).
  Freehand strokes are painted in pieces (`brush.paint` own ranges) from an incremental centre line: keep `live` +
  `finish` byte-equal to `render` if the brush changes. Never read layout (`getBoundingClientRect`) per pointer event
  (use `vpRect`). UI conventions: a control's `title` = "Name (Keys): description" (shown as the styled tooltip with
  key caps), sliders via `slider()` (scrubbable `data-scrub` name + typed value), new shortcuts go in the help sheet. Frontend
  `app/` (plain ES modules, no build step); `app/glow.js` is `variants.paint` in WebGL2: change both together and rerun
  the golden. Strokes compose with `lighten` (union, like the game's one drawing), never source-over. Brush strokes are
  vectors re-rendered from their settings; game strokes stay bitmaps. Vague parts: `iconkit/parts_hidden.json` (keyed by
  group key; the panel's right-click edits it). Delete `outputs/editor/drafts/Autosave.json` after a test session, or the
  user's next start restores it. Line art PNGs for the browser are opaque RGB (grey, alpha): a transparent PNG loses
  faint grey to premultiplied alpha. The runtime path (split, tint, compose, variants, editor) imports no scikit-image: colour formulas and `disk`
  come from `iconkit/lab.py`. The Claude browser pane is often hidden (no screenshots, no animation frames): drive the
  page with dispatched pointer events from `javascript_tool`. The user's browser is Firefox: measure there too
  (headless Firefox with a throwaway profile + `/?perftest[&rt]`, results in `data/editor/perf.json`); never call
  `gl.finish` or upload a whole GPU canvas per frame (a cross-process read back in Firefox, ~12 ms). Parts panel: cards
  are rendered in colour (`part_render`), categories live in `iconkit/parts_categories.json` (eye-checked, editable by
  right-click; `editor check` fails on an uncategorised visible card), the game's damage-type symbols are cut by
  `python -m iconkit.editor symbols` (kind "Symbol", also run by `extract`) and lead the panel. Card rules (panel build):
  completion, prune of strokes no other spell family draws (frames: all; else only detached ones, `editor.off`), strays,
  near copies; diff a rebuild against a copy of the old `parts.json` + card PNGs and eye-check every changed card. Another
  `python -m http.server` may sit on 8765: the server binds exclusively and takes the next free port up to 8775 (the
  page's layout lives per origin); every page load logs `page ready in X s` (`/?boottest` keeps it in perf.json).
  Tabs: the open tab's drawing is in the usual globals, the others in `docs[i].state`; the autosave is `{v: 2, docs}`.
  Test sessions run the server with `--drafts DIR` (own autosave, custom colours and imports, never the user's). Custom
  colours = presets in `outputs/editor/presets.json` (`custom_preset`, `register`: frames / recipes borrowed from the
  nearest game preset). Import = `import_req` (faded tooltips: strokes rebuilt from the colour channels, `unfade`;
  colour = nearest game gradient or one fitted on the icon, `own_colour`) into `outputs/editor/imported/`; the "Name in
  the game" field is the export key. Bitmap → vector strokes: `app/vectorize.js` (check: `node app/vectorize.check.mjs`).
  Eraser modes: Pixels | Tapered | Whole strokes. Erase strokes live in `it.erase` (non-destructive, `{pts, w, taper?}`)
  and every path that applies them goes through `applyErase` (bake + export): a tapered one narrows what is left
  towards the cut with the brush's own end profile (`vectorize.taperCut`: geodesic distance from the cut, widths from
  the stroke before the cut); the drag shows a plain cut, the taper appears on release.
  Barbs (thorny edges): `research/probes/barbs.py` measures them (opening by a .4-width disc; spells 3.1 per 100 px,
  actions 1.0); `vectorize.barbDensity` is the same measure in the page (exact EDT; keep it agreeing with the probe).
  Brush `v.barbs` is calibrated to that measure (`BARB_CAL`, on closed circles; /?brushtest prints `barb_density`);
  game strokes restyle via `it.barbs` (`restyled()`). Re-check the calibration if the barb model or the measure changes.
  Barb shape (`research/probes/barb_shapes.py`): sawtooth splinters pointing one way along the stroke (`brush.barbPoly`,
  shared by brush and restyle; restyle takes the way from the stroke's own path, `flowOf`). Judge by eye on
  `/?barbsheet=ICON,...` (as drawn | cut | restyled | brush; `barbsheet.png` in the drafts folder): density numbers alone
  passed the old stubby spikes the user rejected.
  Launcher (8.1): `Start.bat` / `start.sh` / `Start.command` set up `.runtime/` (uv, Python 3.12, `requirements.lock`);
  no `pyproject.toml` at the root on purpose (a `uv sync` there would strip the CUDA `.venv`). Change libraries in
  `requirements.in`, recompile the lock (command in its header), rerun `update test`. Keep `Start.bat` CRLF (edit it
  with Python or Write, not `sed`, which drops the CRs; `update test` checks). Test the launcher from PowerShell with
  `cmd.exe /c .\Start.bat --no-browser --drafts DIR` (returns at once: the batch hands the console to `iconkit/launch.py`
  with `start /b` so Ctrl+C never asks "Terminate batch job"; that loop restarts after an update); stop its python
  afterwards (port 8765). Ctrl+C harness: send a real CTRL_C_EVENT via AttachConsole to a hidden console.
  Console text a user sees (setup steps `[1/3]`-`[3/3]` across Start.bat / start.sh / `update.fetch_data`, update
  install, the "is running at" line, failures) is formal full sentences without `[tag]` prefixes (user 2026-10-19);
  developer logs keep `[editor]` / `[update]`. On an error `launch.py` keeps the window open (Enter to close).
  Repository: `SpasticPengu/BG3-Icon-Generator` (public). **Commit here as SpasticPengu (repo config) in UTC: `TZ=UTC git
  commit ...`** (overrides the global real-name identity; user 2026-10-19). Branch `public` tracks `origin/main`; every
  older branch has the user's name and +11:00 dates: never push them. Publish (only when the user asks): run the
  personal-strings check from memory `public-repo-identity` (its terms stay out of the repo) and find nothing, then
  `TZ=UTC git commit-tree <work-branch>^{tree} -p public -m "..."`, `git branch -f public <sha>`, and push with
  `git -c credential.helper= -c "credential.helper=!gh auth git-credential" push origin public:main`.
  Rulesets (no bypass, 2026-10-19): `main` can't be deleted or force-pushed (fetch first; if a pull request was merged
  on GitHub, bring it into the work branch and `public` before the next snapshot), `v*` / `data-v*` tags can't be
  deleted or moved (a fix means turning the "Release and data tags" ruleset off for that push), `data` can't be
  deleted (a new data version may replace it). Merges: squash only. Actions: GitHub-owned actions only.
  Game data (no release): orphan branch `data`, one tag per version `data-v<DATA_VERSION>`; the code ships
  `iconkit/data_manifest.json` (every file's SHA-256) and installed copies download GitHub's zip of the tag. New data:
  bump `iconkit.DATA_VERSION`, `python -m iconkit.update data` (needs the game unpack: tree in `outputs/data-tree`, the
  manifest, orphan commit, branch, tag), push `git push origin data data-v<N>` BEFORE the code that needs it. Test an
  install: `git archive --format=zip --prefix=x/ data-v1 > d.zip`, `ICONGEN_DATA_URL=<file URL of d.zip>`, Start.bat.
  Releases (D48, GitHub): bump `iconkit/__init__.py` `__version__`, commit, tag `v<version>`, push the tag (only when
  the user asks): `.github/workflows/release.yml` tests, builds and publishes. `update.REPO` = the GitHub repository.
  Release notes (user 2026-10-19): formal, in `### Bug Fixes` / `### Features` / `### Performance Improvements` (only
  the sections with entries) + `### Installation`; set with `gh release edit vX --notes-file` once the workflow is done.
  The in-app Update dialog renders them (`notesInto`: headings, bullets, text only). The zip is `BG3-Icon-Generator.zip`
  (no version: Windows names the unzipped folder after it; the updater takes any `.zip` asset).
  Updates (D48): `iconkit/update.py` (`python -m iconkit.update test | build OUT | check | apply | rollback`), version in
  `iconkit/__init__.py`; `update.REPO` empty = no checks until hosting is chosen; a git checkout never self-updates.
  Test the page's update flow with `ICONGEN_UPDATE_FEED=<local releases/latest JSON>` and delete `outputs/update/` after.
  Bump `editor.DATA_V` when a change needs every user to re-cut `data/editor/`. In a release, the shapes panel's edits go
  to `outputs/editor/user/` (`read_list` / `edit_list`); here they still edit the shipped `iconkit/parts_*.json`.
  Tabs: unsaved = the drawing's hash differs from when it was opened or saved (`docSig`, `markSaved`); `closeDocs`
  asks only then. Library section ids stay `icons / parts / mine / drafts`; the UI says Icons / Shapes / Imported / Drafts.
  Groups: `item.g` + `GROUPS`, `tidyGroups()` (in `changed()`) keeps each group's strokes together. Above 512 px
  `variants.paint` grows the glow at 512 and enlarges it, `grammar.tint` runs on threads (same numbers).
- Look at icons before judging them: `python -m iconkit.sheet OUT.png ICON... | @list.txt` (tooltip |
  controller | master | alpha, labelled; write OUT to the scratchpad). Train only on `data/train.txt`.
