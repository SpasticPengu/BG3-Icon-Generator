# BG3 Icon Generator

A free, local app for making **Baldur's Gate 3 spell, action and illithid power icons** that look like the game's own,
and for turning them into everything a mod needs.

You draw with the game's real strokes and shapes, colour the icon with the game's own colour gradients and glow, and
export it once: the app builds the controller, tooltip and PC hotbar versions, the DDS textures and the mod files.

> Unofficial fan tool. Not made, approved or endorsed by Larian Studios or Wizards of the Coast. See [NOTICE.md](NOTICE.md).

## What it does

- **An editor built on the game's art.** Open any of the game's ~1,100 spell, action and illithid power icons, or add
  its parts (damage-type symbols, figures, frames, rays and more) from the Shapes library. Move, scale, rotate, flip,
  group, align and erase them, or draw your own strokes with a brush that matches the game's edge, taper and thorns.
- **The game's colours.** 31 colour gradients measured from the game's icons, picked automatically from the spell's kind,
  intent and damage type, plus your own colours or gradients.
- **Live previews** of the controller icon, the PC hotbar slot and the tooltip, on the backgrounds the game uses.
- **Export for your mod.** Hotbar atlas DDS, tooltip and controller textures, TextureBank and atlas metadata, ready to
  drop into a mod. Also PNG or WebP images up to 2048 px (sharp at large sizes) for mod pages.
- **Bring your own icons.** Import a mod's existing icons in bulk, including faded tooltip icons (the faded strokes are
  rebuilt), to edit and export them again under their original names.
- **Several icons at once** in tabs, exported together.
- **Updates itself** from this repository's releases (it asks first).
- **Other languages:** the app works with your browser's built-in page translation.

## Install

Windows 10 or 11. (macOS and Linux launchers are included but not tested yet.)

1. Download the latest app release (`bg3-icon-generator-<version>.zip`) from
   [Releases](https://github.com/SpasticPengu/BG3-Icon-Generator/releases) and unzip it anywhere.
2. Double-click **`Start.bat`** (macOS: `Start.command`, Linux: `./start.sh`).

The first start needs the internet once and takes a few minutes. It sets up the app's own Python and libraries in a
`.runtime` folder next to it (nothing is installed elsewhere and no admin rights are needed), then downloads the game's
icons (about 110 MB). In all, about 420 MB on disk. The editor then opens in your browser.

Each start checks the libraries, and the app offers updates when a new release is out. To remove it, delete the folder.

## Using exported icons in a mod

Exports go to `outputs/editor/<mod name>/`:

- `mod/` holds the game files (the hotbar atlas and its metadata, tooltip and controller textures, TextureBank). Copy
  them into your mod's folder.
- The icon's **Name in the game** (in the Spell panel) is the name your spells refer to in their `Icon` field.
- `png/` holds the same icon as images for your mod page.

## For developers

The app is plain Python (numpy, scipy, Pillow) serving a browser editor (`app/`, plain ES modules, no build step).
Building the game data from scratch needs an unpacked copy of the game (BG3 Modders Multitool) and the dataset
pipeline in `iconkit/`; `implementation-plan.md` records how every part was measured and decided, and `research/`
holds the probes behind it. Releases: a `v<version>` tag builds and publishes the app
(`.github/workflows/release.yml`); the game data is a separate `data-v<N>` release.

## Credits and notice

Baldur's Gate 3 art belongs to Larian Studios; Dungeons & Dragons material belongs to Wizards of the Coast; spell data
from the SRD 5.1 (CC BY 4.0). Full text in [NOTICE.md](NOTICE.md). Free, and it will stay free.
