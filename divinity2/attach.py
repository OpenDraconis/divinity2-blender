from pathlib import PureWindowsPath

from .engine import MAIN_HAND, SLOT_TO_NODE, node_for_slot

ATTACHABLES = "attachables"

SOCKETS = ("Bone_Weapon_01", "Bone_Weapon_02", "Bone_Weapon_03",
           "Bone_Weapon_04", "Bone_Weapon_05", "Bone_Weapon_06")


def is_attachable(entry_name: str) -> bool:
    parts = PureWindowsPath(str(entry_name)).parts
    return bool(parts) and parts[0].lower() == ATTACHABLES


def weapon_name(entry_name: str) -> str:
    return PureWindowsPath(str(entry_name)).stem


def attachment_bone(weapon: str, bone_names, index: int = 0) -> str | None:
    have = [s for s in SOCKETS if s in set(bone_names)]
    if not have:
        return None
    if index == 0 and node_for_slot(MAIN_HAND) in have:
        return node_for_slot(MAIN_HAND)
    return have[min(index, len(have) - 1)]
