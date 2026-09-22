"""A whole region: what stands in it, who walks it, and what lights it.

A region is a folder under `World/`, and what it holds is spread over three
places. The ground and the built geometry are NIFs beside it; the props, the
lights and the trees are binary XML beside those; the characters, the items
and the triggers live with the episode, not with the region, and name their
region in an attribute. **The attribute places them, not the folder**:
Banditcamp's humans are in `Episodes/Episode_1_Extended/Characters/
BanditCamp_characterfile.xml`, outside `Regions/Banditcamp`, and a reader that
only looked there found 47 of the 99 characters and 169 of the 199 items. The
engine loads that file because `Characters/gamestats_global_characters.xml`
includes it, beside the region's own `Regions/<r>/Characters/
gamestats_characters.xml`; every character and item file Banditcamp's reads
touch is included by one of the two. Install-wide one file is in a folder and
in no include list, `Regions/BrokenValley_2/Items/
bv_mindread_2_cellar_itemfile.xml` -- measured 2026-09-16 -- so a reader of
BrokenValley_2 should follow the includes instead of the folders.

| what | file | what names its model |
|---|---|---|
| scenery | `World/<r>/<sub>/scenery.xml` | `rpgstats_sceneryprototypes.xml` |
| characters | `Episodes/<e>/**/Characters/*.xml` | `rpgstats_characterprototypes_visual.xml` |
| items | `Episodes/<e>/**/Items/*.xml` | `rpgstats_itemprototypes.xml` -> `..._itemvisualprototypes.xml` |
| triggers | `Episodes/<e>/Triggers/*.xml` | nothing: a trigger is a volume |
| lights | `World/<r>/<sub>/Lights/<time>/lights.xml` | nothing |
| trees | `World/<r>/<sub>/trees.xml` | `forest-settings.xml`, and see below |
| vegetation | `World/<r>/<sub>/Vegetation.nif` | itself |

**Every placement is stored the same way**: an `NiPoint3` child for the
position and an `NiMatrix3` child for the basis, in that order, and both in
metres. The engine's own readers say so --
`CRpgStats_V2_Scenery::LoadXML`, `CRpgStats_V2_Character::LoadXML`,
`CRpgStats_V2_Item::LoadXML` and `CGameLogic_Tree::LoadXML` all take
`children[0]` as the position and `children[1]` as the orientation. The
binary stream stores children in reverse, and the shared reader undoes that
once, for everything; see `divinity2.docs`.

**A trigger is a prism or a point.** `Trigger_area` holds a `PolyArea` with
`Top` and `Bottom` and a ring of `AreaPoint`s at the bottom height, so the
volume is that polygon extruded upward. `Trigger_Point`, `Trigger_Orientation`
and their named cousins hold a single position, with a basis when the thing
has a facing. The `Type` number is not decoded here: the child element is its
own label and needs no table.

**A tree has no mesh.** `model="BoxWood"` names a `CTreeModel` in
`forest-settings.xml`, whose `model` is a SpeedTree `.spt` -- a procedural
definition, not geometry. The whole SpeedTree runtime is linked into the game
(`CSpeedTreeRT::LoadTree`, `CTreeModel::SetupBranchGeometry`) and grows the
tree at load. So a tree arrives as a marker with its name, its position and
its size, and the size is exact:
`CGameLogic_Tree::PreparePhysicsData` computes it as
`rescaled.y * CTreeModel.size`, where `CGameLogic_Tree::UpdateInstanceData`
sets `rescaled.y = (1 - v) + instance.y * v * 2` for `v = treesizevariation`.
`instance.x` is the tree's rotation and `instance.z` its colour variation,
both fed to the SpeedTree shader; neither is converted here.

**Vegetation is scattered by the engine, not stored.** `Vegetation.nif` is the
region's library of grass and undergrowth meshes, one `NiNode` per source
file, and `vegetationtemplatedata.xml` names them again with their textures.
Where each blade stands is generated at load from a seed and a per-cell mask
(`Vegetation/VM_<x>_<y>.tga`, the names
`CVegetationGridManager::GenerateVegetationGridEntryDescriptors` scans for).
`divinity2.vegetation` generates the same field (`docs/vegetation.md`).
"""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import docs

#: Where the placement files live, relative to the install.
WORLD = Path("World")

#: The table that says which time of day each region is loaded at.
WORLD_REGIONS = Path("Worldregions.xml")

#: The scenery prototype table, beside the install root, and the element in
#: it that names a model. The placement calls the thing `Scenery`; the
#: prototype that describes it is a `sceneryitem`.
SCENERY_PROTOTYPES = "rpgstats_sceneryprototypes.xml"
SCENERY_ITEM = "sceneryitem"

#: `Assets\...` in a prototype path *replaces* onto this folder, it does not
#: nest under it.
SCENERY_ROOT = Path("Win32") / "Scenery"
ITEM_ROOT = Path("Win32") / "Items"
CHARACTER_ROOT = Path("Win32") / "Characters" / "Templates"

#: A sub-region's time settings: the `lightsetting` entries of its own file,
#: in file order (`CGameLogic_SubRegion::LoadLightSettings`), each naming a
#: folder under `Lights/`.
LIGHT_SETTINGS = "lightsettings.xml"

#: The one node that carries a trigger's polygon.
AREA = "PolyArea"

#: The water planes' style table, beside `lights.xml` in the same time folder.
WATER = "waterplanedata_v2.xml"

#: `WaterPlaneData`'s numbers, typed. Every other attribute the entry has is
#: carried too, as the string the file holds.
WATER_FIELDS = ("shininess", "wavestrength", "wavesize", "wavespeed",
                "fresneloffset", "lodstrength", "lodstepsize", "sunstrength",
                "texscale", "fogmodifier", "alphamodifier", "vertexwavestrength",
                "foamstrength")

#: What a water plane holds when no entry of its own name was loaded:
#: `CWaterPlaneData::CWaterPlaneData`, floats read out of the exe. The two colours
#: are `WaterColor` and `FogColor`, in the order an entry lists its `NiColor`s.
WATER_DEFAULTS = {
    "type": "0", "fogmodifier": 5.0, "alphamodifier": 15.0, "wavestrength": 0.1,
    "wavesize": 0.5, "shininess": 512.0, "sunstrength": 2.0, "texscale": 1.0,
    "wavespeed": 3.0, "fresneloffset": 0.2, "lodstrength": 2.0, "lodstepsize": 5.0,
    "vertexwavestrength": 0.0, "foamstrength": 0.0,
    "colours": [(0.35, 0.35, 0.35), (0.09, 0.23, 0.08)],
}


@dataclass
class Placed:
    """One thing standing in a region."""

    kind: str                       #: scenery, character, item, trigger, light, tree
    uuid: str                       #: the name the file gives it
    name: str                       #: what to call it in the scene
    position: tuple                 #: metres, region space
    basis: np.ndarray | None = None  #: 3x3 rotation, rows as the engine reads them
    scale: float = 1.0
    model: Path | None = None       #: the file holding its mesh, when it has one
    fields: dict = field(default_factory=dict)  #: everything else the file said
    polygon: list = field(default_factory=list)  #: a trigger's ring, in metres
    height: tuple | None = None     #: a trigger prism's (bottom, top)


@dataclass
class Region:
    name: str
    sub: str
    placed: list = field(default_factory=list)
    statics: Path | None = None      #: `StaticMeshes.nif`, the built geometry
    vegetation: Path | None = None   #: `Vegetation.nif`, the library
    missing: dict = field(default_factory=dict)  #: kind -> how many found no model
    unread: dict = field(default_factory=dict)   #: path -> why it would not parse

    def of(self, kind: str) -> list:
        return [p for p in self.placed if p.kind == kind]


# ---------------------------------------------------------------- the basics

def _attrs(node) -> dict:
    """Everything the file said about this node, by name.

    The whole record, not a chosen subset: a field that is useless to the
    add-on is the one the port needs later, and the file already holds it. A
    name divinity2-lib has not recovered is written down as its hash
    rather than dropped, so a gap shows up in the table instead of vanishing.
    """
    return node.named()


def record(node, skip=(), prefix: str = "") -> dict:
    """Everything under a node, not only its own attributes.

    A descendant's attribute is written `child.attr`, and a child name that
    repeats takes its place among its namesakes, `NiColor[1].r`. `skip` names
    children already carried another way -- the position and the basis, which
    arrive as numbers. A light keeps its colour two levels down and a scenery
    prop its type info one level down; `_attrs` alone dropped both.
    """
    out = {prefix + k: v for k, v in _attrs(node).items()}
    if node.text:
        out[prefix + "#text"] = node.text
    names = [c.name for c in node.children]
    seen = {}
    for child, name in zip(node.children, names):
        index = seen.get(name, 0)
        seen[name] = index + 1
        if any(child is s for s in skip):
            continue
        key = name if names.count(name) == 1 else f"{name}[{index}]"
        out.update(record(child, (), f"{prefix}{key}."))
    return out


def _point(node) -> tuple:
    return tuple(float(node.get(k, 0.0)) for k in "xyz")


def _basis(node) -> np.ndarray:
    return np.array([_point(row) for row in node.children], dtype=float)


def placement(node):
    """(position, basis, the children they came from) of a placement."""
    position, basis, used = (0.0, 0.0, 0.0), None, []
    for child in node.children:
        if child.is_a("NiPoint3") and not any(u.is_a("NiPoint3") for u in used):
            position = _point(child)
            used.append(child)
        elif child.is_a("NiMatrix3") and basis is None:
            basis = _basis(child)
            used.append(child)
    return position, basis, used


def folder(root, region: str, sub: str) -> Path:
    here = Path(root) / WORLD / region
    return here / sub if sub == "Main" else here / "Subregions" / sub


#: What could not be read, and why: `divinity2.docs.UNREAD`.
_read = docs.read


@lru_cache(maxsize=4)
def files_under(root: Path, under: str, suffix: str) -> dict:
    """Every file of one kind, keyed by its lower-cased relative path.

    Larian's own tables disagree with the disk about case, and a Linux
    filesystem does not forgive that.
    """
    base = Path(root) / under
    if not base.is_dir():
        return {}
    return {
        str(p.relative_to(base).with_suffix("")).lower().replace("\\", "/"): p
        for p in base.rglob(f"*{suffix}")
    }


# ------------------------------------------------------------- model lookups

@lru_cache(maxsize=4)
def _scenery_models(root: Path) -> dict:
    """Scenery prototype UUID -> the `.item` on disk."""
    doc = _read(Path(root) / SCENERY_PROTOTYPES)
    if doc is None:
        return {}
    files = files_under(Path(root), str(SCENERY_ROOT), ".item")
    out = {}
    for node in doc.find_all(SCENERY_ITEM):
        uuid, named = node.get("UUID"), node.get("NIFFile")
        if not uuid or not named:
            continue
        parts = named.replace("\\", "/").split("/")
        if parts and parts[0].lower() == "assets":
            parts = parts[1:]
        found = files.get("/".join(parts).lower())
        if found:
            out[uuid] = found
    return out


@lru_cache(maxsize=4)
def character_models(root: Path) -> dict:
    """Visual prototype UUID -> the `.cat` on disk.

    A `Visual` gives `PrototypeName` -- the family, `SkeletonHuman` -- and
    `TemplateName`, which is the template inside it. The template is also the
    name of a file under `Characters/Templates`, for 300 of the game's 302
    visuals; the two that are not are unused Froblin variants.
    """
    root = Path(root)
    files = files_under(root, str(CHARACTER_ROOT), ".cat")
    out = {}
    for table in docs.glob(root, "episodes/*/rpgstats_characterprototypes_visual.xml"):
        doc = _read(table)
        if doc is None:
            continue
        for node in doc.find_all("Visual"):
            uuid = node.get("UUID")
            template = next((c.text for c in node.children if c.is_a("TemplateName")), "")
            found = files.get(template.lower())
            if uuid and found:
                out.setdefault(uuid, found)
    return out


@lru_cache(maxsize=4)
def _item_models(root: Path) -> dict:
    """Item prototype UUID -> the `.item` on disk.

    Two hops: an `item` names a `VisualUUID`, and that `itemvisual` names a
    `Folder` and a `NifFileName` under `Items`. 1,141 of 1,177 resolve; the
    rest are cutscene props the game does not ship.
    """
    root = Path(root)
    files = files_under(root, str(ITEM_ROOT), ".item")
    visuals = {}
    for table in docs.glob(root, "episodes/*/rpgstats_itemvisualprototypes.xml"):
        doc = _read(table)
        if doc is None:
            continue
        for node in doc.find_all("itemvisual"):
            key = f"{node.get('Folder', '')}/{node.get('NifFileName', '')}"
            found = files.get(key.replace("\\", "/").lower())
            if node.get("UUID") and found:
                visuals.setdefault(node.get("UUID"), found)

    out = {}
    for table in docs.glob(root, "episodes/*/rpgstats_itemprototypes.xml"):
        doc = _read(table)
        if doc is None:
            continue
        for node in doc.find_all("item"):
            found = visuals.get(node.get("VisualUUID", ""))
            if node.get("UUID") and found:
                out.setdefault(node.get("UUID"), found)
    return out


# ------------------------------------------------------------- the placements

def _scenery(root: Path, region: str, sub: str) -> list:
    doc = _read(folder(root, region, sub) / "scenery.xml")
    if doc is None:
        return []
    models = _scenery_models(Path(root))
    out = []
    for node in doc.find_all("Scenery"):
        position, basis, used = placement(node)
        proto = node.get("PrototypeUUID", "")
        out.append(Placed(
            kind="scenery",
            uuid=node.get("UUID", proto),
            name=proto or node.get("UUID", "scenery"),
            position=position,
            basis=basis,
            scale=float(node.get("Scale", 1.0) or 1.0),
            model=models.get(proto),
            fields={"prototype": proto, **record(node, used)},
        ))
    return out


def _from_episodes(root: Path, region: str, sub: str, where: str, element: str,
                   kind: str, models: dict, model_key: str) -> list:
    """Characters and items: same shape, different table.

    Every `<where>` folder of the episode, filtered on `RegionName` and
    `SubRegionName` -- the rule `_triggers` already used. A UUID that two files
    both place is placed once, from the first file in path order.
    """
    out, taken = [], set()
    for table in _episode_files(Path(root), where):
        doc = _read(table)
        if doc is None:
            continue
        for node in doc.find_all(element):
            # An `Item` without a position is not placed in the world -- it is
            # what something else is carrying, and the same files hold both.
            if node.get("RegionName") != region or node.get("SubRegionName") != sub:
                continue
            if not any(c.is_a("NiPoint3") for c in node.children):
                continue
            if node.get("UUID") and node.get("UUID") in taken:
                continue
            taken.add(node.get("UUID"))
            position, basis, used = placement(node)
            key = node.get(model_key, "")
            out.append(Placed(
                kind=kind,
                uuid=node.get("UUID", ""),
                name=node.get("UUID") or key or kind,
                position=position,
                basis=basis,
                model=models.get(key),
                fields=record(node, used),
            ))
    return out


def _episode_files(root: Path, where: str) -> list:
    """Every document in a `<where>` folder anywhere under an episode."""
    return docs.glob(root, f"episodes/*/{where}/*.xml")


def _triggers(root: Path, region: str, sub: str) -> list:
    return [placed for _, where, placed in _all_triggers(root) if where == (region, sub)]


def teleport_targets(root) -> dict:
    """Every trigger a teleport can land on, per episode, across the whole game.

    `CRpgStats_V2_Character::TeleportToTrigger` accepts only a `Point` or an
    `Orientation` trigger, and takes the region and sub-region from the trigger
    itself -- which may lie in a sub-region that is not loaded. So the runtime
    needs them all, not only the region's own: `{episode: {uuid: {region, sub,
    shape, position, basis}}}`, episode lower-cased.
    """
    out = {}
    for episode, (region, sub), placed in _all_triggers(root):
        if placed.fields["shape"] in ("Point", "Orientation"):
            out.setdefault(episode, {})[placed.uuid] = {
                "region": region, "sub": sub, "shape": placed.fields["shape"],
                "position": list(placed.position),
                "basis": None if placed.basis is None else np.asarray(placed.basis).tolist()}
    return out


def _all_triggers(root: Path) -> list:
    """`(episode, (region, sub), Placed)` for every trigger every episode places.
    Every one of the game's 6,026 `Trigger_base` names its `SubRegion` (measured)."""
    out = []
    for table in docs.glob(root, "episodes/*/triggers/*.xml"):
        episode = Path(table).relative_to(root).parts[1].lower()
        doc = _read(table)
        if doc is None:
            continue
        for node in doc.find_all("Trigger"):
            kind_number = node.get("Type")
            if kind_number is None or not node.children:
                continue
            inner = node.children[0]
            base = next((c for c in inner.children if c.is_a("Trigger_base")), None)
            if base is None:
                continue
            where = (base.get("Region"), base.get("SubRegion"))

            shape = next((c for c in inner.children
                          if not c.is_a("Trigger_base")), None)
            placed = Placed(
                kind="trigger",
                uuid=node.get("UUID", ""),
                name=node.get("UUID", "trigger"),
                position=(0.0, 0.0, 0.0),
                fields={**record(node),
                        **_attrs(base),
                        **(_attrs(shape) if shape is not None else {}),
                        "type": kind_number,
                        "shape": _label(shape) if shape is not None else "",
                        "active": base.get("Active", "1")},
            )
            if shape is not None:
                area = next(shape.find_all(AREA), None)
                if area is not None:
                    ring = [_point(p) for point in area.find_all("AreaPoint")
                            for p in point.children if p.is_a("NiPoint3")]
                    placed.polygon = ring
                    placed.height = (float(area.get("Bottom", 0.0)),
                                     float(area.get("Top", 0.0)))
                    if ring:
                        placed.position = tuple(
                            sum(p[k] for p in ring) / len(ring) for k in range(3))
                else:
                    placed.position, placed.basis, _ = placement(shape)
            out.append((episode, where, placed))
    return out


def _label(node) -> str:
    """A trigger's shape element, by its own name without the `Trigger_`.

    A list of six known shapes turned 743 of the game's 6,769 into "other"
    (`EffectArea`, `SoundArea`, ...)."""
    return node.name[len("Trigger_"):] if node.name.startswith("Trigger_") else node.name


def time_settings(root, region: str, sub: str) -> list:
    """The time settings a sub-region lists, in its own order."""
    doc = _read(folder(root, region, sub) / LIGHT_SETTINGS)
    return [n.get("name") for n in doc.find_all("lightsetting")] if doc else []


def time_setting(root, region: str, sub: str, wanted: str = "") -> str:
    """The time setting the engine loads a sub-region at.

    `CGameLogic_SubRegion::Load`: the one asked for if the sub-region lists it
    (`HasTimeSetting`), else the first one it lists, else none at all -- the
    sub-region then has no current time setting. What is asked for is the
    region's `timesetting` (`time_of`) unless `wanted` names one. Banditcamp
    asks for `Dawn`; `Main` lists it, the cave lists only `Day`.
    """
    listed = time_settings(root, region, sub)
    wanted = wanted or time_of(root, region)
    if wanted in listed:
        return wanted
    return listed[0] if listed else ""


def _time_at(model_path, time: str = "") -> str:
    """`time_setting` for the sub-region a model file lies in:
    `<root>/World/<region>/Main/...` or `<root>/World/<region>/Subregions/<sub>/...`."""
    parts = Path(model_path).parent.parts
    if WORLD.name not in parts:
        return ""
    at = len(parts) - 1 - parts[::-1].index(WORLD.name)
    root, region = Path(*parts[:at]), parts[at + 1]
    sub = parts[at + 2] if parts[at + 2] == "Main" else parts[at + 3]
    return time_setting(root, region, sub, time)


def _lights(root: Path, region: str, sub: str, time: str = "") -> list:
    here = folder(root, region, sub)
    time = time_setting(root, region, sub, time)
    if not time:
        return []
    doc = _read(here / "Lights" / time / "lights.xml")
    if doc is None:
        return []
    out, inside = [], []
    # `CSpotLight::LoadXML` takes exactly two children: an `NiTransform` and a
    # whole `point_light`, which `CPointLight::LoadXML` reads as its own. That
    # inner one is the spot, not a second light.
    for node in doc.find_all("spot_light"):
        out.append(_light(node, "spot"))
        inside += list(node.find_all("point_light"))
    for node in doc.find_all("point_light"):
        if not any(node is i for i in inside):
            out.append(_light(node, "point"))
    for node in doc.find_all("dir_light"):
        out.append(_light(node, "sun"))
    return out


def _light(node, shape: str) -> Placed:
    """One light, with the colour and dimmer its `GBLight` carries.

    A point light's position is the `translate` under its `GBLight`; a
    directional light has none, only two angles, and a spot light has an
    `NiTransform`. Both of the latter shine along `direction`, the **first
    column** of their basis: `NiDirectionalLight::UpdateWorldData` and
    `NiSpotLight::UpdateWorldData` copy `m_kWorldDir` out of the world
    rotation's column 0. For the sun that basis is `sun_basis`.
    """
    gb = next(node.find_all("GBLight"), None)
    position = (0.0, 0.0, 0.0)
    colour = (1.0, 1.0, 1.0)
    ambient = (0.0, 0.0, 0.0)
    dimmer = 1.0
    if gb is not None:
        dimmer = float(gb.get("dimmer", 1.0) or 1.0)
        for child in gb.children:
            if child.is_a("translate"):
                position = _point(child)
            elif child.is_a("diffuse_color"):
                colour = tuple(float(child.get(k, 1.0)) for k in "rgb")
            elif child.is_a("ambient_color"):
                ambient = tuple(float(child.get(k, 0.0)) for k in "rgb")

    derived = dict(shape=shape, dimmer=dimmer, colour=colour, ambient=ambient)
    point = next(node.find_all("point_light"), node)
    basis = None
    if shape == "sun":
        derived["angle_y"] = float(node.get("angle_y", 0.0) or 0.0)
        derived["angle_z"] = float(node.get("angle_z", 0.0) or 0.0)
        basis = sun_basis(derived["angle_y"], derived["angle_z"])
    else:
        derived["radius"] = float(point.get("m_fMaxAttenuationRadius", 1.0) or 1.0)
        derived["inner"] = float(point.get("m_fMinAttenuationRadius", 0.0) or 0.0)
    if shape == "spot":
        # The transform is the spot's own; its position agrees with the inner
        # light's `translate` in all 71 spot lights the install ships.
        transform = next(node.find_all("NiTransform"), None)
        if transform is not None:
            position, basis, _ = placement(transform)
        derived["fov"] = float(node.get("fov", 0.0) or 0.0)
    if basis is not None:
        derived["direction"] = [float(v) for v in np.asarray(basis)[:, 0]]
    derived["shadows"] = (next(node.find_all("light"), node).get("m_bCastShadows", "0"))
    name = point.get("Name") or node.get("Name", "")
    return Placed(kind="light", uuid=name, name=name or shape, position=position,
                  basis=basis, fields={**record(node), **derived})


def water_styles(model_path, time: str = "") -> dict:
    """The water plane styles a sub-region loads, keyed by the plane they are for.

    `waterplanedata_v2.xml` is a style table, **not** a placement. The planes
    themselves are geometry inside `StaticMeshes.nif`, marked
    `UserPropBuffer=WaterPlane`, which `CRegionVisual::ParseRegionNode` turns
    into `CWaterPlane`s. The engine reads the table from the folder of the time
    setting it loads at (`CRegionVisual::ApplyCurrentTimeSettings` ->
    `CWaterRenderer::UpdateTimeSettings`), merges it by name, and a later entry
    of the same name overwrites an earlier one (`CWaterPlaneDataMan::LoadXML`).

    Returns `{}` when that folder ships no such file: the engine then keeps
    what it had, which on a region's first load is `WATER_DEFAULTS`. Use
    `water_style` for what one plane ends up with.
    """
    if model_path is None:
        return {}
    found = Path(model_path).parent / "Lights" / _time_at(model_path, time) / WATER
    if not found.is_file():
        return {}
    doc = _read(found)
    if doc is None:
        return {}

    out = {}
    for node in doc.find_all("WaterPlaneData"):
        name = node.get("name")
        if not name:
            continue
        style = {"type": "0", **_attrs(node)}
        for key in WATER_FIELDS:
            try:
                style[key] = float(style[key])
            except (KeyError, ValueError):
                pass
        style["colours"] = [
            tuple(float(c.get(k, 0.0)) for k in "rgb") for c in node.children
        ]
        out[name] = style
    return out


def water_style(styles: dict, plane: str) -> dict:
    """One plane's style: its own entry, matched by exact name
    (`CWaterPlaneDataMan::AddWaterPlane`, `NiStringEqualsFunctor`), or the
    constructor's defaults. Banditcamp's `Pond_BC_01_A` has no entry of its
    own at any hour, so it is drawn with the defaults."""
    return {**WATER_DEFAULTS, **styles.get(plane, {})}


def sun_basis(angle_y: float, angle_z: float) -> np.ndarray:
    """The sun's rotation, entry for entry as the engine builds it.

    `CDirLight::UpdateVisual` copies `MakeZRotation(angle_z) * MakeYRotation(angle_y)`
    into the light. Gamebryo's `NiMatrix3::MakeZRotation` writes
    `[[c, s, 0], [-s, c, 0], [0, 0, 1]]` and `MakeYRotation`
    `[[c, 0, -s], [0, 1, 0], [s, 0, c]]` -- the transposes of the textbook
    matrices -- so the product is too, and its column 0, the way the light
    travels, is `(cy*cz, -cy*sz, sy)`. The textbook product used before gave
    the same height with x mirrored.
    """
    cy, sy = np.cos(angle_y), np.sin(angle_y)
    cz, sz = np.cos(angle_z), np.sin(angle_z)
    return np.array([[cz, sz, 0], [-sz, cz, 0], [0, 0, 1]]) @ \
        np.array([[cy, 0, -sy], [0, 1, 0], [sy, 0, cy]])


@lru_cache(maxsize=4)
def _tree_models(root: Path) -> dict:
    """`CTreeModel` name -> its size, variation and `.spt`, from `forest-settings.xml`."""
    doc = _read(Path(root) / "forest-settings.xml")
    if doc is None:
        return {}
    out = {}
    for node in doc.find_all("CTreeModel"):
        name = node.get("name")
        if name:
            out.setdefault(name, dict(
                spt=node.get("model", ""),
                size=float(node.get("size", 1.0) or 1.0),
                variation=float(node.get("treesizevariation", 0.0) or 0.0),
            ))
    return out


def _trees(root: Path, region: str, sub: str) -> list:
    doc = _read(folder(root, region, sub) / "trees.xml")
    if doc is None:
        return []
    models = _tree_models(Path(root))
    out = []
    for node in doc.find_all("CGameLogic_Tree"):
        points = [c for c in node.children if c.is_a("NiPoint3")]
        if len(points) < 2:
            continue
        position, instance = _point(points[0]), _point(points[1])
        model = node.get("model", "")
        described = models.get(model, {})
        variation = described.get("variation", 0.0)
        rescaled = (1.0 - variation) + instance[1] * variation * 2.0
        out.append(Placed(
            kind="tree",
            uuid=node.get("uuid", ""),
            name=f"{model} {node.get('uuid', '')}".strip(),
            position=position,
            scale=rescaled * described.get("size", 1.0),
            fields={**record(node, points[:1]),
                    **dict(model=model, spt=described.get("spt", ""),
                           variation_id=node.get("variation", "0"),
                           rotation=instance[0], colour=instance[2])},
        ))
    return out


# ------------------------------------------------------------------ the whole

def _declared(root) -> dict:
    """`CGameLogic_World::LoadXML`: every `region` of `Worldregions.xml`, each
    with an implicit `Main` and its `subregion` children, in file order."""
    doc = _read(Path(root) / WORLD_REGIONS)
    return {} if doc is None else {
        node.get("name"): ["Main"] + [c.get("name") for c in node.children if c.is_a("subregion")]
        for node in doc.find_all("region")}


def regions(root) -> list:
    """Every region the engine knows. Two of them (`DialogDesigner`,
    `FeatureScene`) ship no folder; reading one finds nothing, visibly."""
    return sorted(_declared(root))


def subregions(root, region: str) -> list:
    """`Main` first, then the region's sub-regions as `Worldregions.xml` lists them."""
    return _declared(root).get(region, [])


def time_of(root, region: str) -> str:
    """The time setting `Worldregions.xml` asks for a region, as written.

    Banditcamp asks for `Dawn`. Whether a sub-region has it is
    `time_setting`'s question, not this one's.
    """
    doc = _read(Path(root) / WORLD_REGIONS)
    for node in (doc.find_all("region") if doc else ()):
        if node.get("name") == region:
            return node.get("timesetting", "")
    return ""


def read(root, region: str, sub: str = "Main", time: str = "") -> Region:
    """Read one region into plain data. Knows nothing about Blender.

    `time` empty means the one `Worldregions.xml` gives the region.
    """
    root = Path(root)
    time = time_setting(root, region, sub, time)
    here = folder(root, region, sub)
    out = Region(name=region, sub=sub)

    out.placed += _scenery(root, region, sub)
    out.placed += _from_episodes(root, region, sub, "Characters", "Character",
                                 "character", character_models(root),
                                 "VisualPrototypeUUID")
    out.placed += _from_episodes(root, region, sub, "Items", "Item",
                                 "item", _item_models(root), "PrototypeUUID")
    out.placed += _triggers(root, region, sub)
    out.placed += _lights(root, region, sub, time)
    out.placed += _trees(root, region, sub)

    statics = here / "StaticMeshes.nif"
    out.statics = statics if statics.is_file() else None
    plants = here / "Vegetation.nif"
    out.vegetation = plants if plants.is_file() else None

    for kind in ("scenery", "character", "item"):
        want = out.of(kind)
        out.missing[kind] = sum(1 for p in want if p.model is None)
    out.unread = {str(path): why for path, why in docs.UNREAD.items()
                  if root in Path(path).parents}
    return out
