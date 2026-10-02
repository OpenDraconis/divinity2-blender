from dataclasses import dataclass

DRAW_BOTH = 3

IGNORE = 0
EMISSIVE = 1
AMB_DIF = 2

FACTORS = (
    "ONE", "ZERO", "SRC_COLOR", "INV_SRC_COLOR", "DST_COLOR", "INV_DST_COLOR",
    "SRC_ALPHA", "INV_SRC_ALPHA", "DST_ALPHA", "INV_DST_ALPHA", "SRC_ALPHA_SAT",
)

FUNCTIONS = (
    "ALWAYS", "LESS", "EQUAL", "LESS_EQUAL", "GREATER", "NOT_EQUAL",
    "GREATER_EQUAL", "NEVER",
)


@dataclass
class Alpha:
    blending: bool = False
    source: str = "ONE"
    destination: str = "ZERO"
    testing: bool = False
    function: str = "ALWAYS"
    threshold: int = 0

    @property
    def additive(self) -> bool:
        return self.blending and self.source == "ONE" and self.destination == "ONE"


def _name(table, index: int, fallback: str) -> str:
    return table[index] if 0 <= index < len(table) else fallback


def alpha(block) -> Alpha:
    flags = int(block.flags)
    return Alpha(
        blending=bool(flags & 1),
        source=_name(FACTORS, (flags >> 1) & 0xF, "ONE"),
        destination=_name(FACTORS, (flags >> 5) & 0xF, "ZERO"),
        testing=bool((flags >> 9) & 1),
        function=_name(FUNCTIONS, (flags >> 10) & 0x7, "ALWAYS"),
        threshold=int(block.threshold),
    )


DEFAULT_VERTEX_COLOUR_FLAGS = 8

LIGHT_EMISSIVE = 0


def vertex_colour(block) -> int:
    if block is None:
        return (DEFAULT_VERTEX_COLOUR_FLAGS >> 4) & 3
    return int(block.flags.source_vertex_mode)


def lighting_mode(block) -> int:
    if block is None:
        return (DEFAULT_VERTEX_COLOUR_FLAGS >> 3) & 1
    return int(block.flags.lighting_mode)


def two_sided(block) -> bool:
    return block is not None and int(block.draw_mode) == DRAW_BOTH


MAPS = ("base", "dark", "detail", "gloss", "glow", "bump_map", "normal", "parallax",
        "decal_0", "decal_1", "decal_2", "decal_3")

NORMAL_TYPES = {"FMT_DXT1": "AG", "FMT_DXT5": "AG", "FMT_DXN": "RG"}

EXTRA_DEFAULTS = {"ObjectNormalScale": 1.0, "ObjectHDRScale": 1.0,
                  "FallOffPower": 1.0, "FallOffColor": [0.0, 0.0, 0.0]}


def _colour(c) -> list:
    return [float(c.r), float(c.g), float(c.b)] + ([float(c.a)] if hasattr(c, "a") else [])


def _map(desc) -> dict:
    flags = desc.flags
    out = {
        "file": str(desc.source.file_name) if desc.source is not None else None,
        "uv_set": int(flags.texture_index),
        "filter": str(flags.filter_mode.name),
        "clamp": str(flags.clamp_mode.name),
    }
    if getattr(desc, "has_texture_transform", False):
        out["transform"] = {
            "translation": [float(desc.translation.u), float(desc.translation.v)],
            "scale": [float(desc.scale.u), float(desc.scale.v)],
            "rotation": float(desc.rotation),
            "method": str(desc.transform_method.name),
            "center": [float(desc.center.u), float(desc.center.v)],
        }
        out["transform"]["matrix"] = uv_matrix(out["transform"])
    return out


# NiBezFloatKey::LoadBinary @625de0 decomp
def _float_keys(interpolator) -> dict:
    data = getattr(getattr(interpolator, "data", None), "data", None)
    if data is None or not int(data.num_keys):
        return {"type": None, "keys": [], "value": float(getattr(interpolator, "value", 0.0))}
    kind = data.interpolation.name
    keys = []
    for k in data.keys:
        row = [float(k.time), float(k.value)]
        if kind == "QUADRATIC_KEY":
            row += [float(k.forward), float(k.backward)]
        elif kind == "TBC_KEY":
            row += [float(k.tbc.t), float(k.tbc.b), float(k.tbc.c)]
        keys.append(row)
    return {"type": kind, "keys": keys}


# NiTextureTransformController::Update @636840 decomp, NiTimeController::ComputeScaledTime @54cd60 decomp
def _texture_controllers(texturing, maps: dict, shader_maps: list) -> None:
    ctlr = getattr(texturing, "controller", None)
    while ctlr is not None:
        if type(ctlr).__name__ == "NiTextureTransformController":
            flags = ctlr.flags
            index = int(ctlr.texture_slot)
            entry = {
                "member": ctlr.operation.name,
                "cycle": flags.cycle_type.name, "anim": flags.anim_type.name,
                "backwards": bool(flags.play_backwards), "active": bool(flags.active),
                "frequency": float(ctlr.frequency), "phase": float(ctlr.phase),
                "start": float(ctlr.start_time), "stop": float(ctlr.stop_time),
                "interpolator": type(ctlr.interpolator).__name__,
                "slot": index, "shader_map": bool(ctlr.shader_map),
                **_float_keys(ctlr.interpolator),
            }
            if ctlr.shader_map:
                target = next((m for m in shader_maps if m["id"] == index), None)
            else:
                target = maps.get(MAPS[index]) if index < len(MAPS) else None
            if target is not None:
                target.setdefault("controllers", []).append(entry)
        ctlr = getattr(ctlr, "next_controller", None)


# NiTextureTransform::UpdateMatrix @533fd0 decomp
def uv_matrix(transform: dict) -> list:
    from math import cos, sin
    c, s = cos(transform["rotation"]), sin(transform["rotation"])
    (tx, ty), (sx, sy), (cx, cy) = transform["translation"], transform["scale"], transform["center"]
    method = transform["method"]
    if method == "MAYA_DEPRECATED":
        dx, dy = tx - cx, ty - cy
        return [[c * sx, -s * sy, dy * -s + c * dx + cx], [s * sx, sy * c, cy + s * dx + c * dy]]
    if method == "MAYA":
        dy = 1.0 - (ty + cy)
        return [[c * sx, sy * -s, (tx - cx) * c + dy * s + cx],
                [-s * sx, -c * sy, c * dy + (cx - tx) * s + cy]]
    dy, dx = ty - cy, -cx - tx
    return [[c * sx, sx * s, (dx * c + dy * s) * sx + cx], [-s * sy, sy * c, (c * dy - s * dx) * sy + cy]]


def _extra(block):
    kind = type(block).__name__
    if kind in ("NiFloatExtraData", "NiIntegerExtraData", "NiBooleanExtraData"):
        return block.float_data if kind == "NiFloatExtraData" else (
            int(block.integer_data) if kind == "NiIntegerExtraData" else bool(block.boolean_data))
    if kind == "NiColorExtraData":
        return _colour(block.data)
    if kind == "NiStringExtraData":
        return str(block.string_data)
    return {"unread": kind}


# CMeshWrapper::SetupTexturingProperty @c9de80 decomp
PART_SLOTS = {"base": "_DM", "gloss": "_SM", "glow": "_GM", "normal": "_NM"}

def rebind(maps: dict, entry: dict, known, has_nbt: bool) -> dict:
    out = dict(maps)
    for slot, suffix in PART_SLOTS.items():
        tried = ([entry["name"] + suffix] if entry.get("search") else []) + [entry["texture_base"] + suffix]
        name = next((n for n in tried if n.lower() in known), None)
        if slot == "normal" and not has_nbt:
            name = None
        if name is None and slot != "base":
            out.pop(slot, None)
            continue
        kept = out.get(slot) or {"uv_set": 0, "filter": "FILTER_BILERP", "clamp": "WRAP_S_WRAP_T"}
        out[slot] = {**kept, "file": name or "_black"}
    return out


def describe(properties: dict, shape, data, pixel_format=lambda name: None,
             standard_data: bool = False, entry: dict | None = None, known=frozenset()) -> dict:
    texturing = properties.get("NiTexturingProperty")
    maps = {}
    for slot in MAPS:
        if texturing is not None and getattr(texturing, f"has_{slot}_texture", False):
            maps[slot] = _map(getattr(texturing, f"{slot}_texture"))
    if entry is not None:
        has_nbt = len(getattr(data, "normals", ()) or ()) > 0 and len(getattr(data, "tangents", ()) or ()) > 0
        maps = rebind(maps, entry, known, has_nbt)
    if "parallax" in maps:
        maps["parallax"]["offset"] = float(texturing.parallax_offset)
    if "bump_map" in maps:
        maps["bump_map"].update(luma_scale=float(texturing.bump_map_luma_scale),
                                luma_offset=float(texturing.bump_map_luma_offset))
    if "normal" in maps:
        maps["normal"]["pixel_format"] = pixel_format(maps["normal"]["file"])
        found = maps["normal"]["pixel_format"]
        maps["normal"]["packing"] = None if found is None else NORMAL_TYPES.get(found, "RGB")
    shader_maps = [dict(_map(m.map), id=int(m.map_id))
                   for m in (getattr(texturing, "shader_textures", None) or ()) if m.has_map]
    if texturing is not None:
        _texture_controllers(texturing, maps, shader_maps)

    colours = None
    block = properties.get("NiMaterialProperty")
    if block is not None:
        colours = {"ambient": [1.0, 1.0, 1.0], "diffuse": _colour(block.diffuse_color),
                   "specular": _colour(block.specular_color), "emissive": _colour(block.emissive_color),
                   "glossiness": float(block.glossiness), "alpha": float(block.alpha)}

    extra = {str(e.name): _extra(e) for e in (getattr(shape, "extra_data_list", None) or ())
             if e is not None}
    if entry is not None and entry.get("extra_data") == "UseFakeSpecular":
        extra.setdefault("UseFakeSpecular", True)
    for name, value in EXTRA_DEFAULTS.items():
        extra.setdefault(name, value)
    if len(getattr(data, "vertex_colors", ()) or ()):
        extra.setdefault("HasVertexColors", True)

    if standard_data:
        extra.update(STANDARD_DATA)

    block = properties.get("NiSpecularProperty")
    specular = bool(int(block.flags) & 1) if block is not None else False
    decoded = alpha(properties["NiAlphaProperty"]) if properties.get("NiAlphaProperty") is not None else Alpha()
    source = vertex_colour(properties.get("NiVertexColorProperty"))
    has_colours = bool(extra.get("HasVertexColors"))
    return {
        "maps": maps,
        "shader_maps": shader_maps,
        "apply_mode": str(texturing.apply_mode.name) if texturing is not None else None,
        "material": colours,
        "specular": specular,
        "alpha": dict(decoded.__dict__),
        "two_sided": two_sided(properties.get("NiStencilProperty")),
        "vertex_colour": source,
        "lighting_mode": lighting_mode(properties.get("NiVertexColorProperty")),
        "extra": extra,
        "program": program(maps, extra, specular, decoded, source if has_colours else IGNORE,
                           lighting_mode(properties.get("NiVertexColorProperty"))),
    }


# CShadingTools::SetupStandardData @6ce490 decomp
STANDARD_DATA = {"EnableFallOff": False, "FallOffPower": 2.0, "FallOffColor": [0.0, 0.0, 0.0]}


def program(maps: dict, extra: dict, specular: bool, blend: Alpha, colours: int, lighting: int) -> dict:
    additive = blend.additive
    return {
        "specular": specular,
        "gloss": specular and "gloss" in maps,
        "fake_specular": specular and (bool(extra.get("UseFakeSpecular")) if additive else True),
        "env": extra.get("UseEnvMapping") is True and specular and "gloss" in maps,
        "falloff": extra.get("EnableFallOff") is True,
        "fog": extra.get("CanBeFogged") is not False and not additive,
        "colours": {AMB_DIF: "diffuse", EMISSIVE: "emissive"}.get(colours),
        "lit": lighting != LIGHT_EMISSIVE,
    }
