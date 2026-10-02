"""How a region is lit: the sky, the fog, the shadows, the wind.

Everything in `World/<region>/<sub>/Lights/<time>/` and the
`lightsettings.xml` beside it. These are settings files, not placements, and
the add-on interprets only a little of what they say -- so this carries them
across **whole** rather than picking fields out of them. `docs.to_plain`
keeps every element, every attribute and every value, under its recovered
name or under its hash where no name has been recovered, and the far side
takes what it can use.

What each file is, from the engine's own loaders:

| file | class | what it says |
|---|---|---|
| `atmosphere.xml` | `CAtmosphere::LoadXML` | the sky, the clouds, the skybox, the classic fog, 31 named settings and the local volumes that override them |
| `lights.xml` | `CLight::LoadXML` and friends | the sun and every point light, which `divinity2.region` already reads as placements |
| `ppsettings.xml` | `CPostProcessManager` | HDR, depth of field, light shafts |
| `shadowsettings.xml` | `CShadowMapRenderer::LoadXML` | three shadow maps: omni, character, cascaded |
| `volumetricfogSettings.xml` | `CVolumetricFogRenderer::LoadXML` | density, movement and colour |
| `waterplanedata_v2.xml` | `CWaterPlaneDataMan` | the water styles, read by `region.water_styles` |
| `windsettings.ini` | SpeedTree | how the wind moves branches and leaves; plain text, `key v1 v2 ...` |
| `lightsettings.xml` | -- | which time settings this region authors |

**The sky is four files deep.** `atmosphere.xml` names a skybox texture
(`sSurfaceTexture`), two cloud maps and two star maps, and each of them is a
`.dds` name for a file that is a NIF on disk, the same trap the terrain's
megatextures spring. `CSkyBox::LoadXML` reads `sSurfaceTexture`, `bEnabled`, `fRotation`
and `fHeight` and **never reads `sMeshName`**, which the files carry anyway.
"""

from pathlib import Path

from . import docs

#: The settings files beside a region, per time of day.
FILES = ("atmosphere.xml", "lights.xml", "ppsettings.xml", "shadowsettings.xml",
         "volumetricfogSettings.xml", "waterplanedata_v2.xml")

#: The one that is not binary XML.
WIND = "windsettings.ini"

#: The table of times the region authors, beside the `Lights` folder.
SETTINGS = "lightsettings.xml"

def _read(path: Path):
    node = docs.read(path)
    return None if node is None else docs.to_plain(node)


def _wind(path: Path) -> dict:
    """`windsettings.ini`: one key per line, then one or more numbers."""
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="latin-1").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        numbers = []
        for word in parts[1:]:
            try:
                numbers.append(float(word))
            except ValueError:
                numbers = None
                break
        if numbers:
            out[parts[0]] = numbers
    return out


def read(root, region: str, sub: str = "Main", time: str = "") -> dict:
    """Every settings file the region ships for one time of day.

    `time` empty means the one `Worldregions.xml` gives the region.
    """
    from . import region as dv2_region          # circular only at import time

    root = Path(root)
    here = dv2_region.folder(root, region, sub)
    # A sub-region need not list every hour -- see `region.time_setting`.
    time = dv2_region.time_setting(root, region, sub, time)

    out = {"time": time}
    if time:
        hour = here / "Lights" / time
        for name in FILES:
            found = _read(hour / name)
            if found is not None:
                out[name] = found
        out[WIND] = _wind(hour / WIND)
    settings = _read(here / SETTINGS)
    if settings is not None:
        out[SETTINGS] = settings
    return out


# ------------------------------------------------------------------ the sky

def find(tree, name: str):
    """The first element with this name anywhere in a read tree."""
    if tree is None:
        return None
    for node in docs.walk(tree):
        if node["name"] == name:
            return node
    return None


# ------------------------------------------------------------ the engine's frame

#: Every atmosphere setting and the value `CAtmosphereSettingsFactory::GetSettingsMap`
#: (@0x1156980, Dev Cut @0xc7e430) creates it with. A time setting's load makes a
#: new collection, so a name the file lacks has this value (none is missing in
#: the 170 shipped files). docs/sources.md, "Atmosphere defaults".
WHITE, BLACK = [1.0, 1.0, 1.0], [0.0, 0.0, 0.0]
SETTINGS_FACTORY = {
    "CFDepth": 0.1, "CFColor": WHITE, "CloudBrightness": 1.0, "CloudDensity": 0.2,
    "CloudShadowColor": BLACK, "CloudColor": WHITE, "HFDensity": 0.2, "HFHeight": -200.0,
    "HFWaveHeight": 1.0, "HFWaveSpeed": 1.0, "HFColor": WHITE, "PPSaturation": 1.0, "PPHue": 0.0,
    "PPBrightness": 1.0, "PPContrast": 1.0, "PPUnsharpMask": 0.0, "PFColor": BLACK, "PFStrength": 0.0,
    "SkySaturation": 1.0, "SkyHue": 0.0, "SkyBrightness": 1.0, "SkyContrast": 1.0, "SkyColor": BLACK,
    "GroundColor": BLACK, "GrassBrightness": 0.0, "DarkMapBrightness": 0.0, "AmbientBrightness": 0.0,
    "ColorCorrectSourceColor": WHITE, "ColorCorrectTargetColor": WHITE, "BloomScale": 0.0,
    "BrightpassOffset": 0.0, "BrightpassThreshold": 0.0, "TargetRangeSize": 0.0,
}

#: `CLocalAtmosphereSettingsCollection::LoadXML` @0x7287d0: the cylinder's
#: attributes and the value each takes when absent.
LOCAL_SHAPE = {"InnerRadius": 1.0, "OuterRadius": 1.0, "InnerTop": 1.0, "OuterTop": 1.0,
               "InnerBottom": 0.0, "OuterBottom": 0.0}


def _rgb(node, default=None):
    if node is None:
        return default
    return [docs.number(node["attrs"].get(k), 0.0) for k in "rgb"]


def _settings(collection) -> dict:
    """`CAtmosphereSettingsCollection::LoadXML` @0x10a66d0: `{name: (value,
    enabled)}` for the names the factory knows; unknown names are dropped."""
    out = {}
    for node in (collection or {"children": []})["children"]:
        name = node["attrs"].get("Name")
        if name not in SETTINGS_FACTORY:
            continue
        enabled = node["attrs"].get("Enabled") == "1"
        if node["name"] == "atmosphere_colorsetting":
            out[name] = (_rgb(find(node, "Color"), SETTINGS_FACTORY[name]), enabled)
        else:
            out[name] = (docs.number(node["attrs"].get("Value"), SETTINGS_FACTORY[name]), enabled)
    return out


def frame(read_out: dict) -> dict:
    """What the engine renders one time setting with, as plain data.

    - `settings`: the global atmosphere collection, all 33 values. **A global
      setting always applies**: `CAtmosphereFloatSetting::Apply` @0x109a870 never
      reads `Enabled` on it.
    - `locals`: each `atmosphere_localsettingscollection` with its cylinder and
      `{name: {value, enabled}}`; a disabled local setting contributes the
      global value. The camera-weighted blend runs per frame on the far side
      (`CAtmosphere::Update` @0x6d0fd0).
    - `globals`: `CLightManager::LoadXML` (Dev Cut @0xb78100) with its values
      for an absent attribute; `fEnvCubeMapIntensity` from the atmosphere
      element (ctor 1.0).
    - `sun`: `Sun/dir_light` with `CDirLight`'s first-load defaults (backlight
      black and 0, shadow bleeding 0.25); `active` false means the pre-pass
      draws hemisphere ambient only.
    - `hdr`: `ppsettings.xml` `CHDRPPEffect`.
    - `points`: `Lights`, every point light whole.
    """
    atmosphere = read_out.get("atmosphere.xml")
    # The global collection is the atmosphere element's own child; each local
    # carries another one inside it.
    top = find(atmosphere, "atmosphere") if atmosphere is not None else None
    main = next((c for c in (top or {"children": []})["children"]
                 if c["name"] == "atmosphere_settingscollection"), None)
    settings = dict(SETTINGS_FACTORY)
    settings.update({name: value for name, (value, _) in _settings(main).items()})

    locals_ = []
    for node in (top or {"children": []})["children"]:
        if node["name"] != "atmosphere_localsettingscollection":
            continue
        position = find(node, "Position")
        locals_.append({
            "name": node["attrs"].get("Name", ""),
            "position": [docs.number((position or {"attrs": {}})["attrs"].get(k), 0.0) for k in "xyz"],
            **{key: docs.number(node["attrs"].get(key), default) for key, default in LOCAL_SHAPE.items()},
            "settings": {name: {"value": value, "enabled": enabled}
                         for name, (value, enabled) in _settings(find(node, "atmosphere_settingscollection")).items()},
        })

    lights = find(read_out.get("lights.xml"), "light_manager")
    given = (find(lights, "GlobalSettings") or {"attrs": {}})["attrs"]
    globals_ = {
        "fGlobalNormalScale": docs.number(given.get("fGlobalNormalScale"), 1.0),
        "fGlobalFakeSpecularIntensity": docs.number(given.get("fGlobalFakeSpecularIntensity"), 1.0),
        "fGlobalFallOffIntensity": docs.number(given.get("fGlobalFallOffIntensity"), 0.5),
        # Applied only when >= 0; the engine starts at 0.
        "TreeLeafIntensity": max(docs.number(given.get("fLeafEmmisiveIntensity"), 0.0), 0.0),
        "fAttenuationTreshold": docs.number(given.get("fAttenuationTreshold"), 0.4),
        "fMaxShadowDistance": docs.number(given.get("fMaxShadowDistance"), 20.0),
        "fEnvCubeMapIntensity": docs.number((top or {"attrs": {}})["attrs"].get("EnvCubeMapIntensity"), 1.0),
    }

    sun = None
    dir_light = find(find(lights, "Sun"), "dir_light") if lights is not None else None
    if dir_light is not None:
        light = find(dir_light, "light") or {"attrs": {}}
        gb = find(dir_light, "GBLight") or {"attrs": {}, "children": []}
        a = dir_light["attrs"]
        sun = {
            "active": light["attrs"].get("m_bActive") == "1",
            "cast_shadows": light["attrs"].get("m_bCastShadows") == "1",
            "angle_y": docs.number(a.get("angle_y"), 0.0), "angle_z": docs.number(a.get("angle_z"), 0.0),
            "intensity": docs.number(gb["attrs"].get("dimmer"), 1.0),
            "colour": _rgb(find(gb, "diffuse_color"), WHITE),
            "specular_level": docs.number(light["attrs"].get("m_fSpecularLevel"), 1.0),
            "backlight_colour": [docs.number(a.get(f"backlight_{k}"), 0.0) for k in "rgb"],
            "backlight_intensity": docs.number(a.get("backlight_intensity"), 0.0),
            "shadow_bleeding": docs.number(a.get("shadowbleeding"), 0.25),
        }

    points = []
    for point in _all(find(lights, "Lights"), "point_light"):
        light = find(point, "light") or {"attrs": {}}
        gb = find(point, "GBLight") or {"attrs": {}, "children": []}
        points.append({
            "name": point["attrs"].get("Name", ""),
            "position": [docs.number((find(gb, "translate") or {"attrs": {}})["attrs"].get(k), 0.0) for k in "xyz"],
            "min_radius": docs.number(point["attrs"].get("m_fMinAttenuationRadius"), 0.0),
            "max_radius": docs.number(point["attrs"].get("m_fMaxAttenuationRadius"), 0.0),
            "dimmer": docs.number(gb["attrs"].get("dimmer"), 1.0),
            "colour": _rgb(find(gb, "diffuse_color"), WHITE),
            "active": light["attrs"].get("m_bActive") == "1",
            "record": {**point["attrs"], **{f"light.{k}": v for k, v in light["attrs"].items()}},
        })

    hdr = (find(read_out.get("ppsettings.xml"), "CHDRPPEffect") or {"attrs": {}})["attrs"]
    return {"settings": settings, "locals": locals_, "globals": globals_, "sun": sun,
            "points": points, "hdr": dict(hdr)}


def _all(tree, name: str):
    if tree is None:
        return []
    return [node for node in docs.walk(tree) if node["name"] == name]


def _selftest():
    import os
    game = os.environ.get("DV2_EXTRACT")
    if not game:
        print("set DV2_EXTRACT to run the check")
        return
    got = read(game, "Banditcamp", "Main")
    assert got["time"] == "Dawn", got["time"]
    assert "atmosphere.xml" in got and "shadowsettings.xml" in got
    assert got["windsettings.ini"]["MaxBendAngle"] == [35.0]
    # A global setting applies whatever its `Enabled` says: Banditcamp at dawn
    # has a warm classic fog, which reading `Enabled` threw away.
    lit = frame(got)
    assert lit["settings"]["CFDepth"] == 0.123 and lit["settings"]["AmbientBrightness"] == 0.4, lit["settings"]
    zones = [n for n in docs.walk(got["atmosphere.xml"])
             if n["name"] == "atmosphere_localsettingscollection"]
    assert [z["attrs"]["Name"] for z in zones] == ["BC_Lava", "BC_Temple"], \
        [z["attrs"]["Name"] for z in zones]
    # The lava pit is warmer and thicker than the temple: this is the fog the
    # add-on has been throwing away.
    lava = {n["attrs"]["Name"]: n["attrs"].get("Value")
            for n in docs.walk(zones[0]) if n["name"] == "atmosphere_floatsetting"}
    assert lava["CFDepth"] == "0.047" and lava["HFDensity"] == "19", lava
    print(f"environment: {got['time']}, "
          f"{len(zones)} local volume(s), all checks pass")


if __name__ == "__main__":
    _selftest()
