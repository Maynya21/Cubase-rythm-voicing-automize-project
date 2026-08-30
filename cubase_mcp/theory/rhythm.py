"""리듬 패턴 엔진.

패턴은 "한 마디 안에서 언제/얼마나/얼마나 세게" 를 박(beat) 단위로 적어둔
목록입니다. 실제 음높이는 보이싱 단계에서 정해지므로, 여기서는 리듬만
다루고 :func:`render_bar` 에서 둘을 합칩니다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

#: (시작 박, 길이 박, 상대 벨로시티 0~1)
Event = Tuple[float, float, float]

ARP_ORDERS = ["up", "down", "updown", "downup", "up_inclusive", "alberti",
              "inside_out", "outside_in", "random", "as_is"]


@dataclass
class RhythmPattern:
    name: str
    korean: str
    description: str
    mode: str                      # block / arp / strum
    beats_per_bar: float
    events: List[Event]
    tags: List[str] = field(default_factory=list)
    swing: float = 0.0             # 기본 스윙 (0=스트레이트, 0.66≈트리플렛)
    swing_unit: float = 0.5        # 스윙을 적용할 음표 단위 (0.5=8분, 0.25=16분)
    arp_order: str = "up"
    strum_ms: float = 0.0          # 스트럼 시 음 사이 간격(ms)


def _p(name, korean, description, mode, bpb, events, tags=(), **kw) -> RhythmPattern:
    return RhythmPattern(name, korean, description, mode, bpb, list(events), list(tags), **kw)


# --------------------------------------------------------------------------- #
# 패턴 라이브러리
# --------------------------------------------------------------------------- #
_PATTERNS: List[RhythmPattern] = [
    # ---- 기본 -------------------------------------------------------------
    _p("whole", "온음표", "한 마디에 한 번, 길게 지속. 패드/스트링에 적합",
       "block", 4, [(0, 4, 1.0)], ["기본", "패드"]),
    _p("half", "2분음표", "2박마다 한 번",
       "block", 4, [(0, 2, 1.0), (2, 2, 0.9)], ["기본"]),
    _p("quarter", "4분음표", "정박 4번. 가장 단순한 컴핑",
       "block", 4, [(0, 1, 1.0), (1, 1, 0.82), (2, 1, 0.92), (3, 1, 0.82)], ["기본"]),
    _p("eighth", "8분음표", "8분음표 균등 반복",
       "block", 4, [(i * 0.5, 0.5, 1.0 if i % 2 == 0 else 0.78) for i in range(8)], ["기본"]),
    _p("sixteenth", "16분음표", "16분음표 균등 반복. 빠른 리듬 기타/신스",
       "block", 4, [(i * 0.25, 0.25, 1.0 if i % 4 == 0 else (0.85 if i % 2 == 0 else 0.7))
                    for i in range(16)], ["기본"]),

    # ---- 팝 / 발라드 -------------------------------------------------------
    _p("pop_ballad", "팝 발라드", "1박, 2박반, 4박. 잔잔한 발라드 반주의 정석",
       "block", 4, [(0, 1.5, 1.0), (1.5, 1.5, 0.82), (3, 1, 0.9)], ["팝", "발라드"]),
    _p("charleston", "찰스턴", "1박 + 2박반. 재즈/팝 컴핑의 기본 싱코페이션",
       "block", 4, [(0, 1.5, 1.0), (1.5, 2.5, 0.85)], ["재즈", "팝"]),
    _p("charleston_rev", "역찰스턴", "2박반 + 4박. 뒤로 밀린 느낌",
       "block", 4, [(1.5, 1.5, 0.9), (3, 1, 1.0)], ["재즈", "팝"]),
    _p("push", "앞당김(푸시)", "마디 마지막 8분에 미리 들어가 다음 마디를 당겨줌",
       "block", 4, [(0, 3.5, 1.0), (3.5, 0.5, 0.88)], ["팝", "발라드"]),
    _p("pump8", "펌핑 8분", "8분음표 스타카토. EDM/댄스팝 신스 코드",
       "block", 4, [(i * 0.5, 0.42, 1.0 if i % 2 == 0 else 0.75) for i in range(8)],
       ["팝", "EDM", "신스"]),
    _p("four_floor", "포온더플로어", "4분음표 짧은 스탭. 하우스/댄스",
       "block", 4, [(i, 0.35, 1.0 if i % 2 == 0 else 0.85) for i in range(4)], ["EDM", "하우스"]),
    _p("anthem", "앤섬", "1박 롱 + 3박반 셋잇단 느낌의 강한 스탭",
       "block", 4, [(0, 2.5, 1.0), (2.5, 0.5, 0.8), (3, 1, 0.95)], ["팝", "락"]),

    # ---- 락 ---------------------------------------------------------------
    _p("rock8", "락 8비트", "8분음표 다운스트로크 느낌. 어택 강조",
       "block", 4, [(i * 0.5, 0.45, 1.0 if i % 2 == 0 else 0.72) for i in range(8)], ["락"]),
    _p("rock_syncopa", "락 싱코페이션", "1, 2박반, 3박반, 4박반의 밀당",
       "block", 4, [(0, 1.5, 1.0), (1.5, 1.0, 0.85), (2.5, 1.0, 0.9), (3.5, 0.5, 0.8)], ["락", "펑크"]),
    _p("power_drive", "파워 드라이브", "16분 셔플 없이 밀어붙이는 리프용",
       "block", 4, [(0, 0.5, 1.0), (0.75, 0.25, 0.8), (1.5, 0.5, 0.9), (2, 0.5, 1.0),
                    (2.75, 0.25, 0.8), (3.5, 0.5, 0.9)], ["락", "메탈"]),

    # ---- 펑크 / R&B / 시티팝 ----------------------------------------------
    _p("funk16", "펑크 16비트", "당김이 많은 16분 커팅. 기타/클라비",
       "block", 4, [(0, 0.25, 1.0), (0.75, 0.25, 0.8), (1.25, 0.25, 0.72),
                    (1.75, 0.25, 0.9), (2.5, 0.25, 0.85), (3, 0.25, 0.95),
                    (3.25, 0.25, 0.7), (3.75, 0.25, 0.8)], ["펑크", "R&B"]),
    _p("citypop16", "시티팝 16비트", "16분 셔플감의 넓은 코드 커팅",
       "block", 4, [(0, 0.5, 1.0), (0.75, 0.25, 0.75), (1.5, 0.5, 0.88),
                    (2.25, 0.25, 0.72), (2.5, 0.5, 0.92), (3.25, 0.25, 0.78),
                    (3.5, 0.5, 0.85)], ["시티팝", "R&B"], swing=0.15, swing_unit=0.25),
    _p("neosoul", "네오소울", "느슨한 16분에 살짝 늦은 그루브",
       "block", 4, [(0, 1.0, 0.95), (1.25, 0.75, 0.72), (2.5, 0.5, 0.88),
                    (3.25, 0.75, 0.8)], ["네오소울", "R&B"], swing=0.2, swing_unit=0.25),
    _p("rnb_triplet", "R&B 셋잇단", "12/8 느낌의 셔플 컴핑",
       "block", 4, [(0, 0.67, 1.0), (0.67, 0.66, 0.72), (1.33, 0.67, 0.8),
                    (2, 0.67, 0.95), (2.67, 0.66, 0.72), (3.33, 0.67, 0.8)], ["R&B", "블루스"]),

    # ---- 재즈 -------------------------------------------------------------
    _p("jazz_four", "프레디 그린", "4분음표 짧게 4번. 스윙 리듬기타의 표준",
       "block", 4, [(i, 0.3, 0.9 if i % 2 == 0 else 0.75) for i in range(4)], ["재즈", "스윙"]),
    _p("jazz_comp", "재즈 컴핑", "불규칙한 싱코페이션 컴핑. 스윙 적용",
       "block", 4, [(0, 0.9, 0.95), (1.5, 0.5, 0.78), (2.5, 1.0, 0.88), (3.5, 0.5, 0.72)],
       ["재즈"], swing=0.62),
    _p("jazz_ballad", "재즈 발라드", "여백이 많은 느린 컴핑",
       "block", 4, [(0, 2.0, 0.9), (2.5, 1.5, 0.78)], ["재즈", "발라드"], swing=0.6),

    # ---- 라틴 -------------------------------------------------------------
    _p("bossa", "보사노바", "보사노바 기타 컴핑 (2-3 클라베 계열)",
       "block", 4, [(0, 1.0, 0.95), (1.5, 0.5, 0.78), (2.5, 1.0, 0.88), (3.5, 0.5, 0.75)],
       ["라틴", "보사노바"]),
    _p("samba", "삼바", "빠른 16분 당김의 삼바 컴핑",
       "block", 4, [(0, 0.5, 0.95), (0.75, 0.25, 0.7), (1.5, 0.5, 0.85), (2, 0.5, 0.9),
                    (2.75, 0.25, 0.72), (3.5, 0.5, 0.85)], ["라틴", "삼바"]),
    _p("montuno", "몬투노", "살사 피아노 몬투노 (아르페지오형)",
       "arp", 4, [(0, 0.5, 0.95), (0.5, 0.5, 0.75), (1, 0.5, 0.85), (1.5, 0.5, 0.72),
                  (2, 0.5, 0.95), (2.5, 0.5, 0.75), (3, 0.5, 0.85), (3.5, 0.5, 0.72)],
       ["라틴", "살사"], arp_order="updown"),
    _p("reggae", "레게 스캥크", "뒷박(오프비트)만 짧게. 레게/스카",
       "block", 4, [(0.5, 0.35, 0.9), (1.5, 0.35, 0.85), (2.5, 0.35, 0.9), (3.5, 0.35, 0.85)],
       ["레게", "스카"]),

    # ---- 가스펠 / 로파이 ---------------------------------------------------
    _p("gospel", "가스펠", "4분 정박에 16분 장식이 붙는 두터운 컴핑",
       "block", 4, [(0, 0.75, 1.0), (0.75, 0.25, 0.7), (1, 1.0, 0.85), (2, 0.75, 0.95),
                    (2.75, 0.25, 0.7), (3, 1.0, 0.85)], ["가스펠", "R&B"]),
    _p("lofi", "로파이", "느슨한 스윙 8분, 여백 많음",
       "block", 4, [(0, 1.4, 0.85), (1.5, 0.9, 0.65), (2.5, 1.4, 0.78)],
       ["로파이", "힙합"], swing=0.58),

    # ---- 아르페지오 --------------------------------------------------------
    _p("arp_up", "아르페지오 상행", "8분음표로 낮은음부터 차례로",
       "arp", 4, [(i * 0.5, 0.5, 0.9 if i % 2 == 0 else 0.75) for i in range(8)],
       ["아르페지오"], arp_order="up"),
    _p("arp_down", "아르페지오 하행", "8분음표로 높은음부터 차례로",
       "arp", 4, [(i * 0.5, 0.5, 0.9 if i % 2 == 0 else 0.75) for i in range(8)],
       ["아르페지오"], arp_order="down"),
    _p("arp_updown", "아르페지오 상하행", "올라갔다 내려오는 왕복",
       "arp", 4, [(i * 0.5, 0.5, 0.9 if i % 2 == 0 else 0.75) for i in range(8)],
       ["아르페지오"], arp_order="updown"),
    _p("arp16", "16분 아르페지오", "16분음표 상행. 신스 아르프",
       "arp", 4, [(i * 0.25, 0.25, 0.95 if i % 4 == 0 else 0.72) for i in range(16)],
       ["아르페지오", "신스"], arp_order="up"),
    _p("alberti", "알베르티 베이스", "낮-높-중-높. 고전 피아노 반주형",
       "arp", 4, [(i * 0.5, 0.5, 0.9 if i % 2 == 0 else 0.72) for i in range(8)],
       ["아르페지오", "클래식"], arp_order="alberti"),
    _p("ballad_arp", "발라드 아르페지오", "느린 8분 아르페지오. 피아노 발라드",
       "arp", 4, [(i * 0.5, 1.0, 0.88 if i % 4 == 0 else 0.7) for i in range(8)],
       ["아르페지오", "발라드"], arp_order="up_inclusive"),
    _p("broken", "분산화음", "낮은음 + 위 화음 반복 (기타 핑거스타일 느낌)",
       "arp", 4, [(0, 1.0, 0.95), (1, 0.5, 0.7), (1.5, 0.5, 0.75), (2, 1.0, 0.9),
                  (3, 0.5, 0.7), (3.5, 0.5, 0.75)], ["아르페지오", "기타"], arp_order="inside_out"),

    # ---- 스트럼 -----------------------------------------------------------
    _p("strum_down", "다운 스트럼", "4분마다 아래로 긁기",
       "strum", 4, [(i, 0.95, 1.0 if i % 2 == 0 else 0.85) for i in range(4)],
       ["기타", "스트럼"], strum_ms=22.0),
    _p("strum_folk", "포크 스트럼", "다운-다운업-업다운업의 기본 포크 패턴",
       "strum", 4, [(0, 0.5, 1.0), (1, 0.5, 0.85), (1.5, 0.5, 0.7), (2.5, 0.5, 0.72),
                    (3, 0.5, 0.88), (3.5, 0.5, 0.7)], ["기타", "포크"], strum_ms=18.0),
    _p("strum16", "16분 스트럼", "빠른 16분 커팅 스트럼",
       "strum", 4, [(i * 0.25, 0.22, 0.95 if i % 4 == 0 else 0.7) for i in range(16)],
       ["기타", "펑크"], strum_ms=10.0),

    # ---- 다른 박자 ---------------------------------------------------------
    _p("waltz", "왈츠 (3/4)", "쿵-짝-짝. 3박자 반주",
       "block", 3, [(0, 1, 1.0), (1, 1, 0.75), (2, 1, 0.75)], ["3박", "왈츠"]),
    _p("waltz_arp", "왈츠 아르페지오 (3/4)", "베이스 + 화음 두 번",
       "arp", 3, [(0, 1, 0.95), (1, 1, 0.72), (2, 1, 0.72)], ["3박", "왈츠"],
       arp_order="inside_out"),
    _p("sixeight", "6/8 발라드", "6/8 셋잇단 아르페지오",
       "arp", 3, [(i * 0.5, 0.5, 0.9 if i % 3 == 0 else 0.7) for i in range(6)],
       ["6/8", "발라드"], arp_order="up"),
    _p("twelve_eight", "12/8 블루스", "12/8 셔플 블루스 컴핑",
       "block", 4, [(0, 0.67, 1.0), (1, 0.67, 0.8), (2, 0.67, 0.95), (3, 0.67, 0.8)],
       ["블루스", "12/8"], swing=0.66),
]

RHYTHM_PATTERNS: Dict[str, RhythmPattern] = {p.name: p for p in _PATTERNS}


def list_rhythm_patterns(tag: Optional[str] = None) -> List[Dict[str, object]]:
    out = []
    for p in RHYTHM_PATTERNS.values():
        if tag and tag not in p.tags:
            continue
        out.append({
            "name": p.name,
            "korean": p.korean,
            "description": p.description,
            "mode": p.mode,
            "beats_per_bar": p.beats_per_bar,
            "hits_per_bar": len(p.events),
            "tags": p.tags,
            "default_swing": p.swing,
        })
    return out


def get_pattern(name: str) -> RhythmPattern:
    key = (name or "quarter").lower()
    if key not in RHYTHM_PATTERNS:
        raise ValueError(
            f"모르는 리듬 패턴입니다: {name!r} "
            f"(사용 가능: {', '.join(sorted(RHYTHM_PATTERNS))})"
        )
    return RHYTHM_PATTERNS[key]


# --------------------------------------------------------------------------- #
# 아르페지오 순서
# --------------------------------------------------------------------------- #

def arp_sequence(pitches: Sequence[int], order: str, length: int,
                 rng: Optional[random.Random] = None) -> List[int]:
    """보이싱을 아르페지오 순서에 따라 ``length`` 개의 음 열로 펼칩니다."""
    p = sorted(pitches)
    if not p:
        return []
    order = (order or "up").lower()
    if order == "up":
        seq = p
    elif order == "down":
        seq = p[::-1]
    elif order == "updown":                       # 양 끝 중복 없음
        seq = p + p[-2:0:-1] if len(p) > 2 else p + p[::-1]
    elif order == "downup":
        rev = p[::-1]
        seq = rev + rev[-2:0:-1] if len(p) > 2 else rev + p
    elif order == "up_inclusive":                 # 맨 위 음을 한 번 더
        seq = p + [p[0] + 12]
    elif order == "alberti":                      # 낮-높-중-높
        if len(p) >= 3:
            seq = [p[0], p[-1], p[len(p) // 2], p[-1]]
        else:
            seq = p
    elif order == "inside_out":                   # 베이스 + 위 화음
        seq = [p[0]] + p[1:]
    elif order == "outside_in":
        seq, lo, hi = [], 0, len(p) - 1
        while lo <= hi:
            seq.append(p[lo])
            if lo != hi:
                seq.append(p[hi])
            lo, hi = lo + 1, hi - 1
    elif order == "random":
        r = rng or random.Random()
        seq = list(p)
        r.shuffle(seq)
    else:                                          # as_is
        seq = list(pitches)
    if not seq:
        return []
    return [seq[i % len(seq)] for i in range(length)]


# --------------------------------------------------------------------------- #
# 한 마디 렌더링
# --------------------------------------------------------------------------- #

def _apply_swing(start: float, swing: float, unit: float) -> float:
    """오프비트를 뒤로 밀어 스윙감을 만듭니다.

    ``swing`` 0.5 = 스트레이트, 0.66 ≈ 트리플렛 셔플.
    """
    if swing <= 0 or swing == 0.5:
        return start
    pair = unit * 2
    pos = start % pair
    if abs(pos - unit) < 1e-6:
        return start - unit + pair * swing
    return start


def render_bar(
    pattern: RhythmPattern,
    pitches: Sequence[int],
    bar_start: float = 0.0,
    velocity: int = 90,
    swing: Optional[float] = None,
    humanize_timing: float = 0.0,     # 박 단위 표준편차
    humanize_velocity: float = 0.0,   # 벨로시티 표준편차
    accent: float = 1.0,              # 첫 박 강조 배수
    duration_scale: float = 1.0,
    beats_available: Optional[float] = None,
    rng: Optional[random.Random] = None,
    arp_order: Optional[str] = None,
    strum_ms: Optional[float] = None,
    bpm: float = 120.0,
    clamp_to_bar: bool = True,
) -> List[Tuple[float, float, int, int]]:
    """패턴 한 마디를 ``(시작 박, 길이 박, 음높이, 벨로시티)`` 목록으로.

    ``beats_available`` 이 패턴의 마디 길이보다 짧으면 잘라냅니다
    (예: 한 마디에 코드가 두 개일 때). ``clamp_to_bar`` 를 끄면 노트 길이가
    마디를 넘어가도 그대로 둡니다 (let ring).
    """
    rng = rng or random.Random()
    pitches = sorted(pitches)
    if not pitches:
        return []

    swing_amt = pattern.swing if swing is None else swing
    limit = pattern.beats_per_bar if beats_available is None else beats_available
    order = arp_order or pattern.arp_order
    strum = pattern.strum_ms if strum_ms is None else strum_ms
    strum_beats = (strum / 1000.0) * (bpm / 60.0)

    events = [e for e in pattern.events if e[0] < limit - 1e-9]
    out: List[Tuple[float, float, int, int]] = []

    arp_notes = arp_sequence(pitches, order, len(events), rng) if pattern.mode == "arp" else []

    for idx, (start, dur, vel_scale) in enumerate(events):
        t = _apply_swing(start, swing_amt, pattern.swing_unit)
        if humanize_timing:
            t += rng.gauss(0.0, humanize_timing)
        t = max(0.0, t)
        length = dur * duration_scale
        if clamp_to_bar:
            length = min(length, max(0.05, limit - start))
        base_vel = velocity * vel_scale
        if start < 1e-6:
            base_vel *= accent
        if humanize_velocity:
            base_vel += rng.gauss(0.0, humanize_velocity)
        v = int(max(1, min(127, round(base_vel))))

        if pattern.mode == "arp":
            out.append((bar_start + t, length, arp_notes[idx], v))
        elif pattern.mode == "strum":
            up = idx % 2 == 1                      # 짝수번째는 업스트로크로 간주
            seq = pitches[::-1] if up else pitches
            for n, pitch in enumerate(seq):
                offset = n * strum_beats
                nv = int(max(1, min(127, v - n * 2)))
                out.append((bar_start + t + offset, max(0.05, length - offset), pitch, nv))
        else:
            for n, pitch in enumerate(pitches):
                # 아래쪽 음을 살짝 세게 (자연스러운 균형)
                nv = int(max(1, min(127, v - n)))
                out.append((bar_start + t, length, pitch, nv))

    return out


# --------------------------------------------------------------------------- #
# 그리드 표기법 — 리듬 직접 입력
# --------------------------------------------------------------------------- #

#: 치는 기호 -> 상대 벨로시티
GRID_HITS = {"X": 1.0, "x": 0.82, "o": 0.55}
#: 쉬는 기호 (앞 음을 여기서 끊습니다)
GRID_RESTS = "-."
#: 앞 음을 이어서 늘리는 기호
GRID_TIES = "~_"
#: 마디 구분
GRID_BAR = "|"

GRID_HELP = """\
리듬 그리드 표기법
  X   세게 치기 (악센트)
  x   치기
  o   여리게 치기 (고스트)
  -   쉬기 (앞 음이 여기서 끊깁니다)   . 도 같습니다
  ~   앞 음을 이어서 늘리기            _ 도 같습니다
  |   마디 구분
  공백은 무시하므로 읽기 쉽게 넣어도 됩니다.

칸 수가 한 마디의 분할을 정합니다 (4/4 기준):
  x-x-        4칸  -> 4분음표
  x-x-x-x-    8칸  -> 8분음표
  x--x--x-    8칸  -> 8분음표, 당김
  x~~~        4칸  -> 온음표처럼 한 마디 지속
  X--x-X--x   8칸  -> 1박과 3박에 악센트

예시
  "x-x-x-x-"          8비트 균등
  "X~~-x~~-"          2박씩 길게, 첫 박 악센트
  "x--x--x-"          찰스턴 계열 당김
  "X-o-x-o- | x-x-xxx-"  두 마디 패턴
"""


def parse_grid(
    text: str,
    beats_per_bar: float = 4.0,
    name: str = "custom",
    mode: str = "block",
    swing: float = 0.0,
    arp_order: str = "up",
    strum_ms: float = 18.0,
) -> RhythmPattern:
    """``"x--x-x--"`` 같은 그리드 문자열을 :class:`RhythmPattern` 으로.

    칸 수가 분할을 정합니다. 4/4 에서 8칸이면 8분음표, 16칸이면 16분음표입니다.
    ``|`` 로 마디를 나누면 마디마다 분할이 달라도 됩니다.

    Args:
        text: 그리드 문자열. :data:`GRID_HELP` 참고.
        beats_per_bar: 한 마디의 박 수 (4/4 는 4, 3/4 는 3).
        name: 패턴 이름 (표시용).
        mode: ``block``(화음 동시) / ``arp``(아르페지오) / ``strum``(긁기).
        swing: 0=스트레이트, 0.66≈트리플렛 셔플.
        arp_order: ``mode="arp"`` 일 때 음 순서.
        strum_ms: ``mode="strum"`` 일 때 음 사이 간격(밀리초).
    """
    if mode not in ("block", "arp", "strum"):
        raise ValueError(f"mode 는 block/arp/strum 중 하나여야 합니다: {mode!r}")
    if beats_per_bar <= 0:
        raise ValueError("beats_per_bar 는 0보다 커야 합니다")

    raw = str(text or "")
    cleaned = "".join(ch for ch in raw if not ch.isspace())
    if not cleaned:
        raise ValueError("빈 리듬 문자열입니다.\n" + GRID_HELP)

    bars = [bar for bar in cleaned.split(GRID_BAR) if bar != ""]
    if not bars:
        raise ValueError("리듬에 칸이 하나도 없습니다.\n" + GRID_HELP)

    valid = set(GRID_HITS) | set(GRID_RESTS) | set(GRID_TIES)
    unknown = sorted({ch for ch in cleaned if ch not in valid and ch != GRID_BAR})
    if unknown:
        raise ValueError(
            f"리듬 문자열에 모르는 기호가 있습니다: {' '.join(repr(c) for c in unknown)}\n"
            + GRID_HELP
        )

    for index, bar in enumerate(bars):
        _check_subdivision(bar, beats_per_bar, index, len(bars))

    events: List[Event] = []
    open_hit: Optional[Tuple[float, float]] = None   # (시작 박, 벨로시티)

    def close(at: float) -> None:
        nonlocal open_hit
        if open_hit is not None:
            start, velocity = open_hit
            events.append((start, max(0.05, at - start), velocity))
            open_hit = None

    for bar_index, bar in enumerate(bars):
        step = beats_per_bar / len(bar)
        bar_start = bar_index * beats_per_bar
        for cell_index, symbol in enumerate(bar):
            at = bar_start + cell_index * step
            if symbol in GRID_HITS:
                close(at)
                open_hit = (at, GRID_HITS[symbol])
            elif symbol in GRID_RESTS:
                close(at)
            # 타이(~)는 아무것도 하지 않고 앞 음을 계속 울립니다
    close(len(bars) * beats_per_bar)

    if not events:
        raise ValueError(
            "치는 음이 하나도 없습니다. x, X, o 중 하나는 있어야 합니다.\n" + GRID_HELP
        )

    total_beats = beats_per_bar * len(bars)
    cells = "".join(bars)
    subdivision = len(bars[0]) / beats_per_bar if bars else 1
    swing_unit = 0.25 if subdivision >= 4 else 0.5

    return RhythmPattern(
        name=name,
        korean="직접 입력",
        description=f"그리드 '{raw.strip()}' ({len(cells)}칸, {len(bars)}마디)",
        mode=mode,
        beats_per_bar=total_beats,
        events=events,
        tags=["직접입력"],
        swing=swing,
        swing_unit=swing_unit,
        arp_order=arp_order,
        strum_ms=strum_ms,
    )


#: 한 박을 몇 칸으로 나눌 수 있는가 (2·4·8·16분음표와 셋잇단 계열)
_CELLS_PER_BEAT = (0.25, 0.5, 1, 2, 3, 4, 6, 8, 12, 16)


def _check_subdivision(bar: str, beats_per_bar: float, index: int, total: int) -> None:
    """칸 수가 음악적으로 말이 되는 분할인지 확인합니다.

    칸을 하나 빠뜨리면 9잇단음표 같은 값이 조용히 나옵니다. 의도한 경우는
    거의 없으므로, 그냥 통과시키지 않고 쓸 수 있는 칸 수를 알려 줍니다.
    """
    per_beat = len(bar) / beats_per_bar
    if any(abs(per_beat - allowed) < 1e-9 for allowed in _CELLS_PER_BEAT):
        return
    usable = sorted({int(round(beats_per_bar * allowed))
                     for allowed in _CELLS_PER_BEAT
                     if abs(beats_per_bar * allowed - round(beats_per_bar * allowed)) < 1e-9
                     and beats_per_bar * allowed >= 1})
    where = f"{index + 1}번째 마디" if total > 1 else "리듬"
    raise ValueError(
        f"{where}의 칸이 {len(bar)}개인데, {beats_per_bar:g}박을 그렇게 나눌 수 없습니다.\n"
        f"쓸 수 있는 칸 수: {', '.join(str(n) for n in usable)}\n"
        f"(예: 8칸이면 8분음표, 16칸이면 16분음표, 12칸이면 셋잇단)\n"
        f"마디마다 분할을 다르게 하려면 '|' 로 나누세요.\n" + GRID_HELP
    )


def looks_like_grid(text: str) -> bool:
    """프리셋 이름이 아니라 그리드 문자열로 보이는지."""
    stripped = "".join(ch for ch in str(text or "") if not ch.isspace())
    if not stripped:
        return False
    valid = set(GRID_HITS) | set(GRID_RESTS) | set(GRID_TIES) | {GRID_BAR}
    return all(ch in valid for ch in stripped) and any(ch in GRID_HITS for ch in stripped)


def resolve_pattern(
    rhythm: str,
    beats_per_bar: float = 4.0,
    mode: str = "block",
    swing: float = 0.0,
    arp_order: str = "up",
    strum_ms: float = 18.0,
) -> RhythmPattern:
    """프리셋 이름이든 그리드 문자열이든 받아서 패턴을 돌려줍니다.

    **프리셋 이름을 먼저** 확인합니다. ``sixteenth`` 처럼 이름 안에 ``x`` 가
    들어간 프리셋을 그리드로 오해하지 않기 위해서입니다.
    """
    key = str(rhythm or "quarter").strip()
    if key.lower() in RHYTHM_PATTERNS:
        return RHYTHM_PATTERNS[key.lower()]
    if looks_like_grid(key):
        return parse_grid(key, beats_per_bar=beats_per_bar, mode=mode,
                          swing=swing, arp_order=arp_order, strum_ms=strum_ms)
    raise ValueError(
        f"모르는 리듬입니다: {rhythm!r}\n"
        f"프리셋 이름({', '.join(sorted(RHYTHM_PATTERNS))}) 중 하나이거나,\n"
        f"그리드 문자열이어야 합니다.\n" + GRID_HELP
    )
