"""레시피 기록과 부분 수정 테스트.

'휴머나이즈만 빼고 다시' 같은 수정은 MIDI 를 되읽어 추론하는 대신, 만들 때
쓴 설정을 기록해 두었다가 바꿀 것만 바꿔 다시 만드는 방식입니다. 추론이
없으므로 나머지가 **정확히 같아야** 합니다. 그 점을 확인합니다.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from cubase_mcp import recipes


class TestRecipeStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="recipes-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def touch(self, name):
        (self.tmp / name).write_bytes(b"MThd")

    def test_save_and_load(self):
        self.touch("a.mid")
        recipes.save(self.tmp, "a.mid", {"chords": "C", "voicing": "drop2"})
        self.assertEqual(recipes.load(self.tmp, "a.mid")["params"],
                         {"chords": "C", "voicing": "drop2"})

    def test_only_tracked_fields_are_kept(self):
        self.touch("a.mid")
        recipes.save(self.tmp, "a.mid", {"chords": "C", "무관한값": 1})
        self.assertNotIn("무관한값", recipes.load(self.tmp, "a.mid")["params"])

    def test_none_values_are_not_stored(self):
        self.touch("a.mid")
        recipes.save(self.tmp, "a.mid", {"chords": "C", "seed": None})
        self.assertNotIn("seed", recipes.load(self.tmp, "a.mid")["params"])

    def test_latest_respects_save_order(self):
        """같은 초에 여러 개를 저장해도 순서가 확실해야 합니다."""
        for name in "abcde":
            self.touch(f"{name}.mid")
            recipes.save(self.tmp, f"{name}.mid", {"chords": "C"})
        self.assertEqual(recipes.latest(self.tmp), "e.mid")
        self.assertEqual(recipes.known(self.tmp)[0], "e.mid")

    def test_missing_files_are_skipped(self):
        self.touch("a.mid")
        recipes.save(self.tmp, "a.mid", {"chords": "C"})
        recipes.save(self.tmp, "gone.mid", {"chords": "D"})   # 파일 없음
        self.assertEqual(recipes.known(self.tmp), ["a.mid"])
        self.assertEqual(recipes.latest(self.tmp), "a.mid")

    def test_corrupt_index_does_not_break_anything(self):
        recipes.index_path(self.tmp).write_text("{깨진", encoding="utf-8")
        self.assertEqual(recipes.known(self.tmp), [])
        self.assertIsNone(recipes.load(self.tmp, "a.mid"))
        self.touch("a.mid")
        recipes.save(self.tmp, "a.mid", {"chords": "C"})       # 다시 쓰면 복구
        self.assertEqual(recipes.known(self.tmp), ["a.mid"])

    def test_index_is_trimmed(self):
        original = recipes.MAX_ENTRIES
        recipes.MAX_ENTRIES = 5
        try:
            for i in range(9):
                self.touch(f"{i}.mid")
                recipes.save(self.tmp, f"{i}.mid", {"chords": "C"})
            self.assertLessEqual(len(recipes._load_all(self.tmp)), 5)
            self.assertEqual(recipes.latest(self.tmp), "8.mid")
        finally:
            recipes.MAX_ENTRIES = original

    def test_merge_keeps_unspecified_values(self):
        base = {"chords": "C", "voicing": "drop2", "humanize": "piano_ballad"}
        merged = recipes.merge(base, {"humanize": "off", "voicing": None})
        self.assertEqual(merged, {"chords": "C", "voicing": "drop2",
                                  "humanize": "off"})

    def test_merge_ignores_unknown_fields(self):
        self.assertEqual(recipes.merge({"chords": "C"}, {"뭔가": 1}), {"chords": "C"})

    def test_changed_fields(self):
        diff = recipes.changed_fields({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})
        self.assertEqual(set(diff), {"b", "c"})
        self.assertEqual(diff["b"], {"before": 2, "after": 3})


try:
    from cubase_mcp import server as srv
    from cubase_mcp.config import SETTINGS
    from tests.smf_reader import parse
    HAVE_MCP = True
except ImportError:                                     # pragma: no cover
    HAVE_MCP = False


@unittest.skipUnless(HAVE_MCP, "mcp 패키지가 설치되어 있지 않습니다")
class TestRevise(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="revise-"))
        self.previous = SETTINGS.output_dir
        SETTINGS.output_dir = self.tmp

    def tearDown(self):
        SETTINGS.output_dir = self.previous
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make(self, **kwargs):
        params = dict(chords="C; I-V-vi-IV", voicing="drop2", rhythm="x--x-x--",
                      humanize="piano_ballad", tempo=96, include_bass=True,
                      filename="base.mid", seed=1)
        params.update(kwargs)
        return srv.create_chord_midi(**params)

    def starts(self, result):
        return sorted({n.start for n in parse(Path(result["file"]).read_bytes()).notes})

    def test_generating_records_a_recipe(self):
        made = self.make()
        entry = recipes.load(self.tmp, made["filename"])
        self.assertIsNotNone(entry)
        self.assertEqual(entry["params"]["voicing"], "drop2")

    def test_removing_humanize_snaps_to_the_grid(self):
        """'휴머나이즈 제거해줘' 의 핵심 동작."""
        original = self.make()
        revised = srv.revise_midi(humanize="off")
        self.assertEqual(revised["humanize"], "off")
        self.assertTrue(all(t % 240 == 0 for t in self.starts(revised)),
                        "휴머나이즈를 껐는데 그리드에 붙지 않았습니다")
        self.assertFalse(all(t % 240 == 0 for t in self.starts(original)))

    def test_revision_keeps_everything_else_identical(self):
        original = self.make()
        revised = srv.revise_midi(humanize="off")
        self.assertEqual(revised["chords"], original["chords"])
        self.assertEqual(revised["rhythm_detail"], original["rhythm_detail"])
        self.assertEqual(revised["tempo"], original["tempo"])
        self.assertEqual(revised["tracks"], original["tracks"])

    def test_changing_only_the_voicing(self):
        self.make()
        revised = srv.revise_midi(voicing="rootless_a")
        self.assertEqual(revised["voicing"], "rootless_a")
        self.assertEqual(revised["humanize"], "piano_ballad")

    def test_reports_what_changed(self):
        self.make()
        revised = srv.revise_midi(humanize="off", tempo=120)
        self.assertEqual(set(revised["changed"]), {"humanize", "tempo"})
        self.assertIn("piano_ballad", revised["change_summary"])

    def test_writes_a_new_file_and_keeps_the_original(self):
        original = self.make()
        revised = srv.revise_midi(humanize="off")
        self.assertNotEqual(revised["file"], original["file"])
        self.assertTrue(Path(original["file"]).is_file())
        self.assertTrue(Path(revised["file"]).is_file())

    def test_revised_files_can_be_revised_again(self):
        self.make()
        once = srv.revise_midi(humanize="off")
        twice = srv.revise_midi(filename=once["filename"], voicing="quartal")
        self.assertEqual(twice["humanize"], "off")
        self.assertEqual(twice["voicing"], "quartal")

    def test_defaults_to_the_most_recent_file(self):
        self.make(filename="first.mid")
        self.make(filename="second.mid", voicing="quartal")
        revised = srv.revise_midi(humanize="off")
        self.assertEqual(revised["revised_from"], "second.mid")

    def test_unknown_file_lists_what_is_available(self):
        # 도구는 예상 가능한 오류를 ToolError 로 바꿔 클라이언트에 전달합니다.
        self.make()
        with self.assertRaises(srv._ToolError) as ctx:
            srv.revise_midi(filename="남의트랙.mid", humanize="off")
        self.assertIn("기록이 없어", str(ctx.exception))
        self.assertIn("base.mid", str(ctx.exception))

    def test_requires_at_least_one_change(self):
        self.make()
        with self.assertRaises(srv._ToolError) as ctx:
            srv.revise_midi()
        self.assertIn("무엇을 바꿀지", str(ctx.exception))

    def test_save_as_is_respected(self):
        self.make()
        revised = srv.revise_midi(humanize="off", save_as="깔끔한버전.mid")
        self.assertEqual(Path(revised["file"]).name, "깔끔한버전.mid")

    def test_listing_marks_revisable_files(self):
        self.make()
        (self.tmp / "손으로만든것.mid").write_bytes(b"MThd")
        listed = {f["name"]: f["revisable"] for f in srv.list_output_files()["files"]}
        self.assertTrue(listed["base.mid"])
        self.assertFalse(listed["손으로만든것.mid"])


if __name__ == "__main__":
    unittest.main()
