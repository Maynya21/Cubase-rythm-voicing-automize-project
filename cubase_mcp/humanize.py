"""휴머나이즈 — 사람이 친 것 같은 미세한 타이밍/세기 변화.

무작위로 흔드는 것만으로는 사람처럼 들리지 않습니다. 실제 연주에는
**규칙적인 경향**이 있고, 그게 무작위성보다 훨씬 중요합니다.

이 모듈이 다루는 것:

* **메트릭 악센트** — 1박 > 3박 > 2·4박 > 8분 뒷박 > 16분. 마디 안의 강약 구조.
* **백비트 악센트** — 팝/락에서 2·4박을 밀어주는 습관.
* **성부 균형** — 피아니스트는 최고음(선율)을 세게, 속음을 여리게 칩니다.
* **코드 굴림(roll)** — 화음의 모든 음을 정확히 동시에 치는 사람은 없습니다.
  낮은음부터 몇 밀리초씩 번져 올라가는데, 이게 피아노를 사람처럼 들리게 하는
  가장 큰 요소입니다.
* **선율 리드** — 최고음을 화음보다 살짝 먼저(또는 늦게) 치는 연주 습관.
* **밀당(push/pull)** — R&B는 박 뒤에서 끌고(레이드백), 펑크/EDM은 앞에서 밉니다.
* **정박 정확도** — 정박은 정확하고 뒷박이 흔들리는 게 사람의 실제 패턴입니다.
* **세기-타이밍 결합** — 세게 치는 음은 아주 살짝 빨라집니다.

노트를 다 만든 **뒤에** 후처리로 적용하므로, 코드/베이스/아르페지오 어디에나
같은 방식으로 걸립니다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from .midi.smf import Note

#: 같은 화음으로 묶을 시간 오차 (밀리초). 스트럼처럼 이미 벌어진 것도 한 덩어리로 봅니다.
GROUP_WINDOW_MS = 45.0


@dataclass
class HumanizeProfile:
    """악기/장르별 연주 습관 묶음.

    시간 값은 밀리초, 벨로시티 값은 MIDI 벨로시티(0~127) 단위입니다.
    """

    name: str
    korean: str
    description: str

    # ---- 타이밍 ----------------------------------------------------------
    timing_jitter_ms: float = 0.0      # 무작위 흔들림 (표준편차)
    # start 에 더하는 값입니다: 양수 = 박보다 늦게(레이드백), 음수 = 먼저(푸시)
    push_pull_ms: float = 0.0
    downbeat_tightness: float = 0.5    # 0~1. 높을수록 정박을 정확하게 침
    roll_ms: float = 0.0               # 화음 굴림: 음 하나당 지연 (낮은음 -> 높은음)
    roll_jitter_ms: float = 0.0
    melody_lead_ms: float = 0.0        # 최고음을 얼마나 먼저 치는지 (음수 = 늦게)
    velocity_timing_coupling: float = 0.0   # 세게 칠수록 빨라지는 정도 (ms/벨로시티64)

    # ---- 벨로시티 --------------------------------------------------------
    velocity_jitter: float = 0.0       # 무작위 흔들림 (표준편차)
    metric_accent: float = 0.0         # 마디 안 강약 (0 = 평평, 1 = 또렷)
    backbeat_accent: float = 0.0       # 2·4박 강조
    top_voice_boost: float = 0.0       # 최고음 강조 (벨로시티 가산)
    bass_voice_boost: float = 0.0      # 최저음 강조
    inner_voice_cut: float = 0.0       # 속음 감산
    velocity_sensitive: bool = True    # False 면 벨로시티를 고정 (오르간 등)
    fixed_velocity: int = 100          # velocity_sensitive=False 일 때 쓰는 값

    # ---- 길이 ------------------------------------------------------------
    duration_jitter: float = 0.0       # 길이 흔들림 (비율, 0.05 = ±5%)
    legato: float = 0.0                # 다음 음까지 얼마나 이어 붙일지 (0~1)

    tags: List[str] = field(default_factory=list)


def _p(*args, **kwargs) -> HumanizeProfile:
    return HumanizeProfile(*args, **kwargs)


PROFILES: Dict[str, HumanizeProfile] = {p.name: p for p in [
    _p("off", "끄기", "완전히 정확한 그리드. 아무것도 바꾸지 않습니다.",
       tags=["기계적"]),

    _p("machine", "머신", "그리드에 딱 붙되 강약만 살짝. EDM/신스 시퀀스",
       timing_jitter_ms=0.5, downbeat_tightness=1.0,
       velocity_jitter=2.0, metric_accent=0.35,
       tags=["EDM", "신스", "기계적"]),

    _p("subtle", "은은하게", "어떤 악기에도 무난한 최소한의 흔들림",
       timing_jitter_ms=5.0, downbeat_tightness=0.6, roll_ms=3.0, roll_jitter_ms=1.5,
       velocity_jitter=4.0, metric_accent=0.35, top_voice_boost=3.0,
       duration_jitter=0.05, tags=["범용"]),

    # ---- 피아노 계열 -------------------------------------------------------
    _p("piano_natural", "피아노 (자연스럽게)",
       "일반적인 피아노 반주. 코드 굴림 + 선율 강조 + 메트릭 악센트",
       timing_jitter_ms=7.0, downbeat_tightness=0.65,
       roll_ms=7.0, roll_jitter_ms=3.0, melody_lead_ms=6.0,
       velocity_timing_coupling=1.5,
       velocity_jitter=5.0, metric_accent=0.5, top_voice_boost=6.0,
       bass_voice_boost=3.0, inner_voice_cut=4.0,
       duration_jitter=0.08, legato=0.15, tags=["피아노"]),

    _p("piano_expressive", "피아노 (표현적으로)",
       "루바토에 가까운 큰 흔들림. 솔로 피아노/시네마틱",
       timing_jitter_ms=14.0, downbeat_tightness=0.45,
       roll_ms=14.0, roll_jitter_ms=6.0, melody_lead_ms=12.0,
       velocity_timing_coupling=2.5,
       velocity_jitter=9.0, metric_accent=0.6, top_voice_boost=10.0,
       bass_voice_boost=4.0, inner_voice_cut=6.0,
       duration_jitter=0.14, legato=0.25, tags=["피아노", "클래식", "시네마틱"]),

    _p("piano_ballad", "피아노 발라드",
       "느린 곡용. 굴림을 크게 하고 여린 부분을 더 여리게",
       timing_jitter_ms=10.0, downbeat_tightness=0.5,
       roll_ms=18.0, roll_jitter_ms=7.0, melody_lead_ms=10.0,
       velocity_timing_coupling=2.0,
       velocity_jitter=7.0, metric_accent=0.45, top_voice_boost=9.0,
       bass_voice_boost=5.0, inner_voice_cut=6.0,
       duration_jitter=0.12, legato=0.3, tags=["피아노", "발라드"]),

    _p("rhodes", "로즈 / 일렉피아노",
       "피아노보다 굴림이 작고 그루브가 단단함. 시티팝/네오소울",
       timing_jitter_ms=6.0, push_pull_ms=6.0, downbeat_tightness=0.7,
       roll_ms=4.0, roll_jitter_ms=2.0, melody_lead_ms=3.0,
       velocity_jitter=5.0, metric_accent=0.45, backbeat_accent=0.3,
       top_voice_boost=4.0, inner_voice_cut=3.0,
       duration_jitter=0.07, tags=["일렉피아노", "시티팝", "네오소울"]),

    # ---- 기타 -------------------------------------------------------------
    _p("guitar_strum", "기타 스트럼",
       "피크로 긁는 폭이 넓음. 아래 현이 먼저 나고 세기가 번짐",
       timing_jitter_ms=9.0, downbeat_tightness=0.6,
       roll_ms=22.0, roll_jitter_ms=8.0,
       velocity_jitter=7.0, metric_accent=0.5, backbeat_accent=0.35,
       top_voice_boost=2.0, bass_voice_boost=5.0,
       duration_jitter=0.1, tags=["기타", "포크", "락"]),

    _p("guitar_finger", "기타 핑거스타일",
       "손가락으로 뜯음. 굴림이 작고 베이스(엄지)가 살짝 먼저",
       timing_jitter_ms=6.0, downbeat_tightness=0.7,
       roll_ms=6.0, roll_jitter_ms=3.0, melody_lead_ms=4.0,
       velocity_jitter=5.0, metric_accent=0.4,
       top_voice_boost=5.0, bass_voice_boost=6.0, inner_voice_cut=3.0,
       duration_jitter=0.08, legato=0.2, tags=["기타", "핑거스타일"]),

    _p("guitar_cutting", "기타 커팅",
       "16비트 커팅. 아주 타이트하고 짧게",
       timing_jitter_ms=4.0, downbeat_tightness=0.85,
       roll_ms=9.0, roll_jitter_ms=3.0,
       velocity_jitter=6.0, metric_accent=0.55, backbeat_accent=0.4,
       duration_jitter=0.06, tags=["기타", "펑크", "시티팝"]),

    # ---- 건반/신스/기타 음원 ----------------------------------------------
    _p("organ", "오르간",
       "해먼드/파이프 오르간은 벨로시티가 없습니다. 세기를 고정하고 타이밍만 흔듭니다.",
       timing_jitter_ms=8.0, downbeat_tightness=0.6, roll_ms=9.0, roll_jitter_ms=4.0,
       velocity_sensitive=False, fixed_velocity=100,
       duration_jitter=0.06, legato=0.2, tags=["오르간"]),

    _p("strings", "스트링",
       "활 긋는 시작이 제각각. 굴림이 크고 악센트는 완만",
       timing_jitter_ms=16.0, downbeat_tightness=0.35,
       roll_ms=16.0, roll_jitter_ms=9.0,
       velocity_jitter=8.0, metric_accent=0.3,
       top_voice_boost=5.0, bass_voice_boost=3.0,
       duration_jitter=0.12, legato=0.35, tags=["스트링", "오케스트라"]),

    _p("pad", "패드",
       "어택이 느려 타이밍은 덜 중요. 세기 변화 위주",
       timing_jitter_ms=12.0, downbeat_tightness=0.3,
       roll_ms=10.0, roll_jitter_ms=6.0,
       velocity_jitter=6.0, metric_accent=0.2,
       duration_jitter=0.1, legato=0.4, tags=["패드", "신스", "앰비언트"]),

    # ---- 그루브 성향 -------------------------------------------------------
    _p("laid_back", "레이드백 (뒤로 끌기)",
       "박보다 살짝 늦게. R&B/네오소울/소울의 느긋한 그루브",
       timing_jitter_ms=8.0, push_pull_ms=18.0, downbeat_tightness=0.5,
       roll_ms=8.0, roll_jitter_ms=4.0,
       velocity_jitter=6.0, metric_accent=0.4, backbeat_accent=0.45,
       top_voice_boost=4.0, tags=["R&B", "네오소울", "그루브"]),

    _p("pushed", "푸시 (앞으로 밀기)",
       "박보다 살짝 먼저. 락/펑크/EDM의 몰아가는 느낌",
       timing_jitter_ms=5.0, push_pull_ms=-9.0, downbeat_tightness=0.75,
       roll_ms=4.0, roll_jitter_ms=2.0,
       velocity_jitter=6.0, metric_accent=0.5, backbeat_accent=0.3,
       tags=["락", "펑크", "EDM", "그루브"]),

    _p("jazz_loose", "재즈 (느슨하게)",
       "컴핑의 자유로운 밀당. 흔들림이 크고 악센트가 불규칙",
       timing_jitter_ms=15.0, push_pull_ms=8.0, downbeat_tightness=0.4,
       roll_ms=11.0, roll_jitter_ms=6.0, melody_lead_ms=5.0,
       velocity_timing_coupling=2.0,
       velocity_jitter=10.0, metric_accent=0.3, backbeat_accent=0.25,
       top_voice_boost=5.0, inner_voice_cut=4.0,
       duration_jitter=0.15, tags=["재즈"]),

    _p("lofi_sloppy", "로파이 (헐렁하게)",
       "일부러 어긋난 느낌. 로파이 힙합",
       timing_jitter_ms=22.0, push_pull_ms=24.0, downbeat_tightness=0.25,
       roll_ms=16.0, roll_jitter_ms=10.0,
       velocity_jitter=12.0, metric_accent=0.25,
       duration_jitter=0.2, tags=["로파이", "힙합"]),

    # ---- 베이스 -----------------------------------------------------------
    _p("bass_tight", "베이스 (타이트)",
       "베이스는 보통 코드보다 정확합니다. 흔들림 최소",
       timing_jitter_ms=4.0, downbeat_tightness=0.85,
       velocity_jitter=5.0, metric_accent=0.45,
       duration_jitter=0.05, tags=["베이스"]),

    _p("bass_laid_back", "베이스 (뒤로 끌기)",
       "소울/R&B 베이스의 늦게 놓는 느낌",
       timing_jitter_ms=6.0, push_pull_ms=14.0, downbeat_tightness=0.7,
       velocity_jitter=6.0, metric_accent=0.4, backbeat_accent=0.25,
       duration_jitter=0.07, tags=["베이스", "R&B"]),
]}


def list_humanize_profiles() -> List[Dict[str, object]]:
    return [
        {
            "name": p.name,
            "korean": p.korean,
            "description": p.description,
            "tags": p.tags,
            "timing_jitter_ms": p.timing_jitter_ms,
            "push_pull_ms": p.push_pull_ms,
            "chord_roll_ms": p.roll_ms,
            "velocity_sensitive": p.velocity_sensitive,
        }
        for p in PROFILES.values()
    ]


def get_profile(name: str) -> HumanizeProfile:
    key = (name or "off").lower()
    if key not in PROFILES:
        raise ValueError(
            f"모르는 휴머나이즈 프로파일입니다: {name!r} "
            f"(사용 가능: {', '.join(PROFILES)})"
        )
    return PROFILES[key]


def customize(base: str = "subtle", **overrides) -> HumanizeProfile:
    """기본 프로파일에서 일부 값만 바꾼 프로파일을 만듭니다."""
    profile = get_profile(base)
    unknown = set(overrides) - set(profile.__dataclass_fields__)
    if unknown:
        raise ValueError(
            f"휴머나이즈 프로파일에 없는 항목입니다: {sorted(unknown)} "
            f"(사용 가능: {', '.join(sorted(profile.__dataclass_fields__))})"
        )
    clean = {k: v for k, v in overrides.items() if v is not None}
    return replace(profile, **clean) if clean else profile


# --------------------------------------------------------------------------- #
# 메트릭 위치
# --------------------------------------------------------------------------- #

def _metric_weight(beat_in_bar: float, beats_per_bar: float) -> float:
    """마디 안 위치의 세기 가중치 (1.0 = 가장 강함).

    1박 > 마디 중앙 > 나머지 정박 > 8분 뒷박 > 16분 자리.
    """
    tol = 0.06
    if abs(beat_in_bar) < tol:
        return 1.0
    half = beats_per_bar / 2
    if abs(beat_in_bar - half) < tol:
        return 0.8
    if abs(beat_in_bar - round(beat_in_bar)) < tol:
        return 0.62
    if abs((beat_in_bar * 2) - round(beat_in_bar * 2)) < tol * 2:
        return 0.42
    return 0.28


def _is_backbeat(beat_in_bar: float, beats_per_bar: float) -> bool:
    """4/4 의 2·4박(0부터 세어 1, 3박)인지."""
    if beats_per_bar < 4:
        return False
    tol = 0.06
    return any(abs(beat_in_bar - b) < tol for b in (1.0, 3.0))


# --------------------------------------------------------------------------- #
# 적용
# --------------------------------------------------------------------------- #

def humanize_notes(
    notes: Sequence[Note],
    profile: HumanizeProfile | str = "subtle",
    *,
    tempo: float = 120.0,
    ppq: int = 480,
    time_signature: Tuple[int, int] = (4, 4),
    seed: Optional[int] = None,
    amount: float = 1.0,
) -> List[Note]:
    """노트 목록에 휴머나이즈를 적용해 **새 목록** 을 돌려줍니다.

    Args:
        notes: 원본 노트 (변경하지 않습니다).
        profile: 프로파일 이름 또는 :class:`HumanizeProfile`.
        tempo: BPM. 밀리초를 틱으로 바꿀 때 필요합니다.
        ppq: 4분음표당 틱.
        time_signature: 마디 안 위치를 계산하는 데 씁니다.
        seed: 같은 값을 주면 같은 결과가 나옵니다.
        amount: 0~1 로 전체 효과 강도를 줄입니다.
    """
    p = get_profile(profile) if isinstance(profile, str) else profile
    if p.name == "off" or amount <= 0 or not notes:
        return [replace(n) for n in notes]
    if not 0 <= amount <= 1:
        raise ValueError("amount 는 0.0 ~ 1.0 사이여야 합니다")

    rng = random.Random(seed)
    ticks_per_ms = (ppq * tempo) / 60000.0
    num, den = time_signature
    beats_per_bar = num * 4.0 / den

    def ms(value: float) -> float:
        return value * ticks_per_ms * amount

    # ---- 동시에 울리는 음들을 한 덩어리로 묶기 ---------------------------
    window = GROUP_WINDOW_MS * ticks_per_ms
    groups: List[List[Note]] = []
    for note in sorted(notes, key=lambda n: (n.channel, n.start, n.pitch)):
        if groups and groups[-1][0].channel == note.channel \
                and note.start - groups[-1][0].start <= window:
            groups[-1].append(note)
        else:
            groups.append([note])

    out: List[Note] = []
    for group in groups:
        anchor = min(n.start for n in group)
        beat = anchor / ppq
        beat_in_bar = beat % beats_per_bar
        weight = _metric_weight(beat_in_bar, beats_per_bar)

        # 정박일수록 정확하게: 가중치가 높은 자리는 흔들림을 줄입니다.
        tightness = 1.0 - p.downbeat_tightness * weight
        shift = ms(p.push_pull_ms)
        if p.timing_jitter_ms:
            shift += ms(rng.gauss(0.0, p.timing_jitter_ms)) * tightness

        # 이미 벌어져 있는 덩어리(스트럼 등)는 원래 간격을 지키고,
        # 완전히 동시에 울리는 덩어리에만 굴림을 새로 넣습니다.
        simultaneous = len({n.start for n in group}) == 1
        ordered = sorted(group, key=lambda n: n.pitch)
        top = ordered[-1] if ordered else None
        bottom = ordered[0] if ordered else None

        for index, note in enumerate(ordered):
            start = note.start + shift

            if simultaneous and p.roll_ms and len(ordered) > 1:
                roll = ms(p.roll_ms) * index
                if p.roll_jitter_ms:
                    roll += ms(rng.gauss(0.0, p.roll_jitter_ms))
                start += roll

            if p.melody_lead_ms and note is top and len(ordered) > 1:
                start -= ms(p.melody_lead_ms)

            # ---- 벨로시티 -------------------------------------------------
            if not p.velocity_sensitive:
                velocity = float(p.fixed_velocity)
            else:
                velocity = float(note.velocity)
                if p.metric_accent:
                    velocity *= 1.0 + p.metric_accent * (weight - 0.62) * amount
                if p.backbeat_accent and _is_backbeat(beat_in_bar, beats_per_bar):
                    velocity *= 1.0 + p.backbeat_accent * 0.18 * amount
                if len(ordered) > 1:
                    if note is top:
                        velocity += p.top_voice_boost * amount
                    elif note is bottom:
                        velocity += p.bass_voice_boost * amount
                    else:
                        velocity -= p.inner_voice_cut * amount
                if p.velocity_jitter:
                    velocity += rng.gauss(0.0, p.velocity_jitter) * amount

            # 세게 치는 음은 아주 살짝 빨라집니다.
            if p.velocity_timing_coupling and p.velocity_sensitive:
                start -= ms(p.velocity_timing_coupling) * ((velocity - 64.0) / 64.0)

            # ---- 길이 -----------------------------------------------------
            duration = float(note.duration)
            if p.duration_jitter:
                duration *= 1.0 + rng.gauss(0.0, p.duration_jitter) * amount
            if p.legato:
                duration *= 1.0 + p.legato * amount

            out.append(Note(
                start=max(0, int(round(start))),
                duration=max(1, int(round(duration))),
                pitch=note.pitch,
                velocity=int(max(1, min(127, round(velocity)))),
                channel=note.channel,
            ))

    out.sort(key=lambda n: (n.start, n.pitch))
    return out
