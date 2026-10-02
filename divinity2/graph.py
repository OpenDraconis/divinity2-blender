from dataclasses import dataclass, field

import numpy as np

from . import lod, terrain as dv2_terrain

SHAPES = ("NiTriShape", "NiTriStrips")

SWITCH = ("NiLODNode", "NiSwitchNode")

TEXTURING = "NiTexturingProperty"

PROXY = {
    "effectproxy": "an effect spawns here",
    "glowproxy": "a glow spawns here",
}

PHYSICS_PROXY = "PhysicsPROXY_"

ANONYMOUS = frozenset({
    "undefined geometry", "editable poly", "editable mesh", "polymesh",
    "shape", "mesh", "object", "", "scene root",
})


@dataclass
class Drawable:
    shape: object
    world: np.ndarray
    name: str
    path: str
    properties: dict
    hidden: bool = False
    reason: str = ""
    markers: dict = field(default_factory=dict)

    @property
    def data(self):
        return self.shape.data


def matrix_of(node) -> np.ndarray:
    r = node.rotation
    m = np.eye(4)
    m[:3, :3] = np.array((
        (r.m_11, r.m_12, r.m_13),
        (r.m_21, r.m_22, r.m_23),
        (r.m_31, r.m_32, r.m_33),
    )).T * float(node.scale)
    t = node.translation
    m[:3, 3] = (t.x, t.y, t.z)
    return m


def _markers(node) -> dict:
    return {
        str(e.name): str(e.string_data)
        for e in (getattr(node, "extra_data_list", ()) or [])
        if e is not None and type(e).__name__ == "NiStringExtraData"
    }


def _proxy(markers: dict, path: str):
    for name, why in PROXY.items():
        if markers.get(name) == "yes":
            return why
    if PHYSICS_PROXY in path:
        return "a collision hull"
    return None


def _properties(node) -> dict:
    return {
        type(p).__name__: p
        for p in (getattr(node, "properties", ()) or [])
        if p is not None
    }


def _named(node) -> str:
    name = str(getattr(node, "name", "") or "")
    return "" if name.strip().lower() in ANONYMOUS else name


def walk(root):
    stack = [(root, np.eye(4), {}, {}, "", False, "")]
    while stack:
        node, parent_world, inherited, marked, above, hidden, reason = stack.pop()

        if lod.is_culled(node):
            continue

        world = parent_world @ matrix_of(node)
        state = {**inherited, **_properties(node)}
        marks = {**marked, **_markers(node)}
        own = _named(node)
        path = f"{above}/{str(node.name)}" if above else str(node.name)

        kind = type(node).__name__
        if kind in SHAPES:
            data = getattr(node, "data", None)
            if data is None or not data.num_vertices:
                continue
            if TEXTURING not in state and dv2_terrain.patch_of(path) is None:
                continue
            why, invisible = reason, hidden
            proxy = _proxy(marks, path)
            if proxy is not None:
                why, invisible = proxy, True
            elif lod.is_hidden(node):
                why, invisible = "NiHide", True
            elif not lod.is_nearest(node):
                why, invisible = "a coarser level of detail", True
            yield Drawable(
                shape=node,
                world=world,
                name=own or _last_named(above) or str(node.name) or "shape",
                path=path,
                properties=state,
                hidden=invisible,
                reason=why,
                markers=marks,
            )
            continue

        children = lod.child_nodes(node)
        if kind in SWITCH:
            show, rest = lod.lod_children(node)
            for child in reversed(rest):
                stack.append((child, world, state, marks, path, True,
                              "a coarser level of detail"))
            children = [show] if show is not None else []

        for child in reversed(children):
            stack.append((child, world, state, marks, path, hidden, reason))


def _last_named(path: str) -> str:
    for part in reversed(path.split("/")):
        if part.strip().lower() not in ANONYMOUS:
            return part
    return ""
