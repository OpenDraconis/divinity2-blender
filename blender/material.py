import json
import os
from pathlib import Path

import bpy

from ..divinity2 import material as dv2_property
from ..divinity2 import region as dv2_region
from ..divinity2 import terrain as dv2_terrain
from ..divinity2 import texture as dv2_texture

from .scene import BINORMAL_UV, VERTEX_COLOURS, uv_name

WATER_PLANE = "WaterPlane"

WATER_IOR = 1.33

GAMMA = 2.2

GLOBALS = {"fGlobalNormalScale": 1.0, "fGlobalLightmapIntensity": 1.0,
           "g_TerrainSplatRadius": 100.0, "g_TerrainSplatBlendRadius": 10.0}

EXTENSION = {"WRAP_S_WRAP_T": "REPEAT", "CLAMP_S_CLAMP_T": "EXTEND"}


def cached_image(texture_name: str, game_root: Path, cache: Path):
    cache.mkdir(parents=True, exist_ok=True)
    dds = cache / (dv2_texture.stem(texture_name) + ".dds")

    if not dds.exists():
        source = dv2_texture.texture_path(texture_name, game_root)
        if not source.exists():
            return None
        _write_atomic(dds, dv2_texture.to_dds(source))

    return _raw(bpy.data.images.load(str(dds), check_existing=True))


def _write_atomic(path: Path, data: bytes) -> None:
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    part.write_bytes(data)
    os.replace(part, path)


def _raw(image):
    image.colorspace_settings.name = "Non-Color"
    image.alpha_mode = "CHANNEL_PACKED"
    return image


class _Graph:
    def __init__(self, material):
        self.tree = material.node_tree
        self.tree.nodes.clear()
        self.output = self.tree.nodes.new("ShaderNodeOutputMaterial")
        self.geometry = self.tree.nodes.new("ShaderNodeNewGeometry")
        self._uv = {}

    def new(self, kind, **settings):
        node = self.tree.nodes.new(kind)
        for key, value in settings.items():
            setattr(node, key, value)
        return node

    def feed(self, socket, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.tree.links.new(value, socket)
        else:
            socket.default_value = value

    def math(self, operation, *inputs):
        node = self.new("ShaderNodeMath", operation=operation)
        for socket, value in zip(node.inputs, inputs):
            self.feed(socket, value)
        return node.outputs[0]

    def vector(self, operation, *inputs):
        node = self.new("ShaderNodeVectorMath", operation=operation)
        for socket, value in zip(node.inputs, inputs):
            self.feed(socket, value)
        return node.outputs["Value" if operation in ("DOT_PRODUCT", "LENGTH") else "Vector"]

    def scale(self, vector, factor):
        node = self.new("ShaderNodeVectorMath", operation="SCALE")
        self.feed(node.inputs[0], vector)
        self.feed(node.inputs["Scale"], factor)
        return node.outputs["Vector"]

    def split(self, colour):
        node = self.new("ShaderNodeSeparateXYZ")
        self.feed(node.inputs[0], colour)
        return node.outputs

    def join(self, x, y, z):
        node = self.new("ShaderNodeCombineXYZ")
        for socket, value in zip(node.inputs, (x, y, z)):
            self.feed(socket, value)
        return node.outputs[0]

    def lerp(self, a, b, t):
        node = self.new("ShaderNodeMix", data_type="VECTOR", clamp_factor=False)
        self.feed(node.inputs["Factor"], t)
        self.feed(node.inputs[4], a)
        self.feed(node.inputs[5], b)
        return node.outputs[1]

    def mix(self, a, b, t):
        return self.math("ADD", a, self.math("MULTIPLY", self.math("SUBTRACT", b, a), t))

    def uv(self, index: int):
        if index not in self._uv:
            self._uv[index] = self.new("ShaderNodeUVMap", uv_map=uv_name(index)).outputs["UV"]
        return self._uv[index]

    def global_(self, name: str):
        return self.new("ShaderNodeAttribute", attribute_type="VIEW_LAYER",
                        attribute_name=f"dv2_{name}").outputs["Factor"]

    def sample(self, image, spec: dict, at=None):
        at = self.uv(spec.get("uv_set", 0)) if at is None else at
        matrix = (spec.get("transform") or {}).get("matrix")
        if matrix is not None:
            u, v, _ = self.split(at)
            v = self.math("SUBTRACT", 1.0, v)
            u, v = (self.math("ADD", self.math("ADD", self.math("MULTIPLY", u, row[0]),
                                               self.math("MULTIPLY", v, row[1])), row[2])
                    for row in matrix)
            at = self.join(u, self.math("SUBTRACT", 1.0, v), 0.0)
        clamp = spec.get("clamp", "WRAP_S_WRAP_T")
        node = self.new("ShaderNodeTexImage", image=image,
                        extension=EXTENSION.get(clamp, "REPEAT"),
                        interpolation="Closest" if spec.get("filter") == "FILTER_NEAREST" else "Linear")
        if clamp in ("WRAP_S_CLAMP_T", "CLAMP_S_WRAP_T"):
            u, v, _ = self.split(at)
            if clamp == "WRAP_S_CLAMP_T":
                v = self.math("MINIMUM", self.math("MAXIMUM", v, 0.0), 1.0)
            else:
                u = self.math("MINIMUM", self.math("MAXIMUM", u, 0.0), 1.0)
            at = self.join(u, v, 0.0)
        self.feed(node.inputs["Vector"], at)
        return node.outputs["Color"], node.outputs["Alpha"]


def build_material(drawn, game_root: Path, cache: Path, source=None, standard_data: bool = False,
                   entry: dict | None = None, for_unity: bool = False):
    game_root, cache = Path(game_root), Path(cache)
    desc = dv2_property.describe(drawn.properties, drawn.shape, drawn.data,
                                 lambda name: dv2_texture.pixel_format(name, game_root), standard_data,
                                 entry, dv2_texture.shipped(game_root) if entry is not None else frozenset())
    name = drawn.name or "material"
    material = bpy.data.materials.new(name.replace(":", "_") if for_unity else name)
    material["dv2_material"] = json.dumps(desc)
    material.use_backface_culling = not desc["two_sided"]

    graph = _Graph(material)
    index = dv2_terrain.patch_of(drawn.path) if source is not None else None
    if index is not None and not desc["maps"]:
        _terrain(graph, material, source, index, desc, drawn, game_root, cache)
    else:
        _standard(graph, material, desc, drawn, game_root, cache)

    if source is not None and _is_water(drawn):
        _water(material, source, drawn.name)
    return material


def _frame(graph, drawn):
    if not len(getattr(drawn.data, "tangents", ()) or ()):
        return None
    xy, zs = (graph.split(graph.new("ShaderNodeUVMap", uv_map=name).outputs["UV"]) for name in BINORMAL_UV)
    world = graph.new("ShaderNodeVectorTransform", vector_type="VECTOR",
                      convert_from="OBJECT", convert_to="WORLD")
    graph.feed(world.inputs[0], graph.join(xy[0], xy[1], zs[0]))
    normal = graph.vector("NORMALIZE", graph.geometry.outputs["Normal"])
    binormal = graph.vector("NORMALIZE", world.outputs[0])
    tangent = graph.scale(graph.vector("NORMALIZE", graph.vector("CROSS_PRODUCT", normal, binormal)), zs[1])
    return tangent, binormal, normal


def _decode_normal(graph, colour, alpha, packing, scale, frame):
    r, g, b = graph.split(colour)
    x = graph.math("MULTIPLY_ADD", alpha if packing == "AG" else r, 2.0, -1.0)
    y = graph.math("MULTIPLY_ADD", g, 2.0, -1.0)
    if packing == "RGB":
        z = graph.math("MULTIPLY_ADD", b, 2.0, -1.0)
    else:
        rest = graph.math("SUBTRACT", graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", x, x)),
                          graph.math("MULTIPLY", y, y))
        z = graph.math("SQRT", graph.math("MAXIMUM", rest, 0.0) if packing == "AG" else rest)
    tangent, binormal, normal = frame
    return graph.vector("NORMALIZE", graph.vector(
        "ADD", graph.vector("ADD", graph.scale(tangent, graph.math("MULTIPLY", x, scale)),
                            graph.scale(binormal, graph.math("MULTIPLY", y, scale))),
        graph.scale(normal, z)))


def _gamma(graph, colour):
    node = graph.new("ShaderNodeGamma")
    graph.feed(node.inputs["Color"], colour)
    node.inputs["Gamma"].default_value = GAMMA
    return node.outputs[0]


def _standard(graph, material, desc, drawn, game_root, cache):
    maps, extra = desc["maps"], desc["extra"]
    images = {slot: cached_image(spec["file"], game_root, cache)
              for slot, spec in maps.items() if spec.get("file")}
    missing = sorted(f"{slot}: {maps[slot]['file']}" for slot, image in images.items() if image is None)
    if missing:
        material["dv2_missing"] = json.dumps(missing)
    frame = _frame(graph, drawn)

    at = {}
    if images.get("parallax") is not None and frame is not None:
        spec = maps["parallax"]
        height, _ = graph.sample(images["parallax"], spec)
        tangent, binormal, _ = frame
        eye = graph.geometry.outputs["Incoming"]
        length = graph.vector("LENGTH", eye)
        ex = graph.math("DIVIDE", graph.vector("DOT_PRODUCT", eye, tangent), length)
        ey = graph.math("DIVIDE", graph.vector("DOT_PRODUCT", eye, binormal), length)
        s = spec.get("offset", 0.0)
        hr, hg, _ = graph.split(height)
        du = graph.math("MULTIPLY", graph.math("MULTIPLY_ADD", hr, s, -0.5 * s), ex)
        dv = graph.math("MULTIPLY", graph.math("MULTIPLY_ADD", hg, s, -0.5 * s), ey)
        u, v, _ = graph.split(graph.uv(spec["uv_set"]))
        at[spec["uv_set"]] = graph.join(graph.math("ADD", u, du), graph.math("SUBTRACT", v, dv), 0.0)

    def sample(slot):
        spec = maps[slot]
        return graph.sample(images[slot], spec, at.get(spec.get("uv_set", 0)))

    principled = graph.new("ShaderNodeBsdfDiffuse")
    if images.get("normal") is not None and frame is not None and maps["normal"].get("packing"):
        colour, alpha = sample("normal")
        scale = graph.math("MULTIPLY", graph.global_("fGlobalNormalScale"), extra["ObjectNormalScale"])
        graph.feed(principled.inputs["Normal"],
                   _decode_normal(graph, colour, alpha, maps["normal"]["packing"], scale, frame))

    albedo, coverage = (1.0, 1.0, 1.0), 1.0
    if images.get("base") is not None:
        albedo, coverage = sample("base")
    if images.get("dark") is not None:
        dark, _ = sample("dark")
        lightmap = graph.vector("MULTIPLY", dark, dark)
        albedo = graph.vector("MULTIPLY", albedo, graph.scale(
            lightmap, graph.global_("fGlobalLightmapIntensity")))
    if images.get("detail") is not None:
        detail, _ = sample("detail")
        albedo = graph.vector("MULTIPLY", albedo, graph.scale(detail, 2.0))
    colours = desc["material"] or {"diffuse": [1.0, 1.0, 1.0], "emissive": [0.0, 0.0, 0.0], "alpha": 1.0}
    diffuse, emissive = tuple(colours["diffuse"][:3]), tuple(colours["emissive"][:3])
    program = desc["program"]
    opacity_source = colours["alpha"]
    if program["colours"]:
        vertex = graph.new("ShaderNodeVertexColor", layer_name=VERTEX_COLOURS)
        if program["colours"] == "emissive":
            emissive = vertex.outputs["Color"]
        else:
            diffuse = vertex.outputs["Color"]
        opacity_source = vertex.outputs["Alpha"]
    if not program["lit"]:
        diffuse = (0.0, 0.0, 0.0)
    graph.feed(principled.inputs["Color"], _gamma(graph, graph.vector("MULTIPLY", albedo, diffuse)))
    surface = principled.outputs[0]
    unlit = [graph.vector("MULTIPLY", albedo, emissive)]
    if images.get("glow") is not None:
        glow, _ = sample("glow")
        unlit.append(graph.scale(glow, extra["ObjectHDRScale"]))
    for term in unlit:
        light = graph.new("ShaderNodeEmission")
        graph.feed(light.inputs["Color"], _gamma(graph, term))
        add = graph.new("ShaderNodeAddShader")
        graph.feed(add.inputs[0], surface)
        graph.feed(add.inputs[1], light.outputs[0])
        surface = add.outputs[0]

    opacity = graph.math("MINIMUM", graph.math("MULTIPLY", coverage, opacity_source), 1.0)
    graph.feed(graph.output.inputs["Surface"],
               _transparency(graph, material, desc["alpha"], opacity, surface))


def _transparency(graph, material, alpha: dict, opacity, surface):
    if alpha["testing"]:
        opacity = graph.math("GREATER_THAN", opacity, alpha["threshold"] / 255.0)
        material.surface_render_method = "DITHERED"
    if alpha["blending"]:
        material.surface_render_method = "BLENDED"
    if not (alpha["testing"] or alpha["blending"]):
        return surface
    through = graph.new("ShaderNodeBsdfTransparent").outputs[0]
    if alpha["blending"] and alpha["source"] == "ONE" and alpha["destination"] == "ONE":
        material.use_transparent_shadow = False
        add = graph.new("ShaderNodeAddShader")
        graph.feed(add.inputs[0], through)
        graph.feed(add.inputs[1], surface)
        return add.outputs[0]
    mix = graph.new("ShaderNodeMixShader")
    graph.feed(mix.inputs["Fac"], opacity)
    graph.feed(mix.inputs[1], through)
    graph.feed(mix.inputs[2], surface)
    return mix.outputs[0]


def _is_water(drawn) -> bool:
    return any(
        line.strip() == WATER_PLANE
        for line in drawn.markers.get("UserPropBuffer", "").splitlines()
    )


def _water(material, source, name: str) -> None:
    style = dv2_region.water_style(dv2_region.water_styles(source), name)
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    principled = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(principled.outputs[0], output.inputs["Surface"])

    principled.inputs["Base Color"].default_value = tuple(style["colours"][-1]) + (1.0,)
    principled.inputs["Roughness"].default_value = _roughness(style.get("shininess"))
    principled.inputs["Transmission Weight"].default_value = 1.0
    principled.inputs["IOR"].default_value = WATER_IOR
    material.surface_render_method = "BLENDED"

    for key, value in style.items():
        if isinstance(value, (int, float, str)):
            material[f"dv2_{key}"] = value


def _roughness(shininess) -> float:
    try:
        exponent = float(shininess)
    except (TypeError, ValueError):
        return 0.1
    return (2.0 / (exponent + 2.0)) ** 0.5 if exponent > 0.0 else 1.0


def _image_of(path: Path, cache: Path):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{Path(path).stem}.dds"
    try:
        if not out.exists():
            _write_atomic(out, dv2_texture.to_dds(path))
        image = _raw(bpy.data.images.load(str(out), check_existing=True))
    except (ValueError, RuntimeError, OSError):
        return None
    image.name = Path(path).stem
    return image


def _terrain(graph, material, source, index: int, desc: dict, drawn, game_root: Path, cache: Path) -> None:
    patch = dv2_terrain.patches(source).get(index)
    if patch is None:
        return
    rows = {layer.pass_index * 4 + layer.channel: layer for layer in patch.layers
            if layer.pass_index * 4 + layer.channel < 8}
    if not rows:
        return
    paints = {}
    for layer in rows.values():
        if layer.pass_index not in paints and layer.mask is not None:
            picture = _image_of(layer.mask, cache)
            if picture is not None:
                colour, alpha = graph.sample(picture, {"uv_set": 0, "clamp": "CLAMP_S_CLAMP_T"})
                paints[layer.pass_index] = list(graph.split(colour)) + [alpha]

    def image(name):
        return cached_image(name, game_root, cache) if name else None

    diff, nrm, acc = (0.0, 0.0, 0.0), ((0.5, 0.5, 1.0), 0.5), 0.0
    for row in sorted(rows, reverse=True):
        layer = rows[row]
        if row == 0:
            a = 1.0
        elif layer.pass_index in paints:
            a = paints[layer.pass_index][layer.channel]
        else:
            continue
        texture = image(layer.texture)
        if texture is None:
            continue
        at = graph.vector("MULTIPLY", graph.uv(1), (layer.tiling, layer.tiling, 1.0))
        w = a
        noise = image(layer.noise_composite)
        if noise is not None:
            n, _ = graph.sample(noise, {}, at)
            w = graph.math("MAXIMUM", a, graph.math("MINIMUM", graph.math(
                "MULTIPLY", graph.math("MULTIPLY", graph.split(n)[2], a), 15.0), 1.0))
        chosen = graph.math("MULTIPLY", graph.math("LESS_THAN", acc, 1.0), graph.math("GREATER_THAN", a, 0.0))
        d, _ = graph.sample(texture, {}, at)
        diff = graph.lerp(diff, graph.lerp(d, diff, acc), chosen)
        normal_map = image(layer.normal)
        if normal_map is not None:
            c, ca = graph.sample(normal_map, {}, at)
            nrm = (graph.lerp(nrm[0], graph.lerp(c, nrm[0], acc), chosen),
                   graph.mix(nrm[1], graph.mix(ca, nrm[1], acc), chosen))
        acc = graph.math("ADD", acc, graph.math("MULTIPLY", chosen, w))

    mega = _image_of(patch.megatexture, cache) if patch.megatexture is not None else None
    if mega is not None:
        distance = graph.new("ShaderNodeCameraData").outputs["View Distance"]
        radius = graph.global_("g_TerrainSplatRadius")
        band = graph.global_("g_TerrainSplatBlendRadius")
        m, _ = graph.sample(mega, {"uv_set": 0, "clamp": "CLAMP_S_CLAMP_T"})
        t = graph.math("MINIMUM", graph.math("MAXIMUM", graph.math(
            "DIVIDE", graph.math("SUBTRACT", radius, distance), band), 0.0), 1.0)
        diff = graph.lerp(m, diff, t)

    shade = graph.new("ShaderNodeBsdfDiffuse")
    graph.feed(shade.inputs["Color"], _gamma(graph, diff))
    frame = _frame(graph, drawn)
    if frame is not None:
        _, binormal, normal = frame
        tangent = graph.vector("NORMALIZE", graph.vector("CROSS_PRODUCT", binormal, normal))
        scale = graph.math("MULTIPLY", graph.global_("fGlobalNormalScale"), desc["extra"]["ObjectNormalScale"])
        graph.feed(shade.inputs["Normal"],
                   _decode_normal(graph, nrm[0], nrm[1], "AG", scale, (tangent, binormal, normal)))
    graph.feed(graph.output.inputs["Surface"], shade.outputs[0])
