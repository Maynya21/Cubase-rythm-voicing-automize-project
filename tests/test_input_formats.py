"""입력 방식 테스트 — 도수(로마숫자) 코드 입력과 리듬 그리드 표기법."""

import unittest

from cubase_mcp.theory.chords import ChordError
from cubase_mcp.theory.rhythm import (RHYTHM_PATTERNS, looks_like_grid, parse_grid,
                                      resolve_pattern)
from cubase_mcp.theory.scales import (is_roman_token, parse_chords, parse_key,
                                      split_key_prefix)


class TestChordInput(unittest.TestCase):
    def symbols(self, text, key=None):
        chords, _key, _roman = parse_chords(text, key)
        return [c.symbol for c in chords]

    # ---- 도수 입력 --------------------------------------------------------
    def test_key_prefix_form(self):
        """사용자가 요청한 'C; I-V-ii' 형식."""
        self.assertEqual(self.symbols("C; I-V-ii"), ["C", "G", "Dm"])
        self.assertEqual(self.symbols("C; I-V-vi-IV"), ["C", "G", "Am", "F"])

    def test_key_argument_form(self):
        self.assertEqual(self.symbols("I V vi IV", "C"), ["C", "G", "Am", "F"])

    def test_minor_key_degrees(self):
        self.assertEqual(self.symbols("Am; i-bVI-bVII-V"), ["Am", "F", "G", "E"])

    def test_sevenths_and_secondary(self):
        self.assertEqual(self.symbols("F; ii7-V7-Imaj7"), ["Gm7", "C7", "Fmaj7"])
        self.assertEqual(self.symbols("C; V7/ii"), ["A7"])
        self.assertEqual(self.symbols("C; iiø7"), ["Dm7b5"])

    def test_prefix_key_wins_over_argument(self):
        self.assertEqual(self.symbols("Eb; I-V", key="C"), ["Eb", "Bb"])

    def test_colon_also_works(self):
        self.assertEqual(self.symbols("C: I-V"), ["C", "G"])

    def test_repeat_marker(self):
        self.assertEqual(self.symbols("C; I-%-V-%"), ["C", "C", "G", "G"])

    # ---- 심볼 입력이 깨지지 않아야 함 --------------------------------------
    def test_plain_symbols_still_work(self):
        self.assertEqual(self.symbols("Cmaj7 | Am7 | Dm7 | G7"),
                         ["Cmaj7", "Am7", "Dm7", "G7"])

    def test_hyphen_minor_notation_is_not_split(self):
        """``C-7`` 은 Cm7 입니다. 하이픈을 구분자로 오해하면 안 됩니다."""
        self.assertEqual(self.symbols("C-7 F-9 Bb7"), ["C-7", "F-9", "Bb7"])
        chords, _, roman = parse_chords("C-7 F-9")
        self.assertFalse(roman)
        self.assertEqual(chords[0].intervals, [0, 3, 7, 10])

    def test_flat_root_is_not_mistaken_for_a_degree(self):
        self.assertEqual(self.symbols("Bb Eb Ab"), ["Bb", "Eb", "Ab"])

    def test_mixed_input(self):
        self.assertEqual(self.symbols("I V Am7 IV", "C"), ["C", "G", "Am7", "F"])

    # ---- 판별 / 오류 ------------------------------------------------------
    def test_is_roman_token(self):
        for token in ["I", "ii", "V7", "bVII", "#iv", "iiø7", "V7/ii"]:
            self.assertTrue(is_roman_token(token), token)
        for token in ["C", "Am7", "Bb", "F#m7b5", "C-7", "b"]:
            self.assertFalse(is_roman_token(token), token)

    def test_degrees_without_a_key_are_rejected(self):
        with self.assertRaises(ChordError) as ctx:
            parse_chords("I V vi")
        self.assertIn("조성", str(ctx.exception))

    def test_split_key_prefix(self):
        key, rest = split_key_prefix("Am; i-iv-V")
        self.assertEqual(key.tonic, parse_key("Am").tonic)
        self.assertEqual(rest, "i-iv-V")
        self.assertEqual(split_key_prefix("Cmaj7 Am7"), (None, "Cmaj7 Am7"))

    def test_empty_input_is_rejected(self):
        with self.assertRaises(ChordError):
            parse_chords("")


class TestRhythmGrid(unittest.TestCase):
    def starts(self, text, **kw):
        return [round(e[0], 6) for e in parse_grid(text, **kw).events]

    def lengths(self, text, **kw):
        return [round(e[1], 6) for e in parse_grid(text, **kw).events]

    # ---- 기본 -------------------------------------------------------------
    def test_cell_count_sets_the_subdivision(self):
        self.assertEqual(self.starts("x-x-"), [0.0, 2.0])          # 4칸 = 4분음표
        self.assertEqual(self.starts("x-x-x-x-"), [0, 1, 2, 3])    # 8칸 = 8분음표
        self.assertEqual(self.starts("x-x-x-x-x-x-x-x-"),
                         [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5])         # 16칸 = 16분음표

    def test_tie_extends_the_note(self):
        self.assertEqual(self.lengths("x~~~"), [4.0])
        self.assertEqual(self.lengths("X~~-x~~-"), [1.5, 1.5])

    def test_rest_cuts_the_note(self):
        self.assertEqual(self.lengths("x---"), [1.0])

    def test_syncopation(self):
        self.assertEqual(self.starts("x--x--x-"), [0.0, 1.5, 3.0])

    def test_accent_and_ghost_velocities(self):
        events = parse_grid("X-o-x-o-").events
        self.assertEqual([round(e[2], 2) for e in events], [1.0, 0.55, 0.82, 0.55])

    def test_whitespace_is_ignored(self):
        self.assertEqual(self.starts("x - x -   x - x -"), self.starts("x-x-x-x-"))

    def test_multiple_bars(self):
        pattern = parse_grid("x-x-|x-x-x-x-")
        self.assertEqual(pattern.beats_per_bar, 8.0)
        self.assertEqual([round(e[0], 4) for e in pattern.events],
                         [0.0, 2.0, 4.0, 5.0, 6.0, 7.0])

    def test_triplets(self):
        self.assertEqual(len(parse_grid("x--x--x--x--").events), 4)

    def test_other_time_signatures(self):
        self.assertEqual(self.starts("x-x-x-", beats_per_bar=3), [0.0, 1.0, 2.0])
        self.assertEqual(self.starts("xxx", beats_per_bar=3), [0.0, 1.0, 2.0])

    # ---- 검증 -------------------------------------------------------------
    def test_bad_cell_count_is_rejected(self):
        """칸을 빠뜨리면 9잇단음표 같은 게 조용히 나오면 안 됩니다."""
        with self.assertRaises(ValueError) as ctx:
            parse_grid("X--x-X--x")
        self.assertIn("칸", str(ctx.exception))
        self.assertIn("8", str(ctx.exception))

    def test_unknown_symbol_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            parse_grid("x-q-")
        self.assertIn("'q'", str(ctx.exception))

    def test_all_rests_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_grid("----")

    def test_empty_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_grid("   ")

    def test_bad_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_grid("x-x-", mode="nope")

    # ---- 프리셋과의 구분 ---------------------------------------------------
    def test_preset_names_win_over_grid_detection(self):
        """``sixteenth`` 에는 x 가 들어 있지만 프리셋 이름입니다."""
        for name in RHYTHM_PATTERNS:
            with self.subTest(name=name):
                self.assertIs(resolve_pattern(name), RHYTHM_PATTERNS[name])

    def test_grid_strings_are_detected(self):
        for grid in ["x-x-", "X~~-", "xoxo", "x-x-|x-x-"]:
            self.assertTrue(looks_like_grid(grid), grid)
        for name in ["sixteenth", "bossa", "arp_up", "sixeight"]:
            self.assertFalse(looks_like_grid(name), name)

    def test_grid_pattern_is_tagged(self):
        self.assertIn("직접입력", parse_grid("x-x-").tags)

    def test_empty_grid_says_what_is_missing(self):
        """아직 아무것도 그리지 않았을 때 '모르는 리듬' 이라고 하면 안 됩니다."""
        with self.assertRaises(ValueError) as ctx:
            resolve_pattern("--------")
        message = str(ctx.exception)
        self.assertIn("치는 음", message)
        self.assertNotIn("모르는 리듬", message)

    def test_unknown_rhythm_lists_both_options(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_pattern("nonsense")
        message = str(ctx.exception)
        self.assertIn("bossa", message)
        self.assertIn("x", message)


if __name__ == "__main__":
    unittest.main()
