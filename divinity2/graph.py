"""Walking a Divinity II scene graph the way the engine does.

Everything drawable in this game hangs off a tree of `NiAVObject`s, and what
reaches the screen is decided on the way down, not at the leaf. Four things
accumulate:

**The transform.** Each node's translation, rotation and uniform scale
multiply onto the parent's.

**The property state.** Gamebryo attaches render state to a node, not to a
shape, and a shape inherits it from the nearest ancestor that carries one.
The engine builds that state in `NiAVObject::UpdateProperties`, which walks
*upward* through the parents, and merges each node's own list in
`NiAVObject::PushLocalProperties`: it copies the inherited state and writes
each local property into the one slot its type owns. **The nearest node with
a property of that type wins.** `NiPropertyState` has one slot each for
alpha, material, stencil, specular, shade, dither and fog.

In Divinity II this changes nothing for texturing, material, alpha, specular
or stencil -- measured over 795 drawn shapes, every one of those sits on the
shape itself. It is `NiVertexColorProperty` (79% inherited) and
`NiZBufferProperty` (97%) that live above. The walk does it properly anyway,
because doing it at the leaf is right by accident.

**Whether it is drawn.** Bit 0 of any node's flags is `APP_CULLED`, and the
engine is unambiguous: `NiAVObject::GetAppCulled` is
`return this->m_uFlags & 1;`. A culled node takes its whole subtree with it.

**Which child of a chooser.** `NiLODNode` is a `NiSwitchNode`, and one child
is active at a time. See `divinity2.lod`.

**Whether it has a texture.** A shape with no `NiTexturingProperty` is not
drawn, and this is not a guess about art: `CShadingTools::SetupStandardData`
tests `NiAVObject::GetProperty(8)` -- the texturing slot -- and where it is
missing it does `m_uFlags |= 1`, which is `APP_CULLED`. It does the same for
a shape whose model data carries no texture coordinates
(`m_usDataFlags & 0x3f`). Everything the game shades forward passes through
it: `CRegionVisual::ParseRegionNode`, `CStaticAssetDataManager` and the
terrain manager all call `SetupForwardShadingMaterial`, which calls it.

**The ground is the exception**, and the engine makes it too: a terrain patch
is textured from `Terrain.xml`, not from the model, and
`CTerrainPatchLOD::RecreateForwardShadingPropertyState` builds its property
state afterwards. So a shape inside a `Terrain_Patch_<n>` keeps its place
whatever the model says, and `divinity2.terrain.patch_of` is the same test
the rest of the add-on already uses for it.

In Banditcamp the rule catches eight shapes: the six effect proxies, which
the marker rule already caught, and the two untextured halves of
**`BC_ShadowHide_01`** -- the hundred-and-seventeen-metre block that stood in
the middle of every screenshot for a week. The other two shapes under that
same node do carry a texture, and they stay: one of them is the temple
floor.

**The markers the region reader looks for.** `CRegionVisual::ParseRegionNode`
reads a node's `NiStringExtraData` and turns some of them into something that
is not geometry at all: `effectproxy = yes` becomes a particle system loaded
from `Win32\\Effects\\` and the box that marked it is never drawn, `glowproxy`
becomes a `CGlowEffect`, and a node whose name starts `PhysicsPROXY_` is a
collision hull. Those markers are inherited by everything beneath, so the walk
carries them down with the rest.

The game uses six node types and no more: `NiNode`, `NiTriShape`,
`NiParticleSystem`, `NiLODNode`, `NiBillboardNode`, `NiSortAdjustNode`.
"""

from dataclasses import dataclass, field

import numpy as np

from . import lod, terrain as dv2_terrain

#: The two kinds of node that carry geometry.
SHAPES = ("NiTriShape", "NiTriStrips")

#: A chooser: one child is active, the rest are not drawn.
SWITCH = ("NiLODNode", "NiSwitchNode")

#: `NiProperty::GetType` for the texturing slot, which is the one
#: `CShadingTools::SetupStandardData` asks for by number.
TEXTURING = "NiTexturingProperty"

#: A marker, and what the engine builds from the node instead of a mesh.
#: From `CRegionVisual::ParseRegionNode`; `docs/regions.md` has the whole
#: table, of which these are the ones that replace the geometry outright.
PROXY = {
    "effectproxy": "an effect spawns here",
    "glowproxy": "a glow spawns here",
}

#: The one marker the engine reads off the name, not off extra data:
#: `NiString::Contains(name, "PhysicsPROXY_", 0, 13)`.
PHYSICS_PROXY = "PhysicsPROXY_"

#: Shape names the artists left on the export, which say nothing about what
#: the thing is. A quarter of the game's drawn shapes are called
#: `Undefined Geometry`; the name that means something is on the node above.
ANONYMOUS = frozenset({
    "undefined geometry", "editable poly", "editable mesh", "polymesh",
    "shape", "mesh", "object", "", "scene root",
})


@dataclass
class Drawable:
    """One shape that reaches the screen, with everything decided for it."""

    shape: object              #: the `NiTriShape` itself
    world: np.ndarray          #: its transform, in the file's own units
    name: str                  #: a name that says what it is
    path: str                  #: every node name above it, `a/b/c`
    properties: dict           #: the resolved state, by property class name
    hidden: bool = False       #: drawn by the game, but not at this distance
    reason: str = ""           #: why it is hidden
    markers: dict = field(default_factory=dict)  #: the node's string extra data

    @property
    def data(self):
        return self.shape.data


def matrix_of(node) -> np.ndarray:
    """One node's own transform.

    The rotation comes out of the file row-major and is transposed here, and
    the scale is uniform -- `NiAVObject` has one float, not a vector.
    """
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
    """Why the engine builds something other than a mesh here, or None."""
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
    """Every shape under `root`, in file order, with its state resolved.

    A shape the game never draws is not yielded at all: culled subtrees and
    the inactive children of a chooser are gone, because the engine does not
    build them. A shape the game draws *sometimes* -- a coarser level of
    detail -- is yielded with `hidden` set, because it is real geometry and a
    modder may want it.
    """
    stack = [(root, np.eye(4), {}, {}, "", False, "")]
    while stack:
        node, parent_world, inherited, marked, above, hidden, reason = stack.pop()

        if lod.is_culled(node):
            continue

        world = parent_world @ matrix_of(node)
        # PushLocalProperties: the inherited state, then this node's own on
        # top, one slot per property type.
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
                # `CShadingTools::SetupStandardData` culls it outright.
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
    """The deepest node name in `path` that says something."""
    for part in reversed(path.split("/")):
        if part.strip().lower() not in ANONYMOUS:
            return part
    return ""
