# Vegetation

A region stores a recipe, not instances: a painted mask per grid cell, a table of scatter templates, a table of plants and a library of meshes. The engine generates the instances at load — CVegetationPatch::ProcessVegetationMap @72b6d0 decomp

## Files

`vegetationgridsettings.xml` holds render distances and the cells the grid covers; `vegetationtemplates.xml` holds the layers, each a scatter recipe with its seeds; `vegetationtemplatedata.xml` holds the plants (a mesh, a texture, flags); `Vegetation/VM_<x>_<y>.tga` is one mask per cell; `Vegetation.nif` holds the meshes, one NiNode per `sNifFile`; `Vegetation/atlas.dds` is the billboard atlas — CVegetationGridManager::GenerateVegetationGridEntryDescriptors @6e8ed0 decomp

## Grid and walk

A cell is `CVegetationGridManager::m_usGridEntrySize = 0x20` = 32 m on a side, set in the manager's constructor (nothing else writes it); one sample is 1 m — CVegetationGridManager::CVegetationGridManager @6e9f50 decomp

`ProcessVegetationMap` walks a cell u,v = 0, 1/32, ..., 31/32 (32x32 samples, one per mask pixel, filling `m_vVeggyInstanceArray[1024]`) and asks `CTemplate::CreateInstance(u, v)` per sample; the height query is `GetHeightAt(origin.x + 32*u, origin.y + 32*v)` — CVegetationPatch::ProcessVegetationMap @72b6d0, VeggyLib::CTemplate::CreateInstance @107cd20 decomp

The patch node sits at `index*width`; the origin `ProcessVegetationMap` walks from arrives through the streaming letter — CVegetationGridEntry::UpdateWorldData @72d910 decomp

## Mask

Four bytes per pixel read as RGBA: R picks the template, `round((255 - R)/255*20) % 20`, with R == 0 meaning no plant; G is the size, `G/127.5`; B and A are the ground height cached as `(short)(B<<8|A)/32767*1000` metres (big-endian signed). The engine writes the height back from `CGameLogic_PhysXHelpers::GetHeightAt` the first time it walks a patch. The template count is 20 (`VeggyLib::CTemplateManager::m_aTemplates[20]`); the second `CreateInstance` overload is `(uint)(long long)ROUND(layer * 20.0) % 20` — CGameLogic_PhysXHelpers::GetHeightAt @796140 decomp

The TGA is uncompressed, written by D3DX, bottom-up unless the descriptor says otherwise, channels BGRA; only 32-bit pictures carry plants — CVegetationPatch::ProcessVegetationMap @72b6d0 decomp

## Noise

`CTemplate` has three generators: `m_pkNoiseGenerator` from `PosNoiseType`, `PosSeed`, `PosNumOfSwizzles`; `m_pkHeightNoiseGenerator` from `SizeNoiseType`, `SizeSeed`, `SizeGranularity`, `SizePersistence`; `m_pkDeviationGenerator` that XML never names — VeggyLib::CTemplate::CTemplate @107d600 decomp

Defaults: CRandomNoise(101, 10) for position and CPerlinNoise(101, 16, 0.6) for size — VeggyLib::CTemplate::CTemplate @107d600 decomp

CRandomNoise is a shuffled deck: `UpdateValues` fills 0..1023, calls `srand(seed)`, then `2**NumOfSwizzles` times draws an index and moves that card to the back, which through `NiTArray::RemoveAt` is a swap with the last card (`i = abs(-1 - int(float32(rand()/32767.0) * -1024.0))`). `rand` is MSVC's LCG: `s = s*214013 + 2531011; return (s >> 16) & 0x7fff`. The quotient is stored as float32 before the multiply — VeggyLib::CRandomNoise::UpdateValues @107be00 decomp

`GetNoiseValue(u,v)` draws card `int(1024u + 32v)`: on the sample grid `32i + j`, one card per sample, never past the end of the deck; the `rand()` branch for an index of 1024 or more is never taken. `IntNoise` card is `32x + y`, scaled 0..1 — VeggyLib::CRandomNoise::GetNoiseValue @107bda0, VeggyLib::CRandomNoise::IntNoise @107bce0 decomp

CPerlinNoise is the Hugo Elias tutorial with constants 15731 and 789221 and hash `n ^= n << 13`, except 1376312589 is replaced by 0xd208dd0d: `1 - ((n*(n*n*15731 + 789221) + 0xd208dd0d) & 0x7fffffff) / 2**30`. Smoothing is corners/16 + sides/8 + centre/4, interpolation `(1 - cos(t*pi))/2`, octaves at frequency `2**i` and amplitude `persistence**i`; `GetNoiseValue` folds the sum with `clamp((n + 1)/2, 0, 1)`. It gives size; its integer hash gives rotation, colour and jitter; the quotient is stored as float32 and truncated before multiplying by -1024 — VeggyLib::CPerlinNoise::IntNoise @107b940, VeggyLib::CPerlinNoise::PerlinNoise @107bbb0, VeggyLib::CPerlinNoise::GetNoiseValue @107bc70, VeggyLib::CPerlinNoise::Cosine_Interpolate @107ba80 decomp

The deviation generator is `new CPerlinNoise` with seed 0x39, four octaves, persistence 0.5 (CPerlinNoise(57, 4, 0.5)) — VeggyLib::CTemplate::CTemplate @107d600 decomp

## One plant

`CTemplate::CreateInstance(u,v)`: card = `int(position.GetNoiseValue(u,v))`; name = `SelectData(card)`; a plant with no mesh grows nothing; size = `clamp(sizeNoise.GetNoiseValue(u,v), MinSize, MaxSize)`; turn = `0.5 + 0.5*sizeNoise.IntNoise(int(32u), int(32v))`; tint = `0.5 + fColorVariationScale*sizeNoise.IntNoise(int(96u), int(96v))` only if `bColorVariation`; dx = `clamp(drift.IntNoise(int((u+v)*64)), -1, 1) * 0.008`; dy = `clamp(drift.IntNoise(int((1-u+v)*64)), -1, 1) * 0.008`; grid position is (u+dx, v+dy). 0.008 is a literal in `CreateInstance`, not `m_fMaxPosDeviation` (0.016). `m_fSize` is written only when the mask byte is non-zero — VeggyLib::CTemplate::CreateInstance @107cd20 decomp

`CTemplate::SelectData` walks the entries adding their `iInstanceCount` and returns the first whose running total reaches the card; off the end it returns the first entry. The counts of one template sum to 1024 — VeggyLib::CTemplate::SelectData @107c990 decomp

The final size is `GetRealSize` = `m_fNoiseSize * m_fSize` — VeggyLib::CVeggyInstance::GetRealSize @74ca30 decomp

`CVeggyInstance::m_fRotation` is 0..1 and `CVegetationType::RegisterInstance` hands it to a vertex shader compiled into `Win32/BinaryShaders/` — CVegetationType::RegisterInstance @74e520 decomp

Past `fRenderDistance` the engine swaps a plant for a card from `atlas.dds`, and `fWindScale` drives a vertex animation; both are drawing, not placement — VeggyLib::CTemplateData::GetRenderDistance @74c9d0, VeggyLib::CTemplateData::GetWindScale @74c9f0 decomp
