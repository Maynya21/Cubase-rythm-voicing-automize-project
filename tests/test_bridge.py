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
        # 실제로 확인된 원인이라 프로젝트 여부가 첫 번째 확인 항목입니다.
        self.assertIn("프로젝트", message)
        self.assertIn("Import MIDI File", message)

    def test_message_box_is_quoted_back(self):
        """Cubase 가 되물으면 무엇을 묻는지 그대로 보여 주어야 합니다.

        열린 프로젝트가 없을 때 Cubase 는 파일 창 대신 '새 프로젝트를
        만들까요?' 라고 묻습니다. 그 창을 파일 창으로 오인하면 경로를 거기
        입력하고 Enter 가 [Create] 를 눌러 버립니다.
        """
        class AskingDriver(FakeDriver):
            last_message_box = ("Cubase Elements",
                                "Do you want to create a new project?")

        driver = AskingDriver(dialogs=[None])
        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, driver)
        message = str(ctx.exception)
        self.assertIn("Do you want to create a new project?", message)
        self.assertIn("열린 프로젝트가 없어서", message)
        self.assertFalse(any(a.startswith("type:") for a in driver.actions))

    def test_other_message_boxes_are_reported_too(self):
        class AskingDriver(FakeDriver):
            last_message_box = ("Cubase Elements", "저장하지 않은 변경 사항이 있습니다")

        with self.assertRaises(BridgeError) as ctx:
            run(self.steps, AskingDriver(dialogs=[None]))
        self.assertIn("저장하지 않은 변경 사항", str(ctx.exception))


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
                             key_sent=True, new_windows=["MIDI 파일 가져오기"],
                             is_file_dialog=True)
        self.assertTrue(out["ok"])
        self.assertEqual(out["window_that_appeared"], "MIDI 파일 가져오기")

    def test_unconfirmed_window_is_not_success(self):
        """파일 창임을 확인하지 못한 창을 성공으로 보면 안 됩니다.

        예전에는 창 클래스가 표준 대화상자가 아니면 검사를 건너뛰고 성공으로
        처리했습니다. Cubase 자체 양식의 메시지 창이 그렇게 통과해서,
        '새 프로젝트를 만들까요?' 창을 파일 창이라고 보고했습니다.
        """
        out = self.interpret(cubase_window="Cubase Elements 14", focused=True,
                             foreground_before="Cubase Elements 14",
                             key_sent=True, new_windows=["뭔가 떴음"])
        self.assertFalse(out["ok"], "확인하지 못한 창을 성공으로 보고했습니다")
        self.assertEqual(out["checks"][-1][1], False)

    def test_non_standard_message_box_is_caught(self):
        """Cubase 자체 양식이라 클래스가 #32770 이 아니어도 잡아야 합니다."""
        out = self.interpret(cubase_window="Cubase Elements Project - Untitled1",
                             cubase_process="Cubase14.exe", focused=True,
                             foreground_before="Cubase Elements Project - Untitled1",
                             key_sent=True, new_windows=["Cubase Elements"],
                             is_file_dialog=False, dialog_class="SteinbergWindow",
                             asked="Do you want to create a new project?")
        self.assertFalse(out["ok"])
        self.assertIn("프로젝트를 먼저", " ".join(out["advice"]))

    def test_every_step_is_reported(self):
        out = self.interpret(cubase_window="X", focused=True,
                             foreground_before="Cubase", key_sent=True,
                             new_windows=["열기"], is_file_dialog=True)
        names = [name for name, _ok, _detail in out["checks"]]
        for expected in ("Cubase 창 찾기", "키 전달", "새 창이 떴는가"):
            self.assertIn(expected, names)
        for name, ok, detail in out["checks"]:
            self.assertTrue(name and isinstance(ok, bool) and detail)

    def test_message_box_instead_of_file_dialog(self):
        """열린 프로젝트가 없으면 Cubase 가 파일 창 대신 되묻습니다.

        키는 잘 먹힌 것이므로 '키가 안 먹힌다' 로 보고하면 안 됩니다.
        """
        out = self.interpret(
            cubase_window="Cubase Elements", cubase_process="Cubase14.exe",
            focused=True, foreground_before="Cubase Elements", key_sent=True,
            new_windows=["Cubase Elements"], is_file_dialog=False,
            asked="Do you want to create a new project?")
        self.assertFalse(out["ok"])
        self.assertIn("단축키는 잘 먹혔습니다", out["cause"])
        self.assertTrue(any("프로젝트를 먼저" in a for a in out["advice"]))
        # 키 전달까지는 성공으로 표시되어야 합니다.
        delivered = dict((name, ok) for name, ok, _ in out["checks"])
        self.assertTrue(delivered["키 전달"])
        self.assertFalse(delivered["그 창이 파일 선택 창인가"])

    def test_process_name_is_shown_when_known(self):
        out = self.interpret(cubase_window="내 곡", cubase_process="Cubase14.exe",
                             focused=True, foreground_before="내 곡",
                             key_sent=True, new_windows=["열기"], is_file_dialog=True)
        self.assertIn("Cubase14.exe", out["checks"][0][2])


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


class TestFocusFallback(unittest.TestCase):
    """Windows 는 뒤에서 도는 프로그램이 창을 앞으로 가져오는 것을 막습니다.

    그때 창은 활성화되지 않고 작업 표시줄만 깜빡입니다. 자동 활성화가 실패해도
    사용자가 직접 클릭해서 진행할 길이 있어야 합니다.
    """

    def setUp(self):
        self.path = a_midi_file()

    def test_plan_passes_the_wait_time_to_focus(self):
        steps = import_midi_plan(self.path, "shift+f12", wait_for_user=5)
        focus = next(s for s in steps if s.kind is StepKind.FOCUS)
        self.assertEqual(focus.seconds, 5)
        self.assertIn("직접 클릭", focus.what)

    def test_driver_that_accepts_wait_gets_it(self):
        seen = {}

        class WaitingDriver(FakeDriver):
            def focus_cubase(self, wait_for_user=0.0):
                seen["wait"] = wait_for_user
                return True

        run(import_midi_plan(self.path, "shift+f12", wait_for_user=7),
            WaitingDriver())
        self.assertEqual(seen["wait"], 7)

    def test_old_style_driver_still_works(self):
        """사용자 대기를 지원하지 않는 드라이버도 그대로 돌아가야 합니다."""
        driver = FakeDriver()          # focus_cubase() 에 인자가 없습니다
        result = run(import_midi_plan(self.path, "shift+f12", wait_for_user=3),
                     driver)
        self.assertIn("focus", driver.actions)
        self.assertFalse(result["dry_run"])

    def test_focus_failure_explains_the_windows_restriction(self):
        with self.assertRaises(BridgeError) as ctx:
            run(import_midi_plan(self.path, "shift+f12"),
                FakeDriver(focus_succeeds=False))
        message = str(ctx.exception)
        self.assertIn("깜빡", message)
        self.assertIn("직접 클릭", message)


class TestInputStructLayout(unittest.TestCase):
    """SendInput 에 넘기는 구조체 크기.

    INPUT 은 공용체라 크기가 가장 큰 멤버(MOUSEINPUT)를 따릅니다. 키보드
    멤버만 선언하면 크기를 작게 계산하고, 그 값을 cbSize 로 넘기면 SendInput 이
    ERROR_INVALID_PARAMETER(87) 로 **아무것도 보내지 않습니다.** 실제로 그
    증상을 겪어서 회귀 테스트로 고정합니다.
    """

    def test_input_size_matches_windows(self):
        import ctypes
        from cubase_mcp.bridge import win32
        self.assertEqual(ctypes.sizeof(win32._Input), win32.EXPECTED_INPUT_SIZE)

    def test_union_is_as_large_as_the_mouse_member(self):
        import ctypes
        from cubase_mcp.bridge import win32
        self.assertGreaterEqual(ctypes.sizeof(win32._InputUnion),
                                ctypes.sizeof(win32._MouseInput))

    def test_member_sizes(self):
        import ctypes
        from cubase_mcp.bridge import win32
        self.assertEqual(ctypes.sizeof(win32._KeyBdInput), 24)
        self.assertEqual(ctypes.sizeof(win32._MouseInput), 32)

    def test_fixed_width_types_are_used(self):
        """wintypes 는 운영체제마다 크기가 달라 개발 중 검증이 안 됩니다."""
        source = (Path(__file__).resolve().parent.parent
                  / "cubase_mcp" / "bridge" / "win32.py").read_text(encoding="utf-8")
        struct_part = source[source.index("class _KeyBdInput"):
                             source.index("def _key_input")]
        self.assertNotIn("wintypes.", struct_part)


class TestCubaseWindowSelection(unittest.TestCase):
    """어떤 창을 Cubase 로 볼 것인가.

    이 프로그램의 창 제목이 'Cubase MCP 스튜디오' 라서, 제목만 보면 브라우저와
    명령 프롬프트까지 Cubase 로 잡힙니다. 실제로 그 때문에 Edge 를 앞으로
    가져와 키를 보낸 적이 있습니다.
    """

    def test_our_own_windows_are_excluded_by_process(self):
        from cubase_mcp.bridge.win32 import NEVER_CUBASE
        for process in ("msedge.exe", "chrome.exe", "cmd.exe", "python.exe"):
            self.assertIn(process, NEVER_CUBASE)

    def test_titles_that_would_fool_a_title_only_check(self):
        """이 제목들은 전부 'Cubase' 를 포함하지만 Cubase 가 아닙니다."""
        for title in ["Cubase MCP 스튜디오 - 개인 - Microsoft Edge",
                      "Cubase MCP Studio",
                      "Maynya21/Cubase-rythm-voicing-automize-project - Chrome"]:
            self.assertTrue(looks_like_cubase(title),
                            "제목만으로는 구분할 수 없어야 합니다(그래서 프로세스로 봅니다)")

    def test_real_cubase_process_names_match(self):
        from cubase_mcp.bridge.win32 import PROCESS_MARKERS
        for process in ("cubase14.exe", "Cubase14.exe".lower(), "nuendo13.exe"):
            self.assertTrue(any(m in process for m in PROCESS_MARKERS), process)


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
