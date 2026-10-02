import struct
from functools import lru_cache
from pathlib import Path, PureWindowsPath

from .nif import read_nif

TEXTURE_DIR = Path("Win32") / "Textures"

FOURCC = {
    "FMT_DXT1": b"DXT1",
    "FMT_DXT3": b"DXT3",
    "FMT_DXT5": b"DXT5",
}

_DDSD = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000
_DDPF_FOURCC = 0x4
_DDSCAPS = 0x1000 | 0x8 | 0x400000


@lru_cache(maxsize=8)
def _by_lower_stem(game_root: Path) -> dict:
    directory = Path(game_root) / TEXTURE_DIR
    if not directory.is_dir():
        return {}
    return {p.stem.lower(): p for p in directory.glob("*.nif")}


def stem(texture_name: str) -> str:
    return PureWindowsPath(str(texture_name)).stem


# CTexturePalette::GetTextureWrapper @10dca00 decomp
MISSING = "_black"


# CTextureManager::ParsePersistentTextureCollection @10d3a70 decomp
@lru_cache(maxsize=8)
def shipped(game_root: Path) -> frozenset:
    path = Path(game_root) / TEXTURE_DIR / "Textures.bin"
    if not path.is_file():
        return frozenset()
    data = path.read_bytes()
    (count,), at, names = struct.unpack_from("<I", data), 4, set()
    for _ in range(count):
        (length,) = struct.unpack_from("<I", data, at)
        names.add(Path(data[at + 4:at + 4 + length].decode("latin-1")).stem.lower())
        at += 4 + length
    return frozenset(names)


def texture_path(texture_name: str, game_root: Path) -> Path:
    stem_ = stem(texture_name)
    direct = Path(game_root) / TEXTURE_DIR / (stem_ + ".nif")
    if direct.is_file():
        return direct
    found = _by_lower_stem(Path(game_root))
    if stem_.lower() not in found and (known := shipped(Path(game_root))) \
            and stem_.lower() not in known:
        return found.get(MISSING, direct)
    return found.get(stem_.lower(), direct)


@lru_cache(maxsize=4096)
def pixel_format(texture_name: str, game_root: Path) -> str | None:
    path = texture_path(texture_name, Path(game_root))
    if not path.is_file():
        return None
    return _renderer_data(read_nif(path)).pixel_format.name


def _renderer_data(nif):
    return next(b for b in nif.blocks if type(b).__name__ == "NiPersistentSrcTextureRendererData")


def to_dds(path: str | Path) -> bytes:
    try:
        block = _renderer_data(read_nif(path))
    except StopIteration:
        raise ValueError(f"{Path(path).name} holds no texture") from None

    fmt = FOURCC.get(block.pixel_format.name)
    if fmt is None:
        raise ValueError(f"{Path(path).name}: {block.pixel_format.name} is not DXT")

    top = block.mipmaps[0]
    pixels = bytes(block.pixel_data)

    header = struct.pack(
        "<4sIIIIIII44sII4sIIIIIIIIII",
        b"DDS ", 124, _DDSD,
        top.height, top.width,
        len(pixels) // block.num_mipmaps if block.num_mipmaps else len(pixels),
        0, block.num_mipmaps,
        b"\0" * 44,
        32, _DDPF_FOURCC, fmt, 0, 0, 0, 0, 0,
        _DDSCAPS, 0, 0, 0, 0,
    )
    return header + pixels
