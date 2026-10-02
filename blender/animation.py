import bpy
from mathutils import Matrix, Quaternion, Vector

from ..divinity2 import animation as dv2_animation

# NiMultiTargetTransformController::Update @63e070 decomp
def _sample(track, at: float, factor: float, rest: Matrix):
    t, r, s = dv2_animation.sample(track, at)
    location = Vector(t) * factor if t is not None else rest.to_translation()
    rotation = rest.to_quaternion() if r is None else Quaternion((1.0, 0.0, 0.0, 0.0))
    if r is not None and (track.rotations or Quaternion(r).magnitude > 1e-6):
        rotation = Quaternion(r).normalized()
    scale = 1.0
    if s is not None and (track.scales or s > 0.0):
        scale = s
    return location, rotation, scale


def _rest_local(bone) -> Matrix:
    if bone.parent is None:
        return bone.matrix_local.copy()
    return bone.parent.matrix_local.inverted_safe() @ bone.matrix_local


def build_action(armature_obj, clip, factor: float, fps: int | None = None):
    tracks = [t for t in dv2_animation.tracks(clip.sequence)]
    if not tracks:
        return None

    fps = fps or bpy.context.scene.render.fps
    frames = max(2, int(round(clip.duration * fps)) + 1)

    action = bpy.data.actions.new(f"{armature_obj.name}|{clip.name}")
    action.use_fake_user = True

    if armature_obj.animation_data is None:
        armature_obj.animation_data_create()
    previous = armature_obj.animation_data.action
    armature_obj.animation_data.action = action

    pose_bones = armature_obj.pose.bones
    rest = {b.name: _rest_local(b) for b in armature_obj.data.bones}
    used = 0

    for track in tracks:
        bone = pose_bones.get(track.node)
        if bone is None:
            continue
        bone.rotation_mode = "QUATERNION"
        basis = rest[track.node].inverted_safe()
        used += 1

        for frame in range(frames):
            at = frame / (frames - 1)
            location, rotation, scale = _sample(track, at, factor, rest[track.node])
            local = Matrix.LocRotScale(location, rotation, (scale, scale, scale))
            bone.matrix_basis = basis @ local

            number = 1 + frame
            bone.keyframe_insert("location", frame=number, group=track.node)
            bone.keyframe_insert("rotation_quaternion", frame=number, group=track.node)
            bone.keyframe_insert("scale", frame=number, group=track.node)

    armature_obj.animation_data.action = previous
    if not used:
        bpy.data.actions.remove(action)
        return None

    _mark(action, clip, fps)
    action.frame_range
    return action


def _mark(action, clip, fps: int) -> None:
    for event in dv2_animation.events(clip.sequence):
        marker = action.pose_markers.new(event.text)
        marker.frame = 1 + int(round((event.time - clip.start) * fps))


def build_actions(armature_obj, clips, factor: float) -> list:
    built = []
    for clip in clips:
        action = build_action(armature_obj, clip, factor)
        if action is not None:
            built.append(action)
    return built
