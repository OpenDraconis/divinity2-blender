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
    armature: object = None
    objects: list = field(default_factory=list)
    bones: int = 0
    shared_rig: bool = False
    skinned: int = 0
    attached: int = 0
    hidden_lods: int = 0
    particles: int = 0
    grafted: int = 0
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
    game_root = Path(game_root)
    cache = Path(cache) if cache else game_root.parent / ".dv2-texture-cache"
    for key, value in dv2_material.GLOBALS.items():
        if f"dv2_{key}" not in bpy.context.scene:
            bpy.context.scene[f"dv2_{key}"] = value
    character = model if model is not None else read_model(path)
    result = Result()

    skeleton = rig.shared_skeleton(character, game_root)
    rest = None
    if skeleton is None and with_animation and character.clips and len(character.meshes) == 1:
        skeleton = _animated_tree(character)

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
        result.grafted += terrain.graft(mesh.root, path)
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

            # NiDX9Renderer::CalculateBoneMatrices @5e4250 decomp
            if scene.bind_skin(obj, drawn.shape, result.armature):
                result.skinned += 1
            elif bone is not None and scene.attach_to_bone(
                obj, result.armature, bone
            ):
                result.attached += 1
            elif not scene.hang_on_bone(obj, result.armature, _parent_node(drawn.path)):
                obj.parent = result.armature

        for system, world, where, parent, state in particles.walk(mesh.root):
            obj = scene.build_particles(system, world, factor)
            obj["dv2_path"] = where
            obj["dv2_particles"] = json.dumps(particles.describe(system, world, where, parent, state,
                                                                 mesh.root, factor))
            result.objects.append(obj)
            result.particles += 1

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
        result.actions = dv2_animation.build_actions(
            result.armature, clips, 1.0 / UNITS_PER_METRE
        )
        if result.actions:
            first = _resting(result.actions)
            result.armature.animation_data.action = first
            bpy.context.scene.frame_start = 1
            bpy.context.scene.frame_end = int(first.frame_range[1])

    return result


# CStreamableAssetData::GetActorManager @1063180, NiMultiTargetTransformController::Update @63e070 decomp
def _animated_tree(character):
    return character.meshes[0].root


def _parent_node(path: str) -> str:
    parts = path.split("/")
    return parts[-2] if len(parts) > 1 else ""


def _factor(root) -> float:
    return 1.0 / (UNITS_PER_METRE * float(root.scale))


RESTING = "Still"


def _resting(actions):
    for want in (RESTING, "Idle"):
        for action in actions:
            if action.name.rpartition("|")[2].startswith(want):
                return action
    return actions[0]
