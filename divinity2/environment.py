from pathlib import Path

from . import docs

FILES = ("atmosphere.xml", "lights.xml", "ppsettings.xml", "shadowsettings.xml",
         "volumetricfogSettings.xml", "waterplanedata_v2.xml")

WIND = "windsettings.ini"

SETTINGS = "lightsettings.xml"

def _read(path: Path):
    node = docs.read(path)
    return None if node is None else docs.to_plain(node)


def _wind(path: Path) -> dict:
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
    from . import region as dv2_region

    root = Path(root)
    here = dv2_region.folder(root, region, sub)
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


def find(tree, name: str):
    if tree is None:
        return None
    for node in docs.walk(tree):
        if node["name"] == name:
            return node
    return None


# CAtmosphereSettingsFactory::GetSettingsMap @1156980 decomp
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

# CLocalAtmosphereSettingsCollection::LoadXML @7287d0 decomp
LOCAL_SHAPE = {"InnerRadius": 1.0, "OuterRadius": 1.0, "InnerTop": 1.0, "OuterTop": 1.0,
               "InnerBottom": 0.0, "OuterBottom": 0.0}


def _rgb(node, default=None):
    if node is None:
        return default
    return [docs.number(node["attrs"].get(k), 0.0) for k in "rgb"]


# CAtmosphereSettingsCollection::LoadXML @10a66d0 decomp
def _settings(collection) -> dict:
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


# CAtmosphereFloatSetting::Apply @109a870, CAtmosphere::Update @6d0fd0 decomp
def frame(read_out: dict) -> dict:
    atmosphere = read_out.get("atmosphere.xml")
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
    lit = frame(got)
    assert lit["settings"]["CFDepth"] == 0.123 and lit["settings"]["AmbientBrightness"] == 0.4, lit["settings"]
    zones = [n for n in docs.walk(got["atmosphere.xml"])
             if n["name"] == "atmosphere_localsettingscollection"]
    assert [z["attrs"]["Name"] for z in zones] == ["BC_Lava", "BC_Temple"], \
        [z["attrs"]["Name"] for z in zones]
    lava = {n["attrs"]["Name"]: n["attrs"].get("Value")
            for n in docs.walk(zones[0]) if n["name"] == "atmosphere_floatsetting"}
    assert lava["CFDepth"] == "0.047" and lava["HFDensity"] == "19", lava
    print(f"environment: {got['time']}, "
          f"{len(zones)} local volume(s), all checks pass")


if __name__ == "__main__":
    _selftest()
