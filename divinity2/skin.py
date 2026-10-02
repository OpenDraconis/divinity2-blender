import numpy as np

from .graph import matrix_of


def bone_matrices(shape) -> dict:
    skin = getattr(shape, "skin_instance", None)
    if skin is None or skin.data is None:
        return {}

    return {
        str(skin.bones[i].name): matrix_of(skin.data.bone_list[i].skin_transform)
        for i in range(skin.num_bones)
    }


def weights(shape, count: int) -> dict:
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
    homogeneous = np.concatenate(
        [vertices, np.ones((len(vertices), 1), dtype=np.float64)], axis=1
    )
    return np.einsum("nij,nj->ni", total, homogeneous)[:, :3]


def rotate(directions: np.ndarray, total: np.ndarray) -> np.ndarray:
    moved = np.einsum("nij,nj->ni", total[:, :3, :3], directions)
    length = np.linalg.norm(moved, axis=1, keepdims=True)
    return np.divide(moved, length, out=np.zeros_like(moved), where=length > 0)
