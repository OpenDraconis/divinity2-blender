"""A model's own animation, whole, as plain data: its node tree and every
`NiControllerSequence` it carries.

An effect, a scenery item or a fortress is a `CStreamableAssetData`: a node
tree and, when its flag is set, an embedded KFM whose animations name the
sequences in the block's own list (`CStreamableAssetData::GetActorManager`
@1063180 builds the actor manager from it, not cumulative, so every controlled
block drives the node it names). The engine plays one by its KFM event code
(`CAnimationPlayer::PlayAnimation` @6cb270). The port runs the sequences itself,
so this hands over what they drive and every key, and leaves the rules to the
consumer:

- `nodes`: every `NiAVObject` in file order, depth first, with its parent's
  index, its own transform in the file's units, its `NiBillboardNode` mode
  (`NiBillboardNode::LoadBinary` @5accc0 reads it into the flags,
  `RotateToCamera` @5ac4b0 takes the low three bits), and what the sequences
  can reach through it: its `NiGeomMorpherController`'s targets, its
  `NiFlipController`s' pictures, its `NiFloatExtraData`.
- `sequences`: per sequence its KFM id, cycle, frequency, key span, text keys
  and controlled blocks, each with its interpolator as data (`_interpolator`).

B-spline interpolators arrive as their control points, dequantised by
`nifgen` (`get_translations` and the rest); the consumer evaluates them as
`animation.evaluate` does.
"""

from . import kfm, lod
from . import texture as dv2_texture

#: A handle of 0xFFFF means "this channel is not animated" (`animation.NO_HANDLE`).
NO_HANDLE = 65535


def _name(value) -> str:
    return str(getattr(value, "name", value))


def _vector(v) -> list:
    return [float(v.x), float(v.y), float(v.z)]


def _key_value(value):
    if hasattr(value, "w"):
        return [float(value.w), float(value.x), float(value.y), float(value.z)]
    if hasattr(value, "x"):
        return _vector(value)
    if hasattr(value, "r"):
        return [float(value.r), float(value.g), float(value.b), float(getattr(value, "a", 1.0))]
    return float(value) if not isinstance(value, bool) else bool(value)


def _keys(group) -> dict | None:
    """A `KeyGroup` as `{"type", "keys"}`, each key `[time, value, forward,
    backward]` or, for TBC keys, `[time, value, tension, bias, continuity]`;
    None when it holds no key."""
    if group is None or not int(getattr(group, "num_keys", 0) or 0):
        return None
    kind = _name(group.interpolation)
    out = []
    for key in group.keys:
        row = [float(key.time), _key_value(key.value)]
        if kind == "TBC_KEY":
            tbc = key.tbc
            row += [float(tbc.t), float(tbc.b), float(tbc.c)]
        elif kind == "QUADRATIC_KEY":
            row += [_key_value(key.forward), _key_value(key.backward)]
        out.append(row)
    return {"type": kind, "keys": out}


def _quaternion_keys(data) -> dict | None:
    keys = getattr(data, "quaternion_keys", None)
    if not keys or not len(keys):
        return None
    kind = _name(data.rotation_type)
    out = []
    for key in keys:
        row = [float(key.time), _key_value(key.value)]
        if kind == "TBC_KEY":
            tbc = key.tbc
            row += [float(tbc.t), float(tbc.b), float(tbc.c)]
        out.append(row)
    return {"type": kind, "keys": out}


def _pose(transform) -> dict:
    """An `NiQuatTransform`; a component written as -FLT_MAX is not stated
    (`animation.INVALID`) and arrives as None."""
    t, r, s = transform.translation, transform.rotation, float(transform.scale)
    stated = lambda *v: all(abs(float(x)) < 3.4e38 for x in v)
    return {
        "translation": _vector(t) if stated(t.x, t.y, t.z) else None,
        "rotation": [float(r.w), float(r.x), float(r.y), float(r.z)] if stated(r.w, r.x, r.y, r.z) else None,
        "scale": s if stated(s) else None,
    }


def _comp(interp, handle, size: int, offset, half_range) -> list:
    if handle == NO_HANDLE or not interp.basis_data or not interp.spline_data:
        return []
    return [list(p) for p in interp.spline_data.get_comp_data(
        handle, interp.basis_data.num_control_points, size, offset, half_range)]


def _interpolator(interp) -> dict | None:
    """One interpolator as data. `kind` names what it is; `value` or `pose` is
    what it holds when it has no keys."""
    if interp is None:
        return None
    kind = type(interp).__name__
    data = getattr(interp, "data", None)
    if kind == "NiTransformInterpolator":
        out = {"kind": "transform", "pose": _pose(interp.transform)}
        if data is not None:
            rotation = _name(data.rotation_type)
            out["rotation_type"] = rotation
            if rotation == "XYZ_ROTATION_KEY":
                out["euler"] = [_keys(g) for g in data.xyz_rotations]
            else:
                out["rotations"] = _quaternion_keys(data)
            out["translations"] = _keys(data.translations)
            out["scales"] = _keys(data.scales)
        return out
    if kind == "NiBSplineCompTransformInterpolator":
        return {
            "kind": "bspline_transform", "start": float(interp.start_time), "stop": float(interp.stop_time),
            "pose": _pose(interp.transform),
            "translations": [list(p) for p in interp.get_translations()],
            "rotations": [list(p) for p in interp.get_rotations()],
            "scales": [[float(s)] for s in interp.get_scales()],
        }
    if kind == "NiBSplineCompFloatInterpolator":
        return {"kind": "bspline_float", "start": float(interp.start_time), "stop": float(interp.stop_time),
                "value": float(interp.value),
                "points": _comp(interp, interp.handle, 1, interp.float_offset, interp.float_half_range)}
    if kind == "NiBSplineCompPoint3Interpolator":
        return {"kind": "bspline_point3", "start": float(interp.start_time), "stop": float(interp.stop_time),
                "value": _vector(interp.value),
                "points": _comp(interp, interp.handle, 3, interp.position_offset, interp.position_half_range)}
    if kind == "NiFloatInterpolator":
        return {"kind": "float", "value": float(interp.value), "keys": _keys(data.data) if data else None}
    if kind == "NiPoint3Interpolator":
        return {"kind": "point3", "value": _vector(interp.value), "keys": _keys(data.data) if data else None}
    if kind in ("NiBoolInterpolator", "NiBoolTimelineInterpolator"):
        return {"kind": "bool_timeline" if kind == "NiBoolTimelineInterpolator" else "bool",
                "value": bool(interp.value), "keys": _keys(data.data) if data else None}
    if kind == "NiPathInterpolator":
        return {"kind": "path", "flags": int(interp.flags), "bank_dir": int(interp.bank_dir),
                "max_bank_angle": float(interp.max_bank_angle), "smoothing": float(interp.smoothing),
                "follow_axis": int(interp.follow_axis),
                "path": _keys(interp.path_data.data) if interp.path_data else None,
                "percent": _keys(interp.percent_data.data) if interp.percent_data else None}
    return {"kind": kind}


def _controllers(block):
    c = getattr(block, "controller", None)
    while c is not None:
        yield c
        c = getattr(c, "next_controller", None)


def _node(node, parent: int, path: str) -> dict:
    """One `NiAVObject`: its own transform in the file's units and what hangs on it.

    `rotation` is the matrix's rows as the file stores them; the node's matrix is
    their transpose times `scale`, as `graph.matrix_of` builds it."""
    r = node.rotation
    out = {
        "name": str(node.name), "type": type(node).__name__, "path": path, "parent": parent,
        "translation": _vector(node.translation),
        "rotation": [[float(r.m_11), float(r.m_12), float(r.m_13)],
                     [float(r.m_21), float(r.m_22), float(r.m_23)],
                     [float(r.m_31), float(r.m_32), float(r.m_33)]],
        "scale": float(node.scale), "flags": int(node.flags), "culled": bool(lod.is_culled(node)),
    }
    if out["type"] == "NiBillboardNode":
        out["billboard"] = int(getattr(node, "billboard_mode", 0)) & 7
    extra = {str(e.name): float(e.float_data) for e in (getattr(node, "extra_data_list", ()) or ())
             if e is not None and type(e).__name__ == "NiFloatExtraData"}
    if extra:
        out["float_extra"] = extra
    for c in _controllers(node):
        if type(c).__name__ == "NiGeomMorpherController" and c.data is not None:
            out["morph"] = {
                "relative": bool(c.data.relative_targets), "flags": int(c.morpher_flags),
                "always_update": bool(c.always_update),
                "targets": [{"name": str(m.frame_name), "vectors": [_vector(v) for v in m.vectors]}
                            for m in c.data.morphs],
            }
    for prop in (getattr(node, "properties", ()) or ()):
        if prop is None:
            continue
        for c in _controllers(prop):
            if type(c).__name__ == "NiFlipController":
                out.setdefault("flips", []).append({
                    "slot": int(c.texture_slot),
                    "textures": [f"{dv2_texture.stem(str(s.file_name)).lower()}.dds" if s is not None else None
                                 for s in c.sources],
                    "files": [str(s.file_name) if s is not None else None for s in c.sources],
                })
    return out


def tree(root) -> list:
    """Every `NiAVObject` under `root`, depth first in child order, culled ones too."""
    out = []
    stack = [(root, -1, "")]
    while stack:
        node, parent, above = stack.pop()
        path = f"{above}/{node.name}" if above else str(node.name)
        index = len(out)
        out.append(_node(node, parent, path))
        for child in reversed(lod.child_nodes(node)):
            stack.append((child, index, path))
    return out


def describe(sequence, sequence_id: int) -> dict:
    """One `NiControllerSequence`: timing, text keys and every controlled block."""
    text = getattr(sequence, "text_keys", None)
    return {
        "id": sequence_id, "name": str(sequence.name),
        "cycle": _name(sequence.cycle_type).replace("CYCLE_", ""),
        "frequency": float(sequence.frequency),
        "begin": float(sequence.start_time), "end": float(sequence.stop_time),
        "accum_root": str(getattr(sequence, "accum_root_name", "") or ""),
        "text_keys": [[float(k.time), str(k.value)] for k in text.text_keys] if text is not None else [],
        "blocks": [{
            "node": str(b.node_name), "property": str(b.property_type or ""),
            "controller": str(b.controller_type or ""), "controller_id": str(b.controller_id or ""),
            "interpolator_id": str(b.interpolator_id or ""), "priority": int(b.priority),
            "interpolator": _interpolator(b.interpolator),
        } for b in sequence.controlled_blocks if b.interpolator is not None],
    }


def asset(streamable) -> dict:
    """A `CStreamableAssetData` block: its tree and its sequences by KFM id.

    The embedded KFM's animation `index` is the sequence's place in the block's
    list and its event code the id the engine plays it by; a block without a
    readable KFM takes the list's order as ids.
    """
    sequences = [s for s in (getattr(streamable, "refs", ()) or ())
                 if s is not None and type(s).__name__ == "NiControllerSequence"]
    ids = list(range(len(sequences)))
    if getattr(streamable, "has_data", 0) and getattr(streamable, "data", None):
        try:
            for animation in kfm.read_headerless(bytes(streamable.data)).animations:
                if 0 <= animation.index < len(ids):
                    ids[animation.index] = animation.event_code
        except (kfm.Truncated, ValueError):
            pass
    return {"nodes": tree(streamable.root),
            "sequences": [describe(s, i) for s, i in zip(sequences, ids)]}

