
import re
from pathlib import Path

from . import lod, terrain

MANIFEST = Path("Win32") / "CompiledAssets" / "AssetDataDescriptors.xml"

_ASSET_FILE = re.compile(r'AssetFile="([^"]*)"')


def levels(game_root) -> dict:
    base = Path(game_root) / MANIFEST.parent
    found = {}
    for entry, name, index in terrain.manifest(Path(game_root) / MANIFEST):
        path = base / entry.get("base", "") / entry.get("sub", "") / f"{index}.nif"
        if index > 0 and name and path.is_file():
            found.setdefault((entry.get("base", "").lower(), entry.get("sub", "")), {})[name] = path
    return found


def asset_of(node) -> str | None:
    if "ASSET" not in str(getattr(node, "name", "")):
        return None
    match = _ASSET_FILE.search(lod._user_prop(node))
    return Path(match.group(1).replace("\\", "/")).stem if match else None


def placements(root):
    stack = [root]
    while stack:
        node = stack.pop()
        asset = asset_of(node)
        if asset is not None:
            yield node, asset
            continue
        stack += lod.child_nodes(node)


def graft(root, game_root) -> int:
    known, read, grafted = None, {}, 0
    for placed, asset in placements(root):
        if known is None:
            known = levels(game_root)
        stack = [placed]
        while stack:
            node = stack.pop()
            children = lod.child_nodes(node)
            stack += children
            if type(node).__name__ != "NiLODNode":
                continue
            files = known.get((asset.lower(), str(node.name)), {})
            for stub in children:
                name = str(getattr(stub, "name", ""))
                if name not in files or lod.child_nodes(stub):
                    continue
                grafted += terrain.fill_stub(stub, name, files[name], read)
    return grafted
