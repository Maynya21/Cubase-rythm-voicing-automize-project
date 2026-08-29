# Cubase 코드 · 보이싱 · 리듬 자동 생성 MCP

Cubase 트랙에 넣을 **코드 진행 / 보이싱 / 리듬**을 대화만으로 만들어 MIDI 파일로 뽑아주는
MCP 서버입니다. 만들어진 `.mid` 파일을 Cubase 트랙에 드래그하면 바로 편집할 수 있습니다.

> "C키 시티팝 8마디, 로즈 피아노로 drop2 보이싱에 16비트 커팅으로 뽑아줘"
> → `.mid` 파일 생성 → Cubase에 드래그 → 끝

## 왜 MIDI 파일 방식인가

Cubase **Elements** 를 포함한 모든 에디션에서 동일하게 동작하기 때문입니다.
Pro 전용 기능(Logical Editor 등)이나 비공식 스크립팅에 의존하지 않으므로,
버전이 올라가도 깨지지 않습니다.

---

## 필요한 것

**직접 찾아서 받아야 하는 건 파이썬 하나뿐입니다.** 나머지는 설치 스크립트가
인터넷에서 자동으로 가져옵니다.

| 무엇 | 어디서 | 누가 받나 |
|---|---|---|
| **Python 3.10 이상** | [python.org/downloads](https://www.python.org/downloads/) | **직접 받으셔야 합니다** |
| 이 프로그램 | 아래 1단계 (GitHub) | 직접 받으셔야 합니다 |
| `mcp` 패키지 | PyPI (파이썬 공식 저장소) | 설치 스크립트가 자동으로 |

이 프로그램이 쓰는 외부 패키지는 **`mcp` 딱 하나**입니다. 코드 검색으로 확인할 수
있습니다 — 나머지 import 는 전부 파이썬 표준 라이브러리입니다. MIDI 파일 작성기도
직접 구현되어 있어서 음악 관련 라이브러리를 따로 설치하지 않습니다.

`mcp` 를 설치하면 그게 쓰는 것들(pydantic, anyio, httpx 등)이 함께 따라오지만
전부 `pip` 가 알아서 처리하므로 신경 쓰실 것 없습니다.

> `mido` 는 개발용(테스트 교차검증)이라 설치하지 않아도 프로그램은 정상 동작합니다.

---

## 설치 (Windows) — 자동

### 1. 파일 받기

git 이 없어도 됩니다. 아래 링크를 눌러 ZIP 을 받고 압축을 풉니다.

**[⬇ ZIP 내려받기](https://github.com/Maynya21/Cubase-rythm-voicing-automize-project/archive/HEAD.zip)**

(또는 [저장소 페이지](https://github.com/Maynya21/Cubase-rythm-voicing-automize-project)
에서 초록색 **Code** 버튼 → **Download ZIP**)

압축을 푼 폴더는 **한 곳에 두고 옮기거나 지우지 마세요.**
(예: `C:\Users\사용자이름\Documents\CubaseMCP-프로그램`)
프로그램이 그 폴더를 계속 참조합니다.

<details>
<summary>git 이 있다면</summary>

```powershell
git clone https://github.com/Maynya21/Cubase-rythm-voicing-automize-project.git
```
</details>

### 2. Python 설치
[python.org](https://www.python.org/downloads/) 에서 **Python 3.10 이상**을 설치합니다.
설치 화면에서 **"Add Python to PATH"** 를 반드시 체크하세요. 이걸 놓치면 3단계에서
파이썬을 못 찾습니다.

### 3. `install-windows.bat` 더블클릭

> **잘 안 되면**: 압축 푼 폴더를 탐색기로 열고 주소창에 `cmd` 를 친 뒤 Enter,
> 검은 창에 아래 두 줄을 차례로 넣으셔도 똑같습니다.
> ```
> py -m pip install -e .
> py -m cubase_mcp.setup_wizard
> ```

그게 전부입니다. 스크립트가 알아서 합니다:

- 파이썬을 찾고 (`py` / `python` 둘 다 시도)
- 필요한 패키지를 인터넷에서 자동으로 받아 설치하고
- 테스트 MIDI 파일을 실제로 만들어 보고
- Claude Desktop 설정에 등록

> **기존 설정은 안전합니다.** 이미 쓰고 계신 다른 MCP 서버가 있어도 그대로 두고
> `cubase` 항목만 추가합니다. 손대기 전에 항상 백업(`claude_desktop_config.backup-날짜.json`)을
> 만들고, 설정 파일이 깨져 있으면 **아무것도 바꾸지 않고** 멈춥니다.

macOS / Linux 는 `install-macos-linux.sh` 를 실행하세요.

### 4. Claude Desktop 완전 종료 후 재실행

창만 닫으면 안 됩니다. 트레이 아이콘에서 종료하세요.
다시 켠 뒤 **"설치 잘 됐는지 확인해줘"** 라고 말하면 스스로 점검합니다.

<details>
<summary>수동으로 설치하려면</summary>

```powershell
cd 압축을-푼-폴더
pip install -e .
python -m cubase_mcp.setup_wizard          # 등록
python -m cubase_mcp.setup_wizard --dry-run  # 뭘 할지 보기만
python -m cubase_mcp.setup_wizard --remove   # 등록 해제
```

설정 파일을 직접 쓰고 싶다면 `%APPDATA%\Claude\claude_desktop_config.json` 에:

```json
{
  "mcpServers": {
    "cubase": {
      "command": "python",
      "args": ["-m", "cubase_mcp.server"],
      "env": {
        "CUBASE_MCP_OUTPUT_DIR": "C:\\Users\\사용자이름\\Documents\\CubaseMCP"
      }
    }
  }
}
```
</details>

### 5. Cubase 로 가져오기

만들어진 `.mid` 파일을 **Cubase 프로젝트 창의 트랙 위로 드래그**하거나,
`파일 > 가져오기 > MIDI 파일` 로 불러옵니다.

> 가져오기 대화상자에서 **"템포 트랙 가져오기"를 끄면** 프로젝트 템포가 그대로 유지됩니다.
> 켜면 파일에 기록된 템포·박자표·조표가 프로젝트에 적용됩니다.

---

## 사용법

대화로 요청하면 됩니다. 몇 가지 예:

| 하고 싶은 것 | 이렇게 말하면 됩니다 |
|---|---|
| 진행만 추천받기 | "A마이너로 감성적인 발라드 진행 8마디 추천해줘" |
| 보이싱 비교 | "Dm7 G7 Cmaj7 를 close / drop2 / rootless_a 로 비교해서 음이름 보여줘" |
| 파일 만들기 | "그 진행을 로즈로 drop2 보이싱, 보사노바 리듬, 132BPM으로 만들어줘" |
| 리하모나이즈 | "C Am F G 에 세컨더리 도미넌트랑 텐션 넣어서 다시 짜줘" |
| 조옮김 | "이 진행 Eb키로 옮겨줘" |
| 한 마디 2코드 | "코드 하나당 2박씩 넣어줘" |
| 연주감 조절 | "피아노 발라드 느낌으로 사람이 친 것처럼 해줘" |
| 그루브 조절 | "좀 더 뒤로 끄는(레이드백) 느낌으로" |
| 설치 점검 | "설치 잘 됐는지 확인해줘" |

### 도구 목록

| 도구 | 하는 일 |
|---|---|
| `list_capabilities` | 지원하는 보이싱/리듬/진행/베이스/악기 전체 목록 |
| `analyze_chords` | 코드 구성음 + 조성 안에서의 역할(로마숫자) 분석 |
| `suggest_progression` | 장르에 맞는 코드 진행 제안 (파일 X) |
| `preview_voicing` | 보이싱을 음이름으로 미리보기 (파일 X) |
| `reharmonize_progression` | 리하모나이제이션 (파일 X) |
| `transpose_progression` | 조옮김 (파일 X) |
| **`create_chord_midi`** | **코드+보이싱+리듬 → MIDI 파일 (핵심)** |
| `create_progression_midi` | 조성/장르만 주면 진행 생성부터 파일까지 한 번에 |
| `set_output_folder` | 저장 폴더 변경 |
| `list_output_files` | 만든 파일 목록 |
| `get_settings` | 현재 설정 확인 |
| `check_setup` | 설치 상태 자가 진단 |

---

## 지원 범위

### 보이싱 17종

| 이름 | 설명 |
|---|---|
| `close` | 클로즈 — 한 옥타브 안에 촘촘히 |
| `open` | 오픈 — 1-5-3(-7) 로 넓게 |
| `drop2` / `drop3` / `drop24` | 드롭 보이싱 — 재즈 컴핑 표준 |
| `shell` | 쉘 — 근음+3음+7음 (가이드톤) |
| `rootless_a` / `rootless_b` | 루트리스 (빌 에반스 A형/B형) |
| `quartal` | 4도 쌓기 — 모달/네오소울/시티팝 |
| `triad` | 3화음만 |
| `power` | 파워코드 |
| `pad` | 패드 — 낮은 근음+5도 위에 상성 |
| `guitar` | 기타 코드폼 근사 |
| `piano` | 피아노 양손 (왼손 근음/5도 + 오른손 클로즈) |
| `block` | 블록 (4-way close) |
| `cluster` | 클러스터 — 2도 뭉침 |
| `octaves` | 옥타브 유니즌 |

**보이스 리딩**이 기본으로 켜져 있어, 코드가 바뀔 때 손 움직임이 가장 작은
자리바꿈을 자동으로 고릅니다.

### 리듬 패턴 42종

기본(`whole`~`sixteenth`), 팝/발라드(`pop_ballad`, `charleston`, `push`, `pump8`, `four_floor`, `anthem`),
락(`rock8`, `rock_syncopa`, `power_drive`), 펑크·R&B·시티팝(`funk16`, `citypop16`, `neosoul`, `rnb_triplet`),
재즈(`jazz_four`, `jazz_comp`, `jazz_ballad`), 라틴(`bossa`, `samba`, `montuno`, `reggae`),
가스펠/로파이(`gospel`, `lofi`), 아르페지오(`arp_up`, `arp_updown`, `arp16`, `alberti`, `ballad_arp`, `broken`),
스트럼(`strum_down`, `strum_folk`, `strum16`), 다른 박자(`waltz`, `sixeight`, `twelve_eight`).

스윙, 휴머나이즈(타이밍/벨로시티), 스타카토 조절을 함께 쓸 수 있습니다.

### 휴머나이즈 프로파일 19종

무작위로 흔드는 것만으로는 사람처럼 들리지 않습니다. 실제 연주에는 **규칙적인
경향**이 있고 그게 더 중요합니다. 이 엔진이 다루는 것:

- **메트릭 악센트** — 1박 > 3박 > 2·4박 > 8분 뒷박 > 16분
- **백비트 악센트** — 팝/락에서 2·4박을 밀어주는 습관
- **성부 균형** — 최고음(선율)은 세게, 속음은 여리게
- **코드 굴림** — 화음을 정확히 동시에 치는 사람은 없습니다. 낮은음부터 몇 ms씩
  번져 올라가는 이것이 피아노를 사람처럼 들리게 하는 가장 큰 요소입니다
- **선율 리드** — 최고음을 화음보다 살짝 먼저 치는 습관
- **밀당** — R&B는 박 뒤에서 끌고(레이드백), 펑크/EDM은 앞에서 밉니다
- **정박 정확도** — 정박은 정확하고 뒷박이 흔들리는 게 사람의 실제 패턴입니다
- **세기-타이밍 결합** — 세게 치는 음은 아주 살짝 빨라집니다

프로파일: `off` `machine` `subtle` `piano_natural` `piano_expressive` `piano_ballad`
`rhodes` `guitar_strum` `guitar_finger` `guitar_cutting` `organ` `strings` `pad`
`laid_back` `pushed` `jazz_loose` `lofi_sloppy` `bass_tight` `bass_laid_back`

굴림 폭은 **밀리초 기준**이라 템포가 바뀌어도 손이 건반을 훑는 실제 속도가
유지됩니다. `organ` 은 벨로시티를 아예 고정합니다 — 실제 오르간이 세기에
반응하지 않는 악기이기 때문입니다.

### 코드 진행 템플릿 28종

액시스, 캐논, 두왑, 시티팝, ii-V-I, 턴어라운드, 12마디 블루스, 재즈 블루스,
안달루시안, 마이너 액시스, 네오소울, 가스펠, 보사노바, 리듬 체인지 등.
장르(`pop` `kpop` `citypop` `jazz` `rnb` `rock` `lofi` `bossa` `blues` `gospel` `edm` `latin`
`ballad` `classical` `cinematic` `neosoul`)로 골라 쓸 수 있습니다.

### 코드 심볼

`C` `Cm` `C7` `Cmaj7` `CΔ` `Cm7b5` `Cø` `Cdim7` `C°7` `Caug` `C+` `C6` `C69` `C6/9`
`C9` `C11` `C13` `Cmaj9` `Csus2` `Csus4` `C7sus4` `Cadd9` `CmMaj7` `C-7` `C5`
`C7b9` `C7#9` `C7#11` `C7b13` `C7alt` `Bb13(#11)` `C7(9,13)` `Am/C` `Cno3` …

오타는 조용히 넘어가지 않고 **어디가 해석되지 않았는지** 알려줍니다.

### 리하모나이제이션

`sevenths`(7음 추가) · `tensions`(9th/13th) · `tritone`(트라이톤 대리) ·
`secondary`(세컨더리 도미넌트 삽입) · `relative`(나란한조 대리) ·
`passing_dim`(경과 감7화음) · `modal`(동주단조 차용) · `sus`(sus4 지연)

---

## 알아두면 좋은 것

### 음이름 표기
Cubase 기본값인 **C3 = MIDI 60** 을 씁니다.
Cubase 환경설정에서 C4=60 으로 바꿔 쓰신다면 `set_output_folder` 의
`middle_c_octave` 를 `4` 로 설정하세요.

### 같은 음 겹침
MIDI 규격에는 "이 note off 가 어느 note on 의 짝인지" 정보가 없어서, 같은 음이
겹치면 DAW마다 해석이 달라집니다(Cubase에서는 음이 매달리거나 잘림). 이 서버는
파일로 쓰기 직전에 겹침을 자동으로 정리하므로 그런 문제가 생기지 않습니다.

### 트랙 이름
트랙 이름은 Cubase 호환을 위해 기본적으로 영문(ASCII)으로 씁니다.
한글 트랙명도 넣을 수는 있지만 Cubase 버전에 따라 깨져 보일 수 있습니다.

### 첫 박과 푸시
`pushed` 처럼 박보다 먼저 치는 프로파일에서는 **첫 박만** 그리드에 붙습니다.
프로젝트 시작보다 앞으로 갈 수 없기 때문입니다. 앞에 한 마디를 비워 두면
첫 박도 같은 느낌이 납니다. (해당 프로파일을 쓰면 결과에 안내가 함께 나옵니다.)

### Cubase 를 직접 조작하지는 않습니다
Cubase 에는 외부에서 트랙 내용을 편집하는 공식 API 가 없습니다. Cubase 12+ 의
MIDI Remote API 도 컨트롤러 매핑과 명령 실행 전용이라 노트를 읽거나 쓸 수 없습니다.
그래서 MIDI 파일 방식을 택했고, 나중에 다른 경로(가상 MIDI 포트, MIDI Remote
스크립트 등)가 열려도 갈아끼울 수 있도록 출력 계층을 분리해 두었습니다.
자세한 내용은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 를 보세요.

---

## 개발

```bash
pip install -e ".[dev]"
python -m unittest discover -s tests -t .
```

- 이론/MIDI 코어(`cubase_mcp/theory`, `cubase_mcp/midi`)는 **외부 의존성이 전혀 없습니다.**
  MIDI 파일 작성기도 직접 구현되어 있습니다.
- 테스트는 `tests/smf_reader.py` 의 **독립 파서**로 생성 파일을 다시 읽어 검증합니다
  (17개 보이싱 × 42개 리듬 전 조합 포함).
- `mcp` 패키지가 없으면 서버 테스트만 건너뛰고 나머지는 그대로 돌아갑니다.

### 구조

```
cubase_mcp/
  server.py          MCP 도구 정의
  render.py          코드+보이싱+리듬 → 트랙 (편곡)
  humanize.py        연주 습관 (타이밍/악센트/굴림)
  targets.py         결과를 어디로 내보낼지 (확장 지점)
  setup_wizard.py    Claude Desktop 등록
  config.py          출력 폴더 / 경로 안전 처리
  theory/
    notes.py         음이름 ↔ MIDI 번호
    chords.py        코드 심볼 파서
    scales.py        조성 / 스케일 / 로마숫자
    voicing.py       보이싱 엔진 + 보이스 리딩
    rhythm.py        리듬 패턴 라이브러리
    progression.py   진행 템플릿 / 생성 / 리하모나이제이션
  midi/
    smf.py           표준 MIDI 파일 작성기 (의존성 없음)
```

설계 의도와 확장 방법은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 에 정리해
두었습니다.

## 라이선스

MIT
