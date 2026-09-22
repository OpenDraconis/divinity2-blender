"""The shared rig.

Half the characters carry no skeleton and no clips of their own. They are not
broken: they share a rig with every other character of their family. 105 human
characters run on one `HumanMale` skeleton, and a Froblin has five animation
sets to pick from.

A character's family is the first segment of its mesh entries' paths --
`HumanMale\\Meshes\\M_Torso_A.nif` is family `HumanMale` -- and the family's
files live in `Win32/Characters/<family>/`:

    Skeleton.nif          the skeleton every character of the family uses
    <set>.kfm             one animation set: which clips, and how they join
    <set>.kf              the clips themselves

`Attachables` is not a family. It is where the weapons live.
"""

from pathlib import Path

from . import kfm
from .nif import read_nif

CHARACTERS = Path("Win32") / "Characters"
SKELETON_FILE = "Skeleton.nif"

#: A path segment that names a place, not a family.
NOT_A_FAMILY = {"attachables"}


def families(character) -> list[str]:
    """The families a character's meshes come from, most likely first."""
    seen = []
    for mesh in character.meshes:
        head = str(mesh.name).replace("\\", "/").split("/")[0]
        if head.lower() in NOT_A_FAMILY or head in seen:
            continue
        seen.append(head)
    return seen


def family_of(character, game_root) -> str | None:
    """The family that actually owns a skeleton on disk."""
    for name in families(character):
        if (Path(game_root) / CHARACTERS / name / SKELETON_FILE).is_file():
            return name
    return None


def skeleton_path(character, game_root) -> Path | None:
    name = family_of(character, game_root)
    if name is None:
        return None
    return Path(game_root) / CHARACTERS / name / SKELETON_FILE


def shared_skeleton(character, game_root):
    """The family's skeleton as a NiNode, or None when it owns one already."""
    if character.skeleton is not None:
        return character.skeleton
    path = skeleton_path(character, game_root)
    if path is None:
        return None
    nif = read_nif(path)
    return next((b for b in nif.blocks if type(b).__name__ == "NiNode"), None)


def animation_set(character):
    """The character's own KFM, parsed. See `divinity2.kfm`."""
    if not character.animation_set:
        return None
    try:
        return kfm.read_headerless(bytes(character.animation_set))
    except (kfm.Truncated, ValueError):
        return None


#: `DecideAnimBanks` @838440 for an NPC: these action banks are on (Idle in peace, Melee in combat),
#: never ComplexDialog, Ladder, Swim or Custom (measured in the running game; divinity2-port's notes, character-animation.md 1.1).
NPC_ACTION_BANKS = ("Base", "DialogSimple", "Die", "Skills", "Idle", "Melee")


def engine_clip_files(template: str, game_root, actions=NPC_ACTION_BANKS,
                      weapons=None, states=("Default", "Normal")) -> list[Path]:
    """The `.kf` files the engine can play for a model of that template.

    The character's own KFM is one bank of many: the rest come from its
    `CModelPrototype`'s `CKFMDescriptor`s, chosen per action bank
    (`CKFMRegisterLayer::HandlePropertyChange` @0x6c8ae0 ->
    `CollectKFMDescriptors` @0x6c8950). A descriptor matches when every
    property of the query shares a bit with the descriptor's
    (`CProperty::CheckValues` @0x471a80), and a key the descriptor lacks
    matches anything; when one action bank finds nothing, `Default` is added to
    the query's `SubClass` and it is asked again, so a sub-class KFM hides the
    family's default one.

    `weapons` defaults to every weapon set, which is every set a character of
    this template could reach; `states` is the posture bank plus `Default`.
    """
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

    query = dict(groups.get(template_info["properties"], {}))     # Class and SubClass
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
    """The `.kf` files the character's own KFM names, resolved on disk.

    The KFM writes the names the way the game sees them -- `.\\Froblin_Base.kf`,
    relative to the family's folder -- so only the last segment is used.
    """
    name = family_of(character, game_root)
    if name is None:
        return []
    directory = Path(game_root) / CHARACTERS / name

    parsed = animation_set(character)
    if parsed is None:
        return []
    named = {Path(f.replace("\\", "/")).name for f in parsed.kf_files}
    return sorted(directory / n for n in named if (directory / n).is_file())
