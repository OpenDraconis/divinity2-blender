import sys
from pathlib import Path

_WHEELS = Path(__file__).resolve().parent.parent / "wheels"


def _reader():
    try:
        from nifgen.formats.nif import NifFile
    except ImportError:
        sys.path.extend(str(p) for p in _WHEELS.glob("nifgen-*.whl"))
        from nifgen.formats.nif import NifFile

    return NifFile


def read_nif(path: str | Path):
    return _reader().from_path(Path(path))


UNITS_PER_METRE = 100.0

