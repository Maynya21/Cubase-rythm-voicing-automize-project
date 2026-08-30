"""로컬 스튜디오 화면 테스트.

브라우저 없이 HTTP 계층과 API 를 직접 두드립니다. 로컬 전용 제한과 토큰
검사가 실제로 막는지가 특히 중요합니다 — 이 서버는 파일을 씁니다.
"""

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from cubase_mcp import studio
from cubase_mcp.config import SETTINGS
from cubase_mcp.theory.rhythm import RHYTHM_PATTERNS, parse_grid, pattern_to_grid


class TestGridConversion(unittest.TestCase):
    def test_roundtrip_keeps_the_grid(self):
        for grid in ["x--x-x--", "X~~-x~~-", "x-x-x-x-", "X-o-x-o-"]:
            with self.subTest(grid=grid):
                self.assertEqual(pattern_to_grid(parse_grid(grid), 2, 4), grid)

    def test_every_preset_converts_to_a_valid_grid(self):
        """프리셋을 격자로 불러와 고칠 수 있어야 합니다."""
        for name, pattern in RHYTHM_PATTERNS.items():
            with self.subTest(name=name):
                bar = 3.0 if pattern.beats_per_bar == 3 else 4.0
                grid = pattern_to_grid(pattern, 4, bar)
                rebuilt = parse_grid(grid, beats_per_bar=bar)
                self.assertTrue(rebuilt.events, f"{name}: 타점이 사라졌습니다")

    def test_accents_and_ghosts_survive(self):
        grid = pattern_to_grid(parse_grid("X-o-x-x-"), 2, 4)
        self.assertEqual(grid, "X-o-x-x-")

    def test_long_notes_become_ties(self):
        self.assertEqual(pattern_to_grid(parse_grid("x~~~~~~~"), 2, 4), "x~~~~~~~")

    def test_finer_division_expresses_the_same_rhythm(self):
        """한 박을 더 잘게 나누면 같은 리듬이 더 많은 칸으로 적힙니다."""
        pattern = parse_grid("x~~~")                    # 4칸 = 한 박에 1칸
        self.assertEqual(pattern_to_grid(pattern, 1, 4), "x~~~")
        self.assertEqual(pattern_to_grid(pattern, 2, 4), "x~~~~~~~")
        self.assertEqual(pattern_to_grid(pattern, 4, 4), "x" + "~" * 15)

    def test_rejects_bad_division(self):
        with self.assertRaises(ValueError):
            pattern_to_grid(RHYTHM_PATTERNS["quarter"], 0)


class TestStudioServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="studio-test-"))
        cls.previous = SETTINGS.output_dir
        SETTINGS.output_dir = cls.tmp
        cls.server = studio.build_server()
        cls.token = cls.server.RequestHandlerClass.token
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        SETTINGS.output_dir = cls.previous
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- 도우미 ------------------------------------------------------------
    def post(self, path, body=None, token=None, headers=None):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body or {}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "X-Studio-Token": self.token if token is None else token,
                     **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def get(self, path, headers=None):
        request = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    # -- 페이지 ------------------------------------------------------------
    def test_serves_the_page_with_a_token(self):
        status, html = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Cubase MCP 스튜디오", html)
        self.assertNotIn("{{TOKEN}}", html, "토큰이 주입되지 않았습니다")
        self.assertIn(self.token, html)

    def test_page_file_ships_with_the_package(self):
        self.assertTrue(studio.PAGE.is_file())

    # -- 보안 --------------------------------------------------------------
    def test_requires_the_token(self):
        status, body = self.post("/api/generate", {"chords": "C"}, token="wrong")
        self.assertEqual(status, 403)
        self.assertIn("토큰", body["error"])

    def test_rejects_foreign_host_header(self):
        status, _ = self.get("/", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)

    def test_rejects_foreign_origin(self):
        status, _ = self.post("/api/files", {},
                              headers={"Origin": "https://evil.example.com"})
        self.assertEqual(status, 403)

    def test_binds_to_loopback_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_unknown_route(self):
        self.assertEqual(self.post("/api/nope")[0], 404)

    # -- 기능 --------------------------------------------------------------
    def test_capabilities(self):
        status, data = self.post("/api/capabilities")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(data["voicings"]), 17)
        self.assertGreaterEqual(len(data["rhythms"]), 40)
        self.assertGreaterEqual(len(data["humanize"]), 19)

    def test_preview_with_degrees_and_grid(self):
        status, data = self.post("/api/preview", {
            "chords": "C; I-V-vi-IV", "rhythm": "x--x-x--", "voicing": "drop2"})
        self.assertEqual(status, 200)
        self.assertEqual(data["input_style"], "도수")
        self.assertEqual([c["symbol"] for c in data["chords"]], ["C", "G", "Am", "F"])
        self.assertEqual(data["rhythm"]["source"], "그리드")
        self.assertEqual(len(data["rhythm"]["hits"]), 3)
        self.assertTrue(all(c["voicing"] for c in data["chords"]))

    def test_preview_returns_an_editable_grid_for_presets(self):
        status, data = self.post("/api/preview", {"chords": "C", "rhythm": "bossa",
                                                  "division": 2})
        self.assertEqual(status, 200)
        self.assertEqual(data["rhythm"]["source"], "프리셋")
        self.assertTrue(any(ch in data["rhythm"]["grid"] for ch in "xXo"))

    def test_generate_writes_a_file(self):
        status, data = self.post("/api/generate", {
            "chords": "C; I-V-vi-IV", "rhythm": "X~~-x~~-", "voicing": "drop2",
            "humanize": "piano_natural", "include_bass": True, "tempo": 96,
            "filename": "studio-unit.mid"})
        self.assertEqual(status, 200)
        path = Path(data["file"])
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent, self.tmp)
        self.assertEqual(data["tracks"], ["Chords", "Bass"])
        self.assertTrue(all(v["roman"] for v in data["voicings"]))

    def test_generate_cannot_escape_the_output_folder(self):
        status, data = self.post("/api/generate",
                                 {"chords": "C", "filename": "../../escaped.mid"})
        self.assertEqual(status, 200)
        self.assertEqual(Path(data["file"]).parent, self.tmp)

    def test_reveal_refuses_paths_outside_the_output_folder(self):
        """이 서버가 임의 경로를 여는 통로가 되면 안 됩니다."""
        for bad in ["../../../etc/passwd", "/etc/passwd", "..\\..\\secret.mid",
                    "없는파일.mid", "sub/../../x.mid"]:
            with self.subTest(bad=bad):
                status, data = self.post("/api/reveal", {"filename": bad})
                self.assertEqual(status, 400)
                self.assertIn("출력 폴더", data["error"])

    def test_reveal_accepts_a_file_it_just_made(self):
        """탐색기가 없는 환경에서도 경로 검증은 통과해야 합니다."""
        self.post("/api/generate", {"chords": "C", "filename": "reveal-ok.mid"})
        status, data = self.post("/api/reveal", {"filename": "reveal-ok.mid"})
        # 탐색기가 있으면 200, 없으면 400 이지만 경로 거절은 아니어야 합니다.
        if status == 400:
            self.assertNotIn("출력 폴더 안의 파일만", data["error"])
        else:
            self.assertEqual(status, 200)

    def test_suggest(self):
        status, data = self.post("/api/suggest",
                                 {"key": "C", "genre": "citypop", "bars": 8, "seed": 1})
        self.assertEqual(status, 200)
        self.assertEqual(len(data["chords"]), 8)
        self.assertIn("-", data["romans_text"])

    def test_files_listing(self):
        self.post("/api/generate", {"chords": "C", "filename": "listed.mid"})
        status, data = self.post("/api/files")
        self.assertEqual(status, 200)
        self.assertIn("listed.mid", [f["name"] for f in data["files"]])

    # -- 오류 --------------------------------------------------------------
    def test_errors_are_readable(self):
        cases = [
            ({"chords": "I V vi"}, "조성"),
            ({"chords": "C", "rhythm": "x-x-x"}, "칸"),
            ({"chords": "C", "low": "C5", "high": "C2"}, "낮아야"),
            ({"chords": "Cxyz"}, "Cxyz"),
            ({"chords": "C", "time_signature": "4-4"}, "박자표"),
        ]
        for body, needle in cases:
            with self.subTest(body=body):
                status, data = self.post("/api/preview", body)
                self.assertEqual(status, 400)
                self.assertIn(needle, data["error"])

    def test_malformed_json_is_rejected(self):
        request = urllib.request.Request(
            self.base + "/api/preview", data=b"{not json",
            headers={"Content-Type": "application/json", "X-Studio-Token": self.token})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
