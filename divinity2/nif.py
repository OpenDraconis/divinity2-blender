"""Opening a Divinity II NIF file.

The format itself is not described here. It is described in `nif.xml`, the
NifTools project's format specification, and read by `nifgen`, the Python
reader generated from it. `nif.xml` carries Divinity 2 as a version of its
own: NIF 20.3.0.9 with user version 0x20000 or 0x30000, extensions `nft`,
`item` and `cat`.

So this module does one thing: it puts the vendored reader on the path and
opens the file. If a block is read wrongly, the fix belongs in `nif.xml`
upstream, not here.
"""

import sys
from pathlib import Path

_WHEELS = Path(__file__).resolve().parent.parent / "wheels"


def _reader():
    try:
        from nifgen.formats.nif import NifFile
    except ImportError:
        # Installed, Blender has unpacked the manifest's wheel into its own
        # site-packages. A working tree loaded as a package of its own -- a
        # test, the Unity port -- reads the same wheel as a zip instead.
        sys.path.extend(str(p) for p in _WHEELS.glob("nifgen-*.whl"))
        from nifgen.formats.nif import NifFile

    return NifFile


def read_nif(path: str | Path):
    """Open any NIF the game ships: `.nif`, `.cat`, `.item`, `.nft`."""
    return _reader().from_path(Path(path))


#: Game units in a metre. Every model in the game is authored in
#: centimetres: a human template comes out 1.87 m, a Maxos gate 4.6 m tall, a
#: ruined wall 15.7 m long. How many of those units reach the world is on the
#: tree's root node -- see `blender.importer`.
#:
#: The `worldScale` float the files carry next to their shapes is **not**
#: this. It is a shader input: `DivStandardMaterial::HandleNormalMap` binds it
#: as a material-node variable beside `LocalScale`, and
#: `CShadingTools::SetupStandardData` overwrites the authored value with 1.0
#: before drawing. The engine never reads it as a unit, and neither do we.
UNITS_PER_METRE = 100.0

