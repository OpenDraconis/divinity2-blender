# The character template (`.cat`)

A character in Divinity II is one file. A `.cat` is a NIF that bundles the
skeleton, the meshes, the animation set and the clips, each as an `MdlMan::`
entry that keeps the path it had before it was bundled. Nothing has to be
found beside it on disk.

## What a `.cat` holds

Read from `Black_Goblin.cat`, 2026-09-15:

```
MdlMan::CModelTemplateDataEntry   'Templates\Black_Goblin.cat'
  MdlMan::CSkeletonDataEntry      'Froblin\skeleton.nif'
  MdlMan::CAMDataEntry            'Froblin\Froblin.kfm'
  MdlMan::CMeshDataEntry          'Froblin\Meshes\Froblin.nif'
  MdlMan::CMeshDataEntry          'Froblin\Meshes\1H_Sword_Long_A_A.nif'
  MdlMan::CAnimationDataEntry     'Froblin\Froblin.kf'
```

| entry | field | what it is |
|---|---|---|
| `CSkeletonDataEntry` | `skeleton_data_reference` | the skeleton's own `NiNode` scene root |
| `CAMDataEntry` | `binary_data` | **a KFM without its header**, as `nif.xml` says |
| `CMeshDataEntry` | `mesh_data_reference` | a mesh file's `NiNode` scene root |
| `CAnimationDataEntry` | `controller_seq_list` | the clips, as `NiControllerSequence` |

The clips are named as the game names them: `Idle1`, `Move_F_Normal`,
`Melee_Static_01`, `Hit_Back`. Each carries `start_time`, `stop_time` and one
controlled block per bone.

## Half the characters carry no skeleton

Of the 324 templates in the install, exactly **162 hold a skeleton and clips
and 162 hold neither**. The 162 without are the human ones —
`DefaultHumanMale`, `F_Bandit_T1`, `F_BlackRing_Keara` — and they carry only
meshes. They share a skeleton and its clips with every other human, which is
why the bundle does not repeat them.

`rig.shared_skeleton` resolves that shared rig.

## The version

Divinity II files are NIF **20.3.0.9** with user version `0x20000` or
`0x30000`. `nif.xml` gives that combination its own id, `V20_3_0_9_DIV2`, and
its own token `#DIVINITY2#`, and lists the extensions `nft`, `item` and `cat`.
The Div2-specific fields it guards — `div_2_floats` on geometry data,
`div_2_ints` and `div_2_ref` on a controller sequence — are present in real
files, so a reader that ignores the token reads these files wrongly.

## The trap

`NiTriShapeData.has_uv` reads **0** on every Divinity II shape, including ones
that carry a full UV set. It is a legacy field that this version no longer
writes. The truth is in `data_flags.num_uv_sets`, or simply in whether
`uv_sets` is non-empty. A reader that trusts `has_uv` produces a correct,
fully textured material on a mesh with no UV map, and the asset renders
untextured while every check passes.

## The shared rig

A `.cat` holds only what is unique to that character. Everything a family
shares lives in `Win32/Characters/<family>/`:

```
Win32/Characters/Froblin/
  Skeleton.nif              every Froblin uses this
  Froblin_Base.kf/.kfm      the base clips
  Froblin_Unarmed.kf/.kfm   four more sets: a Froblin has several walks
  Shaman.kf/.kfm
  Soldier_Dualwield.kf/.kfm
  Soldier_Onehanded.kf/.kfm
```

The family is the first segment of a mesh entry's path:
`HumanMale\Meshes\M_Torso_A.nif` is family `HumanMale`. `Attachables` is not a
family — it is where weapons live — so the family is the first segment that
has a `Skeleton.nif` beside it.

This explains both halves at once:

- `DefaultHumanMale.cat` carries four meshes, no skeleton and no clips. Its
  bundled KFM is 34 KB and names `Human_M_Base.kf`. The skeleton is
  `Win32/Characters/HumanMale/Skeleton.nif`, 123 bones.
- `Black_Goblin.cat` carries its own skeleton and 15 clips — but they are all
  deaths, stuns and a flee. No `Idle1`, no walk. Those are in
  `Froblin_Base.kf`, which its KFM names 15 times.

So a character's clips are in two places, and a tool that reads only the `.cat`
gets a creature that can die but not stand.

## Skinning: the skeleton is the rest pose

A skinned shape stores its vertices in its own node's space. What takes them
out of it is one matrix per bone, `NiSkinData.bone_list[i].skin_transform`,
and where that bone stands in the skeleton file:

    v = Σᵢ wᵢ · Wᵢ · Bᵢ · v

`Bᵢ` is the bone's `skin_transform`, `Wᵢ` is the bone's world transform in
`Win32/Characters/<family>/Skeleton.nif`. That is the whole deformation. It is
the same formula PyFFI has used for twenty years; nothing about Divinity II is
special here.

**`NiSkinData.skin_transform` is not part of it.** It is the inverse of the
shape node's own world transform. Measured on `FroblinBoss`:

| shape | node world translation | `skin_transform` translation |
|---|---|---|
| `FroblinBoss_HI` | (0.0, 2.7, 124.1) | (0.0, −2.7, −124.1) |
| `FroblinBoss_Armor_A_HI` | (−393.0, −260.9, 79.2) | (393.0, −79.2, −260.9) |

It says where the geometry came from, not where it goes. Folding it into the
deformation moves a shape by its own node offset — which is nothing at all for
a body authored on the origin, and four metres for an armour authored beside
it. That is the whole reason a character could arrive with a correct body and
its armour standing next to it, and why the fault looked like two different
rigs when it was one wrong term.

Each mesh file carries a copy of the skeleton as well, but that copy is
**collapsed**: every bone node in it sits at the origin. It gives the
parentage and nothing else. The pose is only in `Skeleton.nif`.

One character, one skeleton, one armature.

## Clips are B-splines, not keyframes

A clip stores no keys. It stores the control points of a cubic B-spline,
quantised to 16-bit integers, and the game evaluates the curve as it plays.
`Black_Goblin`'s `Stunned` holds 1,158 `NiBSplineCompTransformInterpolator`
blocks and not one keyframe, which is why a keyframe importer reads it and
finds nothing at all.

A handle of `0xFFFF` means the track is not animated; the interpolator's own
static transform is the value for the whole clip. A component that is absent
is written as `-FLT_MAX`, not left out — `trs_valid`, which is supposed to say
which of translation, rotation and scale are present, is an **empty array** at
this version, so the sentinel in the value is the only thing that tells the
truth.

The control points are not points on the curve. Treating them as keyframes is
the tempting shortcut and gives an animation that is close but wrong, in a way
that reads as bad rigging rather than bad maths.
