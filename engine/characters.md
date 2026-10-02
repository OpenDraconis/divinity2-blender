# Characters, models and equipment

## The `.cat` and the shared rig

A `.cat` bundles a character: skeleton, mesh files, animation set and clips, each as an `MdlMan::` entry that keeps its pre-bundle path (`CSkeletonDataEntry`, `CAMDataEntry`, `CMeshDataEntry`, `CAnimationDataEntry`) — MdlMan::CModelTemplateDataEntry nif

`CAMDataEntry.binary_data` is a KFM without its header; `CAnimationDataEntry.controller_seq_list` holds the clips as NiControllerSequence — nif.xml nif

A character without a skeleton and clips shares the rig of their CModelPrototype. A prototype is the first segment of the mesh entries' paths (`HumanMale\Meshes\M_Torso_A.nif` is HumanMale); its files are in `Win32/Characters/<prototype>/`: `Skeleton.nif`, `<set>.kfm`, `<set>.kf`. `Attachables` is not a prototype, it is where weapons live — MdlMan::CModelPrototype::LoadBinary @c99900 decomp

The skeleton is pooled per prototype — MdlMan::CWrapperMan::GetWrapperInstance @c864d0 decomp

A character's own `.cat` can hold only variant clips (Black_Goblin: Stunned, Flee, Blind and deaths); the standing clip comes from the family's shared set. State name `Still` is `CGameLogic_FixedStrings::ms_kAnimation_Still`, beside `ms_kAnimation_F_Normal` and the movement set — CGameLogic_FixedStrings::InitStrings @79e0d0 decomp

The playable `.kf` files of a template: the character's own KFM is one bank of many; the rest come from its CModelPrototype's CKFMDescriptors, chosen per action bank. A descriptor matches when every property of the query shares a bit with the descriptor's; a key the descriptor lacks matches anything; when one bank finds nothing, `Default` is added to the query's SubClass and it is asked again, so a sub-class KFM hides the prototype's default — CKFMRegisterLayer::HandlePropertyChange @6c8ae0, CKFMRegisterLayer::CollectKFMDescriptors @6c8950, MdlMan::CProperty::CheckValues @471a80 decomp

CModelPrototype holds the CKFMDescriptors, each with a CPropertyGroup of masks over the CStringMapper enums — CKFMRegisterLayer::CollectKFMDescriptors @6c8950 decomp

For an NPC the action banks Idle (in peace) and Melee (in combat) are on; ComplexDialog, Ladder, Swim and Custom are never — CRpgStats_V2_Character::DecideAnimBanks @838440 decomp

## Plain assets

Everything other than a character (scenery, item, effect, flying fortress, compiled asset) is a plain NIF with one `CStreamableAssetData` root; see nif.md — CStreamableAssetData::LoadBinary @1063410 decomp

A compiled model is a `LODGroup` folder: `CompiledAssets/<asset>/<LODGroupNN>/<n>.nif`, the numbered files being its levels — CStaticAssetDataManager::RequestLoadData @73e040 decomp

## MdlManBinary.nif

`Win32/Characters/MdlManBinary.nif` holds the model manager's tables as `MdlMan::` blocks that nif.xml does not describe; the table is loaded beside the templates' folder — CMdlManMapper::Initialize @68a2e0 decomp

`entries`: CMeshEntry blocks by lower-case part name — string name, string texture base, string extra data, u8 search-extra-textures, u32 name id, link to property group. The engine re-binds a part's maps by the entry's texture base — MdlMan::CMeshEntry::LoadBinary @1092340, MdlMan::CMeshWrapper::SetupTexturingProperty @c9de80 decomp

`templates`: each CModelTemplate's slot assignments — u32 name, u32, u32 prototype, u32 properties, u32 count, then count pairs of sized strings (slot, entry) — MdlMan::CModelTemplate::LoadBinary @c9c8a0 decomp

`meshes`: each CMesh — u32 source file, u32 name, u8, u32 slot hash, u32 count, then count pairs of u32 hash and block link; links resolve to CMeshEntry blocks — MdlMan::CMesh::LoadBinary @c97ca0 decomp

`mesh_blocks`: a CMesh holds the node its file is named after, a skinned flag, an equipment type id and entries by name hash — MdlMan::CMesh::LoadBinary @c97ca0 decomp

`slots`: a CSlot block holds a name, the node a rigid part hangs under (`attach`), an id (the hash of the name), the equipment type ids it takes and linked CMesh blocks — MdlMan::CSlot::LoadBinary @1093080 decomp

A CModelPrototype holds its CSlot blocks and the slot ids in model order; a CModelTemplate holds slot-to-entry default pairs, an empty entry is not kept — MdlMan::CModelPrototype::LoadBinary @c99900, MdlMan::CModelTemplate::LoadBinary @c9c8a0 decomp

Name hash: h = (h*33 + c) mod 0xFFFFFFFF over the signed chars; a CMesh keys its entries by it and a CSlot's id is it — MdlMan::GetHashValue @c71ab0 decomp

Equipment part lookup: walk the prototype's slots (only the named slot, or every slot when the name is no slot of the prototype, GetSlotID 0), in each the linked meshes in order; the first CMesh whose entries hold the name hash wins. No property is matched on this path. The file is `<prototype>\Meshes\<node>.nif` for a skinned mesh and `Attachables\<node>.nif` for a rigid one, under `Win32/Characters`; the mesh's own file name is never loaded; a rigid part hangs under its slot's attach node — MdlMan::CModel::AttachPart @c79ce0, MdlMan::CModelPrototype::GetDescriptorByName @c99290, MdlMan::CSlot::GetDescriptor @1093030, MdlMan::CMesh::GetMeshEntry @c97a40, MdlMan::CModel::HandleObjectAdded @c7e160, MdlMan::CModel::SetupMeshData @c7ef20 decomp

Skinned equipment parts bind to the family skeleton by bone name — MdlMan::CModel::ProcessSkinnedGeometry @c7c4c0 decomp

## Skinning

Every skinned shape, heads and hair included, is skinned one way: bones bound by name to the family skeleton. The engine's bone matrices are formed in `NiDX9Renderer::CalculateBoneMatrices`; the formula equals v = sum_i w_i * W_i * B_i * v whenever Shape.Local * NiSkinData.skin_transform is the identity — MdlMan::CModel::ProcessSkinnedGeometry @c7c4c0, NiDX9Renderer::CalculateBoneMatrices @5e4250 decomp

In that formula B_i is `NiSkinData.bone_list[i].skin_transform` and W_i is the bone's world transform in the skeleton file; `NiSkinData.skin_transform` takes no part, it is the inverse of the shape node's own world transform — NiSkinData nif, NiDX9Renderer::CalculateBoneMatrices @5e4250 decomp

The skeleton file is the rest pose for every mesh of a character; a mesh file's copy of the skeleton is collapsed (every bone node at the origin) and gives only parentage — NiSkinData nif

Normals and binormals are skinned by the 3x3 of the same blended matrix, not its inverse transpose, with no renormalisation in the vertex program; the pixel program normalises — DivStandardMaterial::HandlePositionFragment @1132f50 decomp

## Weapons and slots

A weapon is a mesh entry whose path starts `Attachables` and has no skin; one bone carries it. Slot to node is `CRpgStats_V2_SlotMapManager::GetBoneNameForModelmanSlot`: handR is Bone_Weapon_01; weaponSlotBack is Bone_Weapon_02; handL and armL are Bone_Weapon_03; weaponSlotBack2 is Bone_Weapon_04; weaponSlotBack3 is Bone_Weapon_05; weaponSlotBack4 is Bone_Weapon_06; any other slot is the empty string — CRpgStats_V2_SlotMapManager::GetBoneNameForModelmanSlot @8e5850 decomp

The slots `armor`, `arms`, `body`, `claws`, `gloves`, `head`, `helmet`, `legs`, `pants`, `tail`, `torso` map to nothing: they swap a body mesh instead of carrying an object — CRpgStats_V2_SlotMapManager::GetBoneNameForModelmanSlot @8e5850 decomp

The slot and node strings are `CGameLogic_FixedStrings::InitStrings` constants (`ms_kMdlManNode_*` are the ones the model manager uses). The artists' spelling is the value, not the symbol: `ms_kMdlManNode_CastPrimary` holds "Dummy_Cast_Primary". Equipment slots are names of a place for an item and the table turns the ones that hold something into a node. — CGameLogic_FixedStrings::InitStrings @79e0d0 decomp

Name tables in InitStrings by prefix: `ms_kLoadSaveEntry_`, `ms_kLoadSaveTag_`, `ms_kSkillEffect_`, `ms_kMdlManNode_`, `ms_kAchievement_`, `ms_kStatusIcon_`, `ms_kSwoosh_`, `ms_kAnimation_`, `ms_kEffect_` — CGameLogic_FixedStrings::InitStrings @79e0d0 decomp

## Measured

324 character templates — `find ~/dv2-extract/Win32/Characters/Templates -name '*.cat' | wc -l`

46 family skeletons — `find ~/dv2-extract/Win32/Characters -iname skeleton.nif | wc -l`

295 LODGroup folders — `find ~/dv2-extract/Win32/CompiledAssets -name 'LODGroup*' -type d | wc -l`

1141 `ms_*` symbols in InitStrings — `awk -F'\t' '$1=="79e0d0"' $DV2_MEASURE/pdb/gup-decomp.tsv | grep -o 'ms_[A-Za-z0-9_]*' | sort -u | wc -l`

46 `ms_kMdlManNode_*` — `awk -F'\t' '$1=="79e0d0"' $DV2_MEASURE/pdb/gup-decomp.tsv | grep -o 'ms_kMdlManNode_[A-Za-z0-9_]*' | sort -u | wc -l`

485, 194, 146, 44, 37, 19, 15, 13 symbols for `ms_kLoadSaveEntry_`, `ms_kLoadSaveTag_`, `ms_kSkillEffect_`, `ms_kAchievement_`, `ms_kStatusIcon_`, `ms_kSwoosh_`, `ms_kAnimation_`, `ms_kEffect_` — the same command with each prefix in place of `ms_kMdlManNode_`
