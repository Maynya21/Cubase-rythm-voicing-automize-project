"""출력 대상(delivery target) 레지스트리.

만든 편곡을 **어디로 내보낼지** 를 갈아끼울 수 있게 분리한 층입니다.
지금 실제로 동작하는 건 MIDI 파일 하나뿐이지만, 나중에 Cubase 를 직접
제어하는 경로가 열리면 이 파일에 클래스 하나를 더하는 것으로 끝나도록
설계했습니다. :func:`build_arrangement` 는 대상이 무엇인지 전혀 모릅니다.

왜 이렇게 나눠 두는가
---------------------
Cubase 는 외부에서 트랙 내용을 편집하는 공식 API 가 없습니다. 대신 우회로가
몇 가지 있는데, 각각 필요 조건과 위험도가 다릅니다. 어느 쪽이 쓸 만해질지
지금은 알 수 없으므로, **편곡을 만드는 일** 과 **그걸 Cubase 에 넣는 일** 을
갈라 두었습니다. 계획 중인 경로도 이름/필요 조건/할 수 있는 일을 미리
등록해 두어, 사용자가 골랐을 때 "무엇이 있어야 되는지" 를 정확히 알려줍니다.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .config import SETTINGS, unique_path
from .midi.smf import write as write_midi
from .render import ArrangementResult

#: 대상이 할 수 있는 일
#: - ``create``    : 새 내용을 Cubase 로 보냄
#: - ``edit``      : Cubase 안에 이미 있는 내용을 고침
#: - ``transport`` : 재생/정지/녹음 같은 조작
#: - ``realtime``  : 실시간 연주로 보냄 (드래그 불필요)
CAPABILITIES = ("create", "edit", "transport", "realtime")


@runtime_checkable
class DeliveryTarget(Protocol):
    """새 출력 경로를 추가하려면 이 모양만 맞추면 됩니다."""

    name: str
    korean: str
    description: str
    capabilities: tuple
    requirements: List[str]

    def available(self) -> "Availability":
        """지금 이 환경에서 쓸 수 있는지."""

    def deliver(self, arrangement: ArrangementResult, **options: Any) -> Dict[str, Any]:
        """편곡을 실제로 내보내고 결과를 설명하는 dict 를 돌려줍니다."""


@dataclass
class Availability:
    ok: bool
    reason: str = ""
    #: 사용자가 직접 해야 할 준비 (설치, 설정 등)
    todo: List[str] = field(default_factory=list)


class TargetUnavailable(RuntimeError):
    """대상을 지금 쓸 수 없을 때. 무엇이 필요한지 메시지에 담습니다."""


# --------------------------------------------------------------------------- #
# 1. MIDI 파일 (지금 동작하는 유일한 경로)
# --------------------------------------------------------------------------- #

class MidiFileTarget:
    """표준 MIDI 파일로 저장합니다.

    Cubase 의 모든 에디션(Elements 포함)과 모든 버전에서 동일하게 동작하는
    유일한 경로입니다. 비공식 수단에 기대지 않으므로 업데이트로 깨지지 않습니다.
    """

    name = "midi_file"
    korean = "MIDI 파일"
    description = ("`.mid` 파일로 저장합니다. Cubase 트랙 위로 드래그하거나 "
                   "[파일 > 가져오기 > MIDI 파일] 로 불러옵니다.")
    capabilities = ("create",)
    requirements: List[str] = []

    def available(self) -> Availability:
        return Availability(ok=True)

    def deliver(self, arrangement: ArrangementResult, *,
                filename: Optional[str] = None,
                subfolder: Optional[str] = None,
                default_stem: str = "chords",
                **_: Any) -> Dict[str, Any]:
        name = filename or f"{default_stem}.mid"
        if not name.lower().endswith(".mid"):
            name += ".mid"
        path = unique_path(SETTINGS.resolve(name, subfolder))
        write_midi(arrangement.midi, str(path))
        return {
            "target": self.name,
            "file": str(path),
            "filename": path.name,
            "how_to_import": (
                f"Cubase 에서 '{path.name}' 을 프로젝트 창의 트랙 위로 드래그하거나 "
                f"[파일 > 가져오기 > MIDI 파일] 로 불러오세요. 가져오기 창에서 "
                f"'템포 트랙 가져오기'를 끄면 프로젝트 템포가 유지됩니다."
            ),
        }


# --------------------------------------------------------------------------- #
# 2. 아직 없는 경로들 — 이름/조건/한계를 미리 등록해 둡니다
# --------------------------------------------------------------------------- #

@dataclass
class PlannedTarget:
    """구현 전인 경로. 고르면 무엇이 필요한지 정확히 알려주고 멈춥니다.

    빈 껍데기를 만들어 두는 것보다, **왜 아직 안 되는지와 무엇이 있어야 되는지**
    를 사실대로 담아 두는 편이 낫다고 판단했습니다.
    """

    name: str
    korean: str
    description: str
    capabilities: tuple
    requirements: List[str]
    blockers: List[str] = field(default_factory=list)
    probe: Optional[str] = None          # 설치 여부를 볼 파이썬 모듈 이름
    probe_binary: Optional[str] = None   # 설치 여부를 볼 실행 파일 이름

    def available(self) -> Availability:
        todo = list(self.requirements)
        if self.probe and importlib.util.find_spec(self.probe) is None:
            todo.append(f"파이썬 패키지 '{self.probe}' 설치 필요")
        if self.probe_binary and shutil.which(self.probe_binary) is None:
            todo.append(f"'{self.probe_binary}' 실행 파일을 찾을 수 없음")
        return Availability(ok=False, reason="아직 구현되지 않았습니다.", todo=todo)

    def deliver(self, arrangement: ArrangementResult, **options: Any) -> Dict[str, Any]:
        state = self.available()
        raise TargetUnavailable(
            f"'{self.korean}' 경로는 아직 쓸 수 없습니다.\n"
            f"필요한 것: " + " / ".join(state.todo) + "\n"
            f"한계: " + " / ".join(self.blockers) + "\n"
            f"지금은 'midi_file' 을 쓰세요."
        )


PLANNED = [
    PlannedTarget(
        name="virtual_port",
        korean="가상 MIDI 포트 (실시간 연주)",
        description=(
            "가상 MIDI 케이블로 Cubase 에 실시간 연주해 넣습니다. Cubase 트랙을 "
            "녹음 대기시켜 두면 드래그 없이 바로 녹음됩니다."
        ),
        capabilities=("create", "realtime"),
        requirements=[
            "loopMIDI 설치 (Windows용 무료 가상 MIDI 케이블)",
            "python-rtmidi 파이썬 패키지",
            "Cubase 에서 해당 포트를 MIDI 입력으로 켜고 트랙 녹음 대기",
        ],
        blockers=[
            "실시간이라 곡 길이만큼 실제 시간이 걸립니다",
            "이미 있는 트랙을 고치지는 못하고 새로 녹음만 됩니다",
        ],
        probe="rtmidi",
    ),
    PlannedTarget(
        name="midi_remote",
        korean="Cubase MIDI Remote 스크립트",
        description=(
            "Cubase 12 이상의 MIDI Remote API 용 스크립트를 만들어, 가상 포트로 "
            "Cubase 의 메뉴 명령(퀀타이즈/트랜스포즈/실행취소 등)을 실행합니다."
        ),
        capabilities=("transport",),
        requirements=[
            "Cubase 12 이상 (스튜디오 메뉴에 'MIDI Remote' 가 있어야 함)",
            "loopMIDI 등 가상 MIDI 포트",
            "생성된 스크립트를 Cubase MIDI Remote 폴더에 설치",
        ],
        blockers=[
            "MIDI Remote API 는 노트 데이터를 읽거나 쓸 수 없습니다 "
            "(컨트롤러 매핑과 명령 실행 전용)",
            "따라서 '보이싱을 바꿔줘' 같은 편집은 이 경로로는 불가능합니다",
        ],
        probe="rtmidi",
    ),
    PlannedTarget(
        name="ui_automation",
        korean="키보드/메뉴 자동화",
        description=(
            "AutoHotkey 로 Cubase 창에 단축키와 메뉴 클릭을 보내 파일 가져오기 "
            "같은 반복 작업을 대신합니다."
        ),
        capabilities=("create", "transport"),
        requirements=[
            "AutoHotkey v2 설치 (Windows)",
            "Cubase 단축키가 기본값이어야 함",
        ],
        blockers=[
            "창 배치·언어·버전이 바뀌면 쉽게 깨집니다",
            "의도치 않은 곳을 클릭할 수 있어 되돌리기 어려운 조작에는 부적합합니다",
        ],
        probe_binary="AutoHotkey.exe",
    ),
    PlannedTarget(
        name="project_file",
        korean="프로젝트 파일(.cpr) 직접 편집",
        description="Cubase 프로젝트 파일을 직접 읽고 쓰는 방식입니다.",
        capabilities=("create", "edit"),
        requirements=["비공개 포맷 리버스 엔지니어링"],
        blockers=[
            "포맷이 공개되어 있지 않고 버전마다 다릅니다",
            "잘못 쓰면 프로젝트가 손상됩니다. 권장하지 않으며 구현 계획도 없습니다",
        ],
    ),
]


# --------------------------------------------------------------------------- #
# 레지스트리
# --------------------------------------------------------------------------- #

_REGISTRY: Dict[str, Any] = {}


def register(target: Any) -> None:
    """새 출력 경로를 등록합니다. 실제 구현을 추가할 때 이것만 부르면 됩니다."""
    if not hasattr(target, "name"):
        raise ValueError("출력 대상에는 name 이 있어야 합니다")
    _REGISTRY[target.name] = target


register(MidiFileTarget())
for _planned in PLANNED:
    register(_planned)


def get_target(name: str) -> Any:
    key = (name or "midi_file").lower()
    if key not in _REGISTRY:
        raise ValueError(
            f"모르는 출력 대상입니다: {name!r} (사용 가능: {', '.join(_REGISTRY)})"
        )
    return _REGISTRY[key]


def list_targets() -> List[Dict[str, Any]]:
    out = []
    for target in _REGISTRY.values():
        state = target.available()
        out.append({
            "name": target.name,
            "korean": target.korean,
            "description": target.description,
            "capabilities": list(target.capabilities),
            "available": state.ok,
            "reason": state.reason,
            "requirements": state.todo,
            "limitations": list(getattr(target, "blockers", [])),
        })
    return out


def deliver(arrangement: ArrangementResult, target: str = "midi_file",
            **options: Any) -> Dict[str, Any]:
    """편곡을 지정한 경로로 내보냅니다."""
    chosen = get_target(target)
    state = chosen.available()
    if not state.ok:
        raise TargetUnavailable(
            f"'{chosen.korean}' 경로를 지금 쓸 수 없습니다: {state.reason}\n"
            + ("필요한 것: " + " / ".join(state.todo) if state.todo else "")
        )
    return chosen.deliver(arrangement, **options)


def environment_report() -> Dict[str, Any]:
    """어떤 경로가 왜 되는지/안 되는지 한눈에 보는 진단표."""
    return {
        "platform": platform.system(),
        "python": platform.python_version(),
        "output_dir": str(SETTINGS.output_dir),
        "output_dir_writable": _writable(SETTINGS.output_dir),
        "targets": list_targets(),
    }


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False
