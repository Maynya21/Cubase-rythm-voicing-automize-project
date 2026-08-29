"""음악 이론 계층 테스트 (표준 라이브러리만 사용)."""

import unittest

from cubase_mcp.theory.chords import ChordError, parse_chord, parse_progression
from cubase_mcp.theory.notes import NoteError, note_name, parse_note
from cubase_mcp.theory.progression import from_template, generate, reharmonize
from cubase_mcp.theory.rhythm import RHYTHM_PATTERNS, arp_sequence, get_pattern, render_bar
from cubase_mcp.theory.scales import diatonic_chords, parse_key, parse_roman, roman_of
from cubase_mcp.theory.voicing import (VOICING_STYLES, voice_chord, voice_progression,
                                       voicing_movement)


class TestNotes(unittest.TestCase):
    def test_cubase_middle_c(self):
        """Cubase 기본 표기는 C3 = 60, A3 = 69(A440)."""
        self.assertEqual(parse_note("C3"), 60)
        self.assertEqual(parse_note("A3"), 69)
        self.assertEqual(note_name(60), "C3")

    def test_scientific_octave_option(self):
        self.assertEqual(parse_note("C4", middle_c_octave=4), 60)
        self.assertEqual(note_name(60, middle_c_octave=4), "C4")

    def test_accidentals(self):
        self.assertEqual(parse_note("F#3") - parse_note("F3"), 1)
        self.assertEqual(parse_note("Bb3") - parse_note("B3"), -1)
        self.assertEqual(parse_note("Cx3") - parse_note("C3"), 2)

    def test_roundtrip(self):
        for midi in range(12, 116):
            self.assertEqual(parse_note(note_name(midi)), midi)

    def test_rejects_garbage(self):
        for bad in ["H3", "", "C##b#x?", "Z"]:
            with self.assertRaises(NoteError):
                parse_note(bad)


class TestChords(unittest.TestCase):
    CASES = {
        "C": [0, 4, 7], "Cm": [0, 3, 7], "Cdim": [0, 3, 6], "Caug": [0, 4, 8],
        "C7": [0, 4, 7, 10], "Cmaj7": [0, 4, 7, 11], "Cm7": [0, 3, 7, 10],
        "Cm7b5": [0, 3, 6, 10], "Cdim7": [0, 3, 6, 9], "CmMaj7": [0, 3, 7, 11],
        "C6": [0, 4, 7, 9], "Cm6": [0, 3, 7, 9], "C69": [0, 4, 7, 9, 14],
        "C9": [0, 4, 7, 10, 14], "Cmaj9": [0, 4, 7, 11, 14],
        "C13": [0, 4, 7, 10, 14, 21], "Csus4": [0, 5, 7], "Csus2": [0, 2, 7],
        "C7sus4": [0, 5, 7, 10], "Cadd9": [0, 4, 7, 14], "C5": [0, 7],
        "C7b9": [0, 4, 7, 10, 13], "C7#9": [0, 4, 7, 10, 15],
        "C7#11": [0, 4, 7, 10, 18], "C7b13": [0, 4, 7, 10, 20],
        "C7alt": [0, 4, 10, 13, 15, 20],
    }

    def test_qualities(self):
        for symbol, expected in self.CASES.items():
            with self.subTest(symbol=symbol):
                self.assertEqual(parse_chord(symbol).intervals, expected)

    def test_unicode_and_alt_spellings(self):
        self.assertEqual(parse_chord("CΔ").intervals, parse_chord("Cmaj7").intervals)
        self.assertEqual(parse_chord("Cø").intervals, parse_chord("Cm7b5").intervals)
        self.assertEqual(parse_chord("C-7").intervals, parse_chord("Cm7").intervals)
        self.assertEqual(parse_chord("C-9").intervals, parse_chord("Cm9").intervals)
        self.assertEqual(parse_chord("C+").intervals, parse_chord("Caug").intervals)
        self.assertEqual(parse_chord("C6/9").intervals, parse_chord("C69").intervals)
        self.assertEqual(parse_chord("C7(9,13)").intervals, parse_chord("C13").intervals)

    def test_thirteenth_keeps_the_third(self):
        """13화음은 11음을 생략하지만 3음은 반드시 남습니다."""
        self.assertIn(4, parse_chord("C13").intervals)
        self.assertNotIn(17, parse_chord("C13").intervals)

    def test_eleventh_drops_major_third(self):
        self.assertNotIn(4, parse_chord("C11").intervals)
        self.assertIn(3, parse_chord("Cm11").intervals)

    def test_slash_bass(self):
        chord = parse_chord("Am/C")
        self.assertEqual(chord.root, 9)
        self.assertEqual(chord.bass, 0)
        self.assertEqual(chord.bass_pc, 0)

    def test_triad_quality_uses_actual_notes(self):
        """Cm7b5 는 파싱상 minor 로 시작하지만 실제로는 dim 입니다."""
        self.assertEqual(parse_chord("Cm7b5").triad_quality, "dim")
        self.assertEqual(parse_chord("Cdim7").triad_quality, "dim")
        self.assertEqual(parse_chord("Caug").triad_quality, "aug")
        self.assertEqual(parse_chord("Csus4").triad_quality, "sus4")

    def test_rejects_typos(self):
        for bad in ["Cxyz", "H7", "", "Cmaj77x"]:
            with self.assertRaises(ChordError):
                parse_chord(bad)

    def test_progression_separators_and_repeat(self):
        chords = parse_progression("Cmaj7 | Am7, Dm7  G7 | %")
        self.assertEqual([c.symbol for c in chords],
                         ["Cmaj7", "Am7", "Dm7", "G7", "G7"])
        self.assertEqual(len(parse_progression(["C", "F"])), 2)


class TestScales(unittest.TestCase):
    def test_diatonic_major(self):
        self.assertEqual([c.symbol for c in diatonic_chords(parse_key("C"))],
                         ["Cmaj7", "Dm7", "Em7", "Fmaj7", "G7", "Am7", "Bm7b5"])

    def test_diatonic_minor(self):
        self.assertEqual([c.symbol for c in diatonic_chords(parse_key("Am"))],
                         ["Am7", "Bm7b5", "Cmaj7", "Dm7", "Em7", "Fmaj7", "G7"])

    def test_roman_basics(self):
        key = parse_key("C")
        self.assertEqual(parse_roman("V7", key).symbol, "G7")
        self.assertEqual(parse_roman("vi", key).symbol, "Am")
        self.assertEqual(parse_roman("IVmaj7", key).symbol, "Fmaj7")

    def test_altered_romans_measure_from_parallel_major(self):
        """단조에서도 bVII 은 장음계 7음을 내린 음(= 자연단음계의 VII)입니다."""
        self.assertEqual(parse_roman("bVII", parse_key("C")).symbol, "Bb")
        self.assertEqual(parse_roman("bVII", parse_key("Am")).symbol, "G")
        self.assertEqual(parse_roman("bVI", parse_key("Am")).symbol, "F")
        self.assertEqual(parse_roman("bIII", parse_key("C")).symbol, "Eb")

    def test_secondary_dominant(self):
        key = parse_key("C")
        self.assertEqual(parse_roman("V/V", key).symbol, "D")
        self.assertEqual(parse_roman("V7/ii", key).symbol, "A7")

    def test_half_diminished_suffix(self):
        self.assertEqual(parse_roman("iiø7", parse_key("C")).intervals, [0, 3, 6, 10])

    def test_roman_of_labels(self):
        key = parse_key("C")
        labels = [roman_of(parse_chord(s), key)
                  for s in ["Cmaj7", "Am7", "G7", "Bm7b5", "Bb", "Cdim7"]]
        self.assertEqual(labels, ["Imaj7", "vi7", "V7", "viiø7", "bVII", "i°7"])


class TestVoicing(unittest.TestCase):
    PROG = parse_progression("Cmaj7 Am7 Dm7 G7")

    def test_every_style_produces_notes_in_range(self):
        for style in VOICING_STYLES:
            with self.subTest(style=style):
                voicings = voice_progression(self.PROG, style=style, low=40, high=88)
                self.assertEqual(len(voicings), 4)
                for v in voicings:
                    self.assertTrue(v, f"{style} 이 빈 보이싱을 냈습니다")
                    self.assertTrue(all(0 <= p <= 127 for p in v))
                    self.assertEqual(sorted(v), v, "보이싱은 오름차순이어야 합니다")
                    self.assertEqual(len(set(v)), len(v), "중복 음이 있습니다")

    def test_voicings_contain_chord_tones_only(self):
        """텐션 추가를 끄면 코드에 없는 음이 생기면 안 됩니다."""
        skip = {"quartal", "cluster"}          # 이 둘은 의도적으로 텐션을 씁니다
        for style in VOICING_STYLES:
            if style in skip:
                continue
            for chord in self.PROG:
                with self.subTest(style=style, chord=chord.symbol):
                    v = voice_chord(chord, style=style)
                    allowed = set(chord.pitch_classes) | {chord.bass_pc}
                    if style in ("rootless_a", "rootless_b"):
                        allowed.add((chord.root + 14) % 12)   # 9음을 대체음으로 씀
                    self.assertTrue(set(p % 12 for p in v) <= allowed,
                                    f"{style}/{chord.symbol}: 코드 밖 음 발생")

    def test_voice_leading_reduces_movement(self):
        smooth = voicing_movement(voice_progression(self.PROG, "close", voice_leading=True))
        blunt = voicing_movement(voice_progression(self.PROG, "close", voice_leading=False))
        self.assertLess(smooth, blunt)

    def test_max_notes_is_respected(self):
        for n in (3, 4, 5):
            for v in voice_progression(self.PROG, "close", max_notes=n):
                self.assertLessEqual(len(v), n)

    def test_slash_chord_puts_bass_lowest(self):
        v = voice_chord(parse_chord("C/E"), style="close")
        self.assertEqual(v[0] % 12, 4)

    def test_unknown_style_is_rejected(self):
        with self.assertRaises(ValueError):
            voice_chord(parse_chord("C"), style="nope")


class TestRhythm(unittest.TestCase):
    def test_all_patterns_stay_inside_the_bar(self):
        for name, pattern in RHYTHM_PATTERNS.items():
            with self.subTest(pattern=name):
                self.assertTrue(pattern.events, "빈 패턴")
                for start, dur, vel in pattern.events:
                    self.assertGreaterEqual(start, 0)
                    self.assertLess(start, pattern.beats_per_bar)
                    self.assertGreater(dur, 0)
                    self.assertTrue(0 < vel <= 1.0)

    def test_render_produces_valid_notes(self):
        voicing = [60, 64, 67, 71]
        # 아르페지오 순서 중 up_inclusive 는 맨 위에 옥타브 위 근음을 더하므로
        # 음높이 자체가 아니라 피치 클래스로 확인합니다.
        allowed = {p % 12 for p in voicing}
        for name, pattern in RHYTHM_PATTERNS.items():
            with self.subTest(pattern=name):
                events = render_bar(pattern, voicing, velocity=90)
                self.assertTrue(events)
                for start, dur, pitch, vel in events:
                    self.assertGreaterEqual(start, 0)
                    self.assertGreater(dur, 0)
                    self.assertTrue(1 <= vel <= 127)
                    self.assertIn(pitch % 12, allowed)
                    self.assertTrue(0 <= pitch <= 127)

    def test_up_inclusive_adds_the_octave(self):
        self.assertEqual(arp_sequence([60, 64, 67], "up_inclusive", 4), [60, 64, 67, 72])

    def test_half_bar_truncation(self):
        events = render_bar(get_pattern("quarter"), [60], beats_available=2)
        self.assertEqual([e[0] for e in events], [0.0, 1.0])

    def test_swing_delays_offbeats(self):
        straight = render_bar(get_pattern("eighth"), [60], swing=0.0)
        swung = render_bar(get_pattern("eighth"), [60], swing=0.66)
        self.assertEqual(straight[1][0], 0.5)
        self.assertGreater(swung[1][0], 0.5)
        self.assertEqual(swung[0][0], 0.0, "정박은 밀리면 안 됩니다")

    def test_arp_orders(self):
        p = [60, 64, 67, 71]
        self.assertEqual(arp_sequence(p, "up", 4), p)
        self.assertEqual(arp_sequence(p, "down", 4), p[::-1])
        self.assertEqual(arp_sequence(p, "updown", 6), [60, 64, 67, 71, 67, 64])
        self.assertEqual(arp_sequence(p, "alberti", 4), [60, 71, 67, 71])
        self.assertEqual(arp_sequence([], "up", 4), [])

    def test_unknown_pattern_is_rejected(self):
        with self.assertRaises(ValueError):
            get_pattern("nope")


class TestProgression(unittest.TestCase):
    def test_template_in_major(self):
        self.assertEqual(from_template("axis", "C").symbols, ["C", "G", "Am", "F"])

    def test_major_template_in_minor_key_uses_relative(self):
        """장조 템플릿을 단조 키에 쓰면 나란한조로 해석해 다이어토닉을 유지합니다."""
        p = from_template("axis", "Am")
        self.assertEqual(p.symbols, ["C", "G", "Am", "F"])
        self.assertIsNotNone(p.adapted_note)

    def test_minor_template_in_major_key_uses_relative(self):
        self.assertEqual(from_template("minor_axis", "C").symbols, ["Am", "F", "C", "G"])

    def test_adapt_none_and_parallel(self):
        self.assertEqual(from_template("axis", "Am", adapt="parallel").symbols,
                         ["A", "E", "F#m", "D"])
        self.assertIsNone(from_template("axis", "C").adapted_note)

    def test_bars_tiling_and_truncation(self):
        self.assertEqual(len(from_template("axis", "C", bars=8).chords), 8)
        self.assertEqual(len(from_template("canon", "C", bars=3).chords), 3)

    def test_generate_is_deterministic_with_seed(self):
        a = generate("C", "pop", 4, seed=11).symbols
        b = generate("C", "pop", 4, seed=11).symbols
        self.assertEqual(a, b)

    def test_generate_rejects_unknown_genre(self):
        with self.assertRaises(ValueError):
            generate("C", "polka")

    def test_reharmonize_adds_sevenths(self):
        out = reharmonize(parse_progression("C Am F G"), "C",
                          moves=("sevenths",), strength=1.0, seed=1)
        self.assertEqual([c.symbol for c in out], ["Cmaj7", "Am7", "Fmaj7", "G7"])

    def test_tritone_sub_moves_root_by_six_semitones(self):
        out = reharmonize(parse_progression("G7"), "C",
                          moves=("tritone",), strength=1.0, seed=1)
        self.assertEqual(out[0].root, (parse_chord("G7").root + 6) % 12)

    def test_reharmonize_rejects_unknown_move(self):
        with self.assertRaises(ValueError):
            reharmonize(parse_progression("C"), "C", moves=("magic",))


if __name__ == "__main__":
    unittest.main()
