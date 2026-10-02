from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import docs

WORLD = Path("World")

WORLD_REGIONS = Path("Worldregions.xml")

SCENERY_PROTOTYPES = "rpgstats_sceneryprototypes.xml"
SCENERY_ITEM = "sceneryitem"

SCENERY_ROOT = Path("Win32") / "Scenery"
ITEM_ROOT = Path("Win32") / "Items"
CHARACTER_ROOT = Path("Win32") / "Characters" / "Templates"

LIGHT_SETTINGS = "lightsettings.xml"

AREA = "PolyArea"

WATER = "waterplanedata_v2.xml"

WATER_FIELDS = ("shininess", "wavestrength", "wavesize", "wavespeed",
                "fresneloffset", "lodstrength", "lodstepsize", "sunstrength",
                "texscale", "fogmodifier", "alphamodifier", "vertexwavestrength",
                "foamstrength")

WATER_DEFAULTS = {
    "type": "0", "fogmodifier": 5.0, "alphamodifier": 15.0, "wavestrength": 0.1,
    "wavesize": 0.5, "shininess": 512.0, "sunstrength": 2.0, "texscale": 1.0,
    "wavespeed": 3.0, "fresneloffset": 0.2, "lodstrength": 2.0, "lodstepsize": 5.0,
    "vertexwavestrength": 0.0, "foamstrength": 0.0,
    "colours": [(0.35, 0.35, 0.35), (0.09, 0.23, 0.08)],
}


@dataclass
class Placed:
    kind: str
    uuid: str
    name: str
    position: tuple
    basis: np.ndarray | None = None
    scale: float = 1.0
    model: Path | None = None
    fields: dict = field(default_factory=dict)
    polygon: list = field(default_factory=list)
    height: tuple | None = None


@dataclass
class Region:
    name: str
    sub: str
    placed: list = field(default_factory=list)
    statics: Path | None = None
    vegetation: Path | None = None
    missing: dict = field(default_factory=dict)
    unread: dict = field(default_factory=dict)

    def of(self, kind: str) -> list:
        return [p for p in self.placed if p.kind == kind]


def _attrs(node) -> dict:
    return node.named()


def record(node, skip=(), prefix: str = "") -> dict:
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


_read = docs.read


@lru_cache(maxsize=4)
def files_under(root: Path, under: str, suffix: str) -> dict:
    base = Path(root) / under
    if not base.is_dir():
        return {}
    return {
        str(p.relative_to(base).with_suffix("")).lower().replace("\\", "/"): p
        for p in base.rglob(f"*{suffix}")
    }


@lru_cache(maxsize=4)
def _scenery_models(root: Path) -> dict:
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
    out, taken = [], set()
    for table in _episode_files(Path(root), where):
        doc = _read(table)
        if doc is None:
            continue
        for node in doc.find_all(element):
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
    return docs.glob(root, f"episodes/*/{where}/*.xml")


def _triggers(root: Path, region: str, sub: str) -> list:
    return [placed for _, where, placed in _all_triggers(root) if where == (region, sub)]


def teleport_targets(root) -> dict:
    out = {}
    for episode, (region, sub), placed in _all_triggers(root):
        if placed.fields["shape"] in ("Point", "Orientation"):
            out.setdefault(episode, {})[placed.uuid] = {
                "region": region, "sub": sub, "shape": placed.fields["shape"],
                "position": list(placed.position),
                "basis": None if placed.basis is None else np.asarray(placed.basis).tolist()}
    return out


def _all_triggers(root: Path) -> list:
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
    return node.name[len("Trigger_"):] if node.name.startswith("Trigger_") else node.name


def time_settings(root, region: str, sub: str) -> list:
    doc = _read(folder(root, region, sub) / LIGHT_SETTINGS)
    return [n.get("name") for n in doc.find_all("lightsetting")] if doc else []


def time_setting(root, region: str, sub: str, wanted: str = "") -> str:
    listed = time_settings(root, region, sub)
    wanted = wanted or time_of(root, region)
    if wanted in listed:
        return wanted
    return listed[0] if listed else ""


def _time_at(model_path, time: str = "") -> str:
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
    return {**WATER_DEFAULTS, **styles.get(plane, {})}


def sun_basis(angle_y: float, angle_z: float) -> np.ndarray:
    cy, sy = np.cos(angle_y), np.sin(angle_y)
    cz, sz = np.cos(angle_z), np.sin(angle_z)
    return np.array([[cz, sz, 0], [-sz, cz, 0], [0, 0, 1]]) @ \
        np.array([[cy, 0, -sy], [0, 1, 0], [sy, 0, cy]])


@lru_cache(maxsize=4)
def _tree_models(root: Path) -> dict:
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


def _declared(root) -> dict:
    doc = _read(Path(root) / WORLD_REGIONS)
    return {} if doc is None else {
        node.get("name"): ["Main"] + [c.get("name") for c in node.children if c.is_a("subregion")]
        for node in doc.find_all("region")}


def regions(root) -> list:
    return sorted(_declared(root))


def subregions(root, region: str) -> list:
    return _declared(root).get(region, [])


def time_of(root, region: str) -> str:
    doc = _read(Path(root) / WORLD_REGIONS)
    for node in (doc.find_all("region") if doc else ()):
        if node.get("name") == region:
            return node.get("timesetting", "")
    return ""


def read(root, region: str, sub: str = "Main", time: str = "") -> Region:
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
