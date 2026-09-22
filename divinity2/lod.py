"""Levels of detail.

A character ships every level of detail in the same file -- `Froblin_HI`,
`Froblin_MED`, `Froblin_LOW` -- and importing all three stacks three bodies in
the same place.

The game states a level of detail in two unrelated ways, and both have to be
read. A character uses a string in each shape's `UserPropBuffer`. Everything
built into a region uses `NiLODNode`, the standard Gamebryo container, whose
`NiRangeLODData` gives one camera-distance range per child.

Which is which is written down, so it need not be guessed from the name. Every
shape carries a `UserPropBuffer` string, and in it:

    NiBoneLOD#Skin#0#0#

    LODDistance = 0.0

The number after `Skin#` is the level, 0 being the one the game shows up close.
A shape with no such string is not part of a LOD group and is always shown.
"""

import re

USER_PROP = "UserPropBuffer"

_LEVEL = re.compile(r"NiBoneLOD#\w+#(\d+)#")

#: The level the game shows at close range.
NEAREST = 0

#: A line on its own in the buffer that means the shape is never drawn.
#: Seven shapes across the 324 templates carry it -- helper geometry that
#: would otherwise arrive as a visible lump.
HIDDEN = "NiHide"

#: Bit 0 of any `NiAVObject`'s flags: the node is culled and never drawn.
#: The engine is unambiguous -- `NiAVObject::GetAppCulled` is
#: `return this->m_uFlags & 1;` -- and Divinity II uses it for the physics
#: and destruction proxies it ships beside real geometry, such as the barrel's
#: `DESTRUCT_bone_02`, an untextured half-metre cube.
CULLED = 0x1


def child_nodes(node) -> list:
    """A node's children, without the empty slots a NIF list may hold."""
    return [c for c in (getattr(node, "children", ()) or []) if c is not None]


def _user_prop(shape) -> str:
    for extra in getattr(shape, "extra_data_list", None) or ():
        if extra is None:
            continue
        if str(getattr(extra, "name", "")) == USER_PROP:
            return str(getattr(extra, "string_data", ""))
    return ""


def level_of(shape) -> int | None:
    """The shape's LOD level, or None when it is not in a LOD group."""
    match = _LEVEL.search(_user_prop(shape))
    return int(match.group(1)) if match else None


def is_hidden(shape) -> bool:
    """Does the shape say it is never drawn?"""
    return any(
        line.strip().rstrip("#") == HIDDEN
        for line in _user_prop(shape).splitlines()
    )


#: The `NiLODNode` child to show is the nearest one that has geometry.
#:
#: The nearest child is usually empty. A region's built mesh holds its terrain
#: in `NiLODNode`s whose fine children are stub nodes, waiting for a streamed
#: file that the region may not ship: `Banditcamp` has `BC_terrain_A_low`
#: with the mesh in it and `_medium` and `_high` empty. Taking the nearest
#: child and stopping loses the ground of every region -- 1,055 of the 1,059
#: `NiLODNode`s in the game have an empty nearest child, and 1,044 of them
#: hold geometry in a coarser one.
def lod_children(node):
    """(the child to show, the children to hide) for one `NiLODNode`."""
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
    """Does the node's own flag say the engine never draws it?"""
    return bool(int(getattr(node, "flags", 0) or 0) & CULLED)


def is_nearest(shape) -> bool:
    """Should this shape be the visible one?"""
    level = level_of(shape)
    return level is None or level == NEAREST
