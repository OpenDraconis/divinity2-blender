# Animation

## Clips and splines

A clip stores the control points of a cubic B-spline quantised to 16-bit integers, not a key per frame; the interpolators are `NiBSplineCompTransformInterpolator` — NiBSplineCompTransformInterpolator nif

A track whose handle is 0xFFFF (`NO_HANDLE`) is not animated; the interpolator's own static transform (NiQuatTransform) is the value for the whole clip — NiBSplineCompTransformInterpolator nif

B-splines are cubic (degree 3); control points are not on the curve, each span blends four of them — NiBSplineBasis<float,3>::Compute @652dc0 decomp

Knots are open uniform and clamped: 0,0,0,0,1,...,n-4,n-3,n-3,n-3,n-3 over n points; the curve starts on the first point and ends on the last; the first and last spans weigh with 1 and 1/2, inner spans with 1/2 and 1/3 — NiBSplineBasis<float,3>::Compute @652dc0 decomp

A component the file does not carry is written as -FLT_MAX; `trs_valid` is an empty array at NIF 20.3.0.9, so the sentinel is the only indicator — trs_valid nif

A component a track does not state keeps the bone's rest value; the engine writes no INVALID_TRANSLATE or INVALID_ROTATE component — NiMultiTargetTransformController::Update @63e070 decomp

An unskinned asset's node tree is moved by sequences whether or not any shape is skinned — CStreamableAssetData::GetActorManager @1063180, NiMultiTargetTransformController::Update @63e070 decomp

## Keys

Transform interpolation: each of translation, rotation and scale that has keys is interpolated at the sequence time; one without keys keeps the interpolator's own value — NiTransformInterpolator::Update @635cb0 decomp

Key arrays: one key holds; otherwise the two keys around the time are found and the time normalised between them goes to the key type's Interpolate. Before the first key the curve of the first two keys is carried backwards; past the last key the engine reads past its array — NiPosKey::GenInterp @620540, NiFloatKey::GenInterp @621b70, NiRotKey::GenInterp @6250c0 decomp

Hermite key types (Bezier and TCB scalar) use one formula; `forward` is the engine's `m_InTan`, `backward` is `m_OutTan` — NiInterpScalar::Bezier @65cd90, NiInterpScalar::TCB @65ce00, NiBezPosKey::Interpolate @6264b0, NiTCBPosKey::Interpolate @623d20, NiBezPosKey::FillDerivedVals @626710, NiTCBPosKey::FillDerivedVals @6241c0, NiBezPosKey::LoadBinary @626370, NiTCBFloatKey::FillDerivedVals @61ed20 decomp

`NiBezFloatKey::LoadBinary` reads `m_fInTan` then `m_fOutTan`; float keys are [time, value] (linear), [time, value, in, out] (quadratic) or [time, value, t, b, c] (TBC) — NiBezFloatKey::LoadBinary @625de0 decomp

TCB keys carry derived values over their neighbours; the first and last key mirror their one neighbour at time step 1. The file holds tension, continuity, bias in that order — NiTCBPosKey::CalculateDVals @623f80, NiTCBPosKey::LoadBinary @624680 decomp

Quaternion keys: FillDerivedVals turns each key to the side of the one before it and clamps w to [-1,1]; LINEAR slerps, TBC squads between intermediates; the first key is its own predecessor and the last its own successor — NiRotKey::FillDerivedVals @625450, NiLinRotKey::Interpolate @620cd0, NiTCBRotKey::CalculateDVals @6211b0, NiTCBRotKey::FillDerivedVals @621430 decomp

Quaternion helpers are wxyz: Slerp is a counter-warped lerp, fast-normalised; operator* is Hamilton — NiQuaternion::CounterWarp @5817d0, NiQuaternion::Slerp @581970, NiQuaternion::Squad @581c10, NiQuaternion::operator* @581b50, NiQuaternion::Log @581cb0, NiQuaternion::Exp @5818a0 decomp

FastNormalize constants are set by static initialisers at 0x11bd850 and 0x11bd870 from the doubles at 0x1208ec8 and 0x1208ef0; `NiQuaternion::ms_fEpsilon` is 0x3a83126f — NiQuaternion::FastNormalize @5816d0 decomp

Euler rotation keys: each axis's float keys are read at the time, an axis without keys is 0, and the three half angles make a quaternion — NiEulerRotKey::Interpolate @61f530 decomp

## Text keys

Every clip is bracketed by the text keys `start` and `end` — NiTextKeyExtraData nif

`morph:` keys are Gamebryo's: the same label on a walk and a run marks the frames to line up when blending — NiControllerSequence::FindCorrespondingMorphFrame @648320, NiControllerSequence::VerifyMatchingMorphKeys @646ea0 decomp

`eq=<slot>:<item>` puts an item in a slot and `ue=<slot>` takes it out; the slot goes to a bone through the engine's slot table (see characters.md) — CRpgStats_V2_SlotMapManager::GetBoneNameForModelmanSlot @8e5850 decomp

`s=<name>` plays a sound; a bare `v=-5` ramps a value as a body falls — NiTextKeyExtraData nif

## Sequences of an effect, scenery or fortress

`CStreamableAssetData` holds a node tree and, when its flag is set, an embedded KFM whose animations name the sequences in the block's own list; the actor manager is built from it and every controlled block drives the node it names — CStreamableAssetData::GetActorManager @1063180 decomp

The engine plays a sequence by KFM event code — CAnimationPlayer::PlayAnimation @6cb270 decomp

NiBillboardNode reads its mode into the flags; RotateToCamera takes the low three bits — NiBillboardNode::LoadBinary @5accc0, NiBillboardNode::RotateToCamera @5ac4b0 decomp

`NiTextureTransformController::Update` sets one member of the map's NiTextureTransform to the interpolated value each frame (making a MAYA transform first when there is none); the sample time is `ComputeScaledTime` of flags, frequency, phase, start and stop — NiTextureTransformController::Update @636840, NiTimeController::ComputeScaledTime @54cd60 decomp

`NiTextureTransform::UpdateMatrix` gives the 2x3 matrix taking file UV (u,v,1) to the sampled one, for each of three methods; rows are [m00,m01,m02] and [m10,m11,m12] — NiTextureTransform::UpdateMatrix @533fd0 decomp

## KFM (animation set)

A KFM ties a family together: which skeleton its clips were made for, which `.kf` files hold them, and how animations transition. One exists per weapon set; a copy of the character's own is bundled in the `.cat` as `MdlMan::CAMDataEntry` ("a KFM without header") — CAMDataEntry nif

Divinity II writes KFM version 2.2.0.0b (0x0202000B) — kfm.xml nif

Layout: Kfm = header string, unknown byte, NIF file name, master, 2 ints, 2 floats, animation count, animations, 1 int; Animation = event code, KF file name, index, transitions; Transition = animation, type and, unless the type is bare, duration, intermediate animations, text key pair count — kfm.xml nif

An animation carries no name at this version, only an event code (Name is `ver2="16927488"`); clip names come from the NiControllerSequence blocks in the `.kf` — kfm.xml nif

From 2.0.0.0b onwards the intermediate animation carries an unknown int — kfm.xml nif

An embedded KFM animation's `index` is the sequence's place in the block's list and its event code is the id the engine plays it by — CAnimationPlayer::PlayAnimation @6cb270 decomp

## Dialog packs

A `.dialog` pack is a KF of many sequences, each with one NiStringExtraData `OriginalFilename` = `<family>\Animations\Custom\<clip>.kf`; the engine finds a clip by that string, not by the sequence name. nif.xml reads that extra data as `DIV2 Ints` — MdlMan::CDialogWrapper::SetSequences @ca0aa0, MdlMan::CDialogWrapper::GetSequence @ca0840 decomp

## Measured

KFM sets that parse to the exact last byte with bare = {5}: 77 of 121 — `cd ~/dv2-extract && python3 -c "import importlib.util as u,glob;s=u.spec_from_file_location('kfm','$HOME/divinity2-blender/divinity2/kfm.py');k=u.module_from_spec(s);s.loader.exec_module(k);k.BARE_TRANSITIONS=frozenset({5});print(sum(k.read(open(f,'rb').read()).complete for f in glob.glob('Win32/Characters/*/*.kfm')))"`

KFM sets that parse to the exact last byte with bare = {4, 5}: 105 of 121 — the same command with `frozenset({4,5})`

KFM files in the install: 121 — `find ~/dv2-extract/Win32/Characters -name '*.kfm' | wc -l`
