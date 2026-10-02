import struct
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PureWindowsPath

from .nif import read_nif

SKELETON = "CSkeletonDataEntry"
MESH = "CMeshDataEntry"
ANIMATION = "CAnimationDataEntry"
ANIMATION_SET = "CAMDataEntry"

CHARACTER_SUFFIX = ".cat"

ROOT_BLOCK = "MdlMan::CModelTemplateDataEntry"

STREAMABLE = "CStreamableAssetData"


@dataclass
class Clip:
    name: str
    start: float
    stop: float
    sequence: object

    @property
    def duration(self) -> float:
        return self.stop - self.start


@dataclass
class Mesh:
    name: str
    root: object
    entry: dict | None = None


@dataclass
class Character:
    name: str
    path: Path
    skeleton: object = None
    meshes: list[Mesh] = field(default_factory=list)
    clips: list[Clip] = field(default_factory=list)
    animation_set: bytes = b""


def _kind(block) -> str:
    return type(block).__name__.split("::")[-1]


def _sequences(nif) -> list[Clip]:
    return [
        Clip(name=str(s.name), start=s.start_time, stop=s.stop_time, sequence=s)
        for s in nif.blocks
        if type(s).__name__ == "NiControllerSequence"
    ]


def read_model(path: str | Path) -> Character:
    path = Path(path)
    if path.is_dir():
        return read_compiled(path)
    if path.suffix.lower() == CHARACTER_SUFFIX:
        return read_character(path)
    return read_asset(path)


def read_compiled(group: str | Path) -> Character:
    group = Path(group)
    files = sorted(group.glob("*.nif"), key=lambda p: (len(p.stem), p.stem))
    if not files:
        raise ValueError(f"{group.name} holds no NIF")
    model = read_asset(files[-1])
    model.name = group.parent.name if _only_group(group) else (
        f"{group.parent.name} {group.name}"
    )
    model.path = group
    return model


def _only_group(group: Path) -> bool:
    return len(list(group.parent.glob("LODGroup*"))) == 1


def read_asset(path: str | Path) -> Character:
    path = Path(path)
    nif = read_nif(path)

    block = next((b for b in nif.blocks if type(b).__name__ == STREAMABLE), None)
    root = block.root if block is not None else None
    if root is None:
        root = next((b for b in nif.blocks if type(b).__name__ == "NiNode"), None)
    if root is None:
        raise ValueError(f"{path.name} holds no model")

    skinned = any(type(b).__name__ == "NiSkinInstance" for b in nif.blocks)
    return Character(
        name=path.stem,
        path=path,
        skeleton=root if skinned else None,
        meshes=[Mesh(name=path.stem, root=root)],
        clips=_sequences(nif),
        animation_set=(
            bytes(block.data) if block is not None and block.has_data else b""
        ),
    )


# CMdlManMapper::Initialize @68a2e0 decomp
MESH_ENTRIES = "MdlManBinary.nif"


# CModelPrototype::LoadBinary @c99900 decomp, CModelTemplate::LoadBinary @c9c8a0 decomp, CMesh::LoadBinary @c97ca0 decomp
@lru_cache(maxsize=4)
def model_manager(path: str | Path) -> dict:
    path = Path(path)
    out = {"entries": {}, "templates": {}, "meshes": {}, "groups": {}, "descriptors": {},
           "prototypes": {}, "template_models": {}, "enums": {}, "slots": {}, "mesh_blocks": {}}
    if not path.is_file():
        return out
    data = path.read_bytes()
    u32 = lambda at: struct.unpack_from("<I", data, at)[0]   # noqa: E731
    at = data.index(b"\n") + 1 + 4 + 1 + 4
    blocks = u32(at); at += 4
    types = []
    count = struct.unpack_from("<H", data, at)[0]; at += 2
    for _ in range(count):
        n = u32(at); types.append(data[at + 4:at + 4 + n].decode("latin-1")); at += 4 + n
    kinds = struct.unpack_from(f"<{blocks}H", data, at); at += 2 * blocks
    sizes = struct.unpack_from(f"<{blocks}I", data, at); at += 4 * blocks
    strings = []
    count = u32(at); at += 8
    for _ in range(count):
        n = u32(at); strings.append(data[at + 4:at + 4 + n].decode("latin-1")); at += 4 + n
    at += 4 + 4 * u32(at)
    text = lambda i: strings[i] if 0 <= i < len(strings) else None   # noqa: E731

    starts, names = [], {}
    for kind, size in zip(kinds, sizes):
        starts.append(at)
        at += size
    for index, (kind, start) in enumerate(zip(kinds, starts)):
        if types[kind & 0x7FFF] == "CMeshEntry":
            name, base, extra = struct.unpack_from("<IIi", data, start)
            names[index] = text(name)
            out["entries"][text(name).lower()] = {"name": text(name), "texture_base": text(base),
                                                  "extra_data": text(extra), "search": bool(data[start + 12])}
    sized = lambda at: (data[at + 4:at + 4 + u32(at)].rstrip(b"\0").decode("latin-1"),  # noqa: E731
                        at + 4 + u32(at))
    for index, (kind, start) in enumerate(zip(kinds, starts)):
        kind = types[kind & 0x7FFF]
        # CKFMRegisterLayer::CollectKFMDescriptors @6c8950 decomp
        if kind == "CPropertyGroup":
            out["groups"][index] = {u32(start + 4 + 12 * i): struct.unpack_from("<Q", data, start + 8 + 12 * i)[0]
                                    for i in range(u32(start))}
        elif kind == "CKFMDescriptor":
            out["descriptors"][index] = {"kfm": text(u32(start)), "properties": u32(start + 4)}
        elif kind == "CModelPrototype":
            at = start + 16
            at += 4 + 12 * u32(at)
            order = [u32(at + 4 + 4 * i) for i in range(u32(at))]
            at += 4 + 4 * u32(at)
            at += 4 + 8 * u32(at)
            sets = [u32(at + 4 + 4 * i) for i in range(u32(at))]
            at += 4 + 4 * u32(at)
            out["prototypes"][index] = {
                "name": text(u32(start)),
                "properties": u32(start + 12),
                "animation_sets": sets,
                "slot_order": order,
                "slots": [u32(at + 8 + 8 * i) for i in range(u32(at))],
            }
        elif kind == "CSlot":
            count = u32(start + 12)
            at = start + 16 + 4 * count
            out["slots"][index] = {"name": text(u32(start)), "attach": text(u32(start + 4)) or "",
                                   "id": u32(start + 8),
                                   "equipment": [u32(start + 16 + 4 * i) for i in range(count)],
                                   "meshes": [u32(at + 4 + 4 * i) for i in range(u32(at))]}
        elif kind == "CStringMapper":
            at = start + 4
            for _ in range(u32(start)):
                at = sized(at)[1] + 4
            keys, count, at = {}, u32(at), at + 4
            for _ in range(count):
                name, at = sized(at)
                keys[u32(at)] = name
                at += 4
            count, at = u32(at), at + 4
            for _ in range(count):
                key, values, at = u32(at), u32(at + 4), at + 8
                ordinals = {}
                for _ in range(values):
                    name, at = sized(at)
                    ordinals[name] = u32(at)
                    at += 8
                out["enums"][keys.get(key, key)] = {"key": key, "values": ordinals}
        elif kind == "CModelTemplate":
            name, count = u32(start), u32(start + 16)
            pos, assigned, defaults = start + 20, set(), {}
            for _ in range(count):
                slot, pos = sized(pos)
                entry, pos = sized(pos)
                if entry:
                    assigned.add(entry)
                    defaults[slot] = entry
            out["template_models"][text(name).lower()] = {"name": text(name), "prototype": u32(start + 8),
                                                          "properties": u32(start + 12), "defaults": defaults}
            out["templates"].setdefault(text(name).lower(), set()).update(assigned)
        elif kind == "CMesh":
            name, count = u32(start + 4), u32(start + 13)
            linked = out["meshes"].setdefault(text(name).lower(), set())
            linked.update(names[u32(start + 17 + 8 * i + 4)] for i in range(count)
                          if u32(start + 17 + 8 * i + 4) in names)
            out["mesh_blocks"][index] = {
                "node": text(name), "skinned": bool(data[start + 8]), "equipment": u32(start + 9),
                "entries": {u32(start + 17 + 8 * i): names.get(u32(start + 17 + 8 * i + 4))
                            for i in range(count)}}
    return out


def mesh_entry(path: str | Path, template: str, part: str) -> dict | None:
    manager = model_manager(path)
    assigned = {e.lower() for e in manager["templates"].get(template.lower(), ())}
    stem = PureWindowsPath(part).stem.lower()
    found = ({stem} | {e.lower() for e in manager["meshes"].get(stem, ())}) & assigned
    return manager["entries"].get(next(iter(found))) if len(found) == 1 else None


# MdlMan::GetHashValue @c71ab0 decomp
def hash_name(name: str) -> int:
    h = 0
    for byte in name.encode("latin-1"):
        h = ((h * 33 + (byte - 256 if byte > 127 else byte)) & 0xFFFFFFFF) % 0xFFFFFFFF
    return h


def prototype_named(path: str | Path, prototype: str) -> dict | None:
    manager = model_manager(path)
    return next((p for p in manager["prototypes"].values() if (p["name"] or "").lower() == prototype.lower()),
                None)


# CModel::AttachPart @c79ce0 decomp, CModelPrototype::GetDescriptorByName @c99290 decomp, CSlot::GetDescriptor @1093030 decomp
def equipment(path: str | Path, prototype: str, name: str, slot: str | None = None) -> dict | None:
    found = prototype_named(path, prototype)
    if found is None or not name:
        return None
    key = hash_name(name)
    held = slot_contents(path, prototype)
    for slot_name in ([slot] if slot in held else held):
        mesh = held[slot_name]["meshes"].get(key)
        if mesh is None:
            continue
        manager = model_manager(path)
        entry = manager["entries"].get((mesh["entries"][key] or "").lower())
        folder = found["name"] + "\\Meshes" if mesh["skinned"] else "Attachables"
        return {"name": name, "slot": slot_name, "attach": held[slot_name]["attach"], "node": mesh["node"],
                "skinned": mesh["skinned"], "file": f"{folder}\\{mesh['node']}.nif", "entry": entry}
    return None


# CSlot::GetDescriptor @1093030 decomp
@lru_cache(maxsize=64)
def slot_contents(path: str | Path, prototype: str) -> dict:
    manager = model_manager(path)
    found = prototype_named(path, prototype)
    out = {}
    for index in (found or {}).get("slots", ()):
        slot = manager["slots"].get(index)
        if slot is None:
            continue
        meshes = {}
        for linked in slot["meshes"]:
            mesh = manager["mesh_blocks"].get(linked)
            for key in (mesh or {}).get("entries", ()):
                meshes.setdefault(key, mesh)
        out[slot["name"]] = {"attach": slot["attach"], "id": slot["id"], "meshes": meshes}
    return out


def part_path(game_root: str | Path, part: dict) -> Path:
    path = Path(game_root) / "Win32" / "Characters"
    for step in PureWindowsPath(part["file"]).parts:
        path = next((p for p in path.iterdir() if p.name.lower() == step.lower()), path / step) \
            if path.is_dir() else path / step
    return path


# CModel::ProcessSkinnedGeometry @c7c4c0 decomp
def read_part(game_root: str | Path, part: dict) -> Character:
    path = part_path(game_root, part)
    model = read_asset(path)
    model.name = part["name"]
    model.skeleton = None
    model.clips = []
    model.animation_set = b""
    model.meshes = [Mesh(name=part["file"], root=model.meshes[0].root, entry=part["entry"])]
    return model


def read_character(path: str | Path) -> Character:
    path = Path(path)
    nif = read_nif(path)

    try:
        root = next(b for b in nif.blocks if type(b).__name__ == ROOT_BLOCK)
    except StopIteration:
        raise ValueError(f"{path.name} is not a character template") from None

    character = Character(name=path.stem, path=path)

    for entry in root.sub_entry_list:
        kind, name = _kind(entry), str(entry.name)

        if kind == SKELETON:
            character.skeleton = entry.skeleton_data_reference

        elif kind == MESH:
            character.meshes.append(Mesh(
                name=name, root=entry.mesh_data_reference,
                entry=mesh_entry(path.parent.parent / MESH_ENTRIES, path.stem, name)))

        elif kind == ANIMATION_SET:
            character.animation_set = bytes(entry.binary_data)

        elif kind == ANIMATION:
            for sequence in entry.controller_seq_list:
                character.clips.append(
                    Clip(
                        name=str(sequence.name),
                        start=sequence.start_time,
                        stop=sequence.stop_time,
                        sequence=sequence,
                    )
                )

    return character


def read_clips(path: str | Path) -> list[Clip]:
    return _sequences(read_nif(path))


# CDialogWrapper::SetSequences @ca0aa0 decomp, CDialogWrapper::GetSequence @ca0840 decomp
def read_dialog_clips(path: str | Path) -> dict[str, list[Clip]]:
    nif = read_nif(path)
    out: dict[str, list[Clip]] = {}
    for s in nif.blocks:
        if type(s).__name__ != "NiControllerSequence":
            continue
        source = next(str(x.string_data) for x in (nif.blocks[i] for i in s.div_2_ints)
                      if type(x).__name__ == "NiStringExtraData" and str(x.name) == "OriginalFilename")
        family, _, file = source.replace("\\", "/").partition("/")
        out.setdefault(family, []).append(
            Clip(name=Path(file).stem, start=s.start_time, stop=s.stop_time, sequence=s))
    return out
