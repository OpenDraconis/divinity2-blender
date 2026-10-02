# Environment and atmosphere

Files under `World/<region>/<sub>/Lights/<time>/`: `atmosphere.xml` (CAtmosphere::LoadXML: sky, clouds, skybox, classic fog, 31 named settings, local volumes); `lights.xml` (CLight::LoadXML: the sun and every point light); `ppsettings.xml` (CPostProcessManager: HDR, DoF, light shafts); `shadowsettings.xml` (CShadowMapRenderer::LoadXML: three shadow maps, omni, character, cascaded); `volumetricfogSettings.xml` (CVolumetricFogRenderer::LoadXML: density, movement, colour); `waterplanedata_v2.xml` (CWaterPlaneDataMan); `windsettings.ini` (SpeedTree plain text, `key v1 v2 ...`); `lightsettings.xml` (which time settings are authored) — CAtmosphere::LoadXML @6d1620, CLight::LoadXML @718f60, CShadowMapRenderer::LoadXML @6c5550, CVolumetricFogRenderer::LoadXML @6d58b0 decomp

The sky is four files deep: `atmosphere.xml` names a skybox texture (`sSurfaceTexture`), two cloud maps and two star maps. `CSkyBox::LoadXML` reads `sSurfaceTexture`, `bEnabled`, `fRotation` and `fHeight` and never reads `sMeshName` — CSkyBox::LoadXML @725090 decomp

Every atmosphere setting starts with the value `CAtmosphereSettingsFactory::GetSettingsMap` creates it with (identical in both builds); `CAtmosphere::Reload` makes a new collection per time setting, so a name a file lacks keeps that value — CAtmosphereSettingsFactory::GetSettingsMap @1156980 decomp, CAtmosphere::Reload @6d0e00 decomp, CAtmosphereSettingsFactory::GetSettingsMap @c7e430 dc

`CAtmosphereSettingsCollection::LoadXML` sets a value only if the name is in the factory's map and drops unknown names; the collection is {name: (value, enabled)}; the global collection holds all 33 values — CAtmosphereSettingsCollection::LoadXML @10a66d0 decomp

A global setting always applies: `CAtmosphereFloatSetting::Apply` never reads Enabled. A disabled local setting contributes the global value. Settings blend per frame by camera weight. The global collection is the atmosphere element's own child and each local volume carries another inside. A value applies only when >= 0, and the engine starts at 0 — CAtmosphereFloatSetting::Apply @109a870, CAtmosphere::Update @6d0fd0 decomp

A local volume is a cylinder with its own attribute defaults — CLocalAtmosphereSettingsCollection::LoadXML @7287d0 decomp

`CLightManager::LoadXML` (@b78100 dc) gives defaults for absent attributes; `fEnvCubeMapIntensity` comes from the atmosphere element (constructor 1.0). The sun is `Sun/dir_light` with CDirLight first-load defaults (backlight black and 0, shadow bleeding 0.25); `active` false means the pre-pass draws hemisphere ambient only. `ppsettings.xml` is read by CHDRPPEffect — CLightManager::LoadXML @6b73b0 decomp

A sub-region lists the time settings that it authors; it need not list every hour — CGameLogic_SubRegion::LoadLightSettings @898860 decomp
