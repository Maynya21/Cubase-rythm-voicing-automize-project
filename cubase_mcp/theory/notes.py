"""Pitch / note-name utilities.

Cubase(Steinberg)의 기본 노트 표기는 가운데 도가 **C3 = 60** 입니다.
(환경설정에서 바꿀 수 있으므로 ``middle_c_octave`` 로 조정 가능합니다.)
"""

from __future__ import annotations

import re
from typing import Iterable

# 기본 가온음자리 옥타브. Cubase 기본값은 3 (C3 = MIDI 60).
DEFAULT_MIDDLE_C_OCTAVE = 3

_PC_OF_LETTER = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# 조표에 따라 어느 쪽 표기를 쓸지 결정할 때 사용하는 플랫 계열 조성
FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb", "d", "g", "c", "f", "bb", "eb", "ab"}

_NOTE_RE = re.compile(r"^([A-Ga-g])([#b♯♭x]*)(-?\d+)?$")

MIN_MIDI = 0
MAX_MIDI = 127


class NoteError(ValueError):
    """노트 이름을 해석할 수 없을 때."""


def accidental_offset(acc: str) -> int:
    """``#``, ``b``, ``x``(더블샤프), 유니코드 기호를 반음 오프셋으로 변환."""
    offset = 0
    for ch in acc:
        if ch in "#♯":
            offset += 1
        elif ch in "b♭":
            offset -= 1
        elif ch == "x":
            offset += 2
        else:
            raise NoteError(f"알 수 없는 임시표: {ch!r}")
    return offset


def parse_pitch_class(name: str) -> int:
    """``C``, ``F#``, ``Bb``, ``Cx`` 같은 음이름 -> 0..11 피치 클래스."""
    m = _NOTE_RE.match(name.strip())
    if not m or m.group(3) is not None:
        # 옥타브가 붙어 있으면 pitch class 전용 파서로는 거절
        m2 = _NOTE_RE.match(name.strip())
        if not m2:
            raise NoteError(f"음이름을 해석할 수 없습니다: {name!r}")
        if m2.group(3) is not None:
            raise NoteError(f"옥타브 없는 음이름이 필요합니다: {name!r}")
    letter, acc, _ = m.groups()
    return (_PC_OF_LETTER[letter.upper()] + accidental_offset(acc)) % 12


def parse_note(name: str, middle_c_octave: int = DEFAULT_MIDDLE_C_OCTAVE) -> int:
    """``C3``, ``F#4``, ``Bb2`` 같은 노트 이름 -> MIDI 번호.

    옥타브가 생략되면 가온음자리 옥타브로 간주합니다.
    """
    m = _NOTE_RE.match(name.strip())
    if not m:
        raise NoteError(f"노트 이름을 해석할 수 없습니다: {name!r}")
    letter, acc, octave = m.groups()
    pc = _PC_OF_LETTER[letter.upper()] + accidental_offset(acc)
    oct_i = middle_c_octave if octave is None else int(octave)
    midi = (oct_i + 5 - middle_c_octave) * 12 + pc
    if not MIN_MIDI <= midi <= MAX_MIDI:
        raise NoteError(f"MIDI 범위를 벗어났습니다({midi}): {name!r}")
    return midi


def note_name(
    midi: int,
    middle_c_octave: int = DEFAULT_MIDDLE_C_OCTAVE,
    flats: bool = False,
) -> str:
    """MIDI 번호 -> ``C3`` 형태의 노트 이름."""
    names = FLAT_NAMES if flats else SHARP_NAMES
    octave = midi // 12 - 5 + middle_c_octave
    return f"{names[midi % 12]}{octave}"


def pitch_class_name(pc: int, flats: bool = False) -> str:
    names = FLAT_NAMES if flats else SHARP_NAMES
    return names[pc % 12]


def key_prefers_flats(key: str) -> bool:
    """조성 이름을 보고 플랫 표기가 자연스러운지 판단."""
    tonic = key.strip().split()[0] if key.strip() else "C"
    tonic = tonic.rstrip("m")
    return "b" in tonic or tonic in {"F"}


def clamp_to_range(midi: int, lo: int, hi: int) -> int:
    """옥타브 단위로 옮겨 ``lo..hi`` 안에 들어오게 만듭니다."""
    if lo > hi:
        raise ValueError("lo가 hi보다 큽니다")
    while midi < lo:
        midi += 12
    while midi > hi:
        midi -= 12
    # 범위가 한 옥타브보다 좁으면 되돌아갈 수 있으므로 최종 클램프
    return max(MIN_MIDI, min(MAX_MIDI, midi))


def nearest_octave(pc: int, target: int) -> int:
    """피치 클래스 ``pc`` 를 ``target`` 에 가장 가까운 실제 음높이로."""
    base = target - (target % 12) + (pc % 12)
    best = base
    for cand in (base - 12, base, base + 12):
        if MIN_MIDI <= cand <= MAX_MIDI and abs(cand - target) < abs(best - target):
            best = cand
    return max(MIN_MIDI, min(MAX_MIDI, best))


def format_notes(
    pitches: Iterable[int],
    middle_c_octave: int = DEFAULT_MIDDLE_C_OCTAVE,
    flats: bool = False,
) -> str:
    return " ".join(note_name(p, middle_c_octave, flats) for p in pitches)
