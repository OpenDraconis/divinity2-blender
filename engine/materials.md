# Materials and render state

## Alpha, vertex colour, stencil and other properties

NiAlphaProperty flags layout: bit 0 blend enable; bits 1-4 source factor; bits 5-8 destination factor; bit 9 test enable; bits 10-12 test function; bit 13 no sorter — NiAlphaProperty nif

NiVertexColorProperty `vertex_mode` and `lighting_mode` are written only up to NIF 20.0.0.5 and read 0 at 20.3.0.9; the mode is in `flags`. The default property is `m_uFlags = 8`: source IGNORE, lighting EMI_AMB_DIF; nif.xml's "if not present vertex_mode=2" is the exporter's convention. LightingMode EMISSIVE lights with the emissive term alone — NiVertexColorProperty::NiVertexColorProperty @439a50 decomp

NiSpecularProperty's constructor sets `m_uFlags = 0`: absent means off — NiSpecularProperty::NiSpecularProperty @59e7f0 decomp

NiZBufferProperty's default is test on, write on, LESS_EQUAL — NiZBufferProperty::NiZBufferProperty @4456e0 decomp

TexDesc `Flags` packs the UV set (`Texture Index`), the filter mode and the clamp mode — TexturingMapFlags nif

## DivStandardMaterial

`DivStandardMaterial` reads the maps base, dark, detail, gloss, glow, normal, parallax; bump and decals are carried — MdlMan::CMeshWrapper::SetupGeometry @c9eca0, MdlMan::CMeshWrapper::SetupGeometry @c9e2e0 decomp

`MdlMan::CMeshWrapper::SetupGeometry` adds defaults to every geometry that does not carry its own (the file's value wins) and forces NiMaterialProperty ambient to white — MdlMan::CMeshWrapper::SetupGeometry @c9eca0, MdlMan::CMeshWrapper::SetupGeometry @c9e2e0 decomp

`HandlePreLightTextureApplication` inserts parallax, normal, dark, base, detail, decals, gloss, in that order — DivStandardMaterial::HandlePreLightTextureApplication @112d860 decomp

Texture arithmetic is in gamma space: every texture is sampled raw and the maths runs on encoded values — DivStandardMaterial::HandlePreLightTextureApplication @112d860 decomp

Albedo = base * dark^2 * fGlobalLightmapIntensity * 2 * detail; `HandleDarkMap` and `HandleLightMap` both insert MAP_DARK and the compiler merges the two samples into the square — DivStandardMaterial::HandleDarkMap @1126290, DivStandardMaterial::HandleLightMap @11262e0 decomp

Glow is added unlit, times ObjectHDRScale; colour = (MatDiffuse*light + MatEmissive) * albedo; shape colours stand in for the diffuse or emissive term and their alpha for the material's in the opacity (`HandleBaseMap` @1131ec0) — DivStandardMaterial::HandlePreLightTextureApplication @112d860 decomp

Parallax: uv' = uv + (P.rg*s - 0.5*s) * E.xy, E = normalize(mul(float3x3(T,B,N), V)) the tangent-space eye vector, s the map's offset; the parallax map's UV set maps are read at uv' — DivStandardMaterial::HandlePreLightTextureApplication @112d860 decomp

Gates in `DivStandardMaterial::GenerateDescriptor`: specular is NiSpecularProperty flags & 1 (off: MatSpecular 0, no light, pre-pass or fake specular, gloss map not inserted); fake specular is forced on unless the shape blends ONE/ONE, then `UseFakeSpecular` decides; environment is `UseEnvMapping` true, the cube times `fEnvCubeMapIntensity` masked by the gloss map; fall-off is `EnableFallOff` true; fog is off when `CanBeFogged` is false or the shape blends ONE/ONE; vertex colours are ignored by default, AMB_DIFF replaces diffuse and ambient, EMISSIVE replaces emissive, LIGHTING_E means no light — DivStandardMaterial::GenerateDescriptor @1135a00 decomp, DivStandardMaterial::GenerateDescriptor @40e020 dc

A part whose CMeshEntry extra data names `UseFakeSpecular` gets that boolean, true, unless the geometry carries one — FUN_00dc0f60 @dc0f60 dc

`CShadingTools::SetupStandardData` (@6ce490, @ba4a00 dc) runs on region, static-asset and terrain geometry and overwrites EnableFallOff (false), FallOffPower (2) and FallOffColor (0) whatever the file says — CShadingTools::SetupStandardData @6ce490 decomp

Binormal: the engine's normal-map frame uses the first per-vertex block after the normals (nif.xml `Tangents`); the stored tangent is never read. In the Dev Cut the binormal is float4 whose w is `DIV2 Floats` (+1 where the shape has none), the tangent is cross(N,B)*w, "should be -1 when mirrored"; the sign array is read when the file's user version is above 0x2ffff — NiD3DShaderDeclaration::PackEntry @6176a0 decomp, NiGeometryData::LoadBinary @586670 decomp, NiD3DShaderDeclaration::PackEntry @5f7eb0 dc, NiGeometryData::LoadBinary @561130 dc, packing function @5e06c0 dc

The binormal runs along +v of the file; the file's v runs down — NiD3DShaderDeclaration::PackEntry @6176a0 decomp

Skinned normals use the 3x3 of the blended bone matrix and the sign is not transformed — DivStandardMaterial::HandlePositionFragment @1132f50 decomp

`CLarianMaterialLibrary::RegisterGlobalShaderConstants` holds each global's default value until a region's settings set it — CLarianMaterialLibrary::RegisterGlobalShaderConstants @1125020 decomp

## Character part maps

A character part's maps are bound by its CMeshEntry texture base plus the slot suffix (`ms_pacTextureExtensions` @13ee630: `_DM`, `_SM`, `_GM`, `_NM`), ignoring the names the mesh carries; the `.cat` build clears every map but base and glow (`RemoveNonBaseTextures`). A name the engine does not know leaves base `_black` and removes any other slot; a normal map is removed on geometry without normals and binormals. A new map is WRAP_S_WRAP_T, FILTER_BILERP, UV set 0; an existing map keeps its flags — MdlMan::CMeshWrapper::SetupTexturingProperty @c9de80, MdlMan::CModelTemplateDataEntry::RemoveNonBaseTextures @ca1810 decomp

## Water

A node marked `WaterPlane` in its UserPropBuffer (own line) makes `CRegionVisual::ParseRegionNode` build a CWaterPlane; the plane is geometry in `StaticMeshes.nif` and its only texture is `_Gray.tga`. Style comes from `waterplanedata_v2.xml`; the entry's `WaterColor` is listed first and `FogColor` (the water's tint) second — CRegionVisual::ParseRegionNode @6a3790 decomp

`waterplanedata_v2.xml` is read from the time setting's folder (`CRegionVisual::ApplyCurrentTimeSettings` -> `CWaterRenderer::UpdateTimeSettings`), merged by name, a later entry overwrites the entry before it; a plane matches by exact name (NiStringEqualsFunctor) or takes the constructor defaults; with no file the engine keeps what it had (first load: WATER_DEFAULTS) — CWaterPlaneDataMan::LoadXML @10b7c60, CWaterPlaneDataMan::AddWaterPlaneData @10b7aa0, CWaterPlaneData::CWaterPlaneData @10a8a90 decomp

## Terrain material (RenderMethod 1)

The ground is `DTS_PLPMaterial` for colour and `DTS_MRTMaterial` for the normal the light pre-pass reads. Up to eight heap rows chain; row r reads channel r%4 of alpha map r/4 on UV set 0, row 0 painted at 1. From the highest row down each takes what the running weight has left: diff = lerp(D, diff, acc) while acc<1 and paint>0, normal with the same weights, acc += w, w raised by the noise in its composite's blue (*15). Layers tile on UV set 1. No parallax and no layer gloss — CTerrainPatchLOD::AttachMaterial @753950 decomp, CTerrainPatchLOD::RecreatePreLightPassExtraData @753ea0 decomp, CTerrainPatchLOD::RecreatePreLightPassPropertyState @755530 decomp, CDivTerrainSplatPreLightPassMaterial::GenerateDescriptor @110c1c0 decomp, CTerrainSplatRenderer::CTerrainSplatRenderer @bc9310 dc, CTerrainPatchLOD::AttachMaterial @c88700 dc, CTerrainPatchLOD::RecreatePreLightPassPropertyState @c8a2c0 dc

The megatexture replaces the splat past `g_TerrainSplatRadius`, fading in over `g_TerrainSplatBlendRadius`: lerp(mega, splat, (R-d)/Bd); its normal never reaches the light; its gloss (alpha) lights only past the band. Normal: x from alpha, y from green, tangent cross(B,N) with no sign — CDivTerrainSplatMRTMaterial::HandleBlendSplatAndMega @10ff770, CDivTerrainSplatPreLightPassMaterial::HandlePreLightTextureApplication @110f280 decomp

Alpha maps are clamped on UV set 0, layers and composites wrapped on UV set 1, the megatexture clamped on UV set 0 — CTerrainPatchLOD::RecreatePreLightPassPropertyState @755530 decomp, CTerrainPatchLOD::RecreatePreLightPassPropertyState @c8a2c0 dc

Composite slots: the texture side binds slots 0..3 to the rows, in row order, that have a `_CM` and any of UseGloss, UseNoiseBlending, UseParallax (@c8a69c to @c8a6fa dc, GUP @755530); the shader side gives a row with UseNoiseBlending the next bound slot, counting noise rows only (@48e6a0 dc). Where a row flags gloss or parallax without noise the two disagree and a noise row reads the composite of a row before it — CTerrainPatchLOD::RecreatePreLightPassPropertyState @755530, CDivTerrainSplatPreLightPassMaterial::GenerateDescriptor @110c1c0 decomp
