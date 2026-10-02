import re
from dataclasses import dataclass, field
from pathlib import Path

from . import docs, lod, nif

TEXTURE_DIR = "TerrainTextures"

DESCRIPTOR = "Terrain.xml"

_PATCH = re.compile(r"Terrain_Patch_(\d+)")


@dataclass
class Layer:
    texture: str
    normal: str
    tiling: float
    mask: Path | None
    channel: int
    composite: str = ""
    pass_index: int = 0
    record: dict = field(default_factory=dict)
    noise_composite: str = ""


@dataclass
class Patch:
    index: int
    megatexture: Path | None = None
    megatexture_normal: Path | None = None
    megatexture_composite: Path | None = None
    layers: list = field(default_factory=list)


def patch_of(path: str) -> int | None:
    match = _PATCH.search(path or "")
    return int(match.group(1)) if match else None


def _beside(model_path, named: str) -> Path | None:
    if not named:
        return None
    here = Path(model_path).parent / named.replace("\\", "/")
    for candidate in (here, here.with_suffix(".dds")):
        if candidate.is_file():
            return candidate
    return None


def patches(model_path) -> dict:
    root = docs.read(Path(model_path).parent / DESCRIPTOR)
    if root is None:
        return {}

    textures = list(root.find_all("Texture"))

    found = {}
    for node in root.find_all("TerrainPatch"):
        try:
            index = int(node.get("index"))
        except (TypeError, ValueError):
            continue
        patch = Patch(index=index)
        for mega in node.find_all("MegaTexture"):
            patch.megatexture = _beside(model_path, mega.get("path", ""))
            break
        for mega in node.find_all("MegaTexture_NM"):
            patch.megatexture_normal = _beside(model_path, mega.get("path", ""))
            break
        for mega in node.find_all("MegaTexture_CM"):
            patch.megatexture_composite = _beside(model_path, mega.get("path", ""))
            break
        for pass_index, alpha in enumerate(node.find_all("AlphaMap")):
            mask = _beside(model_path, alpha.get("path", ""))
            for entry in alpha.find_all("ID"):
                try:
                    layer_id = int(entry.get("layerID"))
                    channel = int(entry.get("MaskIndex"))
                except (TypeError, ValueError):
                    continue
                if not 0 <= layer_id < len(textures):
                    continue
                texture = textures[layer_id]
                patch.layers.append(Layer(
                    texture=texture.get("path", ""),
                    normal=texture.get("path_NM", ""),
                    tiling=float(texture.get("TextureTiling", "1") or 1),
                    mask=mask,
                    channel=channel,
                    composite=texture.get("path_CM", ""),
                    pass_index=pass_index,
                    record=dict(texture.attributes),
                ))
        patch.layers.sort(key=lambda lay: (lay.pass_index, lay.channel))
        for layer, composite in zip(patch.layers, noise_composites(patch.layers)):
            layer.noise_composite = composite
        found[index] = patch
    return found


def noise_composites(rows) -> list:
    def flag(row, name):
        return row.record.get(name) == "1"

    slots = [row.composite for row in rows
             if row.composite and any(flag(row, n) for n in ("UseGloss", "UseNoiseBlending", "UseParallax"))][:4]
    out, taken = [], 0
    for row in rows:
        if flag(row, "UseNoiseBlending") and taken < len(slots):
            out.append(slots[taken])
            taken += 1
        else:
            out.append("")
    return out


def descriptor(model_path) -> dict | None:
    root = docs.read(Path(model_path).parent / DESCRIPTOR)
    return None if root is None else docs.to_plain(root)


GRAPHIC_OPTIONS = {"RenderMethod": 1, "StaticAssetHighQuality": 1}


# CTerrainSplatRenderer::LoadXML @6ed7f0, CTerrainSplatRenderer::UpdateSplatDistance @6ec9d0 decomp
def splat(model_path, options=GRAPHIC_OPTIONS) -> dict:
    root = docs.read(Path(model_path).parent / DESCRIPTOR) if model_path else None
    node = next(iter(root.find_all("Terrain")), None) if root is not None else None

    def number(key, default):
        try:
            return float(int(node.get(key)))
        except (AttributeError, TypeError, ValueError):
            return default

    radius = number("splatdistance", 100.0)
    if options.get("StaticAssetHighQuality"):
        radius = 2000.0
    return {"radius": radius, "blend": number("splatblenddistance", 25.0)}


STREAM_DESCRIPTOR = Path("Meshes") / "Terrain" / "AssetDataDescriptors.xml"


def levels(model_path) -> dict:
    descriptor = Path(model_path).parent / STREAM_DESCRIPTOR
    found = {}
    for entry, name, index in manifest(descriptor):
        path = descriptor.parent / entry.get("base", "") / f"{index}.nif"
        if entry.get("base") and name and path.is_file():
            found[name] = path
    return found


def manifest(descriptor):
    root = docs.read(descriptor)
    for entry in (root.find_all("AssetDataDescriptor") if root is not None else ()):
        for level in entry.find_all("LODDistance"):
            try:
                index = int(level.get("index"))
            except (TypeError, ValueError):
                continue
            yield entry, level.get("name"), index


def graft(root, model_path) -> int:
    files = levels(model_path)
    if not files:
        return 0

    read = {}
    grafted = 0
    stack = [root]
    while stack:
        node = stack.pop()
        children = lod.child_nodes(node)
        stack += children
        name = str(getattr(node, "name", ""))
        if children or name not in files:
            continue
        grafted += fill_stub(node, name, files[name], read)
    return grafted


def fill_stub(stub, name: str, path: Path, read: dict) -> bool:
    streamed = _streamed(path, name, read)
    if streamed is None:
        return False
    stub.children = [streamed]
    stub.num_children = 1
    return True


def _streamed(path: Path, name: str, read: dict):
    if path not in read:
        try:
            read[path] = nif.read_nif(path).roots[0]
        except Exception:                                      # noqa: BLE001
            read[path] = None
    root = read[path]
    if root is None:
        return None

    stack = [root]
    while stack:
        node = stack.pop()
        if str(getattr(node, "name", "")) == name:
            return node
        stack += lod.child_nodes(node)
    return None
