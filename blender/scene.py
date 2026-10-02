import bpy
import numpy as np
from mathutils import Matrix, Vector

from ..divinity2 import graph, lod
from ..divinity2 import skin as dv2_skin

VERTEX_COLOURS = "RGBA"
BINORMAL_UV = ("dv2_binormal_xy", "dv2_binormal_zs")


def uv_name(index: int) -> str:
    return f"UV{index}"


def matrix_of(block) -> Matrix:
    return Matrix(graph.matrix_of(block).tolist())


def _is_shape(block) -> bool:
    return type(block).__name__ in graph.SHAPES


def rest_matrices(skeleton_root) -> dict:
    out = {}
    stack = [(skeleton_root, np.eye(4))]
    while stack:
        node, parent = stack.pop()
        world = parent @ graph.matrix_of(node)
        name = str(node.name)
        if name and not _is_shape(node):
            out.setdefault(name, world)
        stack += [(c, world) for c in reversed(lod.child_nodes(node))]
    return out


def build_armature(skeleton_root, name: str, scale: float, rest: dict | None = None):
    armature = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, armature)
    bpy.context.collection.objects.link(obj)

    _edit(obj, True)
    edit_bones = {}
    stack = [(skeleton_root, np.eye(4), None)]
    while stack:
        node, parent_world, parent = stack.pop()
        world = Matrix((parent_world @ graph.matrix_of(node)).tolist())
        stack += [(c, parent_world @ graph.matrix_of(node), node) for c in reversed(lod.child_nodes(node))]
        if _is_shape(node):
            continue
        bone_name = str(node.name)
        if not bone_name:
            continue

        bone = armature.edit_bones.new(bone_name)
        bone.head = (0.0, 0.0, 0.0)
        bone.tail = (0.0, 0.1, 0.0)
        placed = world
        if rest is not None and bone_name in rest:
            placed = Matrix(rest[bone_name].tolist())
        bone.matrix = _scaled(placed, scale)

        if parent is not None:
            bone.parent = edit_bones.get(str(parent.name))
        edit_bones[bone_name] = bone

    _edit(obj, False)
    return obj


def _edit(obj, on: bool) -> None:
    view_layer = bpy.context.view_layer
    active = view_layer.objects.active
    if on:
        if active is not None and active.mode != "OBJECT":
            with bpy.context.temp_override(active_object=active, object=active):
                bpy.ops.object.mode_set(mode="OBJECT")
        view_layer.objects.active = obj
        obj.select_set(True)
        view_layer.update()

    with bpy.context.temp_override(
        active_object=obj, object=obj, selected_objects=[obj]
    ):
        bpy.ops.object.mode_set(mode="EDIT" if on else "OBJECT")


def _scaled(world: Matrix, scale: float) -> Matrix:
    m = world.copy()
    m.translation = m.translation * scale
    return m


def build_mesh(drawn, scale: float, rest: dict | None = None):
    shape = drawn.shape
    data = drawn.data
    world = Matrix(drawn.world.tolist())
    name = drawn.name

    raw = np.array([(v.x, v.y, v.z) for v in data.vertices], dtype=np.float64)
    normals = np.array([(n.x, n.y, n.z) for n in data.normals], dtype=np.float64) \
        if data.has_normals and len(data.normals) else None
    count = len(raw)
    binormals = np.array([(b.x, b.y, b.z) for b in data.tangents], dtype=np.float64) \
        if len(getattr(data, "tangents", ()) or ()) else np.zeros((count, 3))
    signs = np.array(list(data.div_2_floats), dtype=np.float64) \
        if getattr(data, "has_div_2_floats", False) else np.ones(count)

    binormals = np.nan_to_num(binormals, nan=0.0, posinf=0.0, neginf=0.0)

    total = dv2_skin.rest_matrices(shape, rest, count) if rest else None
    if total is not None:
        raw = dv2_skin.to_rest_pose(raw, total)
        normals = dv2_skin.rotate(normals, total) if normals is not None else None
        binormals = dv2_skin.rotate(binormals, total)
        world = Matrix.Identity(4)

    vertices = (raw * scale).tolist()
    faces = [(t.v_1, t.v_2, t.v_3) for t in data.triangles]

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(verbose=False)

    if normals is not None:
        mesh.normals_split_custom_set_from_vertices(normals.tolist())

    colours = getattr(data, "vertex_colors", None)
    if colours is not None and len(colours):
        layer = mesh.color_attributes.new(
            name=VERTEX_COLOURS, type="FLOAT_COLOR", domain="POINT"
        )
        layer.data.foreach_set(
            "color", [c for v in colours for c in (v.r, v.g, v.b, v.a)]
        )

    corners = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", corners)
    for index, source in enumerate(data.uv_sets):
        uv = np.array([(t.u, t.v) for t in source], dtype=np.float32)[corners]
        uv[:, 1] = 1.0 - uv[:, 1]
        mesh.uv_layers.new(name=uv_name(index)).data.foreach_set("uv", uv.ravel())
    for layer, pair in zip(BINORMAL_UV, (binormals[:, :2], np.column_stack([binormals[:, 2], signs]))):
        mesh.uv_layers.new(name=layer).data.foreach_set("uv", pair.astype(np.float32)[corners].ravel())

    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = _scaled(world, scale)
    bpy.context.collection.objects.link(obj)
    return obj


def build_particles(system, world, scale: float):
    obj = bpy.data.objects.new(str(system.name) or "particles", None)
    obj.empty_display_type = "SPHERE"
    obj.matrix_world = _scaled(Matrix(world.tolist()), scale)
    bpy.context.collection.objects.link(obj)
    return obj


def bind_skin(obj, shape, armature_obj) -> int:
    skin = getattr(shape, "skin_instance", None)
    if skin is None or skin.data is None:
        return 0

    bones = [str(b.name) for b in skin.bones]
    for bone_name, bone_data in zip(bones, skin.data.bone_list):
        group = obj.vertex_groups.new(name=bone_name)
        for weight in bone_data.vertex_weights:
            group.add([weight.index], weight.weight, "REPLACE")

    modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = armature_obj
    obj.parent = armature_obj
    return len(bones)


def hang_on_bone(obj, armature_obj, bone_name: str) -> bool:
    bone = armature_obj.data.bones.get(bone_name) if bone_name else None
    if bone is None:
        return False
    world = obj.matrix_world.copy()
    obj.parent = armature_obj
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    tail = Matrix.Translation((0.0, bone.length, 0.0))
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = (armature_obj.matrix_world @ bone.matrix_local @ tail).inverted() @ world
    return True


def attach_to_bone(obj, armature_obj, bone_name: str) -> bool:
    bone = armature_obj.data.bones.get(bone_name)
    if bone is None:
        return False

    world = obj.matrix_world.copy()
    obj.parent = armature_obj
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.matrix_world = (
        armature_obj.matrix_world
        @ Matrix.Translation(bone.tail_local - bone.head_local).inverted()
        @ bone.matrix_local
        @ world
    )
    return True

