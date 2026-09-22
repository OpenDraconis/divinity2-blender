"""Where every blade of grass stands, generated the way the engine generates it.

A region ships no list of grass. It ships a **recipe**: a 32x32 mask per grid
cell (`Vegetation/VM_<x>_<y>.tga`), a table of scatter templates
(`vegetationtemplates.xml`), a table of plants (`vegetationtemplatedata.xml`),
and a library of meshes (`Vegetation.nif`). The engine turns the recipe into
instances at load, and the generator is deterministic -- so the same recipe
gives the same field twice, and this module gives the same field as the game.

Everything here is read out of `Divinity2GUP.exe` with its own symbols, not
guessed. The three pieces:

**The loop** -- `CVegetationPatch::ProcessVegetationMap` walks a cell in
`u, v = 0, 1/32, 2/32 ... 31/32`, one step per mask pixel, and asks
`CTemplate::CreateInstance(u, v)` for a plant at each. A cell is
`CVegetationGridManager::m_usGridEntrySize` = **32** metres on a side, set in
the manager's constructor, so a sample is one metre.

**The mask** -- four bytes per pixel, and the engine reads them as RGBA:

| byte | what | how |
|---|---|---|
| R | which template | `round((255 - R) / 255 * 20) % 20`, and `R == 0` means no plant |
| G | how big | `size = G / 127.5` |
| B, A | the ground's height, cached | `(short)(B << 8 | A) / 32767 * 1000` metres |

The height is what `CGameLogic_PhysXHelpers::GetHeightAt` returned when the
cell was first walked; the engine writes it back into the picture so the next
walk is free. It is the game's own ground height, to a millimetre.

**The dice** -- two noise generators per template, both seeded from the XML:

* `CRandomNoise` is a deck of the numbers 0..1023, shuffled by `srand(seed)`
  and `2 ** NumOfSwizzles` swaps with the last card. `GetNoiseValue(u, v)`
  draws card `1024u + 32v` -- which, on the sample grid, is exactly one card
  per sample and never runs off the end. The card picks the plant out of the
  template's entries, whose instance counts sum to 1024.
* `CPerlinNoise` is the Hugo Elias tutorial, verbatim down to the constants
  15731, 789221 and the `n ^ n << 13` hash -- except that where the tutorial
  adds 1376312589 this adds `0xd208dd0d`. It gives the size, and its integer
  hash gives the rotation, the colour and the metre-scale jitter.

What is *not* here: the billboards the engine swaps in past
`fRenderDistance`, and the wind. Both are drawing, not placement.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import docs

#: One grid cell, in metres. `CVegetationGridManager::CVegetationGridManager`
#: sets `m_usGridEntrySize = 0x20` and nothing else writes it.
CELL = 32

#: **A cell is centred on its index, not hung from it.** The engine's own
#: `CVegetationGridEntry::UpdateWorldData` places the patch node at
#: `index * width`, and `ProcessVegetationMap` walks from an origin the
#: streaming letter carries -- which is not that node's position, and chasing
#: it through the letter pool was not worth the hour. So it was measured, the
#: way everything else in this add-on is measured: 747 painted samples, their
#: cached ground height against the ground in the built scene, over every
#: offset from -32 to +32 metres in both axes.
#:
#: | origin | mean error |
#: |---|---|
#: | `index * 32` | 11.68 m |
#: | `index * 32 - 16` | **0.37 m** |
#:
#: Half a cell, in both axes, and nothing near it comes close. The remaining
#: 0.37 m is the sample spacing: the walk asks for the height once a metre.
ORIGIN = -CELL / 2

#: Samples across a cell, one per mask pixel. The walk steps by 1/32.
STEPS = 32

#: `VeggyLib::CTemplateManager` holds this many templates, and the mask's
#: first byte is a fraction of it.
SLOTS = 20

#: The deck `CRandomNoise` shuffles, and the sum of a template's counts.
DECK = 1024

#: Where the mask pictures live, under the sub-region.
MASKS = "Vegetation"

#: `ENoiseType`.
PERLIN, RANDOM = 0, 1

#: `CTemplate`'s own deviation generator, which the XML never names.
DRIFT_SEED, DRIFT_OCTAVES, DRIFT_PERSISTENCE = 57, 4, 0.5

#: How far a plant may drift from its sample, as a fraction of a cell.
DRIFT = 0.008


# --------------------------------------------------------------------------
# the dice
# --------------------------------------------------------------------------

_U32 = 0xFFFFFFFF


class _Rand:
    """Microsoft's `rand`, which is what `CRandomNoise::UpdateValues` shuffles
    with. The multiplier and the addend are the ones in every MSVC runtime."""

    def __init__(self, seed: int):
        self.state = seed & _U32

    def __call__(self) -> int:
        self.state = (self.state * 214013 + 2531011) & _U32
        return (self.state >> 16) & 0x7FFF


class RandomNoise:
    """`VeggyLib::CRandomNoise`: a shuffled deck of 0..1023.

    `UpdateValues` fills the array with `0..1023`, seeds `rand`, and then
    `2 ** m_iNumOfSwizzles` times takes a random card and moves it to the
    back -- which, the way `NiTArray::RemoveAt` fills the hole, is a swap
    with the last card.
    """

    def __init__(self, seed: int, swizzles: int):
        self.seed, self.swizzles = seed, swizzles
        cards = list(range(DECK))
        roll = _Rand(seed)
        for _ in range(int(2.0 ** abs(swizzles))):
            # float32 on the way out of the divide, then truncate: the engine
            # stores the quotient to a `float` before multiplying by -1024.
            quotient = np.float32(roll() / 32767.0)
            drawn = int(float(quotient) * -1024.0)
            i = abs(-1 - drawn)
            cards[i], cards[DECK - 1] = cards[DECK - 1], cards[i]
        self.cards = np.array(cards, dtype=np.int64)

    def value(self, u, v):
        """`GetNoiseValue`: card `1024u + 32v`, as a float."""
        i = np.trunc(np.asarray(u) * 1024.0 + np.asarray(v) * 32.0).astype(np.int64)
        return np.where(i < DECK, self.cards[np.clip(i, 0, DECK - 1)], 0.0)

    def int_noise(self, x, y=0):
        """`IntNoise`: card `32x + y`, scaled to 0..1."""
        i = (np.asarray(x, dtype=np.int64) * 32 + np.asarray(y, dtype=np.int64)) & 0x3FF
        return self.cards[i] / 1024.0


class PerlinNoise:
    """`VeggyLib::CPerlinNoise`, octave for octave."""

    def __init__(self, seed: int, octaves: int, persistence: float):
        self.seed, self.octaves, self.persistence = seed, octaves, persistence

    def int_noise(self, x, y=None):
        n = np.asarray(x, dtype=np.int64)
        if y is not None:
            n = (self.seed * np.asarray(y, dtype=np.int64) + n) & _U32
        else:
            n = (self.seed * n) & _U32
        n = (n ^ (n << 13)) & _U32
        t = (((n * n) & _U32) * 15731 + 789221) & _U32
        t = (t * n - 0x2DF722F3) & _U32
        return 1.0 - (t & 0x7FFFFFFF) * (2.0 ** -30)

    def _smooth(self, x, y):
        corners = (self.int_noise(x - 1, y - 1) + self.int_noise(x + 1, y - 1)
                   + self.int_noise(x - 1, y + 1) + self.int_noise(x + 1, y + 1))
        sides = (self.int_noise(x - 1, y) + self.int_noise(x + 1, y)
                 + self.int_noise(x, y - 1) + self.int_noise(x, y + 1))
        return corners / 16.0 + sides / 8.0 + self.int_noise(x, y) / 4.0

    @staticmethod
    def _cosine(a, b, t):
        f = (1.0 - np.cos(t * 3.1415927410125732)) * 0.5
        return a * (1.0 - f) + b * f

    def _interpolated(self, x, y):
        ix, iy = np.trunc(x).astype(np.int64), np.trunc(y).astype(np.int64)
        fx, fy = x - ix, y - iy
        top = self._cosine(self._smooth(ix, iy), self._smooth(ix + 1, iy), fx)
        low = self._cosine(self._smooth(ix, iy + 1), self._smooth(ix + 1, iy + 1), fx)
        return self._cosine(top, low, fy)

    def noise(self, u, v):
        total = np.zeros_like(np.asarray(u, dtype=np.float64))
        for i in range(self.octaves):
            frequency = 2.0 ** i
            total += self._interpolated(u * frequency, v * frequency) \
                * (self.persistence ** i)
        return total

    def value(self, u, v):
        """`GetNoiseValue`: the octave sum folded into 0..1."""
        return np.clip((self.noise(u, v) + 1.0) * 0.5, 0.0, 1.0)


def _noise(kind: int, seed: int, swizzles: int, octaves: int, persistence: float):
    """What `CTemplate::LoadXML` builds for a `*NoiseType`."""
    if kind == PERLIN:
        return PerlinNoise(seed, octaves, persistence)
    return RandomNoise(seed, swizzles)


# --------------------------------------------------------------------------
# the recipe
# --------------------------------------------------------------------------

@dataclass
class Plant:
    """One row of `vegetationtemplatedata.xml`: a mesh and how to draw it."""
    name: str
    model: str = ""
    texture: str = ""
    scale: float = 1.0
    render_distance: float = 30.0
    fade_out: float = 0.0
    wind_scale: float = 0.0
    colour_scale: float = 0.05
    flags: dict = field(default_factory=dict)
    record: dict = field(default_factory=dict)  # every attribute, as the file holds it

    @property
    def empty(self) -> bool:
        """`CTemplate::CreateInstance` drops a plant with no mesh."""
        return not self.model


@dataclass
class Template:
    """One `<Layer>` of `vegetationtemplates.xml`: a scatter recipe."""
    layer: int
    name: str
    entries: list                      # [(count, plant name)], in file order
    # The defaults are `CTemplate::CTemplate`'s: a `CRandomNoise(101, 10)`
    # for the position and a `CPerlinNoise(101, 16, 0.6)` for the size.
    pos_seed: int = 101
    pos_kind: int = RANDOM
    pos_swizzles: int = 10
    pos_persistence: float = 0.6
    pos_granularity: int = 16
    size_seed: int = 101
    size_kind: int = PERLIN
    size_swizzles: int = 10
    size_persistence: float = 0.6
    size_granularity: int = 16
    min_size: float = 0.0
    max_size: float = 1.0

    def pick(self, card: int) -> str:
        """`CTemplate::SelectData`: walk the entries until their counts pass
        the card. Off the end, the engine hands back the first entry."""
        total = 0
        for count, name in self.entries:
            if count == 0:
                continue
            total += count
            if total >= card:
                return name
        return self.entries[0][1] if self.entries else ""


@dataclass
class Recipe:
    """Everything a sub-region says about its vegetation."""
    region: str
    sub: str
    templates: dict                    # layer index -> Template
    plants: dict                       # name -> Plant
    cells: list                        # [(x, y)] the grid settings name
    masks: dict                        # (x, y) -> Path
    library: Path | None = None        # Vegetation.nif
    atlas: Path | None = None
    settings: dict = field(default_factory=dict)
    grid: dict = field(default_factory=dict)   # `GridManager`'s every attribute, as held


def _flag(text) -> bool:
    return str(text) not in ("0", "None", "")


def read(root: Path, region: str, sub: str = "Main") -> Recipe:
    """The recipe as the sub-region ships it."""
    from .region import folder        # region reads vegetation's tables
    # A sub-region other than Main lives under `Subregions/`
    # (`CRegionVisualMan::PerformRegionSwap`'s base path); joining the name
    # straight onto the region missed every one of them.
    here = folder(root, region, sub)
    templates, plants, cells, settings, record = {}, {}, [], {}, {}

    grid = docs.read(here / "vegetationgridsettings.xml")
    if grid is not None:
        node = next(grid.find_all("GridManager"), None)
        if node is not None:
            record = node.named()
            settings = {
                "bb_min": docs.number(node.get("BBMinDistance"), 25.0),
                "bb_max": docs.number(node.get("BBMaxDistance"), 100.0),
                "instance_min": docs.number(node.get("InstanceMinDistance"), 1.0),
                "instance_max": docs.number(node.get("InstanceMaxDistance"), 30.0),
                "shared_textures": int(docs.number(node.get("SharedNbTextures"), 1)),
                "check_normal": _flag(node.get("CheckNormalDuringPlacement")),
                "angle_to_skip": docs.number(node.get("AngleToSkip"), 1.0),
            }
            for child in node.children:
                name = child.get("value")
                if name and "_" in name:
                    x, _, y = name.partition("_")
                    try:
                        cells.append((int(x), int(y)))
                    except ValueError:
                        pass

    tree = docs.read(here / "vegetationtemplates.xml")
    if tree is not None:
        for layer in tree.find_all("Layer"):
            index = int(docs.number(layer.get("iLayer"), -1))
            for node in layer.find_all("Template"):
                params = next(node.find_all("TemplateEntries"), None)
                entries = [] if params is None else [
                    (int(docs.number(e.get("iInstanceCount"))), e.get("sTemplateDataName", ""))
                    for e in params.find_all("TemplateEntry")]
                get = (lambda k, d: d) if params is None \
                    else (lambda k, d: docs.number(params.get(k), d))
                templates[index] = Template(
                    layer=index, name=node.get("sName", ""), entries=entries,
                    pos_seed=int(get("PosSeed", 101)),
                    pos_kind=int(get("PosNoiseType", RANDOM)),
                    pos_swizzles=int(get("PosNumOfSwizzles", 10)),
                    pos_persistence=get("PosPersistence", 0.6),
                    pos_granularity=int(get("PosGranularity", 16)),
                    size_seed=int(get("SizeSeed", 101)),
                    size_kind=int(get("SizeNoiseType", PERLIN)),
                    size_swizzles=int(get("SizeNumOfSwizzles", 10)),
                    size_persistence=get("SizePersistence", 0.6),
                    size_granularity=int(get("SizeGranularity", 16)),
                    min_size=get("MinSize", 0.0), max_size=get("MaxSize", 1.0))

    data = docs.read(here / "vegetationtemplatedata.xml")
    if data is not None:
        for node in data.find_all("TemplateData"):
            name = node.get("sName", "")
            plants[name] = Plant(
                name=name, model=node.get("sNifFile", "") or "",
                texture=node.get("sTexture", "") or "",
                scale=docs.number(node.get("fScale"), 1.0),
                render_distance=docs.number(node.get("fRenderDistance"), 30.0),
                fade_out=docs.number(node.get("fFadeOutDistance"), 0.0),
                wind_scale=docs.number(node.get("fWindScale"), 0.0),
                colour_scale=docs.number(node.get("fColorVariationScale"), 0.05),
                flags={k: _flag(node.get(k)) for k in (
                    "bAlpha", "bColorVariation", "bNormalMapped", "bRenderToDepth",
                    "bRotation", "bSpecular", "bUseMaterialSystem", "bWindMovement")},
                record=node.named())

    masks = {}
    for path in sorted((here / MASKS).glob("VM_*.tga")):
        x, _, y = path.stem[3:].partition("_")
        try:
            masks[(int(x), int(y))] = path
        except ValueError:
            pass

    library = here / "Vegetation.nif"
    atlas = here / MASKS / "atlas.dds"
    return Recipe(region=region, sub=sub, templates=templates, plants=plants,
                  cells=cells, masks=masks,
                  library=library if library.exists() else None,
                  atlas=atlas if atlas.exists() else None, settings=settings,
                  grid=record)


# --------------------------------------------------------------------------
# the mask
# --------------------------------------------------------------------------

def mask(path: Path) -> np.ndarray | None:
    """One `VM_<x>_<y>.tga` as `(rows, columns, 4)` in **RGBA**, which is the
    order the engine's `NiPixelData` hands to the walk.

    The file is an uncompressed TGA written by D3DX, bottom-up unless its
    descriptor says otherwise, and stores its channels BGRA.

    **Only a 32-bit picture carries plants.** A vegetation map is RGBA -- the
    walk needs all four bytes, two of them for the cached height -- and the
    sub-region's 24-bit pictures are every one of them a solid `ff00ff`, the
    editor's colour for nothing painted. Banditcamp ships 60 of those and 34
    real maps, and no real map holds a single magenta pixel.
    """
    raw = path.read_bytes()
    if len(raw) < 18:
        return None
    id_length, colour_map, kind = raw[0], raw[1], raw[2]
    width, height, depth = struct.unpack_from("<HHB", raw, 12)
    descriptor = raw[17]
    if kind != 2 or colour_map != 0 or depth != 32:
        return None
    start = 18 + id_length
    stride = depth // 8
    pixels = np.frombuffer(raw, dtype=np.uint8, count=width * height * stride,
                           offset=start).reshape(height, width, stride)
    out = np.zeros((height, width, 4), dtype=np.uint8)
    out[:, :, 0] = pixels[:, :, 2]                     # R
    out[:, :, 1] = pixels[:, :, 1]                     # G
    out[:, :, 2] = pixels[:, :, 0]                     # B
    out[:, :, 3] = pixels[:, :, 3]
    if not descriptor & 0x20:                          # bottom-up
        out = out[::-1]
    return out


def heights(cell: np.ndarray) -> np.ndarray:
    """The ground height the engine cached in the mask, in metres.

    `ProcessVegetationMap` packs what `GetHeightAt` returned into the third
    and fourth bytes, big-endian, as a signed sixteenth of `1000 / 32767`.
    """
    packed = (cell[:, :, 2].astype(np.int32) << 8) | cell[:, :, 3].astype(np.int32)
    packed = packed.astype(np.int16)                   # the engine's `(short)`
    return packed.astype(np.float64) / 32767.0 * 1000.0


def slot(red: np.ndarray) -> np.ndarray:
    """Which template a pixel names. `red == 0` means no plant at all."""
    return np.rint((255.0 - red.astype(np.float64)) / 255.0 * SLOTS).astype(int) % SLOTS


# --------------------------------------------------------------------------
# the scatter
# --------------------------------------------------------------------------

@dataclass
class Instance:
    """One plant, where the engine would have put it."""
    plant: str
    x: float
    y: float
    z: float
    size: float
    rotation: float                    # 0..1, a turn
    colour: float


def _fields(template: Template) -> dict:
    """Everything `CreateInstance` reads, for all 1024 samples at once.

    The sample grid is the same in every cell, so this is computed once per
    template and then only looked up.
    """
    step = 1.0 / STEPS
    vs, us = np.meshgrid(np.arange(STEPS) * step, np.arange(STEPS) * step,
                         indexing="ij")
    position = _noise(template.pos_kind, template.pos_seed, template.pos_swizzles,
                      template.pos_granularity, template.pos_persistence)
    size = _noise(template.size_kind, template.size_seed, template.size_swizzles,
                  template.size_granularity, template.size_persistence)

    card = np.trunc(np.asarray(position.value(us, vs), dtype=np.float64)).astype(int)
    noise_size = np.clip(np.asarray(size.value(us, vs), dtype=np.float64),
                         template.min_size, template.max_size)
    # The engine asks the *size* generator for these, with the sample index.
    turn = 0.5 + 0.5 * np.asarray(size.int_noise(np.trunc(32 * us).astype(int),
                                                 np.trunc(32 * vs).astype(int)))
    tint = np.asarray(size.int_noise(np.trunc(96 * us).astype(int),
                                     np.trunc(96 * vs).astype(int)))
    # and the *deviation* generator -- which no attribute configures, so it
    # stays what `CTemplate`'s constructor made it: `new CPerlinNoise` with
    # seed 0x39, four octaves and persistence 0.5. One call per axis,
    # clamped, and 0.008 of a cell -- a literal in `CreateInstance`, not the
    # `m_fMaxPosDeviation` of 0.016 beside it.
    drift = PerlinNoise(DRIFT_SEED, DRIFT_OCTAVES, DRIFT_PERSISTENCE)
    dx = np.clip(np.asarray(drift.int_noise(np.trunc((us + vs) * 64).astype(int))),
                 -1.0, 1.0) * DRIFT
    dy = np.clip(np.asarray(drift.int_noise(
        np.trunc((1.0 - us + vs) * 64).astype(int))), -1.0, 1.0) * DRIFT
    return {"card": card, "noise_size": noise_size, "turn": turn, "tint": tint,
            "u": us + dx, "v": vs + dy}


def scatter(recipe: Recipe, cells=None) -> list:
    """Every instance in the sub-region, cell by cell.

    One pass per cell, over the 32x32 samples `ProcessVegetationMap` walks.
    """
    ready = {i: _fields(t) for i, t in recipe.templates.items()}
    out = []
    for (cx, cy), path in sorted(recipe.masks.items()):
        if cells is not None and (cx, cy) not in cells:
            continue
        picture = mask(path)
        if picture is None or picture.shape[0] != STEPS:
            continue
        ground = heights(picture)
        which = slot(picture[:, :, 0])
        for row in range(STEPS):
            for column in range(STEPS):
                if picture[row, column, 0] == 0:
                    continue
                template = recipe.templates.get(int(which[row, column]))
                if template is None:
                    continue
                f = ready[template.layer]
                name = template.pick(int(f["card"][row, column]))
                plant = recipe.plants.get(name)
                if plant is None or plant.empty:
                    continue
                # `m_fSize` is only written when the byte is not zero, and
                # no painted pixel in this region has a zero there.
                size = picture[row, column, 1] / 127.5
                out.append(Instance(
                    plant=name,
                    x=float(cx * CELL + ORIGIN + f["u"][row, column] * CELL),
                    y=float(cy * CELL + ORIGIN + f["v"][row, column] * CELL),
                    z=float(ground[row, column]),
                    size=float(f["noise_size"][row, column]) * float(size),
                    rotation=float(f["turn"][row, column]),
                    colour=float(0.5 + plant.colour_scale
                                 * float(f["tint"][row, column]))
                    if plant.flags.get("bColorVariation") else 0.5))
    return out


def _selftest():
    """The two things that would silently rot: the deck and the lottery."""
    a = RandomNoise(101, 10).cards
    b = RandomNoise(101, 10).cards
    assert np.array_equal(a, b), "the same seed must give the same deck"
    assert sorted(a.tolist()) == list(range(DECK)), "the deck must stay a deck"
    assert not np.array_equal(a, RandomNoise(66, 10).cards), "seeds must differ"
    t = Template(layer=0, name="x", entries=[(248, "a"), (248, "b"), (247, "c"),
                                             (281, "d"), (0, "e")])
    assert sum(c for c, _ in t.entries) == DECK, "counts must fill the deck"
    assert (t.pick(0), t.pick(248), t.pick(249), t.pick(1024)) == ("a", "a", "b", "d")
    p = PerlinNoise(37, 4, 0.6)
    assert abs(float(p.int_noise(0, 0))) <= 1.0
    assert 0.0 <= float(p.value(0.25, 0.5)) <= 1.0
    print("vegetation: ok")


if __name__ == "__main__":
    _selftest()
