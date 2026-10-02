from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

WIN32 = Path("Win32")

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
    kind: str

    def __str__(self) -> str:
        return self.name


@lru_cache(maxsize=8)
def assets(game_root: Path) -> tuple[Asset, ...]:
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
    path = Path(path)
    return any((path / folder).is_dir() for folder, _ in KINDS.values())
