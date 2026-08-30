"""휴머나이즈 엔진 테스트."""

import unittest

from cubase_mcp.humanize import (GROUP_WINDOW_MS, PROFILES, customize, get_profile,
                                 humanize_notes)
from cubase_mcp.midi.smf import Note

TEMPO = 100.0
PPQ = 480
#: 이 템포에서 1밀리초는 몇 틱인가
TICKS_PER_MS = (PPQ * TEMPO) / 60000.0


def chord_bar(velocity=90, pitches=(60, 64, 67, 71), beats=4):
    """한 마디 동안 정박마다 같은 화음을 치는 노트 목록."""
    return [Note(b * PPQ, PPQ - 20, p, velocity)
            for b in range(beats) for p in pitches]


def groups(notes, beats=4):
    out = []
    for b in range(beats):
        grp = [n for n in notes if abs(n.start - b * PPQ) < PPQ * 0.6]
        if grp:
            out.append(sorted(grp, key=lambda n: n.pitch))
    return out


class TestProfiles(unittest.TestCase):
    def test_every_profile_is_well_formed(self):
        for name, p in PROFILES.items():
            with self.subTest(profile=name):
                self.assertTrue(p.korean and p.description)
                self.assertGreaterEqual(p.timing_jitter_ms, 0)
                self.assertGreaterEqual(p.roll_ms, 0)
                self.assertTrue(0 <= p.downbeat_tightness <= 1)
                self.assertTrue(1 <= p.fixed_velocity <= 127)

    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            get_profile("nope")
        self.assertIn("piano_natural", str(ctx.exception))

    def test_customize_overrides_only_given_fields(self):
        p = customize("piano_natural", roll_ms=30.0)
        self.assertEqual(p.roll_ms, 30.0)
        self.assertEqual(p.melody_lead_ms, get_profile("piano_natural").melody_lead_ms)

    def test_customize_ignores_none(self):
        self.assertEqual(customize("subtle", roll_ms=None).roll_ms,
                         get_profile("subtle").roll_ms)

    def test_customize_rejects_unknown_field(self):
        with self.assertRaises(ValueError):
            customize("subtle", groove_magic=1.0)


class TestApplication(unittest.TestCase):
    def test_off_changes_nothing(self):
        notes = chord_bar()
        out = humanize_notes(notes, "off", tempo=TEMPO, seed=1)
        self.assertEqual([(n.start, n.duration, n.pitch, n.velocity) for n in out],
                         [(n.start, n.duration, n.pitch, n.velocity)
                          for n in sorted(notes, key=lambda n: (n.start, n.pitch))])

    def test_input_is_not_mutated(self):
        notes = chord_bar()
        before = [(n.start, n.velocity, n.duration) for n in notes]
        humanize_notes(notes, "lofi_sloppy", tempo=TEMPO, seed=1)
        self.assertEqual([(n.start, n.velocity, n.duration) for n in notes], before)

    def test_seed_makes_it_reproducible(self):
        notes = chord_bar()
        a = humanize_notes(notes, "piano_natural", tempo=TEMPO, seed=3)
        b = humanize_notes(notes, "piano_natural", tempo=TEMPO, seed=3)
        self.assertEqual([(n.start, n.velocity) for n in a],
                         [(n.start, n.velocity) for n in b])

    def test_output_stays_in_midi_range(self):
        for name in PROFILES:
            with self.subTest(profile=name):
                out = humanize_notes(chord_bar(velocity=120), name,
                                     tempo=TEMPO, seed=2)
                for n in out:
                    self.assertTrue(1 <= n.velocity <= 127)
                    self.assertGreaterEqual(n.start, 0)
                    self.assertGreaterEqual(n.duration, 1)

    def test_note_count_is_preserved(self):
        notes = chord_bar()
        for name in PROFILES:
            with self.subTest(profile=name):
                self.assertEqual(len(humanize_notes(notes, name, tempo=TEMPO, seed=1)),
                                 len(notes))

    # ---- 코드 굴림 --------------------------------------------------------
    def test_chord_roll_spreads_low_to_high(self):
        """굴림은 낮은음부터 순서대로 번져 올라가야 합니다."""
        out = humanize_notes(chord_bar(), customize("piano_natural",
                                                    timing_jitter_ms=0.0,
                                                    roll_jitter_ms=0.0,
                                                    melody_lead_ms=0.0,
                                                    velocity_timing_coupling=0.0,
                                                    push_pull_ms=0.0),
                             tempo=TEMPO, seed=1)
        for group in groups(out):
            starts = [n.start for n in group]
            self.assertEqual(starts, sorted(starts), "낮은음이 먼저 나야 합니다")
            self.assertGreater(starts[-1] - starts[0], 0)

    def test_roll_is_off_when_profile_says_zero(self):
        out = humanize_notes(chord_bar(), customize("piano_natural", roll_ms=0.0,
                                                    roll_jitter_ms=0.0,
                                                    timing_jitter_ms=0.0,
                                                    melody_lead_ms=0.0,
                                                    velocity_timing_coupling=0.0,
                                                    push_pull_ms=0.0),
                             tempo=TEMPO, seed=1)
        for group in groups(out):
            self.assertEqual(len({n.start for n in group}), 1)

    def test_existing_spread_is_preserved_not_re_rolled(self):
        """스트럼처럼 이미 벌어진 덩어리에 굴림을 또 넣지 않습니다."""
        spread = [Note(int(i * 8 * TICKS_PER_MS), 400, 60 + i * 4, 90) for i in range(4)]
        out = humanize_notes(spread, customize("guitar_strum", timing_jitter_ms=0.0,
                                               push_pull_ms=0.0,
                                               velocity_timing_coupling=0.0),
                             tempo=TEMPO, seed=1)
        gaps = [b.start - a.start for a, b in zip(out, out[1:])]
        for gap in gaps:
            self.assertLess(gap, 20 * TICKS_PER_MS, "원래 간격이 커졌습니다")

    # ---- 그루브 -----------------------------------------------------------
    def test_laid_back_plays_late_and_pushed_plays_early(self):
        notes = chord_bar()
        late = humanize_notes(notes, customize("laid_back", timing_jitter_ms=0.0),
                              tempo=TEMPO, seed=1)
        early = humanize_notes(notes, customize("pushed", timing_jitter_ms=0.0),
                               tempo=TEMPO, seed=1)
        # 첫 박은 프로젝트 시작보다 앞설 수 없으므로 2박 이후로 비교합니다.
        late_off = late[4].start - PPQ
        early_off = early[4].start - PPQ
        self.assertGreater(late_off, 0, "레이드백은 박보다 늦어야 합니다")
        self.assertLess(early_off, 0, "푸시는 박보다 빨라야 합니다")

    def test_tight_profile_moves_less_than_loose_one(self):
        notes = chord_bar()
        tight = humanize_notes(notes, "machine", tempo=TEMPO, seed=5)
        loose = humanize_notes(notes, "lofi_sloppy", tempo=TEMPO, seed=5)

        def drift(out):
            return sum(abs(n.start - q.start)
                       for n, q in zip(out, sorted(notes, key=lambda x: (x.start, x.pitch))))

        self.assertLess(drift(tight), drift(loose))

    # ---- 악센트 -----------------------------------------------------------
    def test_metric_accent_makes_beat_one_loudest(self):
        out = humanize_notes(chord_bar(), customize("piano_natural",
                                                    velocity_jitter=0.0,
                                                    top_voice_boost=0.0,
                                                    bass_voice_boost=0.0,
                                                    inner_voice_cut=0.0),
                             tempo=TEMPO, seed=1)
        per_beat = [max(n.velocity for n in g) for g in groups(out)]
        self.assertEqual(per_beat.index(max(per_beat)), 0,
                         f"1박이 가장 세야 합니다: {per_beat}")

    def test_offbeats_are_softer_than_downbeats(self):
        notes = [Note(0, 200, 60, 90), Note(PPQ // 2, 200, 60, 90)]
        out = humanize_notes(notes, customize("piano_natural", velocity_jitter=0.0),
                             tempo=TEMPO, seed=1)
        self.assertGreater(out[0].velocity, out[1].velocity)

    def test_top_voice_is_boosted_and_inner_voices_cut(self):
        out = humanize_notes([Note(0, 400, p, 90) for p in (60, 64, 67, 71)],
                             customize("piano_natural", velocity_jitter=0.0,
                                       metric_accent=0.0),
                             tempo=TEMPO, seed=1)
        by_pitch = {n.pitch: n.velocity for n in out}
        self.assertGreater(by_pitch[71], by_pitch[64], "최고음이 속음보다 세야 합니다")
        self.assertGreater(by_pitch[60], by_pitch[64], "최저음이 속음보다 세야 합니다")

    def test_organ_ignores_velocity(self):
        """오르간은 벨로시티에 반응하지 않는 악기이므로 세기를 고정합니다."""
        out = humanize_notes(chord_bar(velocity=40), "organ", tempo=TEMPO, seed=1)
        self.assertEqual({n.velocity for n in out}, {get_profile("organ").fixed_velocity})

    def test_backbeat_accent_lifts_two_and_four(self):
        base = customize("piano_natural", velocity_jitter=0.0, metric_accent=0.0,
                         top_voice_boost=0.0, bass_voice_boost=0.0,
                         inner_voice_cut=0.0, backbeat_accent=0.0)
        flat = humanize_notes(chord_bar(), base, tempo=TEMPO, seed=1)
        accented = humanize_notes(chord_bar(), customize("piano_natural",
                                                         velocity_jitter=0.0,
                                                         metric_accent=0.0,
                                                         top_voice_boost=0.0,
                                                         bass_voice_boost=0.0,
                                                         inner_voice_cut=0.0,
                                                         backbeat_accent=0.8),
                                  tempo=TEMPO, seed=1)
        self.assertGreater(max(n.velocity for n in groups(accented)[1]),
                           max(n.velocity for n in groups(flat)[1]))

    # ---- amount ----------------------------------------------------------
    def test_amount_zero_is_a_no_op(self):
        notes = chord_bar()
        out = humanize_notes(notes, "lofi_sloppy", tempo=TEMPO, seed=1, amount=0.0)
        self.assertEqual([n.start for n in out],
                         [n.start for n in sorted(notes, key=lambda n: (n.start, n.pitch))])

    def test_amount_scales_the_effect(self):
        notes = chord_bar()
        half = humanize_notes(notes, "piano_ballad", tempo=TEMPO, seed=1, amount=0.4)
        full = humanize_notes(notes, "piano_ballad", tempo=TEMPO, seed=1, amount=1.0)
        self.assertLess(groups(half)[0][-1].start - groups(half)[0][0].start,
                        groups(full)[0][-1].start - groups(full)[0][0].start)

    def test_amount_out_of_range_is_rejected(self):
        with self.assertRaises(ValueError):
            humanize_notes(chord_bar(), "subtle", tempo=TEMPO, amount=2.0)

    def test_roll_is_a_constant_wall_clock_time(self):
        """굴림 폭은 템포와 무관하게 같은 **밀리초** 여야 합니다.

        손이 건반을 훑는 속도는 곡이 빨라진다고 빨라지지 않습니다. 그래서
        틱 수는 템포에 비례해 늘어나지만, 실제 시간으로는 항상 같아야 합니다.
        """
        profile = customize("piano_natural", timing_jitter_ms=0.0, roll_jitter_ms=0.0,
                            melody_lead_ms=0.0, velocity_timing_coupling=0.0,
                            push_pull_ms=0.0)
        spans_ms = {}
        for tempo in (60, 120, 180):
            out = humanize_notes(chord_bar(), profile, tempo=tempo, seed=1)
            first = groups(out)[0]
            ticks = first[-1].start - first[0].start
            spans_ms[tempo] = ticks / ((PPQ * tempo) / 60000.0)

        expected = profile.roll_ms * 3          # 4음 화음 = 간격 3개
        for tempo, span in spans_ms.items():
            self.assertAlmostEqual(span, expected, delta=1.5,
                                   msg=f"{tempo}BPM 에서 굴림 폭이 {span:.1f}ms")

        # 반대로 틱 수는 템포에 비례해 늘어납니다.
        ticks = {t: spans_ms[t] * ((PPQ * t) / 60000.0) for t in spans_ms}
        self.assertLess(ticks[60], ticks[180])


class TestTargets(unittest.TestCase):
    def test_registry(self):
        from cubase_mcp.targets import get_target, list_targets

        names = {t["name"]: t for t in list_targets()}
        self.assertTrue(names["midi_file"]["available"])
        # Cubase 직접 가져오기는 구현되어 있지만 준비가 필요합니다(Windows + 단축키).
        self.assertIn("cubase_import", names)
        self.assertTrue(names["cubase_import"]["limitations"])
        for planned in ("virtual_port", "midi_remote", "project_file"):
            self.assertIn(planned, names)
            self.assertFalse(names[planned]["available"])
            self.assertTrue(names[planned]["limitations"],
                            f"{planned}: 한계를 적어 두어야 합니다")
        self.assertEqual(get_target("midi_file").name, "midi_file")

    def test_unknown_target_is_rejected(self):
        from cubase_mcp.targets import get_target
        with self.assertRaises(ValueError):
            get_target("nope")

    def test_planned_target_explains_what_is_missing(self):
        from cubase_mcp.render import build_arrangement
        from cubase_mcp.targets import TargetUnavailable, deliver
        from cubase_mcp.theory.chords import parse_progression

        arrangement = build_arrangement(parse_progression("C F"))
        with self.assertRaises(TargetUnavailable) as ctx:
            deliver(arrangement, "virtual_port")
        self.assertIn("loopMIDI", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
