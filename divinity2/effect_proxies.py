import re

import numpy as np

from . import graph
from .nif import UNITS_PER_METRE, read_nif

EFFECTS = "Win32/Effects"

# ___real_43160000 in CRegionVisual::ParseRegionNode @6a3790 decomp
DEFAULT_CULLING_DISTANCE = 150.0


def _extra(node, name: str):
    for entry in getattr(node, "extra_data_list", ()) or ():
        if entry is not None and type(entry).__name__ == "NiStringExtraData" and str(entry.name) == name:
            return str(entry.string_data)
    return None


# DivTools::CGBTools::GetExtraDataValue @108ab20 decomp
def _value(buffer: str, key: str) -> str:
    at = buffer.find(key)
    if at < 0:
        return ""
    found = re.match(r'[^"]*"([^"]*)"', buffer[at:])
    return found.group(1) if found else ""


# CRegionVisual::ParseRegionNode @6a3790 decomp
def _proxy(node, world: np.ndarray, scale: float):
    if _extra(node, "effectproxy") != "yes":
        return None
    buffer = _extra(node, "UserPropBuffer")
    file = _value(buffer, "EffectFile") if buffer is not None else ""
    if not file:
        return None
    culling = _value(buffer, "CullingDistance")
    stem = file.split(".", 1)[0].replace("\\", "/")
    return {
        "name": str(node.name),
        "item": f"{EFFECTS}/{stem}.item",
        "culling_distance": float(culling) if culling else DEFAULT_CULLING_DISTANCE,
        "position": [float(v) / UNITS_PER_METRE for v in world[:3, 3]],
        "basis": [[float(v) for v in row] for row in (world[:3, :3] / scale).T],
    }


def proxies(root) -> list:
    found, stack = [], [(root, np.eye(4), 1.0)]
    while stack:
        node, above, scale_above = stack.pop()
        world = above @ graph.matrix_of(node)
        scale = scale_above * float(node.scale)
        made = _proxy(node, world, scale)
        if made is not None:
            found.append(made)
        stack += [(c, world, scale) for c in reversed(getattr(node, "children", ()) or ()) if c is not None]
    return found


def read(model_path) -> list:
    return proxies(read_nif(model_path).roots[0])
