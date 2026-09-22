# The grass, from the engine that grows it

A Divinity II region stores no grass. It stores a **recipe** — a painted mask
per grid cell, a table of scatter templates, a table of plants, and a library
of meshes — and the engine turns that into instances at load, every time, the
same way. This is that generator, read out of `Divinity2GUP.exe` with the
symbols from `Divinity2GUP.pdb`.

Nothing here is inferred from how it looks. Every rule below names the
function it came from, and the two that had to be measured instead say so.

## The files

| file | what it holds |
|---|---|
| `World/<r>/<sub>/vegetationgridsettings.xml` | the render distances, and the cells the grid covers |
| `World/<r>/<sub>/vegetationtemplates.xml` | twelve layers, each a scatter recipe with its seeds |
| `World/<r>/<sub>/vegetationtemplatedata.xml` | thirty-four plants: a mesh, a texture, eight flags |
| `World/<r>/<sub>/Vegetation/VM_<x>_<y>.tga` | one 32×32 mask per cell |
| `World/<r>/<sub>/Vegetation.nif` | the meshes, one `NiNode` per `sNifFile` |
| `World/<r>/<sub>/Vegetation/atlas.dds` | the billboard atlas, which this does not use |

All three XMLs are Larian binary XML inside a NIF wrapper, and every one of
their attribute names was already recovered.

## The walk

`CVegetationPatch::ProcessVegetationMap` is the whole loop:

```
for v = 0; v < 1.0; v += 1/32:
    for u = 0; u < 1.0; u += 1/32:
        pixel = map(round(width * u), round(height * v))
        if pixel.R != 0:
            plant = CVegetationTemplateManager::CreateInstance(u, v, (255 - pixel.R) / 255)
            plant.position = origin + gridPos * gridEntrySize
            plant.size     = pixel.G / 127.5
```

Thirty-two steps in each axis — exactly one per mask pixel, and exactly
`m_vVeggyInstanceArray[1024]`, the array it fills.

**A cell is 32 metres.** `CVegetationGridManager::CVegetationGridManager` sets
`m_usGridEntrySize = 0x20` and nothing else writes it. The loop's height query
is `GetHeightAt(origin.x + 32*u, origin.y + 32*v)`, which is the same 32.

## The mask

Four bytes per pixel, and `NiPixelData` hands them to the walk as RGBA — so
the file's BGRA order has to be undone on the way in.

| byte | what | how |
|---|---|---|
| R | which template | `round((255 - R) / 255 * 20) % 20`; `R == 0` means nothing grows here |
| G | how big | `m_fSize = G / 127.5` |
| B, A | the ground height | `(short)(B << 8 \| A) / 32767 * 1000`, in metres |

The twenty is `VeggyLib::CTemplateManager`'s `m_aTemplates[20]`, and the
second `CreateInstance` overload is literally
`(uint)(long long)ROUND(layer * 20.0) % 20`.

The height is a **cache, not a source**: `ProcessVegetationMap` computes it
with `CGameLogic_PhysXHelpers::GetHeightAt` the first time it walks a patch
and writes it back into the picture. Banditcamp ships it filled for 38% of all
pixels and **99.2% of painted ones** — the game had already been there.

**Only a 32-bit picture carries plants.** A vegetation map needs all four
bytes; the 24-bit ones are, every single one of them, a solid `ff00ff` —
the editor's colour for nothing painted. Banditcamp ships 60 of those and 34
real maps, and no real map holds one magenta pixel.

## The dice

`CTemplate` keeps three noise generators. `LoadXML` builds the first two from
the XML and leaves the third at whatever the constructor made it:

| generator | from | Banditcamp |
|---|---|---|
| `m_pkNoiseGenerator` | `PosNoiseType`, `PosSeed`, `PosNumOfSwizzles` | `CRandomNoise` |
| `m_pkHeightNoiseGenerator` | `SizeNoiseType`, `SizeSeed`, `SizeGranularity`, `SizePersistence` | `CPerlinNoise` |
| `m_pkDeviationGenerator` | nothing — `CTemplate::CTemplate` makes it | `CPerlinNoise(57, 4, 0.5)` |

### `CRandomNoise` — a shuffled deck

`UpdateValues` fills an array with `0 .. 1023`, calls `srand(seed)`, and then
`2 ** m_iNumOfSwizzles` times draws an index and moves that card to the back.
The way `NiTArray::RemoveAt` fills the hole, that is a swap with the last
card:

```python
cards = list(range(1024))
srand(seed)
for _ in range(2 ** swizzles):
    i = abs(-1 - int(float32(rand() / 32767.0) * -1024.0))
    cards[i], cards[1023] = cards[1023], cards[i]
```

`rand` is Microsoft's: `s = s*214013 + 2531011; return (s >> 16) & 0x7fff`.
The `float32` is not decoration — the engine stores the quotient to a `float`
before the multiply, and rounding it in double precision moves cards.

`GetNoiseValue(u, v)` draws card `int(1024u + 32v)`. On the sample grid, where
`u = i/32` and `v = j/32`, that is `32i + j` — one card per sample, every card
once, and never past the end of the deck. The generator has a `rand()` branch
for an index of 1024 or more and **it is never taken**.

### `CPerlinNoise` — the Hugo Elias tutorial, verbatim

Constants and all: `n ^= n << 13`, then
`1 - ((n*(n*n*15731 + 789221) + 0xd208dd0d) & 0x7fffffff) / 2**30`. Where the
published tutorial adds 1376312589, this adds `0xd208dd0d`; that is the only
difference, and it is in the binary.

Smoothing is the tutorial's corners/16 + sides/8 + centre/4, interpolation is
`(1 - cos(t·π))/2`, and `PerlinNoise` sums `nbOctaves` octaves at
`frequency = 2**i`, `amplitude = persistence**i`. `GetNoiseValue` folds the
sum into 0..1 with `clamp((n + 1) / 2, 0, 1)`.

## One plant

`CTemplate::CreateInstance(u, v)`, in order:

```
card  = int(position.GetNoiseValue(u, v))
name  = SelectData(card)                       # the lottery, below
data  = templateData[name];  if data.nif == "" : nothing grows
size  = clamp(sizeNoise.GetNoiseValue(u, v), MinSize, MaxSize)
turn  = 0.5 + 0.5 * sizeNoise.IntNoise(int(32u), int(32v))
tint  = 0.5 + data.fColorVariationScale * sizeNoise.IntNoise(int(96u), int(96v))
                                               # only if bColorVariation
dx    = clamp(drift.IntNoise(int((u + v) * 64)),       -1, 1) * 0.008
dy    = clamp(drift.IntNoise(int((1 - u + v) * 64)),   -1, 1) * 0.008
gridPosition = (u + dx, v + dy)
```

The 0.008 is a literal in `CreateInstance`, not the `m_fMaxPosDeviation` of
0.016 sitting next to it in the class. A quarter of a metre either way.

**The lottery is exact.** `SelectData` walks the template's entries adding up
their `iInstanceCount` and returns the first whose running total reaches the
card. Every one of Banditcamp's twelve layers sums to **1024** — which is what
proves those numbers are counts and not weights or probabilities.

The final size is `GetRealSize`, which is `m_fNoiseSize * m_fSize` — the
Perlin size times the mask's byte.

## Where the cell sits — measured

`CVegetationGridEntry::UpdateWorldData` puts the patch's *node* at
`index * width`, but the origin `ProcessVegetationMap` walks from arrives
through the streaming letter pool, and following it there was not worth the
hour it would have cost.

So it was measured, the way everything else in this add-on is measured.
5,224 painted samples that carry a cached height, against the ground of the
built scene, over every offset from −32 to +32 m in both axes:

| origin | mean error |
|---|---|
| `index * 32` | 11.68 m |
| `index * 32 − 16` | **0.37 m** |

Half a cell, in both axes. Nothing near it comes close, and the residue is
the sample spacing — the walk asks the ground once a metre.

## The check

The same 5,224 samples, with the origin right:

```
meanAbs 0.410 m   median 0.008 m
within 10 cm  5120 of 5224  (98.0%)
```

That one number tests four things at once: the mask's channels, the cell's
size, the cell's origin and the axis conversion. Get any one wrong and it
moves.

The 2% are pixels whose cached height went stale against the ground we build.
Dropped onto the ground that is actually there, of 4,737 plants in Banditcamp:

```
meanAbs 0.026 m   within 10 cm 4699 (99.2%)   worst 0.35 m
```

## The rest of the game

Fourteen of the game's sub-regions carry vegetation -- the outdoor ones -- and
all fourteen read with no special case:

| sub-region | templates | plants | masks | grown |
|---|---:|---:|---:|---:|
| BrokenValley_2/Main | 14 | 36 | 549 | 173,251 |
| RiverTown_FF/Main | 1 | 3 | 267 | 100,878 |
| DZ1/Main | 13 | 36 | 878 | 71,902 |
| Damians_Fortress_1/Main | 2 | 3 | 198 | 69,651 |
| Damians_Fortress_2/Main | 2 | 3 | 215 | 52,190 |
| 001_BattleTower_Beach/Main | 8 | 11 | 109 | 14,612 |
| Exp_AlerothCity/Main | 1 | 3 | 75 | 13,330 |
| 003_Aleroth_City/Main | 1 | 3 | 72 | 13,066 |
| 004_Tutorial/Main | 13 | 34 | 36 | 4,902 |
| Banditcamp/Main | 12 | 34 | 94 | 4,737 |
| … and four more | | | | |
| **all of them** | | | | **523,223** |

Five seconds for the lot, so the whole sweep is cheap to run again after any
change.

## What is ours, not the game's

**The turn.** `m_fRotation` is 0..1 and `CVegetationType::RegisterInstance`
hands it to a vertex shader that is compiled HLSL in
`Win32/BinaryShaders/`. Reading it as one full turn about the up axis is our
choice. Everything else on this page is the engine's.

**The billboards and the wind** are not done at all: past
`fRenderDistance` the engine swaps a plant for a card out of `atlas.dds`, and
`fWindScale` drives a vertex animation. Both are drawing, not placement, and
the numbers travel in the table for whoever wants them.
