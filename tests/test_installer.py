"""설치 스크립트 인코딩 테스트.

cmd.exe 는 배치 파일을 **시스템 코드페이지**로 읽습니다. 파일을 UTF-8 로
저장하면 한국어 Windows(CP949) 에서 바이트 정렬이 어긋나 명령줄 자체가
중간에서 잘립니다. 실제로 그렇게 깨진 적이 있어서 회귀 테스트로 고정합니다.

파이썬이 콘솔로 출력하는 한국어도 CP949 로 표현 가능한 글자만 써야 합니다
(em dash 같은 글자는 CP949 에 없습니다).
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAT = ROOT / "install-windows.bat"
SH = ROOT / "install-macos-linux.sh"
WIZARD = ROOT / "cubase_mcp" / "setup_wizard.py"


class TestWindowsBatch(unittest.TestCase):
    def setUp(self):
        self.raw = BAT.read_bytes()

    def test_exists(self):
        self.assertTrue(BAT.is_file())

    def test_is_pure_ascii(self):
        """한글이 들어가면 CP949 환경에서 명령줄이 잘려 설치가 실패합니다."""
        offenders = [(i, b) for i, b in enumerate(self.raw) if b > 127]
        self.assertEqual(offenders, [],
                         f"비ASCII 바이트 {len(offenders)}개가 있습니다. "
                         f"한국어 안내는 setup_wizard.py 에서 출력하세요.")

    def test_has_no_bom(self):
        self.assertNotEqual(self.raw[:3], b"\xef\xbb\xbf")

    def test_uses_crlf_line_endings(self):
        self.assertEqual(self.raw.count(b"\r\n"), self.raw.count(b"\n"),
                         "배치 파일은 CRLF 줄바꿈이어야 합니다")

    def test_does_not_switch_codepage(self):
        """chcp 65001 은 배치 파서의 파일 위치를 어긋나게 만듭니다."""
        self.assertNotIn(b"chcp", self.raw.lower())

    def test_parenthesis_blocks_are_balanced(self):
        depth = 0
        for number, line in enumerate(self.raw.decode("ascii").split("\r\n"), 1):
            stripped = line.strip()
            if stripped.startswith(("rem", "echo")):
                continue
            depth += stripped.count("(") - stripped.count(")")
            self.assertGreaterEqual(depth, 0, f"{number}번째 줄에서 괄호가 먼저 닫힙니다")
        self.assertEqual(depth, 0, "괄호 블록이 닫히지 않았습니다")

    def test_quotes_are_balanced_per_line(self):
        for number, line in enumerate(self.raw.decode("ascii").split("\r\n"), 1):
            self.assertEqual(line.count('"') % 2, 0,
                             f"{number}번째 줄의 따옴표가 홀수입니다: {line}")

    def test_runs_from_its_own_folder(self):
        text = self.raw.decode("ascii")
        self.assertIn('cd /d "%~dp0"', text,
                      "탐색기에서 더블클릭해도 폴더가 맞도록 cd 해야 합니다")

    def test_tries_several_python_launchers(self):
        text = self.raw.decode("ascii")
        self.assertIn("for %%C in (py python python3)", text)

    def test_pauses_so_the_window_stays_open(self):
        """더블클릭으로 실행하면 pause 가 없을 때 오류를 볼 수 없습니다."""
        self.assertGreaterEqual(self.raw.decode("ascii").count("pause"), 3)


class TestUnixScript(unittest.TestCase):
    def test_uses_lf_line_endings(self):
        raw = SH.read_bytes()
        self.assertNotIn(b"\r\n", raw, "셸 스크립트에 CRLF 가 있으면 실행되지 않습니다")

    def test_has_shebang(self):
        self.assertTrue(SH.read_bytes().startswith(b"#!"))


class TestWizardConsoleOutput(unittest.TestCase):
    def test_printed_text_is_cp949_safe(self):
        """한국어 Windows 콘솔은 CP949 입니다. em dash 같은 글자는 깨집니다."""
        source = WIZARD.read_text(encoding="utf-8")
        characters = set()
        for match in re.finditer(r"print\((.*?)\)\n", source, re.S):
            characters.update(match.group(1))
        bad = []
        for char in sorted(characters):
            if ord(char) < 128:
                continue
            try:
                char.encode("cp949")
            except UnicodeEncodeError:
                bad.append(f"{char!r} (U+{ord(char):04X})")
        self.assertEqual(bad, [], f"CP949 로 표현할 수 없는 글자: {bad}")


if __name__ == "__main__":
    unittest.main()
