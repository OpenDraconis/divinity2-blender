NODES = {
    "Bone_Weapon_01": "weapon socket 1",
    "Bone_Weapon_02": "weapon socket 2",
    "Bone_Weapon_03": "weapon socket 3",
    "Bone_Weapon_04": "weapon socket 4",
    "Bone_Weapon_05": "weapon socket 5",
    "Bone_Weapon_06": "weapon socket 6",
    "Dummy_Cast_Primary": "a spell leaves the body",
    "Dummy_Cast_Secondary": "a second spell origin",
    "Dummy_Impact_01": "a hit registers",
    "Dummy_Impact_02": "a hit registers",
    "Dummy_Impact_03": "a hit registers",
    "Dummy_Impact_04": "a hit registers",
    "Dummy_Impact_05": "a hit registers",
    "Dummy_Impact_06": "a hit registers",
    "Dummy_Impact_07": "a hit registers",
    "Dummy_Impact_08": "a hit registers",
    "Dummy_Impact_09": "a hit registers",
    "Dummy_Impact_10": "a hit registers",
    "Dummy_Head_Above": "a status icon floats",
    "Dummy_Head_Around": "a status icon orbits",
    "Dummy_Foot_Left": "footstep dust",
    "Dummy_Foot_Right": "footstep dust",
    "Head": "the head, for a human",
    "Neck": "the neck",
    "Bone_Eye_Left": "left eye",
    "Bone_Eye_Right": "right eye",
    "Bone_Lid_Left": "left upper lid",
    "Bone_Lid_Right": "right upper lid",
}

SLOT_TO_NODE = {
    "handR": "Bone_Weapon_01",
    "weaponSlotBack": "Bone_Weapon_02",
    "handL": "Bone_Weapon_03",
    "armL": "Bone_Weapon_03",
    "weaponSlotBack2": "Bone_Weapon_04",
    "weaponSlotBack3": "Bone_Weapon_05",
    "weaponSlotBack4": "Bone_Weapon_06",
}

BODY_SLOTS = (
    "armor", "arms", "body", "claws", "gloves", "head", "helmet", "legs",
    "pants", "tail", "torso",
)

MAIN_HAND = "handR"


def node_for_slot(slot: str) -> str | None:
    return SLOT_TO_NODE.get(slot)
