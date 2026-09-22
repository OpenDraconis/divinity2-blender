"""Finding an asset by name.

A modder knows the name of the thing they want -- `goblin`, `damian`,
`chest`, `barrel` -- not which of four thousand files holds it. The catalog is
the index that turns one into the other, built by walking the install once.

The install lays its models out by kind, one folder each, and each folder uses
one extension:

| folder | extension | what is in it |
|---|---|---|
| `Characters/Templates` | `.cat` | a whole character, skeleton and clips |
| `Scenery` | `.item` | walls, doors, trees, furniture |
| `Items` | `.item` | weapons, armour, loot |
| `Effects` | `.item` | spell and particle effects |
| `FlyingFortresses` | `.item` | the flying fortresses, skinned |
| `CompiledAssets` | a folder | a compiled prop, one `LODGroup` per model |

That is every model file the game ships. `Characters/<family>/*.nif` is not
listed: those are the parts a `.cat` already bundles, and a skeleton, which
`divinity2.rig` finds on its own.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

WIN32 = Path("Win32")

#: Kind -> (folder under the install, the extension that folder uses).
#: `terrain` has no extension: a compiled model is a `LODGroup` folder whose
#: numbered files are its levels of detail. Indexing those files instead gives
#: 466 entries of which 296 are called `1` and 164 are called `2`.
KINDS = {
    "character": (WIN32 / "Characters" / "Templates", ".cat"),
    "scenery": (WIN32 / "Scenery", ".item"),
    "item": (WIN32 / "Items", ".item"),
    "effect": (WIN32 / "Effects", ".item"),
    "fortress": (WIN32 / "FlyingFortresses", ".item"),
    "terrain": (WIN32 / "CompiledAssets", ""),
}


@dataclass(frozen=True)
class Asset:
    name: str
    path: Path
    kind: str  # a key of KINDS

    def __str__(self) -> str:
        return self.name


@lru_cache(maxsize=8)
def assets(game_root: Path) -> tuple[Asset, ...]:
    """Every model file in the install, characters first."""
    root = Path(game_root)
    found = []
    for kind, (folder, suffix) in KINDS.items():
        directory = root / folder
        if not directory.is_dir():
            continue
        if suffix:
            found += [
                Asset(name=p.stem, path=p, kind=kind)
                for p in sorted(directory.rglob(f"*{suffix}"))
            ]
        else:
            for model in sorted(directory.iterdir()):
                groups = sorted(model.glob("LODGroup*")) if model.is_dir() else []
                found += [
                    Asset(
                        name=model.name if len(groups) == 1
                        else f"{model.name} {g.name}",
                        path=g,
                        kind=kind,
                    )
                    for g in groups
                ]
    return tuple(found)


def search(game_root: Path, term: str, kind: str = "", limit: int = 100) -> list[Asset]:
    """Assets whose name contains `term`, case ignored, best match first.

    A name that matches exactly comes first, then one that starts with the
    term, then the rest -- otherwise `chest` buries `Chest` under thirty
    `P_Cellars_Chest_Broken_C`.
    """
    term = (term or "").strip().lower()
    found = [
        a
        for a in assets(Path(game_root))
        if term in a.name.lower() and (not kind or a.kind == kind)
    ]
    found.sort(key=lambda a: (a.name.lower() != term,
                              not a.name.lower().startswith(term),
                              a.name.lower()))
    return found[:limit]


def looks_like_game(path) -> bool:
    """Is this an install root rather than some other directory?"""
    path = Path(path)
    return any((path / folder).is_dir() for folder, _ in KINDS.values())
