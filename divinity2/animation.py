"""Clips.

A Divinity II clip does not store a key per frame. It stores the control
points of a cubic B-spline, quantised to 16-bit integers, and the game
evaluates the curve as it plays. This is why a keyframe importer reads such a
clip and finds nothing: there are no keyframes in it to find.

`nifgen` already undoes the quantisation -- `get_translations`,
`get_rotations`, `get_scales` hand back the control points as floats. What is
left is evaluating the curve through them, which is what this module does.

A track whose handle reads `NO_HANDLE` is not animated at all; the
interpolator's own static transform is the value for the whole clip.
"""

from dataclasses import dataclass, field

#: A handle of 0xFFFF means "this track is not animated".
NO_HANDLE = 65535

#: Gamebryo's B-splines are cubic.
DEGREE = 3

BSPLINE_INTERPOLATOR = "NiBSplineCompTransformInterpolator"
TRANSFORM_INTERPOLATOR = "NiTransformInterpolator"


def evaluate(control_points: list, at: float) -> tuple:
    """A cubic B-spline through `control_points`, at 0.0 <= at <= 1.0.

    The control points are not points on the curve; each span is a weighted
    blend of four of them. Treating them as keyframes -- which is the tempting
    shortcut -- gives an animation that is close but wrong, and wrong in a way
    that looks like bad rigging rather than bad maths.

    The knots are open uniform, clamped at both ends: `0,0,0,0,1,...,n-4,
    n-3,n-3,n-3,n-3` over `n` points, so the curve starts on the first point
    and ends on the last. That is `NiBSplineBasis<float,3>::Compute` @652dc0,
    whose first and last spans weigh with 1 and 1/2 where the inner ones
    weigh with 1/2 and 1/3. The unclamped basis missed both ends, so a
    looping clip jumped at every cycle.
    """
    n = len(control_points)
    if n == 0:
        return ()
    if n <= DEGREE:
        return tuple(control_points[-1])

    spans = n - DEGREE
    knots = [0] * DEGREE + list(range(spans + 1)) + [spans] * DEGREE
    u = max(0.0, min(1.0, at)) * spans
    i = min(int(u), spans - 1) + DEGREE

    b = [1.0]
    for d in range(1, DEGREE + 1):
        nxt = [0.0] * (d + 1)
        for k, value in enumerate(b):
            j = i - d + 1 + k
            left, right = knots[j + d] - knots[j], knots[j + d] - u
            share = value * right / left if left else 0.0
            nxt[k] += share
            nxt[k + 1] += value - share
        b = nxt

    width = len(control_points[i - DEGREE])
    return tuple(
        sum(b[k] * control_points[i - DEGREE + k][axis] for k in range(DEGREE + 1))
        for axis in range(width)
    )


@dataclass
class Track:
    """What one bone does over one clip."""

    node: str
    translations: list = field(default_factory=list)
    rotations: list = field(default_factory=list)
    scales: list = field(default_factory=list)
    static: object = None  # NiQuatTransform, when a track is not animated

    @property
    def animated(self) -> bool:
        return bool(self.translations or self.rotations or self.scales)


def _as_lists(interpolator):
    """Control points, or empty where the handle says the track is static."""
    def maybe(handle, get, wrap):
        if handle == NO_HANDLE:
            return []
        return [wrap(v) for v in get()]

    return (
        maybe(interpolator.translation_handle, interpolator.get_translations, tuple),
        maybe(interpolator.rotation_handle, interpolator.get_rotations, tuple),
        maybe(interpolator.scale_handle, interpolator.get_scales, lambda v: (v,)),
    )


@dataclass
class Event:
    """A named moment in a clip, from its `NiTextKeyExtraData`."""

    time: float
    text: str


def events(sequence) -> list[Event]:
    """What the clip says happens, and when.

    Every clip is bracketed by `start` and `end`. The rest is a small grammar,
    and it is worth knowing which half of it belongs to whom:

    `morph:` is Gamebryo's, not Divinity's. `NiControllerSequence` looks it up
    in `FindCorrespondingMorphFrame` and `VerifyMatchingMorphKeys`: a
    `morph: L_Foot_Down` on a walk and the same label on a run mark the frames
    that must be lined up when one blends into the other. It is a blend
    alignment point, and only incidentally the frame a foot lands on.

    `eq=` and `ue=` are Divinity's, and they drive equipment:
    `eq=handR:2H_Sword_Alguard` puts an item in a slot, `ue=weaponSlotBack`
    takes it out again. The slot resolves to a bone through the engine's own
    table -- see `divinity2/engine.py`. `s=Footstep_Walk` plays a sound, and a
    bare `v=-5` ramps a value as a body falls.

    They are carried through as pose markers so the timing survives the trip
    into another engine, where it would otherwise have to be re-authored by
    eye.
    """
    keys = getattr(sequence, "text_keys", None)
    if keys is None:
        return []
    return [Event(time=float(k.time), text=str(k.value)) for k in keys.text_keys]


#: A component the file does not carry is written as -FLT_MAX, not left out.
#: `trs_valid`, which is supposed to say which of the three are present, is an
#: empty array at NIF 20.3.0.9 -- the version does not write it. The sentinel
#: in the value is the only thing that tells the truth.
INVALID = 3.4028234663852886e38


def sample(track: Track, at: float) -> tuple:
    """`(translation, rotation wxyz, scale)` of one track at `0 <= at <= 1`, in the
    file's own units. A component the track neither animates nor states is None."""
    static = track.static
    t = r = s = None
    if static is not None:
        tr, ro = static.translation, static.rotation
        if all(abs(v) < INVALID for v in (tr.x, tr.y, tr.z)):
            t = (tr.x, tr.y, tr.z)
        if all(abs(v) < INVALID for v in (ro.w, ro.x, ro.y, ro.z)):
            r = (ro.w, ro.x, ro.y, ro.z)
        if abs(static.scale) < INVALID:
            s = static.scale
    if track.translations:
        t = evaluate(track.translations, at)
    if track.rotations:
        r = evaluate(track.rotations, at)
    if track.scales:
        s = evaluate(track.scales, at)[0]
    return t, r, s


def tracks(sequence) -> list[Track]:
    """One track per controlled block of a `NiControllerSequence`."""
    out = []
    for block in sequence.controlled_blocks:
        interpolator = block.interpolator
        if interpolator is None:
            continue
        node = str(block.node_name)
        kind = type(interpolator).__name__

        if kind == BSPLINE_INTERPOLATOR:
            translations, rotations, scales = _as_lists(interpolator)
            out.append(
                Track(
                    node=node,
                    translations=translations,
                    rotations=rotations,
                    scales=scales,
                    static=interpolator.transform,
                )
            )
        elif kind == TRANSFORM_INTERPOLATOR:
            # Plain keyframes. A clip mixes both kinds: the root is usually a
            # transform interpolator while the bones are B-splines.
            out.append(Track(node=node, static=interpolator.transform))

    return out
