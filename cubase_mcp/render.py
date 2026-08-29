"""코드 + 보이싱 + 리듬을 합쳐 실제 MIDI 트랙을 만듭니다.

리듬 패턴은 **타임라인 위에 깔린 뒤** 그 시점에 울리는 코드를 찾아
음높이를 얻습니다. 그래서 한 마디에 코드가 두 개면 앞 코드는 패턴의 앞부분,
뒤 코드는 패턴의 뒷부분을 자연스럽게 물려받습니다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .humanize import HumanizeProfile, customize, get_profile, humanize_notes
from .midi.smf import MidiFile, Note, Track, beats_to_ticks
from .theory.chords import Chord
from .theory.notes import note_name
from .theory.rhythm import RhythmPattern, get_pattern, render_bar
from .theory.scales import Key
from .theory.voicing import voice_progression

#: GM 프로그램 번호 (자주 쓰는 것만)
GM_PROGRAMS = {
    "piano": 0, "acoustic_piano": 0, "bright_piano": 1, "electric_piano": 4,
    "rhodes": 4, "harpsichord": 6, "vibraphone": 11, "organ": 16, "rock_organ": 18,
    "nylon_guitar": 24, "acoustic_guitar": 25, "jazz_guitar": 26, "clean_guitar": 27,
    "muted_guitar": 28, "overdrive_guitar": 29, "distortion_guitar": 30,
    "acoustic_bass": 32, "finger_bass": 33, "pick_bass": 34, "fretless_bass": 35,
    "slap_bass": 36, "synth_bass": 38, "strings": 48, "ensemble_strings": 49,
    "synth_strings": 50, "choir": 52, "brass": 61, "sax": 65, "flute": 73,
    "square_lead": 80, "saw_lead": 81, "warm_pad": 89, "poly_synth": 90,
}


@dataclass
class Slot:
    """코드 하나가 울리는 구간."""
    chord: Chord
    start: float           # 박
    length: float          # 박
    voicing: List[int] = field(default_factory=list)

    @property
    def end(self) -> float:
        return self.start + self.length


def build_slots(
    chords: Sequence[Chord],
    beats_per_chord: float | Sequence[float] = 4.0,
) -> List[Slot]:
    """코드 목록을 시간 구간으로 배치합니다."""
    if not chords:
        raise ValueError("코드가 하나도 없습니다")
    if isinstance(beats_per_chord, (int, float)):
        lengths = [float(beats_per_chord)] * len(chords)
    else:
        lengths = [float(b) for b in beats_per_chord]
        if len(lengths) == 1:
            lengths = lengths * len(chords)
        if len(lengths) != len(chords):
            raise ValueError(
                f"beats_per_chord 개수({len(lengths)})가 코드 개수({len(chords)})와 다릅니다"
            )
    if any(l <= 0 for l in lengths):
        raise ValueError("코드 길이는 0보다 커야 합니다")

    slots: List[Slot] = []
    t = 0.0
    for chord, length in zip(chords, lengths):
        slots.append(Slot(chord=chord, start=t, length=length))
        t += length
    return slots


def _slot_at(slots: Sequence[Slot], t: float) -> Optional[Slot]:
    for s in slots:
        if s.start - 1e-6 <= t < s.end - 1e-6:
            return s
    return None


def render_chord_track(
    slots: Sequence[Slot],
    pattern: RhythmPattern,
    *,
    velocity: int = 90,
    swing: Optional[float] = None,
    accent: float = 1.06,
    duration_scale: float = 1.0,
    let_ring: bool = False,
    tempo: float = 120.0,
    channel: int = 0,
    seed: Optional[int] = None,
    ppq: int = 480,
) -> List[Note]:
    """보이싱이 채워진 슬롯들에 리듬 패턴을 입혀 노트 목록을 만듭니다."""
    rng = random.Random(seed)
    total = slots[-1].end
    step = pattern.beats_per_bar

    notes: List[Note] = []
    bar_start = 0.0
    while bar_start < total - 1e-6:
        remaining = total - bar_start
        events = render_bar(
            pattern,
            [0],                      # 음높이는 뒤에서 슬롯별로 교체
            bar_start=bar_start,
            velocity=velocity,
            swing=swing,
            accent=accent,
            duration_scale=duration_scale,
            beats_available=min(step, remaining),
            rng=rng,
            bpm=tempo,
            clamp_to_bar=not let_ring,
        )
        # 히트 시각만 뽑아 슬롯의 보이싱으로 다시 전개
        seen: List[Tuple[float, float, int]] = []
        for t, dur, _pitch, vel in events:
            seen.append((t, dur, vel))

        for t, dur, vel in seen:
            slot = _slot_at(slots, t) or _slot_at(slots, max(0.0, t - 1e-3))
            if slot is None or not slot.voicing:
                continue
            length = dur
            if not let_ring:
                length = min(length, max(0.08, slot.end - t))
            if pattern.mode == "arp":
                pitches = [_arp_pitch(slot, t, pattern)]
            else:
                pitches = slot.voicing
            for n, pitch in enumerate(pitches):
                if pattern.mode == "strum":
                    offset = n * (pattern.strum_ms / 1000.0) * (tempo / 60.0)
                else:
                    offset = 0.0
                v = max(1, min(127, vel - (n if pattern.mode != "arp" else 0)))
                notes.append(Note(
                    start=beats_to_ticks(t + offset, ppq),
                    duration=max(1, beats_to_ticks(max(0.05, length - offset), ppq)),
                    pitch=pitch,
                    velocity=v,
                    channel=channel,
                ))
        bar_start += step

    return notes


def _arp_pitch(slot: Slot, t: float, pattern: RhythmPattern) -> int:
    """아르페지오에서 이 시각에 울릴 음.

    음 순서는 **슬롯(코드) 시작 기준** 으로 셉니다. 코드가 바뀌면 아르페지오도
    처음부터 다시 시작하므로 코드 전환이 또렷하게 들립니다.
    """
    from .theory.rhythm import arp_sequence
    hits = [e[0] for e in pattern.events]
    if not hits or not slot.voicing:
        return slot.voicing[0] if slot.voicing else 60
    step = pattern.beats_per_bar or 4.0
    rel = max(0.0, t - slot.start)
    cycle = int(rel // step)
    within = rel - cycle * step
    idx = min(range(len(hits)), key=lambda i: abs(hits[i] - within))
    seq = arp_sequence(slot.voicing, pattern.arp_order, len(hits) * (cycle + 1) + 1)
    return seq[(cycle * len(hits) + idx) % len(seq)]


# --------------------------------------------------------------------------- #
# 베이스
# --------------------------------------------------------------------------- #

BASS_STYLES = {
    "root": "각 코드 근음을 코드 길이만큼 길게",
    "root_octave": "근음 + 옥타브 위 근음 번갈아 (8분)",
    "root_fifth": "근음과 5도 번갈아 (2박)",
    "eighth": "근음 8분음표 반복 (락/펑크)",
    "quarter": "근음 4분음표 반복",
    "walking": "4분음표 워킹베이스 (다음 코드로 반음/온음 접근)",
    "pump": "댄스/EDM 펌핑 (정박 짧게)",
    "syncopated": "당김이 있는 팝 베이스",
    "follow": "코드 리듬을 그대로 따라감",
}


def render_bass_track(
    slots: Sequence[Slot],
    style: str = "root",
    *,
    octave_note: int = 36,
    low: int = 28,
    high: int = 60,
    velocity: int = 100,
    tempo: float = 120.0,
    channel: int = 1,
    chord_pattern: Optional[RhythmPattern] = None,
    seed: Optional[int] = None,
    ppq: int = 480,
) -> List[Note]:
    """베이스 라인을 만듭니다. ``octave_note`` 근처 옥타브에 배치합니다."""
    if style not in BASS_STYLES:
        raise ValueError(
            f"모르는 베이스 스타일입니다: {style!r} (사용 가능: {', '.join(BASS_STYLES)})"
        )
    rng = random.Random(seed)
    notes: List[Note] = []

    def place(pc: int, near: int) -> int:
        base = near - (near % 12) + (pc % 12)
        pitch = min((base - 12, base, base + 12), key=lambda x: abs(x - near))
        while pitch < low:
            pitch += 12
        while pitch > high:
            pitch -= 12
        return pitch

    def emit(t: float, dur: float, pitch: int, vel: float) -> None:
        notes.append(Note(
            start=beats_to_ticks(max(0.0, t), ppq),
            duration=max(1, beats_to_ticks(max(0.05, dur), ppq)),
            pitch=max(low, min(high, pitch)),
            velocity=int(max(1, min(127, round(vel)))),
            channel=channel,
        ))

    for i, slot in enumerate(slots):
        root = place(slot.chord.bass_pc, octave_note)
        fifth_iv = slot.chord.interval_of(5) or 7
        # 5도는 근음 **위** 로 잡습니다. 아래로 내리면 근음보다 낮아져
        # 베이스 라인의 화성 중심이 흔들립니다.
        fifth = root + fifth_iv
        if fifth > high:
            fifth -= 12
        nxt = slots[i + 1] if i + 1 < len(slots) else None

        if style == "root":
            emit(slot.start, slot.length * 0.98, root, velocity)
        elif style == "root_octave":
            n = max(1, int(slot.length / 0.5))
            for k in range(n):
                emit(slot.start + k * 0.5, 0.45,
                     root + (12 if k % 2 else 0), velocity * (1.0 if k % 2 == 0 else 0.82))
        elif style == "root_fifth":
            n = max(1, int(slot.length / 2))
            for k in range(n):
                emit(slot.start + k * 2, 1.9, root if k % 2 == 0 else fifth,
                     velocity * (1.0 if k % 2 == 0 else 0.88))
        elif style == "eighth":
            n = max(1, int(slot.length / 0.5))
            for k in range(n):
                emit(slot.start + k * 0.5, 0.44, root,
                     velocity * (1.0 if k % 2 == 0 else 0.8))
        elif style == "quarter":
            n = max(1, int(slot.length))
            for k in range(n):
                emit(slot.start + k, 0.92, root, velocity * (1.0 if k % 2 == 0 else 0.86))
        elif style == "pump":
            n = max(1, int(slot.length))
            for k in range(n):
                emit(slot.start + k, 0.4, root, velocity * (1.0 if k % 2 == 0 else 0.9))
        elif style == "syncopated":
            hits = [(0.0, 1.0, 1.0), (1.5, 0.5, 0.82), (2.5, 1.0, 0.92), (3.5, 0.5, 0.8)]
            for off, dur, vs in hits:
                if off < slot.length - 1e-6:
                    emit(slot.start + off, min(dur, slot.length - off), root, velocity * vs)
        elif style == "follow":
            pat = chord_pattern or get_pattern("quarter")
            for off, dur, vs in pat.events:
                if off < slot.length - 1e-6:
                    emit(slot.start + off, min(dur, slot.length - off), root, velocity * vs)
        elif style == "walking":
            n = max(1, int(round(slot.length)))
            tones = sorted({place((slot.chord.root + iv) % 12, octave_note)
                            for iv in slot.chord.intervals if iv < 12})
            for k in range(n):
                if k == 0:
                    pitch = root
                elif k == n - 1 and nxt is not None:
                    target = place(nxt.chord.bass_pc, octave_note)
                    pitch = target + rng.choice([-1, 1])       # 반음 접근
                else:
                    pitch = rng.choice(tones) if tones else root
                emit(slot.start + k, 0.92, pitch,
                     velocity * (1.0 if k % 2 == 0 else 0.88))

    return notes


# --------------------------------------------------------------------------- #
# 전체 편곡
# --------------------------------------------------------------------------- #

@dataclass
class ArrangementResult:
    midi: MidiFile
    slots: List[Slot]
    warnings: List[str] = field(default_factory=list)
    total_beats: float = 0.0
    humanize: str = "off"
    bass_humanize: str = "off"

    @property
    def total_bars(self) -> float:
        num, den = self.midi.time_signature
        return self.total_beats / (num * 4.0 / den)


def build_arrangement(
    chords: Sequence[Chord],
    *,
    key: Optional[Key] = None,
    tempo: float = 120.0,
    time_signature: Tuple[int, int] = (4, 4),
    beats_per_chord: float | Sequence[float] = None,
    repeat: int = 1,
    # 보이싱
    voicing: str = "close",
    low: int = 48,
    high: int = 84,
    max_notes: Optional[int] = None,
    add_tensions: bool = False,
    voice_leading: bool = True,
    # 리듬
    rhythm: str = "quarter",
    swing: Optional[float] = None,
    humanize: str = "off",
    humanize_amount: float = 1.0,
    bass_humanize: Optional[str] = None,
    humanize_timing_ms: Optional[float] = None,
    humanize_velocity: Optional[float] = None,
    velocity: int = 90,
    duration_scale: float = 1.0,
    let_ring: bool = False,
    # 트랙 구성
    include_chords: bool = True,
    include_bass: bool = False,
    bass_style: str = "root",
    bass_octave: int = 36,
    bass_low: int = 28,
    bass_high: int = 60,
    bass_velocity: int = 100,
    chord_program: Optional[str | int] = None,
    bass_program: Optional[str | int] = "finger_bass",
    chord_track_name: str = "Chords",
    bass_track_name: str = "Bass",
    add_markers: bool = True,
    seed: Optional[int] = None,
) -> ArrangementResult:
    """코드 진행 전체를 :class:`MidiFile` 로 편곡합니다."""
    if not chords:
        raise ValueError("코드가 하나도 없습니다")
    if repeat < 1:
        raise ValueError("repeat 는 1 이상이어야 합니다")
    if tempo <= 0:
        raise ValueError("tempo 는 0보다 커야 합니다")

    warnings: List[str] = []
    pattern = get_pattern(rhythm)
    num, den = time_signature
    bar_beats = num * 4.0 / den

    if beats_per_chord is None:
        beats_per_chord = bar_beats
    if isinstance(beats_per_chord, (int, float)) and abs(pattern.beats_per_bar - bar_beats) > 1e-6:
        warnings.append(
            f"리듬 패턴 '{pattern.name}' 는 {pattern.beats_per_bar:g}박 기준인데 "
            f"박자표는 {num}/{den}({bar_beats:g}박)입니다. 패턴은 "
            f"{pattern.beats_per_bar:g}박마다 반복됩니다."
        )

    chord_profile = _humanize_profile(humanize, humanize_timing_ms, humanize_velocity)
    bass_profile = _bass_humanize_profile(bass_humanize, chord_profile)
    if not 0.0 <= humanize_amount <= 1.0:
        raise ValueError("humanize_amount 는 0.0 ~ 1.0 사이여야 합니다")

    chord_list = list(chords) * repeat
    slots = build_slots(chord_list, beats_per_chord)

    voicings = voice_progression(
        [s.chord for s in slots],
        style=voicing,
        low=low,
        high=high,
        max_notes=max_notes,
        voice_leading=voice_leading,
        add_tensions=add_tensions,
    )
    for slot, v in zip(slots, voicings):
        slot.voicing = v

    mf = MidiFile(tempo=tempo, time_signature=time_signature)
    if key is not None:
        mf.key_signature = _key_signature(key)

    if include_chords:
        track = Track(name=chord_track_name, channel=0,
                      program=_program(chord_program))
        track.notes = render_chord_track(
            slots, pattern, velocity=velocity, swing=swing,
            duration_scale=duration_scale, let_ring=let_ring,
            tempo=tempo, channel=0, seed=seed,
        )
        track.notes = humanize_notes(
            track.notes, chord_profile, tempo=tempo, ppq=480,
            time_signature=time_signature, seed=seed, amount=humanize_amount,
        )
        if add_markers:
            track.markers = [(beats_to_ticks(s.start), s.chord.symbol) for s in slots]
        mf.add_track(track)

    if include_bass:
        bass = Track(name=bass_track_name, channel=1, program=_program(bass_program))
        bass.notes = render_bass_track(
            slots, bass_style, octave_note=bass_octave, low=bass_low, high=bass_high,
            velocity=bass_velocity, tempo=tempo, channel=1, chord_pattern=pattern,
            seed=None if seed is None else seed + 1,
        )
        bass.notes = humanize_notes(
            bass.notes, bass_profile, tempo=tempo, ppq=480,
            time_signature=time_signature,
            seed=None if seed is None else seed + 1, amount=humanize_amount,
        )
        mf.add_track(bass)

    if not mf.tracks:
        raise ValueError("트랙을 하나도 만들지 않았습니다 (include_chords/include_bass 확인)")

    if chord_profile.push_pull_ms < 0:
        warnings.append(
            "푸시(앞으로 미는) 프로파일이라 첫 박은 프로젝트 시작보다 앞으로 갈 수 없어 "
            "그리드에 붙습니다. 앞에 한 마디를 비워 두면 첫 박도 같은 느낌이 납니다."
        )

    return ArrangementResult(midi=mf, slots=slots, warnings=warnings,
                             total_beats=slots[-1].end,
                             humanize=chord_profile.name,
                             bass_humanize=bass_profile.name)


def _humanize_profile(name: str, timing_ms: Optional[float],
                      velocity_jitter: Optional[float]) -> HumanizeProfile:
    """프로파일 이름과 수동 오버라이드를 하나의 프로파일로 합칩니다."""
    if timing_ms is None and velocity_jitter is None:
        return get_profile(name)
    # 숫자를 직접 준 경우: 프로파일 위에 그 값만 덮어씁니다.
    base = name if name and name != "off" else "subtle"
    return customize(base, timing_jitter_ms=timing_ms, velocity_jitter=velocity_jitter)


def _bass_humanize_profile(name: Optional[str],
                           chord_profile: HumanizeProfile) -> HumanizeProfile:
    """베이스용 프로파일. 지정하지 않으면 코드 트랙의 느낌에 맞춰 고릅니다."""
    if name:
        return get_profile(name)
    if chord_profile.name == "off":
        return get_profile("off")
    # 코드가 뒤로 끄는 느낌이면 베이스도 같이 끌어야 그루브가 맞습니다.
    return get_profile("bass_laid_back" if chord_profile.push_pull_ms >= 10
                       else "bass_tight")


def _program(value: Optional[str | int]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        if not 0 <= value <= 127:
            raise ValueError(f"GM 프로그램 번호는 0~127 이어야 합니다: {value}")
        return value
    key = str(value).lower().replace(" ", "_")
    if key not in GM_PROGRAMS:
        raise ValueError(
            f"모르는 악기 이름입니다: {value!r} (사용 가능: {', '.join(sorted(GM_PROGRAMS))})"
        )
    return GM_PROGRAMS[key]


#: 5도권 상의 장조 으뜸음 -> 조표의 샾(+)/플랫(-) 수
_SHARPS_FOR_MAJOR = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 1: -5, 8: -4, 3: -3, 10: -2, 5: -1}


def _key_signature(key: Key) -> Tuple[int, int]:
    minor = key.harmony_mode != "major"
    rel_major = (key.tonic + 3) % 12 if minor else key.tonic
    return _SHARPS_FOR_MAJOR.get(rel_major, 0), 1 if minor else 0
