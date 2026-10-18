# BG3 Icon Generator: implementation plan

> **Resume here (2026-10-19): editor on branch `phase-7-editor`** (not merged, no remote). Round 7.0i is built (tabs,
> copy pass, browser translation, sharp big exports, vector strokes at 2048, updates D48; see Phase 7, 7.0i). **The
> launcher is built (8.1, 2026-10-19)**: `Start.bat` / `start.sh` / `Start.command` set up `.runtime/` and restart after an
> in-app update; tested here from nothing and through a restart. **Releases go on GitHub**:
> **Published 2026-10-19 (user):** `main` on `SpasticPengu/BG3-Icon-Generator` is one fresh commit (088cfab, the
> `phase-7-editor` tree, as SpasticPengu with the noreply email in UTC); local branch `public` tracks it. The `data-v1`
> release holds the icons download (102 MB, checked live: the app downloads and verifies it). The older branches keep
> the user's name and +11:00 dates: never push them. From now on commits here are SpasticPengu in UTC (repo config +
> `TZ=UTC`). Publishing later work: snapshot the work branch's tree onto `public` (CLAUDE.md), push only when asked.
> Repository set up (user, 2026-10-19): README, description, topics, wiki / projects off, branches deleted on merge,
> Dependabot alerts + security fixes, private vulnerability reporting (secret scanning was on). `main` = cfcdbcf.
> Open for the user: **a licence** (none yet: the code is all rights reserved until one is added; 8.4), an optional
> social preview image (Settings, web only), and the first app release (`v0.7.0` tag, workflow 8.1b) when asked. Still before a public release: 8.3 (extract from the user's own
> BG3 install; the editor's first run needs `data/` from the Multitool unpack today), 8.4 (README, licences). **Later, user 2026-10-19 ("we'll come back to this"):
> vector conversion edge cases**: a crescent outline whose tip test misses (1 of 4 synthetic crescents still traces as
> two arcs capped side by side; the acute-angle / spur limits in `vectorize.js` were tuned on Moonbeam only), and how
> converted strokes look on icons other than Moonbeam (thorn edges, dots at junctions). Start from the 7.0i "Vector
> strokes at 2048" notes and `node app/vectorize.check.mjs`.

> **Status (2026-10-16):** Phases 1-4 merged into `main` (Phase 1: 31a9cf2; Phase 2, 2.1-2.7: `--no-ff` merge of
> `phase-2-grammar`; Phase 3: `--no-ff` merge of `phase-3-exporter`, 609d427; Phase 4: `--no-ff` merge of
> `phase-4-captions`, 54d3d1a, user "merge"). **Phase 5 work on `phase-5-bakeoff`; the Phase 7 editor prototype on
> `phase-7-editor` (made from it, 2026-10-17; see Resume here).**
> No remote configured.
> Dataset: 1,550 masters (Patch 8 art from `Gustav_Textures.pak` + illithid powers, D23), training list `data/train.txt`
> (991), test `data/holdout.txt` (92; old icons keep their side). Rebuild: put `5e-SRD-Spells.json` in `data/srd/` (see
> 1.3), then `python -m iconkit.extract all` (~6 min, anaconda python).
> **2.1 done: colour = 31 preset gradient maps** (30 + house preset Illithid red; Metamagic red retired by D26, the 8
> two-colour metamagic icons get two presets by stroke, `grammar.json` `two_tone`; `python -m iconkit.grammar`, ~5 min →
> `data/grammar.json` + page `data/grammar.html`). D17 (1A), D18 (2A: the model draws grey glyphs, code colours them).
> **2.2 hotbar recipe v6 (round 5) fitted** → `data/hotbar.json` + check sheet `data/hotbar.png`. `python -m iconkit.hotbar
> fit presets [kinds]` refits the colours only (6 processes, ~10 min once `data/hotbar_cache.npz` exists), `fit <kind>`
> one kind fully, `fit` everything (~1 h), `fit quick ...` smoke test; `... hotbar report` → page `data/hotbar.html`;
> `... hotbar check`; `hotbar.compose(master, family, preset)` for Phase 3.
> Test MAE spells **11.89**, actions **14.53** (round 4: 12.81 / 15.32; round 3: 13.28 / 16.31); illithid powers 15.49 on
> 2 test icons (lined-up cells; training 15.13).
> D19-D36 settled (D24 = user "5A": hotbar recipe v6 final for v1, 2.2 closed; D25 line art + code glow; D26 a second
> colour per stroke; D27-D31 and D4 from 2.5; D32-D33 from 2.6; D34-D36 from 2.7, below).
>
> **2.4 glyph structure measured** (`python -m iconkit.glyph fit`, ~4 min → `data/glyph.json`; `... report` → page
> `data/glyph.html`): line weight is a house constant (~15 px at 512), and a glow grown from the lines in code per colour
> rebuilds the game's to 1.2 L* on test spells, 3.0 on actions (lines alone 9.3 / 11.1).
>
> D25 settled (user "1A"): the model draws line art, code grows the glow; D18, 3.1, 4.2, 5.1 and Phase 6 amended.
>
> **2.5 relations measured** (`python -m iconkit.relations run`, ~1.5 min → `data/relations.json`; `... report` → page
> `data/relations.html`; `... check`): shared drawings by line-art shape (chance-corrected line overlap), not names.
>
> User "1A 2A 3A, but" → D27 (copies weighted 1/n), D4 (make related = same line art recoloured), D28 (element symbol
> library, stamped by code, optional), D29 (the model makes new drawings; only symbols and related copies are exact;
> 5.3 novelty check against the test set's own spread). Phases 3.3, 4.2, 5.3, 6, 7.1, 7.3 amended.
>
> User notes after that (series composites; a draft editor) measured → user "4A 5A" → D30 (series composites in code),
> D31 (draft editor in v1, minimal tools); 5.3, 7.1, 7.5, 7.6 amended. 2.5 closed: all 5 page decisions made.
>
> **2.6 shape vs spell fields measured** (`python -m iconkit.shape run`, ~10 min → `data/shape.json` + `data/shape.npz`;
> `... report` → page `data/shape.html`; `... check`): with one icon per series, only intent and the actions' spell type
> change the drawing; school, area, level and action cost do not (they only look shape-bound when series count per icon).
> User "1A 2A" → D32 (prompt: intent + actions' spell type; School, Level, Use cost fields dropped), D33 (training weight
> 1/sqrt(n) per drawing of a series; amends D27); 4.2, 6, 7.1 amended. 2.6 closed.
>
> **2.7 connections audit (user request: "go through the spells/wiki")** (`python -m iconkit.links run`, ~4 min →
> `data/links.json`; `... report` → page `data/links.html`; `... check`): spell flyouts join the series (712 → 698; spell
> type on actions drops to "weak", reopening part of D32); an action's source changes the drawing; Reapply spells are
> made in code (base shrunk + ring, .86-.97); 19 frame families keep an exact frame. No shared motifs beyond damage symbols.
>
> User "2A 3A" → D35 (Reapply spells made in code, out of training), D36 (frame families in Based on series); then "1A"
> after decision 1 was explained again → D34 (actions name their source; spell type out, amends D32). 4.2, 5.3, 6, 7.1,
> 7.3, 7.5 amended. 2.7 closed: **Phase 2 done.**
>
> **Phase 3 started (2026-10-15) on `phase-3-exporter`.** 3.1 done: `iconkit/variants.py` (line art → master → controller
> 144 / tooltip 380 / hotbar 64; `python -m iconkit.variants test`, ~2 min → `data/variants.json` + sheet
> `data/variants.png`; `... check`). Masters rebuilt from vanilla lines only match the game's over the hotbar dark to
> 1.4 L* (spells), 2.8 (actions), 2.9 (metamagic, part by part); results under 3.1.
>
> 3.2 + 3.3 done: `iconkit/dxt.py` (own BC3 encoder: Pillow's shifts line colours) and `variants.dds / export` (atlas +
> map + TextureBank, tooltip / controller as new GUI textures + `AssetsLowRes` + metadata, D37: the layout of Larian's
> Toolkit guide and Patch 8's own icons, checked 2026-10-15). Test mod `outputs/IconGenTest`
> (`research/probes/ingame_test.py`; Divine converts its files cleanly).
>
> PNG export at any size (`variants.pngs`, `python -m iconkit.variants png ICON [SIZE ...]`). User "why an in-game
> test?" → D37 settled on the evidence (Larian's guide + Patch 8 files), the in-game look moved to Phase 7's test.
> **Phase 3 done (2026-10-15)**, merged into `main` (609d427).
>
> **Phase 4 done (2026-10-16)** on `phase-4-captions`: action sources (632 of 639), 1,083 motifs in
> `iconkit/motifs.jsonl`, captions `python -m iconkit.captions build` → `data/captions.jsonl`; spot-check round 1 (13
> notes → 96 motifs rewritten with their class), round 2 "all read fine" (user). Merged into `main` (54d3d1a).
>
> **Glow leak fixed (2026-10-16, side session): D38, merged into `main`** (`--no-ff` merge of `kk/nice-fermat-a131f2`,
> user "merge"). Lines = 2.4's global ramp **and** above the local midpoint between floor and peak (`glyph.threshold`);
> the 2.4 glow fit now composes like the shipping painter. Glow-made line pixels spells .074 → .039, actions .045 →
> .019; Silencing Blade / Giant Subjugation .16 / .17 → .01; 3.1 round trip spells 1.39 → 1.18 L*, actions 2.77 → 2.84,
> illithid 3.23 → 1.62. Main's `data/glyph.json` + `variants.json` / `.png` refit with the merged code (byte-identical to
> the branch's run), `data/glyph.html` rebuilt; old ones kept as `data/*.pre-d38.*`.
>
> **2.5-2.7 rerun on D38 lines (2026-10-16, side session, `kk/beautiful-torvalds-90cfb0`, merged into `main`, user
> "merge and rerun"): no settled decision's evidence flips.** D27 groups 32 / 82 → 31 / 76 (threshold jitter, plus Flesh
> to Gold / Stone .83 → .99: 6 test icons with their drawing in training), D29 yardstick median .53 → .50 (p90 .83 →
> .84), D30 leave-one-out .91 → .90 (better 140 of 155 → 160 of 182), 2.6 tests 22 of 22 verdicts kept (series 698 →
> 700), D34 source test yes, D35 code .84-.97, D36 frame families 19 → 20 (Dragonborn breath joins: user look, sheet
> `data/dragonborn_frame_family.png`). Details under 2.5-2.7. Main's `data/` reran with the merged code (`relations /
> shape / links` `.json`, `shape.npz`, pages): same results as the branch; old files kept as `*.pre-d38.*`.
>
> **D39 (2026-10-16, chosen by Claude at the user's request): base model FLUX.2 klein 4B, one LoRA, no 3-way
> bake-off**; its reference images do drafts / frames / symbol room, alpha read back from the line drawing, SDXL fallback.
>
> **5.1 done (2026-10-16): D40, alpha read back with one grey k = .8** (adds .3 L* on spells / actions; illithid 4-5,
> looks right). klein 4B is in `models/`, GPU work in `.venv` (Anaconda's torch is CPU-only).
>
> **5.2 spells LoRA done (2026-10-16):** `outputs/lora/klein4b_spells_v1/` (AI Toolkit in `tools/ai-toolkit`, run
> `train/run_aitk.py train/klein4b_spells.yaml`, ~52 min); draws the game's line style, unseen objects stay recognisable;
> ships on the distilled model at LoRA x1.5 (~6 s per icon).
>
> **5.2 all-kinds LoRA done (2026-10-16):** `outputs/lora/klein4b_all_v1/` (947 icons, 3,000 steps, 73 min, checkpoints
> every 250); sheets `outputs/klein4b_all_v1_samples.png` (base, every 500), `outputs/klein4b_all_v1_distilled.png`
> (x1 / x1.5), `..._distilled_x2.png` (x2 / x2.5), `..._1500_distilled.png`. On the distilled model action prompts come
> out inverted (black silhouette on white) until x2.5; the spells LoRA needed x1.5.
>
> **Resume here (2026-10-17, night): editor v2 on branch `phase-7-editor`** (from `phase-5-bakeoff`; not merged,
> nothing pushed; merge only when the user asks). The user tried v1 and sent notes (Phase 7, 7.0b): all of them are
> built (Affinity-style UI, vector strokes with measured game roughness, retroactive taper / width / curve, pen with
> corners + point editing, eraser, light backgrounds, resizable docks, hi-res export, vague parts hidden). Waiting on
> the user: try v2 and send notes. Run: `~\anaconda3\python.exe -m iconkit.editor` (first run cuts
> `data/editor/`: ~3 min strokes + ~2 min parts panel; then serves `http://127.0.0.1:8765/` and opens the browser;
> `--port N`, `--no-browser`; 8765 taken: the next free port up to 8775). Checks: `python -m iconkit.editor check`; GPU golden = page `/?golden` (writes
> `data/editor/golden.json`, `window.goldenResult`); brush vs game = page `/?brushtest` (`window.brushResult`, sheet
> `data/editor/brush_compare.png`); rebuild data: `... editor extract`, `... editor parts`. Drafts + autosave live in
> `outputs/editor/drafts/` (`Autosave.json` is restored on start: delete it after test sessions). Next, once the user
> replies: their notes; then 7.1 / 7.5 / 7.6 pieces still missing (element symbol stamp D28, Based on series D30 / D36
> in the editor); the D47 launcher (first-run extraction still needs scikit-image's `skeletonize` for the parts panel:
> vendor a thinning or keep scikit-image for first run only); the Phase 7 in-game test. Still open from Phase 5 (GPU, separate): the model draft test (draft as klein reference vs img2img on grey
> lines, D31 / D42; the editor writes the draft line art to `outputs/editor/<Mod>/drafts/`). **v2 LoRA trained
> 2026-10-17** (`outputs/lora/klein4b_all_v2/`: saves every 2,000 + final 16,500; samples sheet
> `outputs/klein4b_all_v2_samples.png`) and **scored** (8,000-16,500 at x2 distilled, `outputs/score53_v2/`, with
> v1 2,500 x2 copied in as `v1-2500x2`; sheet `outputs/score53_v2_sheet.png`; numbers in the Status log). **Blind
> test 3** (12,000 x2): **24 of 24 told apart** (tests 1 / 2: 21, 24): 4 passes did not make the drawings pass as the
> game's. User: the giveaway is no reuse of house elements (Divine Strike: same sword,
> only the element changes); pairs 6, 7, 13, 15, 16 don't look like anything. Measured (Status log): the game's drawing
> matches its closest training sibling at kappa .83, the model's .34; the 5 have concrete motifs whose main object
> dissolves. Both point at D42 (composite-first), already settled. **Draft test done** (5.3, `research/probes/draft53.py`): with a draft built
> from game parts the model keeps the game's drawing (.71 vs free .28) but only by copying the draft (never better
> than the draft alone, .69; D30 rebuilds .92 either way) and ignores a prompt asking for another object. Whole-drawing
> starts ship from code. **Masked inpainting done**: keeping the game's shared base and letting the model repaint the
> rest draws the prompt's object (Pact of the Blade's trident, Hex's book, frame insides) about as close to the game as
> another member's own inside (.48-.50 vs .51; free .33); element symbols stay code (.74 vs .53). **D48 settled** (the model
> fills an erased area). **Planner test done** (5.3 note): Qwen3-4B plans + code composes + inpaint: kappa .25 vs free
> .26, plans often miss the main object. **Blind test 4** (planner path, 11 pairs): **11 of 11 told apart**
> (tests 1-3: 21, 24, 24 of 24): no model path so far passes as the game's art; the editor route (game parts, D30 / D36
> code, the model filling an erased area, D48) stays the product. All 92 hold-out icons have now been shown in a blind
> test: a later one needs new icons (e.g. a re-split, or icons drawn after the dataset). **Editor v2 notes fixed
> (2026-10-18, side session, 7.0c): dock hide collapses the pane, every slider / splitter resets (double-click or
> Backspace), freehand frame time flat (5,000 px stroke: 229.7 → 9.8 ms; `/?perftest`), polish pass. Then 7.0d (user:
> research UI/UX, extremely polished, faster): drawing p50 1.9 ms (from 8.1), research-based polish (scrubby
> controls, tooltips with keys, HUD, thumbnails, context menu, shortcuts sheet), snapping (page, strokes, equal gaps)
> + Align / distribute / centre on page; 7.0e: drawing in Firefox as smooth as hovering (measured with headless
> Firefox, `/?perftest&rt`), Parts panel with damage-type symbols, colour and categories; 7.0f: clearer tools,
> right panel reorganised, align in the options bar, glowing swatches, export dialog (single image to share), parts
> completed to whole elements; 7.0g: start-up screen + stable port + boot times in the terminal (the user's "minute"
> not reproduced: 1.2 s), seamless segmented controls, filter chips + parts search, parts round 3 (frame and detached
> prunes, strays, near copies), export 2048 px ~3x faster + lossless WebP, layer groups (Ctrl+G). Waiting on the user:
> try it and send notes (if start-up is slow again, the terminal's `page ready` / `slow:` lines say where).** Then D48 in the editor (erase an area, the model fills it). Only 11
> hold-out icons are still unseen by any blind test (`blind` keys in `outputs/score53_v2/`). Testing in the Claude browser pane: it is often hidden (no screenshots, no animation frames): drive the
> page with dispatched pointer events from `javascript_tool`; the app renders on a timer when no frame comes.
> Settled earlier today: D46, D47, D43 amended (no part names), D45 void. The 5.4 page's names and questions are void.
> Old step list (before the re-evaluation): Next, in order: (1) **parts library** (D43, done above); (2) put the
> names into `iconkit/motifs.jsonl` (per icon: `parts.json` `icons[n].groups` → family via `NAMES`; same name for the
> same part everywhere), `python -m iconkit.captions build / check`, user spot-check; (3) rebuild
> `outputs/trainset_all` captions, run v2 (`train/klein4b_all_v2.yaml`, 4 passes, ~7 h; embeddings re-cache for the
> new captions: close GPU-heavy apps first), score with `ICON_RUN=klein4b_all_v2` + `research/probes/score53.py`
> (gen / score / tells; D41's distilled x1.5-2.5), then a blind test 3 that follows the app's real path per icon
> (composites where a vanilla start exists; a house part taken for a hold-out icon must come from another icon: the
> library includes the hold-out icons) on the 35 hold-out icons not yet shown; (4) amend Phase 7 for D42-D44
> (fields, editor with parts panel, house brush) and prototype the brush from the `tells` stroke numbers.
> Read the Phase 5 section, D39, D40, D5, D11, D25, D29, D31, D36 first. `phase-5-bakeoff` has D38 (fast-forwarded to `main`, 660a36e): 5.1's alpha
> recovery works on the clean line art, and main's `data/glyph.json` holds the matching recipe. Captions for 5.3's hold-out prompts are in `data/captions.jsonl`
> (SDXL's CLIP reads 77 tokens: the longest lose their description tail there).
> Labels: `data/meta.jsonl` (name, VerbalIntent, DamageType), `data/links.json` (sources, frames, reapply).
> Known hotbar gaps (2.2 "Round 5", "Left"): Maiming Strike's bright middle, Mantle's pinker
> glow, Radiant gold's saturated stone, Mind Tax's red glow, spell corners 14-17 L* too bright. Not asked again (round 4
> offer, no answer): an optional PC glyph scale for illithid powers.
>
> User priority (2026-10-14): **the glyph is the product; the PC background is secondary** (ModernUI plays it down). PC-only
> effects (centre light, frames) live in the hotbar recipe, never in masters or training; keep frame tuning minimal.
> Resume: read Status, Decisions, Open questions, then the current phase. After every step update
> the Status log + `plan-overview.html`, commit.

## Goal

**App gist (user, 2026-10-17, after rejecting the part names):**
- Almost everything that can be done programmatically is (colours, glow, variants, export: Phases 2-3).
- An editor with access to all vanilla icons, where individual strokes can be deleted.
- The editor holds common parts (as extracted in 5.4) so nobody has to hunt for the vanilla icon with the best
  copy of a part.
- The editor draws strokes freehand, possibly with basic line / circle / spline tools (house stroke, D44).
- The editor's result is exported as is or used as a reference for the model.
- The editor also takes the spell's parameters, as for a model-made icon.

Local, lightweight app: user fills structured fields (+ description) and gets a BG3-style icon,
then every game variant is built **without** a model (controller 144, tooltip 380 with fade,
hotbar 64 on the right background, DDS, mod files). v1: spells (`Spell_`) + actions/skills
(`Action_`, `Skill_`) + illithid powers (`TadpoleSuperPower_`, D23); passives Phase 9; Class/Subclass and Items later as separate tabs. Must
handle official BG3/D&D spells and fully custom ones; related icons are derived from a generated
spell. The model draws new icons in the game's style, never copies; only fixed parts (damage-type symbols) are reused
exactly (D28, D29). Public release from the start (D10, D11).

## Verified facts (Phase 0; Patch 8 HF10 unpack + BaseGameReference stats)

Reproduce with `research/probes/*.py` (run with anaconda python; out dir = `research/findings`).

**Tiers (spell-like icons)** (`dds_census.py`, `icon_tiers.py`)

| Tier | Size | Format | Location | Background |
|---|---|---|---|---|
| Hotbar / spellbook (PC) | 64 px cell, 2048² atlas, 32×32 grid | BC3, 12 mips | `Icons\Public\{Shared,SharedDev}\Assets\Textures\Icons\Icons_Skills.dds` + UVs in `GUI\Public\{Shared,SharedDev}\GUI\Icons_Skills.lsx` (1,834 keys); Patch 8: `Icons\Public\GustavX\...\Icons.dds` (1024×512) + `GUI\Public\GustavX\GUI\Icons.lsx` (111 keys) | **baked in**, alpha = 1 everywhere |
| Tooltip | 380² | 911 BC7, 446 BC7_SRGB, 164 DXT5; no mips | `GUI\Public\Game\GUI\Assets\Tooltips\Icons\` (1,521; Game.pak); Patch 8: `Mods\GustavX\GUI\Assets\Tooltips\Icons\` (103; Gustav_Textures.pak) | none; **bottom fade** |
| Controller | 144² | 1,480 BC7, 42 DXT1; no mips | `...\ControllerUIIcons\skills_png\` (1,522); Patch 8: `Mods\GustavX\GUI\Assets\ControllerUIIcons\skills_png\` (103) | none; no fade |

- **Patch 8 icons (2026-10-14, user tip):** the 111 GustavX hotbar keys (Arcane Archer, Swarmkeeper, Bladesinger, Hexblade,
  Drunken Master, Oath of the Crown, Giants, Stars, Death Domain, Swashbuckler, Shadow Magic...) had no tooltip/controller art in
  the Multitool unpack. A census of every pak's file table (`Divine -a list-package`, all of `Data\*.pak`) finds skill
  tooltip/controller art in exactly two places: `Public/Game/GUI/Assets` (Game.pak) and `Mods/GustavX/GUI/Assets`
  (Gustav_Textures.pak, extracted to `UnpackedData\Gustav_Textures`, command in `iconkit/paths.py`). `AssetsLowRes` = smaller
  copies. GustavX: 61 Action + 6 Spell (v1, same art style) + 36 PassiveFeature (Phase 9) + 6 Item + 2 `statIcons` (Bladesong
  charges: condition icons, a different style, excluded with that family). Every Spell/Action/Skill icon the stats reference
  now has art; the 86 references without any are items, debug statuses and dead names (`Skill_Air_Teleportation`, `unknown`).

- User's claims checked: controller is **not** the largest (144 < tooltip 380). Tooltip = same art
  as controller (mean RGB diff 5-9/255 after resize) with a bottom fade. PC version carries a
  type-dependent background. All confirmed except the size order.
- Fade (`alpha_fade.py`, 150 icons): alpha ratio tooltip/controller = 1.00 for rows ~19-114 of 380,
  then 0.96@133, 0.90@152, 0.82@171, 0.73@190, 0.64@209, 0.55@228, 0.46@247, 0.37@266, 0.28@285,
  0.21@304, 0.16@323, 0.11@342, 0.07@361. Roughly uniform across columns (0.13-0.22 in rows 300-340,
  slight left-to-right rise). Row 0 = 0.03 (edge artifact?).
  - Refit on all 1,405 pairs (per-pixel median, `extract fadefit` → `data/fade_measured.npy`): row
    profile 1.00 to row ~114, 0.96@133, 0.82@171, 0.64@209, 0.45@247, 0.28@285, 0.16@323, 0.07@361.
    The 2D median is uneven at the borders and leans slightly left to right: **not used** (D13).
  - **Shipped fade = `iconkit/fade.py`**: `(1 - smoothstep(t))^1.8`, t from 25.3% to 124.7% of the
    height, same for every column. Fits the measured central-column profile with RMSE 1.7/255, max 7.3/255
    (plain smoothstep 4/255, linear 5.6/255).
  - **~10% of v1 vanilla tooltips (110 of 1,045) use a radial vignette** (top and sides dimmed too),
    not the bottom fade. Per-icon art; we do NOT reproduce it (user, 2026-10-14: fade is bottom-only).
- Backgrounds: 28 textures in `...\ControllerUIIcons\icon_bg_png\` (144², DXT1, opaque), referenced
  by **no** XAML, so these are Larian's compositing assets. Names: action, actionPassive, bonusAction, buff,
  buffPassive, coldDamagePassive, control, controlPassive, damagePassive, debuffPassive, fireDamage,
  fireDamagePassive, heaingPassive (sic), heal, lightening (sic), metaMagic, monster,
  necroDamagePassive, nonElementalResistancePassive, radiance, spell, summon, tadpole, utility,
  utilityPassive, weaponAction, weaponBonusAction, weaponDamagePassive. Grid: `findings/backgrounds.png`.
- Hotbar background rules (`icon_analysis.py`, `composite_check.py`):
  - `Spell_` 445/445 → `spell_bg` (brown stone). Hotbar ≈ spell_bg ⊕ controller glyph (residual 11.7-18.1/255).
  - `PassiveFeature_` → coloured radial bg keyed by glyph colour: blue 274 → utilityPassive 98%;
    red 9 → damagePassive 100%; magenta 8 → debuffPassive 100%; cyan 7 → heaingPassive 100%;
    pink 3 → controlPassive 100%; green 3 → necroDamagePassive 2/3; orange 22 → actionPassive 45% /
    buffPassive 36% / fireDamagePassive 18%. Residual 9.8/255.
  - `Action_` (574): **no** single bg fits (residual 22-27/255). Framed bg + per-icon coloured glow
    painted behind the glyph (`findings/composite_check.png`, `grid_Action.png`).
    **Resolved in 2.2:** the frame is a controller framed bg (full 144, no crop), darkened, chosen by the glyph's
    colour preset; the "glow" is a dark halo that hides the frame round the glyph (results under 2.2).
- Hotbar glyph looks crisper than a plain downscale of the controller art (residual sits on edges).
  **Resolved in 2.2:** Lanczos of the premultiplied master + unsharp mask; glyph not scaled or shifted (best fit
  scale 1.00, offset 0 on 167 icons).
- Prefixes (tooltip files): Action 553, Spell 445, PassiveFeature 329, Surface 48, Skill 47,
  TadpoleSuperPower 42, statIcons 25, GenericIcon 18, PassiveAction 9, Target 2, Projectile 2, other 1.
  Naming: `Spell_<School>_<Name>`, `Action_<Class>_<Name>`, `PassiveFeature_<Name>`.
  Some `_2` variants carry a Roman numeral badge ("II"), e.g. `Spell_Evocation_HellishRebuke_2`.

**Colour grammar** (`icon_analysis.py`; dominant glyph hue of controller icons; bins: red <15/≥345,
orange 15-40, gold 40-65, green 65-160, cyan 160-200, blue 200-250, violet 250-280, magenta 280-330, pink 330-345)

- Stats field **`VerbalIntent`** is the game's own category. Icons used by SpellData:
  Damage 256 (red 36, orange 24, blue 14, green 10%); Utility 182 (blue 72%); Buff 124 (orange/gold 66%);
  Control 87 (red/pink 67%); Summon 66 (orange 90%); Debuff 49 (magenta 77%); Healing 33 (cyan 78%).
- Damage spells by `DamageType`: Fire 22 orange 86%; Cold 15 blue 93%; Lightning 14 blue 100%;
  Necrotic 13 green 76%; Radiant 11 gold 81%; Psychic 9 magenta 77%; Force 7 red 100%;
  Thunder 7 violet 85%; Acid 6 green 100%; Poison 7 green 57%; Bludgeoning 53 orange 50 / red 26%;
  Piercing 8 red 62%; Slashing 6 orange 66%.
- Official UI palette `GUI\Public\Game\GUI\Theme\DefaultTheme.Colours.xaml` L153-165: Physical/None
  #aaaaaa, Acid #f7ff09, Thunder #7e46ae, Necrotic #a5f280, Fire #ff6600, Lightning #427DE3,
  Cold #44AED4, Psychic #efacdf, Poison #c8f000, Radiant #ffc000, Force #dc1c24, HealAmount #49CBC1.
- User's claims: force red ✓, psychic purple-pink ✓, utility white/blue ✓, buff gold ✓,
  debuff purple ✓ (magenta), control pink ✓ (control_bg is pink). New: healing teal, summon amber,
  thunder violet, necrotic/acid/poison green, radiant gold. School is secondary (Illusion 82% blue,
  others mixed).
  > NOTE / open validation: control-pink vs psychic-pink vs debuff-magenta separation needs exact hue stats (2.1).
- Not all icons are pure emissive strokes: some have dark fills (e.g. Darkvision spell) or
  multi-hue fire gradients (several Action_ icons).

**Relations**
- StatusData icons mostly reuse an existing icon: Spell_ 281, Action_ 166, GenericIcon 153
  (e.g. `GenericIcon_Intent_Debuff`), statIcons 111, Item 100, PassiveFeature 70, Status_ 67, Skill_ 27.
- Spell → passive/action pairs (`pairs.py`, 6 found by name): **same glyph** (alpha IoU 0.61-0.81,
  median 0.70) **recoloured to the passive's own category** (Hex magenta→green, HuntersMark
  magenta→red, ArmorOfAgathys orange→blue, Counterspell red→blue). `findings/pairs.png`.

**Transparency**
- Over-black render → alpha = max(RGB): mean |Δa| 0.082 spells, 0.186 actions, 0.208 passives
  (300-icon sample). Too lossy for passives/actions as-is.

**Data sources**
- Stats: `BG3 Modders Multitool\UnpackedMods\BaseGameReference\{Shared_BaseGameReference\Public\{Shared,SharedDev},GustavX_BaseGameReference\Public\GustavX}\Stats\Generated\Data\*.txt`;
  9,423 entries (SpellData 3,322, StatusData 2,340, PassiveData 977); `using` inheritance must be
  resolved. A later dir redefining an entry with `using "<itself>"` **merges** onto the earlier
  entry (replacing loses e.g. Counterspell's Icon). DamageType is often absent: parse `DealDamage(…, Type)`;
  `Main*WeaponDamageType` → `Weapon`. 1,283 of 1,837 icons have ≥1 stats entry. Fields: Icon, SpellSchool, VerbalIntent,
  DamageType, SpellType, Level, SpellFlags, UseCosts, DisplayName/Description (handles).
- Loca: `...\BaseGameReference\English\Localization\English\english*.loca.xml`.
- D&D text: SRD 5.1 is CC-BY-4.0 (some spell names altered; credit line required). BG3 follows 2014 rules, so 5.1 is the right edition.

**Environment**
- RTX 3080 10 GB, 32 GB RAM, i7-5960X. Anaconda py3.11: torch 2.11, gradio 5.16, PyQt6, opencv,
  onnxruntime, transformers. Default `python` 3.14: Pillow 12.3 only.
- Pillow writes DDS **DXT1/DXT5** (verified), not BC5/BC7; no mip support assumed. Mod atlases:
  5eSpells 2048×2052, 12 mips; others 1-12 mips. Vanilla atlas 12 mips.
- Stability Matrix `~\Downloads\Stability Matrix\`: ComfyUI + InvokeAI;
  models: dreamshaper_7 (SD1.5), Lykon LoRAs `bg3_actions_offset` + `bg3_classicons_offset_mix2`
  (SD1.5, metadata stripped; CivitAI 114265 / 133406, trained with a green background for keying),
  Flux clip_l, t5xxl_fp8, ae (no Flux UNet).
- Web (2026-10): musubi-tuner recommends 12 GB for image LoRA (FLUX.2 dev/klein, Z-Image; block swap + fp8);
  OneTrainer has 8/12/16/24 GB presets (Z-Image, FLUX.2, SDXL); ai-toolkit targets 24 GB; SDXL LoRA ≈10 GB
  with kohya fused backward + Adafactor. LayerDiffuse: SDXL/SD1.5 native in ComfyUI, Flux via
  community TransparentVAE nodes, none for Z-Image.
  > NOTE / open validation: 10 GB fit for Z-Image / FLUX.2 klein at 512 px; licences (klein 4B and Z-Image reportedly Apache-2.0).
- Web (2026-10-16, model cards / docs, D39): `FLUX.2-klein-base-4B` and `FLUX.2-klein-4B` Apache 2.0 (~13 GB bf16,
  multi-reference editing), 9B non-commercial; diffusers 0.41 `Flux2KleinPipeline` (Qwen3 text encoder,
  `max_sequence_length` 512, `image=` references); BFL training docs: 4B needs 12 GB + 32 GB RAM, start at 512, style
  LoRAs 1,500-2,500 steps, lr 8e-5 to 1e-4; BFL blog: train on base, run the LoRA on the distilled model. `Z-Image`
  (base) Apache 2.0, 6B. FLUX 3 Image Klein (2026-10-15): 5.6B, FLUX Kommunity License. Qwen-Image-2.1: research-only.
- claude-mem 13.35.0: worker never started ("Bun runtime not found", `~\.claude-mem\logs`), no DB,
  so nothing captured since install (2026-10-11).

## Decisions & tradeoffs

| # | Decision | Why | Status |
|---|---|---|---|
| D1 | Model makes the transparent glyph only; bg, fade, sizes, DDS, mod files are code | backgrounds are separate compositing assets; hotbar = bg ⊕ glyph | settled (user + data) |
| D2 | Master = controller-style art (no bg, no fade) at 512² RGBA straight alpha. The model generates this; every variant is downscale + bg (hotbar) + **bottom-only** fade (tooltip). Training masters are built from the 380 tooltip **only for its resolution**: per-icon fade divided out, controller alpha/colour where the tooltip has none | 380 is the largest vanilla source; 512 suits the models | settled (user, 2026-10-14) |
| D3 | Colour follows a fitted grammar (family × intent × damage type); app checks it and can "snap" the glyph hue to it | colour is rule-bound; don't trust the model alone | fitted in 2.1: colour = 30 **preset gradient maps**; "snap" = exact re-tint (`grammar.tint`) |
| D17 | Colour is its own app field (any of the 30 presets), pre-set from intent/damage type (grammar default); the 90% colour gate moves to 5.3 as "generated colour = requested preset". Captions naming the colour: see D18 | labels predict the vanilla preset for 85% of hold-out spells; the rest is art direction; keyword/mechanics rules scored worse | **settled** (user "1A", 2026-10-14) |
| D18 | The model learns grey glyphs only: training masters are de-tinted (`grammar.detint`: lightness → grey level by the preset's lightness quantiles; **transparency kept as its own channel**) and the chosen preset is applied after generation (`grammar.tint`: colour from a lightness × opacity × distance-from-centre table, so the glow's own tint and radial hotspots come back). Captions carry shape, effect and **glow-style** words, no colour words (replaces D17's "captions name the colour"). Metamagic-style two-tone art: glyph trained, second colour not reproduced in v1 (superseded by D26: a second colour per stroke) | every vanilla icon is one glyph × one gradient (0.55 ΔE2000); round trip as seen on the hotbar dark, glow included, 0.5 ΔE2000 (per-icon p95 1.7); vanilla recolours 92 glyphs across presets; the user pointed out the glow structure (bright-core lines, emitted glow, hotspots, metallic basic actions), measured in 2.1 | **settled** (user "2A", 2026-10-14); **amended by D25**: the grey glyph the model draws is line art only, the glow comes from code, captions carry no glow words |
| D19 | Action hotbar **frame is its own app field** (the framed controller backgrounds), pre-set from the colour preset (`hotbar.json` `frames`, default first, alternatives ≥ 12%), same pattern as D17. Weapon red defaults to `control` (46%), `weaponAction` (43%) offered next | the preset picks the vanilla frame for most actions. The first "Weapon red splits pink / violet" was an RGB-MAE artefact: the user saw violet win by eye, CIEDE2000 agrees (violet `weaponAction` 65 of 71). Frames are now chosen by perceived colour (`hotbar.closest`) | **settled** (user "1A", 2026-10-14) |
| D20 | Colours no real frame matches (the game drew grey stone with a glow in the glyph's colour: Debuff magenta, Thunder violet, Radiant gold, Psychic pink…) default to a framed background **hue-shifted** to the preset's colour (`hotbar.shift`; a recolour in code of the game's own files, D10-safe), when it beats the best real frame by ≥ 2 median dE2000; also offered in the Frame field | Debuff magenta 10.7 → 4.2, Thunder violet 9.8 → 4.3, Radiant gold 7.4 → 4.4, Psychic pink 6.8 → 4.2 (median dE2000, glyph-free pixels) | **settled** (user "2A", 2026-10-14) |
| D21 | Action/skill icons only ever sit on **framed** backgrounds (`hotbar.FRAMED`, 14); the frameless ones (12 `*Passive`, `tadpole`) are not offered for actions. They mean passives, conditions and illithid powers (Phase 9) | user, 2026-10-14. Checked: of the 11 actions whose closest background was frameless, 10 show a frame in the game (Debuff magenta purple frame, Legendary gold, End-game ally; the recolour, D20, covers them); the 11th, `Action_Mag_Illithid_MindTax`, is an illithid power on the tadpole background (that family is outside v1) | settled (user) |
| D22 | Hotbar recipe **per colour**: the crisp recipe (v4: thinned glow, closed-shape tint, hue-kept darken-only sharpening) where it is closer to the game per pixel, last page's soft recipe elsewhere | crisp is closer for only 24% of 1,012 icons: wins Magic item 100%, Buff gold actions 90%, Wild Magic 89%, healing actions 62%; loses steel utility / Control rose / basic actions 0%, Summon amber 1%, Weapon red 17%, most spells. Crisp fixes Rush and Slash (the user's examples) but the game's lines are softer on most colours | **settled** (user "3A, but", 2026-10-14; the "but" = round 4 notes) |
| D23 | **Illithid powers are a v1 kind** ("Illithid power"): the 41 `TadpoleSuperPower_*` icons join the dataset, training and test set; on the PC hotbar they sit on the vein background (`tadpole`), as is for red powers, recoloured blue-grey for the silver ones; Mind Tax (`Action_Mag_Illithid_MindTax`) is drawn as one | the game puts 30 of 41 of them (and Mind Tax) on the veins; same glyph-and-glow art style; without training icons the app could not make one | **settled** (user, 2026-10-14, chose A in chat) |
| D24 | **Hotbar recipe v6 (round 5) is final for v1; 2.2 closes and work moves to 2.4 glyph structure.** The known hotbar gaps (2.2 "Round 5", "Left") stay as stated; reopen only if an in-game look at exported icons (Phase 3) shows one | the glyph is the product, the PC background secondary (ModernUI plays it down); round 5 test MAE spells 11.89, actions 14.53, each round's gain shrinking (round 4 → 5: −0.9 / −0.8) | **settled** (user "5A", 2026-10-15) |
| D25 | **The model draws line art only; code grows the glow** (amends D18): training masters = the lines only (`glyph.split` line share × master); after generation the colour's glow recipe (`glyph.glow`, `glow` / `borrow` in `data/glyph.json`, blurs ×4 at 512) is added, then `grammar.tint` colours it. Illithid powers get next to no glow because the game draws none (crisp alpha in tooltip and controller art; visible area 1.35× the lines vs spells 3.5×, actions 4.3×; their recipe is a 2 px fringe). Dark-line icons (Darkness, Darkness sorcery points, Darkvision, Ink Blot: the light is in the fill) cannot be drawn this way and leave the line-art training set | test icons: spells 1.2 L*, actions 3.0 (lines alone 9.3 / 11.1); crisp alpha makes Phase 5's alpha recovery simple (dark glows are invisible on black); every glow matches its colour; no glow words in captions. Cost: hand-painted action glows (Rush's red pool, Dash's offset shadow) become even halos | **settled** (user "1A", 2026-10-15; noted: no glow visible on Nebulous Black Hole, answered: the game draws illithid powers without one) |
| D26 | **Two-colour icons: a second colour picked per stroke** (amends D18's "second colour not reproduced in v1"). The app gets a Second colour field; the user clicks the strokes (connected line parts) that take it; each part is tinted and grows its glow in its own colour. Training de-tints each part with its own preset (`glyph.colour_split`). "Metamagic red" is retired: `TWO_TONE` icons (the 8 metamagic, `extract.py`) stay out of preset fitting, `grammar.json` `two_tone` lists their part presets (drop Control rose; symbol Action utility steel, Basic action white 2, Buff gold or Debuff magenta), and their hotbar frame is keyed "Two-tone" (`metaMagic` ×1.02: every metamagic PC cell's closest frame) | the 8 metamagic icons are v1's only two-colour icons (one-gradient miss p95 13-34 dE2000; next 14.3 but one hue inside the same strokes); every stroke is one colour (purity 1.00), each part an existing preset (≤ 3.4 dE2000); homebrew metamagic options are a real modding use | **settled** (user "2A", 2026-10-15) |
| D4 | Related passive/condition = same glyph recoloured to its own category, optional img2img variation | vanilla pairs do exactly this | **settled** (user "2A", 2026-10-15): the same line art recoloured in code, no img2img variation (33 vanilla cross-family pairs: same drawing, 26 recoloured, 24 same size ±5%, stroke kept); 7.3 |
| D27 | Training copies: every v1 icon kept, each same-drawing group (kappa ≥ .9, 32 groups / 82 icons) weighted 1/n; the 5 test icons whose drawing is in training scored apart in 5.3 / 6, not moved (proposed A; B one per group, C full weight) | grey line art (D18, D25) turns recolours into identical images; one per group would lose element symbols / runes | **settled** (user "1A", 2026-10-15); **amended by D33**: weights per series (1/sqrt(n) per drawing), a copy group shares its drawing's weight |
| D28 | Element symbol library: the 11 damage-type symbols (`GenericIcon_DamageType_*` line art, read from the user's game files, D10) stamped by code on generated line art via an optional Element symbol field (off by default), lines under it cleared, then glow + colour (proposed A; B the model draws them) | user note 2026-10-15; the game reuses one symbol per element across series (own element best match 38 of 66 series icons, median .80 vs .50), plain damage icons rarely carry it (3 of 201 by search + Poison Spray by eye) | **settled** (user "3A, but", 2026-10-15; the "but" = D29) |
| D29 | **The model makes new drawings in the game's style; only fixed parts are reused exactly**: the damage-type symbols (D28) and related copies of the user's own icon (D4). A generated icon is never a copy of a vanilla one: 5.3 scores each generated line art's closest training drawing (`relations.kappa`); the spread should match the test set's own (median .53, p90 .83, series siblings .75-.9), none ≥ .9 unless a series variant was asked | user: "while some elements like damage type symbols should stay exact/unchanged, the model should be able to create actual new icons using the style of the game" | **settled** (user, 2026-10-15); **amended by D42 / D43 (2026-10-17)**: house parts (D43) are reused exactly too, and an icon with a vanilla start is composed from it first |
| D30 | **Series composites in code**: a Based on field lists the game's element series (suggested when the typed name matches one, "Divine Strike: Psychic"); with a new damage type, code takes the sibling whose symbol is found best, keeps the series' base lines (in ≥ 80% of members) in the symbol's slot, places the new game symbol there at the slot's size, colours by the series' rule (element colour, or the series' one preset), grows the glow (`relations.compose`, `series_colour`, `paint`). Colour-only series (Glyph of Warding) and effect-drawing ones (Dragonborn breath) excluded (proposed A; B the model draws variants) | user note 2026-10-15; leave-one-out rebuild of every member from a sibling: kappa vs the real member median .91 (sibling as is .84), better in 140 of 155; Elemental Weapon weakest (.69, its own symbol drawings) | **settled** (user "4A", 2026-10-15); 7.5 |
| D31 | **Draft editor in v1, minimal tools**: add a game icon by name, pick strokes (click, shift-click, box), move / scale / rotate / flip / delete, stamp symbols, erase; the draft is either the final line art (exact) or the model's guide (img2img on grey lines or line-art conditioning, a follow-the-draft slider; method chosen in Phase 5). Parts from the user's game files (D10); freehand later; D29's new-vs-copy check shown, not enforced, for guided icons (proposed A; B after v1; C none) | user idea 2026-10-15; vanilla icons are drawn as separate strokes (median 14 connected parts, 99% ≥ 3), so a click picks a meaningful part; one-net drawings (Hex's heart) need the eraser; the same canvas serves D28's stamp and D30 | **settled** (user "5A", 2026-10-15); 5.3, 7.6; **amended by D42 / D44 (2026-10-17)**: the editor is the main path (composite-first), with a house-parts panel (D43) and the house brush in v1 |
| D32 | **Prompt and app fields follow the shape test** (2.6): captions keep intent, plus spell type on actions; school, area, level and action cost stay out of captions (4.2); the app drops the School, Level and Use cost fields and shows Spell type for actions only (proposed A; B keep 4.2's template with school; C intent only) | one icon per series: intent changes the drawing (spells guessed 26% vs chance 12%: debuffs symmetric emblems, mirror .85 vs damage .29), spell type on actions beyond intent (36% vs 27%, chance 25%: cones sweep diagonally with ~22 strokes vs 10, thinner), not on spells (30% vs 29%); school 14% vs 14% from intent; area, level, cost at chance. Per icon school looked shape-bound (Illusion = Disguise Self's 33 faces, Enchantment = Hex's hearts). **2.7 rerun with spell flyouts as series: spell type on actions weak (classifier 30% vs 27% from intent, nearest drawing only), school weak too** | **settled** (user "1A", 2026-10-15); 4.2, 7.1; **amended by D34**: spell type leaves actions' captions and the app too |
| D33 | **Training weights per series**, not only per copy group (amends D27): each drawing of a series of n weighs 1/sqrt(n), D27 copies still share theirs (proposed A; B 1/n; C D27 as is). Series = shared base (kappa .75+), same display name before ':', same `Spell_<School>_<Name>` stem, or one element series (`shape.series`) | per icon every field looked shape-bound (spell cost: nearest drawing 79% vs 56% shuffled), per series only intent and actions' spell type: big series teach caption words their own drawing. All 34 Disguise Self icons are utility spells: 33% of utility spell weight today, 10% with A, 2% with B. 1,083 icons = 712 series. **2.7: series also join spell flyouts (`extract.spell_containers`) and Reapply X with X (698 series); the weights also join frame families split over several series (`links.json` `frames`: Legendary 12, Paladin auras 5, Command Undead 5)** | **settled** (user "2A", 2026-10-15); Phase 6 |
| D34 | **Action prompt: source in, spell type out** (2.7): captions name every action's source (class, monster, end-game ally, legendary, magic item, race, weapon action; `links.sources`), the app gets a Source field for actions; spell type leaves the prompt and the app like school (proposed A; B source in, spell type stays; C D32 as is) | one icon per series, shuffled within intent: source guessed 32% vs 11% (chance 8%), nearest drawing 30% vs 8%; end-game allies 95% / legendary 100% nearest from their own source, magic items 51% (20%), Paladin 31% (9%), Bard 25% (3%); manoeuvres, weapon actions, beasts at chance. Spell type on actions weak once flyouts count as series | **settled** (user "1A", 2026-10-15, after a clearer explanation: two questions, example captions); D32 amended; 4.2, 7.1 |
| D35 | **Reapply variants made in code** (2.7): the 9 Reapply spells leave training (like D14's badges); Make related (7.3) offers a Reapply variant = the icon shrunk to ~72%, nudged down, the game's two-arc ring around it (from the user's game files, D10) (proposed A; B keep in training with a caption word) | rebuilt from the base with the ring of the other pairs: kappa .86-.97 (base as is .26-.38); the illithid Reapply Imperil uses corner sparkles instead (kept) | **settled** (user "2A", 2026-10-15); 6, 7.3 (all 10 Reapply icons are training icons: no test-set change) |
| D36 | **Every frame family in Based on series** (2.7, extends D30): the 19 families that keep an exact frame (Legendary, Arcane Shot, Paladin auras, Divine Intervention, Mantle of Majesty, Magic Circle, Eyebite, Contagion, Transmuter's Stone...); code keeps the frame, the new symbol comes from the damage-type library (element families), the model drawing only the inside (inpainting, 5.3) or the editor (D31) (proposed A; B element series only) | leave-one-out: every member draws 90%+ of its siblings' shared frame, the frame is 15%+ of its lines (median 98%); 2 of the 19 vary by element (D30 already) | **settled** (user "3A", 2026-10-15); 5.3, 7.5 |
| D37 | **Tooltip and controller art ship as new GUI textures** in the mod's own `Mods/<Mod>/GUI/Assets/{Tooltips/Icons,ControllerUIIcons/skills_png}` (+ half-size `AssetsLowRes`) + `Mods/<Mod>/GUI/metadata.lsf` entries, not loose under `Public/Game/GUI/Assets` (the old `bg3-icons` layout); the hotbar atlas stays under `Public/<Mod>` with map + TextureBank. DXT5 (UNORM) by our own encoder (`iconkit/dxt.py`) | Larian's Toolkit guide does exactly this (Convert UI Assets), and so do Patch 8's own 103 icons (their metadata = ours), 5eSpells (196 tooltips) and the 5e Subclasses mods; deploys loose with `-Junction` (Mods/<Folder>), while `Public/Game` needs a pak or an extra junction; `Public/Game` is only needed to replace a vanilla texture (UI guide, ModernUI 0.5). Patch 8's icons are UNORM (BC7), so no sRGB flag; DXT5 is accepted (164 vanilla tooltips). Pillow's DXT5 shifts line colours on hotbar cells (3.2) | **settled** (user, 2026-10-15) on that evidence; the in-game look moved to Phase 7's test |
| D38 | **Line test = global ramp and a local midpoint** (amends 2.4's lines, so D25's training line art and the 3.1 round trip): a pixel is line where its brightness over black is above .55 × the icon's p99 (2.4) **and** above halfway between its floor (min within 12 px at 512, capped at .5 × p99 so wide bright fills stay lines) and its peak (max within 20 px); soft edges = the stricter of the two ramps, computed at 512 and pooled at smaller sizes (`glyph.threshold`, `glyph.split`). The 2.4 glow fit composes like the shipping painter (`glyph.rebuild` = `variants.paint`: line art alpha = line share × alpha grows the coverage, the glow fills the rest); glow recipes refit | user notes 4 / 15 (Phase 4): painted glow between close strokes became line. Glow-made share of line pixels (alpha < .9) spells median .074 → .039 (67 → 19 icons at .15+), actions .045 → .019 (58 → 18), illithid .041 → .041 (no glow: unchanged); blob share (a 25 px disk fits in the mask) spells .255 → .125; Silencing Blade .16 → .01, Giant Subjugation .17 → .01, end-game crests .31-.48 → .01-.03; no stroke core lost; a stroke over black keeps the old mask (self-check). Still at .15+: weapon actions whose lower strokes fade in alpha (Opening Attack, Steady, Hamstring Shot: clean outlines, the measure's false positive) and Darkvision (dark lines, out by D25). 3.1 round trip (L*): spells 1.39 → 1.18, actions 2.77 → 2.84 (per icon 29 better, 24 worse, median change −.04), illithid 3.23 → 1.62, metamagic 2.90 → 3.07. Tried and dropped: white top-hat / midpoint over an opening floor (a disk fits inside thick strokes: thinned Fireball, cut the dark side of shaded illithid strokes, illithid cover .73-.89); midpoint .55 (illithid cover p10 .71); the refit with the old `rebuild` (spells 1.38, actions 3.11: it grew coverage from the line share, the painter from line share × alpha) | **settled, merged** (user "merge", 2026-10-16; side session for notes 4 / 15; crops `data/glow_leak_examples.png` in that worktree). Main's `glyph fit` + `variants test` rerun after the merge (same numbers). Relations (D27 groups 32 / 82 → 31 / 76, D29 yardstick .53 / .83 → .50 / .84), shape (2.6: 22 of 22 verdicts kept) and links reran on D38 lines (`kk/beautiful-torvalds-90cfb0`, merged; main's `data/` rerun too): no settled decision flips, figures under 2.5-2.7; captions' contact sheets not rebuilt |
| D40 | **Alpha read-back = max-RGB with one grey, k = .8, every kind** (5.1): the model's 8-bit image over black C → alpha = min(1, C / .8), grey = C / alpha; no matting net, no LayerDiffuse, no second channel | hold-out, round trip as seen over the hotbar dark, added to the true-line master: spells .30 L*, actions .32 (vs game 1.17 / 3.07; 3.1 1.18 / 2.84), plain max-RGB (k 1) 4.06 / 2.53; .8 is a sharp best (.7: .63 / .70, .9: 1.54 / .88). Illithid powers 4-5 L* at any k from .3 to .9 (shaded strokes: dark opaque = dim transparent over black); low k draws a dark rim round every stroke (seen in `outputs/alpha_illithid_look.png`, hidden by the L* measure over the dark stone), .8 looks like the true-line master. Fallback if 5.3's illithid outputs look off: alpha in its own channel | **chosen by Claude** (measured, 2026-10-16, part of D39's "best approach"); `research/probes/alpha_readback.py` |
| D41 | **Shipping generator = all-kinds LoRA step 2,500 at x2 on the distilled klein 4B, transformer stored in fp8** (diffusers layerwise casting, computed in bf16; LoRA loaded first and kept bf16) (5.3) | hold-out sweep, 184 icons per config (`research/probes/score53.py`): inverted (black on white) at x1.5 / x2 / x2.5: step 1,500 57 / 18 / 5, 2,000 5 / 0 / 0, 2,500 19 / 2 / 0, 3,000 34 / 6 / 1; 2,000 draws rough, spiky strokes (minotaur unreadable), 2,500 the cleanest and keeps the notched octagon frame 3,000 loses; unseen objects at x2: all 12 at 2,500 white on black, the basic-action ladder / padlock invert at 1,500 / 2,250 / 2,750 / 3,000. Novelty (D29) at every LoRA config: closest training drawing median .42-.48, p90 .55-.62, none ≥ .9 (test set .50 / .84); seen-drawing prompts .36-.55: no memorisation. fp8 storage: 3.9 GB on the card, peak 5.0 GB, 1.4 s per icon on the 3080, draws like bf16 (bf16 resident oversubscribed the 10 GB card next to Firefox: 13 s) | **proposed by Claude** (2026-10-16); **in doubt after blind test 1**: the user told 21 of 24 apart ("far too obvious"); the distilled model closes and symmetrises the drawings (enclosed regions 1 vs the game's 0, mirror overlap .49 vs .39), the base model with the same LoRA (x1, 28 steps, CFG 4, 18 s per icon) does not (mirror .35, taper .33 = game) but leaves softer edges (partial alpha .39 vs .17); blind test 2 on the base model: **24 of 24 told apart** (worse than the distilled 21), so the base model is not the fix and the distilled one stays the candidate; next: v2 LoRA, 4 passes (`train/klein4b_all_v2.yaml`) |
| D42 | **Composite-first generation** (design round, 2026-10-17): for a new icon the app first offers a vanilla start (element series D30, frame family D36, a sibling of the same series, house parts named in the motif D43), laid out as a draft in the editor (D31); the model then redraws the draft in the house style (follow-the-draft slider) or fills only what is missing (the inside of a frame); free text-to-image only when nothing fits | 44 of 92 hold-out icons have a vanilla start (D30 element series 9, D36 frame family 4, a series sibling in training 26, a copy of a training drawing 5; nothing 48); each blind grid had 11 of 24 such icons, generated freely (told apart 21 / 24 and 24 / 24; test 2 pair 19, Chromatic Orb: Thunder, is a D30 case); D30 rebuilds at kappa .90 to the real member, free generation .25 | **settled** (user "1A", 2026-10-17); amends D29, D31; 5.3, Phase 7 |
| D43 | **House-parts library**: every v1 master's line parts (median 15 connected parts per icon) grouped across icons into named house parts: ~5 figure styles (the blocky ally bust, Disguise Self's portrait template, the gesture figure, the frontal standing / meditating figure, the spread-eagled star figure), damage symbols, frames, orbs and circles, rays, sparkles, weapons, skulls, hands, ...; offered in the editor, named the same way in the motifs (the LoRA learns each as one drawing), reused exactly like the damage symbols (amends D29) | user 2026-10-17: "figures/silhouettes/humanoids have a few limited styles in which they are drawn whereas the generator always makes something different for each icon"; the 194 training icons whose motif names a figure (`research/probes/figure_sheet.py`) show the 5 styles, the ally bust repeated nearly unchanged on dozens of icons; 2.7's "no shared motifs" was a whole-drawing test, blind to shared parts | **settled** (user "2A", 2026-10-17); **amended (user, 2026-10-17)**: no names ("not accurate for basically any of them"): the parts panel is visual, each part shown in its best copy (whole shape, 5.4); no motif rename |
| D44 | **House brush in v1** (amends D31's "freehand later"): the user draws a centre line, code renders it as the house stroke (measured on real line art, `score53.py tells`: ~14 px wide at 512, ends taper to ~1/3 of the width, edge roughness ~.93, grey ~.91); hand-drawn parts match vanilla ones with no model; optional model redraw of the whole draft | user 2026-10-17 ("free-hand draw icons with the same stroke/line style as the vanilla icons") | **settled** (user "3A", 2026-10-17); Phase 7 editor |
| D45 | **v2 LoRA waits for the part names**: D43's names go into `iconkit/motifs.jsonl` first, then one 4-pass run (`train/klein4b_all_v2.yaml`, 16,500 steps, ~7 h) | v1 saw 0.6 of a pass; a caption change needs a retrain anyway, so one run instead of two | **settled** (user "4A", 2026-10-17); **void (2026-10-17)**: no part names, so v2 waits for nothing; it runs on the user's go with the Phase 4 captions |
| D46 | **App = an editor-centred local web app** (user's gist, Goal): a browser UI with a vector canvas (every vanilla icon, pick / delete / move / scale / flip strokes, a parts panel of best copies, house brush + line / circle / spline tools, the spell fields, a live preview of the in-game versions with glow + colour drawn by a WebGL shader from the JSON recipes, golden-tested against `variants.master`), and the existing Python `iconkit` as the backend (first-run extraction from the user's game files with each icon's strokes cut once, export, the model as an optional sidecar); a browser tab or a pywebview window; scikit-image off the runtime path (only `rgb2lab`, a formula, and `disk`) | user: "responsive/fast and multiplatform". Measured: Python glow + colour 391 ms at 512 (79 at 256), in-game versions 187 ms: fine for export, too slow per edit; the glow is two blurs + a gradient map (milliseconds on any GPU). NumPy 2.3 / SciPy 1.16.2 ship Windows ARM64 wheels, scikit-image unclear. A Rust (Tauri) app was considered and dropped: no Rust inference for FLUX.2 klein (Candle has none; OminiX-MLX is Apple-only), weeks of rewrite | **settled** (user "Start in a new chat" after the stack question, 2026-10-17); amends D5, D31, Phase 7 |
| D48 | **Updates = GitHub releases checked and installed from the app** (`iconkit/update.py`): a release is a zip of the code with a manifest of SHA-256s; the editor checks the newest release (one request, cached 6 h; a switch in the help sheet turns it off and then nothing leaves the computer), downloads it only when asked, verifies the zip and every file, and installs it on a restart (backup first, any failure puts it back, `rollback` by hand). Never touched: `data/`, `models/`, `outputs/`, `.venv/`, and data files the user changed (kept, the new copy saved as `.new`); code is always replaced. The user's edits to shipped lists (hidden / category of shapes) live in `outputs/editor/user/` in a release. `DATA_V` re-cuts the editor's data once when an update needs it. The launcher (8.1) runs `uv sync` at each start (new libraries arrive with the update) and restarts on exit code 75. A git checkout never self-updates | user 7.0i: "make sure the app can easily be updated when it's finally distributed"; GitHub releases are what BG3 Mod Manager and the Multitool use, free, with asset hashes; installing at start avoids replacing code while it runs | **built; releases on GitHub** (user 2026-10-19: "Publish releases on GitHub. I'll create the repository"): `REPO` is set once the repository exists; `.github/workflows/release.yml` publishes a release per version tag |
| D47 | **Install = a per-OS zip with a uv launcher** (`Start.bat` / `Start.command` / `start.sh`): the first run fetches a private Python + libraries into the app folder (no admin, no system Python, ~200 MB, online once), then extracts the icons from the user's BG3 install (auto-detected Steam / GOG paths); the model is an optional in-app download (PyTorch with CUDA ~2.5 GB + klein weights + LoRA; NVIDIA 8 GB+ or Apple Silicon); unsigned launchers warn (SmartScreen / Gatekeeper) unless signed; self-contained builds (PyInstaller / Briefcase) later if the zip proves too fiddly | as easy as BG3 Mod Manager or the Multitool (zip + double-click); no Larian art shipped (D10); the editor works fully without the model | **settled** (user, 2026-10-17); amends D5, 8.1 |
| D48 | **The model fills an erased area** of the editor draft: the user erases or masks a region (a frame's inside, the object a series swaps), the model inpaints only that region from the prompt (klein inpaint pipeline, LoRA, 4 steps, ~2.4 s per candidate), code puts the kept lines back on top; whole game-part drafts ship from code without the model, element symbols stay code (D28 / D30); free text-to-image only with nothing to start from (proposed A; B the model redraws whole drafts, follow-the-draft slider) | 5.3 draft test: given a whole draft the model copies it (to the draft .92-1.0, never closer to the game than the draft alone, .71 vs .69) and ignores a prompt asking for another object; masked inpainting draws the prompt's object (Pact of the Blade's trident, Hex's book, frame insides) with its inside as close to the game's as another member's own (.48-.50 vs .51; free .33) | **settled** (user "D48 A", 2026-10-17); 5.3, Phase 7 |
| D5 | Inference **inside the app** (diffusers + torch); model weights are a **separate, user-initiated download** (base model + our LoRA from HF/CivitAI); app zip stays small, torch installs on first run (uv) | user, 2026-10-14: "app and model are separate downloads, but the model runs in the app" | settled; **amended by D46 / D47 (2026-10-17)**: the model is an optional sidecar download |
| D6 | UI in Gradio (tabs, dropdowns, gallery built in; installed) | least code | proposed |
| D7 | Motif captions written by Claude in-session from labelled contact sheets | best on stylised glyphs, nothing to install | done (4.1, 2026-10-15: 1,083 motifs, `iconkit/motifs.jsonl`) |
| D8 | Base model chosen by bake-off (SDXL vs Z-Image vs FLUX.2 klein 4B), LoRA at 512, evaluated in diffusers | 10 GB VRAM; measure, don't guess; test in the shipping engine | **superseded by D39** (no 3-way bake-off) |
| D39 | **Base model FLUX.2 klein 4B, one LoRA; its reference images do the guided work.** Train the LoRA on `FLUX.2-klein-base-4B` at 512, ship it on the distilled `FLUX.2-klein-4B` (4 steps). Drafts (D31), frame families (D36) and room for a stamped symbol (D28) go through the model's own reference images (`Flux2KleinPipeline(image=...)`), no ControlNet / inpainting add-ons; an edit LoRA (draft → clean line art) only if references fall short. Alpha = read back from the line drawing over black (5.1 a); matting net and LayerDiffuse only if (a) fails. SDXL is the fallback if klein fails 5.3's gate or cannot train on 10 GB. Kept: line art only (D25), colour, glow, sizes and files in code. **5.2 (2026-10-16): the LoRA runs on the distilled model at strength 1.5** (1.0 left 2 of 6 sample prompts black-on-white; 1.5 none, ~6 s per icon on the 3080) | checked 2026-10-16 on the model cards / docs: klein 4B base + distilled Apache 2.0 (9B: non-commercial); diffusers 0.41 `Flux2KleinPipeline`, Qwen3 text encoder, 512-token prompts (SDXL 77: the longest captions lose their tail); text-to-image and multi-reference editing in one model; BFL: train on base, the LoRA loads on the distilled model, ~1 h on a 4090 (~$0.50 rented). Others: Z-Image base 6B Apache but no released edit / control model; FLUX 3 Image Klein (5.6B, released 2026-10-15) FLUX Kommunity License (free under $5M revenue, LoRA redistribution not stated, one day old: re-check later); Qwen-Image-2.1 research-only; SDXL OpenRAIL++, 77 tokens, 1024-native (512 is off its size) | **chosen by Claude at the user's request** (2026-10-16: "choose the best model/architecture ... the best approach in general"); 5.1-5.3 amended |
| D9 | Continuity: this file + project `CLAUDE.md` + memory pointer `bg3-icon-generator-project`; claude-mem not used | claude-mem broken (Bun) and logs actions, not decisions; user chose this, 2026-10-14 | settled |
| D10 | ~~Never ship Larian assets~~ **Amended 2026-10-19 (user): the icons ship.** Releases come with the editor's game data as a separate download (`data-v<N>` GitHub release, `iconkit/update.py` `build_data` / `fetch_data`: cut icons, thumbnails, shape cards, fitted colours / recipes, the 28 hotbar backgrounds), and the review images in `research/findings/` stay in the repository; the tool stays free and unofficial, with `NOTICE.md` (Larian owns the IP in anything derived from its art, per its fan content policy; the Wizards fan content notice; SRD 5.1 credit). User: "depending on what ends up being more convenient we may go back to getting the icons from the user's install" (8.3). The training dataset stays private; the LoRA is public | user: public from the start, 2026-10-14; read Larian's fan content policy and chose to ship, 2026-10-19 (BG3's own terms: free, you answer for infringement; neither page covers redistributing extracted files) | settled, amended |
| D11 | Public release targets: runs on 8 GB VRAM (quantised / offload), base model licence permits LoRA + output redistribution | other modders' hardware; licence hygiene | settled, verify in 5.2 |
| D14 | Numbered badge variants (71 `_N` icons) are left out of training and the test set; a badge, if ever needed, is stamped on in code | models copy badges unasked and draw numbers badly | settled (user, 2026-10-14, A1) |
| D15 | Controller export uses the PC colours; Larian's white/silver controller recolour of 18 weapon actions (and Stinking Cloud, 2 Contagion) is not reproduced | one look everywhere, nothing extra to build | settled (user, 2026-10-14, A2) |
| D16 | Colour outliers (75) stay in training; Phase 2.1 explains them (e.g. orange Utility weapon actions, blue Buffs) in the colour rules | real game art, keeps variety | settled (user, 2026-10-14, A3) |
| D13 | Tooltip fade = one clean bottom-only curve (`iconkit/fade.py`), a function of the row only; the measured 2D mask and per-icon vignettes are not reproduced | user, 2026-10-14: "a perfect fade from the bottom rather than this messy uneven mask" | settled |
| D12 | v1 = **Spells (`Spell_`) + Actions/skills (`Action_`, `Skill_`)**. Passives, status-only icons and derived passives move to Phase 9. Dataset still extracts every family | user, 2026-10-14 | settled |

## Answered questions (2026-10-14)

- Audience: public from the start (D10, D11). Backend: in-app inference, separate model download (D5).
- v1 families: spells + actions/skills (D12). Continuity: plan file + pointer (D9); user asked how
  claude-mem works (explained in chat; hooks verified in `~\.claude\plugins\cache\thedotmack\claude-mem\13.35.0\hooks\hooks.json`).

## Phases

### Phase 1: Dataset (`iconkit/extract.py`; writes `data/`, gitignored)
- **1.1** Parse stats with `using` inheritance (load order Shared < SharedDev < GustavX), resolve
  DisplayName/Description via loca, map icon → entries. Write `data/meta.jsonl`, one row per icon:
  name, family, entries, VerbalIntent, DamageType, SpellSchool, SpellType, Level, SpellFlags,
  UseCosts, name/description text, linked statuses/passives.
- **1.2** Masters: un-fade tooltip 380 with the Phase 0 fade profile (refit in 2.3), take controller
  alpha (upscaled) where ratio < 0.3, upscale to 512 → `data/masters/<icon>.png`.
- **1.3** SRD 5.1 spell list (name, school, level, damage, text) → `data/srd_spells.json`, matched by name.
- **1.4** Tags: numeral badge, multi-hue, dark fill, excluded families (Surface, statIcons,
  TadpoleSuperPower; GenericIcon kept as intent reference).
- **1.5** Hold-out: 10% of spell-like icons, stratified by intent × damage type → `data/holdout.txt`.
- Test: counts match the facts above; master → 380+fade vs vanilla tooltip mean |Δ| ≤ 3/255;
  master → 144 vs vanilla controller ≤ 8/255; 24-icon contact sheet for the user.
- **Results (2026-10-14, after the anomaly fixes):**
  - 1.1 `data/meta.jsonl`: 1,838 icons, 1,283 with stats (= Phase 0), 1,262 named. Spell-like
    (Spell/Action/Skill) with a master: 1,045; 321 of them have no VerbalIntent (252 no stats entry,
    69 entries without the field). Label rules (fixed after the anomaly review):
    - Main entry (name/description): among entries sharing a name word with the icon, SpellData >
      InterruptData > PassiveData > StatusData, then best name match, roots, shortest. Fixes e.g.
      Warding Flare (was "Bomb"), Wrathful Smite (was "Bane's Wrath"), Animate Dead: Zombie (was
      "Lovely Assistant"). Spells outrank a better name match on purpose: vanilla's `FireShield_Warm` file
      shows a snowflake and is used by the spell "Fire Shield: Chill" (its passive/status use it as Warm).
    - Other labels are voted only among entries that agree with the majority VerbalIntent (Jump was
      "Utility · Bludgeoning" from 4 of 30 entries; Entangle, Crown of Madness lost stray damage types).
    - `GenericIcon_DamageType_X` / `GenericIcon_Intent_X`: label from the name, text cleared (their
      entries are random monster spells). Larian's `%%% ` prefix and `EMPTY` names are stripped.
  - 1.2 1,405 masters (all non-excluded families with both tiers). Per-icon fade field (normalised
    convolution of tooltip/controller alpha, σ 12) divides out vanilla's own fade, soft hand-over to
    controller alpha where the fade is < 0.4. Tooltip RGB is undefined under alpha ~0 (BC7), so colour comes
    from the controller there. 200-icon check with the D13 curve: **controller mean 3.73, p95 4.52 /255
    (gate ≤ 8) ✓; tooltip on bottom-fade icons mean 2.14, p95 4.78 (mean ≤ 3) ✓**; vignette icons 18.1.
  - 1.4 tags: excluded 337, numeral_badge 114 (name `_N`, confirmed on the sheet: "II" and Portent "14"),
    multi_hue 2 (second hue peak ≥ 45° away; fire gradients are adjacent hues so not tagged), dark_fill 42.
  - 1.5 `data/train.txt` 890 + `data/holdout.txt` 84 (8.6%; strata of size ≤ 4 round to 0); the 71
    numbered badge variants are in neither (D14). Near-identical twins: 0 split across the two lists.
  - **Patch 8 added (2026-10-14):** meta 1,949 icons (1,386 with stats), **1,508 masters** (+103; 200-icon check controller
    2.94, tooltip 2.14 /255), v1 icons 1,112 → **train 951 + hold-out 90**. `step_holdout` now keeps every icon's earlier side
    (84 of 84 old test icons kept, 0 moved) and tops each stratum up to 10% from new icons only (6 new test actions).
  - 1.3 source: `https://raw.githubusercontent.com/5e-bits/5e-database/main/src/2014/en/5e-SRD-Spells.json`
    (611 KB, 319 spells, SRD 5.1 CC-BY-4.0; downloaded with user OK 2026-10-14) → `data/srd_spells.json`
    + `srd` key in meta. Name matching drops sub-options (`: …`, `(…)`), Reapply/Recast/Activate/Dismiss,
    owners ("Melf's"), British -our, plus a small alias table (Enhance Ability options, Blindness, Enlarge).
    **301 spell-like icons (293 `Spell_`) → 181 SRD spells.** Remaining misses are non-SRD spells
    (Hex, Witch Bolt, smites, Armour of Agathys…), so custom fields are the path for those.

#### Dataset anomalies (2026-10-14; `python -m iconkit.report` → `data/anomalies.html`)

The report leads with decisions A1-A3 as cards (examples, options, recommendation), then "Already
handled" and "Notes for later" as collapsible rows. Image checks are cached in `data/image_checks.npz`
(recomputed automatically when any master is newer; ~8 min, otherwise seconds).

Counts are over the 1,045 v1 icons unless stated. "Fixed" = extraction bug, corrected above.

| Finding | n | Cause | Handling |
|---|---|---|---|
| No stats entry | 252 | Action 175 (Mag 58, Monster 32, EndGameAlly 15, Legendary 11…), Spell 70, Skill 7 | image + hand caption (Phase 4) |
| Stats but no VerbalIntent | 69 | SpellData 23, InterruptData 19 (reactions have no such field), passives/statuses | caption; maybe infer from linked status |
| Damage intent, no damage type | 4 | Minotaur Brutal Leap, Hook Horror Pounce, Dispel Evil and Good: Dismissal, Glyph Explosive Runes | leave empty |
| Conflicting intents across entries | 24 | e.g. Jump Utility 26 / Damage 4; Glyph Detonation Control 4 / Utility 4 (tie) | majority vote; fine |
| Missing name | 1 | `Action_WildMagic_Heal` | caption |
| Labels from unrelated entries | 74 names (all families), 16 damage types | wrong main entry, stray damage types, GenericIcons, `%%%` | **fixed** |
| Colour outlier in its group (> 60° from group mean) | 75 | Utility 27 (21 orange, 6 red vs blue), Buff 20 (16 blue/cyan vs orange), Bludgeoning 6, Control 6… | kept, Phase 2.1 explains (D16) |
| No dominant colour | 31 | basic actions (Dash, Disengage, Help, Hide, Shove, Throw, Jump) + Perform/songs: white/grey with dark fill | Phase 2: an "achromatic common action" style |
| Vanilla tooltip vignette | 110 | per-icon art | not reproduced (D13) |
| Master ≠ vanilla controller (> 6/255) | 23 | **vanilla recolours on controller**: 18 weapon actions white/silver vs red on PC; Stinking Cloud pink vs yellow; Contagion ×2; 2 marginal | PC colours everywhere (D15) |
| Art touches the 4 px border (> 10%) | 38 | full-bleed vanilla art (songs, Perform, weapon actions) | keep |
| Numbered variants | 71 | base art + painted "II"/number | left out (D14) |
| Dark fill / two hues | 38 / 2 | style variety (Darkness, Darkvision; Metamagic Empowered/Heightened) | keep, tagged |
| Near-identical art (RMS ≤ 15/255 at 24 px) | 35 in 17 groups | `_Bonus` twins, numbered variants, Lava/Fire Elemental; no exact copies; **0 train/hold-out leaks** | keep (weight later if needed) |
| No master possible | 27 v1 | 26 exist only in the hotbar atlas (64 px, bg baked in), 1 has no tooltip | skip |
| Thin classes (< 15) | | Piercing 13, Thunder 12, Acid 8, Slashing 7; Rush 7, Throw 5, Wall 5, Teleportation 4 | Phase 2 leans on the UI palette |

Decided by the user, 2026-10-14 ("1A 2A 3A"): A1 → D14 (badge variants out), A2 → D15 (controller
in PC colours), A3 → D16 (outliers kept). `report.py` shows them as decided (`DECIDED` at its top).
Visual check sheets for any icon list: `python -m iconkit.sheet OUT.png ICON... | @list.txt`
(tooltip | controller | master | alpha, labelled).

### Phase 2: Icon rules ("grammar") → `data/grammar.json` + `research/findings/grammar.html`
- **2.1** Palette: hue/sat/val of glow vs core per (family, intent, damage type); compare to UI palette;
  separate control-pink / psychic-pink / debuff-magenta. Explain the 75 colour outliers (D16: they stay
  in training): weapon/physical actions orange whatever the intent? Buffs drawn blue? White/grey
  basic actions (31) as their own style. Start from the report's decision-3 groups + `iconkit.sheet`.
- **2.1 results (2026-10-14, `iconkit/grammar.py`, fitted on train only):**
  - **Every vanilla icon = one monochrome glyph × one colour preset (a gradient map).** Per icon, colour as a
    function of lightness alone (mean a*b* per 5-L* bin, `curve` in `data/colour_features.json`) reproduces every
    opaque pixel to a median **0.55 ΔE2000** (p90 1.35). A group's shared curve: 0.72; the best other group's: 4.0.
    Hues land on exact values (300.0°, 350°) for the same reason. One preset is a true multi-hue ramp (end-game
    allies: red → orange → yellow).
  - **30 presets**: average-linkage clusters (≥ 3 icons) of training-icon curves, threshold 3 ΔE2000 (34 at 2, 26 at 3
    on train+test, 20 at 6). Names = most common group, or an Action family owning ≥ half (Wild Magic, Magic item,
    End-game ally, Glut spores, Metamagic, Divine Strike, Legendary), or "Basic action white" for grey ramps.
    Distinct presets the 13-hue palette had merged (user caught it): Control rose ≠ Force red ≠ Weapon red;
    Spell utility cyan ≠ Action utility steel; Spell healing turquoise ≠ Action healing green; Summon amber ≠ Buff
    gold ≠ Fire orange; two Radiant golds; Lightning blue ≠ Cold blue.
  - Group → preset table (`groups` in `data/grammar.json`, default first, alternatives ≥ 12%). **Default preset right:
    hold-out spells 84.8% (28/33), actions 82.1%; train spells 84.8%, actions 62.5%** (actions: monster/pet abilities
    default to Summon amber whatever their intent, Wild Magic has its own preset). 96.4% of hold-out icons are within
    3 ΔE2000 of a preset.
  - **Recolour in code** (`detint`: lightness → grey level via the preset's lightness quantiles; `tint`: grey level →
    preset lightness → preset a*b*): round trip on hold-out **0.56 ΔE2000** (p90 2.4). Vanilla has **92 same-glyph
    pairs** (alpha IoU > 0.9 at 64 px) in different presets (Divine Strike ×7 elements, Glyph of Warding, Chromatic Orb,
    Dragonborn breath, elemental Slam); moving one into the other's preset in code gives median 6.2 ΔE2000 to the real
    icon, most of it the element symbol the game swaps (snowflake → flame), not colour.
  - **Glow** (user, 2026-10-14: lines brighter at their centre, glow emitted past the lines, bright spots, Metamagic
    two-tone, basic actions metallic). Measured (`glow_style`, 256 px, per preset median in `presets[].style`):
    line core gain (edge → centre L*) +16 to +32 for most spell presets, +3 to +8 for Weapon red, Action utility
    steel, Cold blue, Radiant gold, **about 0 for both basic-action presets** (flat, metallic); glow reach past the lines
    ~30 px at 512 for most, ~50 px for Weapon red / Magic item, 46 for End-game ally and basic actions, 42 Wild Magic.
    Brightness structure (bright cores, glow falloff, bright spots) lives in grey level + alpha, which de-tint keeps.
    Colour that depends on *where* a pixel is: the glow's own tint (Legendary: gold lines, orange glow; Weapon red:
    redder glow) and radial hotspots (End-game ally: yellow centre, pink rim). Tint table over lightness × opacity
    (4 cells) × distance from centre (4 cells), trilinear (no seams), cells < 20 px fall back to lightness only.
    Scored per preset, as seen on the hotbar dark, glow included (`scratchpad lut2.py`): all icons median 0.58 → 0.54;
    End-game ally 2.30 → 1.48 (p95 6.5 → 4.3), Legendary 1.29 → 0.73, Wild Magic 1.05 → 0.58, Thunder halo p95 2.0 → 1.3.
    In `grammar.py`: hold-out round trip **median 0.5, per-icon p95 1.7 ΔE2000**. Not one gradient (p95 > 10): the 4
    Metamagic icons only (red drop, blue flame at the same brightness).
  - **Refit with Patch 8 (2026-10-14): 31 presets**, the 30 unchanged (no earlier icon moved preset) + **Control rose 2** (4:
    Bladesong Finisher, Ki Resonation Blast/Punch, Telekinetic Bolt). The 66 new icons with a colour fall into existing presets
    (Weapon red 12, Control rose 10, Necrotic green 8, Action utility steel 8...). Default preset right: hold-out spells 84.8%,
    actions 75.8% (33 predictable, 6 new); train 85.3% / 63.0%. Round trip median 0.5, per-icon p95 1.8 ΔE2000.
  - **D26 refit (2026-10-15):** the 8 `TWO_TONE` metamagic icons left out of preset fitting (their mixed red + silver
    curves had formed Metamagic red, 4 icons): 31 presets; every other preset's curve, lightness map, colour table and
    member count identical, no group changed, only Action_Singing's nearest (unfitted either way) moved. Their parts
    (`two_tone`): drop Control rose 2.0-3.2 dE2000, symbol Action utility steel 0.6-1.3 / Basic action white 2 2.7-3.4 /
    Buff gold 1.0 / Debuff magenta 3.0. Train actions default right 63.0 → 63.3%, hold-out within 3 dE 96.7 → 97.8%.
  - **Round 4 refit (2026-10-14, illithid powers, D23):** clustered with everything, the 30 red powers renamed Force red to
    "Illithid" (Eldritch Blast, Magic Missile... under that name) and split Basic action white 2 (8 basic actions moved to a
    "3"). So presets are fitted on the other training icons (the 31 come back unchanged: curves, order, names) and
    illithid powers no preset fits within 3 dE form house presets of their own, appended: **Illithid red** (Ceremorphosis,
    Endless Rage, Sorcerer, Stage Fright, Thundering Vault, + Mind Tax, which moved from Force red: 2.32 → 2.14).
    Naming ignores illithid-art icons (`ILLITHID_ART` now in `extract.py`). Group `Illithid`: Force red 66%, Basic action
    white 2 21%, Illithid red 13%. Ink Blot (Control rose 4.9) and Illithid Powers (white 2, 4.0) are too far from any
    preset: left out of `grammar.json` icons like other unfitted icons. Force Tunnel and Supernatural Attraction join the
    Metamagic four as "not one gradient" (two-tone). Eval unchanged for spells / actions; illithid default right 62.5%
    train (any of its presets 97.5%).
  - Superseded first pass (hue only): 13 named hue colours, hold-out spells 84.8% within ±15° of the group's main hue.
    Kept facts: UI damage-type text colours (DefaultTheme) sit within 4° of icon hue except Necrotic (UI 101°, icons
    145°); Psychic vs Debuff differ by 12° of hue but are separate presets.
  - Outliers explained (`WHY` in `grammar.py`, shown on the page): protection/weapon-enchant "Utility" spells drawn as
    buffs; target-holding "Utility" spells as control; movement "Buff" spells as utility; petrify/sleep "Debuff" as
    control; terrain "Control" keeps a material colour; monster/pet actions Summon amber; Wild Magic its own preset;
    water attacks blue; spores Glut green.
  - Rules tried and dropped (scored on hue, train): description keywords (mobility 15 vs 19 right, restrain 6 vs 11,
    protection 23 vs 25, charm/fear 9 vs 14; only "wild magic" helped, vanilla-only). **Mechanics from stats**
    (functors + applied statuses' StatusType/StatusGroups/Boosts; scratch tagger, not in the repo) as a replacement for
    intent: worse (train spells 83.2% vs 88.4%). As overrides: only **"restrains/incapacitates the target → control"**
    helps (train +3/−1, hold-out spells 28 → 30 of 33); penalty → debuff +1/−17, empower → buff +5/−19, move → utility
    +1/−2. Candidate app rule for Phase 7 (needs an effect field or the description).
  - **Inferred art logic** (for captions and the app, Phase 4/7): colour = the category a player reads off the hotbar
    (preset per category, element preset only when the element is the damage dealt: Elemental Weapon variants stay
    Buff gold, Divine Strike variants take the element's preset); house presets by *who* acts (Wild Magic, end-game
    allies, magic items, legendary actions, Glut, metamagic; monsters default amber); spells and class actions are
    told apart for utility and healing; basic actions anyone can take are white; elemental series = shared frame
    glyph + swapped element symbol + element preset.
- **2.2** Backgrounds: spell → spell_bg; action = frame bg + glow (blurred alpha × tint, add/screen)
  fitted, and which frame bg goes with which action (UseCosts? weapon? intent?); 64 px downscale +
  sharpen fitted. (Passive 12-way rule waits for Phase 9.)
- **2.2 results (2026-10-14, `iconkit/hotbar.py`, fitted on train; vanilla = `Icons_Skills` atlas cells, UVs are inset
  half a texel so cells are snapped to the 64 px grid; scores = mean |Δ| /255 over the whole 64 px RGB icon):**
  - **Spells: `spell_bg` (whole 144 → 64)** wins on the glyph-free pixels for 420 of 443 spells (22: too little
    background left; 1 other). Glyph-free pixels 5.45/255 median per icon. The hotbar's own spell background is one
    image (3.4/255 from its per-pixel median), so the gap is texture detail of a different downscale.
  - **Actions/skills: frame = a framed controller bg × a gain, picked by the colour preset** (`frames` in `hotbar.json`),
    each icon's frame chosen by **median CIEDE2000** on the glyph-free pixels (`closest`). First pass used RGB MAE and got
    Weapon red wrong (pink `control` for 42 of 71); the user saw violet win by eye, CIEDE2000 agrees: **Weapon red →
    weaponAction ×0.83 (91%)**, Cold blue → utility. Summon amber → summon ×0.77 (100% of 98), Action utility steel →
    utility ×0.70 (81%), Buff gold → buff ×0.65, Control rose → control ×0.76, Basic action white → action ×0.93, Basic
    action white 2 → bonusAction, Magic item orange → fireDamage ×1.71, End-game ally → control ×0.42, Fire orange → summon,
    Action healing green → heal, Glut → monster, Metamagic → metaMagic. Presets with no action icons borrow the nearest
    preset's frames (`nearest`). The first look (Phase 0, fit4) cropped the bgs by 2 px and found no fit; uncropped they
    line up (frame-ring correlation 0.97). No other icon backgrounds exist in the GUI unpack (searched 2026-10-14).
  - **Recoloured frames (D20):** 9 colours no real frame matches (the game drew grey stone with a glow in the glyph's
    colour) default to a framed bg hue-shifted to the preset's hue (`shift`, CIELAB rotation; entry `[bg, gain, share,
    hue]`): Debuff magenta (lightening, 11.1 → 4.2 median dE2000), Radiant gold (lightening, 7.8 → 4.5), Divine Strike lime
    (control, 11.0 → 3.8), Thunder violet (control, 9.9 → 4.8), Acid yellow (control, 10.6 → 3.6), Necrotic green (buff,
    7.1 → 3.1), Psychic pink (fireDamage, 6.8 → 4.2), Piercing red (control, 6.7 → 4.4), Wild Magic cyan (summon, 7.6 →
    4.7, 19 icons). Rule: shifted beats the best real frame by ≥ 2 (`SHIFT_MIN`). Legendary gold: no shift helps.
    **Hold-out: the default frame (fixed gain) scores median dE2000 3.60 on glyph-free pixels, the per-icon best real frame
    (own gain) 3.61.**
  - **Glyph recipe** (`recipe` in `hotbar.json`, `KEYS`): premultiplied master, Lanczos to 64, unsharp mask; the soft glow
    keeps `glow_kept` of its colour (rising to all of it on the lines); then a **dark glow grown from the line cores**:
    core = opacity above `line_from`, halo = min(1, s · blur(core))^γ darkens the frame. Actions: line cores from 41%,
    s 1.67, blur 1.06 px, γ 0.51, glow colour kept 84%, unsharp 0.39 @ 1.46 px. Spells: from 66%, s 0.42, γ 0.42, glow
    kept 100%, unsharp 0.10 @ 1.08 px. Fitted on MAE + 0.5 × the brightness mismatch 1-4 px outside the lines
    (`PROFILE_W`, `line_profile`). **The first halo** (whole soft glow blurred and boosted: s 1.62, γ 1.36, blur 0.77 px)
    darkened 3-5 px past the lines; the user saw it as "too big / feathered" and described the game's as the spells' bright
    glow, but dark. Measured (L* above the bare frame at 1/2/3/4 px outside the lines, 176 actions): game −4.8 / −2.5 /
    +0.2 / +1.3, first try −3.7 / −1.6 / −0.9 / −0.4, **ours −4.4 / −1.5 / +0.3 / +1.2**, plain overlay +8.5 / +6.2 / +4.1
    / +2.2. The best function of opacity alone (per-bin LUT) reached only −1.9 at 1 px: the game's darkness follows the
    lines, not the soft glow's opacity. Spells: game +3.7 / +2.2 / +3.1 / +4.0, ours +3.6 / +2.3 / +2.3 / +1.6.
  - **64 px MAE, hold-out: spells 13.01 (p90 15.02; plain alpha-over 13.95); actions 15.51 (p90 20.35; plain over on the
    default frame 22.34).** Train 13.78 / 15.40. Both under the 18.1 gate (asserted in `fit()`). Check sheet
    `data/hotbar.png`, review page `data/hotbar.html`. **Largest visible gap left: line crispness** (the game's 64 px lines
    are thinner and sharper than our shrink; candidate: thin the alpha or sharpen at 512 before shrinking).
  - **Round 3 (2026-10-14; user: 2A, frameless = passives, "the dark red glow is slightly too big, reducing contrast
    within the lines" on Weapon red, line crispness, Patch 8):**
    - Frames: framed backgrounds only (D21, `FRAMED` 14). Legendary gold → action ×0.51, Force red → control ×0.56;
      Debuff magenta / Radiant gold keep their recoloured default, frameless alternatives gone. Hold-out: default = per-icon
      best real frame 74%, glyph-free dE2000 3.61 (best real 3.65).
    - Measured on train actions with the old recipe, L* above the bare frame at 1 / 2 px outside the lines, open space,
      game vs ours: Summon amber −13.0/−10.6 vs −10.7/−4.8; **Weapon red −0.7/+2.0 vs −2.8/−0.3** (the game keeps its red
      glow; ours too dark: what the user saw); Buff gold −4.4/−1.5 vs +1.3/+1.6; Basic action white −11.2/−7.4 vs
      −13.5/−9.8; Magic item orange −11.4/−7.2 vs −18.4/−9.4; Cold blue −4.0/−3.7 vs −0.2/+0.3. One shared dark edge
      cannot fit them (`scratchpad preset_profile.py`).
    - **Closed shapes** (`down()` channel 4: fill_holes of alpha > .5 at 512 after an 8 px closing): the game is +5.8 L*
      (actions) / +5.9 (spells) brighter there than in open space at the same distance, tinted within 30° of the glyph's
      hue for 77% / 94% (chroma ~15); 1-2 px inside, game −2.7/+0.6, old ours −5.7/−2.8. A wide blur of the glyph does
      not explain the actions' lift elsewhere (r ≈ 0): per-icon frame variation, not modelled.
    - **Crispness**: edge contrast (mean |Laplacian L*| within 2 px of the lines) ours ÷ game 0.84 actions, 0.82 spells with
      the old recipe; MAE alone always prefers blur.
    - Bake-off (`scratchpad variants.py`, fit on 1/5 of train, scored on another 1/5): a halo by distance (no stacking in
      narrow gaps) scored worse (spells 14.81 vs 14.26); a partly additive soft glow gained nothing; sharpening the finished
      icon (frame + glyph) instead of the glyph: actions 15.95 vs 16.31 but edges 0.94. Kept: halo from the line cores +
      closed-shape tint + sharpening fitted to the game's edge contrast.
    - First refit (per-preset dark edge, tint, edge term; commit 35003ae) matched the L* profiles yet **Rush and Slash
      looked the same and their MAE rose** (15.6 → 17.0, 15.2 → 16.3). Counting pixel classes per Weapon red icon showed
      why: pale line-core pixels (L* > 75) game 479 / ours 577, saturated dark-red glow (L* 25-45, C* > 35) game 534 / ours
      890: our glow was too wide and the glyph unsharp mask fattened the cores (the refit made both worse, it only saw mean
      L*). Same 20% surplus of core pixels on every preset. No sharpening gives game-like cores but soft edges.
    - Fix (scratch `counts.py`, `darken_sharp.py`, `v4_proto.py`): **darken-only sharpening of the finished icon**, masked
      to ~2 px around the glyph (unmasked it speckled the stone): crisp dark rim, cores untouched (Weapon red cores 459 vs
      game 468); **soft glow thinned** (opacity^p, p ≈ 1.25-1.4): dark-red glow 610 vs game 544. Line erosion at 512 also
      thins cores but per-preset optima differ (Summon amber overshoots), not used. Rush 17.0 → 13.9, Slash 16.3 → 14.2;
      over all Weapon red, MAE 18.2 → 18.9 but the (L*, chroma) histogram distance 0.60 → 0.47: crisp-but-slightly-shifted
      costs MAE that blur hides.
    - **Recipe v4** (`parts`): KEYS + `fill`, `glow_thin`; glyph thinned → frame × tint × (1 − halo) → glyph over →
      darken-only sharpen (`sharpen`, `sharpen_px` now mean this). Loss = MAE + 0.5 × L* profile mismatch at 1-4 px per
      region (open, narrow gaps, closed; `regions()`) + 10 × |log edge-contrast ratio| + **10 × (L*, chroma) histogram L1**
      (`hist`, `HIST_W`); then **per colour preset** with ≥ 15 training icons of the kind, `PER_PRESET` (frame brightness,
      sharpening, dark-edge strength and blur, glow kept, glow thinning, tint) refit on its icons (`recipe_for`).
    - Legendary gold: no framed background or recolour matches (best real 7.4 vs recoloured 9.0 dE2000; the game's frame is
      bright gold); 9 of its 12 icons cover the frame, so the darkened plum frame stays the default.
    - Results: see the Status log entry of this round.
  - **Round 4 (2026-10-14; user "3A, but"):** notes on 6 pairs (their odd images = game cells, even = our v4 render, matched to
    0.00 / 0.24): glow too strong, the game shows the stone through it (Maiming Strike = `Action_CripplingStrike`, inside the
    axe); our colour ramp flatter, cores less white and deep parts lighter than the game's (Mantle of Inspiration, Dimension
    Door); a missing bright spot ("or a vignette"); hence dull icons (Divine Strike Radiant Ranged, Dazzling Breath =
    `Action_DragonForm_ScintillatingBreath`); illithid powers need their vein background (Mind Tax). User question: is the
    light not in the controller/tooltip art too? Answered with the measurement below (no). Probes: scratch `probe5-8.py`,
    `proto5*.py` (session scratchpad; rebuild from this text if needed).
    - **Centre light, PC version only.** Mean (game − ours) L* over each preset's icons: a round bright spot centred on the
      square, every preset, both kinds. Per icon, a centred round Gaussian (σ 0.45-0.6 half-widths, peak +11 to +13 L*)
      explains R² 0.12 actions / 0.17 spells; square 0.11 / 0.16; light following the glyph (blur of its opacity) 0.06 /
      0.07. At the centre the lift grows with brightness (+5 L* at L* 25, +10 at L* 85): part gain, part lift. **Not in the
      controller art**: on opaque line pixels (controller alpha > .9 at 64 px, background hidden), PC − controller L* by
      distance from the centre (0-0.2 … 1.0-1.4 half-widths): actions +3.8 +2.6 +0.9 −1.0 −2.5 −3.8, spells +7.4 +4.8
      +1.9 −2.6 −8.7 −19.0 (a strong corner vignette); the controller's own lines are flat (L* 79-80 actions, 81-82
      spells). Bare frame pixels vs a plain overlay: +9.6 at the centre → −1.3 at the edge (actions).
    - **See-through glow.** Slope of the game's fine stone detail (σ 1.2 high-pass) on the frame's own, glow pixels ≥ 2 px
      from the lines, by master opacity .03-.1 / .1-.2 / .2-.35 / .35-.5 / .5-.7: actions game .89 .74 .60 .53 .52, ours
      (v4) .77 .66 .49 .33 .25 (glow too opaque: what the user saw); spells game .93 .76 .55 .44, ours 1.06 1.08 .95 .70
      (too transparent). A plain overlay predicts 1 − opacity; the game's actions keep more stone at high opacity.
    - **Line colours** (opaque lines, master → game PC): game brighter (actions median +3 to +11 L*), less saturated (C*
      Summon amber 31 → 19, Weapon red 55 → 38, Control rose actions 24 → 11, Debuff magenta actions 40 → 17), steeper
      (game L* on master L* slope 1.15-1.5). Part of it is the centre light (middle lines brighter, outer ones darker);
      separate after the light is fitted before adding a line-colour term.
    - **Illithid powers** (D23): 30 of the 41 `TadpoleSuperPower_*` cells and Mind Tax are closest to `tadpole` (median
      dE2000 3.2-6.4, next background 6.2-8.0). Red powers (colour preset Force red, 31; Stage Fright: Control rose 2) sit on
      `tadpole` ×0.97, same hue and chroma. Silver powers (Basic action white 2, 10: Absorb Intellect, Displacer Beast Shape,
      Freecast, Illithid Powers, Fly, Luck of the Far Realms, Mind Sanctuary, Favourable Beginnings, Shield of Thralls,
      Transfuse Health) sit on the veins recoloured blue-grey: hue ≈ 274° (CIELAB), chroma ≈ 0.27 of the red veins', ×0.45. No
      blue vein file exists in the unpack. `TadpoleSuperPower_ForceTunnel_2 / Repulsor_2 / StageFright_2` are new drawings
      (alpha IoU with the base 0.12-0.17; real badge copies ≥ 0.42).
    - Prototype (scratch `proto5.py`: v4 + glow coverage + centre light; fit on 1/5 of train, scored on another 1/5): v4 on
      the score set, actions MAE 16.24, colour mix .594, edge .99, residual by ring +6.4 +3.9 +0.9 −0.9 −2.5; spells 13.72,
      .390, 1.00, +6.9 +4.1 +0.1 −1.4 −0.4. Fits from a zero start left the light at 0 (Nelder-Mead's first step from 0 is
      0.00025). Full 16-number refit (1,500 steps, light at 0): score set worse (actions MAE 16.26 → 16.59, colour mix .56 →
      .64; spells 13.72 → 14.01) and **cover stayed ~1**: MAE punishes stone texture that sits slightly off, so it hides it.
      Only the 5 new numbers, non-zero starts: actions light ×1.03 centre / ×0.97 corners (σ 37 px, too wide), MAE 16.24 →
      15.71 but the centre residual stays +5.6 and colour mix .59 → .62; spells: no useful light (14.00). **Why: one light
      over the finished icon cannot fit both**: the bare frame needs about +10 L* at the centre, the lines only +4 (actions)
      / +7 (spells) with darker edges (spells −19 in the corners). Next try: light the frame under the glyph (frame ×
      (1 + a·spot) + b·spot) plus a weaker light/vignette over everything, and a texture term in the loss (game vs ours
      stone-detail slope per opacity bin) so the glow can become see-through.
      **Texture term tried** (+10 × mean |slope ours − game| over the opacity bins, full refit, light still at 0): it works.
      Stone shown through the glow at opacity .2-.35 / .35-.5 / .5-.7, actions ours .77 .52 .31 vs game .74 .67 .65 (v4 .64
      .42 .19), cover 1.32; spells .87 .72 .52 vs game .78 .58 .47 (v4 1.07 .94 .69), cover 1.42. Cost: actions MAE 16.26 →
      16.80, spells 13.72 → 13.74; colour mix .56 → .62 and .39 → .40; edge .96 / .92. Keep it, and judge by eye on the page.
    - **v5 prototypes (2026-10-14, scratch `proto6-8.py`, fit 1/5 of train, scored on another 1/5; shared recipe vs round 3's
      per-colour recipes):** the cached objective (`Ref`) reproduces the Round 4 baseline exactly. Residual split by pixel
      kind (game − ours L* by ring 0-.3 … 1.05-1.5 half-widths): round 3 actions stone n/a +4.3 +0.9 −1.0 −2.1, lines +7.9
      +6.1 +3.5 +1.2 −0.2; spells stone ≈ 0 everywhere, lines +8.9 +5.9 +0.5 −6.4 −19.5. So a light over everything (proto6)
      lit the spells' stone too (stone centre −10 after the full refit) → **v5b: the stone light under the glyph + a light on
      the glyph only**, plus **line colours** (contrast, colourfulness, lift of the glyph's straight colour) and a **line term
      in the loss** (`LINE_W` × |Δ mean L*| + |Δ spread of L*| + |Δ mean chroma| of opaque lines; MAE barely sees them).
      proto8 (v5b) stage B vs round 3: actions MAE 16.24 → **15.23**, colour mix .618 → .573, line errors (L*, spread, chroma)
      4.3 / 2.4 / 5.9 → 2.5 / 2.9 / 2.1, stone detail by glow opacity .99 .85 .65 .44 .25 → 1.09 1.00 .81 .63 .49 (game 1.05
      .90 .75 .70 .55), ring all +6.4 +3.9 +0.9 −0.9 −2.5 → +3.4 +1.9 +0.1 −0.6 −1.9, lines centre +7.9 → +0.2 (line
      contrast ×1.45: the steeper ramp the user saw), stone centre +6.1 (light on stone weak, ×1.05). Spells 13.72 →
      **13.05**, colour mix .421 → .405, lines 1.8 / 3.5 / 6.2 → 1.6 / 3.3 / 3.5, stone 1.06 1.07 .94 .69 → .96 .91 .78 .57
      (game .96 .78 .58 .47), ring all +6.9 → +2.0, stone centre −3.2; spell line corners stay −19 (few pixels, not fitted).
    - **Illithid PC cells are often enlarged** (smoke test: illithid MAE 23-27, worse than a plain overlay): L* correlation
      of the game cell with our master at size 1 vs enlarged (`same_size`, scratch `artscale.py`): every spell and action
      matches at size 1 (no zoom gains > .05); **16 of 41 illithid powers are the same drawing enlarged ×1.1-1.2** on the
      PC hotbar (Black Hole .31 → .92 at ×1.2, Mind Blast, Charm, Perilous Stakes...) and Levitate is redrawn. Per icon, so
      not part of the recipe: `fit()` leaves such cells out of frames, fitting and test numbers (`eval.not_same_size`).
    - **Full fit (v5, 2026-10-15):** test MAE spells 13.28 → **12.81**, actions 16.31 → **15.32** (round 3 = v4 crisp; round 2 soft: 13.01 /
      15.51); training 13.89 → 13.24, 16.39 → 14.91. Edge contrast 1.00 both. Stone detail by glow opacity, spells ours .89 .76 .59 .32 vs game .91 .73 .56
      .38; actions 1.03 .93 .74 .58 vs 1.04 .86 .71 .66. Lines (median L* / chroma, game · round 3 · now): actions 86/26 ·
      78/33 · 88/29, spells 84/30 · 82/37 · 85/32; a few action colours now overshoot line brightness by 5-7 (Summon amber,
      Action utility steel). Shared recipes: spells crisp (light: stone ×1.12, glyph ×1.06 centre / ×0.97 edges; line
      contrast ×1.05, colourfulness ×0.89), actions crisp (stone ×1.13, glyph ×1.05 / ×0.98; line contrast ×1.37,
      colourfulness ×1.06). D22 per colour: spells crisp except Debuff magenta; actions soft for Summon amber, Action
      utility steel, Basic action white, End-game ally, crisp for the rest (Weapon red now crisp: 17.08 vs 17.39). The
      user's six pairs all closer: Maiming Strike 20.2 → 19.2, Mantle of Inspiration 18.6 → 14.8, Dimension Door 11.7 →
      10.1, Divine Strike Radiant Ranged 21.1 → 19.3, Dazzling Breath 21.7 → 20.7, Mind Tax 23.2 → 13.5 (veins).
      Illithid powers: frames Force red / Illithid red veins as they are (×0.95 / ×0.90), Basic action white 2 veins
      recoloured to −87°, chroma ×0.29 (dE 17.8 → 3.8); recipe fitted freely (soft; training 15.38, plain overlay 19.03):
      lines paler and flatter than the game's white cores. Tried and dropped: the action glyph recipe with only background
      and glow keys refit (training 20.3, saturated red lines). Light spreads clamp at `MIN_LIGHT_PX` 8 (a fit had shrunk the
      stone light to a 2 px dot).
    - Code so far: `extract` (illithid family in v1; numbered name = badge copy only with the base's art, IoU ≥ `BADGE_IOU`
      .3, no existing icon changes side), `grammar` (kind Illithid; keys `Illithid/<intent>` then `Illithid`, so Mind Blast
      stays red, not psychic pink), `hotbar` (`kind()` with illithid + `ILLITHID_ART`, `frame()` per kind via
      `frames_illithid` / `nearest_illithid`, `shift(..., chroma)`, frame entries may carry a 5th field chroma, `parts()` v5
      keys cover / light / light_px / light_edge / light_add / unsharp with 11-key v4 recipes padded neutral, `START`,
      `PLAIN`, `PER_PRESET`, `SOFT`). `fit()` / `report()` still v4 + no illithid frames.
  - **Round 5 (2026-10-15; user notes on the round-4 page, the same six icons):** Maiming Strike "still a little dull, like
    the glyph/lines are missing a bright spot in the middle"; Mantle of Inspiration "the vanilla version has a deeper red
    glow, ours pink-ish"; Dimension Door "slightly less bright in the centre"; Divine Strike Radiant Ranged and Dazzling
    Breath "the background seems brightened, like the glyph is emitting light"; Mind Tax "missing contrast between the
    middle of the lines and the outer edges; the gaps between the veins are darker". Question: what the long runs are
    spent on (answered in chat and on the page: no model training yet; the hotbar fit is a search for ~25 recipe numbers
    per colour, every try re-renders 100-190 icons). Probes (session scratchpad; rebuild from this text): `r5_look.py`
    (the six by pixel kind), `r5_pool.py` (kept as `research/probes/colour_residuals.py`), `r5_scan.py` (nudge the lights,
    print every loss term), `r5_align.py` (sub-pixel / zoom alignment), `r5_preset.py` (one colour's refit, NM vs Powell),
    `r5_ill.py` (illithid on lined-up cells), `r5_compare.py` (game | round 4 | now sheets).
    - **Measured (round 4 fit, per colour, all usable icons):** game − ours L* by ring (0-.3 … 1.05-1.5 half-widths):
      actions' glow and line rims +3 to +9 at the centre while their opaque cores were already 1-6 too bright; Weapon red
      stone +12 at .3-.55; spells' lines +3 to +10 at the centre, −17 to −22 in the corners. Glow chroma: the game's
      20-45% above ours for most colours (Control rose actions 35 vs 26, Debuff magenta actions 42 vs 27, Thunder violet
      actions 48 vs 25) while our line middles were too colourful (Control rose actions 44 vs 37). PC hue offsets (glow /
      line middle, game − ours): Control rose actions +7.9 / +7.1°, Cold blue actions +14 / +28, Lightning blue actions
      +7.6 / +11.6, Fire orange actions −9 / −5. 19 colours with 5-14 icons drew with the shared recipe (Radiant gold
      actions: +17 L* on the glow at the centre, and no dark edge in the game). Illithid line middle − rim: game +19 to
      +21, ours +6 to +8; vein contrast (far-stone L* slope on the frame's) game 1.02-1.10, ours .94.
    - **Alignment:** spells and actions line up at (0, 0) (best sub-pixel shift for 100% / 99.5% of 341 checked); illithid
      cells: L* correlation .70 as is → .91 with zoom .95-1.25 and shifts up to 1 px (25 of 41 move). Now `register()`
      before fitting (REG_MIN .85: 38 used, 5 left out: Charm, Cull the Weak, Levitate, Mind Sanctuary, Psionic Backlash).
    - **Why the centre light stayed weak:** nudging the round-4 recipe (`r5_scan.py`): spells, light +.2 / edge −.1 → MAE
      13.59 → 13.16 but the edge-contrast and profile terms rose; actions: opaque lines already too bright, more light =
      worse everywhere. Nelder-Mead's first simplex is 5% of each start value: hue 1° → 1.007, light .07 → .08 in 300
      iterations. Powell with per-key steps at the same budget: Radiant gold loss 38.0 → 32.4 (NM 33.5), test 19.6 → 16.8
      (NM 18.8); Control rose test 15.5 → 15.2 (NM 15.6).
    - Tried and dropped: fitting each action on its own closest real frame (14 of 33 Control rose icons change frame;
      MAE 14.65 → 15.40 before any refit: a median-dE pick on few glyph-free pixels is noisy; Mantle got fireDamage).
    - **v6 recipe** (`parts`): keys `glow_sat` (glow colourfulness over the lines', clamped ≥ 0), `hue` (turn about grey,
      degrees; PC only), `bloom`, `bloom_px` (the glyph's glow colour blurred and screened over the icon); loss + |mean
      a*, b*| of the opaque lines and |mean L*, a*, b*| of the soft glow (`GLOW_A` .1-.5), weight `LINE_W`; `PER_PRESET` +
      light_edge, frame_light, glow_sat, hue, bloom, bloom_px; `SMALL_KEYS` for `MIN_SMALL` 5-14 icons (kept only when
      the loss drops); Powell (`pw`, `STEP`) for every search; `fit presets`; colour refits in `POOL` 6 processes; master
      cache (`load_masters`, `CACHE_V`). Basic action white's glow_sat fitted −1.28 (flips a near-grey tint): clamped to 0
      (its 22 icons' MAE 8.636 → 8.635) and stored as 0.
    - **Fit (2026-10-15):** `fit illithid` 22 min 45 s (13 min building the cache, the illithid shared refit ~7), then `fit
      presets spell action` 9 min 54 s (36 colours, masters from the cache). Test MAE spells 12.81 → **11.89**, actions
      15.32 → **14.53** (training 13.24 → 12.56, 14.91 → 14.30); illithid 15.49 on 2 test icons (training 15.13; round 4's
      recipe on the same lined-up cells: Force red 14.93 → 14.84, Illithid red 15.97 → 15.84, silver powers 16.00 →
      13.50). Small colours: 21 kept their own numbers; 12 of the 13 with test icons got closer there (Cold blue spells
      14.8 → 15.2 the exception). The user's six: Maiming Strike 19.2 → 18.6, Mantle of Inspiration 14.8 → 14.5,
      Dimension Door 10.1 → 9.3, Divine Strike Radiant Ranged 19.3 → 16.6, Dazzling Breath 20.7 → 18.5, Mind Tax 13.5 →
      16.0. Rings: spells' lines at the centre +2.6 → −0.5, corners −20 → −16.5; Spell utility cyan centre +4 → −2.5.
      Illithid core − rim: game +23, round 4 +7, now +22; vein contrast game 1.00, round 4 .94, now 1.01. Glow chroma
      moved toward the game's for every colour with 8+ icons (Control rose actions 28 → 30 of 35, Debuff magenta spells 19
      → 25 of 26); Control rose actions' hue gap 8.2° → 4.0°.
    - **Left (known gaps, stated on the page):** Maiming Strike: Weapon red's fit kept nearly the same light (glyph ×1.06 →
      ×1.08 at the centre); the game stays ~4 L* brighter on Weapon red lines at the centre and Maiming Strike ~11 (its
      dark axe drawn lighter on the PC icon than in the controller art: 2.3+ px inside the lines game 49.5, controller
      42.2, ours 43.4). Mantle: closer but pinker; its game stone is near grey (chroma 2.5) where the Control rose default
      frame has 10 (44% of Control rose icons sit on another frame; the Frame field, D19). Radiant gold: bloom unused
      (0.01), the stone light (×1.29) carries the lit look, the game's stone around the glyph stays more saturated gold.
      Mind Tax: white cores and dark glow match, its glow is less red (chroma 39 vs 43, hue 29° vs 27°). Illithid numbers
      are extreme (cover 13.4, i.e. the clamp 5; centre light ×2.6) on 34 training icons. Spell corners −14 to −17 L*.
- **2.3** Fade: DONE (D13, `iconkit/fade.py`; re-measure after a patch with `extract fadefit`).
- **2.4** Glyph structure: single-hue share, white-core decomposition error, dark-fill share, stroke width.
- **2.4 results (2026-10-15, `iconkit/glyph.py`; `python -m iconkit.glyph fit` ~4 min with `POOL` 6 → `data/glyph.json`,
  `... report` → `data/glyph.html`, `... check` self-check; scratch probes `g24_measure/lines/glow/upper/ring/show.py`):**
  - Single-hue share and white cores were settled in 2.1 (one gradient per icon, 0.55 dE2000; de-tint round trip 0.5).
  - **"Dark fill" is mostly dark glow.** Alpha > .6 is not the drawn lines on actions: their masters carry an opaque dark
    glow around the lines (Dash, Bursting Arrow: alpha ~.9 at L* < 30), invisible over black. Share of opaque (alpha >
    .9) pixels with L* < 30: median 0 for spells and most action colours, ~0.1 Weapon red, 0.46 Basic action white; 125 of
    1,083 icons above 5%. True dark-line icons (black lines on a lit fill): Darkness, Darkness sorcery points, Darkvision,
    Ink Blot.
  - **Lines** = brightness over black B = L*/100 × alpha above .55 × the icon's p99 (soft ramp .45-.65): traces the
    drawn strokes on every style checked except dark-line icons (sheet `lines1.png`). **Amended by D38 (2026-10-16)**: and
    above the local midpoint between floor and peak, so painted glow between and around close strokes stays out; refit
    numbers: test spells 1.14 L* (lines only 9.76), actions 2.79 (11.21), illithid 1.84 (2.07); stroke p5/p50/p95 spells
    10.8 / 14.0 / 18.0 px, actions 10.0 / 13.4 / 17.2, illithid 8.2 / 10.8 / 16.1 (the halo rims were counted as stroke);
    metamagic still the only two-colour icons (next Giant Subjugation 15.6, purity .65). Probe
    `research/probes/glow_leak.py`. The figures below are the pre-D38 ones.
  - **Line weight is a house constant:** median stroke width (2 × distance to the edge on the skeleton, 512 px) spells
    p5/p50/p95 11.7 / 15.2 / 20.1 px, actions 10.0 / 14.0 / 18.4, illithid 8.2 / 11.9 / 16.1 (≈ 1.8 px at 64); every
    colour's median 10-18. Placement: line box 0.90 (spells) / 0.93 (actions) / 0.83 (illithid) of the square, margin
    20 / 13 / 37 px, light centre 0.05 half-widths off the middle. `glyph.json` `ranges` = p5/p50/p95 per kind (app check).
  - **The glow can be grown from the lines in code.** Per colour: light = light1 · G(blur1) ∗ lines' light + light2 ·
    G(blur2) ∗ ..., coverage = (cover1 · G(blur1) ∗ line share + cover2 · G(blur2) ∗ ...)^gamma (dark glows = coverage
    without light), fitted with Powell on |ΔB| + |Δalpha| at 128 px (≤ 24 icons per colour, 60 per kind). Mean |ΔL*| seen
    over the hotbar dark where either shows anything, test icons: **spells 1.20 (lines only 9.25), actions 3.01 (11.08),
    illithid 2.03 (4.17)**. Upper bound (each icon its own numbers, 40 per kind): spells 0.85 vs shared 0.91, actions 2.34
    vs 2.92: spell glow is a function of the lines; actions keep per-icon painting (Rush's red pools under the figure,
    Dash's shadow is offset). By distance from the lines the averages match (Weapon red within 4 L*, 5 chroma per ring;
    Fire orange spells within 1). Colours with < 8 training icons borrow the kind's recipe that fits their icons best
    (the closest gradient curve picked a bright glow for Basic action white 2's dark shadow: 8.0 → 3.3); Mind Tax counts
    as illithid (4.8 → 1.6). Worse than lines alone: only Darkness and Darkness sorcery points (dark lines).
  - Decision 1 on `data/glyph.html`: A = the model draws line art and code adds the glow (recommended), B = the model
    draws the glow too (D18 as is). User: 1A → D25.
  - **Two-colour icons = the 8 metamagic icons only** (user, 2026-10-15, with the 8 images: "the question of metamagic
    icons"). `glyph.colour_split`: lines' miss of a one-gradient fit (a*, b* per 5-L* bin) p95 13-34 dE2000 for them; next
    Giant Subjugation 14.3 but its 2-means sides mix inside strokes (purity .63: one hue at two strengths, which the tint
    LUT's opacity × radius cells cover); median icon 2.75. Every metamagic stroke takes one side (purity 1.00), so the
    parts split without painting (whole connected line parts, glow pixels to their nearest line). Parts vs presets: drop
    Control rose 2.0-3.2; symbol Action utility steel 0.6-1.3 (Careful, Distant, Quickened, Subtle), Basic action white 2
    2.7-3.4 (Extended, Twinned), Buff gold 1.0 (Empowered), Debuff magenta 3.0 (Heightened). "Metamagic red" (4 icons)
    is a curve of their mixed red and silver. 2.1's other "not one gradient" pair (Force Tunnel, Supernatural Attraction)
    is plain red (miss 4.7 / 2.6). Decision 2 on the page: A = a second colour picked per stroke (recommended), B = one
    colour per icon in v1; either way training de-tints each part with its own colour and Metamagic red is retired.
- **2.5** Relations: mine spell ↔ passive/action/status pairs by shape (alpha IoU), not only by name.
- **2.5 results (2026-10-15, `iconkit/relations.py`; `python -m iconkit.relations run` ~1.5 min → `data/relations.json`,
  `... report` → `data/relations.html`, `... check`; scratch probes `r25_*.py`):**
  - **Shape score = kappa**: 2.4's line mask at 64 px; share of each icon's line pixels within 1 px of the other's, both
    ways, minus what the same amount of line at random places scores, over 1 minus that; max of as placed and each scaled
    to its line box. All 1.2 M pairs: median .20, p99.9 .65. **≥ .9 = same drawing** (copies, recolours, re-placed,
    small symbol swaps; every pair on the check sheet), **.75-.9 = shared base or look-alike** (frame with a swapped symbol,
    or dense bursts vs stripes). Plain tolerant overlap without the chance term scored stripes vs a sunburst .84; alpha
    IoU (2.1) is worse still: of 2.1's 124 "same-glyph" pairs only 30 are the same drawing by lines (87 shared base), big
    glows overlap whatever is drawn.
  - **v1 copies: 32 groups, 82 icons** (12 are recolours of one drawing, kappa ≥ .97 throughout): Glyph of Warding runes
    ×6, elemental MultiAttack ×5, Divine Strike critical ×4, Disguise Self races ×4, Divine Intervention ×3, Myrmidon ×3...
    One per group would drop 50 of 1,083. **5 test icons have their drawing in training** (Divine Strike Radiant
    Critical, Wholeness of Body, Lava Slam, Sunbeam, Grant Flight): fine for colour / recipe tests (another colour in
    train), a memory test for the model. Decision 1 (D27).
  - **Across families: 33 same-drawing pairs** (spell → action / passive, action → passive, GenericIcon): 26 recoloured
    into the related icon's own colour, 24 at the same size ±5% (scale p10/50/90 .93 / .99 / 1.0), stroke weight kept
    (ratio .97). Only 18 share a display name (Blade of the Rime = Ice Knife, Djinni Thunderwave = Thunderwave, Wild
    Magic Gas Cloud = Fog Cloud); of 243 same-name cross-family pairs only 18 are the same drawing. Decision 2 (D4).
  - **Statuses:** of the statuses a v1 spell / action applies that show an icon (989), 56% use the spell's own icon,
    21% a sibling's (Horde Breaker ranged → melee), 23% condition icons (`Status_`, `statIcons_`, `GenericIcon_`); the 399
    without an icon are hidden (`DisablePortraitIndicator` 396). → 3.3 default: a new status uses its spell's icon.
  - **Element symbols (user note: "cold = snowflake, poison = skull + crossbones"):** 13 series named by damage type
    (Divine Strike ×3, Chromatic Orb, Elemental Adept, Protection from Energy, Elemental Weapon, Elemental Cleaver,
    Glyph of Warding, Dragonborn breath, Wasteland Wanderer, the two storm passives) vs the game's 11 damage-type icons
    (`GenericIcon_DamageType_*`). Sliding search (symbol skeleton at 25-100% size, chance-corrected by the window's
    stroke density): own element best match in 38 of 66 series icons, median .80 vs .50 for the best other element.
    Misses: Glyph of Warding (colour only), Dragonborn (draws the breath), Divine Strike physical (own emblem), very small
    symbols. Plain damage icons: 3 of 201 by search (Spiteful Suffering, Conjure Fire Elemental, Lightning Bolt) + Poison
    Spray by eye; Cone of Cold / Ray of Frost draw their own snowflakes. Tried and dropped: cutting symbols out as the
    lines a series does not share (frames spoil it, 28 of 64), normalised template correlation (1.00 anywhere at small
    sizes), 2 px tolerance (other-element median .50 → .73). Decision 3 (D28).
  - **New vs copy yardstick (D29):** each test icon (without the 5 copies) against its closest training drawing: kappa
    median .53 (p10 .39, p90 .83); 17 of 87 at .75+, all series siblings (Divine Strike elements, Hex abilities, Disguise
    Self races, Flesh to Stone / Gold). `relations.json` `novelty`.
  - User 2026-10-15: "1A 2A 3A, but ..." → D27, D4, D28, D29 settled; `DECIDED` set, page rebuilt with the yardstick row.
  - **Series composites (user note: "Divine Strike but with psychic damage"):** `find_symbol` now returns the symbol's
    slot (top, left, size at 128 px); `composite` keeps the series' base lines in the slot and places the new game symbol
    at the slot's size; `compose` picks the sibling whose symbol is found best; `paint` = glow (D25) + tint (D18).
    Leave-one-out over 8 series (155 rebuilds): kappa vs the real member median .91 (p10 .82), the sibling as is .84,
    better 140; per series composite / sibling: Divine Strike .91 / .85, Protection from Energy .94 / .81, Elemental
    Adept .91 / .71, Chromatic Orb .86 / .65, Wasteland Wanderer .90 / .89, Elemental Weapon .69 / .66. Rendered:
    Divine Strike Psychic / Force / Acid, Chromatic Orb Psychic / Necrotic / Radiant / Force (page decision 4).
    Series colour: per element where the members differ (Divine Strike, Chromatic Orb), else one preset (Protection
    from Energy gold). Names follow "Series: Element", so a typed name finds its series.
  - **Draft editor (user idea):** v1 icons have median 14 connected line parts (p10 6, p90 35; 99% ≥ 3) at 512 px:
    clicks pick the sword, rays, frame, symbol strokes; one-net drawings (Hex's heart) need an eraser
    (`relations.parts_image`, page decision 5).
  - **Rerun on D38 lines (2026-10-16; old file `relations.pre-d38.json`): no decision flips.** Kappa over all pairs
    p50/p90/p99/p99.9 .198 / .318 / .442 / .648 → .182 / .291 / .402 / .620 (sparser line maps), thresholds .9 / .75 kept
    (`check` passes). **D27 copies 32 groups / 82 icons → 31 / 76** (one per group drops 45, not 50). Every change but one
    is a pair on the .9 line moving .005-.03: Phalar Aluve ×3 (Sing-Melody .904 → .899) and Blur / Wild Magic Blur
    (.916 → .885) leave; Divine Strike Critical loses Poison (.901 → .879), Conjure Elemental Air, Disguise Self Human
    Male. New: **Flesh to Gold / Flesh to Stone .829 → .994** (the leaked glow was the difference), so **6 test icons**
    have their drawing in training (+ Flesh to Stone). **D29 yardstick** (86 test icons, was 87): median .53 → **.50**,
    p10 .39 → .36, p90 .83 → **.84**; 15 at .75+ (was 17); nearest drawing changed for 28 of 92, mostly end-game allies
    and monsters whose glow pattern no longer counts as line (Watch Summon .68 → .43, Vampire Creatures .60 → .42).
    Across families still 33 same-drawing pairs (Deflect Missiles .912 → .875 and Blur out; Regain HP = healing
    GenericIcon .879 → .904 and Opportunity Attack .832 → .914 in), 27 within 5% of the size (24), stroke ratio p50
    1.00 (.97), 17 share a name (18). Statuses unchanged. **Element symbols (D28): own element the best match in 44 of
    66 series icons (38)**, found in 28; Conjure Elemental Fire higher level now shows its symbol. **D30 composites:
    median .903 (.908), p10 .817, sibling as is .849 (.841), better in 160 of 182 rebuilds (140 of 155: more symbols found,
    so more members can be rebuilt)**; Elemental Weapon still weakest (.698). Line parts per icon p10/50/90 7 / 15 / 37
    (6 / 14 / 35), 99% ≥ 3.
- **2.6** Do school / SpellType / AoE change shape? (radial symmetry, fill ratio, centroid). Keep in
  captions/UI only if they do.
- **2.6 results (2026-10-15, `iconkit/shape.py`; `python -m iconkit.shape run` ~10 min → `data/shape.json` +
  `data/shape.npz`, `... report` → `data/shape.html`, `... check`; scratch probes `s26_census/probe/montage.py`):**
  - Shape = 17 numbers on the line art (2.4's lines at 128 px): fill, line box and aspect, centroid, spread, angular
    spread, elongation and orientation (/ vs \, upright vs lying), mirror (left-right, top-bottom), point and rotational
    symmetry (kappa of the boxed line map vs its flips / turns), strokes, closed-shape share, stroke width. Plus the
    kappa-nearest drawing (2.5). Test per field: balanced accuracy of a 5-fold logistic regression on the numbers and of
    the nearest drawing's label, vs the same with the field shuffled among icons of the same intent (area: same spell
    type); verdict yes = both p < .05, weak = one. Fields: school (spells), SpellType, area (stats: Zone / Wall,
    AreaRadius or ExplodeRadius > 0), level (cantrip / 1 / 2-3 / 4-9), action vs bonus action; kind and intent as controls.
  - **Counted per icon, every field looks shape-bound; it is series.** Illusion averages to a face (Disguise Self: 34
    icons, 33 faces, all one utility spell), Enchantment to a heart (Hex ×7) and hands (Command ×5), Abjuration to a ring
    (Magic Circle ×4, Protection from Energy ×6). D27's same-drawing groups (kappa ≥ .9) miss them: the faces are
    different drawings. Series (`shape.series`) = shared base (kappa .75+) or same display name before ':' or same
    `Spell_<School>_<Name>` stem or one element series: 712 series for 1,083 icons; biggest Disguise Self 34, Divine
    Strike 26, Wild Magic 22, Wild Shape 19, Pact of the Blade 10, Find Familiar 10, Conjure Elemental 10.
  - **One icon per series** (classifier / nearest drawing, vs shuffled within intent): kind .61 / .48 (chance .33);
    intent spells .26 / .25 (chance .12), actions .23 / .19; **SpellType actions .36 / .34 vs .27 / .27 → yes** (Zone:
    diagonal sweep, median 22 strokes vs 10 for Target, 12.6 vs 14.4 px; Projectile thinner strokes 12.7 px); SpellType
    spells .30 / .27 vs .29 / .26 → no; school .14 / .19 vs .14 / .14 → no; area spells no, actions weak (nearest drawing
    .58 vs .50, classifier .50); level no; action vs bonus action no (spells .55 / .57 vs .51 / .50, actions at chance).
    Debuff spells are symmetric emblems (mirror .85, upside down .61 vs damage .29 / .22). No field moves the centroid.
  - Page decisions: 1 = D32 (prompt and app fields), 2 = D33 (training weights per series). User "1A 2A" → both
    settled; 4.2, Phase 6, 7.1 amended. 2.6 closed. (2.7 reran it with flyouts as series: see below.)
  - **Rerun on D38 lines (2026-10-16; vs the 2.7 run, `shape.pre-d38.json` / `.npz`): all 22 verdicts kept.** Series
    698 → 700 (Harm leaves the healing series of Cure Wounds / Regain HP; Gortash's Flame Thrower Tile splits from Flame
    Thrower); every-icon tests 1,033 → 1,038 icons (fewer D27 copies). One per series (classifier / nearest drawing vs
    shuffled within intent): intent spells .212 / .229 (was .217 / .237, chance .125) yes, actions .206 / .202 (.196 /
    .184) yes; spell type on actions .294 / .354 vs .259 / .258 weak (nearest drawing p .01); spell type on spells no;
    school .126 / .212 vs .125 / .134 weak (nearest drawing only, p .015); area spells no, actions weak; level no; cost
    no. Features: line fill median .171 → .157, stroke 14.1 → 13.4 px, symmetry scores −.02 (mirror, rot180, radial),
    parts 14 → 15. `check` passes.
- **2.7** Connections audit (user request, 2026-10-15: "go through the spells/wiki to double check if there are any other
  connections between icons that would affect how we train or if it can be done programmatically").
- **2.7 results (2026-10-15, `iconkit/links.py`; `python -m iconkit.links run` ~4 min → `data/links.json`, `... report` →
  `data/links.html`, `... check`; scratch probes `c27_stats/measure/rows/source/reapply/frames.py`):**
  - **Stats links.** Spell flyouts (container spell + options, `ContainerSpells` / `SpellContainerID`,
    `extract.spell_containers`): 38 families, within kappa median .57 (random .19); 5 were split over several 2.6 series
    (Ranger's Companion over 6, Perform 4, Wild Shape 2, Enlarge / Reduce, Seeming). `using` inheritance is mechanics
    (108 groups, kappa .24: `Target_MainHandAttack` carries Divine Strike, manoeuvres, dipped weapons). `shape.series` now
    joins flyouts and Reapply X with X: 712 → 698 series. 2.6 rerun: spell type on actions yes → weak, school no → weak,
    the rest unchanged (old numbers kept as `data/shape.d33.json`).
  - **Source of each action** (`links.sources`): class / subclass / race from Progressions.lsx (SpellLists, PassiveLists,
    passives' UnlockSpell), items that unlock it (MAG_ = magic item, plain weapons = weapon action), names (Monster,
    EndGameAlly, Legendary, Mag, WildMagic, class names, wild-shape beasts), bg3.wiki for the 21 Battle Master manoeuvres
    (legendary actions = boss abilities, several Honour mode only). 503 of 639 v1 actions labelled (79%). Test as 2.6 (one per series,
    shuffled within intent, 13 sources, 304 actions): classifier 32% vs 11% (chance 8%), nearest drawing 30% vs 8% → yes.
    House styles: end-game allies (95% nearest from their own), legendary (100%, one gold frame), magic items, Paladin,
    Barbarian, Bard; none for manoeuvres, weapon actions, beast attacks. Spells not tested (186 of 233 on several lists).
  - **Variants.** Reapply spells (9) = base shrunk to ~0.72, ~3% lower, inside a two-arc ring: code rebuild with the ring
    of the other pairs kappa .86-.97 (base as is .26-.38); Reapply Imperil (illithid) uses corner sparkles. Ranged twins
    (27): the melee composition with a bow / arrows (kappa .67, one series each). Dismiss icons: the subject dissolving into
    sparkles, mostly blue (a convention, not a stamp).
  - **Frame families** (`links.frames`): candidates = flyouts, series, name prefixes (141); frame = lines in 80% of the
    other members; kept when every member draws 90%+ of it and it is 15%+ of the lines: 19 families, 94 icons (Legendary
    12, Arcane Shot 8, Mantle of Majesty 6, Contagion 6, Paladin auras 5, Command Undead 5, Divine Intervention 4, Magic
    Circle 4, Transmuter's Stone 4, Eyebite 3...); 2 by element (D30). A median rule let loose families in (Pact of the
    Blade's hand). 3 are split over several series (Legendary 12) → D33 weights join them.
  - **Not found:** motifs shared across series beyond the damage symbols (bears, wolves, greatswords, fire elementals are
    redrawn per series); Command vs Mantle of Majesty commands are redrawn (kappa .21-.26).
  - Page decisions: 1 = D34 (action prompt: source in, spell type out), 2 = D35 (Reapply in code), 3 = D36 (frame
    families in Based on series). User "2A 3A", then "1A" after decision 1 was explained again → all settled; 4.2, 5.3, 6,
    7.1, 7.3, 7.5 amended. **2.7 closed; Phase 2 done.**
  - **Rerun on D38 lines (2026-10-16; vs the Phase 4 run, `links.pre-d38.json`): no decision flips.** Sources unchanged
    (game data). **D34 source test** (401 actions one per series, 18 sources, chance .056): classifier .230 → .204,
    nearest drawing .269 → .269 vs .067 / .057 shuffled within intent → yes. Nearest drawing from the same source:
    legendary 1.0 (1.0), Paladin .42 (.31), Monster .38 (.30), Basic action .27 (.18), Monk .22 (.11), magic items .33
    (.48), **end-game allies .60 (.90)**: their crests' shared painted glow (D38: glow-made line share .31-.48 → .01-.03)
    was part of that house style. Within-group kappa: flyouts .561 (.574), `using` .210 (.237), ranged twins .663
    (.672), random .176 (.194). **D35 Reapply code rebuilds .84-.97 (.86-.97)**, base as is .25-.32 (.26-.38), scales
    unchanged. **D36 frame families 19 → 20 (94 → 100 icons): Dragonborn breath joins** (6 icons over 2 series, element;
    the dragon head is the frame, 36% of the lines, recall min .93; the breath differs per element). The leaked glow
    between the head's close strokes kept it under the 90% bar. D30 leaves Dragonborn out of element composites (draws
    the breath, no symbol); D36 now takes it in as a frame family (code keeps the head, the model draws the breath):
    consistent with D36, flagged for a user look (sheet: the worktree's `data/dragonborn_frame_family.png`; `links.html`
    shows example families only). Element families 2 → 3, families over 2+ series 3 → 4. `check` passes.
- Test: on hold-out, palette hue within ±15° for ≥ 90% of spell icons; spell recomposite residual
  ≤ vanilla Phase 0 level (11.7-18.1/255); action recomposite residual target set after the first fit.
  2.2: spell hold-out 12.98 ✓; action target set to the same 18.1, hold-out 15.71 ✓.

### Phase 3: Variant exporter, no model (`iconkit/variants.py`)
- **3.1** master → controller 144 (PC colours, D15), tooltip 380 + `fade.bottom_fade` (D13), hotbar 64
  (`hotbar.compose`: frame by family + preset, D19; halo + sharpen). First the generated line art becomes a master
  (D25): its colour's glow is grown from the lines (`glyph.glow`, recipe `data/glyph.json` `glow` / `borrow`, blurs ×4 at
  512), then coloured: `grammar.tint(grey, alpha, preset)` (D18). Two-colour icons (D26): the user's strokes
  (`glyph.colour_split` sides on vanilla) are tinted and grow their glow in the second colour; hotbar
  `compose(..., second=)` puts them on `frame_two_tone` (`metaMagic` ×1.02), recipe of the first colour. Test: vanilla
  lines only → master ≈ vanilla master (metamagic included, part by part).
  - **Done (2026-10-15), `iconkit/variants.py`.** Line art format (what the model will draw) = RGBA 512: grey level in RGB
    (`grammar.detint` in the colour it was drawn in), alpha = line share × master alpha (`glyph.split` AL × a). `master()`:
    light of the lines (preset lightness × alpha) → glow grown from them (`glyph.glow`, scale 4) → lines over the glow →
    one `grammar.tint` at the final alpha (as 2.1 fitted the presets). Two colours: each stroke set painted alone, every
    pixel takes the part of its nearest line. `variants()`: controller = premultiplied Lanczos to 144 (`extract.resize`),
    tooltip = 380 × `fade.bottom_fade`, hotbar = `hotbar.compose`.
  - **PNG at any size (user, 2026-10-15):** `sized(master, size, fade)` (premultiplied Lanczos; the fade is a function of
    the row share, so it scales; above 512 it only interpolates, the master and the model are 512) and `pngs(...)` →
    `<name>_<size>.png` + `<name>_<size>_tooltip.png` per size + `<name>_hotbar_64.png` (the PC recipe is fitted at 64,
    D24; other hotbar sizes would only resample it). CLI: `python -m iconkit.variants png ICON [SIZE ...] [--out DIR]`
    (a vanilla icon rebuilt from its lines until the model exists; default `outputs/png`, 512). The app's export (7.2)
    offers the same.
  - **Test** (89 test icons with a preset + the 8 metamagic; medians): master from lines vs the game's master over the
    hotbar dark, L* / dE2000: spells 1.39 / 1.44, actions 2.77 / 3.07, illithid 3.23 / 3.27, metamagic 2.90 / 4.03 (2.4 at
    128 px: 1.2 / 3.0 L*). Variants vs the game's files (mean |d| /255, premultiplied; from the vanilla master → from its
    lines): controller spells 2.58 → 4.48, actions 2.96 → 10.04, metamagic 2.32 → 9.28; tooltip spells 1.34 → 3.34,
    actions 1.75 → 6.47; hotbar spells 11.68 → 12.04, actions 14.53 → 16.75 (gate 18.1), metamagic 12.32 → 15.03. Illithid
    hotbar 26.8 either way: their game cells enlarge the drawing (2.2, `register`), not an export fault.
  - **After D38 (2026-10-16, lines without leaked glow, recipes refit through the painter's composition):** L* / dE2000
    spells 1.18 / 1.52, actions 2.84 / 3.08, illithid 1.62 / 2.63, metamagic 3.07 / 4.07; from lines: controller spells
    4.25, actions 9.71, metamagic 9.17; tooltip 3.15 / 6.54 / 6.31; hotbar 12.19 / 16.18 / 14.73.
  - The actions' controller / tooltip gap is alpha (probe on 20: alpha 12.8 /255 vs premultiplied colour 6.9; 2.4's own
    rebuild at 128 has the same 12.9): the even code halo vs the painted glow (D25's stated cost), invisible over the dark
    (2.8 L*). End-game allies lose ~3 /255 more alpha at 512 than at 128 (sharper line share). Not tuned (D24/D25).
- **3.2** DDS: Pillow DXT5; atlas mip chain assembled manually; uppercase `.DDS`.
  - **Done (2026-10-15).** Pillow's encoder is not good enough: on our hotbar cells it shifts line colours (Fireball's
    lines whiter) and paints red / black 4×4 blocks (round trip 8.0-8.7 /255 premultiplied); it re-encodes vanilla BC3
    cells at 0.02, so this is its endpoint choice on fresh content, not the format. `iconkit/dxt.py` = own numpy BC3
    encoder (principal-axis endpoints, 4 least-squares refits keeping the best after 565 rounding, every error weighted by
    alpha; alpha min / max, 8 levels): hotbar 5.1-5.6, controller 1.6-2.2 (Pillow 2.8-4.0), tooltip 0.6-0.7 (1.0-1.3);
    blockiness (L* jump across 4 px block borders) 1.3-1.7 vs the game's own cells 1.1-2.0; a 2048 atlas with mips ~10 s.
    Pillow also writes a wrong linear size (268 for 64 px) and no mip fields: `variants.dds` writes the header itself as
    vanilla (flags 0xA1007, mip count ≥ 1; atlas caps 0x401008, full chain by box filter to 1 px). Tooltip / controller
    without mips (as vanilla). `python -m iconkit.dxt` = self-check.
- **3.3** Mod export per `bg3-icons` skill: atlas sheet (or per-icon atlas) + atlas-map `.lsx` +
  TextureBank `_merged.lsf.lsx` + `Public/Game/GUI/Assets/...` files, names `<MOD>_Spell_<Name>`. A new status the spell
  applies gets the spell's icon unless it is a standard condition (2.5: vanilla 56% own icon, 23% condition icons).
  - **Done (2026-10-15), `variants.export(icons, mod, out)`** (D37): one square power-of-two atlas of 64 px cells (≤ 32 ×
    32) with full mips under `Public/<Mod>/Assets/Textures/Icons/Icons_<Mod>.DDS`, map `Public/<Mod>/GUI/Icons_<Mod>.lsx`
    (UVs on cell bounds, as 5eSpells), TextureBank `Public/<Mod>/Content/UI/[PAK]_UI/_merged.lsf.lsx` (ID = the map's
    UUID, uuid5 of the mod so a re-export keeps it; fields as the user's in-game verified ASL). Tooltip 380 / controller
    144 as **new GUI textures** `Mods/<Mod>/GUI/Assets/{Tooltips/Icons,ControllerUIIcons/skills_png}/<name>.DDS` + entries
    in `Mods/<Mod>/GUI/metadata.lsf.lsx` (MapKey `Assets/<path>.png`, w, h, mipcount 1), not `Public/Game`, plus
    half-size `AssetsLowRes` copies (190 / 72, not in metadata). Merging into an existing mod's metadata / TextureBank is
    app work (7.2). The status-icon rule stays an app rule (7.x).
  - **Checked against Larian's docs and files (user request, 2026-10-15).** Toolkit guide "Adding Skill and Item Icons"
    (docs.baldursgate3.game): 64 px icons go into an atlas (Texture Atlas Editor, powers of two 32-4096, 512 or 1024
    recommended) → `Public/<Mod>/Assets/Textures/Icons/<atlas>.dds` + `Public/<Mod>/GUI/<atlas>.lsx`; 144 / 380 PNGs go
    through Project > Convert UI Assets → `Mods/<Mod>/GUI/Assets/{ControllerUIIcons/skills_png,Tooltips/Icons}` **and**
    `Mods/<Mod>/GUI/AssetsLowRes/...`; one file name for all three. UI page: `metadata.lsf` is required (preloads the DDS
    info); the converter makes RGBA BC7_UNORM_SRGB "when sRGB is set", else BC7_UNORM. Game files: every vanilla icon has
    an `AssetsLowRes` copy at half size (tooltip 190², controller 72², BC7), Patch 8 too; Patch 8's 103 icons are BC7_UNORM
    without mips (Game.pak tooltips: 911 BC7, 446 BC7_SRGB, 164 DXT5) and are registered in `Mods/GustavX/GUI/metadata.lsf`
    exactly as our export (same fields; low res not listed). Patch 8's atlas `Icons.dds` 1024×512 = DXT5, 11 mips, header as
    ours. TextureBank forms: `Icons_Skills` (the spell atlas) `SRGB True`, `Type 0`, Template = own name, no size fields
    (our form, ASL in-game verified); `Icons_Items_2..6` and Patch 8's `Icons` `SRGB False`, `Type 1` + Width / Height /
    Depth. Both ship in the game, so either works; ours stays. Community: bg3_mod_helper's atlas template is ours (2048
    DXT5); a Nexus thread (Texture Atlas Editor icons blank on the hotbar) has no fix, the TextureBank trap fits it.
  - **In-game test mod** (`research/probes/ingame_test.py` → `outputs/IconGenTest`, gitignored): Fireball, Rush and
    Quickened Spell rebuilt from their lines only, exported as `IGT_Spell_FireBoltTest`, `IGT_Action_DashTest`,
    `IGT_Action_HideTest` and set as the icons of Fire Bolt, Dash and Hide (stat overrides `using` themselves), so the
    change shows on every character. `Build-Mod.ps1 -Convert` (Divine) converts both `.lsf.lsx` without error. Kept for
    Phase 7's in-game test (below).
- Test: 30 vanilla masters → compare with vanilla 144/380/64; in-game, a vanilla icon re-exported
  under a new name shows on hotbar, tooltip and controller (user, via `bg3-build-test`).
  - Done offline on 97 icons (3.1). **The in-game look moved to Phase 7's test (user, 2026-10-15):** every piece of the
    export matches a file the game ships or a page of Larian's guide (3.3), nothing in Phases 4-6 uses the export, and
    Phase 7 ends in game anyway. Left for the game to show: the GPU decoding our encoder's blocks (only Pillow decoded
    them) and hotbar colours next to a vanilla icon. **Phase 3 done.**

### Phase 4: Captions
- **4.0 Action sources finished (2026-10-15, `links.sources`; `python -m iconkit.links run` rewrites `data/links.json`,
  the 2.7 file kept as `data/links.p4.json`).** The 136 gaps had four causes in code: PassiveLists also separate with
  commas (Hunter's `ColossusSlayer,GiantKiller,HordeBreaker` was one unknown name), a flyout's options did not inherit the
  container's grant (Elemental Cleaver, Mantle of Majesty, Pact of the Blade), spells handed on by what a class gets were
  not followed (`links.unlocks`, 4 steps: UnlockSpell, ApplyStatus, a status's Passives, flyout options: Dread Ambusher's
  status, Bladesong's passives, Starry Form, Transmuter's Stone), and feats (`Feats.lsx`: Charger, Polearm Master) were
  not read. These fill gaps only (direct grants first); no earlier action label changed. Then `IsDefaultWeaponAction`
  → "Weapon action" (Bash, Slash, Smash, Pin Down), then `links.HAND` (81 icons, checked on contact sheets and stats):
  "Basic action" (Dash, Help, Hide, Dip and the dipped attacks, Jump, Shove, Throw, Disengage, Unarmed Strike, Knock
  Unconscious, Regain HP, Dismiss Summon, Perform and its songs: the "Perform" passive every hero has; drawn in the grey
  metal style), summons by summoner (Pact of the Chain imp / quasit and the Hexblade's Accursed Specter → Warlock; Find
  Familiar's frog and the specter-or-hound reactions → Monster), "Story" (9 origin / quest actions: Absolute power,
  Contact Mizora, Slayer...), "Feat" (Inspiring Leader, Shield Shove, Charger push), wild-shape beasts, Glut / hook horror
  / harpy abilities → Monster. **632 of 639 v1 actions placed**; 7 unused icons with no stats stay blank (AoE Damage On
  Jump, Call Forth Allies, Gargantuan Cleave, Lightning Aura, Lightning Blast, Mind Overload, Shrouded in Shadow); Fly
  and Hide stay "several classes" (captions leave both out). D34's test rerun (400 actions one per series, 18 sources,
  chance 5.6%): classifier 23.6% vs 6.7% shuffled within intent, nearest drawing 26.6% vs 5.7% → still yes; basic actions
  19% nearest from their own (chance 5%).
- **4.1** 16-icon labelled contact sheets → Claude writes motif text (what is drawn, layout) →
  `data/captions.jsonl`.
  - **Done (2026-10-15), `iconkit/captions.py` + `iconkit/motifs.jsonl` (in git: Claude's text, no Larian art).** `python -m
    iconkit.captions sheets DIR` → 68 sheets of 16 (icon over the hotbar dark | its grey line art, `glyph.split` EL; labels:
    name · intent · damage · source), every train + holdout icon by name, so series sit together and get parallel wording.
    1,083 motifs, one per icon: the objects, their pose and direction, placement (upper left, at the bottom, inside a ring),
    "symmetric" / "diagonal" where the layout is; the element symbol named where drawn (D28: "a snowflake symbol");
    shared frames worded the same across a family (Legendary's "square frame of four corner brackets with inward
    arrowheads", Wild Shape's "outline with a small standing human silhouette inside its body", Reapply's "inside a ring of
    two arcs"). 1,053 distinct; the 52 that share one are the same drawing (D27 copies). Glow-only effects (Rush's pool)
    are not described: the line art has none (D25).
  - **Spot-check round 1 (user, 2026-10-16): 13 of 30 noted.** Direction is where the **point** faces (user's definition:
    "which way the 'point' is facing"), and I had read many sword tips backwards at 176 px: 3 of the 13 (Manoeuvring
    Attack, Silencing Blade, Elemental Weapon). Others: beasts facing the wrong way (Relentless Lunge), word choice
    ("giant" sword is regular size, the figure flees rather than crouches; "spread-eagled"; "winged figure" is a humanoid
    angel; Shield of Faith's emblem is no sun; Animate Dead's skeleton hangs from puppet strings; illithid shapes are not
    blades: Black Hole's streaks, Psionic Overload's "two mostly mirrored spiky smears", Ink Blot's slits with liquid
    streaming out in smooth parallel jets). **Class fix:** every motif naming a weapon direction or a facing (293) rechecked
    on 300 px sheets (16 unclear ones at 400 px): 62 of the 181 weapon directions were wrong (34%; Larian's diagonal
    slash swords mostly point up-left or up-right, hilt at the lower corner), plus facings, the notes' series (all 8
    Divine Strike ranged arrows point down, all 5 Elemental Weapon swords point right with the symbol on the blade, the
    whole Animate Dead family on strings). **96 motifs rewritten.** Rule for later motifs: name the direction of the tip,
    look at 300 px or more.
- **4.2** Template: `bg3 <family> icon, <source (actions only)>, <intent>, <damage type> damage, <motif>. <description>`.
  D32 + D34: no school, spell type, area, level or cost words (none changes the drawing once each series counts once;
  per icon "illusion" would mean Disguise Self's face). D34: every action names its source (`links.json` `sources`:
  "paladin", "monster", "end-game ally", "legendary action", "magic item", "weapon action", "race"...), replacing the
  plan's four source tags; finish the 136 actions without one first (basic actions Dash / Help / Hide / Dip → "basic
  action", summons' attacks → the summoner's class or "monster", subclass features the tables miss such as Horde Breaker,
  Bladesong, Elemental Cleaver). Ranged twins say "ranged", Dismiss icons "dismiss" (2.7). D18: no colour words (images are grey glyphs); add effect words (restrains, teleports, heals…), the element
  symbol where the game draws one (2.5 `relations.json` `symbols`: series icons + Poison Spray, Lightning Bolt...;
  D28: in the app the exact symbol is stamped by code, so the prompt can leave it out), a source tag where the drawing style differs (wild magic, monster ability, magic
  item, basic action). **No glow words** (D25: training images are line art, the glow is code); line-core words
  (bright-core vs flat/metallic lines, `core_gain` in `data/grammar.json` `icons`) only if the line art still shows it.
  - **Done (2026-10-15): `python -m iconkit.captions build` → `data/captions.jsonl`** (`icon`, `motif`, `caption`; Larian
    descriptions, so data/), `... check` (self-check). Caption = `bg3 <spell | action | illithid power> icon, <source>,
    <ranged>, <dismiss>, <intent>, <damage type> damage, <motif>. <description>`, empty fields left out. Source on actions
    only (`links.sources` lower case; "legendary action"; "several classes" left out, D34), "ranged" for the 27 ranged twins
    (`links.json` `ranged`), "dismiss" for Dismiss icons. The game's description is kept sentence by sentence: a sentence
    with a colour, glow, school, level, slot, cost (bonus action, reaction, concentration, ritual) or spell-type word, or a
    number placeholder (`[1]`: cutting it out left "and has."), is dropped whole; 702 captions keep some. `captions.BANNED`
    also rejects motifs with those words (a "spear held level" was caught). Words per caption: median 27, max 61. For
    Phase 5: SDXL's CLIP reads 77 tokens, so the longest captions lose the description tail there (not the tags or motif,
    which come first); Z-Image / FLUX text encoders read longer prompts.
  - Line-core words: not added. The line art is a grey level only (D18 de-tint), and the bright-core vs flat look comes
    back from the colour preset at tint time, so the drawing does not carry it.
- Test: user spot-checks 30 captions. `python -m iconkit.captions report` → `data/captions.html` (16 actions, 11 spells, 3
  illithid powers drawn at random, seed 0; icon | line art | caption, numbered). Round 1: 13 notes, all fixed with their
  class (4.1); round 2 (same 30, rewritten): "all read fine" (user, 2026-10-16). **Phase 4 done.**
- **Found while checking (user notes 4, 15): glow leaks into the line art.** Where a painted glow is bright between close
  strokes, `glyph.split`'s line share (brightness over black above .45-.65 × the icon's p99) fills the gap: Silencing
  Blade's sword becomes a solid blob, Giant Subjugation's legs thicken. Measured on train + holdout: share of line pixels
  (AL > .5 at 512) with alpha < .9 (made by glow, not a stroke; Fireball .025, the two examples .16 / .17): spells median
  .074, p90 .20, 67 of 401 at .15+; actions .045 / .135, 58 of 639; illithid .041 / .095, none. Worst: end-game ally
  crests (.31-.48), Rolan Artillery, Opening Attack, acid spits (.33-.39); Darkvision .49 is a dark-line icon D25 already
  drops. Not a caption issue: the training line art (Phase 6) and the 3.1 round trip use the same split. A fix belongs
  before Phase 6 (2.4 line extraction: a local threshold or a ridge / stroke-width test instead of one global p99 ramp),
  measured against the D25 glow round trip so the rebuilt masters do not get worse. **Fixed 2026-10-16: D38** (local
  midpoint test; branch `kk/nice-fermat-a131f2`). Checked by eye first: alpha < .9 marks the glow on the rims and washes
  but misses opaque glow inside Silencing Blade's blade (alpha .7-.9 there) and flags real strokes that fade in alpha on
  weapon actions, so the probe also reports an alpha-free blob share.

### Phase 5: Alpha read-back + model test (gate) (D39: FLUX.2 klein 4B, no 3-way bake-off)
- **5.1** Alpha read-back, no model needed: the model draws the line art over black (grey × alpha), so lay every
  hold-out icon's true line art (`variants.line_art`) over black and read it back: (a) max-RGB with one fitted grey
  `k` (alpha = min(1, C/k), grey = C/alpha) or the line test that made the training data (`glyph.split`'s ramp), plus a
  floor for faint haze. Score |Δa|, grey error on opaque line pixels, and the round trip through `variants.master` as
  seen over the hotbar dark (L* added to 3.1's 1.18 / 2.84 / 1.62); sheet of the worst. D25: lines have crisp alpha,
  the soft and dark glows come from code, so (a) should be enough; (b) matting net only if it fails (LayerDiffuse has
  no klein version). Recheck on real model output in 5.3 (the VAE adds haze).
  **Done (2026-10-16) → D40: k = .8 for every kind.** `research/probes/alpha_readback.py [TRAIN_STEP]` (~15 min, 6
  processes) → `data/alpha_readback.json` + sheet `data/alpha_readback.png`; 162 train (every 6th) + 89 hold-out icons.
  Hold-out medians (|Δalpha| on drawn pixels / grey error on opaque / L* added / L* vs game): spells k .8 .012 / .009 /
  .30 / 1.17, actions .011 / .009 / .32 / 3.07; plain max-RGB spells .100 / .100 / 4.06, actions .091 / .087 / 2.53;
  "core" (k = brightest within 3 px) spells 1.89, actions 1.37 L* added. Illithid (all 41, scratch sweep): k .02 to .3
  medians 2.1-4.7 L*, the worst (Transfuse Health, Displacer Shape, Luck of the Far Realm) ~9 at every k: their shaded
  strokes are partly line-share alpha on opaque pixels, which no single grey separates; low k = dark rim (look, not L*).
  Worst hold-out at the fitted k: Peace Breaker 6.6, Force Tunnel 3.6, Crippling Strike 2.5, then ≤ 1.2.
- **5.2** One LoRA on `FLUX.2-klein-base-4B` at 512 (AI Toolkit or musubi-tuner: fp8 base, prompts cached, batch 1)
  on the spell subset first, then all kinds; inference on the distilled 4B (4 steps). BFL lists 12 GB for 4B training,
  the RTX 3080 has 10: if it does not fit, a rented 24 GB GPU (~1 h, ~$0.50 per run; the user's call), else SDXL.
- **5.3** Score in diffusers on hold-out prompts: palette accuracy (2.1 rules), clean alpha border,
  nearest-vanilla similarity (memorisation check, D29: `relations.kappa` of each generated line art against every
  training drawing; the closest should spread like the test set's, median .53 / p90 .83, none ≥ .9 unless a series
  variant was asked; the 5 `seen_drawing` test prompts scored apart, D27), speed + peak VRAM at 8 GB settings, user
  blind review (real vs generated grid). Control row (D39): klein with no LoRA, given 4 reference icons from the user's
  own game files (D10) and the same prompts: what the LoRA adds, and whether references alone come close. Unseen things
  (user question 2026-10-16: can it draw what the game never drew?): ~12 prompts for objects no motif names (lantern,
  candle, mirror, ladder, cauldron, anvil, clock, compass, lock, dice, throne, mushroom: 0 of 1,083 motifs), each LoRA
  checkpoint (every 250 steps) vs no LoRA; the user judges "recognisable + game style"; the kept checkpoint must keep
  them (overtraining makes a style LoRA draw only its training motifs). Also try how a
  generated drawing leaves room for a stamped symbol (D28): prompt without the symbol + clear lines under it, vs stamp
  first and give it as the reference image. Draft-guided generation (D31): a few editor-style drafts (game parts moved
  and combined) as klein reference images and as img2img on the grey line art at several strengths; score closeness to
  the draft (kappa) against D29's novelty and the user's eye; pick the method and the slider's range (an edit LoRA on
  draft → line art pairs only if both fall short). Frame families (D36): the frame (`links.json` `frames`) as the
  reference, the model draws the inside, code puts the exact frame back on top, for a few prompts per family
  (legendary, aura, Arcane Shot, Magic Circle); score the frame kept and the inside's novelty (D29).
  **Part 1 done (2026-10-16): `research/probes/score53.py`** (gen / score / steer / sheet / blind; args in its
  docstring) → `outputs/score53*/` (`score.json`, `steer.json`, sheets, blind grid). Hold-out sweep (steps 1,500-3,000
  × x1.5-2.5 + no LoRA), control row, unseen objects at every checkpoint, caption parts (no description / no motif /
  SRD text): results in D41 and the Status log. Palette accuracy = the drawing stays grey (D18: code colours it):
  median line chroma 0.5-0.6 at every LoRA config (no LoRA 13). Clean alpha border: haze (alpha more than 8 px from
  any stroke) 0 at every LoRA config: the VAE adds none, D40's read-back holds on real output. Left: the user's blind
  review, then symbol room (D28), drafts (D31), frame families (D36).
  **Draft test done (2026-10-17, `research/probes/draft53.py` drafts / gen / score / sheet → `outputs/draft53/`, sheet
  `outputs/draft53_sheet.png`):** 42 hold-out icons with a vanilla start; the draft = a D30 rebuild from training members
  (9) or the closest training sibling / frame-family member / copy (33); v2 12,000 x2 distilled. Kappa to the game's
  drawing (medians): draft alone .69, free text-only .28, reference .72, img2img .5 .71, .75 .70, both .71; D30 rebuilds:
  draft .92, model .91-.92, free .40. The model copies the draft (to the draft .92-1.0; img2img .5 = .996) and never
  beats it; it ignores a prompt that asks for another object (Trident on a Battleaxe draft stays an axe, Giant Spider on
  Wild Shape stays a wolf); only reference mode sometimes adds the prompt's object (Ki Resonation fist, Sneak Attack
  arrow, Legendary's inside). Strokes stay the game's (roughness .93-.96, taper .32-.35; real .94 / .37). So whole-drawing
  starts ship from code (D30 as decided), the model is not needed for them; its place is a masked region (inpaint) where
  the draft has a gap. Not yet tested: masked inpainting (keep a frame / series base, redraw the rest from the prompt).
  Slider range if used: img2img .5 = copy, .75 or reference = some freedom (reference 3.3-3.6 s per image vs 1.4-2.0).
  **Masked inpainting done (2026-10-17, `research/probes/inpaint53.py` prep / gen / score / sheet → `outputs/inpaint53/`,
  sheet `outputs/inpaint53_sheet.png`):** keep the lines 80% of a series' / frame family's training members share (D30's
  base; pieces under 200 px dropped), the model repaints the rest from the prompt (klein inpaint pipeline, strength 1,
  4 steps, v2 12,000 x2), code puts the exact base back on top. 18 hold-out icons qualify (9 element series, 4 frame
  families, 5 series; 24 skipped: 1 training sibling, or Disguise Self / Wild Shape / Blink whose members share almost no
  lines). Kappa of the new inside (outside the kept area) to the game's inside, medians: inpaint .48, + base as reference
  .50, free .33, another member's own inside .51; whole drawing .76 / .75 vs free .38. Element series: code's symbol swap
  .74 vs inpaint .53 (the model draws a recognisable skull, bolt, rings, flame, but not the game's symbol: D28 / D30 stay
  code). Frame families: inpaint .46 / .48 vs another member's inside .44 (Aura of Protection draws the shield, Legendary
  a new inside). Series: Pact of the Blade draws the prompt's trident in the kept hand (.65 / .68 vs the axe .44; the
  draft test kept the axe), Hex Intelligence the book; Hex Strength (blob), Spiritual Weapon: Greatsword and
  Enlarge/Reduce (small bases) fail. 2.4 s per image (3.4 with the reference), 4.5 GB peak for generation. So the model's
  job in a composite-first app is filling an erased / masked area of a game-part draft, not redrawing whole drafts.
  **Planner test done (2026-10-18, user idea + "D48 A, then the planner test"; `research/probes/planner53.py` catalogue /
  fewshot / plan / gen / score / sheet → `outputs/planner53/`, sheet `outputs/planner53_sheet.png`):** Qwen3-4B (klein's
  text encoder, fp8 storage, 4.1 GB, ~15 s per plan, greedy, 7 hand-written example plans from training icons) writes a
  JSON plan per hold-out caption over a 50-entry catalogue (parts.FAMILIES exemplars cut from training icons only, the 11
  D28 symbols, 14 D36 frames); a code check drops parts the motif never names (33 of 136: spirals, frontal figures,
  broadswords...); code places parts; new regions drawn as sprites (each object generated alone, fitted into its box) or
  by one inpaint over the regions. 91 of 92 plans valid JSON; 84 usable after the check. Kappa to the game's drawing:
  inpaint .25, sprite .21, parts alone .15, free .26 (nothing to start from: .23 / .17 / .07 vs free .25; frame families
  .54 / .55 vs .35; element series .46 vs .40, D30 code .92). Fewer strokes than the game (parts 8 vs 11, ends 35 vs 52).
  By eye: the 4B planner often leaves out the main object (Fly: a bare star figure, Know Your Enemy: rays without the
  face, Harmonizing: no notes) and placed parts read as bare stickers (Watch Summon: an empty ally bust); inpaint is good
  where the plan is right (Soul Reaping's wisps among sparkles, Vampire Creatures, Boot of the Giants). Blind test 4 on
  the last 11 unseen icons (`outputs/score53_v2/blind_planner_inpaint.png`, 10 planner + 1 free fallback; key not opened).
- **5.4** House-parts library (D43, 2026-10-17): `python -m iconkit.parts run` (~3 min, 6 processes) → `data/parts.json`
  (groups, members, per-icon shares) + `data/parts.npz` (line masks, part table, group per part, context pictures);
  `... report` → `data/parts.html` (names applied here, no rerun); `... check` (drawn hook / star / strokes + stale
  names). Parts = 4-connected regions of the D38 line art at 512, ≥ .5% of the icon's lines and ≥ 24 px: 11,684, median
  10 per icon (15 with tiny bits, the Resume note's figure). Plain strokes (skeleton < 1.6 × box side: lines, arcs,
  dots, spurs) are 27% of all lines and stay with the house brush (D44); the 4,892 compound parts (72% of lines) are
  compared as skeletons in their own box at 32 px, as drawn and mirrored (`relations.kappa`; different icons at random
  p50 / p90 / p99 .09 / .27 / .49), grouped by average linkage at mean kappa .75 in 3+ icons: 255 groups, **116 house
  parts (3+ series)**, 139 series parts (D30 / D36 material). 36 names (`parts.FAMILIES`, keyed by group medoid in
  `NAMES`; 34 with a house group, plus portrait shoulders and Pact of the Blade's gripping fist) cover 62 house groups
  + 3 series groups; every named card checked by eye, 6 mixed groups left unnamed (fork /
  knife, lute neck / arrow shaft, eye / halo arc, small rings, ring arcs, jaws / lightning zigzag). Results in the Status
  log; decisions on the page.
  **Whole shapes (user, same day):** a group's stroke grows into the drawing it belongs to: exact repeats (B, every
  group, shift-tested) and, for figures, joined strokes up to the usual figure size without enclosing frames (A);
  members carry both label sets (`members[i][8]` B, `[9]` A, 8-connected), coverage counts B. `parts.EXCLUDE` = eye-checked
  wrong members. ~13 min run (`strokes()` join graph per icon).
- Gate: klein kept (or SDXL fallback) + alpha method, logged in Decisions.

### Phase 6: Full training
- Train on `data/train.txt`, evaluate on `data/holdout.txt` (D14).
- De-tint every training master with its assigned preset (`grammar.detint`, D18; icons no preset fits stay out or are
  de-tinted by their own curve), two-colour icons part by part (`glyph.part_presets`, `grammar.json` `two_tone`, D26); keep the lines only (`glyph.split` line share, D25, D38: no leaked glow; dark-line icons out). Every icon stays; weights (D27 amended by
  D33): copies of one drawing (`relations.json` `groups`, 32 groups / 82 icons) share one drawing's weight, and each
  drawing of a series of n distinct drawings (`shape.series`, ids in `data/shape.npz`: 712 series for 1,083 icons) weighs
  1/sqrt(n). Disguise Self's 34 icons weigh 5.5 (10% of utility spells, was 33%); element symbols are still seen.
  Series = `shape.series` (flyouts and Reapply included, 2.7) joined with the frame families split over several series
  (`links.json` `frames`: Legendary 12, Paladin auras 5, Command Undead 5). The 9 Reapply spells leave training (D35, like
  D14's badges; `links.json` `reapply`), the illithid Reapply Imperil stays.
- Spells + actions/skills: one LoRA with family tags vs one per family, by 5.3 results. Hold-out
  metrics + user review.

### Phase 7: App v1 (tab "Spells & actions"; "Passives", "Class icons", "Items" tabs as placeholders)
- **Amended by D46 / D47 (2026-10-17): the editor (7.6) is the app's main screen and comes first**: a browser vector canvas with the parts panel (best copies, no names), house brush + line / circle / spline, the 7.1 fields beside it, a WebGL live preview; export or "send to model" (method from the Phase 5 draft test). Python `iconkit` is the backend; install per D47.
- **7.0 Editor prototype (2026-10-17, branch `phase-7-editor`)**: `iconkit/editor.py` (data cut, server, export,
  check) + `app/` (`index.html`, `editor.js` drawing model / tools / panels / fields, `glow.js` WebGL paint). Stdlib
  server only (`ThreadingHTTPServer` on 127.0.0.1, static `app/` + `data/editor/`, nothing else reachable).
  - Data (`python -m iconkit.editor extract`, ~3 min, 6 processes → `data/editor/`, 90 MB icons + 12 MB thumbs): the
    1,083 v1 icons of `glyph.json` (the 71 numbered-badge icons, D14, are not offered). Per icon `icons/<n>.png` = line
    art at 512 as **opaque RGB** (R grey = `detint` in its preset or nearest `assigned` one, G alpha = AL × a; two-colour
    icons de-tinted per side as `variants.build`): browsers decode an opaque PNG exactly, a transparent one goes through
    premultiplied alpha. `icons/<n>.lab.png` = stroke ids (R + 256 G): 8-connected labels of AL ≥ .5 = exactly
    `parts.strokes` (checked against `parts.npz`), every soft pixel given to its nearest stroke, soft bits joined to no
    stroke get ids of their own. `thumbs/` = game master over the hotbar dark, 72 px. `index.json`: name, display
    name, kind, preset, second preset + its strokes (D26), glow recipe, intent, damage, source (`links.sources`).
  - Parts panel (`... editor parts`, ~2 min → `parts.json`, `parts/<group>.png`, check sheet `parts_sheet.png`): per
    group, whole shape = `members[i][8]` (+ `[9]` for figure groups: `parts.NAMES` / `FAMILIES` category "figure", used
    only to pick the set, names never shown), `parts.EXCLUDE` members dropped. Measured per member: size (box side px),
    clutter (other strokes' line px inside the shape's footprint, dilated 6 px, holes filled, per shape px),
    typicality (median kappa of the lined-up whole shape vs the other members', as 5.4). Pick = max of size share ×
    (1 − clutter) × typicality share². 254 groups → **186 cards** (68 dropped as the same shape as an earlier card:
    same icon and 80% overlap, or kappa ≥ .9 in their own box); picked copy size p10 / 50 / 90 247 / 392 / 484 px (whole
    shapes include exact repeats, so sparkle groups span the icon), clutter p50 / p90 0 / .01, typicality p10 / 50 .62 /
    .90; the largest member won 127 of 186; where copies carry a fill (the drop with a flame inside: clutter .37-.58)
    the clean one wins. Sheet sent to the user, no reply yet.
  - Editor: items = stroke bitmaps (game strokes or brush strokes) with an affine each; icon browser (search name /
    file, kind filter; click opens, Shift-click adds), parts panel (click adds the best copy at its game position,
    selected); select / Shift-add / box, move, corner scale, rotate handle (Shift 15°), wheel scale, flip H / V, ±15°,
    duplicate, delete, undo / redo (200), arrows nudge; spell fields: kind, name, intent, damage, source (actions),
    colour (Auto = `grammar.keys` + `groups`, else the kind's commonest preset), hotbar frame (actions / illithid:
    the colour's frames first, then every framed background at its median gain; spells: spell background), second
    colour + "selected → 2nd / 1st". Line art view toggle.
  - House brush (D44, measured on 149 icons' line art): crisp edge (alpha .01 → .90 across one pixel), grey .82 at
    the edge to .975 at the centre (by share of the half width), median width 12.8 px (default 14, slider 4-40), ends
    taper to 1/3 over one width; freehand (Chaikin ×2), line (Shift snaps 15°), circle (closed, no taper), spline
    (Catmull-Rom; double-click / Enter ends, ending on the first point closes). Not modelled: edge roughness (.93).
  - Live preview (`app/glow.js`): `variants.paint` as WebGL2 passes (prep lq lookup → one separable pass for both
    Gaussian blurs, scipy kernel, zero outside → glow + `tint` trilinear LUT + skimage `lab2rgb`). `L = clamp(100 E / A,
    lq0, lq200)` replaces the detint / tint round trip (exact for a non-decreasing lq). **Golden vs `variants.master`
    on the same line art, 91 test icons (the 89 hold-out with a preset + metamagic in hold-out): median 0.018 L* at 128
    px (3.1's measure), 0.051 at 512, worst pixel 3.5 L*, alpha ≤ .002; strokes recomposed in the canvas = the cut line
    art, 0 pixels off; ~0.4-1.3 ms per repaint (RTX 3080; Python 391 ms).** Two colours: the preview gives each pixel
    to the side with the larger blurred line share (Python: exact nearest line): 8 metamagic icons median 0.13 L*,
    Extended / Twinned ~.5, a few seam pixels up to 56 L*; no seam visible at editor size; export is exact. Controller
    144 / tooltip 380 (fade.py formula as a gradient) are canvas downscales over the dark; the hotbar 64 is Python
    `hotbar.compose` on the WebGL master (`/api/hotbar`, 179 ms, 350 ms after the last edit).
  - Export (`/api/export`): line art (+ second-colour mask) → `variants.master` (exact path) → `outputs/editor/<Mod>/`:
    `icons/` masters + settings, `drafts/<key>_lineart.png` (the model's reference later), `png/` (512, tooltip, hotbar
    64), `mod/` = the whole mod rebuilt from every icon exported to it (`variants.export`: atlas + map + TextureBank +
    GUI textures + metadata); key `<Mod>_<Spell|Action|TadpoleSuperPower>_<Name>`. `variants()` / `pngs()` take
    `bg=` (the Frame field). 8-bit line art through this path vs `variants.build`: 0.011 L* (`editor check`).
  - Runtime path without scikit-image (D46): `iconkit/lab.py` = skimage's `rgb2lab` / `lab2rgb` / `disk` (exact, dtype
    kept; self-check vs skimage); `glyph`, `grammar`, `hotbar` import them from there, `deltaE_ciede2000` /
    `skeletonize` load skimage on first use (fitting, reports). `editor check` asserts skimage stays unloaded.
  - Missing, by plan: element symbol stamp (D28), Based on series / frame families (D30 / D36), eraser (D31: one-net
    drawings like Hex's heart), draft save / load, Description / motif / N candidates / seed (model, 7.2), D29
    new-vs-copy score, Make related (7.3), prefill from SRD (7.4), D47 launcher. (Eraser and drafts: done in 7.0b.)
- **7.0b Editor v2 (2026-10-17, user notes on v1)**. Notes: brush / line / circle / spline strokes "too smooth unlike
  the game icons"; some parts "not useful / too vague" (3 screenshots); strokes show a "layered" look where they
  cross (scribble over an icon); where is the eraser; "pretty and intuitive with quality of life and accessibility";
  roughness an option; taper applied retroactively; spline customisation (straight, curved, adjustable); "pretend this
  is a Photoshop / Affinity app"; a light background to check the glow; resizable panes; strokes as vectors for any
  output size, only if quality holds. All built (9ecaa51):
  - **Union, not layers**: strokes compose with canvas `lighten` (per pixel the brighter grey; alpha union), so a
    stroke's darker rim no longer cuts across the one below. Golden unchanged (game strokes never overlap): 0.018 L*.
  - **Vague parts**: no measure separates them (best single one, total skeleton per box side < 1.8, agrees 87% with my
    eye labels; a depth-2 tree on 12 measures 81-83% vs 76% for "keep all"). So an eye-checked list like
    `parts.EXCLUDE`: `iconkit/parts_hidden.json` (group key -> why, stable across part reruns; 44 cards: plain arcs /
    lines, stray dots, loose tangles, face fragments; the user's three examples were cards 20, 124, 125), hidden in the
    panel; right-click hides / unhides any card (the server rewrites the file), "Show hidden parts" lists them.
  - **Brush = vector strokes rendered in the browser** (`app/brush.js`; settings stay editable, the item re-renders).
    Outline polygon (quads + mitred corners + pointed tips, one nonzero fill = union, canvas antialiasing), grey by
    the cross-section PROFILE at each pixel's nearest centre point. Edge model measured on the game (sections of the
    D38 line art along their skeleton chains, `editor.chains` / `edges`, 32 px next to real stroke ends left out):
    half-width variation over the median, hold-out, 478 sections: width slow (> 15 px) .065, mid .035, fine .015,
    centre wander .024 / .017. Generator = filtered noise per scale, amplitudes calibrated by `/?brushtest` (the brush
    drawn on each hold-out section's own centre line and width, measured the same way): slow .151 (σ 15), mid .020
    (σ 5; the slow noise supplies most of that band), fine .020, wander .035 / .026, core grey .03 → brush .060 / .035 /
    .014 / .022 / .017 (all within 8%; smooth brush .001-.006). Tips (hold-out sections; 1,783 train tips agree): width
    .32 at a real end, .95 by 38 px; fit `tip + (1 - tip) (d / 3 widths)^.7` within .03. Tried and dropped: replaying the
    game's measured edge sequences (wobble matched, .029 vs .025, but beads: edge walks run into touching strokes and
    the max-of-segments renderer fills nicks; sheet looked wrong).
  - **Tools** (left rail, Photoshop keys): Move / select V (handles: corner scale about the opposite corner, Alt about
    the centre; rotate dot; Alt-drag copies), Edit points A (drag, Alt-click corner / smooth, double-click adds, Del
    removes), Brush B (stabiliser), Line L, Ellipse U (Shift circle, Alt from centre), Pen P (cardinal spline: Curve 0 =
    straight, 1 = Catmull-Rom; Alt-click corner; click first point closes), Eraser E (pixels: non-destructive per-item
    eraser strokes in local coords, so erased brush strokes keep their settings; or whole strokes), Hand H / Space /
    middle drag. Context options bar per tool; with brush strokes selected it edits them (width, roughness, taper start
    / end, tip, curve, closed, smoothing) with coalesced undo.
  - **UI**: top bar (New, Save, Export, undo / redo, background: hotbar dark / black / grey / light / white / checker,
    line-art view, zoom), resizable docks (splitters: drag, arrow keys, double-click collapses; Tab hides both; widths
    kept in localStorage), library tabs Icons / Parts / Drafts (drag onto the canvas places at the drop point), right
    dock: Properties (X / Y / W / H, keep proportions, rotate by, flips, arrange, 1st / 2nd colour), Layers (eye, lock,
    rename by double-click, drag reorder), Spell (colour swatch grids from each preset's gradient), In game previews,
    Export (PNG size 512 / 1024 / 2048). Status bar (coords, preview ms), shortcuts dialog (?). Accessibility: every
    control named (checked: 0 unnamed), aria-pressed / -selected, separators with keyboard, live status, focus rings.
  - **Drafts**: game strokes stored by icon + stroke id, vectors by settings (no game art in a draft);
    `outputs/editor/drafts/<name>.json` + thumbnail; autosave 1.5 s after a change, restored on start.
  - **Any-size export**: the browser flattens the drawing at the PNG size (brush strokes re-rendered at that scale,
    their noise laid out per px at 512 so the shape holds; game strokes enlarged smoothly), Python grows the glow at
    that size (`glyph.glow` scales its blurs, the tint table is size-free). Quality never below the old upscale of the
    512 master (crop compared: brush edges sharper, game strokes and glow alike). Mod files stay at the game's sizes.
- **7.0c Editor v2 fixes (2026-10-18, user notes on v2)**: (1) the left pane's hide button hid its content, not the pane;
  (2) every slider resettable to its default; (3) freehand drawing drops the frame rate badly; (4) polish.
  - **Dock hide**: a splitter drag writes `--lw` / `--rw` inline on `#app`, which beats the `.noleft { --lw: 0 }` rule,
    so a resized dock kept its column (measured: 300 px left after hiding). The grid now reads its own column
    variables (`--lc` / `--ls` / `--rc` / `--rs`) that a hidden dock zeroes, and the splitter hides with its dock. Both
    docks checked with resized widths: canvas 268 → 573 px (left hidden) → 978 px (both), back to 300 / 400 on show.
  - **Reset**: one rule for everything adjustable: double-click (the slider or its value) or Backspace / Delete while
    it has focus puts it back to its default (`DEF` = `Brush.DEFAULTS` + eraser 24; with brush strokes selected the reset
    applies to them, like any slider change). A value that differs from its default shows in the accent colour. The dock
    splitters follow the same rule (default width; VS Code's sash behaviour), so double-click no longer collapses a
    dock: the header buttons and Tab do. Zoom has no slider: the % button fits, Ctrl+1 is 100%. Checked: width, rough,
    tip, smoothing, eraser by both routes; Backspace on a focused slider no longer deletes the selected strokes.
  - **Freehand speed**: page `/?perftest[=px]` (default brush, a 5,000 px spiral over Fireball, one pointermove per 4
    px, frames run by hand so a hidden tab works; per move: the work until its frame is painted, incl. `gl.finish` and a
    small-preview read back; `window.perfResult`). **Before: p50 83 ms, first 500 px 12.4 ms, last 500 px 229.7 ms, max
    424, release 260 ms. After: p50 8.1 ms, first 500 px 8.2, last 500 px 9.8, max 26.8, release 13.5.** Cause:
    every move re-rendered the whole stroke (`Brush.render` 168 ms at 5,000 px: canvas path building ~3 µs per call,
    75 ms for 5,000 quads; the nearest-centre loop with `Math.hypot`; per-point values), then composed every stroke
    twice. Fix (`app/brush.js`): `render = paint(prepare)`; `paint(st, i0, i1, o0, o1)` paints any range of points and
    keeps only pixels whose nearest centre point is in its own range, so overlapping pieces tile a stroke; freehand
    strokes are always painted in 128-point pieces; a stroke being drawn (`live`) paints each piece once, when later
    points can no longer change it (smoothing reach + end taper), and each frame only the rest; `finish` on release.
    Each noise array has its own random stream (a sample's wobble no longer depends on the stroke's length; the
    noise is reused while long enough); the loop compares squared distances and shades once per pixel. Checked: live
    + finish = `render` byte for byte (default, 40 px, 60 px, no taper, short); the loop rewrite = the old code on the
    same noise (0 px off freehand / ellipse; 11 px by ≤ 2 grey at a path's sharp corners: tie-break); one long path
    instead of pieces rasterises edges up to 10/255 alpha apart (Skia), hence pieces everywhere. Per update: 1.2 ms
    at the default width, 4.9 ms at 40 px, 9.5 ms at 60 px (max width). Full re-render (sliders on a drawn stroke)
    2,500 px: 68 → 25 ms. Editor: the stroke update and the repaint share one frame, the other strokes are composed
    once per drag, no second full compose without a second colour, no hotbar request mid-stroke, coalesced pointer
    events (fast strokes keep every mouse sample). New random streams change the wobble of strokes drawn before
    (same statistics); NOISE recalibrated by `/?brushtest` (slow .151 → .167, fine .020 → .022): brush vs game
    .0651 / .0368 / .0148 / .0224 / .0172 vs .0651 / .0351 / .0150 / .0236 / .0169 (all within 6%; smooth .001-.006).
    Golden (compose changed): 91 one-colour icons 0.015 L* at 128 (0.048 at 512, worst 1.1), 0 stroke px off; 9
    two-colour 0.134 (seam max 56, as before).
  - **Polish** (looked at in the pane and headless Edge at 1440 × 900): selected library tab marked by an accent
    underline (its raised grey was 1 step off the strip: unreadable), one-line tab labels; hover on tabs, panel headers
    and swatches; Spell selects fill their column (Kind / Intent / Damage / Source were four widths); second colour
    "None" draws a hatched empty bar, so its label lines up with the first colour's; checkboxes in the accent colour
    (were browser blue); splitters drawn as a 1 px line, accent on hover / focus; undo / redo grey out with nothing to
    undo / redo, and the options bar's flip / rotate / arrange / duplicate / delete with nothing selected; library
    empty states span the grid (Drafts' text sat in one 64 px cell) and a search without a match says so; arrow keys /
    Home / End move between library tabs (roving tabindex); "1 stroke"; Properties X / Y / W / H follow a slider
    change on selected strokes. Library hint texts kept as they were (a rewording was declined). `editor check` passes.
- **7.0d Editor v3 (2026-10-18, user: "research UI/UX for these kinds of apps and make sure it's extremely polished";
  "performance while drawing is a lot better but I still want it faster if possible")**.
  - **Faster drawing, round 2** (`/?perftest` now reports ms per frame part, `window.perfMs`, `&w=` width). Start:
    p50 8.1-9.3 ms, p90 11.7-14.4; parts per move: stroke 4.0, input handler 2.1, GPU read back 3.3, rest < 0.6.
    (1) Input: `toDoc` read `vp.getBoundingClientRect()` right after the status bar's coordinates changed, so every
    mouse sample forced a layout of the whole page (the 1,000-tile library): the canvas box is now kept by the
    ResizeObserver, the status bar is `contain: strict`, coordinates are written only when they change (2.1 → 0.05 ms).
    (2) The live stroke is composed from its settled pieces + its end directly (no extra 512² copy). (3) The in-game
    previews' high-quality downscale (~3 ms of GPU: the slow frames were every 4th, when they refreshed) waits for the
    release, like Photoshop's Navigator. (4) The stroke's centre line, noise and buffers are extended, not rebuilt:
    `resampleFrom` keeps output length + carry per input point, the smoother redoes only points whose window moved,
    noise arrays are streams that draw their next samples, per-point arrays are reused (5,000 px: last 500 px 5.2 →
    1.7 ms). (5) The nearest-point buffers are reused (no change measured; kept: less garbage). Result, default
    brush, 5,000 px: **p50 1.8 ms, p90 3.6, max 12.9, first / last 500 px 1.8 / 1.7, release 11.6**; 26 of 1,250
    frames over 5 ms (pieces settling). Width 40: p50 7.4, p90 13 (tail paint: Skia fill of ~300 overlapping quads 2.5
    ms, nearest 1.5, shading 1.1; cutting the fill means a different edge rasteriser = a brush look change: not done).
    Exactness: new `render` = the committed one byte for byte (6 freehand cases, path, ellipse, 4x export, raw), live
    + finish = render (default, 40, 60 no taper, short): brush look unchanged, brushtest numbers stand.
  - **UI research** (web, 2026-10-18; sources in the chat): Photoshop / Figma / Affinity number controls scrub by
    dragging their name (Shift faster, Alt / Option finer) and take typed values; Photoshop's tooltips = name +
    shortcut (rich ones add a line); pro tools are keyboard-first, contextual, dense, neutral greys with the accent for
    state; brush size / zoom feedback on the canvas (Photoshop's HUD); the brush outline only for painting tools
    (Krita bug 327612); Layers thumbnails identify layers; Figma UI3 keeps docked, resizable panels, collapsible.
  - **Controls (batch A)**: every slider = scrubbable name (drag sideways; Shift ×10, Alt ¼; one undo step) + range +
    typed value (Enter / leaving applies, clamped; arrows step, Shift ×10; Esc reverts); reset unchanged (double-click
    the name or slider, Backspace on the slider). Properties X / Y / W / H / Rotate: scrub the letter, arrows nudge live
    (Shift ×10, one undo step per run), typed values, Esc cancels; the fields not being edited follow (`syncProps`).
    Checked in the page: typed / clamped / invalid values, arrows, scrub with Shift / Alt, reset, Properties nudges,
    typed X, Esc on W, Y scrub +20, Rotate scrub 90°, undo steps back in order.
  - **Feedback (batch B)**: one styled tooltip for every `title` (moved to `data-tip`, so the browser's slow unstyled
    one never shows): "Name (Keys): description" laid out as name + key caps ("or" between alternatives) + a dim line;
    450 ms on hover, at once when moving to the next control within 400 ms, on keyboard focus (`:focus-visible`), beside
    rail tools, below others (above when no room), clamped to the window; Esc / click / wheel hide it; `aria-describedby`
    while shown. On-canvas HUD pill (zoom %, Fit, `[` / `]` width or eraser size, draft saved, exported; 0.9 s). Brush
    / eraser cursor: outline + a centre cross (cross alone when the outline would be a dot), kept while painting.
    Double-click the Hand tool fits (Photoshop). `[` / `]` change the size by at least 1 px (2 × 1.15 rounded back to 2:
    the brush could not grow from its minimum). Top bar below 1100 px: captions hidden visually (kept for screen
    readers), no scrollbar strip. Checked: tip markup / timing / placement (1440 and 800 px windows), HUD texts, `]`
    from 2 → 3, Hand double-click → Fit 142%, header 800 / 800 px wide, names kept.
  - **Panels (batch C)**: Layers rows get a 24 px thumbnail of the stroke's own bitmap (Photoshop's Layers panel: tells
    "Part 251 · 4" from "· 5" at a glance) and the header shows the stroke count; empty state says what to do. Canvas
    right-click menu (Photoshop / Affinity): the stroke under the cursor becomes the selection; duplicate / delete,
    flip / rotate, forward / backward / front / back, second colour, select all / none, fit; shortcuts shown; arrows /
    Home / End / Esc; items needing a selection greyed out. Shortcuts sheet grouped (Tools, Drawing, Selection,
    Transform and arrange, View, Edit and files, Sliders and fields, Library) with the new mouse gestures. Fixed on the
    way: Ctrl+Shift+] / [ (front / back) never fired (Shift turns them into } / {); Ctrl+Alt+N (advertised on New) had
    no handler. Contrast: the only colour under 4.5:1, `--faint`, was unused (now only disabled menu items).
    Checked in the page: thumbnails drawn (10 of 10), count, menu with / without a selection, keyboard focus moves,
    Duplicate 10 → 20, Ctrl+Shift+] brings the bottom stroke to the top, sheet groups.
  - **Final checks**: `/?perftest` on the finished code p50 1.9 ms, p90 3.4, max 11.1, first / last 500 px 2.0 / 1.9
    (release 21.8: now includes the preview refresh); golden 0.015 / 0.048 L*, worst 1.1, 0 stroke px off, two-colour
    0.134 (unchanged); `editor check` passes; brushtest not rerun: the brush output is byte-identical to the
    calibrated one. Not done (options, if more is wanted): predicted pointer events (draw ~1 frame ahead, then replace:
    lower felt latency, can overshoot on a mouse), a `desynchronized` canvas (hardware-dependent), a cheaper edge
    rasteriser for wide brushes (a look change: needs brushtest), painting in a worker.
  - **Snapping and alignment (user, same day: "optional snapping so elements can be aligned with each other or the page
    or spaced evenly")**: a stroke's box is now its visible pixels (alpha ≥ half; `tight`, cached per alpha array): brush
    bitmaps carry 2-3 px of empty margin, so aligned strokes would sit visibly off; selection outlines, handles and X /
    Y / W / H follow. Snapping (Figma / Affinity smart guides; top-bar magnet, Ctrl+Shift+; by key position, on by
    default, remembered): moving, the selection's box snaps within 6 screen px to the page's edges and centre, other
    strokes' edges and centres, the spot centred between its two row neighbours, and the gap already used in its row
    (a chain); scaling, the dragged corner snaps to the same lines. Pink guides: lines across both boxes, gap bars with
    their size. Ctrl pressed once dragging moves freely (Ctrl at the press stays Ctrl-click = add to the selection,
    Photoshop's convention). Properties → Align: left / centres / right / top / middles / bottom to the selection's
    box or the page (one stroke: always the page), space evenly across / down (3+, the outermost two stay, equal gaps
    between boxes), centre on the page (the selection as one block; nothing selected: the whole drawing; also in the
    right-click menu). Fixed on the way: the cached canvas box (ResizeObserver) could be one frame stale after the
    options bar changed height (tool switch), so the first press after it landed off; it is re-read once per press.
    Checked in the page (three lines): centred between neighbours 171.5 → 174 (= target), gap chain C → 235 (= B.r +
    gap), page centre 256, Ctrl during the drag and snapping off move freely, shortcut toggles, scale corner → page
    edge 512, align top 209 ×3, gaps 52 / 52, page centres 256 ×3, block centred (256, 256), one stroke right → 512
    with "Selection" greyed, guides drawn (screenshot: row line + "52" gap labels). `editor check` passes. Drawing
    speed unaffected (brush drags never enter the snapping code); a perftest under 33% foreign GPU load measured the
    committed and the new code alike (p50 2.0 / 1.9 ms; the 1.9 ms runs above were on an idle GPU).
- **7.0e (2026-10-18, user: "drawing still needs to be faster (basically no different from when not holding mouse 1)";
  "the parts still need cleaning up ... I can't easily find the damage type symbols ... maybe include colour if
  appropriate and categories")**.
  - **Measured in the user's browser** (default browser = Firefox 158; my numbers so far were Chromium): headless
    Firefox with a throwaway profile (`--headless --no-remote --profile <tmp>`, never the user's), `/?perftest` now
    posts its result to `/api/perf` → `data/editor/perf.json`; new real-time mode `/?perftest&rt`: one mouse move per
    animation frame, hovering, then drawing the same path, then moving the whole drawing; frame intervals + main-thread
    ms per frame. **Firefox before: hover 6.94 ms (144 Hz), drawing 13.88 ms median (half rate), p90 45, max 129, 171 of
    751 frames slow; main thread 14.6 ms a frame, of it the glow preview 11.8.** Cause: `gl.finish()` after every
    repaint plus a whole-canvas `texImage2D` from a GPU 2D canvas (Firefox reads it back across processes); Chromium
    pays 0.16 ms for the same. Fix: no `gl.finish` (`painter.ms` = time to issue the work); while a freehand stroke is
    drawn the composite lives in a CPU canvas (`under`, the brush's settled pieces too) and only the area the stroke's
    end changed (this frame's end ∪ the last frame's, which holds any piece that just settled) is recomposed and
    uploaded with `texSubImage2D`. **After (Firefox): drawing 6.94 ms median = hovering, p90 6.96, 9-11 of 751 slow
    (hover 4), main thread 1.8 ms; moving the whole drawing 6.94 / 6.96; the release frame 13.9 (one 144 Hz frame).**
    Frame test (synthetic): Firefox p50 6.38 → 1.90 ms, Chromium 2.1. The fast path's composite = a whole compose of
    the same frame (0 bytes off, checked by perftest). Golden unchanged (0.015 / 0.048 L*, worst 1.1, 0 stroke px off;
    two-colour 0.134).
  - Found on the way: another `python -m http.server 8765` (not this project's) shared the editor's port: Windows'
    SO_REUSEADDR (http.server's default) let both bind, so requests reached either server (headless Firefox got that
    server's directory listing). The editor now binds exclusively (`SO_EXCLUSIVEADDRUSE`) and moves to a free port
    when 8765 is taken; checked: a second bind is refused. Synthetic pointer events: Firefox's mouse is pointerId 0;
    `setPointerCapture` is best-effort now (a bad id threw and aborted the press).
  - **Parts panel**: (1) **Damage types**: the game's 11 damage-type symbols (`GenericIcon_DamageType_*`, read from the
    user's game files, D10/D28) are cut into strokes like the v1 icons (`python -m iconkit.editor symbols`, also run by
    `extract`; index kind "Symbol", "Damage symbols" in the Game icons filter) and lead the panel as captioned cards.
    Presets: the damage type's own (grammar group `damage/<type>`); Physical (bludgeoning / piercing / slashing, no
    group) the best-fitting one, Basic action white 2 (16.1 ΔE; next Action utility steel). Adding one: half size,
    centred (or at the drop point), and an empty Damage type field takes its type (an empty Intent becomes Damage), so
    the Auto colour matches the card. (2) **Colour**: every card is rendered as it will look: its strokes alone, glow +
    colour through `variants.master` in its source icon's colour (its second colour for D26 strokes), over the hotbar
    dark (`part_render`; `editor parts` ~4 min). (3) **Categories** (eye-checked on contact sheets of all cards,
    2026-10-18; D43's names were rejected as inaccurate, so these are coarse and checked): Damage types 11, Figures 22,
    Hands & arms 13, Creatures 11, Skulls & bones 5, Weapons 17, Objects 6, Elements & nature 16, Sun, moon & stars 5,
    Rays & effects 12, Frames & rings 10, Symbols & marks 13, Shapes & lines 8 (shapes I could not name honestly).
    `iconkit/parts_categories.json` (group key -> category, in git); a dropdown with counts, sticky section headings in
    "All". Right-click a card: hide / show, or move it to another category (the server rewrites the file). `editor
    check` fails on a visible card without a category. (4) **Clean-up**: 4 more cards hidden (2 near duplicates: 168
    of 169, 70 of 68; 2 stray bits: 134, 185): 48 hidden, 138 visible + 11 symbols. Checked in the page: dropdown,
    sections, Weapons filter 17, Fire added on an empty drawing (Damage Fire, Intent Damage, Auto Fire orange, half
    size), Cold dropped by drag, category move + back, hide + show, files unchanged after the round trips.
- **7.0f (2026-10-18, user notes)**: drawing performance "good now"; swatches "don't look good"; parts "inconsistent, they
  don't truly capture all of the common element" (screenshots: a piece of Glyph of Warding's rune, a small blob with
  sparks); tools "too subtle"; right panel: "when more layers appear the layers panel gets taller and pushes other
  important panels down"; "some controls could be along the top bar, e.g. the align buttons"; export "more robust /
  customisable ... sometimes you simply want just one copy of the icon to share online".
  - **Tools rail**: 40 px chips (21 px icons, raised, bordered) with the shortcut letter in a corner, the active tool
    filled with the accent, divider lines between groups; rail 54 px.
  - **Right panel**: Properties + Spell scroll together at the top; Layers has its own height (default 40% of the
    panel; drag the line above it, arrows, double-click / Backspace for the default; kept per browser) and scrolls
    inside, so new strokes never move the other panels; the in-game previews are a compact strip at the bottom
    (controller 72, hotbar 64 at 1:1, tooltip 100). The Export panel moved into the export dialog.
  - **Options bar (Move tool)**: align left / centres / right / top / middles / bottom, Selection | Page, space evenly
    across / down, centre on page (Affinity's context toolbar); Properties keeps X / Y / W / H, rotate and the stroke
    colour (its duplicate flip / arrange rows are gone: the bar, the right-click menu and the keys have them).
  - **Colour swatches**: each preset a tile on the hotbar dark with a glowing dot (its bright core into its glow
    colours), sorted by hue (red → orange → yellow → green → teal → blue → violet → pink, greys last), a ring for the
    choice, names in the tooltips; the chosen colour as a larger tile + name.
  - **Export dialog** (top-bar Export, Ctrl+E): Image = one picture to share: look (icon with glow, tooltip with fade,
    hotbar cell with frame, line art) × size 16-2048 (presets or typed) × background (none, hotbar dark, black, white,
    any colour), live preview, Copy image (clipboard; the blob is kept ready so the click's permission holds) and
    Download PNG; rendered by Python on the export path (`/api/image`; above 512 from the browser's sharp flattening).
    Mod files: mod name, game files / PNG set (+ 1024 / 2048) / line art for the model as checkboxes
    (`export_req` `what`). `editor check` covers a PNG-only export and a 128 px hotbar image. Checked in the page:
    every look and size, typed 300, download name, PNG-only export wrote just the 3 PNGs.
  - **Parts = whole common elements**: the user's two examples, measured: card 36 (Glyph of Warding) belongs to a
    group of the six Glyph variants, which draw the identical rune (two mirrored), yet 5.4's rule B kept a different
    third of the rune in each copy: it tests a stroke's pixels against the other copies' lines and a 16 px shift, and in
    a dense self-similar rune a shifted stroke still lands on lines, so real rune strokes fail. Card 241 (Tiger's
    Bloodlust) groups a drop shape that is a paw pad (Bear Claws), a rock (Boar Kick-up) and the tiger's nose: the
    common element is just a drop, and the picked copy was a piece of a face. Fix in the panel build
    (`editor.complete`, `embedded`): every copy lined up with the candidate through the part boxes (`parts.icon_box`,
    mirrored as needed), a stroke of the candidate's icon joins when a stroke of the same place and shape (IoU of the
    3 px dilated masks ≥ .4) is in ⅔ of the other copies (shape, not pixel hits); the picked copy is the best one that
    stands alone once completed (strokes within half its size outweigh it less than 1.5×); a small part (under 160 px)
    that never stands alone is a detail of larger drawings and is hidden ("a fragment ... (auto, panel build)"), a big
    one keeps its least crowded copy (the bow, always drawn with an arrow and a frame). Result: 92 strokes added to the
    picked copies, 14 cards merged into others once complete (36 is now the same full rune as 23), 12 groups became
    distinct (categorised by eye), 4 cards re-filed by their new content (a ring, a head, a wing, a fork), 3 more small
    fragments hidden by the rule (241, a heart, drops) and 3 broken pieces by eye (83, 158, 225): 54 hidden, 136 parts
    + 11 symbols shown in 13 categories. Contact sheets of every visible card checked (whole runes, frames, figures,
    weapons, skulls; odd shapes left in "Shapes & lines").
- **7.0g (2026-10-18, user notes)**: segmented buttons "don't look good at the border between options"; "being able to
  group together layers / strokes"; hi-res export "takes a while", smaller files without loss; parts still questionable
  (Arcane Lock's frame keeps a piece of the lock, a copy with a corner missing, the bow without its string, small bits
  on the acid spew and the heart); filtering "faster / more intuitive than a dropdown"; "the startup of the app takes a
  minute, where the window looks incomplete" (screenshot: status "loading…", canvas unplaced, empty panels).
  - **Start-up**: not reproduced here: a fresh server process prints its URL after 1.8 s, and the page is built and
    the session restored 1.2 s after navigation in Firefox (headless, `/?boottest`), 0.3 s in Chromium. The user's
    terminal showed every run on a random port: a stray `python -m http.server 8765` (not ours) held 8765 all day, so
    each run was a new origin (layout, tab and filters reset, nothing cached). Now: ports 8765-8775 before a random
    one (stable origin); a start-up screen covers the page until it is built and the session restored (step name, a
    seconds count after 3 s, the error if it fails: never a half-drawn page); every page load logs `page ready in X s
    (data, editor built, session restored)` in the terminal and keeps slow ones (> 4 s) in `data/editor/perf.json`;
    any request over 2 s is logged (`slow: GET /api/recipes took ...`). If it is slow again, the terminal says where.
  - **Segmented controls** (export Look / Background, Align to, eraser mode, stroke colour): a recessed track with the
    chosen option as a raised accent pill, options borderless with a 2 px gap (no shared borders, so no seams; the
    tabs' style).
  - **Library filters**: the dropdowns became one-click chips with counts (Parts: All + 13 categories with short names,
    full names in tooltips and the section headings; clicking the chosen one again shows all; Game icons: All / Spells
    / Actions / Illithid / Symbols), kept per browser; Parts got a search field (category, damage type, the game icons
    a part comes from: cards now carry `from`, their group's icons).
  - **Parts, round 3** (the user's five cards, measured with `complete_probe` / a prune probe): Arcane Lock's frame kept
    the lock's shackle because 5.4's grouping put it in (2 of the 3 copies are Arcane Lock icons); the "corner missing"
    card was the same frame from Arcane Lock: Dismiss, whose burst replaces a corner; the acid spew's "bit" was the
    creature's eye (in all three spit icons at the same place); the heart's bits were False Life's sparkle and dot; the
    bow is drawn without a string in every icon where it stands alone (the Ranged actions: a gripped arc under the
    arrow; full bows only fused with a figure), so it stays as the game draws it. Rules (panel build): (1) **prune**:
    a stroke that no copy from another spell family draws (`editor.family`: Spell_<School>_<Name>; Arcane Lock and its
    Dismiss are one family) goes from a "Frames & rings" card, and from any other card only when it is detached
    (`editor.off`: outside the convex hull of the shared strokes and over 10% of the part's size away: False Life's
    sparkle beside the heart). Pruning every unshared stroke was tried first and stripped a face's features, an arrow's
    head and half a crescent (other spells draw the shared shape with other details); (2) **strays**: strokes under 15%
    of the part's largest stroke that are off its larger strokes go (`editor.strays`: the eye, specks beside swords,
    ropes, rings); (3) **near copies**: a card from 2+ of the same icons that is 60%+ of another card and lies inside it
    (own boxes, 2 px slack) merges into it (the frame with a corner missing).
  - **Faster, smaller export images**: 2048 px took 9-12 s to paint. The glow is a wide blur: grown at 512 and enlarged
    it matches growing it at 2048 (0.003 L* mean, 0.2 max over the hotbar dark), so `variants.paint` does that above
    512; `grammar.tint` runs in 8 row bands on threads above 512² (numpy releases the GIL; identical numbers): paint at
    2048 9.1 → 2.3 s. The export dialog keeps the drawing's PNGs per drawing state and the server keeps the last 4
    painted images, so a background or file change only re-encodes (2048 in the dialog: 0.6 s instead of a repaint). Files: fully
    transparent pixels get black RGB before encoding (invisible; a few % smaller), and **WebP (lossless)** is offered
    for Download: the same pixels (checked by decoding), about 40% smaller than PNG (2048 Fireball 2,239 → 1,373 KB);
    Copy stays PNG (clipboards take PNG only). PNG `optimize` was measured and left out: 9% smaller for 9x the time.
  - **Layer groups** (Figma / Affinity): Ctrl+G groups the selection, Ctrl+Shift+G ungroups (also in the right-click
    menu); a group's strokes stay together in the stacking order; a click on the canvas picks the whole group, a
    double-click goes inside it (its strokes one by one; Esc or a click outside leaves, picking the group); Layers shows
    a folder row (fold, eye / lock for all, count, double-click renames) with its strokes indented; dragging a stroke
    among a group's rows puts it in that group, elsewhere it leaves; a group row drags as one block; Bring forward /
    back moves a group as a block (inside a group: among its strokes); duplicates (Ctrl+J, Alt-drag) land right above
    their originals, a whole group's copy is a new group; undo, drafts and autosave keep groups.
  - **Glow at the image edge** (user, with an Aura of Protection export: "never cut off in a sharp way by the edge"): the
    glow is grown with zeros outside the image, so a stroke near the edge left glow alpha .32 on the edge column (a hard
    band). The game fades its own glow there (Aura of Protection: alpha .01 / .07 / .16 at 0 / 4 / 8 px from the edge),
    though 786 of 1,083 game masters do touch an edge with glow or lines. Now the glow's coverage (and its light) is
    multiplied by a smoothstep of the distance to the edge per axis over 12 px at 512 (`variants.edge_window`,
    `EDGE_FADE`; `app/glow.js` `EDGE`, same formula in the final pass); lines are untouched. Measured on the hold-out
    rebuilds: median seen L* vs the game 2.44 → 2.50 at 24 px (16 px: 2.47, 32 px: 2.54); 24 px started too far in for the
    user ("start a little later ... it can still be close to the edge"), so 12 px (2.44 → 2.465, worst icon +0.16; 8 px:
    2.457): the user's drawing ends at
    alpha 0 / .12 / .37 at 0 / 4 / 8 px (8 px also looked soft: 0 / .23 / .47). `variants check` asserts it (a line 12 px from the edge). The glow fits
    (`glyph.rebuild`) are unchanged: the fade is a shipping rule, not part of the game-matched recipe.
- **7.0h (2026-10-18, user)**: "immediately accessible to other modders": (1) import their current icons in bulk and
  have them converted ("possibly into the vector version if it doesn't change the look of the strokes"); (2) a custom
  colour / gradient option ("some modders choose unique colours"); (3) tabs, to work on several icons and export them
  at once. Order: tabs (import opens into them), custom colours (imported off-palette icons need them), import, vectors.
  - **Tabs**: one per open icon above the canvas (colour dot, name, ×, middle-click closes, + / Ctrl+Alt+N new,
    Ctrl+Alt+W close, Ctrl+Alt+← → or arrow keys on the strip to switch). The open tab's drawing lives in the usual
    globals; the others keep theirs (strokes, groups, fields, undo / redo) in `docs[i].state`; the mod name is shared.
    Opening a game icon or a draft takes a new tab unless the open one is empty (golden runs stay in one tab). The
    autosave keeps every tab (`{v: 2, cur, docs}`; a v 1 file still opens). Export dialog: "Export all N tabs" exports
    each tab under its own name (duplicate names refused) and rebuilds the mod files once, at the end. The server takes
    `--drafts DIR` so test sessions never write the user's autosave. Checked in the page: open / switch / new / close,
    restore after reload (3 tabs), undo per tab, export all (2 icons, one atlas with both).
  - **Custom colours**: a "+" tile at the end of both colour lists opens a dialog: 1 colour = the nearest game preset's
    gradient turned to its hue and chroma (curve and lut rotated / scaled in a*b*: the game's chroma-by-lightness and
    glow / core differences kept); 2-4 colours = the modder's gradient, each stop at its own L* (a*b* interpolated along
    the lightness bins, the same at every opacity and distance). The light ramp (`lq`) is always a game preset's (the
    nearest), so lines stay bright and glows soft; the canvas previews it live ("Custom: Preview", never listed). Saved
    as "Custom: <name>" in `outputs/editor/presets.json` (`editor.custom_preset`, `register`, `/api/presets`): in every
    tab's list (a dot marks them; right-click: edit / delete; a deleted colour falls back to Auto). Glow recipe, hotbar
    recipe and frames borrow the nearest game preset (`hotbar.nearest`, `glyph.borrow` entries added in memory), so
    export, PNGs, hotbar cells and the mod need no other change. `editor check` makes a teal one, paints it (a* < -10),
    builds its hotbar cell and deletes it. Checked in the page: 1 colour (sea-glass teal Fireball + hotbar), a 3-colour
    gradient, Cancel restores, delete, a hotbar image through Python.
  - **Import** (library tab "Mine": Import files / Import folder / drop files or folders on the library; `editor.import_req`,
    `/api/import`, `/api/imported`, files in `outputs/editor/imported/`): files are grouped by name (a mod's tooltip and
    controller DDS of one icon share it), atlas sheets and AssetsLowRes copies skipped. Source: a ≥ 256 px image as is;
    else the tooltip icon with its faded strokes rebuilt (below); else the controller icon (144 px). User: "it should
    also take the tooltip ones which are faded and reconstruct them", "we would only need to recover the strokes":
    measured on 30-60 hold-out tooltips vs the game's masters, the fade only scales alpha, the colour channels still draw
    every stroke (dE76 0.8-3.2 even at fade < .05), alpha / fade turns the faded rows to haze (line IoU .26 / .11 / 0 at
    fade < .5 / < .2 / < .05). `editor.unfade`: the RGB lightness that best separates the lines on the unfaded rows
    (median fit IoU .96), a soft ramp around it below, gated by the alpha evidence (alpha / fade > .25 where any alpha is
    left; in the last rows only strokes continuing from above, else colour bleed made border strips): line IoU .91 /
    .88 / .64, sharper than joining the 144 px controller icon (.94 / .95 / .91 but its glow reads as haze lines), which
    stays the fallback when the colours don't show the lines (fit < .6). Colour (user: "extract the custom gradient for
    modders' spells"): the three game gradients nearest by curve are tried (rebuild error, mean dE76 over the hotbar dark,
    rows shown unfaded only); a colour fitted on the icon itself (`editor.own_colour`: curve, lq, lut from its pixels) is
    kept as "Custom: <name>" when no game gradient comes within 3 dE of it, and reused by later icons of the same look.
    Kind from the name's words (Action / Skill / Attack, TadpoleSuperPower / Illithid, else Spell). Each icon opens in a
    tab (first 30); its "Name in the game" field (new, Spell panel; export key, empty = Mod_Kind_Name) keeps the original
    name, so the mod's spells keep pointing at it; the hotbar frame follows the kind, not the name. Cards: a dot = own
    colour, an amber border = rebuilt look more than 6 L* off (painted / textured icons). Measured: tooltip-only Arcane
    Lock 1.2 L*, Fireball 1.6, a 512 PNG 1.9, a hue-turned Fireball 1.2 with its own colour; ~8 s an icon. `editor check`
    imports a tooltip-only Rush and a hue-turned Fireball. Checked in the page: drop of a tooltip + controller pair, a
    tooltip alone and an off-palette PNG → 3 tabs, export all → the atlas has the original names. Fix after a look:
    blending tooltip and controller doubled strokes a pixel apart (False Life's wreath): when a tooltip's colours fail,
    the controller icon is used alone (its lines match the game's as well, IoU .94).
  - **Vector strokes** (user: "possibly into the vector version if it doesn't change the look of the strokes";
    `app/vectorize.js`, right-click "To vector strokes", and on import when "Make vector strokes where the look stays" is
    ticked, default on): a game / imported stroke is a connected piece of the drawing, often several brush marks that
    touch, so one path per stroke converted 3 of 77. Now: mask (alpha ≥ 128) thinned (Zhang-Suen), staircase spares
    removed, spurs under a width pruned, the centre-line graph split into marks (at each junction the two branches that
    run on most straight, > 120°, continue each other; junctions closer than a width are one crossing), each mark a
    path through points every 0.8 widths with its median width and a taper at a free end that thins; dots a round dab.
    The marks are rendered (width ×1 / 0.9 / 1.1) and kept, grouped when several, only when together they cover the
    same pixels (`match`: IoU with 1 px edge tolerance ≥ .9); erased, too faint (no pixel ≥ 128) or changed strokes stay
    as drawn. Measured: Protection from Missiles 11 of 11 (by eye the same as the game's), the three test imports 22 of
    37 strokes (False Life 12 of 12, matching the game's icon). `node app/vectorize.check.mjs`: a line (1 mark), a cross
    (2), a dot (a dab), a ring (closed), match tolerance. User after trying: vectorising on import should be optional
    ("to avoid any of the weird artifacts"): the import checkbox is now off by default (opt-in; right-click To vector
    strokes stays).
  - **Barbs: thorny vs smooth strokes** (user: "some vanilla examples look like a sort of thorny vine, other times it's
    smoother"; with examples: Buff-gold rays, arcs, skulls; then "most actual Spell icons are thorny whereas most other
    passives / actions are smoother"). `research/probes/barbs.py` (all 1,083 v1 icons): the lines opened with a disc of
    .4 widths; each removed piece reaching 2 px+ is a barb (≤ 1 width) or a thorn (longer). A first try on skeleton
    chains missed most barbs (each thorn breaks the skeleton into short chains). Measured: barb length / width median
    .32 (p75 .57), base .71, swept 28° from straight out (IQR 12-46°), neighbours on a side swept the same way 71% of the
    time; barbs per 100 px of stroke by kind: **spells 3.1 (81% above 2.5), actions 1.0 (5%), illithid powers 1.3**:
    the user's reading holds. Brush: `v.barbs` per 100 px (`brush.js` BARB from the measures; generated along the arc
    length from their own random stream so a stroke being drawn keeps its barbs; none on tapers; thin swept triangles in
    `paint`, the pixel search widened only next to a barb). Calibrated so the setting reads as the game is measured: on
    closed circles (no cut ends, whose corners count as barbs) the measure reads .26 from the wobble alone and .67 per
    barb drawn (`BARB_CAL`); after: 1 → .95, 2 → 2.15, 3.1 → 2.93, 4 → 3.62. With barbs the mid / fine wobble is scaled
    (`BARB_NOISE` .75 / .75 / .83 / .75): /?brushtest then matches the game on fine width and centre wander; mid-scale
    width reads high because the test's clean runs between skeleton junctions leave most of the game's barbs out (noted,
    not chased). New strokes take the icon kind's value (auto; the Barbs slider sets your own, double-click returns to
    auto); strokes saved before keep none, so old drawings don't change. The page's measure (`vectorize.barbDensity`)
    first read .55 of the probe: a 3-4 chamfer distance (octagonal, widths 8% high) and the image edge counted as core;
    now an exact Euclidean transform (Felzenszwalb), integer disc, body length as the probe: Rush 1.5 vs 1.51, Arcane Lock
    3.2 vs 3.1, Thorn Whip 3.2 vs 3.1. Vectorising gives each converted stroke its own measured density (shape still
    judged without barbs). Freehand frame time with barbs ≈ without in the same run (5.0 vs 6.3 ms here; the pane was
    slow that day); live strokes stay byte-equal to the render (`fast_path_bytes_off` 0).
  - **Smoother / thornier game strokes** (user: "parts like the damage type icons ... thorny and smooth versions; or
    convert an icon's strokes between smoother / thornier"): a Barbs slider for selected game / imported strokes (Move
    tool options; the stroke's own density shown, reset = as drawn). The stroke's own barbs are cut (the same opening;
    pixels over 1.5 px from the barb-free body go, its soft rim stays) and the chosen density drawn on the body's edge
    with the measured shapes, swept along the stroke's main axis, normals from the distance inside the body, tips that
    would point back inside skipped, a 0.5 px soft edge; non-destructive (`it.barbs`, saved in drafts; the bitmap grows
    by the barbs' reach). Works on every part, damage-type symbols included. Checked: Chromatic Orb as drawn (2.8) /
    smooth / 1 / 5 rendered and compared by eye; restore after reload. `node app/vectorize.check.mjs` adds the measure
    (a plain line 0, six spikes on 200 px 3.05).
  - **Barbs that flow like the game's** (user, with ours vs vanilla Lightning: "the barbs do not look good or follow the
    flow of the vanilla versions"). `research/probes/barb_shapes.py` (200 icons, 4,999 spell barbs, each in its own frame
    along the edge): spell barbs are sawteeth, not spikes. The tip sits over the front end of the base (median .88, IQR
    .69-1.12; a third hook past it). The free part lies at 25° to the edge (IQR 12-45°, 2.1 times as long as wide), the
    tallest quarter stands up more (58°). Neighbours point the same way along the stroke on the same side (70%) and across
    it (62%), so the flow is the stroke's, not a side's. The old "lean 28° from the normal" came from base middle → tip and
    hid this. The opening sees only the free tip, so the footprint along the edge was set by eye against Lightning Bolt
    and checked with /?brushtest. New shape (`brush.barbShape` + `barbPoly`, shared by the brush and restyle): a splinter
    hugging the edge over `base` (median .8 widths), rising as the 1.5 power to `len` (median .27) at its front, a small
    notch under the tip (`hook` .05), 85% of a stroke's barbs one way. Restyled game strokes take the flow from the
    stroke's own path: steps along the body from one end (`flowOf`, two BFS passes), so zigzags and spirals keep it, not
    the old straight main axis. Rim points where the edge runs across the flow (ends, corners) and barbs with a foot off
    the body (narrow ends) are skipped; barbs are filled with the grey just inside the edge; all polygons share one winding
    (`addPoly`; mixed windings cut holes where barbs overlapped). Calibration redone (/?brushtest on circles): .8 per
    splinter (`BARB_CAL` [.26, .8]): 1 → 1.0, 2 → 2.16, 3.1 → 3.16, 4 → 3.73. `BARB_NOISE` .25 / .6 / .7 / .75: centre
    wander matches the game, mid / fine width read 17% high (the splinters carry them). New page `/?barbsheet=ICON,...`
    (as drawn | cut | restyled at the kind's value | a brush zigzag, saved as `barbsheet.png` in the drafts folder,
    measured densities in `window.barbsheetDone`). Restyled at 3.1, largest stroke measured: Lightning symbol 2.77,
    Lightning Bolt 3.06, Arcane Lock 3.55. Thorn Whip reads 6.0: cutting its long thorns leaves stumps that count as barbs
    (cut alone 4.75; thorns are not restyled). Perftest: fast path byte-equal, p50 3.6 ms.
- **7.0i (2026-10-19, user)**: "the tabs need better names than Parts, Mine ... and better design (maybe icons)";
  "closing tabs always prompts ... I want better tab management for closing / saving / editing multiple tabs"; a copy
  pass ("simple, concise and professional") and other languages without translating the app; high-res exports where
  vector and game strokes differ in sharpness; "make sure the app can easily be updated when it's distributed".
  - **Library tabs**: Icons (the game's) · Shapes (was Parts) · Imported (was Mine) · Drafts, each an icon over a short
    label; the open one raised with an accent bar and icon. The "Shapes & lines" chip reads "Lines" so it doesn't clash.
  - **Document tabs**: a tab is unsaved when its drawing differs from the one it was opened or last saved with (FNV hash
    of its saved form, so undoing back counts as saved; opened icons, drafts, imports and empty tabs start saved). The dot
    on the close button marks unsaved tabs (VS Code). Closing asks only for unsaved tabs: one dialog, Save / Don't save /
    Cancel, or for several a ticked list of which to save. The last 10 closed tabs reopen (Ctrl+Alt+T, the tab menu).
    Tab menu: Save, Save all tabs (Ctrl+Alt+S), Rename (or double-click / F2), Duplicate, Close, Close other tabs, Close
    tabs to the right, Close saved tabs, Close all; Ctrl- / Shift-click picks several (menu and Ctrl+Alt+W act on them);
    drag to reorder. Saving a tab = its draft (Ctrl+S too); the autosave keeps each tab's saved mark and draft name.
  - **Copy pass**: every visible string in the page, the help sheet, the export and colour dialogs and the import notes
    rewritten short and plain, one word per thing: stroke, vector stroke, game stroke, shape (was part), icon, tab, draft,
    thorns (was barbs), main / second colour. Dropped internal detail from the UI (L* distances, fit scores, file lists,
    "what the model sees"). Kept keys and file paths exact.
  - **Other languages without translating the app**: the browser's own page translation (Firefox's runs on the
    computer, Chrome / Edge right-click › Translate). The page is `lang="en"`, all text is in the DOM (titles become the
    styled tooltip on first hover, after the translation pass), nothing reads UI text back, and keys (`<kbd>`, menu
    shortcuts, tooltip key caps), the app name, coordinates and the export folder are `translate="no"`. Said in the help
    sheet's footer. Not tried with a real translator yet.
  - **Big exports: game strokes as sharp as vector strokes** (user's Moonbeam-like example: the vector crescent "looks
    out of place ... due to its sharpness"). Above 512 px vectors are drawn at full size, game strokes were smoothly
    enlarged, so their 512 px edge grew with the size (×4 at 2048: a ~6 px blur). `crispUp` (editor.js, used by
    `flatten`): after enlarging, the alpha ramp is made k times steeper about one half, so the edge is as sharp as at 512
    and the outline is the smooth curve through the 512 px pixels; only where the stroke is solid (its 512 px pixels
    within one reach alpha .7+, full from .95), so faint and fading strokes stay as enlarged. Checked at 2048 on
    Moonbeam with one and then 8 strokes converted: a game dot and a vector dot side by side now have the same edge.
    Dots (`n === 1` dabs) now take enough sides that no facet shows at large sizes (sagitta < .2 px; still 16 at the
    usual sizes, so 512 output is unchanged). Seen there and fixed next (below): straight-edged thorns, square ends.
  - **Vector strokes at 2048** (the follow-up above, done here at the user's request; all checked on Moonbeam converted
    and exported at 2048, before / after side by side):
    - Thorns (`brush.barbPoly`): finer back edge (10 steps) and a front edge that both wobble by up to .04 widths (the
      game's half pixel at 512) and a tip rounded over .08 of the height; the wobble comes from the barb's own size, so
      no extra random numbers and every barb stays where it was. Converted closed paths get thorns too (dots don't).
    - Boxy ends (`vectorize`): a run shorter than 1.2 widths is a round dot, not a 2-point path with two pointed caps;
      a traced line whose ends meet within .75 widths is closed with a corner there (Moonbeam's crescent, its two ends
      13 px apart at the tip); at a junction where two branches leave at an acute angle and a short spur (< 2 widths)
      runs to the tip, the branches join at a corner and the spur stays its own mark (a crescent outline: one closed
      path with a corner at each tip, the tip a dot or a short tapered stroke; was two arcs capped side by side, a
      creased beak; IoU .95-.99 on synthetic crescents). Two ends left over at a junction also join at a corner.
    - Brush corners: a corner too sharp for a mitre is now round (a bevel cut tips flat); a closed path whose only corner
      is its start gets its closing join (it had none: a flat cut); joins meet the body at its own edge points.
    - Hairlines: the canvas leaves a faint line (alpha ~210) where edges of one fill's pieces meet inside the stroke
      (seen at corners and tight bends; overlapping the pieces made it worse, and so did splitting quads into
      triangles). Fixed in `paint`: a pixel under 250 with opaque pixels on both sides (across, down, diagonal) takes
      their alpha; the outline never has opaque on both sides. Quads whose cross-sections cross (bends tighter than the
      half width) are drawn as four triangles (a self-crossing quad's negative lobe cut a hole). Dip pixels on the
      converted Moonbeam strokes: 33-41 → 0.
    - Game strokes at large sizes (`crispUp`): enlarged from a copy with a clear 1 px border (a bitmap cropped to its
      pixels was cut flat at its own edge) and blurred .4 source px before the sharpening (the line art's edges are
      pixel steps, the soft rim being the glow's: sharpened as they were, dots came out flat-sided).
    Checks: `node app/vectorize.check.mjs` adds a cut ring (stays open) and a crescent (closed, a corner at each tip);
    /?brushtest barbs 1 → 1.04, 2 → 2.22, 3.1 → 3.12, 4 → 3.75 (was 1.0 / 2.16 / 3.16 / 3.73), plain strokes
    unchanged; perftest fast path byte-equal, the hairline pass costs nothing measurable (A/B on vs off 4.03 / 4.04 ms
    per move in the same session); editor check passes.
  - **Updates** (D48): `iconkit/update.py` (check, stage, apply, rollback, build, test) and `iconkit.__version__`
    (0.7.0). The editor checks on start (2 s after the page is up, once per 6 h on the server), shows an "Update to X"
    button only when a newer release exists, and its dialog shows the release notes; "Update and restart" downloads
    and verifies, autosaves the tabs, and the server stops, installs and starts again (the page reloads when the version
    changes; the tabs come back from the autosave). Help sheet footer: version and "Check for updates" (off: only a
    local version request). Tested: `python -m iconkit.update test` (tampered download refused, a failure half way
    undone, edited lists kept, rollback, git checkout refused, real build) and in the page with a local v0.8.0 feed
    (`ICONGEN_UPDATE_FEED`): button, notes, download + verify; the install itself is refused in this git checkout by
    design. `editor check` adds the user-list layer. Open: where to publish (8.4), the launcher (8.1).
- **7.1** Fields: kind (spell/action), name, description, motif, intent, damage type, source (actions only, D34: class,
  monster, end-game ally, legendary action, magic item, weapon action, race, basic action; pre-set when starting from a
  game action); D32 + D34: school, spell type, level and use cost dropped, they change nothing in the drawing; N candidates; seed; colour (D17), frame (D19), **second colour + stroke picking** (D26: click
  connected strokes; a brush only if generated strokes turn out to touch), **element symbol** (D28: off by default, set
  to the damage type when ticked; size + spot presets centred / low centre / inside a frame, then drag; the 11
  `GenericIcon_DamageType_*` line arts read from the user's game, D10; lines under it cleared before glow and colour).
- **7.2** fields → prompt → diffusers pipeline (base + LoRA, user-supplied weights folder) → alpha →
  palette check/snap → master → variants → export.
- **7.3** "Make related action/skill" from the chosen spell icon (D4, settled: the same line art, its own colour field
  pre-set from the related intent, that colour's glow, same size and place; no model run, no variation). Vanilla
  precedent (2.5): 33 cross-family pairs are one drawing, 26 recoloured, 24 same size ±5%, stroke kept. Reapply variant
  (D35): the icon's line art shrunk (`links.reapply`, scale and offset `links.json` `reapply_scale`: 0.725, +4 px at 128)
  with the game's two-arc ring (median ring of the game's Reapply spells, from the user's files, D10), then glow + colour.
- **7.4** Prefill from vanilla BG3 spells (Phase 1 data) or SRD list.
- **7.5** "Based on series" (D30): the game's element series with a symbol slot (Divine Strike melee / critical /
  ranged, Chromatic Orb, Protection from Energy, Elemental Weapon; passive series in Phase 9), suggested when the typed
  name's part before ":" matches a series. A new damage type → `relations.compose` (sibling with the best-found symbol,
  base lines kept, new game symbol in the slot) → `series_colour` → glow + tint; no model run. The result opens in the
  editor (7.6) for changes. Colour-only and effect-drawing series (Glyph of Warding, Dragonborn breath) are not offered.
  D36: the list also holds the 19 frame families (`links.json` `frames`: legendary actions, Arcane Shot, Paladin auras,
  Divine Intervention, Mantle of Majesty, Magic Circle, Eyebite, Contagion, Transmuter's Stone...): code keeps the frame
  (lines in 80% of the members, from the user's game) and the inside comes from the damage-type library (element
  families), the model drawing only the inside (inpainting, method from 5.3) or the editor.
- **7.6** Draft editor (D31), the same canvas as the symbol stamp (D28): add a game icon by name (line art from the
  user's game, D10), pick strokes (click / shift-click / box; connected line parts as in `relations.parts_image`),
  move / scale / rotate / flip / delete, stamp symbols, erase. Output: the final line art (exact, then glow + colour) or
  the model's guide with a follow-the-draft slider (method from 5.3). D29's new-vs-copy score shown, not enforced, for
  guided icons. Freehand drawing later.
- Test: 5 official + 5 custom spells end-to-end → mod files → in-game check (user); one series composite (Divine
  Strike: Psychic) and one editor draft among them. From Phase 3: first the test mod (`research/probes/ingame_test.py` →
  `outputs/IconGenTest`, loose `Build-Mod.ps1 -All`): Fire Bolt / Dash / Hide show icons rebuilt from vanilla lines on the
  hotbar, tooltip and controller view, colours as the vanilla icon beside them; then deactivate it.

### Phase 8: Public release
- **8.1** Launcher: small zip with app code + `uv`; first run creates the env (torch CUDA, diffusers,
  gradio) inside the app folder. Each start: `uv sync` (an update's new libraries), then the editor; exit code 75 = start
  again (the in-app update's restart, D48), with `ICONGEN_LAUNCHER=1` set.
  **Built 2026-10-19.** `Start.bat` (Windows), `start.sh` (Linux), `Start.command` (macOS, runs start.sh). Everything
  goes into `.runtime/` (gitignored; delete it to start over): uv 0.12.18 (Windows: its release zip from GitHub, checked
  against the published SHA-256 with `certutil`, unpacked with the built-in `tar`; no PowerShell: Windows PowerShell
  started from PowerShell 7 failed to load its own modules; macOS / Linux: astral's install script with
  `UV_UNMANAGED_INSTALL`), a uv-managed Python 3.12 (`--managed-python`: the same Python everywhere, not whatever is on
  the machine), the env `.runtime/env`, uv's cache. The libraries are `requirements.lock` (compiled from
  `requirements.in` with hashes, `--universal`, `--exclude-newer 2026-10-01`, pinned to the minor versions the checks run
  on: numpy 2.4, scipy 1.17, Pillow 12, scikit-image 0.26), installed exactly by `uv pip sync --require-hashes` at each
  start. Deliberately no `pyproject.toml` at the root: a stray `uv run` / `uv sync` there would sync the developer's
  CUDA `.venv` down to these libraries. OpenCV dropped: `extract.icon_fade`'s one `cv2.GaussianBlur` is
  `ndimage.gaussian_filter(mode="mirror", truncate=4)` (max difference 4e-7). An update replaces `Start.bat` while it
  runs and cmd reads batch files as it goes, so it hands over to a copy, `.runtime\launch.bat` (without `call`). The
  editor's restart: the request sets a flag and stops the server; the main thread installs, then exits 75 (under the
  launcher) or replaces its process (a timer started from a request thread was a daemon and died with the server, seen
  in the test). Tested here: first start from nothing (uv downloaded and verified, Python + libraries set up, editor up;
  312 MB with the cache), then a staged release + restart: server stopped, install refused (git checkout, by design),
  exit 75, libraries re-synced, editor back on the same port. `update test` also checks the release has the launchers,
  executable in the zip, CRLF / LF line endings, and a lock that covers `requirements.in`. Not tried: macOS / Linux.
- **8.1b** Releases on GitHub (user 2026-10-19). `.github/workflows/release.yml`: a pushed tag `v<version>` (must equal
  `iconkit.__version__`, checked) runs `update test` and `update build`, then `gh release create` with the zip and its
  `.sha256` and notes generated from the commits; the app's updater reads that release (`/releases/latest`; the asset's
  `digest`, else the `.sha256`). To release: bump `iconkit/__init__.py`, commit, `git tag v0.7.1`, push the tag. The
  updater test needs no libraries (checked on plain Python 3.14), so the workflow installs nothing.
- **8.1c** Updates (D48, built 7.0i): set `update.REPO`; a release = `python -m iconkit.update build OUT` (zip +
  manifest + .sha256) attached to a GitHub release whose tag is the version (`iconkit.__version__`, bump it per
  release); `python -m iconkit.update test` before publishing.
- **8.2** Models: settings page points at a weights folder; optional "download" button that fetches
  the base model + LoRA from Hugging Face only when the user clicks it. VRAM presets (8 / 12 / 16+ GB).
- **8.3** Game data: read the 28 backgrounds (and vanilla spell list for prefill) straight from the
  user's BG3 `Data\*.pak` (LSPK reader; check format against LSLib source) or an unpacked folder.
- **8.4** README (setup, SRD 5.1 credit, licences), app licence, LoRA model card. Ask user: hosting
  (GitHub/Nexus/CivitAI) and app licence.
- Test: unzip on a clean folder, first run, generate, export.

### Phase 9: Passives (after v1)
- Passive 12-way bg rule (2.2 deferred), `PassiveFeature_`/`PassiveAction_` training data,
  "make related passive/condition" from a spell (D4), status-only icons.

### Phase 10: Class/Subclass icons
- `GUI\Public\Game\GUI\Assets\ClassIcons` (58 × 300², 58 × 140², 1 × 112²).

### Phase 11: Item icons
- `Tooltips\ItemIcons` 3,010 (380², 2 × 512²), `ControllerUIIcons\items_png` 3,045, six `Icons_Items*` atlases.

## Risks

- 10 GB VRAM for FLUX.2 klein 4B training (BFL lists 12 GB): train at 512, fp8 base, prompts cached, block swap;
  else a rented 24 GB GPU (~$0.50 per run) or SDXL (D39).
- A brand-new model may beat klein (FLUX 3 Image Klein, 2026-10-15): the LoRA is per base model, switching = one
  retrain (~1 h) if its licence allows (D11).
- ~1,000-1,300 usable spell-like icons: enough for a style LoRA; watch memorisation (5.3).
- Soft-glow alpha fidelity (5.1). Action glow is per-icon art, so the recipe is an approximation (2.2).
- Licensing: dataset stays private; LoRA release follows CivitAI precedent (Lykon); SRD needs credit.
- Public users without NVIDIA GPUs: v1 is CUDA-only (CPU fallback is slow); AMD/Intel only if asked.
- Torch first-run install is ~2.5 GB plus base model weights: state sizes up front in the README.

## Status log (newest first)

- 2026-10-19: repository set up (user): README.md (features, install, exports in a mod, developers, credits),
  description + 6 topics, wiki / projects off, delete branch on merge, Dependabot alerts + security fixes, private
  vulnerability reporting; pushed as cfcdbcf (with the update-check guard). No licence yet (user's call).
- 2026-10-19: published (user): `main` = one snapshot commit 088cfab as SpasticPengu in UTC (no personal strings,
  78 files); `data-v1` release uploaded and downloaded back by the app (3,524 files, SHA-256 checked); the update check
  now only counts `v<version>` releases (GitHub reported the lone `data-v1` as latest). Repo identity SpasticPengu + UTC.
- 2026-10-19: D10 amended (user): the icons ship as a `data-v1` download (`update.build_data` / `fetch_data`, checked
  against its SHA-256; hotbar backgrounds included, `paths.BACKGROUNDS` falls back to `data/backgrounds`), `NOTICE.md`,
  review PNGs back in git. Fresh-unzip test: launcher set up the runtime, downloaded and unpacked the icons, editor up,
  Fireball opened, hotbar preview, shapes, image and mod export all worked. Update test passes.
- 2026-10-19: repository `SpasticPengu/BG3-Icon-Generator` (public, empty): `REPO` set, remote added (no push); the
  updater reads "no release yet" (404) as no update (checked live); the six Larian-made review PNGs untracked and
  ignored (still in the old history: see Resume here before pushing).
- 2026-10-19: releases on GitHub (user): release workflow (tag = version → updater test, build, GitHub release);
  `REPO` waits for the repository.
- 2026-10-19: 8.1 launcher built and tested on Windows (first start from nothing, update restart via exit code 75);
  `requirements.lock` pinned to the tested versions, OpenCV dropped; vector conversion edge cases noted for later
  (Resume here); update test passes.
- 2026-10-19: 7.0i vector strokes at 2048: irregular soft-tipped thorns, no boxy ends (short runs → dots, loops closed
  with a corner, crescent tips joined), round joins past the mitre, closing join, no hairlines in strokes, game
  strokes enlarged without flat edges; vectorize check, brushtest, perftest, editor check pass.
- 2026-10-19: 7.0i updates (D48): `iconkit/update.py` (check, verified download, install on restart with backup and
  rollback, user files and edited lists kept, release build, self-test), Update button + dialog, version and opt-out in
  the help sheet, shapes lists' user layer, `DATA_V`; update test and editor check pass.
- 2026-10-19: 7.0i big exports: game strokes sharpened after enlarging (`crispUp`: alpha ramp ×k where solid), so they
  match vector strokes at 1024 / 2048; dots get more sides at large sizes. Checked by eye at 2048 (Moonbeam, mixed).
- 2026-10-19: 7.0i copy pass (short, plain, one word per thing; shapes, thorns) and browser translation support (keys,
  names and paths kept as written); editor check passes.
- 2026-10-19: 7.0i tabs: library sections Icons / Shapes / Imported / Drafts with icons; document tabs ask only when
  unsaved (Save / Don't save / Cancel, one list for several), reopen closed tabs, tab menu (save, save all, rename,
  duplicate, close others / to the right / saved / all), Ctrl-click to pick several, drag to reorder. Tested in the page.
- 2026-10-18: 7.0h barbs flow like the game's: barb shapes measured (`barb_shapes.py`: sawteeth, tip forward, one way
  along the stroke), splinter shape shared by brush + restyle, restyle follows the stroke's path; recalibrated
  (3.1 → 3.16); /?barbsheet; editor check, vectorize check, perftest pass.
- 2026-10-18: 7.0h barbs: measured on 1,083 icons (spells 3.1 per 100 px, actions 1.0, illithid 1.3), brush barbs by kind
  (calibrated on circles), Barbs slider for game strokes (smoother / thornier), vector import opt-in; checks pass.
- 2026-10-18: 7.0h vector strokes from bitmap strokes where the look stays (graph split into marks, coverage ≥ .9; on import
  by default); `node app/vectorize.check.mjs` and `editor check` pass.
- 2026-10-18: 7.0h import of modders' icons (files / folders, faded tooltips rebuilt from their colours, own gradient fitted
  when no game one fits, original names kept on export); `editor check` passes.
- 2026-10-18: 7.0h custom colours (one colour or a 2-4 colour gradient, saved for every tab); `editor check` passes.
- 2026-10-18: 7.0h tabs (several icons open, autosave of all tabs, export all tabs); checked in the page.
- 2026-10-18: 7.0g edge fade narrowed to 12 px (user: start later, close to the edge is fine); golden (0.015 / 0.049
  L*, worst 1.1), `editor check`, `variants check` pass.
- 2026-10-18: 7.0g glow fades out over 24 px at the image edge (export + WebGL preview; user: no sharp cut); hold-out
  rebuilds 2.44 → 2.50 L* median vs the game; `editor check`, `variants check` (new edge assertion) and the golden pass
  (one colour 0.015 / 0.049 L*, worst 1.1, 0 px off; two colours 0.137). Page GETs retry once on a dropped connection
  (a connect timeout in the pane stopped two golden runs).
- 2026-10-18: 7.0g parts round 3 (frame prune, detached-stroke prune, strays, near copies; 3 rebuilds, every changed card
  eye-checked; card 202 filed under Creatures), export speed (2048 px in the dialog ~3.5 s, paint 9.1 → 2.3 s; WebP
  lossless ~40% smaller), layer groups (Ctrl+G; checked in the page: pick, inside, Esc, arrange, duplicate, undo,
  drag-drop, autosave). `editor check` passes.
- 2026-10-18: 7.0g library filters as chips (parts categories, icon kinds) + parts search; checked in the page.
- 2026-10-18: 7.0g segmented controls restyled (track + pill, no seams).
- 2026-10-18: 7.0g start-up: stable port (8765-8775), start-up screen, boot times in the terminal and slow requests
  logged; boot measured 1.2 s (Firefox) / 0.3 s (Chromium), the user's minute not reproduced. `editor check` passes.
- 2026-10-18: user notes on 7.0e (7.0f): drawing "good now"; clearer tool rail; right panel with a fixed-height Layers
  panel; align / distribute in the options bar; colour swatches as glowing tiles by hue; export dialog (one image to
  share: look × size × background, copy / download; mod files with options); parts completed to their whole common
  element by stroke-shape matching across copies, fragments hidden (Glyph of Warding's full rune; Tiger's nose gone).
  `editor check` passes (now covering PNG-only export and a single image). Commit: see `git log`.

- 2026-10-18: user "drawing still needs to be faster (no different from not holding mouse 1)" + "parts need cleaning
  up, damage type symbols, colour, categories" → 7.0e. Measured in Firefox (the user's browser, headless, throwaway
  profile): drawing ran at half the frame rate of hovering (13.9 vs 6.9 ms, glow preview 11.8 ms of 14.6 per frame:
  `gl.finish` + whole-canvas upload); now drawing = hovering (6.94 / 6.94 ms, main thread 1.8 ms), moving too; golden
  unchanged. Editor port shared with another http.server through SO_REUSEADDR: exclusive bind now. Parts: damage-type
  symbols as a category, every card in colour, 13 eye-checked categories (dropdown, sections, right-click to move /
  hide), 4 more junk cards hidden. `editor check` passes. Commit: see `git log`.

- 2026-10-18: user "research UI/UX ... extremely polished; drawing faster if possible" → 7.0d. Drawing round 2:
  5,000 px stroke p50 8.1 → 1.8 ms, p90 11.7 → 3.6 (forced page layout per mouse sample removed, previews wait for
  release, centre line / noise / buffers extended instead of rebuilt; brush output byte-identical). Polish from the
  research (sources in the chat): scrubbable slider names + typed values, Properties scrub / arrow nudges, styled
  tooltips with key caps, on-canvas HUD, brush cursor cross, Hand double-click fits, compact top bar, layer thumbnails
  + count, canvas right-click menu, grouped shortcuts sheet; fixed Ctrl+Shift+] / [ and Ctrl+Alt+N, `]` stuck at 2 px.
  Golden / editor check pass. Then the user asked for snapping: smart guides (page, strokes, equal gaps) while moving /
  scaling, Align / distribute / centre on page in Properties, strokes' boxes = visible pixels. Waiting on the user to
  try it. Commit: see `git log`.

- 2026-10-18: editor v2 notes (7.0c, side session): (1) dock hide fixed (inline splitter width beat the hide rule; both
  docks collapse fully now, checked with resized widths); (2) every slider and both splitters reset by double-click or
  Backspace (checked in the page); (3) freehand frame time on a 5,000 px stroke (`/?perftest`): last 500 px 229.7 →
  9.8 ms, p50 83 → 8.1, release 260 → 13.5 (strokes painted in pieces, only the unsettled end per frame; brushtest
  recalibrated, golden unchanged); (4) polish pass (tabs, hover / disabled states, aligned fields, empty states,
  splitters, tab keys; list in 7.0c). `editor check` passes. Waiting on the user to try it. Commit: see `git log`.

- 2026-10-18: user's blind test 4 answers (planner path) → **11 of 11 right** (p = .0005): 10 planner icons (7 with
  nothing to start from, 3 series) + 1 free fallback (Animal Friendship), all told apart. Commit: see `git log`.

- 2026-10-18: user "D48 A ... Then run the planner test" → D48 settled; planner test (5.3 Planner note). Along the way:
  catalogue exemplars first cut with parts' exact-repeat strokes pulled in neighbours (pointing hand + skull, broadsword +
  rays + skull, fist + axe): objects now take the part's own strokes, figures the whole shape, 2 figure exemplars rejected
  by eye (`BAD_EXEMPLARS`), portrait / spell-slot star dropped (cut as hair / one point). transformers 5 returns a dict from
  `apply_chat_template`. Qwen3 with fp8 layerwise casting hit "CUDA illegal memory access" twice (after ~75 and ~10
  plans); plans.json resumes, the third run finished. `planner_inpaint` scored in `outputs/score53_v2` (0 inverted,
  nearest training drawing p50 .47, 1 copy ≥ .9). Blind test 4 made. Commit: see `git log`.

- 2026-10-17: user idea: a small "decision" model plans the icon's composition from the prompt, code puts it together
  from game parts, and only the regions that need something new go to the image model (= D42 + D48 automated). Measured
  (scratch `planner_ceiling.py`, `parts.json` shares, `compose_census.how`): the 44 hold-out icons with a vanilla start are
  already rule-planned (D28 / D30 / D36 / Based on); on the 48 with none, median line shares house parts 0 (≥ .25 in 16
  of 48), plain strokes .20, the icon's own compound drawing .54, so the planner mostly sets layout + house parts and
  splits multi-object motifs (blind 3 pairs 6, 7, 13, 15, 16), the image model still draws ~half. klein's text encoder
  is the full Qwen3-4B chat model (`Qwen3ForCausalLM`, tied head, chat template), so a local planner needs no new weights.
  Blocker: a planner picks parts by name and D43's names were dropped (name the house groups, or retrieve by motif words).
  Proposed test (after D48): Qwen3 plan JSON per hold-out prompt → compose + inpaint per region → kappa + a blind grid on
  the 11 unseen icons. Waiting on the user. Commit: see `git log`.

- 2026-10-17: user "Run the masked inpainting test" → `research/probes/inpaint53.py` (5.3 Masked inpainting note).
  First run left chance dots in the bases (lines 80% of members share by accident inside orbs / Divine Strikes; pasted
  back on top): base pieces under 200 px dropped, rerun (numbers after the fix; before: inside .45 / .45). Generation
  crashed once at model load (segfault, commit free 10.8 GB; as the training's first try), the retry ran. D48 proposed
  (chat): the model fills an erased / masked area of the editor draft. Commit: see `git log`.

- 2026-10-17: user "Run the Phase 5 draft test" → `research/probes/draft53.py` (5.3 Draft test note: numbers there).
  42 hold-out icons with a vanilla start (`compose_census.how` a-d; candidates limited to the icons in
  `outputs/trainset_all`), the klein inpaint pipeline with a full mask as img2img (strength .5 / .75 of 4 steps), the
  draft as `image_reference`, or both; free = score53_v2's 12000x2 images (same seeds). First run's D30 drafts pasted the
  symbol with its glow (relations' `B` = brightness incl. glow) and the model kept the haze: fixed (symbol = line share x
  B, like a training image), the 9 rebuilt and regenerated; numbers above are after the fix. The gen log's 9.6 GB peak
  includes prompt encoding (counter not reset), so it is not the generation peak. Commit: see `git log`.

- 2026-10-17: user on blind test 3: "the biggest giveaway is that it doesn't reuse some common elements like on divine
  strike where the sword is the same only the element is the real change. Some icons just don't look like anything
  describable like 6, 7, 13, 15, 16." Measured (scratch `blind3_notes.py` → `outputs/score53_v2/blind3_notes.json`;
  `compose_census.how` classes): of the 24, 4 are D30 element series (Divine Strike x3, Protection from Energy: Fire),
  7 have another series sibling in training, 13 nothing (as grids 1-2: 11 of 24 had a vanilla start). On the 11 with a
  sibling, the game's drawing vs its closest training sibling kappa median **.83** (Divine Strike .88, Protection from
  Energy .85, Disguise Self Drow .87, Step of the Wind .83, Hex .80), the generated one **.34** (Divine Strike .47-.52):
  the model does not redraw the shared sword; D30's rebuild reaches .90 (D42). 4 of the 7 "series" siblings are name
  ties, not the same drawing (Minotaur / Deep Rothe Gore .21, Giant Web / Web .10, Wild Shape .34, Disguise Self
  Dispel / Seeming .30). Pairs 6, 7, 13, 15, 16 have concrete motifs (hook-horror claw + arc; figure leaping in wind
  swirls + boot; figure flying in wind swirls + stars; chain + upright spiked mace + sparkles; three diamond footprints +
  speed strokes); the model draws the effect strokes (swirls, sparkles, speed lines) but the main object dissolves (claw
  → swirl, mace → a T, figures → tangles); kappa to the game's drawing .16 / .04 / .14 / .21 / .26 (these 24: median .24;
  all 184 hold-out images: v2 .253, v1 .252: more passes did not help). Both notes point at D42 (composite-first, house parts D43, brush D44), already
  settled; no new decision. 11 hold-out icons remain unseen by any blind test. Commit: see `git log`.

- 2026-10-17: user's blind test 3 answers (v2 12,000 x2) → **24 of 24 right** (p = 6e-8 by chance), as test 2. Per pair
  `tell_stats` (scratch `blind3_pairs.py`: real line art vs generated seed 0), median real / gen: cover .173 / .176,
  width 14 / 14.3, ends 50.5 / 53, parts 11 / 10 (stroke amount and size matched); **enclosed regions 1 / 3** (gen more
  in 16 of 24), **mirror .41 / .54** (Magic Jar .17 / .73, Devour Intellect .41 / .68, Fear .31 / .65, Bane .22 / .56),
  **taper .33 / .29** (gen blunter in 15 of 24), **roughness .943 / .931** (gen smoother in 18 of 24), width CV .35 / .37.
  So the giveaway stays the drawing (closed, symmetric, logo-like shapes, blunt ends), not the stroke amount. Asked the
  user which cues they used. Commit: see `git log`.

- 2026-10-17: user "Make blind test 3 on 12,000 x2" → `score53.py blind outputs/score53_v2 12000x2` (tests 1-2's keys
  copied into `outputs/score53_v2/` so `blind` leaves their 48 icons out; 0 overlap checked) →
  `outputs/score53_v2/blind_12000x2.png` (24 pairs, same code colouring both sides), key beside it, not opened.
  Waiting on the user's answers. Commit: see `git log`.

- 2026-10-17: user "Score v2 now: 8,000, 10,000, 12,000, 14,000 and the final, distilled at x2, then a sheet" →
  `ICON_RUN=klein4b_all_v2 score53.py gen outputs/score53_v2 holdout 8000:2 ... 16500:2` (184 images each, 1.33-1.38 s
  per image, 5.0 GB peak, ~25 min) + score / tells / steer; v1's `2500x2` copied in (its score reproduces: 2 of 184
  inverted). Inverted: v1 2, 8,000 2, then **0** at 10,000 / 12,000 / 14,000 / 16,500. Line chroma 0.6-1.1 (grey).
  Closest training drawing p10 / 50 / 90: v1 .34 / .44 / .58, v2 .32-.36 / .43-.46 / .55-.58, **no copies ≥ .9** (4
  passes did not make it copy). Kappa to the game's own drawing of the prompt (steer `to_real` median): v1 .252, 8,000
  .236, **10,000 .272**, 12,000 .253, 14,000 .259, 16,500 .249 (small spread: the drawing still differs from the
  game's). Tells (medians; real: cover .158, width 14, parts 11, ends 52, taper .33, holes 0, mirror .39): v1 .163 / 14.1
  / 9 / 45 / .37 / 1 / .49; 8,000 .188 / 18 / 7 / 31 / .28 / 1 / .58 (simpler, thicker, more symmetric); 10,000 .178 /
  16.1 / 9 / 47 / .38 / 2 / .34; **12,000 .185 / 15.2 / 11 / 59 / .29 / 2 / .41** (parts, ends, mirror, grey closest to
  real); 14,000 .183 / 12.2 / 12 / 68 / .37 / 3 / .41; 16,500 .177 / 16 / 9 / 50 / .28 / 2 / .38. v2 inks more (cover
  +.02-.03) and closes more outlines (holes 2-3 vs real 0, v1 1); v1's too-symmetric look (.49) is gone from 10,000 on.
  Sheet (`outputs/score53_v2_sheet.png`, 16 prompts, seed 0): v2 strokes rougher and more gestural than v1; 12,000 the
  most detailed figures (faces, minotaur); 10,000 a clean charging bull; 14,000 paints a grey filled block on Spiritual
  Weapon (greatsword); 16,500 breaks the minotaur. Read: 10,000 and 12,000 are the candidates, the user's blind test
  decides. Commit: see `git log`.

- 2026-10-17: **v2 LoRA done**: 16,500 steps in 6 h 33 min (1.43 s / step), exit 0; `outputs/lora/klein4b_all_v2/`
  (`_000002000` ... `_000016000` + final `klein4b_all_v2.safetensors`, 92 MB each), final loss 0.22 (one step's
  value, noisy). Base-model samples (seed 42, 25 steps; `outputs/klein4b_all_v2_samples.png`): white brushy line art at
  every save. Flask, snowflake (streaks from the left) and the unseen lantern hold at every step. Minotaur: a whole
  charging bull from 10,000 (head lowered + speed strokes at 16,500). Runner: the game's gesture figure (open head,
  single-stroke limbs) at 8,000-12,000, busier after. Paladin shield in the notched octagon from 6,000, but 10,000 and
  16,000 draw a "W" in the shield and 16,000 squares the frame. Illithid ring + thorny shaft never complete (16,500: a
  thorny ring, no shaft). Unseen anvil drifts to abstract blocks from 4,000 (10,000 closest): as in v1, the unseen
  object goes first. Read: 8,000-14,000 the best rows; one seed on the base model, so 5.3 scoring decides. Commit: see
  `git log`.

- 2026-10-17: user "I'm going to be AFK so can we do the training now?" → **v2 LoRA training started** (D45 void, so
  the Phase 4 captions as in v1: captions unchanged since `outputs/trainset_all` was built, latents + all 3,102 text
  embeddings came from the cache in 5 s). `tools/ai-toolkit/venv/Scripts/python.exe train/run_aitk.py
  train/klein4b_all_v2.yaml > outputs/lora/klein4b_all_v2.log 2>&1` (Bash). 1.42 s / step (v1 1.44-1.46), ~7.1 GB card
  total with Firefox open; 16,500 steps ≈ 6.5 h + a ~2.7 min sample round every 2,000 steps. First attempt died while loading the
  transformer with 0xC0000005 (access violation, no traceback, no Application event); the retry loaded fine. Commit
  free was ~11 GB (of 47.9) before the load and dipped to 9.7 GB at its peak on the retry: low commit is the likely
  cause (FPilot 3.8 GB, ~10 Claude processes, Firefox hold 28.5 GB private). Commit: see `git log`.

- 2026-10-17: user tried the editor and sent notes (too-smooth brush, vague parts, layered crossings, no eraser,
  pretty / intuitive / accessible, roughness option, retroactive taper, spline control, Photoshop / Affinity feel, light
  background, resizable panes, vector strokes for any size) → **editor v2** (Phase 7, 7.0b; 9ecaa51): union compositing,
  44 vague parts hidden + right-click hide, vector brush with game-measured edges (calibrated within 8%, `/?brushtest`),
  pen + point editing, eraser, docks / layers / properties / zoom / backgrounds / drafts + autosave, hi-res export.
  Checks: golden 0.018 L* (unchanged), `editor check` (export 0.011 L*, 1024 PNG, drafts, no scikit-image at runtime),
  scripted session in the browser pane (every tool, undo, export, reload restores the autosave). Test outputs removed;
  `outputs/editor/MyIcons` (the user's own export) left as is.

- 2026-10-17: **editor prototype (Phase 7, D46) on `phase-7-editor`** (side session started from the planning chat):
  `iconkit/lab.py` (runtime path without scikit-image, f3feb86), stroke data for 1,083 icons + parts panel of 186
  best copies (6927ac4; check sheet `data/editor/parts_sheet.png` sent to the user), stdlib server + browser editor +
  WebGL paint (303d021), fixes and `editor check` (f60cc0c). Golden: WebGL vs `variants.master` 0.018 L* median on 91
  test icons, ~1 ms per repaint; export path 0.011 L* vs `variants.build`. Every tool tried in the browser pane
  (dispatched pointer events: brush, line, circle, spline, select, move, flip, rotate, duplicate, delete, undo, box,
  part drop, export); found and fixed there: grid rows collapsing (aspect-ratio + overflow), the parts list not
  unwrapped, the server's default backlog of 5 dropping a burst of requests ("Failed to fetch" after 30 golden icons),
  no renders in a hidden tab (timer fallback). Details under Phase 7, 7.0; next steps in the Resume note.

- 2026-10-17: user asked about a portable Rust app (all platforms), then "Maybe not then. I just want it to be
  responsive/fast and multiplatform", asked how easy it is to install, and answered "Start in a new chat" to "record
  this stack and install method, then start the editor prototype?" → D46 (editor-centred local web app: browser
  vector canvas + WebGL live preview, Python `iconkit` backend), D47 (per-OS zip + uv launcher, model optional), D43
  amended (no names), D45 void, D5 amended, Phase 7 note. Measured for D46: Python glow + colour 391 ms at 512, 79 at
  256, in-game versions 187 ms (Fire Bolt, Dash, Hide, Chromatic Orb: Fire). The editor prototype starts in a new
  session on branch `phase-7-editor`. Commit: see `git log`.

- 2026-10-17: user: the part names are "not accurate for basically any of them"; step back and re-evaluate; app gist
  recorded under Goal (editor at the centre, programmatic wherever possible, parts panel of best copies, freehand +
  line / circle / spline, spell parameters, export or model reference). Re-evaluation in chat (Resume note): most of
  the gist is already settled (D31 editor, D42 composite-first, D43 parts panel, D44 house brush, 7.1 fields, Phases
  2-3 programmatic); what changes is that names and the motif rename go (D43, D45), the parts panel shows each part's
  best copy, the editor becomes the app's main screen with geometric tools, and the model test that matters next is
  draft-guided generation, not renamed captions. Waiting for the user's answer. Commit: see `git log`.

- 2026-10-17: user "why highlight just the head? I mean more general shapes" → **whole shapes** (5.4 amended):
  each group's repeated stroke now grows into the drawing it belongs to. (B) every group: the strokes the game repeats at
  the same place relative to the part anywhere in the icon (members lined up on the part, 4 px tolerance, in half or
  more of the other members, and only if that support drops by .3 when the stroke is nudged 16 px across itself: a
  crowded area keeps its support every way and never counts); adds to the part in 186 of 255 groups (median ×3.5): the
  whole legendary frame, the whole Divine Strike ray fan, both Reapply arcs, skulls with crossbones. (A) figure families
  only: the strokes joined to the figure (gaps under 18 px: heads float 13-16 px over their shoulders) up to the
  family's usual figure size (75th percentile of the members' joined-object boxes), never a stroke that closes round
  the figure (frame, ring, cross); gated on context .25 (the ally bust never grows, so Wild Shape animals stay out).
  Tried and dropped, by eye on the sheets: growing into the lines most members draw around the part (a ring took each
  orb's symbol, Heat Metal's daggers the breastplate), chance-correcting it (lost the figures' varying bodies), joining
  for every family (Divine Strike's sword joined the fire flame), a median-size box (the frontal figure stayed a head),
  a 12 px join (Soul Catching, Wholeness of Body, Umbral Shroud heads alone), the mean shift drop (refused long arcs and
  rays). A lone stroke cannot tell a slim sword from a slit pupil (kappa .9+), so `parts.EXCLUDE` lists the members an
  eye check put in the wrong family. Three rounds of two independent visual reviewers (subagent workflow) on the
  family sheets drove the fixes; renames: portrait (hair + shoulders merged), gesture figure, hooded figure (was
  "diamond"), spell-slot star, legendary frame, long-point star, slim sword / broadsword, beckoning hand, thunder whirl,
  orb ring, skull in profile (36 names). Known misses stated on the page (held weapons and motion lines join figures;
  Hold Person's figure is drawn joined to its frame; Otiluke's open sphere arcs and Revivify's joined cross still light
  up; Invoke Duplicity's hood floats 28 px off). Coverage (B only):
  house share of an icon's lines p75 22%, p90 48% (was 17% / 40%); 103 icons half or more house parts (was 72). The page
  questions were also rewritten (user: "a bit confusing"): 2 questions + a "settled without a question" list. Also:
  `strokes()` builds each icon's join graph once (a whole-image dilation per join round took the run past 20 min; now
  ~13 min). Commit: see `git log`.

- 2026-10-17: user "these questions are a bit confusing" → the page's 3 cards (they mixed naming, figure handling and
  a bookkeeping choice, in analysis terms) rewritten by a small workflow (2 independent plain-language drafts + a
  judge that read them cold and checked every fact against this plan and `parts.py`) into 2 questions + a "Settled
  without a question" list (Resume note). The judge also caught an error in my chat summary: Divine Strike's ray fan is
  one of the 36 names, not an unnamed series part. Page wording: "copies match" (0-1 line-overlap score) instead of
  kappa; over all 36 names the median is .96 (.97 for the 34 house-part names). Commit: see `git log`.

- 2026-10-17: Resume step (1) → **5.4 house-parts library** (D43), `iconkit/parts.py` + review page `data/parts.html`
  (method under 5.4). Measured: copies of a house part are near exact (median kappa .97 to the group's middle part).
  Figures: **ally bust 34 icons / 15 series, kappa 1.00 (94% exact)**, frontal figure (round open head and neck; body
  varies) 24 / 18 .92, Disguise Self portrait hair 20 / 6 .85 + shoulders 20 / 1 series .90, gesture figure head 7 / 7
  .96, star figure 4 / 4 .85. Of the 224 v1 icons whose motif names a figure (figure_sheet's regex, hold-out included),
  85 draw a house figure part; the other 139 draw a figure no other icon copies (biggest part's closest match elsewhere
  median .70, under the .75 group cut): many are the gesture figure, posed anew each time, so it is a style, not a stamp.
  Others: four-point sparkle 54 / 28 .99, skull 28 / 24 .95, dagger 20 / 19 .88, ring 20 / 16 .92, four-point star
  19 / 16 .87, healing cross 14 / 10 .98, sword 12 / 11 .96, drop 12 / 5 .93, fire symbol 10 / 6 .97, lightning bolt,
  necrotic skull, pointing hand, chevron, broken ring, spiky spore, legendary frame corner, Reapply ring, Divine Strike
  rays (5-34 icons). Today's motifs name one part many ways (ally bust: "standing" 28, "silhouette" 22, "human
  silhouette" 16; dagger: "sword" 14). Coverage: 444 of 1,083 icons draw a house part; house share of an icon's lines
  median 0 / p75 17% / p90 40% (with series parts 8 / 42 / 71%); 72 icons are half or more house parts. Mean shares by
  kind (house / series / plain strokes / own drawing): actions 13 / 9 / 32 / 45%, spells 10 / 16 / 21 / 52%, illithid
  5 / 1 / 33 / 60%. Cross-check: 12 of the 26 icons where D28 finds its damage symbol also show a named symbol part
  (multi-stroke symbols split into plain strokes); 83 of the 100 frame-family icons carry a grouped part. Page decisions:
  1 the names (A keep / B rename / C only parts in 8+ icons), 2 figures (A copied styles as stamps + gesture figure as a
  motif style / B all five as stamps / C names only), 3 series-only parts (A stay D30 / D36 material / B name them too).
  Commit: see `git log`.

- 2026-10-17: user "1A 2A 3A 4A in another chat" → D42 (composite-first), D43 (house-parts library, amends D29), D44
  (house brush in v1, amends D31), D45 (v2 waits for the part names) settled; work continues in a new chat from the
  Resume note. Commit: see `git log`.

- 2026-10-17: user (before another training run): compositing should play a larger role in prompting; an in-depth
  compositing feature from vanilla parts, plus freehand drawing in the vanilla stroke style; the blind icons lacked the
  game's common elements (test 2 pair 19, Chromatic Orb: Thunder = a circle + the thunder symbol); figures have a few
  limited styles, the generator makes a new one each time. Measured: (1) the 194 training icons whose motif names a
  figure (`research/probes/figure_sheet.py`; census `research/probes/compose_census.py`) use ~5 house figures: the blocky ally bust (round head, squared open
  shoulders) repeated nearly unchanged on dozens of icons (Wild Shape forms, party / ally effects, constellations),
  Disguise Self's one portrait template (~28 races), the gesture figure (single-stroke limbs, small open head) for
  action poses, the frontal standing / meditating figure, the spread-eagled star figure; 2.7's "no shared motifs" was a
  whole-drawing test and could not see shared parts. (2) How the app would make each hold-out icon: D30 element series
  9, D36 frame family 4, another series with a training sibling 26, copy of a training drawing 5, nothing to start
  from 48: 44 of 92 have a vanilla start, and 11 of each blind grid's 24 did but were generated freely (pairs 18 / 19 of
  test 2 are D30 cases). Decisions put to the user (chat): 1 composite-first, 2 parts library + exact house parts, 3
  house brush in v1, 4 v2 after the motif rename. Commit: see `git log`.

- 2026-10-16: user blind test 2 (`blind_base2500x1.png`, base model + LoRA x1, 24 icons not in test 1): 24 of 24 told
  apart (p = 6e-8 by chance); the base model is not the fix, my read of its strokes as "more Larian" was wrong. Prepared
  v2 (`train/klein4b_all_v2.yaml`: v1 at 16,500 steps = 4 passes, saves + samples every 2,000; only the length changes, so
  its effect can be read alone); `score53.py` picks the run by `ICON_RUN`, the last step's file by name. Commit: see
  `git log`.

- 2026-10-16: user blind test 1 (`blind_2500x2.png`): 21 of 24 told apart, "far too obvious"; user: "how much of the
  training data have we trained it with?" → 947 of 991 train icons in the set (Reapply 9, dark-line 6, no preset 29
  left out), 4,136 samples per weighted pass; step 2,500 at batch 1 = 0.60 of a pass (a lone drawing, 6 repeats, seen
  ~3.6 times; 1-repeat copies and big-series members 0.6 times, ~40% never). Recurring objects were seen often anyway
  (motif counts × repeats × .6: figures 194 icons ~460 times, hands 150 ~380, swords 129 ~340, skulls 43 ~120, flasks 6
  ~21). Line statistics (`score53.py tells`, medians, real / distilled 2,500 x2): cover .158 / .163, edge fringe .17 /
  .17, width 14 / 14 px, roughness .93 / .95, grey .91 / .89, parts 11 / 9, ends 52 / 45, width CV .36 / .38, taper .33
  / .37, enclosed regions 0 / 1, mirror overlap .39 / .49: the giveaway is the drawing (closed outlines, symmetry, less
  detail), not the stroke. User: the game has house conventions for figures, swords, maces, beakers, skulls. Base model
  + same LoRA x1 (28 steps, CFG 4, empty negative; `gen ... base:2500:1`, 18.4 s per icon, 5.0 GB): 0 of 92
  inverted, nearest training drawing .26 / .36 / .51 (none ≥ .9), mirror .35, taper .33, enclosed regions 1, fringe
  .39, width 12: open, gestural strokes like the game's (`outputs/score53_sheet_base.png`), the distilled model's
  prior is what closes and symmetrises them. Blind grid 2 from the base model on 24 icons not in grid 1 (`blind` now
  leaves out icons of earlier grids). Commit: see `git log`.

- 2026-10-16: user "Start 5.3 scoring on the all-kinds LoRA" → 5.3 part 1. `research/probes/score53.py`: prompts encoded
  once, transformer stored fp8 on the card (bf16 resident + Firefox spilled to 13 s per icon; peft casts a LoRA loaded
  after the casting to fp8, so load it first and skip `lora_` modules; free the old transformer, `.to("cpu")` + gc,
  before the next checkpoint, else 3.8 GB stays). Hold-out (92 prompts × 2 seeds) inverted at x1.5 / x2 / x2.5: 1,500
  57 / 18 / 5, 2,000 5 / 0 / 0, 2,500 19 / 2 / 0, 3,000 34 / 6 / 1, no LoRA 161 of 184; sheets
  `outputs/score53_sheet_3000.png`, `..._candidates.png`. Control row (no LoRA, Magic Missile / Hex / Dash / Levitate
  line art as references, 5.2 s per icon): 0 inverted, but shaded renders, caption text, grey fills; closest drawing
  median .53 and 3 copies ≥ .9 (Dash .96 into Boot of the Giants, .92 into Nether Brain; Hex into its own series):
  references copy, so use them only where copying is the point (drafts, frames); `outputs/score53_sheet_refs.png`.
  Unseen objects (`outputs/score53_unseen_sheet.png`, none + every 250 steps at x2): all 12 recognisable from 1,000 on,
  750 slips to shaded renders. Caption parts at 2,500 x2 (user question: would 5etools' fuller spell text give more
  direction?): the motif drives the drawing (dropping it: .36 to the full-caption image; .21 vs .25 to the game's
  drawing), the game description barely (.93 to the full image on the 52 captions that have one; to the game's
  drawing .250 vs .248); without a motif the game description gives no direction (.208 vs tags only .214); SRD 5.1
  text instead of the motif (23 spells) .236 vs game description .223 vs full caption .289. So fuller flavour text
  adds little next to a motif; 5etools' non-SRD text is not openly licensed (SRD 5.1 is CC-BY-4.0). Blind grid
  `outputs/score53/blind_2500x2.png` (24 pairs, same code colouring both; key `blind_2500x2_key.json`, not opened).
  D41 proposed. Commit: see `git log`.

- 2026-10-16: all-kinds LoRA done (`outputs/lora/klein4b_all_v1/`, 3,000 steps in 73 min at 1.44-1.46 s / step, 5.8 GB
  card total). Base-model samples (seed 42, 25 steps; `outputs/klein4b_all_v1_samples.png`): all 8 prompts white brushy
  line art from step 500; flask, snowflake, lantern good at every step; 1,500 the most coherent row (bull, runner,
  shield in the notched octagon, ring + thorny shaft, hammer over anvil); 2,000-2,500 rougher (bull abstract, runner
  broken, anvil prompt abstract from 2,000: the unseen object drifts first); 3,000 bull and runner back, frame becomes a
  rounded shield, ring a partial arc. Distilled 4-step (`research/probes/klein_lora.py`, now reads the run's own
  `config.yaml` prompts; ~5.3 s per icon, peak 7.8 GB): step 3,000 x1.0 4 of 8 inverted (bull, runner, shield, ring:
  black on white), x1.5 1 of 8 (runner silhouette), x2 1 of 8, x2.5 0 of 8 but plainer lines and the octagon frame lost
  (D36: code restores frames). Step 1,500 x1.5: 3 of 8 inverted (bull, runner, shield). Unseen lantern and anvil clean
  on distilled at every strength. Spells are never inverted; the actions' silhouettes are what the distilled prior pulls
  to black on white. Commit: see `git log`.

- 2026-10-16: user "Resume" → all-kinds LoRA restarted and training. The stall was in text-embedding caching only:
  `train/run_aitk.py` now logs memory and each part's device at every AI Toolkit device switch. During
  `cache_text_encoder` the transformer IS on the CPU (unet cpu, te cuda:0) and PyTorch holds 4.67 GiB allocated / 4.85
  reserved, yet Windows' counter gives the python process 9.5 GB dedicated (Firefox 2.1, dwm 1.7 on top: the card is
  oversubscribed and WDDM pages, 236 → 1.3 captions / s as it fills). The extra ~4.7 GB sits outside PyTorch's
  allocator (cause not found; AI Toolkit's cudaMallocAsync switch is off) and is gone once the encoder moves off (5.5 GB
  card total while sampling). Only the 123 uncached r6 captions were left: done in 1.5 min; all 1,034 r6 embeddings are
  on disk, so training never caches again. Training itself as the spells run: ~1.56 s / step, 5.8 GB card total. If
  new captions ever need caching: close GPU-heavy apps (browsers) first. Commit: see `git log`.

- 2026-10-16: first LoRA done (`outputs/lora/klein4b_spells_v1/`, 2,000 steps in 52 min, checkpoints every 250, 92 MB
  each; sheet `outputs/klein4b_spells_v1_samples.png`). AI Toolkit's base-model samples: white brushy line art from step
  500 on (250: flask inverted, snowflake blue), clock / cauldron wobble at 750 and return; at 2,000 all 6 prompts
  recognisable, the 3 unseen objects (lantern, cauldron, clock) never collapse into training motifs. **Shipping path
  checked** (`research/probes/klein_lora.py`, `.venv` + `peft`; sheet `outputs/klein4b_spells_v1_distilled.png`): the
  LoRA loads on the distilled klein 4B in diffusers; at strength 1.0 2 of 6 come out inverted (black on white), at 1.5
  all 6 white on black and brushy, ~6 s per 512 icon (4 steps, whole-model offload, peak 7.8 GB bf16); the base model
  in diffusers (single file, 28 steps, guidance 4) looks alike at ~23 s. Without the LoRA the distilled model writes
  caption words as text ("UUTICY"). D39 amended: ship distilled + LoRA x1.5. Commit: see `git log`.

- 2026-10-16: user "download the base transformer and install AI Toolkit" → 5.2 started. AI Toolkit (commit 12395a1) in
  `tools/ai-toolkit` (gitignored) with its own venv (torch 2.13 cu130, its pinned diffusers); it loads klein from BFL's
  single file, so `models/FLUX.2-klein-base-4B/flux-2-klein-base-4b.safetensors` (7.75 GB) instead of the diffusers
  transformer, and hard-codes the text encoder to the hub's Qwen/Qwen3-4B: `train/run_aitk.py` points it at
  `models/qwen3-4b` (hard links to the encoder already downloaded: stock Qwen3-4B, 36 layers, 2560 wide). VAE from
  `ai-toolkit/flux2_vae` (small, automatic). `iconkit/trainset.py`: D27 + D33 weights as repeat folders (R 6; `check`:
  lone drawing 1, copy group 1, Disguise Self's 31 train icons 5.29), leaves out hold-out, Reapply (D35), dark-line (D25,
  6 icons), no-preset icons. Spells: 343 icons, 1,486 samples per pass (`outputs/trainset_spells`). Run
  `train/klein4b_spells.yaml` (rank 32, 512 px, fp8 base + encoder, embeddings cached, lr 1e-4, 2,000 steps, save +
  6 samples every 250): **fits easily, ~1.5 s / step, 6.1 of 10 GB in use with other apps**. Step 250 already draws white
  brushy line art on black, the unseen lantern / cauldron / clock recognisable; flask came out inverted (black on
  white), snowflake blue-tinted. Sheets: `python train/samples_sheet.py RUN_DIR OUT.png`. Commit: see `git log`.

- 2026-10-16: user "start 5.1" → `research/probes/alpha_readback.py` (162 train + 89 hold-out, 15 min) + an illithid
  sweep (all 41, k .02-.3) + a look at the worst two at 512 (`outputs/alpha_illithid_look.png`) → D40: k = .8 for every
  kind (spells .30, actions .32 L* added; illithid 4-5 at any k, .8 without the dark rim lower k draws). 5.1 done. Base
  model check for 5.2: only `FLUX.2-klein-base-4B`'s transformer differs (7.75 GB). Commit: see `git log`.

- 2026-10-16: user "download the non-shrunk version" → `models/FLUX.2-klein-4B` (diffusers parts, 15 GB, sizes match
  HF). Anaconda's torch is the conda CPU-only build, so a project uv env `.venv` (gitignored; user chose it over
  replacing Anaconda's): torch 2.11.0+cu128, diffusers 0.41.0, transformers 5.20.0, sees the RTX 3080.
  `research/probes/klein_unseen.py` (no LoRA, 12 unseen objects × 2 seeds, 512 px, 4 steps) → sheet
  `outputs/klein_unseen.png`: all 24 recognisable, but generic clip-art outlines (even thin strokes, closed symmetric
  shapes, front views), not Larian's line style: what the LoRA has to teach. 5.3-6 s per image with whole-model CPU
  offload (mostly moving weights), peak 7.8 GB (bf16; 8 GB cards will need the fp8 weights). Commit: see `git log`.

- 2026-10-16: user asked whether klein can draw things the game never drew → 5.3 gets an unseen-objects test (12
  objects in 0 of 1,083 motifs, every checkpoint vs no LoRA, user judges). Diffusers download for `FLUX.2-klein-4B`:
  transformer 7.75 GB + Qwen3 text encoder 8.05 GB + VAE 0.17 GB ≈ 16 GB (HF API). Commit: see `git log`.

- 2026-10-16: user "choose the best model/architecture ... the best approach in general" → D39: FLUX.2 klein 4B, one
  LoRA (train on base, run on distilled), reference images for drafts / frames / symbols, alpha read back (5.1 a), SDXL
  fallback; D8 superseded. Checked on model cards / diffusers docs the same day (Environment, D39). Phase 5 amended
  (5.1-5.3, gate), Risks updated. Nothing run. Commit: see `git log`.

- 2026-10-16: user "merge and rerun" → `kk/beautiful-torvalds-90cfb0` (2.5-2.7 rerun on D38 lines) merged into `main`
  (`--no-ff`, plan conflicts resolved: both Status entries kept, D38 row / header say merged). Main's `data/` reran
  with the merged code from a temporary `main` worktree linked to it: `relations run / check / report` (9.3 min),
  `shape` (8), `links` (2.7), `glyph report` (1.4, `glyph.html` was stale): checks pass, `relations.json`,
  `shape.json`, `shape.npz`, `links.json` byte-identical to the branch's run. Old files kept as `data/*.pre-d38.*`;
  Dragonborn sheet copied to `data/dragonborn_frame_family.png` (user look, D36). `phase-5-bakeoff` fast-forwarded to
  `main`. Commit: see `git log`.

- 2026-10-16: user "merge main into phase-5-bakeoff" → fast-forward to 660a36e (the branch had no commits of its own);
  `glyph check` and `variants check` pass in the main checkout against its refit `data/glyph.json`. This note committed
  on `kk/nice-fermat-a131f2` and `phase-5-bakeoff` fast-forwarded to it. Commit: see `git log`.

- 2026-10-16: user "merge" → `kk/nice-fermat-a131f2` merged into `main` (`--no-ff`, 97d54b8; it also carries 9ce5a1f,
  the Phase 4 plan note). Main's `data/glyph.json` refit with the merged code from a temporary `main` worktree whose
  `data/` linked to the main checkout's (fit 10.4 min, `variants test` 4.7 min): byte-identical to the branch's run, 3.1
  spells 1.18 / actions 2.84 / illithid 1.62 / metamagic 3.07 L*. Old files kept as `data/*.pre-d38.*`. `phase-5-bakeoff`
  does not have D38 yet. Commit: see `git log`.

- 2026-10-16 (side session, branch `kk/beautiful-torvalds-90cfb0`, fast-forwarded onto D38's `kk/nice-fermat-a131f2`;
  D38 not yet in `main`, so run in the worktree's own `data/`, masters junctioned read-only from main): `glyph fit`
  (identical to D38's `glyph.json`), then `relations run / check / report` (12 min beside the glyph fit; the local line
  test costs 0.5 s per master at 512 px), `shape run / check / report` (8 min), `links run / check / report` (3 min);
  old outputs kept as `*.pre-d38.*`. No settled decision's evidence flips (2.5-2.7 "Rerun on D38 lines"): D27 31 / 76,
  D29 .50 / .84, D30 .90, 2.6 22 of 22 verdicts kept, D34 yes, D35 .84-.97, D36 + Dragonborn breath (user look). Not
  merged. Commit: see `git log`.

- 2026-10-16 (side session, branch `kk/nice-fermat-a131f2`): glow leak fixed, D38. Probe `research/probes/glow_leak.py`
  reproduced the Phase 4 numbers; prototypes on every 5th training icon (top-hat, midpoint over an opening floor, over an
  erosion floor; radii, cap, midpoint); the erosion-floor midpoint kept illithid lines unchanged and halved the glow-made
  share. The first refit made 3.1 worse (spells 1.38, actions 3.11): `glyph.rebuild` composed lines and glow unlike
  `variants.paint`; fixed (also `relations.paint`), refit: 3.1 spells 1.18, actions 2.84, illithid 1.62, metamagic 3.07.
  Checks 2.4 / 2.5 / 2.6 / 3.1-3.3 pass; hotbar untouched (no `CACHE_V` bump). Not merged; main's `data/` still has the
  old `glyph.json`. Commit: see `git log`.

- 2026-10-16: user "merge" → `phase-4-captions` merged into `main` (`--no-ff`, 54d3d1a); branch `phase-5-bakeoff` made
  from `main` for the next chat. Commit: see `git log`.

- 2026-10-16: user "Round 2 captions all read fine" → **Phase 4 done** on `phase-4-captions` (not merged). Resume here
  rewritten for Phase 5 (ask about the merge first). Commit: see `git log`.

- 2026-10-16: user's spot-check round 1 (13 of 30 noted). Fixed with their class: all 293 direction / facing motifs
  rechecked at 300 px, 62 of 181 weapon directions were backwards; 96 motifs rewritten, captions rebuilt, page shows
  round 2. Found from notes 4 / 15: glow leaks into the line art (12% of icons at 15%+ glow-made line pixels), a
  pre-Phase 6 line-extraction fix, not a caption one. Commit: see `git log`.

- 2026-10-15: 4.1 + 4.2 done. 1,083 motifs from 68 contact sheets (`iconkit/motifs.jsonl`), template applied
  (`captions build` → `data/captions.jsonl`, `check`), spot-check page `data/captions.html` (30 captions). Hand sources
  refined while looking (the five Perform instruments → basic action, Wild Shape bat → Druid). Next: the user's notes on
  the 30 captions. Commit: see `git log`.

- 2026-10-15: Phase 4 started (new chat). User "Merge" → `phase-3-exporter` merged into `main` (`--no-ff`, 609d427),
  branch `phase-4-captions`. 4.0 done: action sources 503 → 632 of 639 (`links.unlocks`, comma lists, feats, weapon-action
  flag, `links.HAND`); D34's test still yes (23.6% vs 6.7%). `iconkit/captions.py` started (contact sheets). Commit: see
  `git log`.

- 2026-10-15: user "why do we need an in-game test?" → "Ok, but don't start phase 4 in this chat". D37 settled on the
  evidence (3.3), the in-game look moved to Phase 7's test (test mod kept). **Phase 3 done**, branch not merged. Resume
  here rewritten for Phase 4 in a new chat. Commit: see `git log`.

- 2026-10-15: user: "why a pak?", "PNG at any resolution". No pak needed (D37 puts everything under `Mods/` and
  `Public/<Folder>`, which loose `-All` deploys); test instructions now loose. `variants.sized / pngs` + `png` CLI: PNGs at
  any size (plain + tooltip fade) and the 64 px hotbar PNG; self-check extended. Commit: see `git log`.

- 2026-10-15: user pointed at Larian's UI docs ("look more thoroughly online"). Read the official UI and "Adding Skill and
  Item Icons" pages, community tools (bg3_mod_helper, bg3.wiki, Nexus) and Larian's own files (Patch 8 GUI metadata,
  TextureBanks, atlas, AssetsLowRes, formats). D37's layout is the Toolkit's own; one gap fixed: `export` now writes the
  half-size `AssetsLowRes` copies every vanilla icon has. Findings under 3.3. Commit: see `git log`.

- 2026-10-15: 3.2 + 3.3 done. `iconkit/dxt.py` (own BC3 encoder; Pillow's shifted line colours and blocked up hotbar
  cells: 8.0-8.7 → 5.1-5.6 /255), `variants.dds` (vanilla header, atlas mips), `variants.export` (atlas + map +
  TextureBank, tooltip / controller as new GUI textures + metadata, D37 proposed), checks extended. Test mod
  `outputs/IconGenTest` (Fire Bolt, Dash, Hide get icons rebuilt from vanilla lines), Divine converts it. Next: the user's
  in-game look. Skill `bg3-icons` updated (GUI-texture layout, Pillow encoder caveat). Commit: see `git log`.

- 2026-10-15: user "Phase 3" → branch `phase-3-exporter`. 3.1 done: `iconkit/variants.py` (line art format, `master()`
  with code glow + one tint, two colours by nearest stroke, `variants()` controller / tooltip / hotbar, `test`, `check`).
  Vanilla lines → master within 1.4 L* (spells), 2.8 (actions) over the hotbar dark; hotbar from lines 12.04 / 16.75
  (gate 18.1). Sheet `data/variants.png` checked by eye. Next 3.2 DDS. Commit: see `git log`.

- 2026-10-15: user "Just merge" → `phase-2-grammar` merged into `main` (`--no-ff`, local; no remote). Phase 3 starts on
  `phase-3-exporter` when the user says so. Commit: see `git log`.

- 2026-10-15: user "1A" → D34 (actions name their source in captions and the app; spell type out, D32 amended);
  `links.DECIDED` complete, page rebuilt; 4.2 (template, source words, labels to finish for 136 actions), 7.1 amended.
  2.7 closed, **Phase 2 done**; next Phase 3 after the user merges. Commit: see `git log`.

- 2026-10-15: user "2A 3A, can you explain 1 more clearly?" → D35 (Reapply in code, out of training), D36 (frame families
  in Based on series) settled; 5.3, 6, 7.3, 7.5 amended; `links.DECIDED` set; decision 1's card rewritten as two questions
  (source, spell type) with example captions per option; D34 still open. Commit: see `git log`.

- 2026-10-15: 2.7 connections audit (user request). `iconkit/links.py` (action sources from progressions / items / names /
  wiki, flyouts, Reapply rebuild, frame families, page, self-check); `extract.spell_containers`; `shape.series` joins
  flyouts and Reapply (698 series), `shape.npz` keeps K. Found: action source changes the drawing; spell type on actions
  only weak once flyouts count once; Reapply in code .86-.97; 19 frame families. Page `data/links.html` decisions 1-3
  (D34-D36 open). Commit: see `git log`.

- 2026-10-15: user "1A 2A" → D32 (prompt and app fields follow the shape test), D33 (training weights per series,
  1/sqrt(n); D27 amended); `shape.DECIDED` set, page rebuilt; 4.2, Phase 6, 7.1 amended. 2.6 closed, **Phase 2 done**;
  next Phase 3 after the user merges. Commit: see `git log`.

- 2026-10-15: 2.6 shape vs spell fields. `iconkit/shape.py` (17 line-art shape numbers, kappa nearest drawing, series
  linking, per-field tests against intent-kept shuffles, page, self-check). Found: per icon every field looks shape-bound
  because of series (Disguise Self's 33 faces = "Illusion"); one per series only intent and the actions' spell type change
  the drawing. Page `data/shape.html` with decisions 1-2 (D32, D33 open). Commit: see `git log`.

- 2026-10-15: user "4A 5A" → D30 (series composites in code), D31 (draft editor in v1, minimal tools); `DECIDED` set,
  page rebuilt (all 5 decisions made); 5.3 (draft-guided test), 7.5 (Based on series), 7.6 (editor), 7 test amended.
  2.5 closed; next 2.6. Commit: see `git log`.

- 2026-10-15: user notes (series composites like "Divine Strike, psychic"; a draft editor of game parts). Measured:
  composites rebuild real series members at kappa .91 (sibling .84, better 140 / 155), rendered missing elements;
  icons split into median 14 strokes. `relations.py`: symbol slots, `composite` / `compose` / `series_colour` / `paint`,
  `parts_image`, check extended. Page decisions 4-5 (D30, D31 open), 1-3 folded under "Earlier decisions". Commit: see
  `git log`.

- 2026-10-15: user "1A 2A 3A, but symbols stay exact, the model makes new icons" → D27, D4, D28 settled, D29 added.
  Measured the yardstick for "new": test icons' closest training drawing kappa median .53, p90 .83 (`relations.json`
  `novelty`); page row added, phases 3.3 / 4.2 / 5.3 / 6 / 7.1 / 7.3 amended. Next 2.6. Commit: see `git log`.

- 2026-10-15: 2.5 relations. `iconkit/relations.py` (kappa shape score on line art, same-drawing groups, cross-family
  pairs, status icons, element symbol search, page, self-check). Found 32 v1 copy groups (5 test icons with their drawing
  in training), 33 cross-family same-drawing pairs (recoloured, same size), statuses reuse the spell's icon 56%; the
  user's mid-step note on damage-type symbols measured (one reused symbol per element, rarely on plain spells). Page
  `data/relations.html` with decisions 1-3 (D27, D4, D28 open). Commit: see `git log`.

- 2026-10-15: user "2A" → D26 (a second colour per stroke). `extract.TWO_TONE` (the 8 metamagic icons; `glyph.run` warns
  if its detector disagrees); `grammar` fits presets without them (Metamagic red retired, every other preset identical)
  and stores their part presets (`two_tone`); `hotbar.frame / compose(second=)` give two-colour actions
  `frame_two_tone` (`metaMagic` ×1.02, moved from the old Metamagic red entry in `hotbar.json`; no refit, D24); self-checks
  extended. Phases 3.1, 6, 7.1 amended. Before copies `data/grammar.d26.json`, `data/glyph.d26.json`. Commit: see `git log`.

- 2026-10-15: user raised metamagic icons (8 images). Measured: they are v1's only two-colour icons, every stroke one
  colour, each part an existing preset (drop Control rose; symbol steel / Basic action white 2 / Buff gold / Debuff
  magenta). `glyph.colour_split` + self-check; decision 2 on `data/glyph.html`. Commit: see `git log`.

- 2026-10-15: user "1A" → D25 (the model draws line art, code grows the glow); D18, 3.1, 4.2, 5.1, Phase 6 amended. The
  user's note (no glow visible on Nebulous Black Hole) checked on the game's tooltip and controller art: illithid
  powers are drawn without a glow (visible area 1.35× the lines; spells 3.5×, actions 4.3×); answered on the page.
  Commit: see `git log`.

- 2026-10-15: user "5A" → D24 (hotbar recipe v6 final, 2.2 closed). 2.4 glyph structure: `iconkit/glyph.py` (line mask
  from brightness over black, stroke widths and placement, a per-colour glow grown from the lines, small colours borrow
  the recipe that fits them best). Found: actions' "dark fills" are an opaque dark glow; line weight ~15 px at 512 on
  every colour; code glow rebuilds test spells to 1.2 L*, actions 3.0 (lines alone 9.3 / 11.1). Page `data/glyph.html`
  with decision 1 (who draws the glow). Commit: see `git log`.

- 2026-10-15: round 5 done. User notes on the six icons + "what is the time spent on". Measured per colour
  (`colour_residuals.py`), alignment (spells / actions exact; illithid cells lined up by zoom + shift), the optimizer
  (Nelder-Mead barely moves keys that start small → Powell). v6 recipe (glow colourfulness, hue, bloom, colour terms,
  per-colour lights, numbers for small colours), `fit presets`, parallel colour refits, master cache (a colours-only
  refit ~10 min). Test spells 11.89, actions 14.53 (round 4: 12.81 / 15.32). Page `data/hotbar.html` opens with decision
  5 (2.4 vs another hotbar round). Memory `perceptual-image-fits`, skill `icongen-review-round`, repo `CLAUDE.md`
  updated. Commit: see `git log`.

- 2026-10-15: round 4 done. v5 recipe fitted (stone light + glyph light, line colours with a line term, stone texture
  term, D22 per colour, illithid veins); test spells 12.81, actions 15.32; the user's six pairs all closer. Found: 16 of
  41 illithid PC cells enlarge the drawing ×1.1-1.2 (Levitate redrawn) → `same_size()` keeps such cells out of fitting.
  Review page `data/hotbar.html` (round 4) for the user. Commit: see `git log`.

- 2026-10-14: round 4 resumed. Step 1 done: dataset with illithid powers (train 991 / test 92, checks passed); colour
  refit kept the 31 presets (fit without illithid powers) + house preset Illithid red (see 2.1 "Round 4 refit"). v5 code in
  `hotbar.py` (frame light, `Ref` / `objective()` / `nm()`, stone texture term, D22 style pins, illithid frames); prototype
  of the v5 fit running. Commit: see `git log`.

- 2026-10-14: user "3A, but" (D22 settled) with notes on glow, flat colours, a missing bright spot, dull icons and the
  illithid vein background; chose to add illithid powers to v1 (D23). Measured (2.2 Round 4): a centred round light only
  the PC version has (checked on the controller art itself, the user's question), the game's glow shows about twice the
  stone texture ours does on actions, PC line colours brighter / whiter / steeper, illithid frames (red veins as is,
  silver ones on blue-grey veins). Code half done (see Round 4 "Code so far"); session paused before the dataset
  rebuild and the v5 fit. Commit: see `git log`.

- 2026-10-14: user answered 2A (D20 settled), noted frameless backgrounds mean passives/conditions (D21), Weapon red's
  "dark red glow" too big, line crispness, and Patch 8 icons. **Patch 8:** 111 GustavX hotbar icons; their tooltip and
  controller art found in `Gustav_Textures.pak` (census of every pak) and extracted; dataset 1,508 masters, train 951 /
  test 90 (old split kept), grammar refit 31 presets (no earlier icon moved). **Hotbar:** framed-only frames; measured
  per-colour dark edges, lit closed shapes, crispness and pixel classes (findings under 2.2 round 3); recipe v4 + per-colour
  refits. Final hue-kept fit: test MAE actions 16.31 (last page 15.51), spells 13.28 (13.01); edge contrast actions 1.00 /
  spells 0.99 (was 0.85 / 0.82); crisp closer per pixel for 24% of icons. D22 proposed (per colour crisp or soft),
  review page `data/hotbar.html` opens with it. If 3A: express the soft recipe in the new parameters (add a glyph-unsharp
  amount) and pick per colour by training MAE, then refit. Memory: `bg3-ui-reference`, `perceptual-image-fits`; skill
  `bg3-icons` (Patch 8 icon sources). Commit: see `git log`.

- 2026-10-14: user feedback on the page: violet is the Weapon red frame (by eye) and the halo is too wide ("the spells'
  glow, but dark"); chose 1A (D19 settled). Frames re-chosen by CIEDE2000; 9 colours get hue-shifted frames (D20
  proposed); halo = dark glow from the line cores, fitted on MAE + brightness profile next to the lines (hold-out actions
  15.51, spells 13.01). Page shows before/after strips and brightness-by-distance charts. Memory `perceptual-image-fits`
  added. Commit: see `git log`.

- 2026-10-14: user asked to see the halo, how "ours" is made and what D19 means: review page `data/hotbar.html`
  (`python -m iconkit.hotbar report`): D19 card (both frames, game examples, same glyph on both, app mock-ups A/B),
  halo strips (game | plain | ours | halo alone | zooms) + frame-visible charts, the 8 build steps for one action and
  one spell. `page.src` gained `lossless`. Commit: see `git log`.

- 2026-10-14: 2.2 done (`iconkit/hotbar.py`): spells on `spell_bg`; action frame = framed controller bg × gain picked by
  colour preset (hold-out 89% = vanilla's frame); dark halo + unsharp glyph recipe; hold-out 64 px MAE spells 12.98, actions
  15.71 (gate 18.1). D19 proposed. Next 2.4. Commit: see `git log`.

- 2026-10-14: D18 settled (user "2A", with glow caveats). Measured the glow: brightness structure survives de-tint;
  colour that depends on position (glow tint, radial hotspots) now in the tint table (lightness × opacity × centre
  distance); per-preset glow style (`core_gain`, `glow_px`) saved for captions; Metamagic flagged two-tone. Plan
  phases 3/4/5 updated. Commit: see `git log`.

- 2026-10-14: D17 settled (user "1A"). User spotted that the 13 hue colours merge distinct looks (Control ≠ Force):
  measured why: vanilla colour is a gradient map per preset; 2.1 rebuilt on **30 presets** with exact de-tint/re-tint
  (`grammar.py` rewritten; `page.py` embeds in-memory images). Mechanics/keyword hypotheses tested (results under
  2.1). D18 proposed (grey-glyph training), waiting on user. Commit: see `git log`.

- 2026-10-14: Phase 1 merged to `main` (31a9cf2, --no-ff); branch `phase-2-grammar`. 2.1 colour rules fitted
  (`iconkit/grammar.py`, results under Phase 2); review helpers shared in `iconkit/page.py` (`report.py` output
  unchanged). D17 proposed, waiting on user. Commit: see `git log`.

- 2026-10-14: User decided 1A 2A 3A → D14-D16. Badge variants out of `train.txt`/`holdout.txt`
  (890/84); report shows decisions as decided; `iconkit/sheet.py` added (user OK). Commit: see `git log`.

- 2026-10-14: Clean bottom fade (D13, `iconkit/fade.py`, commit 50fe92a). Anomaly report
  (`iconkit/report.py`); extraction label bugs fixed (main-entry ranking, intent-agreeing votes,
  GenericIcon labels, placeholders); user decisions A1-A3 pending. Commit: see `git log`.
- 2026-10-14: Phase 1 DONE: 1.3 SRD list downloaded (user OK) and matched (298 icons → 181 spells).
  Commit c739ad5.
- 2026-10-14: Phase 1.1/1.2/1.4/1.5 done on `phase-1-dataset` (`iconkit/extract.py`, `iconkit/paths.py`).
  User confirmed D2: master = controller-style art, tooltip used only for resolution, bottom-only fade.
  Commit d5a026c.

- 2026-10-14: user answers folded in: public release (D10, D11), in-app inference with separate
  model download (D5), v1 = spells + actions/skills (D12), continuity via this file (D9). Phases
  8-11 reshaped. Commit 2e146e0.
- 2026-10-14: Phase 0 done. Research of tiers, formats, backgrounds, colour grammar, pairs,
  transparency, prior art, hardware, training/transparency tooling; claude-mem diagnosed (Bun
  missing). Repo created, plan written. Commit 40fcb17.
