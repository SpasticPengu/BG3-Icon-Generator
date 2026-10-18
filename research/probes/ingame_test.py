"""Phase 3 in-game test mod: three vanilla drawings rebuilt from their lines only (variants.build), exported under new
names (variants.export) and set as the icons of spells every character has, so a change shows on every surface:
    Fire Bolt  (Projectile_FireBolt) <- Fireball            IGT_Spell_FireBoltTest     spell on spell_bg
    Dash       (Shout_Dash)          <- Rush                IGT_Action_DashTest        action, Weapon red frame
    Hide       (Shout_Hide)          <- Quickened Spell     IGT_Action_HideTest        two colours, metamagic frame
Writes outputs/IconGenTest/{Mods,Public}/IconGenTest (gitignored: Larian art). Build it with the user's toolchain:
    Build-Mod.ps1 -Mod "<repo>\\outputs\\IconGenTest" -Convert      (validates the .lsf.lsx; touches no game files)
    Build-Mod.ps1 -Mod "<repo>\\outputs\\IconGenTest" -All          (loose: junctions + convert + register; no pak needed,
                                                                     every file is under Mods/ or Public/<Folder>, D37)
Deactivate it after the look: it changes Fire Bolt, Dash and Hide in every save while active.
    python research/probes/ingame_test.py   (anaconda python, from the repo root)"""
import json, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from iconkit.extract import D, log
from iconkit.variants import build, variants, export
from iconkit import hotbar

MOD = "IconGenTest"
TESTS = [("Projectile_FireBolt", "Projectile", "Spell_Evocation_Fireball", "IGT_Spell_FireBoltTest"),
         ("Shout_Dash", "Shout", "Action_Rush", "IGT_Action_DashTest"),
         ("Shout_Hide", "Shout", "Skill_Sorcerer_Passive_Metamagic_QuickenedSpell", "IGT_Action_HideTest")]
META = """<?xml version="1.0" encoding="utf-8"?>
<save>
  <version major="4" minor="0" revision="9" build="328" />
  <region id="Config">
    <node id="root">
      <children>
        <node id="Dependencies" />
        <node id="ModuleInfo">
          <attribute id="Author" type="LSString" value="BG3 Icon Generator" />
          <attribute id="CharacterCreationLevelName" type="FixedString" value="" />
          <attribute id="Description" type="LSString" value="Phase 3 exporter test: Fire Bolt, Dash and Hide get icons rebuilt from vanilla line art." />
          <attribute id="Folder" type="LSString" value="{mod}" />
          <attribute id="GMTemplate" type="FixedString" value="" />
          <attribute id="LobbyLevelName" type="FixedString" value="" />
          <attribute id="MD5" type="LSString" value="" />
          <attribute id="MainMenuBackgroundVideo" type="FixedString" value="" />
          <attribute id="MenuLevelName" type="FixedString" value="" />
          <attribute id="Name" type="FixedString" value="{mod}" />
          <attribute id="NumPlayers" type="uint8" value="4" />
          <attribute id="PhotoBooth" type="FixedString" value="" />
          <attribute id="StartupLevelName" type="FixedString" value="" />
          <attribute id="Tags" type="LSString" value="" />
          <attribute id="Type" type="FixedString" value="Add-on" />
          <attribute id="UUID" type="FixedString" value="{uid}" />
          <attribute id="Version64" type="int64" value="36028797018963968" />
          <children>
            <node id="PublishVersion">
              <attribute id="Version64" type="int64" value="36028797018963968" />
            </node>
            <node id="Scripts" />
            <node id="TargetModes">
              <children>
                <node id="Target">
                  <attribute id="Object" type="FixedString" value="Story" />
                </node>
              </children>
            </node>
          </children>
        </node>
      </children>
    </node>
  </region>
</save>
"""

J, G = (json.loads((D / f).read_text(encoding="utf-8")) for f in ("glyph.json", "grammar.json"))
H = json.loads((D / "hotbar.json").read_text(encoding="utf-8"))
B = hotbar.backgrounds()
out = Path(__file__).resolve().parents[2] / "outputs" / MOD
icons = {}
for _, _, src, name in TESTS:
    _, _, m, p, p2 = build(src, J, G)
    icons[name] = variants(m, src, p, H, B, p2)
    log(f"    {src} -> {name} ({p}{' + ' + p2 if p2 else ''})")
files = export(icons, MOD, out)
(out / "Mods" / MOD / "meta.lsx").write_text(META.format(mod=MOD, uid=uuid.uuid5(uuid.NAMESPACE_URL, f"bg3-icon-generator/{MOD}")),
                                             encoding="utf-8")
stats = "".join(f'new entry "{e}"\ntype "SpellData"\ndata "SpellType" "{t}"\nusing "{e}"\ndata "Icon" "{n}"\n\n' for e, t, _, n in TESTS)
st = out / "Public" / MOD / "Stats/Generated/Data/Spell_IconGenTest.txt"
st.parent.mkdir(parents=True, exist_ok=True)
st.write_text(stats, encoding="utf-8")
for name, v in icons.items():                                       # PNG previews next to the mod, for a look before the game
    for tier, im in v.items():
        im.save(out / f"preview_{name}_{tier}.png")
log(f"[3 in-game] wrote {len(files) + 2} mod files + previews under {out}")
