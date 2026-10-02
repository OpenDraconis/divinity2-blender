# Terrain

A terrain patch's levels above 0 are `Meshes/Terrain/Terrain_Patch_<i>/<n>.nif`; `Meshes/Terrain/AssetDataDescriptors.xml` maps file to stub: `<AssetDataDescriptor base="Terrain_Patch_6"><LODDistances><LODDistance name="RT_patch_A_LOW" distance="700000" index="0"/><LODDistance name="RT_patch_A_MAX" distance="0" index="1"/>`. `index` is the numbered `.nif`, `name` is the stub's name and the node inside the file carries it; `distance` orders the levels with 0 nearest — CStaticAssetDataManager::CollectLODNodeNames @73e310 decomp

The stub carries half of the placement and the streamed node the other half; the streamed node hangs under the stub as its child and keeps its own transform. A stub matches its streamed node by name — CStaticAssetDataManager::RequestLoadData @73e040 decomp

A level that ships inline is also named in the manifest and already has children; only an empty stub waits for a file — CStaticAssetDataManager::RequestLoadData @73e040 decomp

Terrain shapes carry no NiTexturingProperty, only NiMaterialProperty; the recipe is `Terrain.xml`: `<Terrain splatdistance="116" splatblenddistance="20"><TerrainPatch index="6"><AlphaHeap><AlphaMap path="TerrainTextures\AlphaMaps\6_6_AlphaMap_1.tga"><Layers><ID layerID="6" MaskIndex="2" AlphaMapIndex="1"/>...</Layers>...<MegaTexture path="TerrainTextures\MegaTexture_6.dds"/><Textures><Texture path="BV2_Moss_A.dds" path_NM="..." TextureTiling="50" ID="6"/>`. One Texture per layer gives picture and tiling; one channel of one alpha map (MaskIndex 0..3 = R,G,B,A) gives the weight; the MegaTexture is the ground baked flat and the game fades to it past `splatdistance` — CTerrainTextureManager::LoadXML @72faf0 decomp

`layerID` is a position in the texture list, not the `ID` attribute: `CTerrainTextureManager::LoadXML` appends every `<Texture>` in file order and `GetTextureIDOnLayer(n)` returns the n-th — CTerrainTextureManager::LoadXML @72faf0 decomp

`TilingParams[i] = (float)m_iTextureTiling`, an integer; layers are passed pass by pass, within a pass by channel (heap row order) — CTerrainPatchLOD::AttachExtraData @754670 decomp

`CTerrainSplatRenderer::LoadXML` reads `splatdistance` and `splatblenddistance` from Terrain.xml with `atoi`; the constructor gives 100 and 25 where absent; `UpdateSplatDistance` forces the radius to 2000 when `CGraphicSettings::m_eRenderMethod` is not 0 — CTerrainSplatRenderer::LoadXML @6ed7f0, CTerrainSplatRenderer::UpdateSplatDistance @6ec9d0 decomp

The game reads RenderMethod and StaticAssetHighQuality from `graphicoptions.xml` in the player's profile; with no file or attribute they are RenderMethod 1 (light pre-pass) and StaticAssetHighQuality 0. Presets 0, 1 and 4 turn StaticAssetHighQuality off, 2 and 3 on, 5 (user-defined) keeps the file's values. Only the file sets the render method: `SetRenderMethod` (@6a2b70 dc) has no caller — CGraphicSettings::GetSaveFile @769010, CGraphicSettings::LoadXML @76a300, CGraphicSettings::CGraphicSettings @76a700 decomp, CGraphicSettings::LoadXML @6a4f70 dc, CGraphicSettings::CGraphicSettings @6a2d80 dc, CGraphicSettings::SetQualityIndex @6a3a50 dc

## Measured


18 terrain manifests under World — `find ~/dv2-extract/World -path '*Meshes/Terrain/AssetDataDescriptors.xml' | wc -l`
