"""테스트용 가짜 드라이버.

Windows 가 아닌 곳에서도 조작 순서와 안전장치를 전부 확인하기 위한 것입니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FakeDriver:
    """실제로는 아무 키도 보내지 않고 기록만 남깁니다."""

    window: Optional[str] = "Cubase Elements 14 - 내 프로젝트"
    #: 각 호출 시점에 맨 앞에 있을 창 제목. 비면 window 를 씁니다.
    foreground_sequence: List[str] = field(default_factory=list)
    dialogs: List[Optional[str]] = field(default_factory=lambda: ["열기", "가져오기 옵션"])
    focus_succeeds: bool = True

    actions: List[str] = field(default_factory=list)
    slept: float = 0.0
    _front_index: int = 0
    _dialog_index: int = 0

    def find_cubase(self) -> Optional[str]:
        self.actions.append("find")
        return self.window

    def focus_cubase(self) -> bool:
        self.actions.append("focus")
        return self.focus_succeeds

    def foreground_title(self) -> str:
        if self.foreground_sequence:
            index = min(self._front_index, len(self.foreground_sequence) - 1)
            self._front_index += 1
            return self.foreground_sequence[index]
        return self.window or ""

    def send_keys(self, keys: str) -> None:
        self.actions.append(f"key:{keys}")

    def type_text(self, text: str) -> None:
        self.actions.append(f"type:{text}")

    def wait_for_dialog(self, timeout: float) -> Optional[str]:
        found = (self.dialogs[self._dialog_index]
                 if self._dialog_index < len(self.dialogs) else None)
        self._dialog_index += 1
        self.actions.append(f"dialog:{found}")
        return found

    def sleep(self, seconds: float) -> None:
        self.slept += seconds
