"""코드 심볼 파서 / 코드 정의.

``Cmaj7``, ``F#m7b5``, ``Bb13(#11)``, ``G7sus4``, ``Am/C`` 같은
실제 리드시트 표기를 파싱해서 근음 기준 반음 간격 목록으로 바꿉니다.

간격(interval)은 12를 넘는 값을 그대로 유지합니다.
9=14, 11=17, 13=21 처럼 텐션의 원래 높이를 보존해야
보이싱 단계에서 자연스러운 음역 배치를 할 수 있기 때문입니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

from .notes import accidental_offset, pitch_class_name

#: 3화음 기본형
TRIADS = {
    "major": [0, 4, 7],
    "minor": [0, 3, 7],
    "dim": [0, 3, 6],
    "aug": [0, 4, 8],
    "sus2": [0, 2, 7],
    "sus4": [0, 5, 7],
}

#: 텐션 번호 -> 기본 반음 간격
TENSION_SEMITONES = {2: 2, 4: 5, 6: 9, 9: 14, 11: 17, 13: 21}

_LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

_ROOT_RE = re.compile(r"^([A-Ga-g])([#b♯♭x]*)")

# 심볼 표기 정규화 (긴 것부터 치환)
_NORMALIZE = [
    ("Δ", "maj7"),
    ("^", "maj7"),
    ("ø7", "m7b5"),
    ("ø", "m7b5"),
    ("°7", "dim7"),
    ("º7", "dim7"),
    ("°", "dim"),
    ("º", "dim"),
    ("♯", "#"),
    ("♭", "b"),
    ("–", "-"),
    ("—", "-"),
]


class ChordError(ValueError):
    """코드 심볼을 해석할 수 없을 때."""


@dataclass
class Chord:
    """파싱된 코드 하나."""

    symbol: str                     # 정규화된 원본 심볼 (예: "Cmaj7")
    root: int                       # 근음 피치 클래스 0..11
    intervals: List[int]            # 근음 기준 반음 간격 (0 포함, 오름차순)
    bass: Optional[int] = None      # 슬래시 베이스 피치 클래스 (없으면 None)
    quality: str = "major"          # major / minor / dim / aug / sus2 / sus4
    seventh: Optional[str] = None   # None / "dom" / "maj" / "dim6"
    tensions: List[str] = field(default_factory=list)  # ["b9", "#11"] 등 표시용

    @property
    def pitch_classes(self) -> List[int]:
        """중복 없는 구성음 피치 클래스 (등장 순서 유지)."""
        seen: List[int] = []
        for iv in self.intervals:
            pc = (self.root + iv) % 12
            if pc not in seen:
                seen.append(pc)
        return seen

    @property
    def bass_pc(self) -> int:
        return self.bass if self.bass is not None else self.root

    @property
    def triad_quality(self) -> str:
        """실제 구성음으로 판정한 3화음 성질.

        ``Cm7b5`` 처럼 파싱 단계에서는 minor 로 시작해 5음이 변화된 코드도
        여기서는 ``dim`` 으로 올바르게 나옵니다.
        """
        third, fifth = self.interval_of(3), self.interval_of(5)
        if third == 3 and fifth == 6:
            return "dim"
        if third == 4 and fifth == 8:
            return "aug"
        if third == 3:
            return "minor"
        if third == 4:
            return "major"
        if third == 5:
            return "sus4"
        if third == 2:
            return "sus2"
        return self.quality

    @property
    def is_minor(self) -> bool:
        return self.triad_quality == "minor"

    @property
    def has_seventh(self) -> bool:
        return any(9 <= iv <= 11 for iv in self.intervals)

    def note_names(self, flats: bool = False) -> List[str]:
        return [pitch_class_name(pc, flats) for pc in self.pitch_classes]

    def interval_of(self, degree: int) -> Optional[int]:
        """3, 5, 7, 9 같은 도수의 실제 간격을 찾습니다 (없으면 None)."""
        window = {
            1: (0, 0), 3: (2, 5), 5: (6, 8), 7: (9, 11),
            9: (13, 15), 11: (16, 18), 13: (20, 22),
        }.get(degree)
        if window is None:
            return None
        for iv in self.intervals:
            if window[0] <= iv <= window[1]:
                return iv
        return None


def _pc_from_letter(letter: str, acc: str) -> int:
    return (_LETTER_PC[letter.upper()] + accidental_offset(acc)) % 12


def _normalize(symbol: str) -> str:
    s = symbol.strip()
    for a, b in _NORMALIZE:
        s = s.replace(a, b)
    return s


def _flatten_parens(s: str) -> str:
    """``C7(9,13)`` -> ``C7add9add13`` / ``C7(#11)`` -> ``C7#11``.

    괄호 안의 맨숫자 텐션은 add 로 간주합니다.
    """
    def repl(m: re.Match) -> str:
        out = []
        for tok in re.split(r"[,\s]+", m.group(1)):
            tok = tok.strip()
            if not tok:
                continue
            if re.fullmatch(r"(9|11|13|6|2|4)", tok):
                out.append("add" + tok)
            else:
                out.append(tok)
        return "".join(out)

    return re.sub(r"\(([^)]*)\)", repl, s)


def parse_chord(symbol: str) -> Chord:
    """코드 심볼 문자열을 :class:`Chord` 로 파싱."""
    original = _normalize(symbol)
    raw = _flatten_parens(original).replace(" ", "")
    if not raw:
        raise ChordError("빈 코드 심볼입니다")

    # --- 슬래시 베이스 분리 -------------------------------------------------
    bass_pc: Optional[int] = None
    if "/" in raw:
        head, _, tail = raw.rpartition("/")
        tail = tail.strip()
        m_bass = _ROOT_RE.match(tail)
        if head and m_bass and m_bass.end() == len(tail):
            bass_pc = _pc_from_letter(*m_bass.groups())
            raw = head
        # 해석되지 않으면 슬래시를 심볼의 일부로 취급 (예: "C6/9")

    # --- 근음 ---------------------------------------------------------------
    m = _ROOT_RE.match(raw)
    if not m:
        raise ChordError(f"근음을 찾을 수 없습니다: {symbol!r}")
    root = _pc_from_letter(*m.groups())
    s = raw[m.end():]

    # 근음 바로 뒤의 '-' 는 마이너 표기이므로 b9/b13 추출 전에 치환해 둡니다.
    if s.startswith("-"):
        s = "m" + s[1:]

    # --- 부가 토큰 추출 -----------------------------------------------------
    adds: List[int] = []
    omits: List[int] = []
    alters: List[Tuple[int, int]] = []   # (도수, 반음 변화)
    tension_labels: List[str] = []
    state = {"alt": False, "sixnine": False}

    def _consume(pattern: str, handler) -> None:
        nonlocal s
        while True:
            mm = re.search(pattern, s)
            if not mm:
                return
            handler(mm)
            s = s[: mm.start()] + s[mm.end():]

    def _on_add(mm: re.Match) -> None:
        acc = mm.group(1) or ""
        adds.append(TENSION_SEMITONES[int(mm.group(2))] + accidental_offset(acc))

    def _on_alter(mm: re.Match) -> None:
        sign = 1 if mm.group(1) in "#+" else -1
        alters.append((int(mm.group(2)), sign))
        tension_labels.append(("#" if sign > 0 else "b") + mm.group(2))

    if re.search(r"6/9|69", s):
        state["sixnine"] = True
        s = re.sub(r"6/9|69", "", s, count=1)

    _consume(r"(?i)alt(?:ered)?", lambda mm: state.__setitem__("alt", True))
    _consume(r"(?i)add(#|b)?(13|11|9|6|4|2)", _on_add)
    _consume(r"(?i)(?:no|omit)(3|5|1)", lambda mm: omits.append(int(mm.group(1))))

    # --- 기본 성질 ----------------------------------------------------------
    quality = "major"
    seventh: Optional[str] = None

    sus_m = re.search(r"(?i)sus(4|2)?", s)
    if sus_m:
        quality = "sus2" if sus_m.group(1) == "2" else "sus4"
        s = s[: sus_m.start()] + s[sus_m.end():]

    if re.match(r"(?i)^dim", s):
        quality = "dim"
        s = s[3:]
        if s.startswith("7"):
            seventh = "dim6"
            s = s[1:]
    elif re.match(r"(?i)^aug", s):
        quality = "aug"
        s = s[3:]
    elif s.startswith("+"):
        quality = "aug"
        s = s[1:]
    elif re.match(r"^(min|m)(?!aj)", s):
        if quality == "major":
            quality = "minor"
        s = re.sub(r"^(min|m)", "", s, count=1)
        if re.match(r"(?i)^(maj|M)(?=7|9|11|13|$)", s):
            seventh = "maj"
            s = re.sub(r"(?i)^(maj|M)", "", s, count=1)

    if seventh is None and re.match(r"(?i)^maj(?=7|9|11|13|$)", s):
        seventh = "maj"
        s = s[3:]
    if seventh is None and re.match(r"^M(?=7|9|11|13|$)", s):
        seventh = "maj"
        s = s[1:]

    # --- 확장 숫자 ----------------------------------------------------------
    extension = 0
    num_m = re.match(r"^(13|11|9|7|6|5)", s)
    if num_m:
        extension = int(num_m.group(1))
        s = s[num_m.end():]

    # 남은 변화음(#5, b9, #11 ...) 추출
    _consume(r"(#|b|\+)(13|11|9|6|5)", _on_alter)

    # --- 간격 조립 ----------------------------------------------------------
    intervals = list(TRIADS[quality])

    if quality == "dim" and seventh == "dim6":
        intervals.append(9)                     # bb7
    elif extension == 6 or state["sixnine"]:
        intervals.append(9)
    elif extension >= 7 or seventh == "maj":
        if seventh == "maj":
            intervals.append(11)
        else:
            intervals.append(10)
            seventh = "dom" if quality in ("major", "sus4", "sus2", "aug") else seventh

    if extension >= 9 or state["sixnine"]:
        intervals.append(14)

    if extension == 11:
        # 도미넌트/메이저 11th는 3음과 부딪히므로 관습적으로 3음을 생략
        if quality == "major" and 4 in intervals:
            intervals.remove(4)
        intervals.append(17)
    elif extension == 13:
        intervals.append(21)
        if quality == "minor":
            intervals.append(17)                # m13은 11음을 포함하는 게 일반적

    if extension == 5:                          # 파워코드
        intervals = [0, 7]

    if state["alt"]:
        intervals = [0, 4, 10, 13, 15, 20]      # 1 3 b7 b9 #9 b13
        quality, seventh = "major", "dom"
        tension_labels = ["b9", "#9", "#11", "b13"]

    intervals.extend(adds)

    # --- 변화음 적용 --------------------------------------------------------
    for degree, sign in alters:
        base = {5: 7, 9: 14, 11: 17, 13: 21, 6: 9}[degree]
        target = base + sign
        if base in intervals:
            intervals[intervals.index(base)] = target
        elif target not in intervals:
            intervals.append(target)

    for degree in omits:
        drops = {1: (0,), 3: (3, 4), 5: (6, 7, 8)}[degree]
        intervals = [iv for iv in intervals if iv not in drops]

    intervals = sorted(set(intervals))
    if not intervals:
        raise ChordError(f"구성음이 없습니다: {symbol!r}")

    leftover = s.strip()
    if leftover:
        raise ChordError(
            f"코드 심볼을 해석하지 못했습니다: {symbol!r} (남은 문자 {leftover!r})"
        )

    if not tension_labels:
        tension_labels = []

    return Chord(
        symbol=original.strip(),
        root=root,
        intervals=intervals,
        bass=bass_pc,
        quality=quality,
        seventh=seventh,
        tensions=tension_labels,
    )


def parse_progression(text: Union[str, Sequence[str]]) -> List[Chord]:
    """``"Cmaj7 | Am7 | Dm7 | G7"`` 처럼 여러 코드를 한 번에 파싱.

    ``|`` 와 공백, 쉼표를 구분자로 취급하고 ``%`` 는 직전 코드 반복입니다.
    """
    if isinstance(text, (list, tuple)):
        tokens = [str(t).strip() for t in text if str(t).strip()]
    else:
        tokens = [t for t in re.split(r"[|,\s]+", str(text).strip()) if t]
    chords: List[Chord] = []
    for tok in tokens:
        if tok in ("%", "-"):
            if not chords:
                raise ChordError("반복 기호(%) 앞에 코드가 없습니다")
            chords.append(chords[-1])
        else:
            chords.append(parse_chord(tok))
    if not chords:
        raise ChordError("코드를 하나도 찾지 못했습니다")
    return chords


def chord_to_symbol(root_pc: int, quality: str, seventh: Optional[str] = None,
                    flats: bool = False) -> str:
    """간단한 역방향 변환 (진행 생성기에서 사용)."""
    name = pitch_class_name(root_pc, flats)
    suffix = {
        ("major", None): "",
        ("major", "maj"): "maj7",
        ("major", "dom"): "7",
        ("minor", None): "m",
        ("minor", "dom"): "m7",
        ("minor", "maj"): "mMaj7",
        ("dim", None): "dim",
        ("dim", "dom"): "m7b5",
        ("dim", "dim6"): "dim7",
        ("aug", None): "aug",
        ("aug", "maj"): "augMaj7",
        ("aug", "dom"): "7#5",
        ("sus4", None): "sus4",
        ("sus4", "dom"): "7sus4",
        ("sus2", None): "sus2",
    }.get((quality, seventh), "")
    return name + suffix
