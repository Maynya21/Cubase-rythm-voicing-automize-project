"""MIDI 작성 / 편곡 렌더링 테스트.

생성한 파일은 `tests.smf_reader` 의 독립 파서로 다시 읽어 검증합니다.
"""

import unittest

from cubase_mcp.midi.smf import (MidiError, MidiFile, Note, Track, beats_to_ticks,
                                 render, resolve_overlaps, _varlen)
from cubase_mcp.render import (BASS_STYLES, build_arrangement, build_slots,
                               render_bass_track)
from cubase_mcp.theory.chords import parse_progression
from cubase_mcp.theory.rhythm import RHYTHM_PATTERNS
from cubase_mcp.theory.scales import parse_key
from cubase_mcp.theory.voicing import VOICING_STYLES

from .smf_reader import parse


def _read_varlen(data, i=0):
    value = 0
    while True:
        byte = data[i]; i += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value


class TestSMF(unittest.TestCase):
    def test_varlen_roundtrip(self):
        for value in [0, 1, 127, 128, 255, 8192, 16383, 16384, 1048575, 0x0FFFFFFF]:
            self.assertEqual(_read_varlen(_varlen(value)), value)

    def test_header_and_conductor(self):
        mf = MidiFile(tempo=96.0, time_signature=(3, 4), key_signature=(-3, 1))
        mf.add_track(Track(name="T", notes=[Note(0, 480, 60)]))
        parsed = parse(render(mf))
        self.assertEqual(parsed.fmt, 1)
        self.assertEqual(parsed.ppq, 480)
        self.assertEqual(len(parsed.tracks), 2)          # 컨덕터 + 1
        self.assertAlmostEqual(parsed.tracks[0]["tempo"], 96.0, places=3)
        self.assertEqual(parsed.tracks[0]["time_signature"], (3, 4))
        self.assertEqual(parsed.tracks[0]["key_signature"], (-3, 1))

    def test_notes_roundtrip(self):
        mf = MidiFile()
        mf.add_track(Track(name="Chords", program=4, notes=[
            Note(0, 480, 60, 90), Note(0, 480, 64, 88), Note(480, 960, 67, 70),
        ]))
        parsed = parse(render(mf))
        self.assertEqual(len(parsed.notes), 3)
        self.assertEqual(parsed.tracks[1]["name"], "Chords")
        self.assertEqual(parsed.tracks[1]["programs"], [(0, 4)])
        by_pitch = {n.pitch: n for n in parsed.notes}
        self.assertEqual((by_pitch[67].start, by_pitch[67].duration), (480, 960))
        self.assertEqual(by_pitch[60].velocity, 90)

    def test_repeated_same_pitch_does_not_hang(self):
        """같은 음이 연달아 나와도 note off 가 먼저 나가 음이 끊기지 않게 유지됩니다."""
        mf = MidiFile()
        mf.add_track(Track(notes=[Note(i * 480, 480, 60) for i in range(8)]))
        parsed = parse(render(mf))                       # 파서가 짝을 검사합니다
        self.assertEqual(len(parsed.notes), 8)

    def test_overlapping_same_pitch_is_clipped(self):
        """같은 음이 겹치면 앞 노트를 다음 노트 직전까지 줄입니다."""
        notes = [Note(0, 1920, 60), Note(480, 480, 60)]
        out = resolve_overlaps(notes)
        self.assertEqual([(n.start, n.duration) for n in out], [(0, 480), (480, 480)])

    def test_exact_duplicate_note_is_dropped(self):
        out = resolve_overlaps([Note(0, 480, 60), Note(0, 960, 60)])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].duration, 960)          # 더 긴 쪽을 남깁니다

    def test_different_pitches_may_overlap(self):
        out = resolve_overlaps([Note(0, 1920, 60), Note(480, 480, 64)])
        self.assertEqual(sorted(n.duration for n in out), [480, 1920])

    def test_different_channels_may_overlap(self):
        out = resolve_overlaps([Note(0, 1920, 60, channel=0),
                                Note(480, 480, 60, channel=1)])
        self.assertEqual(sorted(n.duration for n in out), [480, 1920])

    def test_resolve_overlaps_does_not_mutate_input(self):
        original = Note(0, 1920, 60)
        resolve_overlaps([original, Note(480, 480, 60)])
        self.assertEqual(original.duration, 1920)

    def test_markers(self):
        mf = MidiFile()
        mf.add_track(Track(name="T", notes=[Note(0, 480, 60)],
                           markers=[(0, "Cmaj7"), (1920, "G7")]))
        self.assertEqual(parse(render(mf)).tracks[1]["markers"],
                         [(0, "Cmaj7"), (1920, "G7")])

    def test_rejects_invalid_values(self):
        with self.assertRaises(MidiError):
            Note(0, 480, 200)
        with self.assertRaises(MidiError):
            Note(0, 480, 60, velocity=0)
        with self.assertRaises(MidiError):
            Note(0, 480, 60, channel=99)
        with self.assertRaises(MidiError):
            render(MidiFile())
        with self.assertRaises(MidiError):
            render(MidiFile(tempo=0, tracks=[Track(notes=[Note(0, 1, 60)])]))

    def test_beats_to_ticks(self):
        self.assertEqual(beats_to_ticks(1), 480)
        self.assertEqual(beats_to_ticks(0.5), 240)
        self.assertEqual(beats_to_ticks(1.5), 720)


class TestArrangement(unittest.TestCase):
    PROG = parse_progression("Cmaj7 Am7 Dm7 G7")

    def test_default_layout_is_one_bar_per_chord(self):
        result = build_arrangement(self.PROG)
        self.assertEqual(result.total_beats, 16.0)
        self.assertEqual(result.total_bars, 4.0)

    def test_two_chords_per_bar_split_the_pattern(self):
        """한 마디에 코드가 둘이면 앞 코드는 패턴 앞부분, 뒤 코드는 뒷부분을 받습니다."""
        result = build_arrangement(self.PROG, rhythm="quarter", beats_per_chord=2,
                                   voicing="close")
        parsed = parse(render(result.midi))
        starts = sorted({n.start / 480 for n in parsed.notes})
        self.assertEqual(starts, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        # 2박(=Am7 구간)에 울리는 음은 Am7 구성음이어야 합니다
        at_beat2 = {n.pitch % 12 for n in parsed.notes if n.start == 960}
        self.assertTrue(at_beat2 <= {9, 0, 4, 7}, at_beat2)

    def test_notes_do_not_cross_chord_boundaries(self):
        result = build_arrangement(self.PROG, rhythm="whole", let_ring=False)
        for slot in result.slots:
            pass
        parsed = parse(render(result.midi))
        for note in parsed.notes:
            bar = note.start // 1920
            self.assertLessEqual(note.start + note.duration, (bar + 1) * 1920 + 1)

    def test_let_ring_allows_overlap(self):
        long_pattern = build_arrangement(self.PROG, rhythm="whole", let_ring=True,
                                         duration_scale=2.0)
        parsed = parse(render(long_pattern.midi))
        self.assertTrue(any(n.duration > 1920 for n in parsed.notes))

    def test_every_voicing_and_rhythm_combination_renders(self):
        for voicing in VOICING_STYLES:
            for rhythm in RHYTHM_PATTERNS:
                with self.subTest(voicing=voicing, rhythm=rhythm):
                    result = build_arrangement(self.PROG, voicing=voicing, rhythm=rhythm)
                    parsed = parse(render(result.midi))   # 유효성 검사 포함
                    self.assertTrue(parsed.notes, "노트가 하나도 없습니다")

    def test_bass_track_stays_in_bass_range(self):
        for style in BASS_STYLES:
            with self.subTest(style=style):
                result = build_arrangement(self.PROG, include_chords=False,
                                           include_bass=True, bass_style=style, seed=1)
                parsed = parse(render(result.midi))
                self.assertTrue(parsed.notes)
                for note in parsed.notes:
                    self.assertTrue(28 <= note.pitch <= 60,
                                    f"{style}: {note.pitch} 가 베이스 음역 밖입니다")
                    self.assertEqual(note.channel, 1)

    def test_markers_carry_chord_symbols(self):
        result = build_arrangement(self.PROG, add_markers=True)
        markers = parse(render(result.midi)).tracks[1]["markers"]
        self.assertEqual([m[1] for m in markers], ["Cmaj7", "Am7", "Dm7", "G7"])

    def test_key_signature_written(self):
        for key, expected in [("C", (0, 0)), ("Am", (0, 1)), ("Eb", (-3, 0)),
                              ("F# minor", (3, 1))]:
            with self.subTest(key=key):
                result = build_arrangement(self.PROG, key=parse_key(key))
                self.assertEqual(parse(render(result.midi)).tracks[0]["key_signature"],
                                 expected)

    def test_repeat_multiplies_length(self):
        result = build_arrangement(self.PROG, repeat=3)
        self.assertEqual(result.total_beats, 48.0)

    def test_time_signature_mismatch_warns(self):
        result = build_arrangement(self.PROG, rhythm="waltz", time_signature=(4, 4))
        self.assertTrue(result.warnings)

    def test_humanize_is_reproducible_with_seed(self):
        a = render(build_arrangement(self.PROG, humanize_timing_ms=15,
                                     humanize_velocity=8, seed=7).midi)
        b = render(build_arrangement(self.PROG, humanize_timing_ms=15,
                                     humanize_velocity=8, seed=7).midi)
        self.assertEqual(a, b)

    def test_humanize_never_produces_negative_time(self):
        result = build_arrangement(self.PROG, humanize_timing_ms=200, seed=2)
        for note in parse(render(result.midi)).notes:
            self.assertGreaterEqual(note.start, 0)

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            build_arrangement([])
        with self.assertRaises(ValueError):
            build_arrangement(self.PROG, repeat=0)
        with self.assertRaises(ValueError):
            build_arrangement(self.PROG, tempo=0)
        with self.assertRaises(ValueError):
            build_arrangement(self.PROG, beats_per_chord=[1, 2])   # 개수 불일치
        with self.assertRaises(ValueError):
            build_arrangement(self.PROG, include_chords=False, include_bass=False)
        with self.assertRaises(ValueError):
            build_arrangement(self.PROG, bass_style="nope", include_bass=True)

    def test_per_chord_durations(self):
        result = build_arrangement(self.PROG, beats_per_chord=[2, 2, 4, 8])
        self.assertEqual([s.length for s in result.slots], [2, 2, 4, 8])
        self.assertEqual(result.total_beats, 16)

    def test_slots_are_contiguous(self):
        slots = build_slots(self.PROG, [1.5, 2.5, 4, 8])
        for a, b in zip(slots, slots[1:]):
            self.assertAlmostEqual(a.end, b.start)


if __name__ == "__main__":
    unittest.main()
