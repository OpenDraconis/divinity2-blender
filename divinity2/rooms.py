import numpy as np

from . import graph
from .nif import UNITS_PER_METRE, read_nif

ROOM, GROUP, PORTAL = "NiRoom", "NiRoomGroup", "NiPortal"


def _worlds(root) -> dict:
    found = {}
    stack = [(root, np.eye(4))]
    while stack:
        node, above = stack.pop()
        world = above @ graph.matrix_of(node)
        found[id(node)] = world
        for child in getattr(node, "children", ()) or ():
            if child is not None:
                stack.append((child, world))
    return found


def _of(root, kind: str) -> list:
    found, stack = [], [root]
    while stack:
        node = stack.pop()
        if type(node).__name__ == kind:
            found.append(node)
        stack += [c for c in (getattr(node, "children", ()) or ()) if c is not None]
    return found[::-1]


# NiRoom::UpdateWorldData @665b20 decomp
def _wall(plane, world: np.ndarray) -> list:
    normal = np.array((plane.normal.x, plane.normal.y, plane.normal.z))
    point = world @ np.append(normal * plane.constant, 1.0)
    turned = world[:3, :3] @ normal
    turned = turned / np.linalg.norm(turned)
    return [float(v) for v in turned] + [float(turned @ point[:3]) / UNITS_PER_METRE]


# NiPortal::UpdateWorldData @66a670 decomp
def _vertex(vertex, world: np.ndarray) -> list:
    return [float(v) / UNITS_PER_METRE for v in (world @ np.array((vertex.x, vertex.y, vertex.z, 1.0)))[:3]]


def table(root) -> dict:
    worlds = _worlds(root)
    groups = _of(root, GROUP)
    members = [r for g in groups for r in g.rooms]
    room_at = {id(r): i for i, r in enumerate(members)}
    portal_at = {}
    portals = []

    def portal(node):
        if id(node) not in portal_at:
            portal_at[id(node)] = len(portals)
            adjoiner = node.adjoiner
            portals.append({
                "name": str(node.name),
                "flags": int(node.portal_flags),
                "plane_count": int(node.plane_count),
                "vertices": [_vertex(v, worlds[id(node)]) for v in node.vertices],
                "adjoiner": None if adjoiner is None else
                {"room": room_at[id(adjoiner)]} if id(adjoiner) in room_at else {"node": str(adjoiner.name)},
            })
        return portal_at[id(node)]

    out_rooms = []
    for index, room in enumerate(members):
        out_rooms.append({
            "name": str(room.name),
            "group": next(i for i, g in enumerate(groups) if any(r is room for r in g.rooms)),
            "walls": [_wall(p, worlds[id(room)]) for p in room.wall_planes],
            "in_portals": [portal(p) for p in room.in_portals],
            "out_portals": [portal(p) for p in room.out_portals],
            "fixtures": [{"name": str(f.name), "type": type(f).__name__} for f in room.fixtures],
        })
    return {
        "groups": [{"name": str(g.name), "shell": None if g.shell is None else str(g.shell.name),
                    "rooms": [room_at[id(r)] for r in g.rooms]} for g in groups],
        "rooms": out_rooms,
        "portals": portals,
    }


def read(model_path) -> dict:
    return table(read_nif(model_path).roots[0])
