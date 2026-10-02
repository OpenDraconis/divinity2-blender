# Using the add-on

The add-on reads the game into Blender: one model by name, or a whole region. It does not export; see [Export to Unity](#export-to-unity).

## Install

Needs Blender 5.2 or newer (`blender_version_min` in [blender_manifest.toml](../blender_manifest.toml)) and a Developer's Cut install of the game. The wheels [nifgen](../wheels/nifgen-2026.9.15+dv2-py3-none-any.whl) and [divinity2-lib](../wheels/divinity2_lib-0.3.0-py3-none-any.whl) ship inside the add-on.

1. Blender: Edit > Preferences > Get Extensions > drop-down menu (top right) > Install from Disk, pick `divinity2-<version>.zip`.
2. Preferences > Add-ons > Divinity II: set the two folders below, then press Unpack the game.

| Preference | Property | Meaning |
|---|---|---|
| Divinity II install | `install` | The game's install folder, the one holding `Data` and `bin`. Empty: `DV2_GAME` if set, else every Steam library is searched |
| Game folder | `game_root` | An empty folder the game is unpacked into and read from (the extracted copy, `DV2_EXTRACT`) |

Unpack the game (`divinity2.unpack`) writes every file the engine loads, and its documents named, into the Game folder; it needs about 7 GB free (7,400,000,000 bytes checked) and refuses a non-empty folder that holds no `unpack.json`. Pressing it again stops it; unpack again to finish. The same unpack runs outside Blender with `python -m dv2lib unpack <folder>` (see the [divinity2-lib usage](https://github.com/OpenDraconis/divinity2-lib/blob/main/docs/usage.md)).

## Operators and panel

| Where | Label | `bl_idname` |
|---|---|---|
| File > Import | Divinity II asset | `divinity2.import_asset` |
| File > Import | Divinity II region | `divinity2.import_region` |
| 3D viewport sidebar (N), tab Divinity II, panel Divinity II | the same two buttons | |
| Preferences > Add-ons > Divinity II | Unpack the game | `divinity2.unpack` |

Every entry point asks for the Game folder first; with none set the operators report "Unpack the game in the add-on's Preferences".

### Divinity II asset

| Field | Meaning |
|---|---|
| Name | Case-insensitive substring filter over asset names: exact match first, then prefix, then the rest |
| Asset | The matches, each with its kind (character, scenery, item, effect, terrain, fortress) |

A script that passes only `search` gets the asset whose name is an exact match, or the only match; otherwise the operator reports the match count. Names follow the game's prefixes: `P_` scenery, `IT_` items, `EFF_` effects.

```python
bpy.ops.divinity2.import_asset(search="Black_Goblin")
```

A character arrives as one armature plus one object per mesh with every clip as an action (the first assigned); anything else arrives as one object per shape. Text keys of a clip become pose markers carrying name and frame.

### Divinity II region

| Field | Meaning |
|---|---|
| Region | The regions the game declares |
| Sub-region | One sub-region, or `All <n>`: each has its own origin, so all but the first arrive switched off |
| Time of day | As the game does (`<game>`), or a time setting the sub-region lists |
| Ground, Scenery, Items, Characters, Lights, Trees | On by default |
| Triggers, Grass | Off by default (Grass is thousands of objects) |

```python
bpy.ops.divinity2.import_region(region_name="Banditcamp", sub="Main", vegetation=True)
```

Each kind lands in its own collection (`Banditcamp Main scenery`, `... light`, ...); a hidden `... models` collection holds one copy of each model and every placement is a linked copy of it. Lights become Blender lights, trigger areas prisms, trees empties of the engine's size, particle systems empties carrying `dv2_particles`. Everything a file says is written to the object as `dv2_*` custom properties (`dv2_kind`, `dv2_uuid`, `dv2_fields` as JSON, `dv2_path`, `dv2_dimmer`, `dv2_radius`, `dv2_material`, `dv2_missing`, `dv2_drawn`); the scene carries `dv2_<global name>`.

## Textures

Converted textures live in the add-on's user folder, `bpy.utils.extension_path_user(<package>, path="texture-cache")`. Blender keeps it across upgrades and removes it with the add-on. Textures are NIFs read from the Game folder; nothing is written into the game. The format is in [textures](../engine/textures.md).

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `DV2_GAME` | game lookup in [divinity2-lib](https://github.com/OpenDraconis/divinity2-lib) | The game's Steam install folder; used when the Divinity II install preference is empty |
| `DV2_EXTRACT` | the environment self-check in [environment.py](../divinity2/environment.py) | The extracted copy, the same folder as the Game folder |
| `DV2_DOCS` | [docs.py](../divinity2/docs.py) | Extra document folders, separated by `os.pathsep`; each holds a `docs/` tree of `.json` documents |

## Export to Unity

The export to Unity is not done from the Blender GUI. `tools/export_game.py` in [divinity2-port](https://github.com/OpenDraconis/divinity2-port) runs Blender headless (`blender -b --factory-startup`, the binary from `BLENDER`) and loads this add-on from `../divinity2-blender` (or `DV2_ADDON`) as the package `dv2addon`. The GUI is for viewing and inspecting the game in Blender. This add-on does not write game files.

## What is in the files

[engine/](../engine/): what the engine does and where each rule is shown. See the [index](README.md).
