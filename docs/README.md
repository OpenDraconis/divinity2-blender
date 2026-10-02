# divinity2-blender documentation

| Folder | Holds |
|---|---|
| `docs/` | How to use the add-on |
| `engine/` | What the Divinity II engine and its file formats do |

## docs

- [using-it.md](using-it.md): install, operators, panel, preferences, texture cache, environment variables, the export path to Unity

## engine

- [nif.md](../engine/nif.md): the file format, units, scene graph, culling, level of detail
- [animation.md](../engine/animation.md): B-spline clips, key types, text keys, KFM, sequences
- [characters.md](../engine/characters.md): `.cat`, shared rigs, model manager tables, skinning, weapon slots
- [materials.md](../engine/materials.md): render properties, DivStandardMaterial, water, terrain material
- [textures.md](../engine/textures.md): texture NIFs, the known-name table, normal maps
- [terrain.md](../engine/terrain.md): streamed patch levels, Terrain.xml, graphics options
- [static-assets.md](../engine/static-assets.md): `ASSET` nodes and streamed levels
- [regions.md](../engine/regions.md): placements, region nodes, triggers, lights, trees
- [environment.md](../engine/environment.md): atmosphere, sky, light settings
- [vegetation.md](../engine/vegetation.md): the grass generator
- [particles.md](../engine/particles.md): particle systems and Larian markers

The export to Unity lives in [divinity2-port](https://github.com/OpenDraconis/divinity2-port).
