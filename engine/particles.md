# Particle systems

A NiParticleSystem is an emitter; modifiers and a controller chain run each frame: `NiPSysUpdateCtlr::Update` -> `NiParticleSystem::Do_UpdateSystem` — NiPSysUpdateCtlr::Update @5b68d0, NiParticleSystem::Do_UpdateSystem @5cea50 decomp

A mesh emitter picks points on triangle shapes — NiPSysMeshEmitter::EmitFromFace @5bf390 decomp

A WaterSplash system is culled by `CheckWaterSplashEffect` and drawn again as `WaterSplashTriShape`, which hands an empty config so `SetupShaderMaps` falls back to normal map `FX_WaterSplash_A_NM` in shader slot 1 — CheckWaterSplashEffect @6cbe40, WaterSplashTriShape::SetupShaderMaps @116a0b0 decomp

Larian markers in a system's or its parent's UserPropBuffer: `CheckWaterSplashProperty` and `HasOrientationEffectProperty` (both ContainsNoCase), `CheckRefractionEffect` — CheckWaterSplashProperty @6cbde0, HasOrientationEffectProperty @6cbb70, CheckRefractionEffect @6cbd20 decomp

An extra-data value is the first quoted string after `key` in the buffer — DivTools::CGBTools::GetExtraDataValue @108ab20 decomp

A `RefractionEffect` buffer names the normal map and the power across and down, each 30 when absent — CheckRefractionProperty @6cbbc0 decomp

An effect proxy region node (`effectproxy = yes`) loads its system from `Win32\Effects\<EffectFile>` with `CullingDistance`, both `key = value` lines in the UserPropBuffer — CRegionVisual::ParseRegionNode @6a3790, DivTools::CGBTools::GetExtraDataValue @108ab20 decomp
