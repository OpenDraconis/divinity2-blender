"""Importing one Divinity II model into the current Blender scene.

A character and a barrel take the same path. Where they differ is what the
file filled in: a barrel has no skeleton, so no armature is built and every
shape keeps its own node transform.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import bpy

from ..divinity2 import attach, graph, particles, rig, static_asset, terrain
from ..divinity2.character import read_clips, read_model
from ..divinity2.nif import UNITS_PER_METRE

from . import animation as dv2_animation
from . import material as dv2_material
from . import scene


@dataclass
class Result:
    """What arrived, so a caller can check rather than trust."""

    armature: object = None
    objects: list = field(default_factory=list)
    bones: int = 0
    shared_rig: bool = False
    skinned: int = 0
    attached: int = 0
    hidden_lods: int = 0
    particles: int = 0       #: particle systems, as empties carrying `dv2_particles`
    grafted: int = 0         #: terrain and static asset stubs filled from their streamed files
    materials: int = 0
    clips: int = 0
    actions: list = field(default_factory=list)


def import_asset(
    path,
    game_root,
    cache=None,
    with_animation: bool = True,
    shared_clips: bool = True,
    extra_clips=(),
    standard_data: bool = False,
    for_unity: bool = False,
    model=None,
) -> Result:
    """Read any model file and build it: armature, meshes, skin, materials, clips.

    `extra_clips` are clips from elsewhere that play on this skeleton -- a
    region's `customanimations.kf`, named by the scripts of the characters that
    stand in it. They come after the character's own and its family's.

    `standard_data`: the model is region geometry, a static asset or terrain,
    which the engine runs through `CShadingTools::SetupStandardData`
    (`divinity2.material.STANDARD_DATA`).

    `for_unity`: build what Unity's FBX importer takes as the game has it, which is not
    always what the game has (the head and hair below, `build_material`'s names). The
    Unity port asks for it; in Blender itself the model stays as the engine draws it.

    `model`: the model already read (`character.read_part`, one equipment part), `path` its file.
    """
    game_root = Path(game_root)
    cache = Path(cache) if cache else game_root.parent / ".dv2-texture-cache"
    # A model alone has no region: the engine's registration defaults light it.
    for key, value in dv2_material.GLOBALS.items():
        if f"dv2_{key}" not in bpy.context.scene:
            bpy.context.scene[f"dv2_{key}"] = value
    character = model if model is not None else read_model(path)
    result = Result()

    # Half the characters carry no skeleton: they share their family's.
    skeleton = rig.shared_skeleton(character, game_root)
    rest = None

    if skeleton is not None:
        rest = scene.rest_matrices(skeleton)
        result.armature = scene.build_armature(
            skeleton, character.name, _factor(skeleton), rest
        )
        result.bones = len(result.armature.data.bones)
        result.shared_rig = character.skeleton is None

    bone_names = (
        [b.name for b in result.armature.data.bones] if result.armature else []
    )

    carried_so_far = 0
    for mesh in character.meshes:
        bone = None
        if attach.is_attachable(mesh.name):
            bone = attach.attachment_bone(
                attach.weapon_name(mesh.name), bone_names, carried_so_far
            )
            carried_so_far += 1

        factor = _factor(mesh.root)
        # A region's terrain stubs are empty until their streamed files are
        # hung under them. Everything else has no manifest and is untouched.
        result.grafted += terrain.graft(mesh.root, path)
        # A region's static assets likewise, at the finest level (`divinity2.static_asset`).
        result.grafted += static_asset.graft(mesh.root, game_root)
        for drawn in graph.walk(mesh.root):
            obj = scene.build_mesh(drawn, factor, rest)
            obj["dv2_path"] = drawn.path
            result.objects.append(obj)

            if drawn.hidden:
                obj.hide_set(True)
                obj.hide_render = True
                result.hidden_lods += 1

            built = dv2_material.build_material(drawn, game_root, cache, path, standard_data,
                                                 mesh.entry, for_unity)
            if built is not None:
                obj.data.materials.append(built)
                result.materials += 1

            if result.armature is None:
                continue

            # Every skinned shape, heads and hair included, is skinned the one
            # way the engine skins it: `MdlMan::CModel::ProcessSkinnedGeometry`
            # @c7c4c0 binds its bones by name to the family skeleton, and
            # `NiDX9Renderer::CalculateBoneMatrices` @5e4250 deforms it like any
            # other shape. `skin.py`'s formula equals the engine's whenever
            # `Shape.Local * NiSkinData.skin_transform` is the identity, which
            # it is for every shape of F_Rhode, the 28-bone MAX head included.
            if scene.bind_skin(obj, drawn.shape, result.armature):
                result.skinned += 1
            elif bone is not None and scene.attach_to_bone(
                obj, result.armature, bone
            ):
                result.attached += 1
            else:
                # No socket for it. It still travels with the character.
                obj.parent = result.armature

        for system, world, where, parent, state in particles.walk(mesh.root):
            obj = scene.build_particles(system, world, factor)
            obj["dv2_path"] = where
            obj["dv2_particles"] = json.dumps(particles.describe(system, world, where, parent, state,
                                                                 mesh.root, factor))
            result.objects.append(obj)
            result.particles += 1

    # A family's shared `.kf` repeats what the character already bundles --
    # a Froblin's own 15 clips are exactly Froblin_Base.kf's 15 -- so the
    # shared set only contributes names the character does not already have.
    clips = list(character.clips)
    if shared_clips:
        known = {c.name for c in clips}
        for kf in rig.clip_files(character, game_root):
            for clip in read_clips(kf):
                if clip.name not in known:
                    known.add(clip.name)
                    clips.append(clip)
    known = {c.name for c in clips}
    clips += [c for c in extra_clips if c.name not in known]
    result.clips = len(clips)

    if with_animation and clips and result.armature is not None:
        # A clip's translation keys are in game units in the bone's own local
        # space, and a Blender bone has no scale to carry the root's 0.01 --
        # `EditBone.matrix` keeps the orientation and drops it. So keys always
        # convert by the full unit, never by the tree's factor.
        result.actions = dv2_animation.build_actions(
            result.armature, clips, 1.0 / UNITS_PER_METRE
        )
        if result.actions:
            first = _resting(result.actions)
            result.armature.animation_data.action = first
            bpy.context.scene.frame_start = 1
            bpy.context.scene.frame_end = int(first.frame_range[1])

    return result


def _factor(root) -> float:
    """Game units to metres for one node tree.

    Every model in the game is authored in centimetres. How many of those
    units reach the world is stated on the tree's root node: a character
    leaves `Scene Root` at 1.0, and every scenery, item, effect and fortress
    bakes the conversion into it as 0.01. `graph.walk` already applies that
    scale, so the factor must not apply it a second time -- hence the product.
    """
    return 1.0 / (UNITS_PER_METRE * float(root.scale))


#: What the engine calls the state a character stands in, from its own
#: animation table: `CGameLogic_FixedStrings::ms_kAnimation_Still`, beside
#: `ms_kAnimation_F_Normal` and the rest of the movement set.
RESTING = "Still"


def _resting(actions):
    """The clip to show first.

    A character's own `.cat` holds only its variant clips -- `Black_Goblin`
    has `Stunned`, `Flee`, `Blind` and twelve ways to die -- and the standing
    clip comes from the family's shared set, which is appended after. Taking
    the first action therefore shows a goblin mid-stun.
    """
    for want in (RESTING, "Idle"):
        for action in actions:
            if action.name.rpartition("|")[2].startswith(want):
                return action
    return actions[0]
