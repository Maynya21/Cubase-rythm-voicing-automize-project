"""Windows 드라이버 — ctypes 로 Win32 API 를 직접 부릅니다.

추가 패키지 없이 표준 라이브러리만 씁니다. pywinauto 나 AutoHotkey 를 쓰지
않은 이유는, 선물로 줄 프로그램에서 설치 단계를 늘리고 싶지 않아서입니다.

키 입력은 ``SendInput`` 을 씁니다. 유니코드 경로(한글 폴더명)도 그대로
넣을 수 있어야 하는데, ``KEYEVENTF_UNICODE`` 가 그걸 해 줍니다.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import List, Optional, Tuple

from .plan import CUBASE_MARKERS, is_dangerous_window, looks_like_cubase

#: Windows 표준 대화상자의 창 클래스. 파일 열기/저장 창이 이것입니다.
DIALOG_CLASS = "#32770"

#: 파일 창 제목에 흔히 들어가는 말 (클래스 확인이 안 될 때의 보조 수단)
FILE_DIALOG_WORDS = ("열기", "가져오기", "불러오기", "open", "import", "browse",
                     "선택", "select")

_IS_WINDOWS = hasattr(ctypes, "windll")

if _IS_WINDOWS:                                  # pragma: no cover - Windows 전용
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:                                            # 다른 운영체제에서도 import 는 되게
    user32 = None
    kernel32 = None

# --- SendInput 구조체 -------------------------------------------------------
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

#: 키 이름 -> 가상 키 코드
VK = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "menu": 0x12,
    "shift": 0x10, "win": 0x5B,
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "tab": 0x09, "space": 0x20, "backspace": 0x08, "delete": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
    **{ch: ord(ch.upper()) for ch in "abcdefghijklmnopqrstuvwxyz0123456789"},
}

MODIFIERS = {"ctrl", "control", "alt", "menu", "shift", "win"}


class _KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyBdInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _InputUnion)]


def _key_input(vk: int, unicode_char: int = 0, up: bool = False) -> _Input:
    flags = KEYEVENTF_KEYUP if up else 0
    if unicode_char:
        flags |= KEYEVENTF_UNICODE
    return _Input(type=INPUT_KEYBOARD,
                  union=_InputUnion(ki=_KeyBdInput(
                      wVk=0 if unicode_char else vk,
                      wScan=unicode_char,
                      dwFlags=flags, time=0,
                      dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0)))))


def _send(inputs: List[_Input]) -> None:                # pragma: no cover
    array = (_Input * len(inputs))(*inputs)
    user32.SendInput(len(inputs), array, ctypes.sizeof(_Input))


def parse_keys(combo: str) -> Tuple[List[int], int]:
    """``"ctrl+alt+i"`` -> (조합키 코드들, 본 키 코드)."""
    parts = [p.strip().lower() for p in str(combo).split("+") if p.strip()]
    if not parts:
        raise ValueError("빈 키 조합입니다")
    unknown = [p for p in parts if p not in VK]
    if unknown:
        raise ValueError(
            f"모르는 키 이름입니다: {', '.join(unknown)}\n"
            f"쓸 수 있는 이름: {', '.join(sorted(VK))}"
        )
    modifiers = [VK[p] for p in parts[:-1] if p in MODIFIERS]
    main = VK[parts[-1]]
    if parts[-1] in MODIFIERS and len(parts) > 1:
        raise ValueError(f"조합키만으로는 안 됩니다: {combo!r}")
    return modifiers, main


class Win32Driver:
    """실제 Windows 조작. Windows 가 아니면 생성 시 오류를 냅니다."""

    def __init__(self) -> None:
        if not _IS_WINDOWS:
            raise RuntimeError(
                "이 기능은 Windows 에서만 동작합니다. "
                "macOS/Linux 는 아직 지원하지 않습니다."
            )

    # -- 창 찾기 -----------------------------------------------------------
    def _windows(self) -> List[Tuple[int, str]]:     # pragma: no cover
        found: List[Tuple[int, str]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _param):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                found.append((hwnd, buffer.value))
            return True

        user32.EnumWindows(callback, 0)
        return found

    def find_cubase(self) -> Optional[str]:          # pragma: no cover
        for hwnd, title in self._windows():
            if looks_like_cubase(title):
                self._hwnd = hwnd
                return title
        return None

    def focus_cubase(self) -> bool:                  # pragma: no cover
        hwnd = getattr(self, "_hwnd", None)
        if hwnd is None and not self.find_cubase():
            return False
        hwnd = self._hwnd
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)               # SW_RESTORE
        # 다른 프로세스 창을 앞으로 가져오려면 입력 스레드를 붙여야 합니다.
        target = user32.GetWindowThreadProcessId(hwnd, None)
        current = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(current, target, True)
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            user32.AttachThreadInput(current, target, False)
        time.sleep(0.15)
        return looks_like_cubase(self.foreground_title())

    def foreground_title(self) -> str:                # pragma: no cover
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def foreground_class(self) -> str:                # pragma: no cover
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value

    # -- 입력 --------------------------------------------------------------
    def release_modifiers(self) -> None:              # pragma: no cover
        """눌린 채 남아 있을 수 있는 조합키를 모두 놓습니다.

        Ctrl 이나 Alt 가 눌린 상태로 남으면 그다음 입력이 전부 단축키로
        해석됩니다. 실제로 작업 전환 창이 튀어나온 원인 중 하나입니다.
        """
        _send([_key_input(VK[name], up=True)
               for name in ("ctrl", "alt", "shift", "win")])
        time.sleep(0.02)

    def send_keys(self, keys: str) -> None:           # pragma: no cover
        modifiers, main = parse_keys(keys)
        self.release_modifiers()
        events = [_key_input(vk) for vk in modifiers]
        events.append(_key_input(main))
        _send(events)
        time.sleep(0.03)                              # 앱이 조합을 인식할 틈
        _send([_key_input(main, up=True),
               *(_key_input(vk, up=True) for vk in reversed(modifiers))])
        self.release_modifiers()
        time.sleep(0.05)

    def type_text(self, text: str) -> None:           # pragma: no cover
        # 조합키가 눌린 채면 글자가 전부 단축키로 해석됩니다.
        self.release_modifiers()
        events: List[_Input] = []
        for char in str(text):
            code = ord(char)
            events.append(_key_input(0, unicode_char=code))
            events.append(_key_input(0, unicode_char=code, up=True))
        if events:
            _send(events)
        time.sleep(0.05)

    def wait_for_dialog(self, timeout: float) -> Optional[str]:   # pragma: no cover
        """**파일 대화상자** 가 앞으로 나올 때까지 기다립니다.

        예전에는 '창 제목이 바뀌면 대화상자' 로 봤는데, 그러면 Windows 작업
        전환 창까지 대화상자로 오인합니다. 이제는 창 클래스가 표준 대화상자
        (``#32770``)인지 확인하고, 위험한 창이면 그 자리에서 실패로 처리합니다.
        """
        before = self.foreground_title()
        deadline = time.monotonic() + max(0.1, timeout)
        while time.monotonic() < deadline:
            time.sleep(0.15)
            current = self.foreground_title()
            if not current or current == before:
                continue
            if is_dangerous_window(current):
                return current       # 호출하는 쪽에서 위험한 창으로 걸러냅니다
            klass = self.foreground_class()
            if klass == DIALOG_CLASS:
                return current
            if any(word in current.lower() for word in FILE_DIALOG_WORDS):
                return current
            # 그 밖의 창은 계속 기다립니다 (Cubase 가 잠깐 제목을 바꾸는 경우 등)
        return None

    def sleep(self, seconds: float) -> None:          # pragma: no cover
        time.sleep(max(0.0, seconds))
