# Carried meshes (`Attachables\`)

A weapon, a torch, a book or an effect plane is bundled into a character's
`.cat` like any other mesh. Two things set it apart:

- its entry path starts with `Attachables\`, and
- it has no `NiSkinInstance`. It is not deformed by the skeleton; one bone
  carries it.

## Which bone: read out of the executable

The assets do not say, and neither do the game's 4,096 XML files or 2,920 Lua
scripts. The executable does, in one function —
`CRpgStats_V2_SlotMapManager::GetBoneNameForModelmanSlot`:

| equipment slot | node |
|---|---|
| `handR` | `Bone_Weapon_01` |
| `weaponSlotBack` | `Bone_Weapon_02` |
| `handL`, `armL` | `Bone_Weapon_03` |
| `weaponSlotBack2` | `Bone_Weapon_04` |
| `weaponSlotBack3` | `Bone_Weapon_05` |
| `weaponSlotBack4` | `Bone_Weapon_06` |
| anything else | the empty string |

Which slot an item sits in is the animation's business: a clip's text keys
carry `eq=handR:2H_Sword_Alguard` to equip and `ue=weaponSlotBack` to unequip.
A mesh a `.cat` simply bundles has no such event, so it is in the main hand.

`Bone_Weapon_01` is in eight of the 46 family skeletons — Froblin, Goblin,
HumanMale, HumanFemale, SkeletonHuman and the three Trolls — which is every
rig that carries anything.

See `docs/engine.md` for how that was read, and `divinity2/engine.py` for the
table.

## The `Dummy_` nodes are effect points

Counted over all 46 family skeletons, and confirmed against the engine's own
names:

| node | what the game hangs on it |
|---|---|
| `Dummy_Cast_Primary`, `Dummy_Cast_Secondary` | where a spell leaves the body |
| `Dummy_Impact_01` … `Dummy_Impact_10` | where a hit registers |
| `Dummy_Head_Above`, `Dummy_Head_Around` | where a status icon floats |
| `Dummy_Foot_Left`, `Dummy_Foot_Right` | where footstep dust spawns |

`Dummy_1H_Sword` and `Dummy_1H_Sword01` exist in the Froblin rig alone, at the
same positions as its `Bone_Weapon_01` and `Bone_Weapon_03`: artist aliases,
not a second system.

No other skeleton has a weapon dummy: `HumanMale` and `HumanFemale`, who carry
swords, bows, staves and shields, have none at all. A rule built on these names
looks right on a goblin and is wrong everywhere else.

It is not in the game's data files either. The install carries 4,096 XML
files and 2,920 Lua scripts; neither mentions a bone. The only `Dummy_` in
any Lua is a training dummy in the tutorial.

## What was in the files, and was not enough

This is the part worth writing down, because the naming invites a wrong
answer. Everything was checked:

| where | what is there | attachment? |
|---|---|---|
| `Attachables\*.nif` | scene root, a node named after the weapon, geometry, and rendering extra data (`worldScale`, `FallOffPower`, `EnableFallOff`, `UseEnvMapping`) | no |
| the `.cat`'s `CMeshDataEntry` | `name` and `mesh_data_reference`; the two Div2 fields `nif.xml` calls unknown read 2 and 1 on **every** entry, carried or not | no |
| `Win32/Items/**/*.item` | the same NIF again, plus `swoosh_begin` and `swoosh_end` for the weapon trail, and a `DivStandardMaterial` name | no |
| the family skeleton | `Dummy_` nodes — see above | for one family out of 46 |

The game decides at runtime, from its equipment rules. The assets do not
record it.

## What the add-on does

One rule, and it is the engine's: a carried mesh goes on the node its slot
maps to, and a mesh with no slot event is in the main hand — `handR`, which is
`Bone_Weapon_01`. A rig with no socket gets none, and the mesh is parented to
the armature object so it still travels with the character.
