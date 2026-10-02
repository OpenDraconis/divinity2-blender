import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from ..divinity2 import region as dv2_region
from ..divinity2 import vegetation as dv2_vegetation

from . import material as dv2_material
from .importer import import_asset

KINDS = ("terrain", "scenery", "item", "character", "tree", "light",
         "trigger", "vegetation")

WATTS = 40.0

MARKER = 0.25

SUN_WATTS = 4.0

AMBIENT = 0.12


ALL = "*"


@dataclass
class Built:
    counts: dict = field(default_factory=dict)
    models: int = 0
    failed: list = field(default_factory=list)
    unresolved: int = 0


def _named(name: str, made: list | None = None):
    found = bpy.data.collections.get(name)
    if found is None:
        found = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(found)
    if made is not None and found not in made:
        made.append(found)
    return found


def _matrix(placed) -> Matrix:
    basis = Matrix.Identity(4)
    if placed.basis is not None:
        basis = Matrix([list(row) for row in placed.basis]).to_4x4()
    basis.translation = Vector(placed.position)
    return basis @ Matrix.Scale(placed.scale, 4)


STANDARD_DATA_KINDS = ("terrain", "scenery")


def _import_into(path, game_root, cache, into, **options) -> list:
    was = set(bpy.data.objects)
    import_asset(path, game_root, cache=cache, with_animation=False, **options)
    made = [o for o in bpy.data.objects if o not in was]
    for obj in made:
        obj["dv2_drawn"] = obj.visible_get() and not obj.hide_render
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        into.objects.link(obj)
    return made


def _library(path, game_root, cache, into, kind=""):
    made = _import_into(path, game_root, cache, into, standard_data=kind in STANDARD_DATA_KINDS)
    for obj in made:
        obj.hide_set(True)
        obj.hide_render = True
    return made


def _copy(source, where: Matrix, into, name: str):
    copies = {}
    for obj in source:
        made = obj.copy()
        into.objects.link(made)
        drawn = bool(obj.get("dv2_drawn", True))
        made.hide_set(not drawn)
        made.hide_render = not drawn
        copies[obj.name] = made
    for obj in source:
        if obj.parent is not None and obj.parent.name in copies:
            copies[obj.name].parent = copies[obj.parent.name]
    roots = []
    for obj in source:
        if obj.parent is None:
            copies[obj.name].matrix_world = where @ obj.matrix_world
            roots.append(copies[obj.name])
    for root in roots:
        root.name = name
    return roots


def _describe(obj, placed):
    obj["dv2_kind"] = placed.kind
    obj["dv2_uuid"] = placed.uuid
    obj["dv2_fields"] = json.dumps(placed.fields)


def _light(placed, into):
    shape = placed.fields.get("shape", "point")
    data = bpy.data.lights.new(placed.name or shape,
                               {"sun": "SUN", "spot": "SPOT"}.get(shape, "POINT"))
    data.color = placed.fields.get("colour", (1.0, 1.0, 1.0))
    dimmer = float(placed.fields.get("dimmer", 1.0))
    obj = bpy.data.objects.new(placed.name or shape, data)
    into.objects.link(obj)

    if shape in ("sun", "spot"):
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = Vector(placed.fields["direction"]).to_track_quat("-Z", "Y")
    if shape == "sun":
        data.energy = dimmer * SUN_WATTS
    else:
        radius = float(placed.fields.get("radius", 1.0))
        data.energy = dimmer * WATTS
        data.use_custom_distance = True
        data.cutoff_distance = radius
        data.shadow_soft_size = max(float(placed.fields.get("inner", 0.0)), 0.01)
        obj.location = placed.position
        if shape == "spot":
            data.spot_size = math.radians(float(placed.fields.get("fov", 45.0)))
    _describe(obj, placed)
    return obj


def _trigger(placed, into):
    if placed.polygon and placed.height:
        bottom, top = placed.height
        ring = [Vector((p[0], p[1], bottom)) for p in placed.polygon]
        mesh = bpy.data.meshes.new(placed.name or "trigger")
        verts = ring + [Vector((v.x, v.y, top)) for v in ring]
        n = len(ring)
        faces = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
        faces += [list(range(n))[::-1], list(range(n, 2 * n))]
        mesh.from_pydata([tuple(v) for v in verts], [], faces)
        mesh.update()
        obj = bpy.data.objects.new(placed.name or "trigger", mesh)
        obj.display_type = "WIRE"
    else:
        obj = bpy.data.objects.new(placed.name or "trigger", None)
        obj.empty_display_type = "SPHERE"
        obj.empty_display_size = MARKER
        obj.matrix_world = _matrix(placed)
    into.objects.link(obj)
    obj.hide_render = True
    _describe(obj, placed)
    return obj


def _tree(placed, into):
    obj = bpy.data.objects.new(placed.name or "tree", None)
    obj.empty_display_type = "CONE"
    obj.empty_display_size = max(placed.scale, 0.1)
    obj.location = placed.position
    into.objects.link(obj)
    obj.hide_render = True
    _describe(obj, placed)
    return obj


def _world(placed):
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("Divinity II")
        bpy.context.scene.world = world
    background = world.node_tree.nodes.get("Background")
    if background is None:
        return world
    ambient = placed.fields.get("ambient", (0.0, 0.0, 0.0))
    background.inputs[0].default_value = tuple(ambient) + (1.0,)
    background.inputs[1].default_value = AMBIENT * float(placed.fields.get("dimmer", 1.0))
    world["dv2_ambient"] = ambient
    return world


def _engine_globals(game_root, name: str, sub: str, time: str, statics) -> None:
    from ..divinity2 import environment as dv2_environment
    from ..divinity2 import terrain as dv2_terrain

    scene = bpy.context.scene
    for key, value in dv2_material.GLOBALS.items():
        scene[f"dv2_{key}"] = value
    lit = dv2_environment.frame(dv2_environment.read(game_root, name, sub, time))
    scene["dv2_fGlobalNormalScale"] = lit["globals"]["fGlobalNormalScale"]
    scene["dv2_fGlobalLightmapIntensity"] = lit["settings"]["DarkMapBrightness"]
    if statics is not None:
        splat = dv2_terrain.splat(statics)
        scene["dv2_g_TerrainSplatRadius"] = splat["radius"]
        scene["dv2_g_TerrainSplatBlendRadius"] = splat["blend"]
    scene.view_settings.view_transform = "Standard"


def _one(game_root, name: str, sub: str, time: str, kinds, cache,
         built: Built, library: dict) -> list:
    read = dv2_region.read(game_root, name, sub, time)
    made = []
    templates = None
    _engine_globals(game_root, name, sub, time, read.statics)

    def _collection(label):
        return _named(f"{name} {sub} {label}", made)

    def count(kind):
        built.counts[kind] = built.counts.get(kind, 0) + 1

    if "terrain" in kinds and read.statics is not None:
        for _ in _import_into(read.statics, game_root, cache, _collection("terrain"), standard_data=True):
            count("terrain")

    for kind in ("scenery", "item", "character"):
        if kind not in kinds:
            continue
        want = read.of(kind)
        if not want:
            continue
        into = _collection(kind)
        if templates is None:
            templates = _collection("models")
            templates.hide_viewport = templates.hide_render = True
        for placed in want:
            if placed.model is None:
                built.unresolved += 1
                continue
            key = str(placed.model)
            if key not in library:
                try:
                    library[key] = _library(placed.model, game_root, cache, templates, kind)
                    built.models += 1
                except Exception as exc:                       # noqa: BLE001
                    library[key] = []
                    built.failed.append(f"{placed.model.name}: {exc}")
            source = library[key]
            if not source:
                continue
            for root in _copy(source, _matrix(placed), into, placed.name):
                _describe(root, placed)
            count(kind)

    for kind, make in (("light", _light), ("trigger", _trigger), ("tree", _tree)):
        if kind not in kinds:
            continue
        want = read.of(kind)
        if not want:
            continue
        into = _collection(kind)
        for placed in want:
            make(placed, into)
            if placed.fields.get("shape") == "sun":
                _world(placed)
            count(kind)

    if "vegetation" in kinds and read.vegetation is not None:
        _vegetation(game_root, name, sub, read, _collection, cache, count)

    return made


def _vegetation(game_root, name, sub, read, _collection, cache, count):
    library = _collection("vegetation library")
    made = _import_into(read.vegetation, game_root, cache, library)
    library.hide_viewport = True

    meshes = {}
    for obj in made:
        parts = str(obj.get("dv2_path", "")).split("/")
        if len(parts) > 1:
            meshes.setdefault(parts[1], []).append(obj)
    if not meshes:
        return

    recipe = dv2_vegetation.read(game_root, name, sub)
    into = _collection("vegetation")
    for plant in dv2_vegetation.scatter(recipe):
        source = meshes.get(recipe.plants[plant.plant].model)
        if not source:
            continue
        where = (Matrix.Translation((plant.x, plant.y, plant.z))
                 @ Matrix.Rotation(plant.rotation * 2.0 * math.pi, 4, "Z")
                 @ Matrix.Scale(plant.size, 4))
        for root in _copy(source, where, into, plant.plant):
            root["dv2_kind"] = "vegetation"
            root["dv2_plant"] = plant.plant
            root["dv2_colour"] = plant.colour
        count("vegetation")


def import_region(game_root, name: str, sub: str = "Main", time: str = "",
                  kinds=KINDS, cache=None) -> Built:
    game_root = Path(game_root)
    built = Built()
    library = {}
    subs = dv2_region.subregions(game_root, name) if sub == ALL else [sub]

    for index, one in enumerate(subs):
        made = _one(game_root, name, one, time, kinds, cache, built, library)
        if index and made:
            layer = bpy.context.view_layer.layer_collection
            for collection in made:
                found = layer.children.get(collection.name)
                if found is not None:
                    found.exclude = True
    built.counts["sub-regions"] = len(subs)
    return built
