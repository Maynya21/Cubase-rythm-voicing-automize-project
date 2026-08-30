"""Cubase 창을 직접 조작하는 계층.

Cubase 는 외부에서 트랙을 다루는 공식 API 가 없으므로, 사람이 하는 조작
(창 활성화 → 단축키 → 파일 대화상자에 경로 입력)을 대신 수행합니다.

**설계 원칙**

1. *실제 키 입력은 위험합니다.* 엉뚱한 창에 들어가면 되돌리기 어려운 일이
   벌어집니다. 그래서 모든 단계 앞에 "지금 앞에 있는 창이 정말 Cubase 인가"
   를 다시 확인하고, 아니면 즉시 멈춥니다.
2. *플랫폼 의존 코드를 최소로 격리합니다.* 순서와 안전장치는 :mod:`.plan` 에
   있고 어떤 운영체제에서도 테스트할 수 있습니다. Windows API 를 실제로
   호출하는 부분은 :mod:`.win32` 하나뿐입니다.
3. *언어와 무관하게 동작해야 합니다.* Cubase 메뉴 이름은 한국어판/영문판이
   다르고 버전마다 바뀝니다. 그래서 메뉴를 더듬지 않고 **사용자가 지정한
   키 커맨드** 를 씁니다.
"""

from .plan import (BridgeError, Driver, Step, StepKind, describe, import_midi_plan,
                   run)

__all__ = ["BridgeError", "Driver", "Step", "StepKind", "describe",
           "import_midi_plan", "run"]
