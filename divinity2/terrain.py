"""The ground of a region, and the textures that are not in the model.

A region's terrain is inside its `StaticMeshes.nif`, under a node called
`[--WorldProcessedTerrain--]`, as one `NiLODNode` per patch. Three things
about it are unlike every other mesh in the game.

**Its levels of detail are streamed, not stored.** Each patch's `NiLODNode`
holds one level inline and an empty stub for every other one, and the geometry
those stubs are waiting for is in `Meshes/Terrain/Terrain_Patch_<i>/<n>.nif`.
`AssetDataDescriptors.xml` is the manifest that says which file fills which
stub -- see `levels` and `graft`. Without it the ground arrives at whatever
level the region happened to ship inline: Banditcamp at 9,992 vertices where
the game draws 36,883, and RiverTown_FF's flying islands as 24-vertex plates.
A region with no manifest is unaffected; `divinity2.lod` still picks the
finest level that actually holds geometry.

**It carries no `NiTexturingProperty`.** A terrain shape resolves only a
`NiMaterialProperty`, so a reader that asks the model what to draw gets
nothing and the ground arrives white.

**Its material is splatted, and `Terrain.xml` holds the whole recipe.**

```
<Terrain splatdistance="116" splatblenddistance="20">
  <TerrainPatch index="6">
    <AlphaHeap>
      <AlphaMap path="TerrainTextures\\AlphaMaps\\6_6_AlphaMap_1.tga">
        <Layers><ID layerID="6" MaskIndex="2" AlphaMapIndex="1"/> ... </Layers>
    <MegaTexture path="TerrainTextures\\MegaTexture_6.dds"/>
  <Textures>
    <Texture path="BV2_Moss_A.dds" path_NM="..." TextureTiling="50" ID="6"/>
```

One `Texture` per `ID` gives the layer's picture and how often it tiles across
the patch. One channel of one alpha map -- `MaskIndex` 0 to 3 is red, green,
blue, alpha -- gives that layer's weight. The `MegaTexture` is the same ground
baked flat for distance; the game fades to it past `splatdistance`.

Two extensions lie in this chain and both were measured, not assumed: a
`MegaTexture` named `.dds` is a NIF like every other texture in this game, and
an `AlphaMap` named `.tga` is a `.dds` on disk, which is also a NIF.
`Terrain.xml` itself is Larian's binary XML, read through the shared reader --
see `divinity2.docs`.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import docs, lod, nif

#: Where the region keeps its own pictures, beside `StaticMeshes.nif`.
TEXTURE_DIR = "TerrainTextures"

#: What the file calls the descriptor.
DESCRIPTOR = "Terrain.xml"

_PATCH = re.compile(r"Terrain_Patch_(\d+)")


@dataclass
class Layer:
    """One splat layer of one patch."""

    texture: str            #: the diffuse, as the file names it
    normal: str             #: its normal map, or ""
    tiling: float           #: how many times it repeats across the patch
    mask: Path | None       #: the alpha map that weights it
    channel: int            #: which of the mask's four channels
    composite: str = ""     #: `_CM`: gloss in red, height in green, noise in blue
    pass_index: int = 0     #: which alpha map, in `AlphaHeap` order: one pass each
    record: dict = field(default_factory=dict)  #: the whole `<Texture>` element
    #: The composite map the pre-light-pass shader reads this layer's noise
    #: from, or "" when it blends without noise (`noise_composites`).
    noise_composite: str = ""


@dataclass
class Patch:
    """One terrain patch: the baked picture, and the recipe behind it."""

    index: int
    megatexture: Path | None = None
    megatexture_normal: Path | None = None
    megatexture_composite: Path | None = None
    layers: list = field(default_factory=list)


def patch_of(path: str) -> int | None:
    """The patch index in a node path, or None when it is not terrain."""
    match = _PATCH.search(path or "")
    return int(match.group(1)) if match else None


def _beside(model_path, named: str) -> Path | None:
    """A path `Terrain.xml` names, resolved beside the model.

    The descriptor writes an alpha map as `.tga` and the file is `.dds`, the
    same way a mesh writes `.tga` for a texture that is a NIF.
    """
    if not named:
        return None
    here = Path(model_path).parent / named.replace("\\", "/")
    for candidate in (here, here.with_suffix(".dds")):
        if candidate.is_file():
            return candidate
    return None


def patches(model_path) -> dict:
    """Every patch the region describes, by index.

    Returns `{}` when the region ships no `Terrain.xml`, which is what a model
    outside a region does.
    """
    root = docs.read(Path(model_path).parent / DESCRIPTOR)
    if root is None:
        return {}

    # `layerID` is a position in this list, not an `ID` attribute:
    # `CTerrainTextureManager::LoadXML` appends every `<Texture>` in file order
    # and `GetTextureIDOnLayer(n)` returns the n-th. Looking it up by `ID` put
    # every layer one texture off and dropped the first.
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
                    # `TilingParams[i] = (float)m_iTextureTiling` -- an integer
                    tiling=float(texture.get("TextureTiling", "1") or 1),
                    mask=mask,
                    channel=channel,
                    composite=texture.get("path_CM", ""),
                    pass_index=pass_index,
                    record=dict(texture.attributes),
                ))
        # Pass by pass, and within a pass by channel: the heap's row order.
        patch.layers.sort(key=lambda lay: (lay.pass_index, lay.channel))
        for layer, composite in zip(patch.layers, noise_composites(patch.layers)):
            layer.noise_composite = composite
        found[index] = patch
    return found


def noise_composites(rows) -> list:
    """Which composite each heap row's noise reads, as the game's terrain
    pre-light-pass material binds and samples them
    (docs/sources.md, "Terrain composite slots").

    The texture side (`RecreatePreLightPassPropertyState`, Dev Cut @0xc8a69c)
    binds composite slots 0..3 to the rows, in row order, that have a `_CM` and
    any of UseGloss, UseNoiseBlending, UseParallax. The shader side
    (`GenerateDescriptor`, Dev Cut @0x48e6a0) gives a row with UseNoiseBlending
    the next slot that is bound, counting noise rows only. Where a row flags
    gloss or parallax without noise the two disagree and a noise row reads an
    earlier row's composite (26 of 312 heaps; none in Banditcamp).
    """
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
    """`Terrain.xml` whole, as plain data: `splatdistance`, `splatblenddistance`
    and the editor's own state beside the patches, which `patches` does not
    keep. None when the region ships no descriptor."""
    root = docs.read(Path(model_path).parent / DESCRIPTOR)
    return None if root is None else docs.to_plain(root)


#: The graphics options the game was played with: `Profile/graphicoptions.xml`
#: in the Proton prefix (measured; docs/sources.md, "Graphics options").
#: With no file the code defaults are RenderMethod 1, StaticAssetHighQuality 0.
GRAPHIC_OPTIONS = {"RenderMethod": 1, "StaticAssetHighQuality": 1}


def splat(model_path, options=GRAPHIC_OPTIONS) -> dict:
    """`g_TerrainSplatRadius` and `g_TerrainSplatBlendRadius` for a region.

    `CTerrainSplatRenderer::LoadXML` @0x6ed7f0 reads `splatdistance` and
    `splatblenddistance` from `Terrain.xml` (constructor 100 and 25 where absent);
    `UpdateSplatDistance` @0x6ec9d0 forces the radius to 2000 when
    `StaticAssetHighQuality` is on."""
    root = docs.read(Path(model_path).parent / DESCRIPTOR) if model_path else None
    node = next(iter(root.find_all("Terrain")), None) if root is not None else None

    def number(key, default):
        try:
            return float(int(node.get(key)))              # atoi
        except (AttributeError, TypeError, ValueError):
            return default

    radius = number("splatdistance", 100.0)
    if options.get("StaticAssetHighQuality"):
        radius = 2000.0
    return {"radius": radius, "blend": number("splatblenddistance", 25.0)}


# ------------------------------------------------------------ the streamed levels

#: The streaming manifest, relative to the model that names the stubs.
STREAM_DESCRIPTOR = Path("Meshes") / "Terrain" / "AssetDataDescriptors.xml"


def levels(model_path) -> dict:
    """Every streamed terrain level, keyed by the stub node it fills.

    `AssetDataDescriptors.xml` is the manifest the engine streams from:

    ```
    <AssetDataDescriptor base="Terrain_Patch_6">
      <LODDistances>
        <LODDistance name="RT_patch_A_LOW" distance="700000" index="0"/>
        <LODDistance name="RT_patch_A_MAX" distance="0"      index="1"/>
    ```

    `index` is the numbered `.nif` inside `Terrain_Patch_<i>/`, and the node
    inside that file is named exactly as `name` -- which is also the name of
    the stub waiting for it in `StaticMeshes.nif`.

    Returns `{}` when the region ships no manifest, which is what a model
    outside a region does.
    """
    descriptor = Path(model_path).parent / STREAM_DESCRIPTOR
    found = {}
    for entry, name, index in manifest(descriptor):
        path = descriptor.parent / entry.get("base", "") / f"{index}.nif"
        if entry.get("base") and name and path.is_file():
            found[name] = path
    return found


def manifest(descriptor):
    """`(AssetDataDescriptor, level name, index)` for every `LODDistance` of an
    `AssetDataDescriptors.xml` whose index is a number -- the terrain's and the
    static assets' alike; nothing when the file is not there."""
    root = docs.read(descriptor)
    for entry in (root.find_all("AssetDataDescriptor") if root is not None else ()):
        for level in entry.find_all("LODDistance"):
            try:
                index = int(level.get("index"))
            except (TypeError, ValueError):
                continue
            yield entry, level.get("name"), index


def graft(root, model_path) -> int:
    """Fill each empty terrain stub with the geometry its streamed file holds.

    **Neither file places the patch on its own.** The stub carries half the
    placement and the streamed node the other half, and the two compose: the
    streamed node hangs under the stub as its child, keeping its own
    transform. Measured on `Banditcamp` `Terrain_Patch_0`, where the grafted
    `_high` level then lands on the inline `_low` level's bounding box to 0.1
    units over a 9,414-unit span. Splicing the streamed node's *children*
    under the stub instead drops its transform and misses by exactly that --
    4,203 units on this patch.

    Without this the ground of every streaming region arrives at its coarsest
    level -- Banditcamp at 9,992 vertices where the game draws 36,883, and
    RiverTown_FF's flying islands as 24-vertex plates.

    `divinity2.lod` needs no part in this. `lod_children` already shows the
    nearest child that holds geometry, so a filled stub is chosen and the
    coarse level is marked hidden, exactly as before.

    Returns how many stubs were filled.
    """
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
        # A level that ships its geometry inline is named in the manifest too,
        # and already has children. Only an empty stub is waiting for a file.
        name = str(getattr(node, "name", ""))
        if children or name not in files:
            continue
        grafted += fill_stub(node, name, files[name], read)
    return grafted


def fill_stub(stub, name: str, path: Path, read: dict) -> bool:
    """Hang the node called `name` in the streamed file under the empty `stub`,
    keeping its own transform; False when the file holds none. `read` caches
    each file's root across calls."""
    streamed = _streamed(path, name, read)
    if streamed is None:
        return False
    stub.children = [streamed]
    stub.num_children = 1
    return True


def _streamed(path: Path, name: str, read: dict):
    """The node called `name` in the streamed file."""
    if path not in read:
        try:
            read[path] = nif.read_nif(path).roots[0]
        except Exception:                                      # noqa: BLE001
            # A streamed file that will not read leaves the coarse level in
            # place, which is what the add-on drew before this existed.
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
