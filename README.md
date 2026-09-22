# Divinity II for Blender

A Blender add-on that imports the models and whole regions of
**Divinity II: Developer's Cut** (Larian Studios, 2009).

- **Every model the game ships**: 324 characters with their skeletons,
  textures and animations, 1,695 scenery pieces, 886 items, 378 effects,
  295 props and 21 flying fortresses.
- **Whole regions**: the ground, the scenery, items, characters, lights, trees,
  triggers, and the grass the game scatters at load time. The import menu
  lists all 21 regions the game declares, with 124 sub-regions.
- **In metres, textured**: diffuse and normal maps, transparency, vertex
  colours, and animation clips as actions with their events as markers.

## What you need

- Blender 5.2 or newer
- Your own copy of Divinity II: Developer's Cut. The original Ego Draconis
  release is not supported.
- About 7 GB of free disk space

## Install

1. Download `divinity2-<version>.zip` from
   [Releases](https://github.com/ygalsk/divinity2-blender/releases).
2. In Blender: *Edit > Preferences > Get Extensions*, open the drop-down menu
   in the top right, choose *Install from Disk…* and pick the zip.
3. Still in Preferences, expand the **Divinity II** add-on, set **Game folder**
   to an empty folder and press **Unpack the game**. This takes about a
   minute and happens once.

A Steam copy of the game is found automatically. For any other install, first
set **Divinity II install** to the folder that contains `Data` and `bin`.

## Use

**One model:** *File > Import > Divinity II asset*, or the **Divinity II** tab
in the 3D view's sidebar (press `N`). Type part of a name, such as `goblin`,
`damian`, `chest` or `P_Doors`, pick the model and press OK.

**A whole region:** *File > Import > Divinity II region*. Choose the region, the
sub-region and what to bring in. Grass is off by default because it adds
thousands of objects. Banditcamp with everything takes about 50 seconds.

To get a model out again, use Blender's own glTF or FBX export.

The full guide is [docs/using-it.md](docs/using-it.md).

## Known limitations

- Effects that are pure particle emitters import as nothing.
- Equipment changes that animations trigger are not simulated.
- Trees are placeholder markers of the right size: the game grows them from
  SpeedTree definitions, and no mesh for them exists on disk.
- Walk cycles tread in place. That is how the game stores them: the engine
  moves the character, not the clip.

## Credits and license

- The add-on is licensed under GPL-3.0-or-later, see [LICENSE](LICENSE).
- NIF files are read by `nifgen`, generated from the
  [NifTools](https://github.com/niftools/nifxml) format description
  (BSD-3-Clause), bundled as a wheel.
- Archives and the game's binary XML are read by
  [divinity2-lib](https://github.com/ygalsk/divinity2-lib) (MIT), bundled as a
  wheel; `python -m dv2lib unpack` unpacks the game from the command line.
- Details are in [NOTICE](NOTICE).

This project is not affiliated with or endorsed by Larian Studios. It contains
no game files. You need your own copy of the game.
