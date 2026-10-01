"""Reading a model's Gamebryo particle systems, whole, as plain data.

`graph.walk` yields geometry only, and a `NiParticleSystem` is not geometry:
it is an emitter, a list of modifiers and a chain of controllers that the
engine runs every frame (`NiPSysUpdateCtlr::Update` @5b68d0 ->
`NiParticleSystem::Do_UpdateSystem` @5cea50). The port runs them itself, so
this hands over every field of every block the system reaches, by `nif.xml`'s
names, and leaves the rules to the consumer.

What a block reference becomes:

- the system itself: `"self"`;
- any other `NiAVObject` (the emitter object, the gravity or drag object, a
  collider's plane, a mesh emitter's hidden shape): `{"node": path, "world":
  4x4}`, the node's transform in the model's space in metres, the way
  `blender.importer` places a shape (`world` times the tree's factor); a
  triangle shape also carries its `vertices`, `normals` and `triangles`, in
  its own space, because a mesh emitter picks its points on them
  (`NiPSysMeshEmitter::EmitFromFace` @5bf390);
- any other block (interpolators, key data, the particle data, the collider
  chain): its own fields, the same way.

Which systems the engine builds is decided as for geometry: a culled subtree
is not built (`lod.is_culled`). A system is kept whatever its own flags say:
a `WaterSplash` system is culled by `CheckWaterSplashEffect` @6cbe40 and drawn
again as a `WaterSplashTriShape`, which the consumer decides from `markers`.
"""

import re

import numpy as np

from . import graph, lod
from . import material as dv2_material

#: The two block types that are a particle system (`nif.xml`).
SYSTEMS = ("NiParticleSystem", "NiMeshParticleSystem")

#: The Larian markers read from a system's or its parent's `UserPropBuffer`:
#: `CheckWaterSplashProperty` @6cbde0, `HasOrientationEffectProperty` @6cbb70,
#: both `ContainsNoCase`, and `CheckRefractionEffect` @6cbd20.
MARKERS = ("WaterSplash", "OrientationEffect", "Refraction")


#: Fields the record leaves out: the controller chain is a list of its own
#: (`describe`), so a controller does not carry the rest of it again.
SKIP = ("next_controller",)


def walk(root):
    """Every particle system under `root` the engine builds, with where it hangs.

    Yields `(system, world, path, parent, state)`: the block, its transform in
    the file's units, its node path, the node above it and its property state,
    resolved the way `graph.walk` resolves a shape's.
    """
    stack = [(root, np.eye(4), "", None, {})]
    while stack:
        node, parent_world, above, parent, inherited = stack.pop()
        if lod.is_culled(node) and type(node).__name__ not in SYSTEMS:
            continue
        world = parent_world @ graph.matrix_of(node)
        state = {**inherited, **graph._properties(node)}
        path = f"{above}/{node.name}" if above else str(node.name)
        if type(node).__name__ in SYSTEMS:
            yield node, world, path, parent, state
            continue
        for child in reversed(lod.child_nodes(node)):
            stack.append((child, world, path, node, state))


def _nodes(root):
    """Every `NiAVObject` under `root`, culled or not, by identity: `(path, world)`."""
    out = {}
    stack = [(root, np.eye(4), "")]
    while stack:
        node, parent_world, above = stack.pop()
        world = parent_world @ graph.matrix_of(node)
        path = f"{above}/{node.name}" if above else str(node.name)
        out[id(node)] = (path, world, node)
        for child in lod.child_nodes(node):
            stack.append((child, world, path))
    return out


def _prop(props: str, key: str) -> str | None:
    """`DivTools::CGBTools::GetExtraDataValue` @108ab20: the first quoted string
    after `key` in the buffer."""
    found = re.search(re.escape(key) + r'[^"]*"([^"]*)"', props)
    return found.group(1) if found else None


def _refraction(props: str) -> dict | None:
    """`CheckRefractionProperty` @6cbbc0: a `RefractionEffect` buffer names the
    normal map and the power across and down, each 30 when absent. The screen
    scaling it applies after (`/800`, `/600`) is left to the consumer."""
    if "refractioneffect" not in props.lower():
        return None
    power = []
    for key in ("RefractionPowerW", "RefractionPowerH"):
        try:
            power.append(float(_prop(props, key)))
        except (TypeError, ValueError):
            power.append(30.0)
    return {"normal_map": _prop(props, "NormalMap"), "power": power}


def _splash(markers: list) -> dict | None:
    """`CheckWaterSplashEffect` @6cbe40 hands `WaterSplashTriShape` an empty
    config, so `SetupShaderMaps` @116a0b0 always falls back to the normal map
    `FX_WaterSplash_A_NM` in shader slot 1."""
    return {"normal_map": "FX_WaterSplash_A_NM"} if "WaterSplash" in markers else None


def _user_props(*nodes) -> str:
    return "\n".join(str(e.string_data) for n in nodes if n is not None
                     for e in (getattr(n, "extra_data_list", ()) or ())
                     if e is not None and type(e).__name__ == "NiStringExtraData"
                     and str(e.name) == "UserPropBuffer")


class _Record:
    """The generic serialiser: one block or struct to plain data."""

    def __init__(self, system, nodes: dict, factor: float):
        self.system = system
        self.nodes = nodes
        self.factor = factor
        self.open = set()

    def node(self, block):
        path, world, _ = self.nodes[id(block)]
        out = {"node": path, "world": _metres(world, self.factor)}
        data = getattr(block, "data", None)
        if type(block).__name__ in graph.SHAPES and data is not None:
            out["vertices"] = [[v.x, v.y, v.z] for v in data.vertices]
            out["normals"] = [[v.x, v.y, v.z] for v in data.normals] if data.has_normals else []
            out["triangles"] = [[t.v_1, t.v_2, t.v_3] for t in data.triangles]
        return out

    def value(self, v):
        if v is None or isinstance(v, (bool, str)):
            return v
        if hasattr(v, "__members__") and hasattr(v, "_value"):
            return {"value": int(v), **{m: self.value(getattr(v, m)) for m in type(v).__members__}}
        if hasattr(v, "name") and isinstance(v, int) and type(v).__mro__[1].__name__ != "int":
            return str(v.name)
        if isinstance(v, (int, np.integer)):
            return int(v)
        if isinstance(v, (float, np.floating)):
            return float(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        if v is self.system:
            return "self"
        if id(v) in self.nodes:
            return self.node(v)
        if isinstance(v, (list, tuple)):
            return [self.value(i) for i in v]
        if hasattr(type(v), "_get_filtered_attribute_list"):
            return self.block(v)
        return str(v)

    def block(self, b):
        if id(b) in self.open:
            return {"type": type(b).__name__, "cycle": True}
        self.open.add(id(b))
        out = {"type": type(b).__name__}
        for field in type(b)._get_filtered_attribute_list(b):
            if field[0] not in SKIP:
                out[field[0]] = self.value(getattr(b, field[0], None))
        self.open.discard(id(b))
        return out


def _metres(world, factor: float) -> list:
    """A transform in the file's units as the model's space in metres: the
    factor on every row but the last, as `blender.scene.build_mesh` scales a
    shape's vertices and its translation."""
    m = np.array(world, dtype=np.float64)
    m[:3] *= factor
    return m.tolist()


def describe(system, world, path: str, parent, state: dict, root, factor: float,
             pixel_format=lambda name: None) -> dict:
    """One particle system as plain data.

    `world` is its transform in the file's units and `factor` the tree's game
    units to metres (`blender.importer._factor`). `material` is what
    `material.describe` makes of the system's resolved property state (`walk`), and
    `zbuffer` its `NiZBufferProperty` (absent: test and write on, LESS_EQUAL,
    `NiZBufferProperty::NiZBufferProperty`). `refraction` is the Larian
    refraction config (`_refraction`) or None, `splash` the water splash's
    (`_splash`) or None.
    """
    nodes = _nodes(root)
    record = _Record(system, nodes, factor)
    z = state.get("NiZBufferProperty")
    props = _user_props(system, parent)
    controllers = []
    c = system.controller
    while c is not None:
        controllers.append(record.block(c))
        c = c.next_controller
    return {
        "name": str(system.name),
        "path": path,
        "type": type(system).__name__,
        "world": _metres(world, factor),
        "factor": factor,
        "world_space": bool(getattr(system, "world_space", True)),
        "flags": int(system.flags),
        "markers": (markers := [m for m in MARKERS if m.lower() in props.lower()]),
        "user_props": props,
        "refraction": _refraction(props),
        "splash": _splash(markers),
        "material": dv2_material.describe(state, system, system.data, pixel_format),
        "zbuffer": {"test": bool(z.flags.z_buffer_test), "write": bool(z.flags.z_buffer_write),
                    "function": str(z.flags.test_func.name)} if z is not None
                   else {"test": True, "write": True, "function": "TEST_LESS_EQUAL"},
        "data": record.block(system.data) if system.data is not None else None,
        "modifiers": [record.block(m) for m in system.modifiers if m is not None],
        "controllers": controllers,
    }
