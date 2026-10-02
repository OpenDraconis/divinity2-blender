# Regions

## Where a region's data lives

A region is a folder under `World/`; ground and built geometry are NIFs beside it, props, lights and trees are binary XML beside those; characters, items and triggers live with the episode and name their region in an attribute, which places them, not the folder — CRpgStats_V2_Character::LoadXML @83ce30, CRpgStats_V2_Item::LoadXML @8de5f0 decomp

Scenery is `World/<r>/<sub>/scenery.xml` named by `rpgstats_sceneryprototypes.xml`; characters are `Episodes/<e>/**/Characters/*.xml` named by `rpgstats_characterprototypes_visual.xml`; items are `Episodes/<e>/**/Items/*.xml` named by `rpgstats_itemprototypes.xml` then `..._itemvisualprototypes.xml`; triggers are `Episodes/<e>/Triggers/*.xml`; lights are `World/<r>/<sub>/Lights/<time>/lights.xml`; trees are `World/<r>/<sub>/trees.xml` named by `forest-settings.xml`; vegetation is `World/<r>/<sub>/Vegetation.nif` — CRpgStats_V2_Scenery::LoadXML @9952a0, CRpgStats_V2_Character::LoadXML @83ce30, CRpgStats_V2_Item::LoadXML @8de5f0, CGameLogic_Tree::LoadXML @a68b70 decomp

`CGameLogic_World::LoadXML` takes every `region` of `Worldregions.xml` with an implicit `Main` and its `subregion` children, in file order. A non-Main sub-region lives under `Subregions/` — CGameLogic_World::LoadXML @782380, CRegionVisualMan::PerformRegionSwap @6ba230 decomp

## Placements

Every placement is an NiPoint3 child (position) then an NiMatrix3 child (basis), in metres: `CRpgStats_V2_Scenery::LoadXML`, `CRpgStats_V2_Character::LoadXML`, `CRpgStats_V2_Item::LoadXML` and `CGameLogic_Tree::LoadXML` all take children[0] as the position and children[1] as the orientation. The binary stream stores children in reverse — CRpgStats_V2_Scenery::LoadXML @9952a0, CRpgStats_V2_Character::LoadXML @83ce30, CRpgStats_V2_Item::LoadXML @8de5f0, CGameLogic_Tree::LoadXML @a68b70 decomp

A tree's instance data is filled from `rand()/2^31`, so its three components are in [0,1] — CGameLogic_Tree::UpdateInstanceData @a686e0 decomp

## What a region node becomes

`CRegionVisual::ParseRegionNode` walks `StaticMeshes.nif` and decides per node — CRegionVisual::ParseRegionNode @6a3790 decomp:

- `CDummyGeometry` (RTTI): nothing, the function returns.
- `effectproxy = yes`: a particle system from `Win32\Effects\<EffectFile>` at the node's world transform with `CullingDistance`; the box is not drawn.
- `glowproxy`: a CGlowEffect.
- a name containing `PhysicsPROXY_`: a collision hull.
- `IsCubeMapPosition`, `CubemapPosition`: a cubemap probe.
- `IsItemPosition`, `ItemPosition`, `ItemPrototypeName`, `ItemCollectionName`: an item spawn.
- `IsStatic`, `ExternalAssetPath`, `ASSET`: a streamed asset reference.
- `TERRAIN_PATCH`: a terrain patch.
- `Imposter`: a billboard imposter.
- `River`, `WaterPlane`: a CWaterPlane.
- `decal`: a CDecalNode.
- `ANTIPORTAL_`, `antiportal`: a CAntiPortal.
- `DungeonPR`, `ENTRY-BOX`: an NiRoom or NiShell (the portal system).
- `ActiveDistance`: a distance.

`EffectFile` and `CullingDistance` are `key = value` lines in the node's UserPropBuffer read by `DivTools::CGBTools::GetExtraDataValue`; positions in the function are multiplied by `CNifManager::ms_fRescaleSize` — CRegionVisual::ParseRegionNode @6a3790, DivTools::CGBTools::GetExtraDataValue @108ab20 decomp

## Triggers

Teleport accepts only a Point or an Orientation trigger and takes region and sub-region from the trigger itself, which may lie in an unloaded sub-region; every `Trigger_base` names its SubRegion — CRpgStats_V2_Character::TeleportToTrigger @837cb0 decomp

## Lights

A point light's position is `translate` under its GBLight; a directional light has two angles; a spot light has an NiTransform — CLight::LoadXML @718f60 decomp

Directional and spot lights shine along column 0 of their basis: `NiDirectionalLight::UpdateWorldData` and `NiSpotLight::UpdateWorldData` copy `m_kWorldDir` from rotation column 0 — NiDirectionalLight::UpdateWorldData @509310, NiSpotLight::UpdateWorldData @5089f0 decomp

`CSpotLight::LoadXML` takes exactly two children, an NiTransform and a whole `point_light` (`CPointLight::LoadXML`); the inner point light is the spot, not a second light — CSpotLight::LoadXML @10b05d0, CPointLight::LoadXML @7137a0 decomp

Sun rotation: `CDirLight::UpdateVisual` copies MakeZRotation(angle_z) * MakeYRotation(angle_y). `NiMatrix3::MakeZRotation` writes [[c,s,0],[-s,c,0],[0,0,1]] and `MakeYRotation` [[c,0,-s],[0,1,0],[s,0,c]] (transposes of the textbook matrices); column 0, the light direction, is (cy*cz, -cy*sz, sy) — CDirLight::UpdateVisual @10ae6a0 decomp, NiMatrix3::MakeZRotation @52bee0, NiMatrix3::MakeYRotation @52be90 decomp

## Time settings

A sub-region's `lightsetting` entries are read in file order (`CGameLogic_SubRegion::LoadLightSettings`), each naming a folder under `Lights/`. `CGameLogic_SubRegion::Load` takes the asked one if listed (`HasTimeSetting`), else the first listed, else none; the asked one is the region's `timesetting` unless a time is wanted — CGameLogic_SubRegion::Load @898b70, CGameLogic_SubRegion::LoadLightSettings @898860 decomp

## Trees

Trees have no mesh: `model="BoxWood"` names a CTreeModel in `forest-settings.xml` whose model is a SpeedTree `.spt` (`__IdvSpt_02_`, a procedural definition); the runtime grows it at load — CSpeedTreeRT::LoadTree @bf4650, CTreeModel::LoadSptFile @1054280, CTreeModel::SetupBranchGeometry @1055d80, SetupLeafMeshGeometry, SetupFrondGeometry decomp

Tree size = rescaled.y * CTreeModel.size; rescaled.y = (1 - v) + instance.y * v * 2 for v = treesizevariation; instance.x is the rotation and instance.z the colour variation, both passed to the SpeedTree shader as a trig pair (`g_vTreeRotationTrig`) — CGameLogic_Tree::PreparePhysicsData @a688f0, CGameLogic_Tree::UpdateInstanceData @a686e0 decomp

## Vegetation

Vegetation is scattered by the engine; `Vegetation.nif` is the library (one NiNode per source file named by `sNifFile` in `vegetationtemplatedata.xml`); per-cell masks are `Vegetation/VM_<x>_<y>.tga` found by `CVegetationGridManager::GenerateVegetationGridEntryDescriptors`. The scatter is in vegetation.md — CVegetationGridManager::GenerateVegetationGridEntryDescriptors @6e8ed0 decomp
