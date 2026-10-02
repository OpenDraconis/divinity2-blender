
import re

import numpy as np

from . import graph, lod
from . import material as dv2_material

SYSTEMS = ("NiParticleSystem", "NiMeshParticleSystem")

# CheckWaterSplashProperty @6cbde0 decomp, HasOrientationEffectProperty @6cbb70 decomp, CheckRefractionEffect @6cbd20 decomp
MARKERS = ("WaterSplash", "OrientationEffect", "Refraction")


SKIP = ("next_controller",)


def walk(root):
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


# CGBTools::GetExtraDataValue @108ab20 decomp
def _prop(props: str, key: str) -> str | None:
    found = re.search(re.escape(key) + r'[^"]*"([^"]*)"', props)
    return found.group(1) if found else None


# CheckRefractionProperty @6cbbc0 decomp
def _refraction(props: str) -> dict | None:
    if "refractioneffect" not in props.lower():
        return None
    power = []
    for key in ("RefractionPowerW", "RefractionPowerH"):
        try:
            power.append(float(_prop(props, key)))
        except (TypeError, ValueError):
            power.append(30.0)
    return {"normal_map": _prop(props, "NormalMap"), "power": power}


# CheckWaterSplashEffect @6cbe40 decomp, WaterSplashTriShape::SetupShaderMaps @116a0b0 decomp
def _splash(markers: list) -> dict | None:
    return {"normal_map": "FX_WaterSplash_A_NM"} if "WaterSplash" in markers else None


def _user_props(*nodes) -> str:
    return "\n".join(str(e.string_data) for n in nodes if n is not None
                     for e in (getattr(n, "extra_data_list", ()) or ())
                     if e is not None and type(e).__name__ == "NiStringExtraData"
                     and str(e.name) == "UserPropBuffer")


class _Record:
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
    m = np.array(world, dtype=np.float64)
    m[:3] *= factor
    return m.tolist()


def describe(system, world, path: str, parent, state: dict, root, factor: float,
             pixel_format=lambda name: None) -> dict:
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
