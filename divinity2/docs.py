import fnmatch
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOTS: list = []

UNREAD: dict = {}

READ: set = set()


def use(*folders) -> None:
    for folder in folders:
        if folder and Path(folder) not in ROOTS:
            ROOTS.append(Path(folder))


def begin(*folders) -> None:
    ROOTS[:] = []
    UNREAD.clear()
    READ.clear()
    use(*folders)


def roots() -> list:
    listed = [Path(p) for p in os.environ.get("DV2_DOCS", "").split(os.pathsep) if p]
    return ROOTS + [p for p in listed if p not in ROOTS]


@lru_cache(maxsize=16)
def _index(root: Path) -> dict:
    base = root / "docs"
    return {p.relative_to(base).as_posix()[:-len(".json")].lower(): p
            for p in base.rglob("*.json")} if base.is_dir() else {}


def find(path):
    parts = [part.lower() for part in Path(path).parts]
    for root in roots():
        index = _index(root)
        tops = _tops(root)
        start = next((i for i, part in enumerate(parts) if part in tops), None)
        found = None if start is None else index.get("/".join(parts[start:]))
        if found is not None:
            return found
    return None


@lru_cache(maxsize=16)
def _tops(root: Path) -> frozenset:
    return frozenset(key.split("/", 1)[0] for key in _index(root))


def key_of(found: Path) -> str:
    for root in roots():
        base = root / "docs"
        if base in found.parents:
            return found.relative_to(base).as_posix()[:-len(".json")].lower()
    return ""


def glob(game_root, pattern: str) -> list:
    want = pattern.lower()
    found = {}
    for root in roots():
        base = root / "docs"
        for key, path in _index(root).items():
            if fnmatch.fnmatchcase(key, want):
                found.setdefault(key, Path(game_root) / path.relative_to(base).as_posix()[:-len(".json")])
    return [found[k] for k in sorted(found)]


def hash_of(name: str) -> int:
    h = 0
    for c in name.encode("latin-1"):
        h = (h * 33 + c) & 0xFFFFFFFF
    return h


@dataclass
class Node:
    name: str
    attributes: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    text: str = ""

    def is_a(self, name: str) -> bool:
        return self.name == name

    def get(self, name: str, default=None):
        if name in self.attributes:
            return self.attributes[name]
        return self.attributes.get(f"#{hash_of(name):08x}", default)

    def named(self) -> dict:
        return dict(self.attributes)

    def find_all(self, name: str):
        stack = [self]
        while stack:
            node = stack.pop()
            if node.name == name:
                yield node
            stack += reversed(node.children)


def node(tree: dict) -> Node:
    return Node(tree["name"], dict(tree["attrs"]),
                [node(c) for c in tree.get("children", ())], tree.get("text") or "")


def to_plain(n: Node) -> dict:
    out = {"name": n.name, "attrs": dict(n.attributes),
           "children": [to_plain(c) for c in n.children]}
    if n.text:
        out["text"] = n.text
    return out


def walk(tree: dict):
    yield tree
    for child in tree.get("children", ()):
        yield from walk(child)


def number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read(path):
    path = Path(path)
    found = find(path)
    if found is None:
        if path.is_file():
            UNREAD[path] = ("no document folder holds it; unpack the game again "
                            "from the add-on's preferences")
        return None
    try:
        made = node(json.loads(found.read_text(encoding="utf-8")))
        READ.add(key_of(found))
        return made
    except (OSError, ValueError, KeyError, TypeError) as exc:
        UNREAD[path] = f"{type(exc).__name__}: {exc}"
        return None
