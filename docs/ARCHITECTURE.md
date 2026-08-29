# 구조와 확장 계획

이 문서는 **나중에 Cubase 직접 제어를 붙이게 될 때 어디를 건드리면 되는지**
를 남겨 두기 위한 것입니다.

## 층 구조

```
    말로 요청                  MCP 도구            음악 계산            내보내기
  "시티팝 8마디"  ──▶  server.py  ──▶  theory/ + render.py  ──▶  targets.py  ──▶  .mid
                                              │                      │
                                        humanize.py            (여기만 갈아끼우면 됨)
```

핵심은 **편곡을 만드는 일**과 **그걸 Cubase 에 넣는 일**을 갈라 둔 것입니다.
`render.build_arrangement()` 는 자기 결과가 어디로 갈지 전혀 모릅니다.
`targets.py` 만 그걸 압니다.

| 파일 | 하는 일 | 아래층을 아는가 |
|---|---|---|
| `theory/` | 코드·조성·보이싱·리듬 계산 | MIDI 를 모름 |
| `humanize.py` | 노트 목록에 연주 습관 적용 | MIDI Note 만 앎 |
| `render.py` | 위 셋을 합쳐 `MidiFile` 생성 | 출력 대상을 모름 |
| `midi/smf.py` | 표준 MIDI 파일 작성 | 음악 이론을 모름 |
| `targets.py` | 결과를 Cubase 로 보냄 | 여기서만 Cubase 를 앎 |
| `server.py` | MCP 도구 정의 | 전부 앎 |

## Cubase 를 직접 제어하려면

### 전제: Cubase 에는 트랙 내용을 편집하는 공식 API 가 없습니다

Reaper 의 ReaScript 같은 것이 Cubase 에는 없습니다. Pro 든 Elements 든 같습니다.
Cubase 12+ 의 **MIDI Remote API** 는 자바스크립트로 짜지만, 하드웨어 컨트롤러를
파라미터에 매핑하고 **메뉴 명령을 실행**하는 용도입니다. 파트 안의 노트를
읽거나 쓰는 기능은 없습니다.

그래서 "보이싱을 drop2 로 바꿔줘" 같은 편집은 **어느 경로를 택하든 Cubase 밖에서
계산** 해야 합니다. 직접 제어냐 아니냐는 결국 *사용자가 드래그를 몇 번 하느냐*
의 문제이지, 기능의 한계가 아닙니다. 이 판단이 아래 우선순위의 근거입니다.

### 등록되어 있는 경로

`targets.list_targets()` 로 확인할 수 있고, MCP 도구 `list_capabilities` 의
`delivery_targets` 에도 그대로 나옵니다.

| 경로 | 상태 | 할 수 있는 것 | 필요 조건 | 한계 |
|---|---|---|---|---|
| `midi_file` | **동작** | 생성 | 없음 | 드래그 필요 |
| `virtual_port` | 계획 | 생성, 실시간 | loopMIDI + python-rtmidi | 곡 길이만큼 실제 시간 소요. 편집 불가 |
| `midi_remote` | 계획 | 트랜스포트/명령 | Cubase 12+ + 가상 포트 + 스크립트 설치 | 노트 편집 불가 |
| `ui_automation` | 계획 | 생성, 명령 | AutoHotkey v2 | 창 배치·언어에 민감해 잘 깨짐 |
| `project_file` | **계획 없음** | (편집) | 비공개 포맷 해석 | 프로젝트 손상 위험. 구현하지 않음 |

### 새 경로를 추가하는 방법

`targets.py` 에 클래스 하나를 더하고 `register()` 하면 끝입니다.
다른 파일은 건드릴 필요가 없습니다.

```python
class VirtualPortTarget:
    name = "virtual_port"
    korean = "가상 MIDI 포트"
    description = "..."
    capabilities = ("create", "realtime")
    requirements = ["loopMIDI", "python-rtmidi"]

    def available(self) -> Availability:
        # 포트가 실제로 열리는지 확인해서 Availability(ok=..., todo=[...]) 반환
        ...

    def deliver(self, arrangement, **options) -> dict:
        # arrangement.midi 의 노트를 시간 순으로 실제 연주
        ...

register(VirtualPortTarget())
```

계획 단계의 경로를 빈 껍데기로 두지 않고 `PlannedTarget` 으로 등록해 둔 이유는,
사용자가 그걸 골랐을 때 **"무엇이 있어야 되는지"를 정확히 알려주기** 위해서입니다.
조용히 실패하거나 "지원하지 않음" 한 줄만 뱉는 것보다 낫습니다.

## 반대 방향: Cubase 안의 내용을 고치려면

지금은 없는 기능입니다. 필요한 것:

1. **MIDI 읽기** (`midi/smf.py` 에 파서 추가)
   테스트용 파서(`tests/smf_reader.py`)가 이미 있으므로 이를 다듬어 올리면 됩니다.
2. **분석** — 읽은 노트에서 코드를 추정하고 (`theory/` 재사용), 리듬을 뽑아냄
3. **부분 교체** — "리듬은 두고 보이싱만", "코드는 두고 리듬만" 같은 조합

사용자 흐름은 이렇게 됩니다:

```
Cubase 파트를 폴더로 드래그  ──▶  읽기 + 분석  ──▶  일부만 교체  ──▶  새 .mid
```

`virtual_port` 나 `ui_automation` 이 붙으면 양 끝의 드래그가 사라지지만,
가운데 계산은 그대로입니다. 그래서 이 순서로 만드는 것이 맞습니다.

## 휴머나이즈를 확장하려면

`humanize.py` 의 `PROFILES` 에 `HumanizeProfile` 을 하나 추가하면 됩니다.
적용 로직(`humanize_notes`)은 노트 목록만 받으므로 코드/베이스/아르페지오
어디에나 똑같이 걸립니다.

지금 다루는 요소: 메트릭 악센트, 백비트, 성부 균형(최고음/최저음/속음),
코드 굴림, 선율 리드, 밀당(레이드백/푸시), 정박 정확도, 세기-타이밍 결합,
길이 흔들림, 레가토.

아직 없는 것(넣는다면 여기): 프레이즈 단위 크레셴도, 페달, 실제 연주에서 뽑은
그루브 템플릿, 손 크기에 따른 넓은 보이싱의 굴림 증가.
