"""표준 MIDI 파일(SMF) 작성기 — 외부 의존성 없음.

Cubase 가 그대로 읽을 수 있는 Format 1 파일을 만듭니다.
분해능은 큐베이스 기본값과 같은 **480 PPQ** 입니다.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import BinaryIO, Dict, List, Optional, Sequence, Tuple

PPQ = 480

# 메타 이벤트
_META = 0xFF
_END_OF_TRACK = 0x2F
_TEMPO = 0x51
_TIME_SIG = 0x58
_KEY_SIG = 0x59
_TRACK_NAME = 0x03
_INSTRUMENT_NAME = 0x04
_MARKER = 0x06


class MidiError(ValueError):
    pass


@dataclass
class Note:
    """틱 단위 노트 하나."""
    start: int
    duration: int
    pitch: int
    velocity: int = 90
    channel: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.pitch <= 127:
            raise MidiError(f"음높이가 MIDI 범위를 벗어났습니다: {self.pitch}")
        if not 1 <= self.velocity <= 127:
            raise MidiError(f"벨로시티가 범위를 벗어났습니다: {self.velocity}")
        if not 0 <= self.channel <= 15:
            raise MidiError(f"채널이 범위를 벗어났습니다: {self.channel}")
        if self.duration < 1:
            self.duration = 1
        if self.start < 0:
            self.start = 0


@dataclass
class Track:
    name: str = "Track"
    notes: List[Note] = field(default_factory=list)
    channel: int = 0
    program: Optional[int] = None      # GM 프로그램 번호 (0-127)
    markers: List[Tuple[int, str]] = field(default_factory=list)

    def add(self, note: Note) -> None:
        self.notes.append(note)


@dataclass
class MidiFile:
    tempo: float = 120.0
    time_signature: Tuple[int, int] = (4, 4)
    key_signature: Optional[Tuple[int, int]] = None   # (샾/플랫 수 -7..7, 0=장조 1=단조)
    tracks: List[Track] = field(default_factory=list)
    ppq: int = PPQ
    #: 템포 변화 [(틱, BPM)]
    tempo_changes: List[Tuple[int, float]] = field(default_factory=list)

    def add_track(self, track: Track) -> Track:
        self.tracks.append(track)
        return track


# --------------------------------------------------------------------------- #
# 저수준 인코딩
# --------------------------------------------------------------------------- #

def _varlen(value: int) -> bytes:
    """가변 길이 수량 인코딩."""
    if value < 0:
        raise MidiError(f"가변 길이 값은 음수일 수 없습니다: {value}")
    buf = value & 0x7F
    out = bytearray()
    value >>= 7
    while value:
        buf <<= 8
        buf |= ((value & 0x7F) | 0x80)
        value >>= 7
    while True:
        out.append(buf & 0xFF)
        if buf & 0x80:
            buf >>= 8
        else:
            break
    return bytes(out)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack(">I", len(payload)) + payload


def _meta(kind: int, data: bytes) -> bytes:
    return bytes([_META, kind]) + _varlen(len(data)) + data


def _text_meta(kind: int, text: str) -> bytes:
    """텍스트 메타 이벤트.

    SMF 규격의 텍스트는 원래 ASCII 입니다. Cubase(특히 Windows)는 UTF-8 트랙명을
    깨서 보여줄 수 있으므로 latin-1 로 넣을 수 있으면 그쪽을 씁니다.
    """
    try:
        data = text.encode("latin-1")
    except UnicodeEncodeError:
        data = text.encode("utf-8", errors="replace")
    return _meta(kind, data)


def _tempo_meta(bpm: float) -> bytes:
    if bpm <= 0:
        raise MidiError(f"BPM 은 0보다 커야 합니다: {bpm}")
    us_per_beat = int(round(60_000_000 / bpm))
    return _meta(_TEMPO, us_per_beat.to_bytes(3, "big"))


def _time_sig_meta(numerator: int, denominator: int) -> bytes:
    if denominator <= 0 or (denominator & (denominator - 1)) != 0:
        raise MidiError(f"박자표 분모는 2의 거듭제곱이어야 합니다: {denominator}")
    power = denominator.bit_length() - 1
    # 마디당 메트로놈 클릭은 분모에 맞춰 계산 (4분음표 = 24클릭)
    clocks = max(1, int(round(24 * 4 / denominator)))
    return _meta(_TIME_SIG, bytes([numerator, power, clocks, 8]))


def _key_sig_meta(sharps: int, minor: int) -> bytes:
    return _meta(_KEY_SIG, bytes([sharps & 0xFF, 1 if minor else 0]))


# --------------------------------------------------------------------------- #
# 트랙 직렬화
# --------------------------------------------------------------------------- #

def resolve_overlaps(notes: Sequence[Note]) -> List[Note]:
    """같은 채널·같은 음높이가 겹치지 않도록 앞 노트를 잘라냅니다.

    MIDI 에는 "이 note off 가 어느 note on 의 짝인지" 를 나타내는 정보가 없어서,
    같은 음이 겹치면 DAW 마다 해석이 달라집니다 (Cubase 에서는 음이 매달리거나
    엉뚱하게 잘립니다). 그래서 파일로 쓰기 전에 앞 노트를 다음 노트 직전까지
    줄이고, 시작점까지 같은 완전 중복은 더 긴 쪽만 남깁니다.
    """
    groups: Dict[Tuple[int, int], List[Note]] = {}
    for note in notes:
        groups.setdefault((note.channel, note.pitch), []).append(note)

    out: List[Note] = []
    for group in groups.values():
        group.sort(key=lambda n: (n.start, -n.duration))
        kept: List[Note] = []
        for note in group:
            if kept and kept[-1].start == note.start:
                continue                       # 완전 중복 (더 긴 쪽을 이미 담았음)
            kept.append(Note(note.start, note.duration, note.pitch,
                             note.velocity, note.channel))
        for i, note in enumerate(kept[:-1]):
            nxt = kept[i + 1]
            if note.start + note.duration > nxt.start:
                note.duration = max(1, nxt.start - note.start)
        out.extend(kept)
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


def _serialize_track(track: Track) -> bytes:
    """(절대 틱, 우선순위, 바이트) 목록을 만들어 델타타임으로 변환."""
    events: List[Tuple[int, int, bytes]] = []

    events.append((0, 0, _text_meta(_TRACK_NAME, track.name)))
    if track.program is not None:
        if not 0 <= track.program <= 127:
            raise MidiError(f"프로그램 번호가 범위를 벗어났습니다: {track.program}")
        events.append((0, 1, bytes([0xC0 | track.channel, track.program])))
    for tick, text in track.markers:
        events.append((max(0, tick), 1, _text_meta(_MARKER, text)))

    for note in resolve_overlaps(track.notes):
        ch = note.channel if note.channel else track.channel
        # note off 를 note on 보다 먼저 처리해야 같은 음이 겹칠 때 끊기지 않습니다.
        events.append((note.start + note.duration, 2,
                       bytes([0x80 | ch, note.pitch, 64])))
        events.append((note.start, 3, bytes([0x90 | ch, note.pitch, note.velocity])))

    events.sort(key=lambda e: (e[0], e[1]))

    out = bytearray()
    last = 0
    for tick, _prio, payload in events:
        out += _varlen(tick - last)
        out += payload
        last = tick
    out += _varlen(0) + _meta(_END_OF_TRACK, b"")
    return _chunk(b"MTrk", bytes(out))


def _conductor_track(mf: MidiFile) -> bytes:
    events: List[Tuple[int, int, bytes]] = [
        (0, 0, _text_meta(_TRACK_NAME, "Conductor")),
        (0, 1, _time_sig_meta(*mf.time_signature)),
        (0, 2, _tempo_meta(mf.tempo)),
    ]
    if mf.key_signature is not None:
        events.append((0, 3, _key_sig_meta(*mf.key_signature)))
    for tick, bpm in mf.tempo_changes:
        events.append((max(0, tick), 4, _tempo_meta(bpm)))
    events.sort(key=lambda e: (e[0], e[1]))

    out = bytearray()
    last = 0
    for tick, _prio, payload in events:
        out += _varlen(tick - last)
        out += payload
        last = tick
    out += _varlen(0) + _meta(_END_OF_TRACK, b"")
    return _chunk(b"MTrk", bytes(out))


def render(mf: MidiFile) -> bytes:
    """:class:`MidiFile` 을 SMF 바이트열로."""
    if not mf.tracks:
        raise MidiError("트랙이 하나도 없습니다")
    chunks = [_conductor_track(mf)] + [_serialize_track(t) for t in mf.tracks]
    header = struct.pack(">HHH", 1, len(chunks), mf.ppq)
    return _chunk(b"MThd", header) + b"".join(chunks)


def write(mf: MidiFile, path: str) -> str:
    """파일로 저장하고 경로를 돌려줍니다."""
    data = render(mf)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


# --------------------------------------------------------------------------- #
# 박(beat) <-> 틱 변환
# --------------------------------------------------------------------------- #

def beats_to_ticks(beats: float, ppq: int = PPQ) -> int:
    return int(round(beats * ppq))


def bars_to_beats(bars: float, time_signature: Tuple[int, int] = (4, 4)) -> float:
    num, den = time_signature
    return bars * num * (4.0 / den)
