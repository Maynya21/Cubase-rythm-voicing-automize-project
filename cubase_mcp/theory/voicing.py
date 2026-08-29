"""보이싱 엔진.

코드 하나(:class:`~cubase_mcp.theory.chords.Chord`)를 실제 음높이 목록으로
바꿉니다. 스타일별로 어떤 음을 쓸지 정하고, 그 다음 **보이스 리딩** 단계에서
앞 코드와의 이동량이 가장 작은 자리바꿈/옥타브를 고릅니다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .chords import Chord

#: 기본 음역 (MIDI). Cubase 표기로 C2 ~ C5.
DEFAULT_LOW = 48
DEFAULT_HIGH = 84
DEFAULT_CENTER = 64

#: 음을 덜어내야 할 때 버리는 순서 (앞에 있을수록 먼저 버림)
_TRIM_PRIORITY = [5, 1, 11, 13, 9, 3, 7]
#: 텐션을 얹은 경우에는 9음이 근음 역할을 대신하므로 근음을 먼저 버립니다.
_TRIM_PRIORITY_TENSION = [1, 5, 11, 13, 9, 3, 7]


@dataclass
class VoicingStyle:
    name: str
    korean: str
    description: str
    tags: List[str] = field(default_factory=list)
    needs_seventh: bool = False
    min_notes: int = 3


VOICING_STYLES: Dict[str, VoicingStyle] = {
    "close": VoicingStyle("close", "클로즈", "구성음을 한 옥타브 안에 촘촘히 쌓는 기본 보이싱", ["기본", "피아노", "패드"]),
    "open": VoicingStyle("open", "오픈", "1-5-3(-7) 순으로 넓게 벌린 보이싱. 통기타/피아노 반주에 잘 맞음", ["기본", "피아노", "기타"]),
    "drop2": VoicingStyle("drop2", "드롭2", "클로즈에서 위에서 두 번째 음을 한 옥타브 내림. 재즈 컴핑 표준", ["재즈", "피아노", "기타"], needs_seventh=True, min_notes=4),
    "drop3": VoicingStyle("drop3", "드롭3", "위에서 세 번째 음을 한 옥타브 내림. 드롭2보다 더 벌어진 소리", ["재즈", "기타"], needs_seventh=True, min_notes=4),
    "drop24": VoicingStyle("drop24", "드롭2&4", "2번째와 4번째 음을 내림. 아주 넓고 오케스트라적인 울림", ["재즈", "빅밴드"], needs_seventh=True, min_notes=4),
    "shell": VoicingStyle("shell", "쉘", "근음 + 3음 + 7음만. 가이드톤 중심의 가볍고 명료한 소리", ["재즈", "왼손"], needs_seventh=True),
    "rootless_a": VoicingStyle("rootless_a", "루트리스 A", "3-5-7-9 (빌 에반스 A형). 베이스가 근음을 칠 때 사용", ["재즈", "피아노"], needs_seventh=True, min_notes=4),
    "rootless_b": VoicingStyle("rootless_b", "루트리스 B", "7-9-3-13 (빌 에반스 B형). A형보다 한 옥타브 위 배치", ["재즈", "피아노"], needs_seventh=True, min_notes=4),
    "quartal": VoicingStyle("quartal", "쿼탈", "4도 쌓기. 모달/네오소울/시티팝의 현대적인 울림", ["모던", "시티팝", "네오소울"]),
    "triad": VoicingStyle("triad", "트라이어드", "3화음만 사용. 텐션 없이 단순하고 밝게", ["팝", "락", "기본"]),
    "power": VoicingStyle("power", "파워코드", "근음-5도-옥타브. 락/메탈 기타", ["락", "메탈", "기타"]),
    "pad": VoicingStyle("pad", "패드", "낮은 근음+5도 위에 상성 화음을 얹은 넓은 지속음", ["패드", "신스", "발라드"]),
    "guitar": VoicingStyle("guitar", "기타", "기타 코드폼에 가까운 배치 (근음-5도-옥타브-3음-7음)", ["기타", "팝", "락"]),
    "piano": VoicingStyle("piano", "피아노 양손", "왼손 근음/5도 + 오른손 클로즈. 실제 피아노 반주 배치", ["피아노", "발라드", "팝"]),
    "block": VoicingStyle("block", "블록(4-way close)", "맨 위 선율을 한 옥타브 아래에 겹쳐 두껍게", ["재즈", "빅밴드"], min_notes=4),
    "cluster": VoicingStyle("cluster", "클러스터", "2도 간격으로 뭉친 현대적 텐션 덩어리", ["모던", "네오소울", "앰비언트"]),
    "octaves": VoicingStyle("octaves", "옥타브", "근음만 옥타브로. 유니즌 리프/베이스 더블링", ["락", "신스", "리프"], min_notes=1),
}


def list_voicing_styles() -> List[Dict[str, object]]:
    return [
        {
            "name": s.name,
            "korean": s.korean,
            "description": s.description,
            "tags": s.tags,
            "requires_seventh_chord": s.needs_seventh,
        }
        for s in VOICING_STYLES.values()
    ]


# --------------------------------------------------------------------------- #
# 내부 도우미
# --------------------------------------------------------------------------- #

def _degree_of_interval(iv: int) -> int:
    """반음 간격 -> 화성 도수(1,3,5,7,9,11,13)."""
    if iv == 0:
        return 1
    if 2 <= iv <= 5:
        return 3
    if 6 <= iv <= 8:
        return 5
    if 9 <= iv <= 11:
        return 7
    if 13 <= iv <= 15:
        return 9
    if 16 <= iv <= 18:
        return 11
    if 20 <= iv <= 22:
        return 13
    return 1 if iv % 12 == 0 else 9


#: 도수 -> 허용 반음 범위
_DEGREE_WINDOW = {1: (0, 0), 3: (2, 5), 5: (6, 8), 7: (9, 11),
                  9: (13, 15), 11: (16, 18), 13: (20, 22)}


def _pick_degree(chord: Chord, degree: int,
                 intervals: Optional[Sequence[int]] = None) -> Optional[int]:
    """도수에 해당하는 간격을 찾습니다.

    ``intervals`` 를 주면 코드 원본 대신 그 목록에서 찾습니다
    (텐션을 덧붙인 뒤의 상태를 반영하기 위함).
    """
    if intervals is None:
        return chord.interval_of(degree)
    window = _DEGREE_WINDOW.get(degree)
    if window is None:
        return None
    for iv in sorted(intervals):
        if window[0] <= iv <= window[1]:
            return iv
    return None


def _compact(intervals: Sequence[int]) -> List[int]:
    """텐션을 한 옥타브 안으로 접되, 서로 부딪히면 위 옥타브에 남깁니다."""
    out: List[int] = []
    for iv in sorted(intervals):
        folded = iv % 12
        if folded in [o % 12 for o in out]:
            continue
        # 반음 충돌(예: 1음과 b9)이 생기면 접지 않고 원래 높이 유지
        if any(abs(folded - (o % 12)) == 1 for o in out) and iv >= 12:
            out.append(iv)
        else:
            out.append(folded)
    return sorted(set(out))


def _trim(chord: Chord, intervals: List[int], max_notes: int,
          tension_mode: bool = False) -> List[int]:
    """음 수를 줄입니다. 기본은 5음 -> 근음 순, 텐션 모드에서는 근음 -> 5음 순."""
    ivs = list(intervals)
    priority = _TRIM_PRIORITY_TENSION if tension_mode else _TRIM_PRIORITY
    while len(ivs) > max_notes:
        for degree in priority:
            victims = [iv for iv in ivs if _degree_of_interval(iv) == degree]
            if victims and len(ivs) > max_notes:
                ivs.remove(victims[0])
                break
        else:
            ivs.pop()
    return sorted(ivs)


def _stack(root_pc: int, intervals: Sequence[int], bass_octave_note: int) -> List[int]:
    """근음을 ``bass_octave_note`` 근처에 두고 간격을 그대로 쌓습니다."""
    base = bass_octave_note - (bass_octave_note % 12) + (root_pc % 12)
    return [base + iv for iv in intervals]


def _inversions(pitches: Sequence[int]) -> List[List[int]]:
    """자리바꿈 후보들 (맨 아래 음을 차례로 옥타브 위로)."""
    out: List[List[int]] = []
    cur = sorted(pitches)
    for _ in range(len(cur)):
        out.append(list(cur))
        cur = sorted(cur[1:] + [cur[0] + 12])
    return out


def _distance(a: Sequence[int], b: Sequence[int]) -> float:
    """두 보이싱 사이의 평균 이동량 (양방향 최근접 매칭)."""
    if not a or not b:
        return 0.0
    fwd = sum(min(abs(x - y) for y in b) for x in a) / len(a)
    bwd = sum(min(abs(y - x) for x in a) for y in b) / len(b)
    return (fwd + bwd) / 2


def _fit(
    pitches: Sequence[int],
    low: int,
    high: int,
    center: int,
    prev: Optional[Sequence[int]],
    allow_inversion: bool = True,
) -> List[int]:
    """음역 안에 넣으면서 앞 보이싱과 가장 부드럽게 이어지는 배치를 고릅니다."""
    base = sorted(pitches)
    candidates: List[List[int]] = []
    variants = _inversions(base) if allow_inversion else [base]
    for variant in variants:
        for shift in range(-3, 4):
            cand = [p + 12 * shift for p in variant]
            if cand[0] < low or cand[-1] > high:
                continue
            candidates.append(cand)
    if not candidates:
        # 음역이 너무 좁으면 중심에 최대한 가깝게 옥타브만 이동
        best = base
        best_score = None
        for shift in range(-4, 5):
            cand = [p + 12 * shift for p in base]
            score = abs(sum(cand) / len(cand) - center)
            if best_score is None or score < best_score:
                best, best_score = cand, score
        return [max(0, min(127, p)) for p in best]

    def score(cand: List[int]) -> float:
        centre_penalty = abs(sum(cand) / len(cand) - center) * 0.35
        lead = _distance(cand, prev) if prev else 0.0
        return lead + centre_penalty

    return min(candidates, key=score)


# --------------------------------------------------------------------------- #
# 스타일별 간격 산출
# --------------------------------------------------------------------------- #

def _intervals_for_style(chord: Chord, style: str, max_notes: Optional[int],
                         add_tensions: bool = False) -> List[int]:
    ivs = list(chord.intervals)
    if add_tensions:
        ivs = _with_tensions(chord, ivs)
    third = _pick_degree(chord, 3, ivs)
    fifth = _pick_degree(chord, 5, ivs)
    seventh = _pick_degree(chord, 7, ivs)
    ninth = _pick_degree(chord, 9, ivs)
    thirteenth = _pick_degree(chord, 13, ivs)
    eleventh = _pick_degree(chord, 11, ivs)

    if style == "triad":
        out = [0] + [x for x in (third, fifth) if x is not None]
    elif style == "power":
        out = [0, fifth if fifth is not None else 7, 12]
    elif style == "octaves":
        out = [0, 12]
    elif style == "shell":
        guide = seventh if seventh is not None else thirteenth
        out = [0] + [x for x in (third, guide) if x is not None]
        if len(out) < 3 and fifth is not None:
            out.append(fifth)
    elif style == "rootless_a":
        # 3 - 5(또는 13) - 7 - 9
        upper = thirteenth if (chord.seventh == "dom" and thirteenth is not None) else fifth
        out = [x for x in (third, upper, seventh, ninth or 14) if x is not None]
    elif style == "rootless_b":
        # 7 - 9 - 3 - 13  (3음과 13음을 한 옥타브 올림)
        top3 = (third + 12) if third is not None else None
        top13 = ((thirteenth if thirteenth is not None else (fifth or 7)) + 12)
        out = [x for x in (seventh, ninth or 14, top3, top13) if x is not None]
    elif style == "quartal":
        out = _quartal_intervals(chord)
    elif style == "cluster":
        upper = [x for x in (ninth, third, eleventh, fifth, thirteenth, seventh) if x is not None]
        if len(upper) < 3:
            upper = [iv for iv in ivs if iv != 0] or list(ivs)
        folded = [u % 12 for u in upper]
        base = min(folded)
        out = sorted({f if f >= base else f + 12 for f in folded})
    elif style == "open":
        # 1 - 5 - 3 - 7 - 9
        order = [0, fifth, (third + 12) if third is not None else None,
                 (seventh + 12) if seventh is not None else None,
                 (ninth + 12) if ninth is not None else None]
        out = [x for x in order if x is not None]
    elif style == "guitar":
        order = [0, fifth, 12, (third + 12) if third is not None else None,
                 (seventh + 12) if seventh is not None else None]
        out = [x for x in order if x is not None]
    elif style == "pad":
        upper = _compact([x for x in (third, fifth, seventh, ninth) if x is not None])
        out = [0, fifth if fifth is not None else 7] + [u + 12 for u in upper]
        out = sorted(set(out))
    elif style == "block":
        close = _compact(ivs)
        out = sorted(set(close + [close[-1] - 12]))
    elif style in ("drop2", "drop3", "drop24"):
        close = _trim(chord, _compact(ivs), 4, tension_mode=add_tensions)
        out = _drop(close, style)
    else:  # close, piano 및 알 수 없는 이름
        out = _compact(ivs)

    out = sorted(set(x for x in out if x is not None))
    if max_notes:
        out = _trim(chord, out, max_notes, tension_mode=add_tensions)
    return out or [0]


def _with_tensions(chord: Chord, ivs: List[int]) -> List[int]:
    """9th(및 도미넌트의 13th)를 덧붙입니다.

    13th 는 도미넌트 코드에만 붙입니다. 마이너7 코드에 13th 를 붙이면
    도리안 색채가 강제로 들어가 조성에서 벗어나는 음이 되기 때문입니다.
    """
    out = list(ivs)
    tq = chord.triad_quality
    if tq in ("major", "minor") and chord.interval_of(9) is None:
        out.append(14)
    if chord.seventh == "dom" and chord.interval_of(13) is None \
            and chord.interval_of(11) is None:
        out.append(21)
    return sorted(set(out))


def _drop(close: List[int], style: str) -> List[int]:
    c = sorted(close)
    if len(c) < 4:
        return c
    if style == "drop2":
        idx = [len(c) - 2]
    elif style == "drop3":
        idx = [len(c) - 3]
    else:  # drop24
        idx = [len(c) - 2, len(c) - 4]
    out = list(c)
    for i in idx:
        out[i] = out[i] - 12
    return sorted(out)


def _available_pool(chord: Chord) -> List[int]:
    """코드톤 + 관용적으로 쓸 수 있는 텐션의 피치 클래스 풀 (근음 기준)."""
    pool = {iv % 12 for iv in chord.intervals}
    tq = chord.triad_quality
    if tq in ("major", "minor"):
        pool.add(2)                       # 9th
    if tq == "minor" or tq in ("sus4", "sus2"):
        pool.add(5)                       # 11th
    if tq in ("major", "minor") and chord.seventh != "maj":
        pool.add(9)                       # 13th / 6th
    # 장3도와 완전4도가 함께 있으면 4도를 뺀다 (반음 충돌 회피)
    if 4 in pool and 5 in pool:
        pool.discard(5)
    return sorted(pool)


def _quartal_intervals(chord: Chord, notes: int = 4) -> List[int]:
    """코드톤/텐션 풀 안에서 4도에 가장 가까운 음을 쌓습니다 (So What 계열)."""
    pool = _available_pool(chord)
    tq = chord.triad_quality
    if chord.seventh == "dom":
        start = _pick_degree(chord, 7)
    elif tq == "minor":
        start = _pick_degree(chord, 5)
    else:
        start = _pick_degree(chord, 3)
    cur = (start if start is not None else 0) % 12
    out = [cur]
    used = {cur % 12}
    for _ in range(notes - 1):
        best, best_score = None, None
        for pc in pool:
            if pc % 12 in used:
                continue
            cand = pc
            while cand <= cur + 2:        # 최소 단3도 위
                cand += 12
            if cand - cur > 7:            # 5도를 넘으면 4도 쌓기가 아니다
                continue
            score = abs((cand - cur) - 5)  # 완전4도(5반음)에 가까울수록 좋음
            if best_score is None or score < best_score:
                best, best_score = cand, score
        if best is None:                   # 풀이 부족하면 완전4도로 강행
            best = cur + 5
        out.append(best)
        used.add(best % 12)
        cur = best
    return sorted(set(out))


# --------------------------------------------------------------------------- #
# 공개 API
# --------------------------------------------------------------------------- #

def voice_chord(
    chord: Chord,
    style: str = "close",
    low: int = DEFAULT_LOW,
    high: int = DEFAULT_HIGH,
    center: Optional[int] = None,
    prev: Optional[Sequence[int]] = None,
    max_notes: Optional[int] = None,
    voice_leading: bool = True,
    add_bass: bool = False,
    bass_octave: int = 48,
    spread: float = 0.0,
    add_tensions: bool = False,
) -> List[int]:
    """코드 하나를 MIDI 음높이 목록으로.

    ``prev`` 를 넘기면 그 보이싱과 가장 가까운 자리바꿈을 고릅니다.
    ``add_bass`` 는 슬래시 코드/근음을 아래쪽에 따로 추가합니다.
    ``add_tensions`` 를 켜면 9th/13th 를 관용적으로 덧붙입니다.
    """
    style = (style or "close").lower()
    if style not in VOICING_STYLES:
        raise ValueError(
            f"모르는 보이싱 스타일입니다: {style!r} "
            f"(사용 가능: {', '.join(VOICING_STYLES)})"
        )
    center = center if center is not None else (low + high) // 2

    intervals = _intervals_for_style(chord, style, max_notes, add_tensions)
    pitches = _stack(chord.root, intervals, center)

    # 자리바꿈을 허용하면 안 되는 스타일 (구조 자체가 배치를 규정)
    fixed = style in ("power", "octaves", "guitar", "pad", "open", "rootless_b",
                      "drop2", "drop3", "drop24", "block", "quartal")
    allow_inv = voice_leading and not fixed
    pitches = _fit(pitches, low, high, center, prev if voice_leading else None,
                   allow_inversion=allow_inv)

    if spread:
        pitches = _apply_spread(pitches, spread, low, high)

    if style == "piano":
        # 왼손: 근음 + 5도, 오른손: 위에서 만든 클로즈 보이싱
        lh_root = chord.bass_pc
        lh = [_nearest(lh_root, bass_octave)]
        fifth = _pick_degree(chord, 5)
        if fifth is not None:
            lh.append(lh[0] + fifth)
        pitches = sorted(set(lh + [p for p in pitches if p > lh[-1] + 2]))
    elif add_bass or (chord.bass is not None and chord.bass != chord.root):
        bass_pc = chord.bass_pc
        bass = _nearest(bass_pc, bass_octave)
        while pitches and bass >= pitches[0] - 2:
            bass -= 12
        if bass >= 0:
            pitches = [bass] + pitches

    return sorted(set(max(0, min(127, p)) for p in pitches))


def _nearest(pc: int, target: int) -> int:
    base = target - (target % 12) + (pc % 12)
    return min((base - 12, base, base + 12), key=lambda x: abs(x - target))


def _apply_spread(pitches: List[int], amount: float, low: int, high: int) -> List[int]:
    """0.0~1.0 사이 값으로 보이싱을 위아래로 벌립니다."""
    if len(pitches) < 3 or amount <= 0:
        return pitches
    out = sorted(pitches)
    mid = len(out) // 2
    for i in range(1, mid + 1):
        if random.random() < amount and out[i - 1] - 12 >= low:
            out[i - 1] -= 12
    return sorted(set(out))


def voice_progression(
    chords: Sequence[Chord],
    style: str = "close",
    low: int = DEFAULT_LOW,
    high: int = DEFAULT_HIGH,
    max_notes: Optional[int] = None,
    voice_leading: bool = True,
    add_bass: bool = False,
    bass_octave: int = 48,
    center: Optional[int] = None,
    add_tensions: bool = False,
) -> List[List[int]]:
    """진행 전체를 보이싱. 각 코드는 직전 보이싱을 참조해 부드럽게 이어집니다."""
    out: List[List[int]] = []
    prev: Optional[List[int]] = None
    for chord in chords:
        v = voice_chord(
            chord, style=style, low=low, high=high, center=center, prev=prev,
            max_notes=max_notes, voice_leading=voice_leading,
            add_bass=add_bass, bass_octave=bass_octave, add_tensions=add_tensions,
        )
        out.append(v)
        # 베이스 음은 보이스 리딩 비교에서 제외 (상성만 부드럽게)
        prev = v[1:] if (add_bass or (chord.bass is not None and chord.bass != chord.root)) and len(v) > 3 else v
    return out


def voicing_movement(voicings: Sequence[Sequence[int]]) -> float:
    """진행 전체의 평균 이동량 (작을수록 부드러움). 테스트/리포트용."""
    if len(voicings) < 2:
        return 0.0
    return sum(_distance(voicings[i], voicings[i + 1]) for i in range(len(voicings) - 1)) / (len(voicings) - 1)
