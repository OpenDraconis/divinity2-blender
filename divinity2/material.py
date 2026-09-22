"""What a shape's properties say about its surface.

`nif.xml` describes the blocks; what it does not say is which combinations
Divinity II actually ships and what they mean on screen. Measured over the
character templates, there are three:

| `NiAlphaProperty.flags` | what it is |
|---|---|
| 4844 | alpha test, `GREATER` than the threshold -- a cut-out |
| 4333 | alpha blend, `SRC_ALPHA` over `INV_SRC_ALPHA` |
| 4097 | additive, `ONE` plus `ONE` |

168 of the 324 characters carry one. Ignoring the block is why hair, capes
and glow planes arrive as opaque cards.

The flag word is the standard Gamebryo layout:

    bit 0      blending enabled
    bits 1-4   source blend factor
    bits 5-8   destination blend factor
    bit 9      testing enabled
    bits 10-12 test function
    bit 13     no sorter
"""

from dataclasses import dataclass

#: `StencilDrawMode.DRAW_BOTH`: draw the back faces as well as the front.
DRAW_BOTH = 3

#: `SourceVertexMode`: which term of the lighting equation a shape's vertex
#: colours feed. The numbers are `nif.xml`'s, named here so the rest of the
#: add-on can say which one it means without importing the reader.
IGNORE = 0
EMISSIVE = 1
AMB_DIF = 2

#: The blend factors, in the order the flag word numbers them.
FACTORS = (
    "ONE", "ZERO", "SRC_COLOR", "INV_SRC_COLOR", "DST_COLOR", "INV_DST_COLOR",
    "SRC_ALPHA", "INV_SRC_ALPHA", "DST_ALPHA", "INV_DST_ALPHA", "SRC_ALPHA_SAT",
)

#: The test functions, likewise.
FUNCTIONS = (
    "ALWAYS", "LESS", "EQUAL", "LESS_EQUAL", "GREATER", "NOT_EQUAL",
    "GREATER_EQUAL", "NEVER",
)


@dataclass
class Alpha:
    """A decoded `NiAlphaProperty`."""

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
    """Decode a `NiAlphaProperty`."""
    flags = int(block.flags)
    return Alpha(
        blending=bool(flags & 1),
        source=_name(FACTORS, (flags >> 1) & 0xF, "ONE"),
        destination=_name(FACTORS, (flags >> 5) & 0xF, "ZERO"),
        testing=bool((flags >> 9) & 1),
        function=_name(FUNCTIONS, (flags >> 10) & 0x7, "ALWAYS"),
        threshold=int(block.threshold),
    )



#: `NiVertexColorProperty::NiVertexColorProperty` sets `m_uFlags = 8`: source
#: IGNORE, lighting EMI_AMB_DIF. A shape with no such property anywhere above
#: it draws with that default (`NiPropertyState`'s default properties) -- not
#: with nif.xml's "if not present, vertex_mode=2", which is the exporter's
#: convention and not what the engine does.
DEFAULT_VERTEX_COLOUR_FLAGS = 8

#: `LightingMode`: EMISSIVE lights with the emissive term alone.
LIGHT_EMISSIVE = 0


def vertex_colour(block) -> int:
    """What a shape's vertex colours are for, as `SourceVertexMode`.

    The mode is in `flags`. The block's own `vertex_mode` and `lighting_mode`
    fields are written only at NIF 20.0.0.5 and earlier, and read 0 at this
    game's 20.3.0.9 whatever the shape carries -- the same trap as `has_uv`.
    `VertexColorFlags` in the reader decodes the real thing. Absent is the
    engine's default property, IGNORE (`DEFAULT_VERTEX_COLOUR_FLAGS`).
    """
    if block is None:
        return (DEFAULT_VERTEX_COLOUR_FLAGS >> 4) & 3
    return int(block.flags.source_vertex_mode)


def lighting_mode(block) -> int:
    """`LightingMode` of a `NiVertexColorProperty`; absent is EMI_AMB_DIF."""
    if block is None:
        return (DEFAULT_VERTEX_COLOUR_FLAGS >> 3) & 1
    return int(block.flags.lighting_mode)


def two_sided(block) -> bool:
    """Does a `NiStencilProperty` say to draw the back faces too?

    The engine culls unless told otherwise, and this game's files only ever
    tell it otherwise: `draw_mode` is `DRAW_BOTH` in all 12 of the 228
    sampled scenery files that carry the property -- banners, flags, bushes,
    swamp grass, water plants -- and no other value appears anywhere. So a
    shape with no stencil property is culled.

    The NifTools addon reads it the same way in both directions: it sets
    `use_backface_culling` on every material it builds and clears it only
    when the property is present, and its exporter writes no stencil property
    when culling is on. The round-trip closes.
    """
    return block is not None and int(block.draw_mode) == DRAW_BOTH


#: Every map slot of `NiTexturingProperty`, in `nif.xml`'s order, by the name
#: the descriptor gives it. `DivStandardMaterial` reads base, dark, detail,
#: gloss, glow, normal and parallax (docs/sources.md,
#: "Standard material"); bump and the decals are carried so nothing is lost.
MAPS = ("base", "dark", "detail", "gloss", "glow", "bump_map", "normal", "parallax",
        "decal_0", "decal_1", "decal_2", "decal_3")

#: How `DivStandardMaterial::GenerateDescriptor` reads a normal map, by the
#: pixel format of its `NiSourceTexture`: DXT1 and DXT5 are `NormalMapType` 2,
#: x in alpha and y in green; DXN is type 1, x in red; any other format is
#: type 0, plain RGB. The formats are `nif.xml`'s `PixelFormat` names.
#: Never by what the picture holds: 12 of the game's 1,259 normal maps hold
#: RGB-looking content and the engine reads those through alpha and green all
#: the same. `CalculateScaledNormalFromColor` rebuilds z as
#: `sqrt(saturate(1 - x*x - y*y))`.
NORMAL_TYPES = {"FMT_DXT1": "AG", "FMT_DXT5": "AG", "FMT_DXN": "RG"}

#: What `MdlMan::CMeshWrapper::SetupGeometry` adds to every geometry that does
#: not carry its own: a value in the file wins, these fill the rest.
EXTRA_DEFAULTS = {"ObjectNormalScale": 1.0, "ObjectHDRScale": 1.0,
                  "FallOffPower": 1.0, "FallOffColor": [0.0, 0.0, 0.0]}


def _colour(c) -> list:
    return [float(c.r), float(c.g), float(c.b)] + ([float(c.a)] if hasattr(c, "a") else [])


def _map(desc) -> dict:
    """One `TexDesc`, whole. `Flags` packs the UV set (`Texture Index`), filter
    and clamp mode (`nif.xml` `TexturingMapFlags`)."""
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


def uv_matrix(transform: dict) -> list:
    """`NiTextureTransform::UpdateMatrix` @0x533fd0: the 2x3 matrix that takes a
    file UV `(u, v, 1)` to the one sampled, for each of the three methods.
    Rows are `[m00, m01, m02]` and `[m10, m11, m12]`."""
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
    dy, dx = ty - cy, -cx - tx                       # MAX
    return [[c * sx, sx * s, (dx * c + dy * s) * sx + cx], [-s * sy, sy * c, (c * dy - s * dx) * sy + cy]]


def _extra(block):
    """An extra data block's value, whatever its type; the type name where the
    reader does not know how to read it, so the gap stays visible."""
    kind = type(block).__name__
    if kind in ("NiFloatExtraData", "NiIntegerExtraData", "NiBooleanExtraData"):
        return block.float_data if kind == "NiFloatExtraData" else (
            int(block.integer_data) if kind == "NiIntegerExtraData" else bool(block.boolean_data))
    if kind == "NiColorExtraData":
        return _colour(block.data)
    if kind == "NiStringExtraData":
        return str(block.string_data)
    return {"unread": kind}


#: The slots `MdlMan::CMeshWrapper::SetupTexturingProperty` @0xc9de80 binds by
#: name, and the suffix it puts on the texture base (`ms_pacTextureExtensions`
#: @0x13ee630). docs/sources.md, "Character part maps"
PART_SLOTS = {"base": "_DM", "gloss": "_SM", "glow": "_GM", "normal": "_NM"}

def rebind(maps: dict, entry: dict, known, has_nbt: bool) -> dict:
    """A character part's maps as the engine binds them: by the part's
    `CMeshEntry` texture base plus the slot's suffix, ignoring the names the
    mesh carries (the `.cat` build stripped all but base and glow). A name the
    engine does not know leaves base `_black` and removes any other slot; a
    normal map needs normals and binormals on the shape. A new map is
    `WRAP_S_WRAP_T`, `FILTER_BILERP`, UV set 0; an existing one keeps its flags.
    `known` is `texture.shipped`: the names the engine can load, lower case."""
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
    """The material the engine builds for one shape, as plain data.

    `properties` is the property state the walk resolved (`graph`), `shape`
    the geometry and `data` its geometry data. `pixel_format(file)` names a
    texture's `PixelFormat`, None where the texture is missing; only the normal
    map needs it, and its packing stays None when the format is not known.

    Nothing is chosen for a consumer: every map slot with its UV set, filter,
    clamp and transform; `NiMaterialProperty` with ambient forced to white the
    way `SetupGeometry` forces it; `NiSpecularProperty`, alpha, stencil and
    vertex colour state; and every extra data block on the shape, with the
    engine's defaults where the file has none. `entry` is a character part's
    `CMeshEntry` (`character.mesh_entry`): its maps are rebound (`rebind`) against
    `known`. `standard_data` is True for the
    geometry `CShadingTools::SetupStandardData` runs on: a region's own nodes,
    static assets and terrain. `program` is what the engine switches on.
    """
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

    colours = None
    block = properties.get("NiMaterialProperty")
    if block is not None:
        colours = {"ambient": [1.0, 1.0, 1.0], "diffuse": _colour(block.diffuse_color),
                   "specular": _colour(block.specular_color), "emissive": _colour(block.emissive_color),
                   "glossiness": float(block.glossiness), "alpha": float(block.alpha)}

    extra = {str(e.name): _extra(e) for e in (getattr(shape, "extra_data_list", None) or ())
             if e is not None}
    # Dev Cut `FUN_00dc0f60` @0xdc1307..0xdc136c: a part whose `CMeshEntry` extra
    # data names `UseFakeSpecular` gets that boolean, true, unless the geometry
    # carries one. The 828 entries hold only that value or none (688 / 140).
    if entry is not None and entry.get("extra_data") == "UseFakeSpecular":
        extra.setdefault("UseFakeSpecular", True)
    for name, value in EXTRA_DEFAULTS.items():
        extra.setdefault(name, value)
    if len(getattr(data, "vertex_colors", ()) or ()):
        extra.setdefault("HasVertexColors", True)

    if standard_data:
        extra.update(STANDARD_DATA)

    # `NiSpecularProperty::NiSpecularProperty` sets `m_uFlags = 0`: absent is off.
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


#: `CShadingTools::SetupStandardData` (@0x6ce490; Dev Cut @0xba4a00), which the
#: region, static-asset and terrain loaders run on their geometry, overwrites
#: these whatever the file says: no fall-off rim on scenery.
STANDARD_DATA = {"EnableFallOff": False, "FallOffPower": 2.0, "FallOffColor": [0.0, 0.0, 0.0]}


def program(maps: dict, extra: dict, specular: bool, blend: Alpha, colours: int, lighting: int) -> dict:
    """What `DivStandardMaterial::GenerateDescriptor` switches on for a shape
    (Developer's Cut; docs/sources.md, "Material gates"):

    - `specular`: `NiSpecularProperty` flag. Off makes MatSpecular 0 -- no light,
      pre-pass or fake specular -- and the gloss map is not inserted.
    - `fake_specular`: forced on unless the shape blends ONE/ONE; there
      `UseFakeSpecular` decides. Needs `specular`.
    - `env`: `UseEnvMapping` true; the cube is masked by the gloss map.
    - `falloff`: `EnableFallOff` true (after `STANDARD_DATA` where it applies).
    - `fog`: off when `CanBeFogged` is false or the shape blends ONE/ONE.
    - `colours`: "diffuse" (AMB_DIF: they replace MatDiffuse and MatAmbient),
      "emissive" (they replace MatEmissive), or None; and their alpha replaces
      MatDiffuse's in the opacity.
    - `lit`: False when the lighting mode is EMISSIVE: no light at all.
    """
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
