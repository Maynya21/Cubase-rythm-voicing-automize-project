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

#: 실행 파일 이름에서 찾을 표시. 제목보다 이쪽이 확실합니다.
#: Cubase 14 는 창 제목이 프로젝트 이름 위주라 'Cubase' 가 없을 수 있습니다.
PROCESS_MARKERS = ("cubase", "nuendo")

#: 절대로 Cubase 가 아닌 실행 파일.
#: 이 프로그램의 창 제목이 'Cubase MCP 스튜디오' 라서, 제목만 보면 브라우저와
#: 명령 프롬프트까지 Cubase 로 잡혔습니다. 실제로 그 때문에 Edge 를 앞으로
#: 가져와 키를 보냈습니다.
NEVER_CUBASE = (
    "msedge.exe", "chrome.exe", "firefox.exe", "whale.exe", "iexplore.exe",
    "opera.exe", "brave.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "windowsterminal.exe", "conhost.exe", "python.exe", "pythonw.exe",
    "py.exe", "explorer.exe", "code.exe", "notepad.exe",
)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# 창 활성화 관련
SW_RESTORE = 9
SW_SHOW = 5
ASFW_ANY = -1
SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x0002

#: 파일 창 제목에 흔히 들어가는 말 (클래스 확인이 안 될 때의 보조 수단)
FILE_DIALOG_WORDS = ("열기", "가져오기", "불러오기", "open", "import", "browse",
                     "선택", "select")

#: 파일 이름을 적는 칸이 있는 창만 파일 대화상자로 봅니다.
#: 메시지 창("새 프로젝트를 만들까요?")도 같은 #32770 클래스라서, 이것으로
#: 구분하지 않으면 메시지 창에 파일 경로를 입력하게 됩니다.
INPUT_CLASSES = ("edit", "combobox", "comboboxex32", "richedit", "richedit20w")

_IS_WINDOWS = hasattr(ctypes, "windll")

if _IS_WINDOWS:                                  # pragma: no cover - Windows 전용
    # use_last_error=True 라야 SendInput 이 막혔을 때 이유를 알 수 있습니다.
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
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


# 구조체는 **고정 폭 타입** 으로 적습니다. ctypes.wintypes 의 DWORD/LONG 은
# 운영체제에 따라 크기가 달라져서(리눅스에서는 c_ulong 이 8바이트), Windows 의
# 실제 레이아웃과 어긋날 수 있고 개발 중에 검증할 수도 없습니다.
WORD = ctypes.c_uint16
DWORD = ctypes.c_uint32
LONG = ctypes.c_int32
#: ULONG_PTR — 포인터 크기의 부호 없는 정수. 실제 포인터가 아니라 값입니다.
ULONG_PTR = (ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8
             else ctypes.c_uint32)


class _KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", WORD), ("wScan", WORD),
                ("dwFlags", DWORD), ("time", DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _MouseInput(ctypes.Structure):
    """쓰지는 않지만 **반드시 선언해야 합니다.**

    Win32 의 INPUT 은 공용체(union)이고 그 크기는 가장 큰 멤버인 MOUSEINPUT 을
    따릅니다. 키보드 멤버만 선언하면 ctypes 가 INPUT 을 작게 계산하고,
    그 크기를 cbSize 로 넘기면 SendInput 이 ERROR_INVALID_PARAMETER(87) 로
    아무것도 보내지 않습니다. 실제로 그 증상을 겪었습니다.
    """
    _fields_ = [("dx", LONG), ("dy", LONG),
                ("mouseData", DWORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeyBdInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", DWORD), ("union", _InputUnion)]


#: Windows x64 에서의 sizeof(INPUT). 이 값이 어긋나면 SendInput 이 87 로 실패합니다.
EXPECTED_INPUT_SIZE = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28


def _key_input(vk: int, unicode_char: int = 0, up: bool = False) -> _Input:
    flags = KEYEVENTF_KEYUP if up else 0
    if unicode_char:
        flags |= KEYEVENTF_UNICODE
    return _Input(type=INPUT_KEYBOARD,
                  union=_InputUnion(ki=_KeyBdInput(
                      wVk=0 if unicode_char else vk,
                      wScan=unicode_char,
                      dwFlags=flags, time=0, dwExtraInfo=0)))


if _IS_WINDOWS:                                  # pragma: no cover
    # 인자 형식을 명시해 두어야 ctypes 가 포인터를 올바로 넘깁니다.
    user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(_Input),
                                 ctypes.c_int)
    user32.SendInput.restype = ctypes.c_uint


#: SendInput 이 실패하는 대표적인 이유
ERROR_ACCESS_DENIED = 5        # 권한 문제 (상대가 관리자 권한)
ERROR_INVALID_PARAMETER = 87   # 구조체 크기 등이 어긋남


class InputBlocked(RuntimeError):
    """키 입력이 운영체제에 의해 차단됐을 때."""


def _send(inputs: List[_Input]) -> None:                # pragma: no cover
    """키 이벤트를 보냅니다. **보내진 개수를 반드시 확인합니다.**

    Cubase 가 관리자 권한으로 실행 중이면 Windows 가 낮은 권한 프로세스의
    입력을 차단합니다(UIPI). 그때 SendInput 은 오류를 던지지 않고 조용히 0 을
    돌려주기 때문에, 확인하지 않으면 '키를 보냈는데 아무 일도 안 일어나는'
    상태가 됩니다. 실제로 그 증상을 겪었습니다.
    """
    array = (_Input * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(_Input))
    if sent != len(inputs):
        code = ctypes.get_last_error()
        if code == ERROR_ACCESS_DENIED:
            raise InputBlocked(
                "Windows 가 키 입력을 차단했습니다.\n"
                "Cubase 가 '관리자 권한으로 실행' 중이면, 관리자가 아닌 "
                "프로그램은 Cubase 에 키를 보낼 수 없습니다.\n"
                "해결 방법 (둘 중 하나):\n"
                "  1. Cubase 를 관리자 권한 없이 실행하세요 (보통 이게 낫습니다).\n"
                "     Cubase 바로 가기 우클릭 > 속성 > 호환성 에서 "
                "'관리자 권한으로 이 프로그램 실행' 체크를 해제.\n"
                "  2. 또는 스튜디오/Claude Desktop 도 관리자 권한으로 실행하세요."
            )
        if code == ERROR_INVALID_PARAMETER:
            raise InputBlocked(
                f"키 입력 구조가 잘못됐습니다 (오류 87, INPUT 크기 "
                f"{ctypes.sizeof(_Input)}). 프로그램 오류이니 알려 주세요."
            )
        raise InputBlocked(
            f"키 입력이 전달되지 않았습니다 (보낸 것 {sent}/{len(inputs)}, "
            f"오류 코드 {code})."
        )


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
    def _process_name(self, hwnd: int) -> str:       # pragma: no cover
        """그 창을 소유한 실행 파일 이름 (예: ``Cubase14.exe``)."""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False,
                                      pid.value)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(260)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer,
                                                   ctypes.byref(size)):
                return buffer.value.rsplit("\\", 1)[-1]
        finally:
            kernel32.CloseHandle(handle)
        return ""

    def _is_cubase_window(self, hwnd: int, title: str) -> bool:   # pragma: no cover
        """실행 파일로 판별합니다. 제목은 마지막 수단입니다."""
        process = self._process_name(hwnd).lower()
        if process and any(m in process for m in PROCESS_MARKERS):
            return True
        if process in NEVER_CUBASE:
            return False
        return looks_like_cubase(title)

    def _is_cubase_process(self, hwnd: int) -> bool:              # pragma: no cover
        process = self._process_name(hwnd).lower()
        return bool(process) and any(m in process for m in PROCESS_MARKERS)

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
        """Cubase 의 **주 창** 을 찾습니다.

        Cubase 는 믹스콘솔, 트랜스포트 등 창이 여러 개입니다. 그중 가장 큰
        창을 주 창으로 봅니다. 작은 도구 창을 앞으로 가져오면 단축키가
        먹히지 않을 수 있기 때문입니다.
        """
        windows = self._windows()
        # 실행 파일로 확인된 창이 하나라도 있으면 **그것들만** 봅니다.
        # 제목 판별로 넘어가면 이 프로그램의 창('Cubase MCP 스튜디오')까지
        # 후보에 들어와 브라우저를 앞으로 가져오게 됩니다.
        candidates = [(hwnd, title) for hwnd, title in windows
                      if self._is_cubase_process(hwnd)]
        if not candidates:
            candidates = [(hwnd, title) for hwnd, title in windows
                          if self._is_cubase_window(hwnd, title)]
        if not candidates:
            return None

        def area(hwnd: int) -> int:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return 0
            return max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)

        hwnd, title = max(candidates, key=lambda item: area(item[0]))
        self._hwnd = hwnd
        return title

    def cubase_windows(self) -> List[str]:           # pragma: no cover
        """찾은 Cubase 창들 (진단용). 실행 파일로 확인된 것만."""
        windows = self._windows()
        found = [(hwnd, title) for hwnd, title in windows
                 if self._is_cubase_process(hwnd)]
        if not found:
            found = [(hwnd, title) for hwnd, title in windows
                     if self._is_cubase_window(hwnd, title)]
        return [f"{title} [{self._process_name(hwnd)}]" for hwnd, title in found]

    def foreground_is_cubase(self) -> bool:          # pragma: no cover
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        if self._is_cubase_process(hwnd):
            return True
        if self._process_name(hwnd).lower() in NEVER_CUBASE:
            return False
        return looks_like_cubase(self.foreground_title())

    def focus_cubase(self, wait_for_user: float = 0.0) -> bool:   # pragma: no cover
        """Cubase 를 앞으로 가져옵니다.

        Windows 는 포그라운드 창을 바꿀 권한을 엄격히 제한합니다. 사용자가
        브라우저에서 버튼을 누른 상황이면 포그라운드 프로세스는 브라우저이고,
        뒤에서 도는 이 프로그램은 권한이 없습니다. 그때 Windows 는 창을
        활성화하는 대신 **작업 표시줄을 깜빡이기만** 합니다.

        알려진 우회를 순서대로 시도하고, 그래도 안 되면 ``wait_for_user`` 초
        동안 사용자가 직접 Cubase 를 클릭하기를 기다립니다. 사람이 클릭하면
        권한 문제가 애초에 생기지 않습니다.
        """
        hwnd = getattr(self, "_hwnd", None)
        if hwnd is None and not self.find_cubase():
            return False
        hwnd = self._hwnd

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        for attempt in (self._focus_attach, self._focus_unlock, self._focus_switch):
            try:
                attempt(hwnd)
            except Exception:
                continue
            time.sleep(0.18)
            if self.foreground_is_cubase():
                return True

        if wait_for_user > 0:
            deadline = time.monotonic() + wait_for_user
            while time.monotonic() < deadline:
                time.sleep(0.25)
                if self.foreground_is_cubase():
                    return True
        return False

    def _focus_attach(self, hwnd: int) -> None:       # pragma: no cover
        """**현재 포그라운드 창의 스레드** 에 우리 입력 큐를 붙입니다.

        포그라운드 권한을 가진 쪽은 지금 앞에 있는 창의 스레드입니다. 예전에는
        대상(Cubase) 스레드에 붙였는데, 그러면 권한이 넘어오지 않습니다.
        """
        user32.AllowSetForegroundWindow(ASFW_ANY)
        front = user32.GetForegroundWindow()
        front_thread = user32.GetWindowThreadProcessId(front, None) if front else 0
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        ours = kernel32.GetCurrentThreadId()

        attached = []
        for thread in {front_thread, target_thread}:
            if thread and thread != ours and user32.AttachThreadInput(ours, thread, True):
                attached.append(thread)
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            for thread in attached:
                user32.AttachThreadInput(ours, thread, False)

    def _focus_unlock(self, hwnd: int) -> None:       # pragma: no cover
        """포그라운드 잠금 시간을 잠시 0 으로 두고 다시 시도합니다."""
        previous = ctypes.c_uint(0)
        user32.SystemParametersInfoW(SPI_GETFOREGROUNDLOCKTIMEOUT, 0,
                                     ctypes.byref(previous), 0)
        try:
            user32.SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, 0,
                                         ctypes.c_void_p(0), SPIF_SENDCHANGE)
            user32.AllowSetForegroundWindow(ASFW_ANY)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            user32.SystemParametersInfoW(
                SPI_SETFOREGROUNDLOCKTIMEOUT, 0,
                ctypes.c_void_p(previous.value), SPIF_SENDCHANGE)

    def _focus_switch(self, hwnd: int) -> None:       # pragma: no cover
        """마지막 수단. Alt+Tab 이 쓰는 것과 같은 전환입니다."""
        user32.SwitchToThisWindow(hwnd, True)

    def foreground_title(self) -> str:                # pragma: no cover
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def _children(self, hwnd: int) -> List[Tuple[str, str]]:   # pragma: no cover
        """자식 컨트롤의 (클래스, 글자) 목록."""
        out: List[Tuple[str, str]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(child, _param):
            klass = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(child, klass, 128)
            length = user32.GetWindowTextLengthW(child)
            text = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(child, text, length + 1)
            out.append((klass.value, text.value))
            return True

        user32.EnumChildWindows(hwnd, callback, 0)
        return out

    def _is_file_dialog(self, hwnd: int) -> bool:     # pragma: no cover
        """파일 이름을 적는 칸이 있으면 파일 대화상자로 봅니다."""
        return any(klass.lower() in INPUT_CLASSES
                   for klass, _text in self._children(hwnd))

    def _message_text(self, hwnd: int) -> str:        # pragma: no cover
        """메시지 창이 무엇을 묻고 있는지 (진단용)."""
        parts = [text.strip() for klass, text in self._children(hwnd)
                 if klass.lower() == "static" and text.strip()]
        return " ".join(parts)

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

        표준 대화상자 클래스(``#32770``)만으로는 부족합니다. Cubase 의
        "새 프로젝트를 만들까요?" 같은 **메시지 창도 같은 클래스** 라서,
        그것을 파일 창으로 오인하면 경로를 거기 입력하고 Enter 가 기본 버튼을
        눌러 버립니다. 그래서 파일 이름을 적는 칸이 있는지까지 확인합니다.

        파일 창이 아닌 메시지 창을 만나면 그 내용을 :attr:`last_message_box` 에
        남깁니다. 무엇을 묻고 있는지 사용자에게 그대로 보여 주기 위해서입니다.
        """
        self.last_message_box: Optional[Tuple[str, str]] = None
        before = self.foreground_title()
        deadline = time.monotonic() + max(0.1, timeout)
        while time.monotonic() < deadline:
            time.sleep(0.15)
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                continue
            current = self.foreground_title()
            if not current or current == before:
                continue
            if is_dangerous_window(current):
                return current       # 호출하는 쪽에서 위험한 창으로 걸러냅니다
            klass = self.foreground_class()
            if klass == DIALOG_CLASS or any(word in current.lower()
                                            for word in FILE_DIALOG_WORDS):
                if self._is_file_dialog(hwnd):
                    return current
                # 메시지 창입니다. 무엇을 묻는지 기억해 두고 계속 기다립니다.
                self.last_message_box = (current, self._message_text(hwnd))
                continue
        return None

    def sleep(self, seconds: float) -> None:          # pragma: no cover
        time.sleep(max(0.0, seconds))

    # -- 진단 --------------------------------------------------------------
    def is_elevated(self) -> Optional[bool]:          # pragma: no cover
        """지금 이 프로그램이 관리자 권한인지 (모르면 None)."""
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return None

    def snapshot(self) -> List[Tuple[int, str]]:      # pragma: no cover
        return self._windows()

    def new_windows(self, before: List[Tuple[int, str]]) -> List[str]:
        """스냅샷 이후 새로 생긴 창들.

        모달 대화상자가 앞으로 나오지 않는 경우도 있어서, 앞 창만 보는 것보다
        확실합니다.
        """
        seen = {hwnd for hwnd, _title in before}
        return [title for hwnd, title in self._windows()
                if hwnd not in seen and title.strip()]

    def diagnose(self, shortcut: str, wait: float = 2.5,
                 wait_for_user: float = 0.0) -> dict:  # pragma: no cover
        """단축키를 눌러 보고 무슨 일이 있었는지 자세히 보고합니다.

        글자는 입력하지 않습니다. '아무 일도 안 일어난다' 의 원인을 좁히려면
        어디까지 됐는지 알아야 하므로 단계별 상태를 모두 담습니다.
        """
        report: dict = {"shortcut": shortcut, "elevated": self.is_elevated()}
        report["cubase_window"] = self.find_cubase()
        report["all_cubase_windows"] = self.cubase_windows()
        if not report["cubase_window"]:
            report["problem"] = (
                "Cubase 창을 찾지 못했습니다. Cubase 가 실행 중이고 최소화되어 "
                "있지 않은지 확인해 주세요.")
            return report
        report["cubase_process"] = self._process_name(getattr(self, "_hwnd", 0))

        report["focused"] = self.focus_cubase(wait_for_user=wait_for_user)
        report["foreground_before"] = self.foreground_title()
        report["foreground_class_before"] = self.foreground_class()
        report["foreground_process_before"] = self._process_name(
            user32.GetForegroundWindow())
        if not self.foreground_is_cubase():
            report["problem"] = (
                f"Cubase 를 앞으로 가져오지 못했습니다. "
                f"지금 앞에 있는 창: {report['foreground_before']!r}\n"
                f"Windows 는 뒤에서 도는 프로그램이 창을 앞으로 가져오는 것을 "
                f"막습니다(그래서 Cubase 가 깜빡이기만 합니다).\n"
                f"[Cubase 를 직접 클릭할 시간 주기] 를 켜고 다시 눌러 보세요. "
                f"카운트다운 동안 Cubase 창을 클릭하시면 됩니다.")
            report["focus_denied"] = True
            return report

        before = self.snapshot()
        try:
            self.send_keys(shortcut)
            report["key_sent"] = True
        except InputBlocked as exc:
            report["key_sent"] = False
            report["problem"] = str(exc)
            return report

        self.last_message_box = None
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            time.sleep(0.2)
            fresh = self.new_windows(before)
            if fresh:
                report["new_windows"] = fresh
                hwnd = user32.GetForegroundWindow()
                if hwnd and self.foreground_class() == DIALOG_CLASS:
                    report["is_file_dialog"] = self._is_file_dialog(hwnd)
                    if not report["is_file_dialog"]:
                        report["asked"] = self._message_text(hwnd)
                break
        report.setdefault("new_windows", [])
        report["foreground_after"] = self.foreground_title()
        report["foreground_class_after"] = self.foreground_class()
        return report
