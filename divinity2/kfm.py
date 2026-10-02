import re
import struct
from dataclasses import dataclass, field

HEADER = b";Gamebryo KFM File Version"

BARE_TRANSITIONS = frozenset({4, 5})


class Truncated(ValueError):
    pass


class _Reader:
    def __init__(self, data: bytes, at: int = 0):
        self.data = data
        self.at = at

    def _take(self, count: int) -> bytes:
        end = self.at + count
        if end > len(self.data):
            raise Truncated(f"wanted {count} bytes at {self.at}")
        chunk = self.data[self.at : end]
        self.at = end
        return chunk

    def int32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def float32(self) -> float:
        return struct.unpack("<f", self._take(4))[0]

    def byte(self) -> int:
        return self._take(1)[0]

    def string(self) -> str:
        length = self.int32()
        if not 0 <= length <= len(self.data) - self.at:
            raise Truncated(f"string of {length} at {self.at}")
        return self._take(length).decode("cp1252", "replace")


@dataclass
class Transition:
    animation: int
    type: int
    duration: float = 0.0
    events: list = field(default_factory=list)
    text_key_pairs: int = 0


@dataclass
class Animation:
    event_code: int
    kf_file: str
    index: int
    transitions: list = field(default_factory=list)


@dataclass
class AnimationSet:
    skeleton: str = ""
    master: str = ""
    animations: list = field(default_factory=list)
    complete: bool = True

    source: bytes = b""

    @property
    def kf_files(self) -> list[str]:
        seen = []
        for animation in self.animations:
            if animation.kf_file and animation.kf_file not in seen:
                seen.append(animation.kf_file)
        if not self.complete:
            for name in named_kf_files(self.source):
                if name not in seen:
                    seen.append(name)
        return seen


def _transition(reader: _Reader) -> Transition:
    animation = reader.int32()
    kind = reader.int32()
    if kind in BARE_TRANSITIONS:
        return Transition(animation=animation, type=kind)

    duration = reader.float32()
    events = []
    for _ in range(reader.int32()):
        reader.int32()
        events.append(reader.string())
    return Transition(
        animation=animation,
        type=kind,
        duration=duration,
        events=events,
        text_key_pairs=reader.int32(),
    )


def _body(reader: _Reader) -> AnimationSet:
    out = AnimationSet(
        skeleton=reader.string(), master=reader.string(), source=reader.data
    )
    reader.int32()
    reader.int32()
    reader.float32()
    reader.float32()

    count = reader.int32()
    if not 0 <= count <= len(reader.data) // 8:
        raise Truncated(f"{count} animations in {len(reader.data)} bytes")

    for _ in range(count):
        mark = reader.at
        try:
            animation = Animation(
                event_code=reader.int32(),
                kf_file=reader.string(),
                index=reader.int32(),
            )
            animation.transitions = [
                _transition(reader) for _ in range(reader.int32())
            ]
        except (Truncated, struct.error, UnicodeError):
            reader.at = mark
            out.complete = False
            break
        out.animations.append(animation)
    return out


_KF_NAME = re.compile(rb"[\x20-\x7e]{4,}")


def named_kf_files(data: bytes) -> list[str]:
    seen = []
    for match in _KF_NAME.finditer(data):
        text = match.group().decode("cp1252", "replace")
        if text.lower().endswith(".kf") and text not in seen:
            seen.append(text)
    return seen


def read(data: bytes) -> AnimationSet:
    if not data.startswith(HEADER):
        raise ValueError("not a KFM")
    start = data.index(b"\n") + 1
    reader = _Reader(data, start)
    reader.byte()
    return _body(reader)


def read_headerless(data: bytes) -> AnimationSet:
    return _body(_Reader(data))
