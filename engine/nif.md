# NIF files and the scene graph

Models are NIF 20.3.0.9 with user version 0x20000 or 0x30000; the extensions are `nft`, `item` and `cat` — version V20_3_0_9_DIV2 nif

The Divinity fields (`div_2_floats` on geometry data, `div_2_ints` and `div_2_ref` on a controller sequence) are part of the V20_3_0_9_DIV2 layout — nif

`NiTriShapeData.has_uv` reads 0 at NIF 20.3.0.9; the UV count is `data_flags.num_uv_sets` — has_uv, data_flags nif

NIF puts the UV origin top left; UV set 1 carries the terrain splat layers — TexturingMapFlags nif

`CNifManager::CNifManager` sets `ms_fRescaleSize` to the global config's `world_scale` and `ms_fInvRescaleSize` to its inverse — CNifManager::CNifManager @10cddb0 decomp

The scale that reaches the world sits on the tree's root node: a character's `Scene Root` is 1.0, every scenery, item, effect and fortress root carries 0.01 — NiAVObject scale nif

The `worldScale` float next to shapes is a shader input, not a unit: `DivStandardMaterial::HandleNormalMap` binds it beside LocalScale and `CShadingTools::SetupStandardData` overwrites the authored value with 1.0 before drawing — CShadingTools::SetupStandardData @6ce490 decomp

Every asset other than a character is a plain NIF with one `CStreamableAssetData` block at the root: a link to the NiNode root, a flag byte, and, when the flag is set, an embedded KFM handed to `DivTools::CKFMToolStreamer::LoadBinaryStream` — CStreamableAssetData::LoadBinary @1063410 decomp

`CStreamableAssetData::GetNIFRoot` returns `m_spNIFRoot` and nothing else; the geometry is in the file — CStreamableAssetData::GetNIFRoot @1063160 decomp

## Walking the tree

A node's world transform is its translation, rotation and one uniform scale float multiplied onto the parent's — NiAVObject::UpdateWorldData @536970 decomp

Bit 0 of a node's flags is APP_CULLED: `NiAVObject::GetAppCulled` is `return this->m_uFlags & 1;`. A culled node takes its subtree. Physics and destruction proxies sit beside real geometry this way — NiAVObject::GetAppCulled @443db0 decomp

A shape is drawn at its parent node's world transform, so it moves when a clip moves that node — NiAVObject::UpdateWorldData @536970 decomp

Render state attaches to a node and a shape inherits from the nearest ancestor that carries one: `NiAVObject::UpdateProperties` walks upward, `PushLocalProperties` copies the inherited state and writes each local property into the one slot its type owns, the nearest wins. NiPropertyState has one slot each for alpha, material, stencil, specular, shade, dither, fog — NiAVObject::PushLocalProperties @535af0 decomp

A shape with no NiTexturingProperty is not drawn: `CShadingTools::SetupStandardData` tests `NiAVObject::GetProperty(8)` (the texturing slot) and sets `m_uFlags |= 1` (APP_CULLED) where it is missing; the same for a shape whose data carries no UVs (`m_usDataFlags & 0x3f`). `CRegionVisual::ParseRegionNode`, `CStaticAssetDataManager` and the terrain manager all call SetupForwardShadingMaterial. Terrain patches are textured from Terrain.xml; `CTerrainPatchLOD::RecreateForwardShadingPropertyState` builds their state afterwards — CShadingTools::SetupStandardData @6ce490 decomp

Markers in a region node's NiStringExtraData: `effectproxy = yes` loads a particle system from `Win32\Effects\` and the box is never drawn; `glowproxy` makes a CGlowEffect; a node name containing `PhysicsPROXY_` is a collision hull (`NiString::Contains(name, "PhysicsPROXY_", 0, 13)`). Markers are inherited by everything beneath — CRegionVisual::ParseRegionNode @6a3790 decomp

## Level of detail

NiLODNode is a NiSwitchNode: one child is active — NiLODNode nif

Region geometry uses NiLODNode with NiRangeLODData, one camera-distance range per child — NiRangeLODData nif

## Measured

1695 scenery files — `find ~/dv2-extract/Win32/Scenery -name '*.item' | wc -l`

886 item files — `find ~/dv2-extract/Win32/Items -name '*.item' | wc -l`

378 effect files — `find ~/dv2-extract/Win32/Effects -name '*.item' | wc -l`

21 flying-fortress files — `find ~/dv2-extract/Win32/FlyingFortresses -name '*.item' | wc -l`
