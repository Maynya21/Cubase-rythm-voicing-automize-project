"""코드 진행 템플릿, 생성, 리하모나이제이션."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .chords import Chord, chord_to_symbol, parse_chord
from .notes import pitch_class_name
from .scales import Key, parse_key, parse_roman, roman_of


@dataclass
class ProgressionTemplate:
    name: str
    korean: str
    description: str
    romans: List[str]
    genres: List[str] = field(default_factory=list)
    prefers_minor: bool = False


_T = ProgressionTemplate

TEMPLATES: Dict[str, ProgressionTemplate] = {t.name: t for t in [
    # ---- 팝 ---------------------------------------------------------------
    _T("axis", "액시스(만능 진행)", "I-V-vi-IV. 현대 팝에서 가장 많이 쓰이는 진행",
       ["I", "V", "vi", "IV"], ["pop", "kpop", "rock", "edm"]),
    _T("axis_vi", "vi 시작 액시스", "vi-IV-I-V. 같은 진행을 6도부터 시작해 서정적",
       ["vi", "IV", "I", "V"], ["pop", "kpop", "ballad"]),
    _T("doowop", "두왑 (50s)", "I-vi-IV-V. 복고풍의 따뜻한 진행",
       ["I", "vi", "IV", "V"], ["pop", "ballad", "rock"]),
    _T("canon", "캐논 진행", "I-V-vi-iii-IV-I-IV-V. 파헬벨 캐논의 8마디",
       ["I", "V", "vi", "iii", "IV", "I", "IV", "V"], ["pop", "kpop", "ballad", "classical"]),
    _T("pop_punk", "팝펑크", "I-V-vi-IV 를 IV 로 밀어 시작",
       ["IV", "I", "V", "vi"], ["pop", "rock"]),
    _T("emotional", "감성 진행", "IV-V-iii-vi. K-발라드/시티팝의 단골",
       ["IVmaj7", "V7", "iii7", "vi7"], ["kpop", "citypop", "ballad"]),
    _T("just_two", "투코드", "I-V 반복. 훅 중심 곡의 단순한 뼈대",
       ["I", "V"], ["pop", "edm"]),

    # ---- 발라드 / 시티팝 ---------------------------------------------------
    _T("citypop", "시티팝", "IVmaj7-iii7-vi7-I7. 세련된 4도 시작",
       ["IVmaj7", "iii7", "vi7", "I7"], ["citypop", "jazz", "kpop"]),
    _T("citypop_ii", "시티팝 ii-V", "ii7-V7-Imaj7-vi7 순환",
       ["ii7", "V7", "Imaj7", "vi7"], ["citypop", "jazz", "lofi"]),
    _T("ballad_desc", "하행 발라드", "I-V/vii-vi-I/v-IV. 베이스가 순차 하행",
       ["I", "V", "vi", "I", "IV", "I", "ii", "V"], ["ballad", "kpop"]),
    _T("sad_pop", "슬픈 팝", "vi-V-IV-V. 해결되지 않고 맴도는 느낌",
       ["vi", "V", "IV", "V"], ["pop", "ballad", "kpop"]),

    # ---- 마이너 ------------------------------------------------------------
    _T("andalusian", "안달루시안", "i-bVII-bVI-V. 플라멩코/락의 하행 진행",
       ["i", "bVII", "bVI", "V"], ["rock", "latin", "cinematic"], prefers_minor=True),
    _T("minor_axis", "마이너 액시스", "i-bVI-bIII-bVII. 어둡고 웅장한 팝",
       ["i", "bVI", "bIII", "bVII"], ["pop", "rock", "edm", "cinematic"], prefers_minor=True),
    _T("minor_loop", "마이너 순환", "i-iv-bVII-bIII",
       ["i", "iv", "bVII", "bIII"], ["pop", "rnb", "lofi"], prefers_minor=True),
    _T("harmonic_minor", "화성단조", "i-iv-V7-i. 클래식한 단조 종지",
       ["i", "iv", "V7", "i"], ["classical", "cinematic", "rock"], prefers_minor=True),

    # ---- 재즈 --------------------------------------------------------------
    _T("ii_v_i", "투파이브원", "ii7-V7-Imaj7. 재즈 화성의 기본 단위",
       ["ii7", "V7", "Imaj7", "Imaj7"], ["jazz", "bossa", "lofi"]),
    _T("minor_ii_v_i", "마이너 투파이브원", "iiø7-V7-i. 단조 재즈의 기본 단위",
       ["iiø7", "V7", "i7", "i7"], ["jazz", "bossa"], prefers_minor=True),
    _T("turnaround", "턴어라운드", "Imaj7-vi7-ii7-V7. 마디 끝을 되돌리는 진행",
       ["Imaj7", "vi7", "ii7", "V7"], ["jazz", "citypop", "lofi"]),
    _T("rhythm_changes", "리듬 체인지 A", "I-vi-ii-V 를 두 배로 촘촘히",
       ["Imaj7", "vi7", "ii7", "V7", "iii7", "VI7", "ii7", "V7"], ["jazz"]),
    _T("coltrane_lite", "3도 이동", "Imaj7-bIII7-bVImaj7-V7. 자이언트 스텝스 느낌",
       ["Imaj7", "bIII7", "bVImaj7", "V7"], ["jazz"]),
    _T("blues12", "12마디 블루스", "정통 12마디 블루스",
       ["I7", "IV7", "I7", "I7", "IV7", "IV7", "I7", "I7", "V7", "IV7", "I7", "V7"],
       ["blues", "rock", "jazz"]),
    _T("jazz_blues", "재즈 블루스", "ii-V 가 들어간 12마디 블루스",
       ["I7", "IV7", "I7", "v7", "IV7", "#iv°", "I7", "VI7", "ii7", "V7", "I7", "V7"],
       ["jazz", "blues"]),
    _T("bossa", "보사노바", "Imaj7-ii7-V7 순환에 iv 를 섞음",
       ["Imaj7", "ii7", "V7", "Imaj7", "iv7", "bVII7", "Imaj7", "V7"], ["bossa", "jazz"]),

    # ---- R&B / 가스펠 -------------------------------------------------------
    _T("neosoul", "네오소울", "Imaj7-iii7-vi7-ii7. 부드럽게 4도씩 내려감",
       ["Imaj7", "iii7", "vi7", "ii7"], ["rnb", "neosoul", "lofi"]),
    _T("gospel", "가스펠", "I-I7/III-IV-#iv°-I/V-VI7-ii7-V7",
       ["I", "I7", "IV", "#iv°", "I", "VI7", "ii7", "V7"], ["gospel", "rnb"]),
    _T("rnb_loop", "R&B 루프", "ii7-V7 을 두 마디씩 늘려 잡은 그루브",
       ["ii7", "ii7", "V7", "V7"], ["rnb", "lofi", "neosoul"]),

    # ---- 락 ----------------------------------------------------------------
    _T("mixolydian", "믹솔리디안 락", "I-bVII-IV-I. 클래식 락의 기본",
       ["I", "bVII", "IV", "I"], ["rock"]),
    _T("power_pop", "파워팝", "I-IV-V-IV",
       ["I", "IV", "V", "IV"], ["rock", "pop"]),
]}

#: 장르 -> 어울리는 템플릿 이름 목록
GENRE_INDEX: Dict[str, List[str]] = {}
for _t in TEMPLATES.values():
    for _g in _t.genres:
        GENRE_INDEX.setdefault(_g, []).append(_t.name)


def list_progression_templates(genre: Optional[str] = None) -> List[Dict[str, object]]:
    out = []
    for t in TEMPLATES.values():
        if genre and genre.lower() not in t.genres:
            continue
        out.append({
            "name": t.name,
            "korean": t.korean,
            "description": t.description,
            "romans": t.romans,
            "bars": len(t.romans),
            "genres": t.genres,
            "minor_key": t.prefers_minor,
        })
    return out


def list_genres() -> List[str]:
    return sorted(GENRE_INDEX)


@dataclass
class Progression:
    chords: List[Chord]
    romans: List[str]
    key: Key
    template: Optional[str] = None
    #: 조성이 템플릿의 장/단조와 달라 변환한 경우 그 설명
    adapted_note: Optional[str] = None

    @property
    def symbols(self) -> List[str]:
        return [c.symbol for c in self.chords]

    def describe(self) -> str:
        return " | ".join(f"{s}" for s in self.symbols)


def from_template(
    template: str,
    key: str | Key,
    bars: Optional[int] = None,
    adapt: str = "relative",
) -> Progression:
    """템플릿 이름과 조성으로 진행을 만듭니다.

    템플릿은 장조용/단조용 로마숫자로 쓰여 있습니다. 사용자가 준 조성이
    템플릿과 반대 모드면 ``adapt`` 방식으로 맞춥니다.

    * ``"relative"`` (기본) — 나란한조로 해석. ``axis`` + ``Am`` -> ``C G Am F``.
      코드가 모두 원래 조성의 다이어토닉 안에 남습니다.
    * ``"parallel"`` — 같은 으뜸음조로 해석. ``axis`` + ``Am`` -> ``Am E Fm D`` 같은
      직역이 아니라, 템플릿 모드를 그대로 두고 으뜸음만 맞춥니다.
    * ``"none"`` — 변환 없이 준 조성에 그대로 대입.
    """
    if template not in TEMPLATES:
        raise ValueError(
            f"모르는 진행 템플릿입니다: {template!r} "
            f"(사용 가능: {', '.join(sorted(TEMPLATES))})"
        )
    t = TEMPLATES[template]
    k = parse_key(key) if not isinstance(key, Key) else key

    interp = k
    note = None
    key_is_minor = k.harmony_mode != "major"
    if adapt != "none" and key_is_minor != t.prefers_minor:
        if adapt == "relative":
            # 장조 템플릿 + 단조 키 -> 나란한장조에서 해석 (그 반대도 동일)
            shift = 3 if key_is_minor else 9
            interp = Key(tonic=(k.tonic + shift) % 12,
                         mode="major" if t.prefers_minor is False else "minor",
                         name=pitch_class_name((k.tonic + shift) % 12, k.prefers_flats))
            note = (f"'{t.korean}' 템플릿은 "
                    f"{'단조' if t.prefers_minor else '장조'}용이라 "
                    f"나란한조({interp.name}{'m' if t.prefers_minor else ''}) 기준으로 해석했습니다.")
        elif adapt == "parallel":
            interp = Key(tonic=k.tonic,
                         mode="minor" if t.prefers_minor else "major",
                         name=k.name)
            note = (f"'{t.korean}' 템플릿을 같은 으뜸음의 "
                    f"{'단조' if t.prefers_minor else '장조'}로 해석했습니다.")
        else:
            raise ValueError(f"adapt 는 relative/parallel/none 중 하나여야 합니다: {adapt!r}")

    romans = list(t.romans)
    if bars:
        if bars <= len(romans):
            romans = romans[:bars]
        else:
            romans = [romans[i % len(romans)] for i in range(bars)]
    chords = [parse_roman(r, interp) for r in romans]
    return Progression(chords=chords, romans=romans, key=k, template=template,
                       adapted_note=note)


def generate(
    key: str | Key = "C",
    genre: str = "pop",
    bars: int = 4,
    template: Optional[str] = None,
    seed: Optional[int] = None,
    adapt: str = "relative",
) -> Progression:
    """장르에 맞는 진행을 고르거나 만듭니다."""
    k = parse_key(key) if not isinstance(key, Key) else key
    rng = random.Random(seed)
    if template:
        return from_template(template, k, bars, adapt=adapt)
    candidates = GENRE_INDEX.get(genre.lower())
    if not candidates:
        raise ValueError(
            f"모르는 장르입니다: {genre!r} (사용 가능: {', '.join(list_genres())})"
        )
    # 조성의 장/단조에 맞는 템플릿을 우선
    minor = k.harmony_mode != "major"
    preferred = [n for n in candidates if TEMPLATES[n].prefers_minor == minor]
    pool = preferred or candidates
    return from_template(rng.choice(pool), k, bars, adapt=adapt)


# --------------------------------------------------------------------------- #
# 리하모나이제이션
# --------------------------------------------------------------------------- #

REHARM_MOVES = {
    "sevenths": "모든 3화음에 7음을 더해 재즈풍으로",
    "tensions": "9th/13th 를 더해 색채를 넓힘",
    "tritone": "도미넌트를 트라이톤 대리코드로 치환 (G7 -> Db7)",
    "secondary": "다음 코드로 향하는 세컨더리 도미넌트를 삽입",
    "relative": "일부 코드를 나란한조 대리코드로 치환 (I <-> vi)",
    "passing_dim": "온음으로 움직이는 자리에 경과 감7화음 삽입",
    "modal": "동주단조 차용 (IV -> iv, bVI, bVII)",
    "sus": "도미넌트를 sus4 로 지연 해결",
}


def reharmonize(
    chords: Sequence[Chord],
    key: str | Key = "C",
    moves: Sequence[str] = ("sevenths",),
    strength: float = 0.6,
    seed: Optional[int] = None,
) -> List[Chord]:
    """진행에 리하모나이제이션 기법을 적용합니다.

    ``strength`` 는 0~1 사이의 적용 확률입니다. 마디 수를 늘리는 기법
    (secondary, passing_dim)은 코드를 삽입하므로 길이가 달라질 수 있습니다.
    """
    k = parse_key(key) if not isinstance(key, Key) else key
    rng = random.Random(seed)
    flats = k.prefers_flats
    unknown = [m for m in moves if m not in REHARM_MOVES]
    if unknown:
        raise ValueError(
            f"모르는 리하모나이제이션 기법입니다: {unknown} "
            f"(사용 가능: {', '.join(REHARM_MOVES)})"
        )
    out = list(chords)

    if "sevenths" in moves:
        out = [_add_seventh(c, k, flats) if rng.random() < strength else c for c in out]
    if "tensions" in moves:
        out = [_add_tension(c, flats) if rng.random() < strength else c for c in out]
    if "modal" in moves:
        out = [_modal_swap(c, k, flats, rng) if rng.random() < strength * 0.6 else c for c in out]
    if "relative" in moves:
        out = [_relative_swap(c, k, flats, rng) if rng.random() < strength * 0.5 else c for c in out]
    if "tritone" in moves:
        out = [_tritone_sub(c, flats) if (_is_dominant(c) and rng.random() < strength) else c
               for c in out]
    if "sus" in moves:
        out = [_sus_swap(c, flats) if (_is_dominant(c) and rng.random() < strength * 0.5) else c
               for c in out]
    if "secondary" in moves:
        out = _insert_secondary(out, flats, rng, strength)
    if "passing_dim" in moves:
        out = _insert_passing_dim(out, flats, rng, strength)
    return out


def _is_dominant(c: Chord) -> bool:
    return c.seventh == "dom" and c.triad_quality in ("major", "sus4")


def _add_seventh(c: Chord, key: Key, flats: bool) -> Chord:
    if c.has_seventh or c.triad_quality in ("sus2", "sus4"):
        return c
    tq = c.triad_quality
    scale = [key.degree_pc(i + 1) for i in range(7)]
    if tq == "dim":
        return parse_chord(pitch_class_name(c.root, flats) + "m7b5")
    if tq == "aug":
        return c
    # 조성 안에 단7도가 있으면 도미넌트/m7, 아니면 장7도
    if tq == "minor":
        seventh = "dom"                       # chord_to_symbol 규약상 m7
    elif (c.root + 10) % 12 in scale:
        seventh = "dom"
    else:
        seventh = "maj"
    return parse_chord(chord_to_symbol(c.root, tq, seventh, flats))


def _add_tension(c: Chord, flats: bool) -> Chord:
    name = pitch_class_name(c.root, flats)
    tq = c.triad_quality
    if _is_dominant(c):
        return parse_chord(name + "13")
    if tq == "major" and c.seventh == "maj":
        return parse_chord(name + "maj9")
    if tq == "minor" and c.has_seventh:
        return parse_chord(name + "m9")
    if tq == "major" and not c.has_seventh:
        return parse_chord(name + "add9")
    if tq == "minor" and not c.has_seventh:
        return parse_chord(name + "m9")
    return c


def _tritone_sub(c: Chord, flats: bool) -> Chord:
    # 트라이톤 대리코드는 관습적으로 플랫으로 적습니다 (G7 -> Db7).
    return parse_chord(pitch_class_name((c.root + 6) % 12, True) + "7#11")


def _sus_swap(c: Chord, flats: bool) -> Chord:
    return parse_chord(pitch_class_name(c.root, flats) + "7sus4")


def _relative_swap(c: Chord, key: Key, flats: bool, rng: random.Random) -> Chord:
    """I <-> vi, IV <-> ii 같은 나란한조 대리."""
    tq = c.triad_quality
    if tq == "major":
        new_root = (c.root + 9) % 12
        return parse_chord(pitch_class_name(new_root, flats) + "m7")
    if tq == "minor":
        new_root = (c.root + 3) % 12
        return parse_chord(pitch_class_name(new_root, flats) + "maj7")
    return c


def _modal_swap(c: Chord, key: Key, flats: bool, rng: random.Random) -> Chord:
    """동주단조 차용: IV -> iv, V -> bVII, I -> bIII 등."""
    degree = (c.root - key.tonic) % 12
    if degree == 5 and c.triad_quality == "major":       # IV -> iv
        return parse_chord(pitch_class_name(c.root, flats) + "m7")
    if degree == 7 and c.triad_quality == "major":       # V -> bVII
        return parse_chord(pitch_class_name((key.tonic + 10) % 12, True))
    if degree == 9 and c.triad_quality == "minor":       # vi -> bVI
        return parse_chord(pitch_class_name((key.tonic + 8) % 12, True) + "maj7")
    return c


def _insert_secondary(chords: List[Chord], flats: bool, rng: random.Random,
                      strength: float) -> List[Chord]:
    """각 코드 앞에 그 코드로 향하는 V7 을 끼워 넣습니다."""
    out: List[Chord] = []
    for i, c in enumerate(chords):
        if i > 0 and rng.random() < strength * 0.5 and c.triad_quality in ("major", "minor"):
            dom_root = (c.root + 7) % 12
            if dom_root != chords[i - 1].root:
                out.append(parse_chord(pitch_class_name(dom_root, flats) + "7"))
        out.append(c)
    return out


def _insert_passing_dim(chords: List[Chord], flats: bool, rng: random.Random,
                        strength: float) -> List[Chord]:
    """온음으로 상행하는 두 코드 사이에 경과 감7화음을 삽입."""
    out: List[Chord] = []
    for i, c in enumerate(chords):
        out.append(c)
        if i + 1 < len(chords):
            step = (chords[i + 1].root - c.root) % 12
            if step == 2 and rng.random() < strength:
                out.append(parse_chord(pitch_class_name((c.root + 1) % 12, False) + "dim7"))
    return out


def analyze(chords: Sequence[Chord], key: str | Key = "C") -> List[Dict[str, object]]:
    """진행을 조성 안에서 분석해 로마숫자/구성음을 돌려줍니다."""
    k = parse_key(key) if not isinstance(key, Key) else key
    flats = k.prefers_flats
    return [
        {
            "symbol": c.symbol,
            "roman": roman_of(c, k),
            "root": pitch_class_name(c.root, flats),
            "quality": c.triad_quality,
            "notes": c.note_names(flats),
            "intervals": c.intervals,
            "bass": pitch_class_name(c.bass, flats) if c.bass is not None else None,
        }
        for c in chords
    ]
