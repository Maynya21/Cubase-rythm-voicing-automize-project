"""조성, 스케일, 로마숫자 도수 해석."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

from .chords import Chord, ChordError, chord_to_symbol, parse_chord
from .notes import _PC_OF_LETTER, accidental_offset, pitch_class_name

SCALES = {
    "major":            [0, 2, 4, 5, 7, 9, 11],
    "ionian":           [0, 2, 4, 5, 7, 9, 11],
    "dorian":           [0, 2, 3, 5, 7, 9, 10],
    "phrygian":         [0, 1, 3, 5, 7, 8, 10],
    "lydian":           [0, 2, 4, 6, 7, 9, 11],
    "mixolydian":       [0, 2, 4, 5, 7, 9, 10],
    "aeolian":          [0, 2, 3, 5, 7, 8, 10],
    "minor":            [0, 2, 3, 5, 7, 8, 10],
    "natural_minor":    [0, 2, 3, 5, 7, 8, 10],
    "locrian":          [0, 1, 3, 5, 6, 8, 10],
    "harmonic_minor":   [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor":    [0, 2, 3, 5, 7, 9, 11],
    "major_pentatonic": [0, 2, 4, 7, 9],
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "blues":            [0, 3, 5, 6, 7, 10],
    "whole_tone":       [0, 2, 4, 6, 8, 10],
    "phrygian_dominant": [0, 1, 4, 5, 7, 8, 10],
    "lydian_dominant":  [0, 2, 4, 6, 7, 9, 10],
    "altered":          [0, 1, 3, 4, 6, 8, 10],
    "diminished_hw":    [0, 1, 3, 4, 6, 7, 9, 10],
    "diminished_wh":    [0, 2, 3, 5, 6, 8, 9, 11],
}

# 다이어토닉 7화음 (major / natural minor / harmonic minor)
DIATONIC_SEVENTHS = {
    "major":          [("major", "maj"), ("minor", "dom"), ("minor", "dom"), ("major", "maj"),
                       ("major", "dom"), ("minor", "dom"), ("dim", "dom")],
    "minor":          [("minor", "dom"), ("dim", "dom"), ("major", "maj"), ("minor", "dom"),
                       ("minor", "dom"), ("major", "maj"), ("major", "dom")],
    "harmonic_minor": [("minor", "maj"), ("dim", "dom"), ("aug", "maj"), ("minor", "dom"),
                       ("major", "dom"), ("major", "maj"), ("dim", "dim6")],
}

DIATONIC_TRIADS = {
    "major":          ["major", "minor", "minor", "major", "major", "minor", "dim"],
    "minor":          ["minor", "dim", "major", "minor", "minor", "major", "major"],
    "harmonic_minor": ["minor", "dim", "aug", "minor", "major", "major", "dim"],
}

_ROMAN_VALUES = [("VII", 7), ("VI", 6), ("IV", 4), ("V", 5), ("III", 3), ("II", 2), ("I", 1)]

_KEY_RE = re.compile(
    r"^\s*([A-Ga-g])([#b♯♭]*)\s*"
    r"(maj(?:or)?|min(?:or)?|m|dor(?:ian)?|phr(?:ygian)?|lyd(?:ian)?|"
    r"mixo(?:lydian)?|aeo(?:lian)?|loc(?:rian)?|harm(?:onic)?[ _]?min(?:or)?|"
    r"mel(?:odic)?[ _]?min(?:or)?)?\s*$",
    re.IGNORECASE,
)

_MODE_ALIASES = {
    None: "major", "": "major",
    "maj": "major", "major": "major",
    "m": "minor", "min": "minor", "minor": "minor",
    "dor": "dorian", "dorian": "dorian",
    "phr": "phrygian", "phrygian": "phrygian",
    "lyd": "lydian", "lydian": "lydian",
    "mixo": "mixolydian", "mixolydian": "mixolydian",
    "aeo": "aeolian", "aeolian": "aeolian",
    "loc": "locrian", "locrian": "locrian",
}


class KeyError_(ValueError):
    """조성 문자열을 해석할 수 없을 때."""


@dataclass
class Key:
    """조성. ``tonic`` 은 피치 클래스, ``mode`` 는 :data:`SCALES` 의 키."""

    tonic: int
    mode: str = "major"
    name: str = "C"

    @property
    def scale(self) -> List[int]:
        return [(self.tonic + iv) % 12 for iv in SCALES[self.mode]]

    @property
    def prefers_flats(self) -> bool:
        """조표에 플랫이 많은 조성인지 (표기 선택용)."""
        # 5도권에서 F, Bb, Eb, Ab, Db, Gb 계열은 플랫 표기
        flat_majors = {5, 10, 3, 8, 1, 6}
        rel_major = self.tonic if self.mode in ("major", "ionian", "lydian") else (self.tonic + 3) % 12
        return rel_major in flat_majors

    @property
    def harmony_mode(self) -> str:
        """다이어토닉 화음 표를 고를 때 쓰는 major/minor 축약."""
        if self.mode in ("harmonic_minor",):
            return "harmonic_minor"
        if self.mode in ("minor", "natural_minor", "aeolian", "phrygian", "dorian", "locrian",
                         "melodic_minor"):
            return "minor"
        return "major"

    def degree_pc(self, degree: int, accidental: int = 0) -> int:
        """1..7 도수 -> 피치 클래스.

        ``accidental`` 이 붙은 경우(bVII, #iv 등)에는 **평행 장조** 를 기준으로
        계산합니다. 대중음악 표기에서 단조의 ``bVII`` 는 자연단음계의 VII 을
        다시 내린 음이 아니라 장음계 VII 을 내린 음(= 자연단음계의 VII)을
        뜻하기 때문입니다.
        """
        if accidental:
            scale = SCALES["major"]
        else:
            scale = SCALES[self.mode] if self.mode in SCALES else SCALES["major"]
            if len(scale) != 7:
                scale = SCALES["major"] if self.harmony_mode == "major" else SCALES["minor"]
        return (self.tonic + scale[(degree - 1) % 7] + accidental) % 12


def parse_key(text: str) -> Key:
    """``"C"``, ``"Am"``, ``"F# minor"``, ``"Bb dorian"`` 같은 문자열 -> :class:`Key`."""
    if isinstance(text, Key):
        return text
    m = _KEY_RE.match(str(text))
    if not m:
        raise KeyError_(f"조성을 해석할 수 없습니다: {text!r}")
    letter, acc, mode_raw = m.groups()
    tonic = (_PC_OF_LETTER[letter.upper()] + accidental_offset(acc)) % 12
    key_lower = (mode_raw or "").lower().replace(" ", "").replace("_", "")
    if key_lower.startswith("harm"):
        mode = "harmonic_minor"
    elif key_lower.startswith("mel"):
        mode = "melodic_minor"
    else:
        mode = _MODE_ALIASES.get(mode_raw.lower() if mode_raw else None, None)
        if mode is None:
            mode = _MODE_ALIASES.get(key_lower, "major")
    # 소문자 음이름만 쓴 경우(예: "am") 마이너로 간주하지는 않습니다 — 명시적 표기를 요구.
    return Key(tonic=tonic, mode=mode, name=str(text).strip())


def scale_pitch_classes(key: Key, scale_name: Optional[str] = None) -> List[int]:
    name = scale_name or key.mode
    if name not in SCALES:
        raise KeyError_(f"모르는 스케일입니다: {name!r}")
    return [(key.tonic + iv) % 12 for iv in SCALES[name]]


def parse_roman(numeral: str, key: Key) -> Chord:
    """로마숫자 표기를 실제 코드로 변환.

    지원: ``I ii V7 vi IV bVII #iv° V/V ii/IV IVmaj7 V7sus4 iiø7`` 등.
    """
    text = numeral.strip()
    if not text:
        raise KeyError_("빈 로마숫자입니다")

    # 세컨더리 도미넌트: "V/V", "V7/ii"
    secondary_target: Optional[str] = None
    if "/" in text:
        head, _, tail = text.partition("/")
        if re.match(r"^[b#]*[ivIV]+", tail):
            secondary_target, text = tail.strip(), head.strip()

    m = re.match(r"^([b#]*)([ivIV]+)(.*)$", text)
    if not m:
        raise KeyError_(f"로마숫자를 해석할 수 없습니다: {numeral!r}")
    acc_str, roman, suffix = m.groups()
    accidental = accidental_offset(acc_str.replace("#", "#").replace("b", "b")) if acc_str else 0

    upper = roman.upper()
    degree = None
    for token, value in _ROMAN_VALUES:
        if upper == token:
            degree = value
            break
    if degree is None:
        raise KeyError_(f"로마숫자를 해석할 수 없습니다: {numeral!r}")

    is_upper = roman[0].isupper()

    base_key = key
    if secondary_target:
        target = parse_roman(secondary_target, key)
        base_key = Key(tonic=target.root,
                       mode="major" if not target.is_minor else "minor",
                       name=pitch_class_name(target.root))

    root_pc = base_key.degree_pc(degree, accidental)
    # bIII/bVI 는 플랫으로, #iv 는 샤프로 적는 것이 자연스럽습니다.
    if accidental < 0:
        use_flats = True
    elif accidental > 0:
        use_flats = False
    else:
        use_flats = key.prefers_flats

    # 접미사 정규화
    suffix = (suffix.replace("ø7", "m7b5").replace("ø", "m7b5")
                    .replace("°", "dim").replace("º", "dim"))

    if suffix:
        symbol = pitch_class_name(root_pc, use_flats)
        if not is_upper and not re.match(r"(?i)^(m|dim|sus|aug|\+|-)", suffix):
            symbol += "m"
        return parse_chord(symbol + suffix)

    quality = DIATONIC_TRIADS[base_key.harmony_mode][(degree - 1) % 7]
    if accidental or secondary_target:
        quality = "major" if is_upper else "minor"
    elif is_upper and quality in ("minor", "dim"):
        quality = "major"
    elif not is_upper and quality in ("major", "aug"):
        quality = "minor"
    return parse_chord(chord_to_symbol(root_pc, quality, None, use_flats))


def diatonic_chords(key: Key, sevenths: bool = True) -> List[Chord]:
    """조성의 다이어토닉 7화음(또는 3화음) 7개."""
    table = DIATONIC_SEVENTHS if sevenths else DIATONIC_TRIADS
    mode = key.harmony_mode
    out: List[Chord] = []
    for i in range(7):
        root = key.degree_pc(i + 1)
        if sevenths:
            quality, seventh = table[mode][i]
        else:
            quality, seventh = table[mode][i], None
        out.append(parse_chord(chord_to_symbol(root, quality, seventh, key.prefers_flats)))
    return out


def roman_of(chord: Chord, key: Key) -> str:
    """코드가 조성 안에서 몇 도인지 로마숫자로 표시 (분석/표시용)."""
    numerals = ["I", "II", "III", "IV", "V", "VI", "VII"]
    major = SCALES["major"]
    interval = (chord.root - key.tonic) % 12
    if interval in major:
        base, prefix = numerals[major.index(interval)], ""
    else:
        base, prefix = numerals[major.index(interval + 1)], "b"
    tq = chord.triad_quality
    if tq in ("minor", "dim"):
        base = base.lower()
    suffix = ""
    if tq == "dim":
        if chord.seventh == "dim6":
            suffix = "°7"
        elif chord.has_seventh:
            suffix = "ø7"
        else:
            suffix = "°"
    elif tq == "aug":
        suffix = "+"
    elif chord.seventh == "maj":
        suffix = "maj7"
    elif chord.has_seventh:
        suffix = "7"
    if chord.bass is not None and chord.bass != chord.root:
        suffix += "/" + pitch_class_name(chord.bass, key.prefers_flats)
    return f"{prefix}{base}{suffix}"


# --------------------------------------------------------------------------- #
# 코드 입력 — 심볼과 도수를 함께 받습니다
# --------------------------------------------------------------------------- #

#: ``C; I-V-ii`` 처럼 앞에 조성을 붙이는 표기
_KEY_PREFIX_RE = re.compile(r"^\s*([^;:]{1,24})\s*[;:]\s*(.+)$", re.S)

#: 로마숫자로 보이는 토큰. 음이름은 A~G 라 i/v 와 겹치지 않습니다.
_ROMAN_TOKEN_RE = re.compile(r"^[b#♭♯]*[ivIV]+")


def is_roman_token(token: str) -> bool:
    """이 토큰이 도수 표기(로마숫자)인지."""
    return bool(_ROMAN_TOKEN_RE.match(str(token).strip()))


def split_key_prefix(text: str) -> Tuple[Optional[Key], str]:
    """``"C; I-V-ii"`` -> (Key(C), ``"I-V-ii"``). 접두사가 없으면 (None, 원문)."""
    m = _KEY_PREFIX_RE.match(str(text))
    if not m:
        return None, str(text)
    head, rest = m.group(1).strip(), m.group(2).strip()
    try:
        return parse_key(head), rest
    except KeyError_:
        return None, str(text)          # 조성이 아니면 접두사로 보지 않습니다


def _tokenize(text: str) -> List[str]:
    """구분자로 나눕니다.

    ``-`` 는 ``I-V-ii`` 의 구분자이기도 하고 ``C-7``(=Cm7)의 일부이기도 합니다.
    그래서 ``-`` 로 나눈 결과가 **전부 로마숫자일 때만** 구분자로 취급합니다.
    """
    body = str(text).strip()
    dashed = [t for t in re.split(r"[-|,\s]+", body) if t]
    if dashed and all(is_roman_token(t) or t == "%" for t in dashed):
        return dashed
    return [t for t in re.split(r"[|,\s]+", body) if t]


def parse_chords(
    text: Union[str, Sequence[str]],
    key: Optional[Union[str, Key]] = None,
) -> Tuple[List[Chord], Optional[Key], bool]:
    """코드 심볼과 도수 표기를 함께 받아 파싱합니다.

    받는 형태::

        "Cmaj7 | Am7 | Dm7 | G7"     코드 심볼
        "C; I-V-ii"                  조성 접두사 + 도수
        "I V vi IV"                  도수 (key 인자 필요)
        "Am; i-bVI-bVII"             단조
        "I V Am7 IV"                 섞어 쓰기

    Returns:
        (코드 목록, 사용한 조성, 도수 표기를 썼는지)
    """
    if isinstance(text, (list, tuple)):
        body = " ".join(str(t) for t in text)
    else:
        body = str(text)

    prefix_key, body = split_key_prefix(body)
    resolved: Optional[Key] = prefix_key
    if resolved is None and key is not None:
        resolved = key if isinstance(key, Key) else parse_key(key)

    tokens = _tokenize(body)
    if not tokens:
        raise ChordError("코드를 하나도 찾지 못했습니다")

    used_roman = any(is_roman_token(t) for t in tokens)
    if used_roman and resolved is None:
        raise ChordError(
            "도수(로마숫자)로 입력하려면 조성이 필요합니다. "
            "key 를 지정하거나 'C; I-V-ii' 처럼 앞에 조성을 붙여 주세요."
        )

    chords: List[Chord] = []
    for token in tokens:
        if token in ("%", "-"):
            if not chords:
                raise ChordError("반복 기호(%) 앞에 코드가 없습니다")
            chords.append(chords[-1])
        elif is_roman_token(token):
            chords.append(parse_roman(token, resolved))
        else:
            chords.append(parse_chord(token))
    return chords, resolved, used_roman
