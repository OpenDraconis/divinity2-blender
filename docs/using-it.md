# Using it

Everything this add-on does is reachable from two places: the **Divinity II**
tab in the 3D sidebar, and **File > Import**. Two buttons: one model, or one
whole region.

## Install it once

The game keeps its files in archives, and names inside its XML are hashes. The
add-on unpacks the one and names the other, once, with
[divinity2-lib](https://github.com/ygalsk/divinity2-lib), which it carries.

1. **Install the add-on.** In Blender, *Edit > Preferences > Get Extensions*,
   the drop-down menu in the top right, *Install from Disk*, and pick
   `divinity2-<version>.zip`. Blender enables it straight away.
2. **Unpack the game.** Still in Preferences, open the add-on, set **Game
   folder** to an empty folder, and press **Unpack the game**. A Steam copy of
   the Developer's Cut is found by itself; any other install, set **Divinity II
   install** to the folder holding `Data` and `bin` first. The button shows how
   far it is, and pressing it again stops. The folder then holds the game's
   files as the engine loads them -- 34,857 files, 6.9 GB -- and the 3,972
   documents, named, under `docs/`. Measured on the Steam Developer's Cut: 48 s
   inside Blender, 37 s as `python -m dv2lib unpack <folder>`.

   The original Ego Draconis stores its archives in an older version the
   unpacker does not read.

Nothing is written into the game, and after unpacking nothing into the game folder. Converted textures go to
the add-on's own user folder, which Blender keeps across upgrades and removes
with the add-on.

## Import something

Press **N** in the 3D viewport, open the **Divinity II** tab, click the
button. Type a name and press OK.

- The **Name** field filters as you type. It matches any part of the name, so
  `goblin` finds `Goblin`, `Black_Goblin` and `Goblin_Shaman`.
- The **Asset** dropdown lists what matched, each with its kind. Pick one.
- A name that matches exactly, or matches only one asset, needs no pick: a
  script can call the operator with the name alone.

There are 3,599 models in the install, of six kinds:

| kind | how many | what it is |
|---|---|---|
| character | 324 | a creature or person: armature, meshes, clips |
| scenery | 1,695 | walls, doors, trees, furniture, ruins |
| item | 886 | weapons, armour, containers, loot |
| effect | 378 | spell and particle effects |
| terrain | 295 | compiled props, one folder of pieces each |
| fortress | 21 | the flying fortresses, skinned |

Names follow the game's own prefixes, which is the fastest way to browse:
`P_` scenery props, `IT_` items, `EFF_` effects. Type just `P_Doors` or
`IT_Containers` to see a whole set.

## Import a whole region

The second button builds a level: the ground, every prop, every person, the
lights and the triggers, in one go.

- **Region** lists the 21 the game declares; **Sub-region** its interiors.
- **Time of day** picks which `Lights` folder to read — the sun and the lamps
  are authored three times.
- The tick boxes choose what to build. Triggers and grass are off by default:
  triggers are wireframe volumes that get in the way, and the grass is
  thousands of objects, grown the way the engine grows it
  (`docs/vegetation.md`).

Each kind lands in its own collection — `Banditcamp Main scenery`,
`Banditcamp Main light`, and so on — so you can switch off what you are not
working on. A hidden `Banditcamp Main models` collection holds one copy of each
model; every placement in the scene is a linked copy of it, so Banditcamp/Main's
732 scenery placements share 194 meshes.

Everything the game's files said is kept on the object as custom properties:
`dv2_kind`, `dv2_uuid`, and the whole record as JSON in `dv2_fields` (a tree's
model and SpeedTree file among it); a built mesh carries its `dv2_path`.
Nothing is dropped on the way in.

Banditcamp/Main with grass, measured with the add-on installed from its zip
into an empty Blender 5.2 profile: 190 models, 75 pieces of ground and built
geometry, 732 scenery, 199 items, 99 characters, 96 lights, 59 trees and 4,737
plants, nothing unresolved, in 50 seconds.

## What arrives

**A character** is one armature and one object per mesh in the file. The
meshes are skinned to the armature, every clip in the character's set is an
action, and the first one is assigned so you can press space and watch it.
Text keys in a clip — footsteps, sound cues, equip events — arrive as pose
markers on the action, so nothing about a clip's timing is lost.

**Anything else** is one object per shape, placed by its own transform, with
no armature. A flying fortress is the exception: it is skinned and carries its
own bones, so it gets an armature like a character does.

Everything arrives in metres, and everything is in the same world: a goblin is
1.84 m, a Maxos gate 5.9 m wide, the Damian fountain 4.1 m across, a ruined
wall 15.7 m long. Import a character and a door together and the character
fits through the door.

Materials are a Diffuse BSDF with the game's diffuse and normal map wired in,
plus an emission term for what the engine lights by itself (water gets a
Principled BSDF), and transparency honoured: a cut-out surface like hair or a leaf uses alpha
clipping, a blended one blends, an additive one casts no shadow.

Two more things the file says about a surface are honoured, and both are
mostly decided by what the file *does not* say:

- **Vertex colours.** A shape's colours are always written onto the mesh as a
  `RGBA` colour attribute, so nothing is lost. Whether they are drawn is the
  shape's own `NiVertexColorProperty`: most scenery says to ignore them, and a
  shape with no such property anywhere above it ignores them too -- the
  engine's default (`NiPropertyState`), not `nif.xml`'s "if not present"
  default, which is the exporter's convention.
- **Two-sidedness.** Back faces are culled unless the shape carries a
  `NiStencilProperty`, which in this game only ever says `DRAW_BOTH`. Banners,
  flags, bushes and water plants have it; walls do not.

## Levels of detail

A Divinity II file holds every level of detail at once. The add-on imports
them all and hides everything but the nearest, so the viewport shows one
model. The rest are in the outliner, hidden — **Alt+H** brings them back if
you want them; otherwise ignore them.

A compiled prop is the exception: its levels are separate files, one folder
per model, and the add-on takes the finest of each piece. There is nothing
hidden to reveal.

A region's ground is the other exception, and it works the other way round:
the level the region ships inline is the *coarse* one, and the fine levels are
streamed from `Meshes/Terrain/Terrain_Patch_<i>/`. The add-on attaches them,
so the ground you get is the ground the game draws — for Banditcamp that is
36,883 vertices rather than 9,992. The coarse levels are still there, hidden.

## Getting it out again

Use Blender's own exporters. **File > Export > glTF 2.0** carries the mesh,
the armature, the skin weights, the actions and the materials, and is what
Unity, Godot and Unreal all read. FBX works too.

This add-on does not write game files. It reads.

## When something looks wrong

- **A walk cycle treads in place.** That is the data. Divinity II clips carry
  no root motion — the engine moves the character, the clip only cycles the
  legs. Measured over all 729 clips of the human families: not one animates
  `Reference`.
- **A character stands below the floor.** Flying creatures and dragons are
  authored around their body, not their feet. 40 of 324 do this, and they are
  all flyers.
- **A weapon is held loosely.** The socket is right — `Bone_Weapon_01` on the
  right hand, which is what the engine's own slot table says — but a clip that
  was never meant to hold anything does not close the fingers.
- **An effect imports as nothing.** Many effects are emitters: nodes and
  timing with no geometry at all. There is nothing to show.
