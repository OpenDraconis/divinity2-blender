import math
from dataclasses import dataclass, field

NO_HANDLE = 65535

DEGREE = 3

BSPLINE_INTERPOLATOR = "NiBSplineCompTransformInterpolator"
TRANSFORM_INTERPOLATOR = "NiTransformInterpolator"


# NiBSplineBasis::Compute @652dc0 decomp
def evaluate(control_points: list, at: float) -> tuple:
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
    node: str
    translations: list = field(default_factory=list)
    rotations: list = field(default_factory=list)
    scales: list = field(default_factory=list)
    static: object = None
    keys: "Keys | None" = None
    begin: float = 0.0
    end: float = 0.0

    @property
    def animated(self) -> bool:
        return bool(self.translations or self.rotations or self.scales or self.keys)


def _as_lists(interpolator):
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
    time: float
    text: str


def events(sequence) -> list[Event]:
    keys = getattr(sequence, "text_keys", None)
    if keys is None:
        return []
    return [Event(time=float(k.time), text=str(k.value)) for k in keys.text_keys]


INVALID = 3.4028234663852886e38


def sample(track: Track, at: float) -> tuple:
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
    if track.keys is not None:
        time = track.begin + max(0.0, min(1.0, at)) * (track.end - track.begin)
        keyed = track.keys.at(time)
        t = keyed[0] if keyed[0] is not None else t
        r = keyed[1] if keyed[1] is not None else r
        s = keyed[2] if keyed[2] is not None else s
    if track.translations:
        t = evaluate(track.translations, at)
    if track.rotations:
        r = evaluate(track.rotations, at)
    if track.scales:
        s = evaluate(track.scales, at)[0]
    return t, r, s


def tracks(sequence) -> list[Track]:
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
            data = getattr(interpolator, "data", None)
            out.append(Track(node=node, static=interpolator.transform,
                             keys=Keys.read(data) if data is not None else None,
                             begin=float(sequence.start_time), end=float(sequence.stop_time)))

    return out


def _kind(value) -> str:
    return str(getattr(value, "name", value))


def _v(value) -> tuple:
    if hasattr(value, "w"):
        return (float(value.w), float(value.x), float(value.y), float(value.z))
    if hasattr(value, "x"):
        return (float(value.x), float(value.y), float(value.z))
    return (float(value),)


def _add(a, b, k=1.0):
    return tuple(x + k * y for x, y in zip(a, b))


def _scale(a, k):
    return tuple(k * x for x in a)


# NiPosKey::GenInterp @620540 decomp, NiFloatKey::GenInterp @621b70 decomp, NiRotKey::GenInterp @6250c0 decomp
@dataclass
class Curve:
    kind: str
    times: list
    values: list
    ins: list = field(default_factory=list)
    outs: list = field(default_factory=list)
    a: list = field(default_factory=list)
    b: list = field(default_factory=list)

    def at(self, time: float) -> tuple:
        n = len(self.times)
        if n == 1:
            return self.values[0]
        if time > self.times[-1]:
            return self.values[-1]
        i = next(k for k in range(1, n) if time <= self.times[k]) - 1
        u = (time - self.times[i]) / (self.times[i + 1] - self.times[i])
        p0, p1 = self.values[i], self.values[i + 1]
        if self.kind == "LINEAR_KEY":
            return tuple((1.0 - u) * x + u * y for x, y in zip(p0, p1))
        if self.kind in ("QUADRATIC_KEY", "TBC_KEY"):
            out0, in1 = self.outs[i], self.ins[i + 1]
            return tuple(
                a + ((u * ((f + o) - 2.0 * (b - a)) + (3.0 * (b - a) - (2.0 * o + f))) * u + o) * u
                for a, b, o, f in zip(p0, p1, out0, in1))
        if self.kind == "LINEAR_ROT":
            return slerp(u, p0, p1)
        if self.kind == "TBC_ROT":
            return squad(u, p0, self.a[i], self.b[i + 1], p1)
        raise ValueError(f"key type {self.kind} is not interpolated")

    # NiBezPosKey::LoadBinary @626370 decomp, NiTCBPosKey::FillDerivedVals @6241c0 decomp, NiTCBFloatKey::FillDerivedVals @61ed20 decomp
    @classmethod
    def read(cls, group) -> "Curve | None":
        if group is None or not int(getattr(group, "num_keys", 0) or 0):
            return None
        kind = _kind(group.interpolation)
        keys = list(group.keys)
        curve = cls(kind, [float(k.time) for k in keys], [_v(k.value) for k in keys])
        if kind == "QUADRATIC_KEY":
            curve.ins = [_v(k.forward) for k in keys]
            curve.outs = [_v(k.backward) for k in keys]
        elif kind == "TBC_KEY":
            curve.ins, curve.outs = _tcb_tangents(curve.times, curve.values, [k.tbc for k in keys])
        elif kind != "LINEAR_KEY":
            raise ValueError(f"key type {kind} is not interpolated")
        return curve


# NiTCBPosKey::CalculateDVals @623f80 decomp
def _tcb_tangents(times, values, tbcs):
    n = len(values)
    ins, outs = [], []
    for i, p in enumerate(values):
        if n == 1:
            ins.append(_scale(p, 0.0)); outs.append(_scale(p, 0.0)); continue
        if i == 0:
            prev, nxt, dp, dn = _add(_scale(p, 2.0), values[1], -1.0), values[1], 1.0, 1.0
        elif i == n - 1:
            prev, nxt, dp, dn = values[i - 1], _add(_scale(p, 2.0), values[i - 1], -1.0), 1.0, 1.0
        else:
            prev, nxt, dp, dn = values[i - 1], values[i + 1], times[i] - times[i - 1], times[i + 1] - times[i]
        tension, continuity, bias = float(tbcs[i].t), float(tbcs[i].b), float(tbcs[i].c)
        h = (1.0 - tension) * 0.5
        back, ahead = _add(p, prev, -1.0), _add(nxt, p, -1.0)
        ds = _add(_scale(back, h * (1.0 - continuity) * (1.0 + bias)), ahead, h * (1.0 + continuity) * (1.0 - bias))
        dd = _add(_scale(back, h * (1.0 + continuity) * (1.0 + bias)), ahead, h * (1.0 - continuity) * (1.0 - bias))
        ins.append(_scale(ds, 2.0 * dp / (dp + dn)))
        outs.append(_scale(dd, 2.0 * dn / (dp + dn)))
    return ins, outs


# NiQuaternion::FastNormalize @5816d0 decomp
ISQRT_NEIGHBORHOOD = 0.9590659737586975
ISQRT_SCALE = 1.0003110170364380
ISQRT_ADDITIVE_CONSTANT = ISQRT_SCALE / ISQRT_NEIGHBORHOOD ** 0.5
ISQRT_FACTOR = ISQRT_SCALE * (-0.5 / (ISQRT_NEIGHBORHOOD ** 0.5 * ISQRT_NEIGHBORHOOD))
EPSILON = 0.001


def _fast_normalize(q):
    s = sum(x * x for x in q)
    k = ISQRT_ADDITIVE_CONSTANT + ISQRT_FACTOR * (s - ISQRT_NEIGHBORHOOD)
    if s <= 0.9152119755744934:
        k *= ISQRT_ADDITIVE_CONSTANT + ISQRT_FACTOR * (k * k * s - ISQRT_NEIGHBORHOOD)
        if s <= 0.6521196961402893:
            k *= ISQRT_ADDITIVE_CONSTANT + ISQRT_FACTOR * (k * k * s - ISQRT_NEIGHBORHOOD)
    return _scale(q, k)


# NiQuaternion::CounterWarp @5817d0 decomp
def _counter_warp(t, cos):
    k = 0.5854921936988831 * (1.0 - cos * 0.8227968811988831) ** 2
    return (((t + t) - 3.0) * t * k + 1.0 + k) * t


# NiQuaternion::Slerp @581970 decomp
def slerp(t, p, q):
    cos = sum(a * b for a, b in zip(p, q))
    w = 1.0 - _counter_warp(1.0 - t, cos) if t > 0.5 else _counter_warp(t, cos)
    return _fast_normalize(tuple(a + w * (b - a) for a, b in zip(p, q)))


# NiQuaternion::Squad @581c10 decomp
def squad(t, p, a, b, q):
    return slerp((t + t) * (1.0 - t), slerp(t, p, q), slerp(t, a, b))


# NiQuaternion::operator* @581b50 decomp
def _mul(p, q):
    pw, px, py, pz = p
    qw, qx, qy, qz = q
    return (pw * qw - px * qx - py * qy - pz * qz,
            pw * qx + px * qw + py * qz - pz * qy,
            pw * qy + py * qw + pz * qx - px * qz,
            pw * qz + pz * qw + px * qy - py * qx)


def _inverse(q):
    return (q[0], -q[1], -q[2], -q[3])


# NiQuaternion::Log @581cb0 decomp
def _log(q):
    angle = math.pi if q[0] <= -1.0 else 0.0 if q[0] >= 1.0 else math.acos(q[0])
    sin = math.sin(angle)
    k = angle / sin if abs(sin) >= EPSILON else 1.0
    return (0.0, k * q[1], k * q[2], k * q[3])


# NiQuaternion::Exp @5818a0 decomp
def _exp(q):
    angle = math.sqrt(q[1] ** 2 + q[2] ** 2 + q[3] ** 2)
    sin = math.sin(angle)
    k = sin / angle if abs(sin) >= EPSILON else 1.0
    return (math.cos(angle), k * q[1], k * q[2], k * q[3])


# NiRotKey::FillDerivedVals @625450 decomp, NiLinRotKey::Interpolate @620cd0 decomp, NiTCBRotKey::CalculateDVals @6211b0 decomp
def _rotations(data) -> Curve | None:
    keys = list(getattr(data, "quaternion_keys", None) or ())
    if not keys:
        return None
    kind = _kind(data.rotation_type)
    times = [float(k.time) for k in keys]
    values = []
    for k in keys:
        q = _v(k.value)
        if values and sum(a * b for a, b in zip(values[-1], q)) < 0.0:
            q = _scale(q, -1.0)
        values.append((max(-1.0, min(1.0, q[0])), q[1], q[2], q[3]))
    if kind == "LINEAR_KEY":
        return Curve("LINEAR_ROT", times, values)
    if kind != "TBC_KEY":
        raise ValueError(f"rotation key type {kind} is not interpolated")
    curve = Curve("TBC_ROT", times, values)
    n = len(values)
    for i, q in enumerate(values):
        if n == 1:
            curve.a.append(q); curve.b.append(q); continue
        j, k = (0, 1) if i == 0 else (n - 2, n - 1) if i == n - 1 else (i - 1, i + 1)
        tbc = keys[i].tbc
        tension, continuity, bias = float(tbc.t), float(tbc.b), float(tbc.c)
        log_prev = _log(_mul(_inverse(values[j]), q))
        log_next = _log(_mul(_inverse(q), values[k]))
        span = 1.0 / (times[k] - times[j])
        f = (times[i] - times[j]) * span * (1.0 - tension)
        ts = _add(_scale(log_next, (1.0 - continuity) * f * (1.0 - bias)), log_prev, f * (1.0 + continuity) * (1.0 + bias))
        curve.a.append(_mul(q, _exp(_scale(_add(ts, log_next, -1.0), 0.5))))
        g = (times[k] - times[i]) * span * (1.0 - tension)
        td = _add(_scale(log_next, (1.0 + continuity) * g * (1.0 - bias)), log_prev, g * (1.0 - continuity) * (1.0 + bias))
        curve.b.append(_mul(q, _exp(_scale(_add(log_prev, td, -1.0), 0.5))))
    return curve


# NiTransformInterpolator::Update @635cb0 decomp
@dataclass
class Keys:
    translation: Curve | None = None
    rotation: Curve | None = None
    euler: tuple = ()
    scale: Curve | None = None

    @classmethod
    def read(cls, data) -> "Keys":
        keys = cls(translation=Curve.read(data.translations), scale=Curve.read(data.scales))
        if int(getattr(data, "num_rotation_keys", 0) or 0):
            if _kind(data.rotation_type) == "XYZ_ROTATION_KEY":
                keys.euler = tuple(Curve.read(g) for g in data.xyz_rotations)
            else:
                keys.rotation = _rotations(data)
        return keys

    # NiEulerRotKey::Interpolate @61f530 decomp
    def at(self, time: float) -> tuple:
        t = self.translation.at(time) if self.translation else None
        s = self.scale.at(time)[0] if self.scale else None
        r = self.rotation.at(time) if self.rotation else None
        if self.euler:
            x, y, z = ((c.at(time)[0] if c else 0.0) for c in self.euler)
            cx, sx = math.cos(x * 0.5), math.sin(x * 0.5)
            cy, sy = math.cos(y * 0.5), math.sin(y * 0.5)
            cz, sz = math.cos(z * 0.5), math.sin(z * 0.5)
            r = (sx * sy * sz + cx * cz * cy,
                 sx * cz * cy - cx * sy * sz,
                 sx * cy * sz + cx * cz * sy,
                 cx * cy * sz - cz * sy * sx)
        return t, r, s
