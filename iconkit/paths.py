"""Where the unpacked game data lives and where extracted data goes. Edit for another machine."""
import os
from pathlib import Path

# the BG3 Modders Multitool folder with the game unpack (development only; an installed copy downloads its data)
MT = Path(os.environ.get("BG3_MULTITOOL") or Path.home() / "Documents/BG3 Modding/BG3 Modders Multitool")
UNPACKED = MT / "UnpackedData"
GUI = UNPACKED / "GUI/Public/Game/GUI/Assets"
# Patch 8 (GustavX) tooltip + controller icons ship in Gustav_Textures.pak under Mods/GustavX/GUI/Assets, which the
# Multitool unpack lacks. Extract (2026-10-14): Divine.exe -g bg3 -a extract-package -s <Data>\Gustav_Textures.pak
#   -d UnpackedData\Gustav_Textures -x "^Mods/GustavX/GUI/Assets/(Tooltips/(Icons|ItemIcons)|ControllerUIIcons/(skills_png|items_png))/" --use-regex
GUI_X = UNPACKED / "Gustav_Textures/Mods/GustavX/GUI/Assets"
TOOLTIP_DIRS = [GUI / "Tooltips/Icons", GUI_X / "Tooltips/Icons"]                          # load order: later wins
CONTROLLER_DIRS = [GUI / "ControllerUIIcons/skills_png", GUI_X / "ControllerUIIcons/skills_png"]
BACKGROUNDS = GUI / "ControllerUIIcons/icon_bg_png"
if not BACKGROUNDS.exists():                     # an installed copy: the 28 hotbar backgrounds come with the icons download
    BACKGROUNDS = Path(__file__).resolve().parent.parent / "data" / "backgrounds"
BASEREF = MT / "UnpackedMods/BaseGameReference"
# load order: later dirs override earlier ones
STAT_DIRS = [BASEREF / "Shared_BaseGameReference/Public/Shared/Stats/Generated/Data",
             BASEREF / "Shared_BaseGameReference/Public/SharedDev/Stats/Generated/Data",
             BASEREF / "GustavX_BaseGameReference/Public/GustavX/Stats/Generated/Data"]
LOCA = BASEREF / "English/Localization/English/english.loca.xml"
ATLAS_MAPS = [UNPACKED / "GUI/Public/Shared/GUI/Icons_Skills.lsx",
              UNPACKED / "GUI/Public/SharedDev/GUI/Icons_Skills.lsx",
              UNPACKED / "GUI/Public/GustavX/GUI/Icons.lsx"]                            # Patch 8: 111 icons, 1024x512

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _find(dirs, n):
    """icon file in the last dir holding it (load order); a path that does not exist if none does"""
    return next((p for d in reversed(dirs) if (p := d / f"{n}.DDS").exists()), dirs[0] / f"{n}.DDS")


def tooltip(n):
    return _find(TOOLTIP_DIRS, n)


def controller(n):
    return _find(CONTROLLER_DIRS, n)
