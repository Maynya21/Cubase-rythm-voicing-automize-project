"""Cubase 창 조작 계층 테스트.

실제로 키를 보내는 부분은 Windows 에서만 돌지만, **순서와 안전장치** 는
가짜 드라이버로 어디서든 검증할 수 있게 만들었습니다. 여기서 막지 못하면
남의 프로젝트에 키가 쏟아집니다.
"""

import tempfile
import unittest
from pathlib import Path

from cubase_mcp.bridge import BridgeError, StepKind, describe, import_midi_plan, run
from cubase_mcp.bridge.fake import FakeDriver
from cubase_mcp.bridge.plan import is_dangerous_window, looks_like_cubase
from cubase_mcp.bridge.win32 import VK, Win32Driver, parse_keys


def a_midi_file() -> Path:
    folder = Path(tempfile.mkdtemp(prefix="bridge-"))
    path = folder / "test.mid"
    path.write_bytes(b"MThd")
    return path


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.path = a_midi_file()

    def test_plan_order(self):
        kinds = [s.kind for s in import_midi_plan(self.path, "ctrl+alt+i")]
        # 키를 보내기 전에 반드시 창을 확인해야 합니다.
        self.assertLess(kinds.index(StepKind.ASSERT_FRONT), kinds.index(StepKind.KEY))
        self.assertIn(StepKind.WAIT_DIALOG, kinds)
        self.assertIn(StepKind.TYPE, kinds)

    def test_plan_types_the_absolute_path(self):
        steps = import_midi_plan(self.path, "ctrl+alt+i")
        typed = [s.text for s in steps if s.kind is StepKind.TYPE]
        self.assertEqual(typed, [str(self.path)])

    def test_requires_an_absolute_path(self):
        with self.assertRaises(BridgeError):
            import_midi_plan(Path("relative.mid"), "ctrl+alt+i")

    def test_requires_the_file_to_exist(self):
        with self.assertRaises(BridgeError):
            import_midi_plan(self.path.parent / "missing.mid", "ctrl+alt+i")

    def test_missing_key_explains_how_to_set_it(self):
        with self.assertRaises(BridgeError) as ctx:
            import_midi_plan(self.path, "")
        self.assertIn("키보드 단축키", str(ctx.exception))

    def test_skipping_the_options_dialog(self):
        steps = import_midi_plan(self.path, "ctrl+alt+i", confirm_options=False)
        self.assertEqual(sum(1 for s in steps if s.kind is StepKind.WAIT_DIALOG), 1)

    def test_describe_is_human_readable(self):
        lines = describe(import_midi_plan(self.path, "ctrl+alt+i"))
        self.assertTrue(lines[0].startswith("1. "))
        self.assertTrue(any("Cubase" in line for line in lines))


class TestSafety(unittest.TestCase):
    """엉뚱한 창에 키를 보내지 않는지."""

    def setUp(self):
        self.path = a_midi_file()
        self.steps = import_midi_plan(self.path, "ctrl+alt+i")

    def test_happy_path(self):
        driver = FakeDriver()
        result = run(self.steps, driver)
        self.assertIn("key:ctrl+alt+i", driver.actions)
        self.assertIn(f"type:{self.path}", driver.actions)
        self.assertFalse(result["dry_run"])

    def test_dry_run_sends_nothing(self):
        driver = FakeDriver()
        result = run(self.steps, driver, dry_run=True)
        self.assertEqual(driver.actions, [])
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["steps"])

    def test_stops_when_cubase_is_not_running(self):
        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, FakeDriver(window=None))
        self.assertIn("찾지 못했습니다", str(ctx.exception))

    def test_stops_when_focus_fails(self):
        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, FakeDriver(focus_succeeds=False))
        self.assertIn("앞으로 가져오지", str(ctx.exception))

    def test_stops_when_another_window_is_in_front(self):
        """포커스가 다른 앱으로 넘어가면 즉시 멈춰야 합니다."""
        driver = FakeDriver(foreground_sequence=["메모장"])
        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, driver)
        self.assertIn("메모장", str(ctx.exception))
        self.assertNotIn("key:ctrl+alt+i", driver.actions)

    def test_stops_if_focus_is_lost_midway(self):
        """확인은 한 번으로 끝나면 안 됩니다. 중간에 뺏겨도 잡아야 합니다."""
        driver = FakeDriver(foreground_sequence=[
            "Cubase Elements 14",      # 첫 확인 통과
            "다른 프로그램",             # 키 보내기 직전에 뺏김
        ])
        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, driver)
        self.assertIn("다른 프로그램", str(ctx.exception))
        self.assertNotIn("key:ctrl+alt+i", driver.actions)

    def test_stops_when_the_file_dialog_never_appears(self):
        driver = FakeDriver(dialogs=[None])
        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, driver)
        self.assertIn("뜨지 않았습니다", str(ctx.exception))
        # 대화상자가 없는데 경로를 입력하면 프로젝트 창에 글자가 들어갑니다.
        self.assertFalse(any(a.startswith("type:") for a in driver.actions))

    def test_optional_options_dialog_may_be_absent(self):
        """가져오기 옵션 창은 설정에 따라 안 뜰 수 있습니다."""
        driver = FakeDriver(dialogs=["열기", None])
        result = run(self.steps, driver)
        self.assertTrue(result["log"])

    def test_nothing_is_typed_before_the_dialog_opens(self):
        driver = FakeDriver()
        run(self.steps, driver)
        dialog_at = driver.actions.index("dialog:열기")
        type_at = next(i for i, a in enumerate(driver.actions) if a.startswith("type:"))
        self.assertLess(dialog_at, type_at)


class TestDangerousWindows(unittest.TestCase):
    """작업 전환 창 같은 곳에 파일 경로를 입력한 적이 있어 넣은 회귀 테스트."""

    def setUp(self):
        self.path = a_midi_file()
        self.steps = import_midi_plan(self.path, "ctrl+alt+m")

    def test_task_switcher_is_dangerous(self):
        for title in ["작업 전환", "Task Switching", "작업 보기",
                      "Program Manager", "사용자 계정 컨트롤", "", "   "]:
            self.assertTrue(is_dangerous_window(title), title)

    def test_real_dialogs_are_not_dangerous(self):
        for title in ["열기", "Open", "가져오기 옵션", "Cubase Elements 14"]:
            self.assertFalse(is_dangerous_window(title), title)

    def test_stops_when_the_task_switcher_appears_instead_of_a_dialog(self):
        """단축키가 Cubase 에 안 먹히면 작업 전환 창이 뜰 수 있습니다."""
        driver = FakeDriver(dialogs=["작업 전환"])
        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, driver)
        message = str(ctx.exception)
        self.assertIn("작업 전환", message)
        self.assertIn("F 키", message)          # 대안을 알려 주어야 합니다
        # 무엇보다 경로를 입력하지 않았어야 합니다.
        self.assertFalse(any(a.startswith("type:") for a in driver.actions))

    def test_never_types_into_a_dangerous_window(self):
        """대화상자는 통과시키되, 위험한 창은 반드시 막아야 합니다."""
        driver = FakeDriver(
            dialogs=["열기"],
            foreground_sequence=["Cubase Elements 14",   # 첫 확인
                                 "Cubase Elements 14",   # 키 보내기 직전
                                 "작업 전환"],            # 경로 입력 직전에 뒤바뀜
        )
        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, driver)
        self.assertIn("작업 전환", str(ctx.exception))
        self.assertFalse(any(a.startswith("type:") for a in driver.actions))

    def test_process_based_detection_is_preferred(self):
        """Cubase 14 는 창 제목에 'Cubase' 가 없을 수 있습니다.

        드라이버가 실행 파일로 판별할 수 있으면 제목이 무엇이든 그쪽을 믿어야
        합니다.
        """
        class ProcessAwareDriver(FakeDriver):
            def foreground_is_cubase(self):
                return True                      # 제목과 무관하게 Cubase

        driver = ProcessAwareDriver(window="제목없음1",         # 'Cubase' 없음
                                    foreground_sequence=["제목없음1"])
        result = run(self.steps, driver)
        self.assertIn("key:ctrl+alt+m", driver.actions)
        self.assertTrue(result["log"])

    def test_process_detection_can_also_reject(self):
        class ProcessAwareDriver(FakeDriver):
            def foreground_is_cubase(self):
                return False                     # 제목은 Cubase 같아도 아님

        with self.assertRaises(BridgeError):
            run(self.steps, ProcessAwareDriver(window="Cubase Elements 14"))

    def test_never_types_into_a_window_with_no_title(self):
        driver = FakeDriver(
            dialogs=["열기"],
            foreground_sequence=["Cubase Elements 14", "Cubase Elements 14", ""],
        )
        with self.assertRaises(BridgeError):
            run(self.steps, driver)
        self.assertFalse(any(a.startswith("type:") for a in driver.actions))

    def test_missing_dialog_explains_what_to_check(self):
        driver = FakeDriver(dialogs=[None])
        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, driver)
        message = str(ctx.exception)
        self.assertIn("Import MIDI File", message)
        self.assertIn("F 키", message)


class TestProbeInterpretation(unittest.TestCase):
    """진단 결과를 사람이 읽는 판정으로 바꾸는 부분.

    '아무 일도 안 일어난다' 는 원인이 여러 가지라, 어디까지 됐는지 단계별로
    구분해서 알려 주어야 합니다.
    """

    def interpret(self, **report):
        from cubase_mcp.server import _interpret_key_probe
        base = {"shortcut": "shift+f12"}
        base.update(report)
        return _interpret_key_probe(base)

    def test_cubase_not_found(self):
        out = self.interpret(cubase_window=None, problem="Cubase 창을 찾지 못했습니다.")
        self.assertFalse(out["ok"])
        self.assertFalse(out["checks"][0][1])

    def test_input_blocked_by_privilege_is_called_out(self):
        """Cubase 가 관리자 권한이면 키가 조용히 막힙니다. 그걸 짚어야 합니다."""
        out = self.interpret(
            cubase_window="Cubase Elements 14", focused=True,
            foreground_before="Cubase Elements 14", key_sent=False,
            problem="Windows 가 키 입력을 차단했습니다.\n  1. 관리자 권한 없이 실행하세요.")
        self.assertFalse(out["ok"])
        self.assertIn("권한", out["cause"])
        self.assertTrue(out["advice"])

    def test_key_delivered_but_nothing_happened(self):
        out = self.interpret(cubase_window="Cubase Elements 14", focused=True,
                             foreground_before="Cubase Elements 14",
                             key_sent=True, new_windows=[])
        self.assertFalse(out["ok"])
        names = [name for name, ok, _ in out["checks"] if ok]
        self.assertIn("키 전달", names)          # 여기까지는 성공했음을 보여야 합니다
        self.assertTrue(any("할당" in a for a in out["advice"]))

    def test_success_reports_the_window(self):
        out = self.interpret(cubase_window="Cubase Elements 14", focused=True,
                             foreground_before="Cubase Elements 14",
                             key_sent=True, new_windows=["MIDI 파일 가져오기"])
        self.assertTrue(out["ok"])
        self.assertEqual(out["window_that_appeared"], "MIDI 파일 가져오기")

    def test_every_step_is_reported(self):
        out = self.interpret(cubase_window="X", focused=True,
                             foreground_before="Cubase", key_sent=True,
                             new_windows=["열기"])
        self.assertEqual(len(out["checks"]), 4)
        for name, ok, detail in out["checks"]:
            self.assertTrue(name and isinstance(ok, bool) and detail)


class TestWindowMatching(unittest.TestCase):
    def test_recognises_cubase_titles(self):
        for title in ["Cubase Elements 14 - Untitled",
                      "Cubase Pro 13", "Nuendo 13", "cubase le"]:
            self.assertTrue(looks_like_cubase(title), title)

    def test_rejects_other_windows(self):
        for title in ["메모장", "", "Chrome", "Cubase MCP 스튜디오 - Chrome"[:6]]:
            self.assertFalse(looks_like_cubase(title) and "cubase" not in title.lower(),
                             title)
        self.assertFalse(looks_like_cubase("메모장"))
        self.assertFalse(looks_like_cubase(""))


class TestKeyParsing(unittest.TestCase):
    def test_combinations(self):
        self.assertEqual(parse_keys("ctrl+alt+i"), ([VK["ctrl"], VK["alt"]], VK["i"]))
        self.assertEqual(parse_keys("enter"), ([], VK["enter"]))
        self.assertEqual(parse_keys("F5"), ([], VK["f5"]))

    def test_rejects_unknown_names(self):
        for bad in ["ctrl+ㄱ", "", "nope", "ctrl+alt"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_keys(bad)

    def test_driver_refuses_to_run_off_windows(self):
        import platform
        if platform.system() != "Windows":
            with self.assertRaises(RuntimeError) as ctx:
                Win32Driver()
            self.assertIn("Windows", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
