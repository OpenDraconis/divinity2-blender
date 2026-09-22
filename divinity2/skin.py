"""Binding geometry to one armature.

A skinned shape stores its vertices in its own node's space, and one matrix
per bone to get them out of it: `NiSkinData.bone_list[i].skin_transform`.
Together with where that bone stands in the skeleton, that is the whole
deformation:

    v = Σᵢ wᵢ · Wᵢ · Bᵢ · v

`Bᵢ` is the bone's `skin_transform` and `Wᵢ` is the bone's world transform in
the skeleton file. Nothing else takes part.

In particular `NiSkinData.skin_transform` does not. It is the inverse of the
shape node's own world transform -- measured on `FroblinBoss_Armor_A`, the
node sits at (-393.0, -260.9, 79.2) and the skin transform undoes exactly
that -- so it says where the geometry came from, not where it goes. Folding
it into the deformation moves the armour half a metre off the body and moves
a shape that happens to sit at the origin not at all, which is why a
character can look right and its armour wrong at the same time.

So the skeleton file is the rest pose, all of it, for every mesh file of a
character. There is no second pose to reconcile and no reason for a second
armature.

Where a shape mentions a bone the armature does not have, its weight is
dropped and the rest renormalised, so the shape still arrives whole.
"""

import numpy as np

from .graph import matrix_of


def bone_matrices(shape) -> dict:
    """`Bᵢ` per bone name: the shape's own space into that bone's space."""
    skin = getattr(shape, "skin_instance", None)
    if skin is None or skin.data is None:
        return {}

    return {
        str(skin.bones[i].name): matrix_of(skin.data.bone_list[i].skin_transform)
        for i in range(skin.num_bones)
    }


def weights(shape, count: int) -> dict:
    """`wᵢ` per bone name, as arrays over the shape's vertices."""
    skin = getattr(shape, "skin_instance", None)
    if skin is None or skin.data is None:
        return {}

    out = {}
    for i in range(skin.num_bones):
        column = np.zeros(count, dtype=np.float64)
        for entry in skin.data.bone_list[i].vertex_weights:
            if 0 <= entry.index < count:
                column[entry.index] = entry.weight
        out[str(skin.bones[i].name)] = column
    return out


def rest_matrices(shape, rest: dict, count: int) -> np.ndarray | None:
    """Each vertex's blended 4x4 into the armature's rest pose, once, at import.

    `rest` maps a bone name to its 4x4 world matrix in the skeleton, in game
    units. Bones the armature does not have are dropped and the remaining
    weights renormalised, so a shape bound to a bone that was never built
    still arrives whole. None when the shape is not skinned to any of them.
    """
    into_bone = bone_matrices(shape)
    if not into_bone:
        return None

    per_bone = weights(shape, count)
    total = np.zeros((count, 4, 4), dtype=np.float64)
    mass = np.zeros(count, dtype=np.float64)

    for name, weight in per_bone.items():
        target = rest.get(name)
        if target is None:
            continue
        touched = weight > 0.0
        if not touched.any():
            continue
        combined = np.asarray(target) @ into_bone[name]
        total[touched] += weight[touched, None, None] * combined
        mass[touched] += weight[touched]

    bound = mass > 1e-6
    if not bound.any():
        return None

    total[bound] /= mass[bound, None, None]
    total[~bound] = np.eye(4)
    return total


def to_rest_pose(vertices: np.ndarray, total: np.ndarray) -> np.ndarray:
    """Positions moved by `rest_matrices`."""
    homogeneous = np.concatenate(
        [vertices, np.ones((len(vertices), 1), dtype=np.float64)], axis=1
    )
    return np.einsum("nij,nj->ni", total, homogeneous)[:, :3]


def rotate(directions: np.ndarray, total: np.ndarray) -> np.ndarray:
    """Normals and binormals moved the way the engine skins them: by the 3x3 of
    the same blended matrix, with no inverse transpose, then normalised
    (Developer's Cut skinned vertex shader, cache @0x7d1a;
    docs/sources.md, "Skinned normals")."""
    moved = np.einsum("nij,nj->ni", total[:, :3, :3], directions)
    length = np.linalg.norm(moved, axis=1, keepdims=True)
    return np.divide(moved, length, out=np.zeros_like(moved), where=length > 0)
