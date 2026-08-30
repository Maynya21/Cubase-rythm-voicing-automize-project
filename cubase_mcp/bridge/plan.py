"""조작 순서와 안전장치 — 운영체제와 무관한 부분.

키를 실제로 보내는 일은 :class:`Driver` 구현체가 합니다. 여기서는 **무엇을
어떤 순서로, 어떤 확인을 거쳐서** 할지만 정합니다. 덕분에 리눅스에서도
가짜 드라이버로 전 과정을 검증할 수 있습니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable


class BridgeError(RuntimeError):
    """조작을 안전하게 이어갈 수 없을 때. 메시지에 이유를 담습니다."""


class StepKind(str, Enum):
    FIND = "find"                 # Cubase 창 찾기
    FOCUS = "focus"               # 앞으로 가져오기
    ASSERT_FRONT = "assert_front"  # 지금 앞에 있는 창이 Cubase 인지 확인
    KEY = "key"                   # 키 조합 보내기
    TYPE = "type"                 # 글자 입력
    WAIT_DIALOG = "wait_dialog"   # 대화상자가 뜰 때까지 기다리기
    PAUSE = "pause"               # 잠깐 쉬기


@dataclass(frozen=True)
class Step:
    kind: StepKind
    #: 사람이 읽을 설명. 미리보기와 오류 메시지에 그대로 쓰입니다.
    what: str
    keys: Optional[str] = None
    text: Optional[str] = None
    seconds: float = 0.0
    timeout: float = 0.0
    optional: bool = False        # 실패해도 넘어갈 단계인지


@runtime_checkable
class Driver(Protocol):
    """운영체제별 구현이 채워야 할 최소한의 동작."""

    def find_cubase(self) -> Optional[str]:
        """Cubase 창을 찾아 제목을 돌려줍니다. 없으면 None."""

    def focus_cubase(self) -> bool:
        """Cubase 창을 앞으로 가져옵니다."""

    def foreground_title(self) -> str:
        """지금 맨 앞에 있는 창의 제목."""

    def send_keys(self, keys: str) -> None:
        """``"ctrl+alt+i"`` 같은 조합을 보냅니다."""

    def type_text(self, text: str) -> None:
        """글자를 그대로 입력합니다 (파일 경로 등)."""

    def wait_for_dialog(self, timeout: float) -> Optional[str]:
        """새 대화상자가 뜰 때까지 기다리고 제목을 돌려줍니다."""

    def sleep(self, seconds: float) -> None:
        ...


#: Cubase 창 제목에서 찾을 표시
CUBASE_MARKERS = ("cubase", "nuendo")

#: 기본 대기 시간 (초)
DEFAULT_DIALOG_TIMEOUT = 8.0

#: 절대로 글자를 넣으면 안 되는 창.
#: Alt 가 들어간 조합이 Cubase 에 먹히지 않으면 Windows 의 작업 전환 창이
#: 튀어나올 수 있는데, 여기에 파일 경로를 입력하면 엉뚱한 창으로 전환됩니다.
NEVER_TYPE_INTO = (
    "작업 전환", "task switching", "task view", "작업 보기",
    "program manager", "prog man", "시작 메뉴", "start menu",
    "windows 보안", "windows security", "사용자 계정 컨트롤",
    "user account control",
)


def is_dangerous_window(title: str) -> bool:
    """여기에 글자를 넣으면 예상 못 한 일이 벌어지는 창인지."""
    lowered = (title or "").strip().lower()
    if not lowered:
        return True                    # 제목 없는 창 = 정체 불명. 넣지 않습니다.
    return any(marker in lowered for marker in NEVER_TYPE_INTO)


def looks_like_cubase(title: str) -> bool:
    lowered = (title or "").lower()
    return any(marker in lowered for marker in CUBASE_MARKERS)


def front_is_cubase(driver: "Driver", title: Optional[str] = None) -> bool:
    """앞 창이 Cubase 인지. 드라이버가 실행 파일로 판별할 수 있으면 그쪽을 씁니다.

    Cubase 14 는 창 제목이 프로젝트 이름 위주라 'Cubase' 가 들어가지 않을 수
    있어서, 제목만 보면 잘못 판단합니다.

    ``title`` 을 넘기면 창 제목을 **다시 읽지 않습니다.** 두 번 읽으면 그 사이
    창이 바뀌었을 때 오류 메시지에 적히는 창과 실제로 검사한 창이 달라집니다.
    """
    checker = getattr(driver, "foreground_is_cubase", None)
    if callable(checker):
        return bool(checker())
    return looks_like_cubase(title if title is not None else driver.foreground_title())


def import_midi_plan(
    midi_path: Path | str,
    import_key: str,
    *,
    confirm_options: bool = True,
    dialog_timeout: float = DEFAULT_DIALOG_TIMEOUT,
) -> List[Step]:
    """MIDI 파일을 Cubase 로 가져오는 조작 순서를 만듭니다.

    메뉴를 더듬지 않고 사용자가 지정해 둔 키 커맨드를 씁니다. 메뉴 이름은
    한국어판/영문판이 다르고 버전마다 바뀌지만 키 커맨드는 그렇지 않습니다.

    Args:
        midi_path: 가져올 파일의 절대 경로.
        import_key: Cubase 에서 'MIDI 파일 가져오기' 에 할당한 키 조합.
        confirm_options: 가져오기 옵션 대화상자를 Enter 로 넘길지.
        dialog_timeout: 대화상자를 기다릴 최대 시간.
    """
    path = Path(midi_path)
    if not path.is_absolute():
        raise BridgeError(f"절대 경로가 필요합니다: {path}")
    if not path.is_file():
        raise BridgeError(f"파일이 없습니다: {path}")
    if not import_key or not import_key.strip():
        raise BridgeError(
            "Cubase 에서 'MIDI 파일 가져오기' 에 할당한 단축키를 알려 주셔야 합니다.\n"
            "Cubase 메뉴에서 [편집 > 키보드 단축키] 를 열고 'Import MIDI File'\n"
            "(한국어판은 'MIDI 파일 가져오기') 을 찾아 원하는 키를 지정한 뒤,\n"
            "그 키를 설정해 주세요. 예: ctrl+alt+i"
        )

    return [
        Step(StepKind.FIND, "Cubase 창 찾기"),
        Step(StepKind.FOCUS, "Cubase 를 앞으로 가져오기"),
        Step(StepKind.PAUSE, "창이 준비될 때까지 잠깐 기다리기", seconds=0.4),
        Step(StepKind.ASSERT_FRONT, "정말 Cubase 가 앞에 있는지 확인"),
        Step(StepKind.KEY, f"가져오기 단축키({import_key}) 누르기", keys=import_key),
        Step(StepKind.WAIT_DIALOG, "파일 선택 창이 뜨기를 기다리기",
             timeout=dialog_timeout),
        Step(StepKind.TYPE, f"경로 입력: {path.name}", text=str(path)),
        Step(StepKind.PAUSE, "입력이 반영될 때까지 기다리기", seconds=0.25),
        Step(StepKind.KEY, "Enter 로 파일 열기", keys="enter"),
        *([
            Step(StepKind.WAIT_DIALOG, "가져오기 옵션 창을 기다리기",
                 timeout=dialog_timeout, optional=True),
            Step(StepKind.PAUSE, "옵션 창이 그려질 때까지 기다리기", seconds=0.4),
            Step(StepKind.KEY, "Enter 로 옵션 확인", keys="enter", optional=True),
        ] if confirm_options else []),
        Step(StepKind.PAUSE, "가져오기가 끝나기를 기다리기", seconds=0.6),
    ]


def probe_key_plan(import_key: str,
                   dialog_timeout: float = DEFAULT_DIALOG_TIMEOUT) -> List[Step]:
    """단축키가 Cubase 에 먹히는지만 확인하는 순서.

    **글자를 하나도 입력하지 않습니다.** 키를 눌러 보고 무엇이 떴는지만
    보고합니다. 진짜 가져오기를 하기 전에 이걸로 먼저 확인하면, 키가 틀렸을 때
    엉뚱한 창에 경로가 들어가는 일이 없습니다.
    """
    if not import_key or not import_key.strip():
        raise BridgeError("확인할 단축키를 알려 주세요")
    return [
        Step(StepKind.FIND, "Cubase 창 찾기"),
        Step(StepKind.FOCUS, "Cubase 를 앞으로 가져오기"),
        Step(StepKind.PAUSE, "창이 준비될 때까지 기다리기", seconds=0.4),
        Step(StepKind.ASSERT_FRONT, "정말 Cubase 가 앞에 있는지 확인"),
        Step(StepKind.KEY, f"단축키({import_key}) 눌러 보기", keys=import_key),
        Step(StepKind.WAIT_DIALOG, "무엇이 뜨는지 보기", timeout=dialog_timeout,
             optional=True),
    ]


def describe(steps: Sequence[Step]) -> List[str]:
    """미리보기용 설명 목록. 실제로 실행하기 전에 보여 줍니다."""
    return [f"{i + 1}. {step.what}" + ("  (실패해도 계속)" if step.optional else "")
            for i, step in enumerate(steps)]


def run(steps: Sequence[Step], driver: Driver, *,
        dry_run: bool = False) -> Dict[str, Any]:
    """조작을 실행합니다.

    ``dry_run`` 이면 아무것도 보내지 않고 무엇을 할지만 돌려줍니다.
    중간에 Cubase 가 앞에 없어지면 **즉시 멈춥니다.** 뒤늦게 다른 창에
    키를 쏟아붓지 않기 위해서입니다.
    """
    log: List[str] = []
    if dry_run:
        return {"dry_run": True, "steps": describe(steps), "log": log}

    title: Optional[str] = None
    for index, step in enumerate(steps, start=1):
        try:
            if step.kind is StepKind.FIND:
                title = driver.find_cubase()
                if not title:
                    raise BridgeError(
                        "Cubase 창을 찾지 못했습니다. Cubase 가 실행 중이고 "
                        "최소화되어 있지 않은지 확인해 주세요."
                    )
                log.append(f"창 찾음: {title}")

            elif step.kind is StepKind.FOCUS:
                if not driver.focus_cubase():
                    raise BridgeError(
                        "Cubase 를 앞으로 가져오지 못했습니다. 다른 창이 "
                        "전체 화면이거나 관리자 권한으로 실행 중일 수 있습니다."
                    )

            elif step.kind is StepKind.ASSERT_FRONT:
                front = driver.foreground_title()
                if not front_is_cubase(driver, front):
                    raise BridgeError(
                        f"앞에 있는 창이 Cubase 가 아닙니다: {front!r}\n"
                        f"안전을 위해 아무 키도 보내지 않고 멈췄습니다."
                    )
                log.append(f"확인: {front}")

            elif step.kind is StepKind.KEY:
                _guard(driver, step)
                driver.send_keys(step.keys or "")
                log.append(f"키: {step.keys}")

            elif step.kind is StepKind.TYPE:
                _guard(driver, step, dialog_ok=True)
                driver.type_text(step.text or "")
                log.append(f"입력: {step.text}")

            elif step.kind is StepKind.WAIT_DIALOG:
                found = driver.wait_for_dialog(step.timeout)
                if found and is_dangerous_window(found):
                    raise BridgeError(
                        f"단축키를 눌렀더니 파일 창이 아니라 {found!r} 이 떴습니다.\n"
                        f"Cubase 가 그 키를 받지 못했다는 뜻입니다. 아무것도 "
                        f"입력하지 않고 멈췄습니다.\n"
                        f"Alt 가 들어간 조합은 Windows 가 먼저 가로챌 수 있습니다. "
                        f"Cubase 의 키 커맨드를 shift+f12 같은 F 키 계열로 바꾼 뒤 "
                        f"다시 알려 주세요."
                    )
                if not found and not step.optional:
                    raise BridgeError(_no_dialog_message(driver, step))
                log.append(f"대화상자: {found or '없음(건너뜀)'}")

            elif step.kind is StepKind.PAUSE:
                driver.sleep(step.seconds)

        except BridgeError:
            raise
        except Exception as exc:                 # pragma: no cover - 방어적
            if step.optional:
                log.append(f"{step.what} 실패(무시): {exc}")
                continue
            raise BridgeError(f"{index}번째 단계 '{step.what}' 에서 실패했습니다: {exc}") from exc

    return {"dry_run": False, "steps": describe(steps), "log": log, "window": title}


def _no_dialog_message(driver: Driver, step: Step) -> str:
    """파일 창이 안 뜬 이유를 최대한 구체적으로 설명합니다.

    Cubase 가 메시지 창으로 되물은 경우(예: 열린 프로젝트가 없을 때
    "새 프로젝트를 만들까요?")에는 그 내용을 그대로 보여 줍니다. 원인을
    알려면 Cubase 가 무엇을 묻고 있는지가 가장 중요한 단서입니다.
    """
    message_box = getattr(driver, "last_message_box", None)
    if message_box:
        title, text = message_box
        hint = ""
        lowered = (text or "").lower()
        if "new project" in lowered or "새 프로젝트" in text:
            hint = ("\n\n열린 프로젝트가 없어서 Cubase 가 되묻고 있습니다. "
                    "Cubase 에서 프로젝트를 먼저 열거나 만든 뒤 다시 시도해 주세요.")
        return (f"파일 창 대신 Cubase 가 이렇게 묻고 있습니다.\n"
                f"  [{title}] {text}\n"
                f"아무것도 입력하지 않고 멈췄습니다. 그 창을 직접 처리해 주세요."
                f"{hint}")
    return (f"'{step.what}' 에서 파일 창이 뜨지 않았습니다.\n"
            f"확인할 것:\n"
            f"  1. Cubase 에 프로젝트가 열려 있는지 (열린 프로젝트가 없으면 "
            f"가져오기가 동작하지 않습니다)\n"
            f"  2. [편집 > 키보드 단축키] 에서 'Import MIDI File' 에 그 키가 "
            f"지정되어 있고 [할당] 을 눌렀는지\n"
            f"  3. 그 키를 Cubase 에서 직접 눌렀을 때 파일 창이 뜨는지")


def _guard(driver: Driver, step: Step, dialog_ok: bool = False) -> None:
    """키나 글자를 보내기 직전에 대상 창을 다시 확인합니다.

    포커스는 언제든 바뀔 수 있습니다(알림 팝업, 사용자가 다른 창 클릭 등).
    한 번 확인하고 끝내면 그 뒤 입력이 엉뚱한 곳으로 갑니다.

    파일 대화상자는 제목이 Cubase 가 아니므로 ``dialog_ok`` 로 통과시키는데,
    그때도 **위험한 창은 반드시 막습니다.** 예전에는 여기가 느슨해서 작업
    전환 창에 파일 경로가 입력된 적이 있습니다.
    """
    front = driver.foreground_title()
    if is_dangerous_window(front):
        raise BridgeError(
            f"'{step.what}' 직전에 확인해 보니 앞에 있는 창이 "
            f"{front or '제목 없는 창'!r} 입니다.\n"
            f"여기에 입력하면 엉뚱한 일이 벌어지므로 멈췄습니다.\n"
            f"단축키가 Cubase 에 전달되지 않았을 가능성이 큽니다. "
            f"Alt 가 들어간 조합은 Windows 가 가로챌 수 있으니 "
            f"F 키 계열(예: shift+f12)로 바꿔 보세요."
        )
    if front_is_cubase(driver, front):
        return
    if dialog_ok:
        return
    raise BridgeError(
        f"'{step.what}' 직전에 확인해 보니 앞에 있는 창이 Cubase 가 아닙니다"
        f"({front!r}). 안전을 위해 멈췄습니다."
    )
