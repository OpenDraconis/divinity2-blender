from pathlib import Path

from . import kfm
from .nif import read_nif

CHARACTERS = Path("Win32") / "Characters"
SKELETON_FILE = "Skeleton.nif"

NOT_A_PROTOTYPE = {"attachables"}


def prototypes(character) -> list[str]:
    seen = []
    for mesh in character.meshes:
        head = str(mesh.name).replace("\\", "/").split("/")[0]
        if head.lower() in NOT_A_PROTOTYPE or head in seen:
            continue
        seen.append(head)
    return seen


# CWrapperMan::GetWrapperInstance @c864d0 decomp
def prototype_of(character, game_root) -> str | None:
    for name in prototypes(character):
        if (Path(game_root) / CHARACTERS / name / SKELETON_FILE).is_file():
            return name
    return None


def skeleton_path(character, game_root) -> Path | None:
    name = prototype_of(character, game_root)
    if name is None:
        return None
    return Path(game_root) / CHARACTERS / name / SKELETON_FILE


def shared_skeleton(character, game_root):
    if character.skeleton is not None:
        return character.skeleton
    path = skeleton_path(character, game_root)
    if path is None:
        return None
    nif = read_nif(path)
    return next((b for b in nif.blocks if type(b).__name__ == "NiNode"), None)


def animation_set(character):
    if not character.animation_set:
        return None
    try:
        return kfm.read_headerless(bytes(character.animation_set))
    except (kfm.Truncated, ValueError):
        return None


# CRpgStats_V2_Character::DecideAnimBanks @838440 decomp
NPC_ACTION_BANKS = ("Base", "DialogSimple", "Die", "Skills", "Idle", "Melee")


# CKFMRegisterLayer::HandlePropertyChange @6c8ae0 decomp, CKFMRegisterLayer::CollectKFMDescriptors @6c8950 decomp, CProperty::CheckValues @471a80 decomp
def engine_clip_files(template: str, game_root, actions=NPC_ACTION_BANKS,
                      weapons=None, states=("Default", "Normal")) -> list[Path]:
    from . import character as dv2_character

    game_root = Path(game_root)
    manager = dv2_character.model_manager(game_root / CHARACTERS / dv2_character.MESH_ENTRIES)
    template_info = manager["template_models"].get(template.lower())
    enums, groups = manager["enums"], manager["groups"]
    if template_info is None or not enums:
        return []
    prototype = manager["prototypes"].get(template_info["prototype"])
    if prototype is None:
        return []

    def mask(key: str, names) -> int:
        values = enums[key]["values"]
        return sum(1 << values[n] for n in names if n in values)

    query = dict(groups.get(template_info["properties"], {}))
    query[enums["WeaponType"]["key"]] = mask("WeaponType", weapons) if weapons else (1 << 7) - 1
    query[enums["StateType"]["key"]] = mask("StateType", states)
    sub_class, animation = enums["SubClass"]["key"], enums["AnimationType"]

    def matching(asked: dict) -> list[str]:
        hit = []
        for link in prototype["animation_sets"]:
            descriptor = manager["descriptors"].get(link)
            if descriptor is None:
                continue
            has = groups.get(descriptor["properties"], {})
            if all(value & has[key] for key, value in asked.items() if key in has):
                hit.append(descriptor["kfm"])
        return hit

    names = []
    for action in actions:
        bit = animation["values"].get(action)
        if bit is None:
            continue
        asked = dict(query)
        asked[animation["key"]] = 1 << bit
        found = matching(asked)
        if not found:
            asked[sub_class] = asked.get(sub_class, 0) | mask("SubClass", ("Default",))
            found = matching(asked)
        names += [n for n in found if n not in names]

    folder = game_root / CHARACTERS / (prototype["name"] or "")
    files = []
    for name in names:
        found = folder / (Path(name.replace("\\", "/")).stem + ".kf")
        if found.is_file() and found not in files:
            files.append(found)
    return files


def clip_files(character, game_root) -> list[Path]:
    name = prototype_of(character, game_root)
    if name is None:
        return []
    directory = Path(game_root) / CHARACTERS / name

    parsed = animation_set(character)
    if parsed is None:
        return []
    named = {Path(f.replace("\\", "/")).name for f in parsed.kf_files}
    return sorted(directory / n for n in named if (directory / n).is_file())
