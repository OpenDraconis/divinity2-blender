# Static assets

Any node of `StaticMeshes.nif` whose name contains `ASSET` is a static asset — CRegionVisual::ParseRegionNode @6a3790 decomp

Its UserPropBuffer names the model, `AssetFile="StaticAssets/Aleroth/AL_House_C.nif"`; the key is the file name without folder and extension — CStaticAssetManager::Init @6fe830 decomp, CStaticAssetManager::Init @c06bf0 dc

Under its `DummyAsset` child one NiLODNode per model (`LODGroup01`, ...) holds level 0 inline and an empty stub for finer levels — CStaticAssetDataManager::RequestLoadData @73e040 decomp

Level n > 0 streams from `Win32/CompiledAssets/<asset>/<LODGroupNN>/<n>.nif`, whose node carries the stub's name; level names per asset come from `Win32/CompiledAssets/AssetDataDescriptors.xml`. The asset name is compared with NiStricmp (`AL_House_A_Piece_F` is the manifest's `AL_House_A_PIECE_F`). A stub fills only from its own asset's files — CStaticAssetDataManager::RequestLoadData @73e040, CollectLODNodeNames @73e310 decomp

With StaticAssetHighQuality on, the finest level is always requested and the finest loaded level is drawn — CStaticAsset::UpdateStreaming @742c60 decomp, CStaticAsset::EvaluateLODNode @742a40 decomp, CStaticAsset::UpdateStreaming @c772d0 dc

Region `StaticAssets.xml` gives each (asset, LOD group, placement) its switch distances in cm and whether it casts shadows; a placement the file does not describe casts shadows; a file name containing `_SHADOWDUMMY` is drawn only into shadows. `UpdateStreaming` compares the XML's distances, not the manifest's — CStaticAssetManager::LoadXML @6fe390, CStaticAssetManager::FindDescriptor @6fdfb0, CStaticAssetDescriptor::CStaticAssetDescriptor @740860 decomp

Region static kinds are loaded as static assets, and `SetupStandardData` runs on them with the region's own nodes and terrain — CStaticAssetDataManager, CShadingTools::SetupStandardData @6ce490 decomp

## Measured

6 `0.nif`, 296 `1.nif`, 164 `2.nif` under CompiledAssets — `for n in 0 1 2; do find ~/dv2-extract/Win32/CompiledAssets -name $n.nif | wc -l; done`

295 LODGroup folders — `find ~/dv2-extract/Win32/CompiledAssets -name 'LODGroup*' -type d | wc -l`
