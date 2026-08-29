"""MCP 서버 계층 테스트.

`mcp` 패키지가 없는 환경에서는 통째로 건너뜁니다 (이론/MIDI 코어는
외부 의존성이 없으므로 그쪽 테스트는 계속 돌아갑니다).
"""

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from cubase_mcp import server as srv
    HAVE_MCP = True
except ImportError:                                     # pragma: no cover
    HAVE_MCP = False

from .smf_reader import parse


@unittest.skipUnless(HAVE_MCP, "mcp 패키지가 설치되어 있지 않습니다")
class TestServerTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="cubase-mcp-test-"))
        cls.previous = srv.SETTINGS.output_dir
        srv.SETTINGS.output_dir = cls.tmp

    @classmethod
    def tearDownClass(cls):
        srv.SETTINGS.output_dir = cls.previous
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- 도우미 ------------------------------------------------------------
    def call(self, name, **kwargs):
        from mcp.server.mcpserver.exceptions import ToolError

        async def run():
            return await srv.mcp.call_tool(name, kwargs)

        try:
            result = asyncio.run(run())
        except ToolError as exc:
            raise AssertionError(f"도구가 실패했습니다: {exc}") from exc
        content = result.structured_content
        return content.get("result", content) if isinstance(content, dict) else content

    def call_expect_error(self, name, **kwargs):
        from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

        async def run():
            return await srv.mcp.call_tool(name, kwargs)

        try:
            result = asyncio.run(run())
        except UnexpectedToolError as exc:              # 예상 못 한 크래시
            raise AssertionError(f"예상 못 한 크래시입니다: {exc}") from exc
        except ToolError as exc:
            return str(exc)
        if not result.is_error:
            raise AssertionError(f"{name} 이 오류를 내지 않았습니다: {kwargs}")
        return " ".join(getattr(c, "text", "") for c in result.content)

    # -- 테스트 ------------------------------------------------------------
    def test_all_tools_registered(self):
        names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
        self.assertEqual(names, {
            "list_capabilities", "get_settings", "set_output_folder",
            "list_output_files", "analyze_chords", "suggest_progression",
            "preview_voicing", "reharmonize_progression", "transpose_progression",
            "create_chord_midi", "create_progression_midi", "check_setup",
        })

    def test_tool_signatures_survive_the_error_wrapper(self):
        tools = {t.name: t for t in asyncio.run(srv.mcp.list_tools())}
        schema = tools["create_chord_midi"].input_schema
        self.assertEqual(schema.get("required"), ["chords"])
        for expected in ("voicing", "rhythm", "tempo", "include_bass", "seed"):
            self.assertIn(expected, schema["properties"])
        self.assertTrue(tools["create_chord_midi"].description)

    def test_capabilities_lists_everything(self):
        caps = self.call("list_capabilities")
        self.assertGreaterEqual(len(caps["voicing_styles"]), 17)
        self.assertGreaterEqual(len(caps["rhythm_patterns"]), 40)
        self.assertGreaterEqual(len(caps["progression_templates"]), 25)
        self.assertGreaterEqual(len(caps["humanize_profiles"]), 15)
        self.assertIn("citypop", caps["genres"])
        targets = {t["name"]: t for t in caps["delivery_targets"]}
        self.assertTrue(targets["midi_file"]["available"])

    def test_check_setup_reports_healthy(self):
        report = self.call("check_setup")
        self.assertTrue(report["ok"], report["checks"])
        self.assertTrue(all(c["ok"] for c in report["checks"]))
        self.assertGreaterEqual(report["counts"]["humanize_profiles"], 15)

    def test_humanize_profile_reaches_the_file(self):
        straight = self.call("create_chord_midi", chords="C F G C",
                             rhythm="quarter", humanize="off", filename="h-off.mid")
        played = self.call("create_chord_midi", chords="C F G C", rhythm="quarter",
                           humanize="piano_ballad", filename="h-ballad.mid", seed=4)
        self.assertEqual(straight["humanize"], "off")
        self.assertEqual(played["humanize"], "piano_ballad")
        off_starts = {n.start for n in parse(Path(straight["file"]).read_bytes()).notes}
        on_starts = {n.start for n in parse(Path(played["file"]).read_bytes()).notes}
        self.assertNotEqual(off_starts, on_starts)

    def test_unavailable_target_explains_requirements(self):
        message = self.call_expect_error("create_chord_midi", chords="C",
                                         target="virtual_port")
        self.assertIn("loopMIDI", message)

    def test_unknown_humanize_profile_lists_valid_ones(self):
        message = self.call_expect_error("create_chord_midi", chords="C",
                                         humanize="nope")
        self.assertIn("piano_natural", message)

    def test_analyze_chords(self):
        out = self.call("analyze_chords", chords="Cmaj7 | A7 | Dm7 | G7", key="C")
        self.assertEqual([c["roman"] for c in out["chords"]],
                         ["Imaj7", "VI7", "ii7", "V7"])

    def test_suggest_progression_is_seeded(self):
        a = self.call("suggest_progression", key="C", genre="pop", seed=5)
        b = self.call("suggest_progression", key="C", genre="pop", seed=5)
        self.assertEqual(a["chords"], b["chords"])

    def test_preview_voicing_returns_note_names(self):
        out = self.call("preview_voicing", chords="Cmaj7 G7", voicing="drop2")
        self.assertEqual(len(out["voicings"]), 2)
        self.assertTrue(all(v["notes"] for v in out["voicings"]))
        self.assertEqual(len(out["voicings"][0]["notes"]),
                         len(out["voicings"][0]["midi"]))

    def test_transpose(self):
        out = self.call("transpose_progression", chords="Cmaj7 Am7 Dm7 G7/B",
                        to_key="Eb", from_key="C")
        self.assertEqual(out["after"], ["Ebmaj7", "Cm7", "Fm7", "Bb7/D"])

    def test_create_chord_midi_writes_a_valid_file(self):
        out = self.call("create_chord_midi", chords="Cmaj7 | Am7 | Dm7 | G7",
                        voicing="drop2", rhythm="bossa", tempo=132, key="C",
                        include_bass=True, bass_style="root_fifth",
                        instrument="rhodes", filename="unit-test.mid", seed=1)
        path = Path(out["file"])
        self.assertTrue(path.is_file())
        self.assertEqual(out["tracks"], ["Chords", "Bass"])
        self.assertEqual(out["bars"], 4.0)
        parsed = parse(path.read_bytes())
        self.assertEqual(parsed.ppq, 480)
        self.assertAlmostEqual(parsed.tracks[0]["tempo"], 132.0, places=2)
        self.assertTrue(parsed.notes)

    def test_filename_collisions_do_not_overwrite(self):
        first = self.call("create_chord_midi", chords="C", filename="dup.mid")
        second = self.call("create_chord_midi", chords="C", filename="dup.mid")
        self.assertNotEqual(first["file"], second["file"])
        self.assertTrue(Path(first["file"]).is_file())
        self.assertTrue(Path(second["file"]).is_file())

    def test_filenames_cannot_escape_the_output_folder(self):
        out = self.call("create_chord_midi", chords="C",
                        filename="../../escaped.mid")
        self.assertEqual(Path(out["file"]).parent, self.tmp)

    def test_create_progression_midi_end_to_end(self):
        out = self.call("create_progression_midi", key="F# minor", genre="kpop",
                        bars=8, voicing="pad", rhythm="pop_ballad", tempo=76, seed=3)
        self.assertEqual(len(out["chords"]), 8)
        self.assertTrue(Path(out["file"]).is_file())
        self.assertTrue(parse(Path(out["file"]).read_bytes()).notes)

    def test_list_output_files(self):
        self.call("create_chord_midi", chords="C", filename="listed.mid")
        listed = self.call("list_output_files")
        self.assertIn("listed.mid", [f["name"] for f in listed["files"]])

    def test_errors_reach_the_client_with_useful_text(self):
        cases = [
            (dict(chords="Cxyz"), "Cxyz"),
            (dict(chords="C", voicing="nope"), "보이싱"),
            (dict(chords="C", rhythm="nope"), "리듬"),
            (dict(chords="C", time_signature="4-4"), "박자표"),
            (dict(chords="C", low="C5", high="C2"), "낮아야"),
            (dict(chords="C", velocity=999), "velocity"),
            (dict(chords="C", tempo=0), "tempo"),
        ]
        for kwargs, needle in cases:
            with self.subTest(kwargs=kwargs):
                message = self.call_expect_error("create_chord_midi", **kwargs)
                self.assertIn(needle, message)

    def test_unknown_genre_lists_valid_ones(self):
        message = self.call_expect_error("suggest_progression", genre="polka")
        self.assertIn("citypop", message)


if __name__ == "__main__":
    unittest.main()
