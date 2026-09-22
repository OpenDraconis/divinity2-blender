# A region, whole

A Divinity II level is not a file. It is a list of placements in one file, a
prototype table in another, the meshes in a third, the built geometry in a
fourth and the terrain in a fifth — and the people, the loot and the triggers
are not with the region at all, they are with the episode. This page is the
chain, and every step carries the measurement that settled it.

Measured on `Banditcamp` and swept over the whole install: **19 regions, 122
sub-regions, 43,795 scenery placements, 10,311 items, 5,991 triggers, 3,685
lights, 3,323 trees and 1,011 characters.** Of those, nine scenery prototypes
find no file; every character and every item resolves.

## The chain

```
World/<region>/<sub>/scenery.xml      prototype, scale, a basis, a position
       -> rpgstats_sceneryprototypes.xml   sceneryitem: UUID -> NIFFile
       -> Win32/Scenery/<path>.item

Episodes/<e>/Regions/<r>/Characters/*.xml
       -> rpgstats_characterprototypes_visual.xml   Visual: TemplateName
       -> Win32/Characters/Templates/<name>.cat

Episodes/<e>/Regions/<r>/Items/*.xml
       -> rpgstats_itemprototypes.xml        item: VisualUUID
       -> rpgstats_itemvisualprototypes.xml  itemvisual: Folder, NifFileName
       -> Win32/Items/<folder>/<name>.item

Episodes/<e>/Triggers/*.xml           volumes and points, by Region/SubRegion
World/<region>/<sub>/Lights/<time>/lights.xml    point lights and one sun
World/<region>/<sub>/trees.xml        SpeedTree placements
World/<region>/<sub>/StaticMeshes.nif the region's own built geometry
World/<region>/<sub>/Vegetation.nif   the grass library; the engine places it (section 11)
```

None of the `.xml` files is text. Each is Larian's binary XML inside an
`xml::dom::CStreamableNode` block in a NIF container — the file carries a
`.xml` extension and holds neither. The shared reader handles it; see
`divinity2/docs.py`.

## 1. The stream stores a node's children in reverse

This is one fact with two faces, and taking it for two separate quirks is how
it stayed hidden.

The engine's own readers say what the order must be:

| function | `children[0]` | `children[1]` |
|---|---|---|
| `CRpgStats_V2_Scenery::LoadXML` | `NiPoint3`, position | `NiMatrix3`, basis |
| `CRpgStats_V2_Character::LoadXML` | `NiPoint3` | `NiMatrix3` |
| `CRpgStats_V2_Item::LoadXML` | `NiPoint3` | `NiMatrix3` |
| `CGameLogic_Tree::LoadXML` | `m_kPosition` | `m_kInstanceData` |

Every file on disk has them the other way round. And `LoadXML(NiMatrix3*)`
fills rows 0, 1, 2 from `children[0..2]` in order — so the same reversal is
why a matrix read straight out of the file has determinant −1.

Reversing each node's children once, in the reader, settles both:

| | det < 0 | det > 0 |
|---|---:|---:|
| as the stream has it | 775 | 0 |
| **children reversed** | **0** | **775** |
| transposed | 775 | 0 |

Transposing cannot help, whatever else is true: `det(Mᵀ) = det(M)`, so it
leaves every reflection a reflection. And a tree's instance data is the
independent check — `CGameLogic_Tree::UpdateInstanceData` fills it from
`rand()/2³¹`, so all three components are in [0, 1]. After the reversal,
59 of 59 are.

## 2. `Assets` replaces, and the case does not match

A prototype names `Assets\Scenery\P_Junk\X`. The engine's `Assets` root
**replaces** onto `Win32/Scenery`, it does not nest under it, so that resolves
to `Win32/Scenery/Scenery/P_Junk/X.item`.

Larian's own paths disagree with their own filenames on case. Matching
literally loses **10 of Banditcamp's 775**; folding case resolves
**775 of 775**. The same fold is what gets items and characters to 100%.

## 3. A placement is already in metres

The mesh is not. A scenery `.item` carries the conversion on its own root node
as a scale of `0.01` (see `docs/assets.md`), so once the add-on has imported
it the placement's position applies unchanged.

## 4. The engine's own table for a region node

`CRegionVisual::ParseRegionNode` is the function that walks a region's
`StaticMeshes.nif` and decides what each node becomes. It is the answer to
"what is in here that is not geometry", and it is a table, not a guess:

| what it reads | what the node becomes |
|---|---|
| `CDummyGeometry` (RTTI) | nothing; the function returns at once |
| `effectproxy = yes` | a particle system from `Win32\Effects\<EffectFile>`, at the node's world transform, with `CullingDistance`. **The box is not drawn.** |
| `glowproxy` | a `CGlowEffect` |
| a name containing `PhysicsPROXY_` | a collision hull |
| `IsCubeMapPosition`, `CubemapPosition` | a cubemap probe |
| `IsItemPosition`, `ItemPosition`, `ItemPrototypeName`, `ItemCollectionName` | an item spawn |
| `IsStatic`, `ExternalAssetPath`, `ASSET` | a streamed asset reference |
| `TERRAIN_PATCH` | a terrain patch |
| `Imposter` | a billboard imposter |
| `River`, `WaterPlane` | a `CWaterPlane` |
| `decal` | a `CDecalNode` |
| `ANTIPORTAL_`, `antiportal` | a `CAntiPortal` |
| `DungeonPR`, `ENTRY-BOX` | an `NiRoom` / `NiShell` — the portal system |
| `ActiveDistance` | a distance |

`EffectFile` and `CullingDistance` are not attributes: they are `key = value`
lines inside the node's `UserPropBuffer`, pulled out by
`DivTools::CGBTools::GetExtraDataValue`. Positions in this function are
multiplied by `CNifManager::ms_fRescaleSize`.

The add-on reads the three that replace the geometry outright — `effectproxy`,
`glowproxy` and `PhysicsPROXY_` — and marks those shapes hidden with the
reason. Across all 19 regions that is 18 shapes of 2,273. The rest of the
table is read but not acted on yet; the markers are on every object as
`dv2_*` so nothing is lost.

## 5. The built geometry hides one thing and names another

`StaticMeshes.nif` is the region's own geometry: 14.4 MB and 69 drawn shapes
in Banditcamp, placed at the origin because its nodes carry full world
positions. Two kinds of thing in it are not world geometry:

| what | shapes | what marks it |
|---|---:|---|
| `BC_Compartment_*_NDLWL` volume markers | 10 | **`APP_CULLED`** |
| `BC_ShadowHide_01`, an author-side helper | 4 | **nothing** |

`APP_CULLED` is bit 0 of any `NiAVObject`'s flags, and the engine says so
outright — `NiAVObject::GetAppCulled` is `return this->m_uFlags & 1;`. The
add-on drops those 10, and a culled node takes its subtree with it.

`BC_ShadowHide_01` is the honest gap. Its flags are `0x210`, the same as the
58 shapes that are drawn; its node flags are `0x310`, the same as the other
52 nodes; it carries no `UserPropBuffer` and none of section 4's markers; and
`shadowHideObject` in the exe is a Scaleform text-field property, nothing to
do with it. **Only the name says what it is, and the add-on does not invent a
name test the engine does not have.** It comes in visible.

A third thing was on this list and should not have been. `BC_terrain_*_low`
is the region's ground, not junk: those patches are the coarse child of an
`NiLODNode` whose finer children are empty stubs for files this region does
not ship. Hiding them by name threw the floor away — see `divinity2/lod.py`.

Every object keeps its whole node path as `dv2_path`, because the shapes
themselves are nearly all called `Editable Poly` and the name that means
something is on a node above.

## 6. The terrain needs both halves of its placement

`StaticMeshes.nif` holds one `NiLODNode` per patch under
`[--WorldProcessedTerrain--]`, and each holds **one level inline plus one
empty stub node per streamed level**. A patch ships those streamed levels as
`Meshes/Terrain/Terrain_Patch_<i>/0.nif`, `1.nif` and sometimes `2.nif`, each
holding its geometry under a node named exactly as its stub.

`Meshes/Terrain/AssetDataDescriptors.xml` is the manifest that pairs the two,
and it is Larian binary XML like everything else here:

```
<AssetDataDescriptor base="Terrain_Patch_6">
  <LODDistances>
    <LODDistance name="RT_patch_A_LOW" distance="700000" index="0"/>
    <LODDistance name="RT_patch_A_MAX" distance="0"      index="1"/>
```

`index` is the numbered file, `name` is the stub it fills, and `distance`
orders the levels with 0 nearest. **The level shipped inline is not the one
the game draws.** Eighteen sub-regions ship a manifest, and in every one of
them the inline level is a coarse one:

| region | inline | streamed, drawn |
|---|---:|---:|
| Banditcamp, all 7 patches | 9,992 | **36,883** |
| RiverTown_FF, 7 of 13 patches | 24 each | **3,756 – 12,215** |

Without the manifest, Banditcamp's ground is a quarter of the game's and
RiverTown_FF's flying islands are faceted plates. `divinity2/terrain.py` reads
it; `divinity2/lod.py` needs no part in it, because once a stub holds geometry
`lod_children` already prefers it and hides the coarse level.

**Neither file places the patch on its own.** The stub carries half the
placement and the streamed node the other half, and the engine attaches one to
the other. On `Terrain_Patch_0`, stub + node is
`(11390.9, 62440.5, 11651.4)`, which is to within `0.000` exactly where
`0.nif` already puts its own inline level.

The two **compose** — the streamed node hangs under the stub keeping its own
transform. Splicing the streamed node's children under the stub instead, and
so dropping that transform, puts Banditcamp's `Terrain_Patch_0` 4,203 units
east of where its own coarse level sits.

The stub is matched to the streamed node **by name, not by position**: a patch
carries one stub per level and their order is not fixed. Taking the first stub
misses `Terrain_Patch_1` by 184 units.

`Terrain.xml` names the ground's textures, because a terrain mesh carries no
`NiTexturingProperty` at all — see `divinity2/terrain.py` for the splat
recipe.

## 7. Lights

`Lights/<time of day>/lights.xml` holds a `point_light` per lamp and one
`dir_light` for the sun. A point light gives its position under `GBLight` as
`translate`, its colour as `diffuse_color`, its brightness as `dimmer` and its
reach as `m_fMaxAttenuationRadius`.

The sun has no position, only two angles. `CDirLight::UpdateVisual` copies
`MakeZRotation(angle_z) * MakeYRotation(angle_y)` into the light, and
`NiDirectionalLight::UpdateWorldData` takes the world rotation's column 0 as
the direction the light travels. Gamebryo's `NiMatrix3::MakeZRotation` writes
`[[c, s, 0], [-s, c, 0], [0, 0, 1]]` and `MakeYRotation`
`[[c, 0, -s], [0, 1, 0], [s, 0, c]]` -- the transposes of the textbook
matrices -- so the sun travels along

    (cos y · cos z,  −cos y · sin z,  sin y)

This used to be measured instead: the textbook product's −X was below the
horizon in nine regions of nine. That vector has the right height and a
mirrored x, and a check that asks only for the height cannot tell them apart.

A spot light is a point light with an `NiTransform` (`CSpotLight::LoadXML`
takes exactly those two children); it shines along column 0 of that transform
(`NiSpotLight::UpdateWorldData`), with `fov` its cone.

## 8. Triggers

`Episodes/<e>/Triggers/*.xml` holds all 5,991 of them, and a file is not one
region's: each trigger names its own `Region` and `SubRegion` in
`Trigger_base`. There are 17 `Type` numbers, but the number needs no table —
the trigger's one child element is its own label:

| element | what it carries |
|---|---|
| `Trigger_area` | a `PolyArea`: `Bottom`, `Top`, and a ring of `AreaPoint`s |
| `Trigger_Point` | one position |
| `Trigger_Orientation` | a position and a basis |
| `Trigger_PointSound`, `Trigger_PointEncounter`, `Trigger_PlayerSpawnPoint` | the same, with their own attributes |

Every corner of a `PolyArea` sits at `Bottom`, so the volume is that polygon
extruded up to `Top`. The add-on builds exactly that prism, as a wireframe.

## 9. Trees have no mesh, and that is not the reader's fault

`trees.xml` gives a tree a `uuid`, a `model`, a `variation`, a position and
three instance floats. `model` names a `CTreeModel` in `forest-settings.xml`,
whose own `model` is a SpeedTree `.spt`:

```
<CTreeModel name="BoxWood" model="ENV_TR_Boxwood_01.spt" size="15"
            treesizevariation="0.8" billboardDistance="100" .../>
```

`.spt` version `__IdvSpt_02_` is a **procedural definition, not geometry**.
The whole SpeedTree runtime is linked into the game — `CSpeedTreeRT::LoadTree`,
`CTreeModel::LoadSptFile`, `CTreeModel::SetupBranchGeometry`,
`SetupLeafMeshGeometry`, `SetupFrondGeometry` — and grows the tree at load.
No mesh for it exists on disk, in any file, ever. Nor does a reader exist to
borrow: the one free Blender add-on for SpeedTree, `ArdCarraigh/Blender_SRT_Addon`,
reads `.srt` from SpeedTree 7, four major versions later.

What *is* exact is where it stands and how big it is.
`CGameLogic_Tree::PreparePhysicsData` computes the scale as
`rescaled.y * CTreeModel.size`, and `CGameLogic_Tree::UpdateInstanceData`
computes `rescaled.y = (1 - v) + instance.y * v * 2` for
`v = treesizevariation`. So a tree arrives as a cone empty at the right place
and the right size, carrying its model name and its `.spt`.

`instance.x` is the tree's rotation and `instance.z` its colour variation.
Both go to the SpeedTree shader as a trig pair (`g_vTreeRotationTrig`); what
angle `instance.x` stands for is not resolved, so it is kept as a raw
`dv2_rotation` and not applied.

## 10. A water plane is geometry, and the XML beside it is only its style

`CRegionVisual::ParseRegionNode` turns a node marked `UserPropBuffer=WaterPlane`
into a `CWaterPlane`. The node is an ordinary shape in `StaticMeshes.nif` and
was always being imported — as an opaque grey card, because the only texture
it names is `_Gray.tga`. There are **26 of them across 10 sub-regions**, and
`River` never appears as a marker anywhere.

`Lights/<time>/waterplanedata_v2.xml` says what to draw them as, and it holds
no positions at all. Its `WaterPlaneData name` is the node's own name:

| sub-region | node | entry |
|---|---|---|
| `DZ1/Main` | `DZ_water_ocean` | `DZ_water_ocean` |
| `DZ1/DZ_Harbour` | `Water` | `Water` |
| `Banditcamp/Main` | `Pond_BC_01_A` | — |

Banditcamp is the exception: its planes are named for ponds while its file
holds only the three stock entries (`Waterplane_River`, `_Fall`, `_Ocean`). A
plane with no entry of its own is drawn with the constructor's defaults, as the
engine draws it: `CWaterPlaneDataMan::AddWaterPlane` matches by exact name and
nothing else (`region.water_style`, `WATER_DEFAULTS`).

## 11. Vegetation is generated, and the generator is in the binary

`Vegetation.nif` is the region's **library** of grass and undergrowth: one
`NiNode` per source file, named exactly as `vegetationtemplatedata.xml` names
it (`GRS_BV_GrassSmall_D.nif`). Where each blade stands is *not* in any file.
The engine generates it at load, and `divinity2.vegetation` now generates the
same field, out of `Divinity2GUP.pdb`'s own symbols rather than out of a
guess. The whole derivation is in `docs/vegetation.md`; the short of it:

| piece | where it comes from |
|---|---|
| the walk | `CVegetationPatch::ProcessVegetationMap`: 32x32 samples per cell, `u, v = 0 .. 31/32` |
| the cell | 32 m -- `CVegetationGridManager` sets `m_usGridEntrySize = 0x20` |
| the mask | `VM_<x>_<y>.tga`, read RGBA: **R** picks the template, **G** the size, **B** and **A** are the ground height the engine cached there |
| the plant | `CTemplate::SelectData` draws one card from a deck of 1024, and each template's instance counts sum to exactly 1024 |
| the deck | `CRandomNoise::UpdateValues`: `srand(PosSeed)`, then `2 ** PosNumOfSwizzles` swaps with the last card |
| the size | `CPerlinNoise` on `SizeSeed`, `SizeGranularity` octaves, `SizePersistence`, clamped to `MinSize .. MaxSize`, times the mask's `G / 127.5` |
| the turn, the tint, the jitter | `CPerlinNoise::IntNoise` -- the Hugo Elias hash, constants 15731 and 789221, and `0xd208dd0d` where the tutorial has 1376312589 |

Two things had to be measured rather than read, and both are written down
where they are used:

* **A cell is centred on its index.** The engine's own patch node sits at
  `index * width`, but the origin `ProcessVegetationMap` walks from comes
  through the streaming letter, and following it there was not worth the
  hour. Measured instead, against the ground of the built scene over every
  offset from -32 to +32 m in both axes: `index * 32` is out by 11.68 m on
  average and `index * 32 - 16` by 0.37 m. Half a cell, in both axes.
* **`m_fRotation` is a turn, not an angle.** `CreateInstance` writes
  `0.5 + 0.5 * IntNoise(...)`, which is 0..1, and the vertex shader that
  reads it is compiled HLSL. Taking it as a full turn is ours, not the
  game's, and it is the one step in the chain that is not proven.

**Checked, 5,224 samples.** Every painted pixel whose cached height the game
had already written, against the ground the add-on builds: **98.0% within
10 cm**, median 8 mm. That number is what says the mask is read right, the
cell is the right size, the origin is right and the axes are right -- four
things at once, because getting any one of them wrong moves the answer.

Banditcamp comes out at **4,737 plants** from 5,265 painted samples; the
difference is the samples whose card fell on a template entry with no mesh.

## 12. Checked on screen

The first comparison against the running game, and the only check here that
can fail for a reason no file can show. Source: a 100-second Banditcamp
runthrough recorded with the coordinate overlay on, so every frame states
`(x, y, z) in Banditcamp:Main`.

**Where the player stood.** Twelve frames spread over the run, each giving a
position the player actually occupied. For each, the nearest surface under
his feet in the imported region:

| | |
|---|---:|
| points sampled | 12 |
| within 10 cm | **11** |
| mean absolute error | **0.053 m** |
| worst | 0.56 m |

Eight land on `BC_terrain_*`, one on a `P_Terrain_SmallRock` the player was
standing on, three on `BC_Room_A_bars` inside the cave. So the placement
chain, the metre scale and the coordinate convention are right, not just
self-consistent.

**The streamed levels are not what fixes the floor.** Measured at the nine
open-air points, the coarse level the region ships inline is already within
0.21 m mean of the surface the player walked, against 0.19 m for the streamed
level. The graft buys resolution and silhouette — and it is decisive for
`RiverTown_FF`, whose inline level is a 24-vertex plate — but on Banditcamp's
walkable ground the coarse level was never far wrong. Claiming otherwise
would have been easy and false.

**What the picture still lacks.** At `(122.20, 52.04, 1.34)`, facing −X (the
heading the run itself gives: `t18 → t20` is `(−11.06, +0.05)`), the rock
layout matches — dark wall close on the left, open floor to the left of
centre, a bright face above it, rock masses right. A counter-render facing
`+X` shows a different place entirely, which is what makes the match mean
something. What differs is ground cover: the render had no grass, which the
add-on has generated since (section 11), and trees are markers (section 9). Nothing in the comparison is
explained by geometry being wrong.

## What is still open

- **Three of the ten numbers on a water plane.** `waterplanedata_v2.xml`
  stores attribute names as hashes, and all ten are recovered now:
  `wavestrength`, `wavesize`, `wavespeed`, `fresneloffset`, `lodstrength`,
  `sunstrength`, `texscale`, and `fogmodifier`, `alphamodifier`, `lodstepsize`
  (divinity2-lib's name table). What the last three do to the surface is not
  read yet; none of them is needed to draw it.
- **The turn a plant is given.** `CVeggyInstance::m_fRotation` is 0..1 and the
  shader that reads it is compiled HLSL. One full turn is our reading, and
  the only step of the vegetation chain that is not proven.
- **The game's camera rig.** Position and heading are recoverable from the
  overlay; the boom length, field of view and pitch are not, so a screen
  comparison matches layout rather than pixels.
- **Physics.** `Physics.nxb` is NVIDIA PhysX 2 `NxuStream` binary — a set of
  collision hulls, nothing visual, and nothing needs it to look right.
