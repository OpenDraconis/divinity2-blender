import re

USER_PROP = "UserPropBuffer"

_LEVEL = re.compile(r"NiBoneLOD#\w+#(\d+)#")

NEAREST = 0

HIDDEN = "NiHide"

CULLED = 0x1


def child_nodes(node) -> list:
    return [c for c in (getattr(node, "children", ()) or []) if c is not None]


def _user_prop(shape) -> str:
    for extra in getattr(shape, "extra_data_list", None) or ():
        if extra is None:
            continue
        if str(getattr(extra, "name", "")) == USER_PROP:
            return str(getattr(extra, "string_data", ""))
    return ""


def level_of(shape) -> int | None:
    match = _LEVEL.search(_user_prop(shape))
    return int(match.group(1)) if match else None


def is_hidden(shape) -> bool:
    return any(
        line.strip().rstrip("#") == HIDDEN
        for line in _user_prop(shape).splitlines()
    )


def lod_children(node):
    children = child_nodes(node)
    if not children:
        return None, []
    data = getattr(node, "lod_level_data", None)
    ranges = getattr(data, "lod_levels", None) or []
    order = sorted(
        range(len(children)),
        key=lambda i: float(ranges[i].near_extent) if i < len(ranges) else 1e9,
    )
    for i in order:
        if _holds_geometry(children[i]):
            return children[i], [c for j, c in enumerate(children) if j != i]
    return None, children


def _holds_geometry(node) -> bool:
    stack = [node]
    while stack:
        n = stack.pop()
        data = getattr(n, "data", None)
        if type(n).__name__ in ("NiTriShape", "NiTriStrips"):
            if data is not None and data.num_vertices:
                return True
        stack += child_nodes(n)
    return False


def is_culled(node) -> bool:
    return bool(int(getattr(node, "flags", 0) or 0) & CULLED)


def is_nearest(shape) -> bool:
    level = level_of(shape)
    return level is None or level == NEAREST
