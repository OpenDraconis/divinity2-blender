"""The game's documents, as the unpack hands them over.

Most of this game's `.xml` files are not text: they are a tree with every name
replaced by a 32-bit hash, packed into a NIF container. divinity2-lib (`dv2lib`,
bundled as a wheel) reads them and names them, then writes each one as plain JSON
under `docs/<archive path>.json` when the game is unpacked (the preferences' button, or
`python -m dv2lib unpack <folder>`).

This reads that JSON back. A tree is `{"name", "attrs", "text"?, "children"?}`,
an unrecovered name arrives as `#hhhhhhhh`, and **the children are already in
the engine's order** -- `xml::dom::CStreamableNode::LoadBinary` fills the last
child slot first, and the unpack undoes that once, for everything.

A document is found by the path the add-on would have opened, in the folders
`use` was given or `DV2_DOCS` lists. The add-on needs no name table and no
parser of its own.
"""

import fnmatch
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

#: Folders holding a `docs/` tree, searched in the order they were given.
ROOTS: list = []

#: Every path a reader asked for and could not get -> why. A path the game does
#: not ship is an absence and not recorded; a document the game ships and no
#: folder holds, or one that will not parse, is. Before this, a broken
#: `scenery.xml` read as an empty region with nothing said.
UNREAD: dict = {}

#: Every document a reader got, by its lower-cased archive path with `/`: what a
#: caller checks a list of documents against, so one nobody read has to say why.
READ: set = set()


def use(*folders) -> None:
    """Look documents up in these folders too."""
    for folder in folders:
        if folder and Path(folder) not in ROOTS:
            ROOTS.append(Path(folder))


def begin(*folders) -> None:
    """Start one run: exactly these folders (and `DV2_DOCS`), and nothing read
    or missed before. A second region read in the same session must not find
    the first one's documents, nor count its reads."""
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
    """The JSON of the document at `path`, or None when no folder holds it.

    The path is read from its leftmost part that is a top-level name of the
    game -- `World`, `Episodes`, `forest-settings.xml` -- and matched exactly
    from there, so a document that is absent never falls through to another
    of the same file name further up.
    """
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
    """The lower-cased archive path of a document's JSON file."""
    for root in roots():
        base = root / "docs"
        if base in found.parents:
            return found.relative_to(base).as_posix()[:-len(".json")].lower()
    return ""


def glob(game_root, pattern: str) -> list:
    """Every document a folder holds whose archive path matches `pattern`, as the
    path it has under `game_root`. `*` crosses folders, as `fnmatch` has it.

    A region bundle holds only its own documents, so asking it lists what the
    bundle contains; an unpacked game lists what the game ships.
    """
    want = pattern.lower()
    found = {}
    for root in roots():
        base = root / "docs"
        for key, path in _index(root).items():
            if fnmatch.fnmatchcase(key, want):
                found.setdefault(key, Path(game_root) / path.relative_to(base).as_posix()[:-len(".json")])
    return [found[k] for k in sorted(found)]


def hash_of(name: str) -> int:
    """Larian's 32-bit name hash, `h * 33 + c` over latin-1. Case-sensitive."""
    h = 0
    for c in name.encode("latin-1"):
        h = (h * 33 + c) & 0xFFFFFFFF
    return h


@dataclass
class Node:
    name: str
    attributes: dict = field(default_factory=dict)  # name -> value, in file order
    children: list = field(default_factory=list)
    text: str = ""

    def is_a(self, name: str) -> bool:
        return self.name == name

    def get(self, name: str, default=None):
        """An attribute by name -- or by its hash, when no name was recovered for it."""
        if name in self.attributes:
            return self.attributes[name]
        return self.attributes.get(f"#{hash_of(name):08x}", default)

    def named(self) -> dict:
        return dict(self.attributes)

    def find_all(self, name: str):
        """Every descendant with this element name, in document order."""
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
    """`{"name", "attrs", "children"}`, and `"text"` when there is any -- the shape
    `region.json` has always carried a settings file in."""
    out = {"name": n.name, "attrs": dict(n.attributes),
           "children": [to_plain(c) for c in n.children]}
    if n.text:
        out["text"] = n.text
    return out


def walk(tree: dict):
    """Every element of a plain tree, `to_plain`'s shape, in document order."""
    yield tree
    for child in tree.get("children", ()):
        yield from walk(child)


def number(value, default: float = 0.0) -> float:
    """An attribute as a number, or `default` where it is absent or not one."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read(path):
    """The document at `path` as a `Node`, or None -- with the reason recorded in
    `UNREAD` whenever the game ships the file."""
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
