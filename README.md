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

설치가 끝나면 같은 폴더의 **`studio.bat`** 을 더블클릭해서 마우스로 쓰는 화면을
열 수 있습니다.

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
python -m cubase_mcp.setup_wizard --where    # 설정 파일을 어디서 찾는지 확인
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

## 스튜디오 — 마우스로 쓰는 화면

리듬을 `x--x-x--` 처럼 머릿속으로 세는 대신 **격자를 눌러 그릴 수 있습니다.**

### 실행: `studio.bat` 더블클릭

압축을 푼 폴더 안에 있습니다. 더블클릭하면 검은 창이 하나 뜨고 브라우저가 열립니다.
그 검은 창은 **켜 둔 채로** 쓰시고, 다 쓰면 닫으면 됩니다 (창을 닫으면 종료됩니다).

> 자주 쓰신다면 `studio.bat` 을 **우클릭 → 보내기 → 바탕 화면에 바로 가기 만들기** 로
> 바탕화면에 두시면 편합니다. 작업 표시줄에 고정해도 됩니다.

터미널을 쓰신다면 `cubase-studio` 또는 `python -m cubase_mcp.studio` 도 같습니다.
(`cubase-studio` 는 `pip install -e .` 을 다시 실행해야 생깁니다.)

브라우저가 열립니다. 할 수 있는 것:

- **리듬을 마우스로 그리기** — 칸을 클릭하면 `치기 → 악센트 → 여리게 → 늘리기 → 쉼`
  으로 바뀝니다. 드래그하면 이어서 칠해지고, 우클릭은 지우기입니다.
- **프리셋을 격자로 불러와 고치기** — 보사노바를 불러온 뒤 한 칸만 바꾸는 식으로
  쓸 수 있습니다.
- 박자표 · 한 박 나누기(8분/16분/셋잇단) · 마디 수를 바꾸면 격자가 다시 그려집니다
- 코드는 심볼이나 도수로 입력하고, 도수 버튼을 눌러 넣을 수도 있습니다
- 보이싱 · 연주감 · 악기 · 음역을 고르고 [만들기] 를 누르면 바로 저장됩니다

표준 라이브러리만 써서 **로컬에서만** 돕니다. 127.0.0.1 에만 연결을 받고,
페이지에 심어 둔 토큰이 있는 요청만 처리하므로 다른 프로그램이나 웹페이지가
건드릴 수 없습니다. tkinter 는 파이썬 설치 방식에 따라 빠져 있을 수 있어
쓰지 않았습니다.

MCP 로 대화하면서 쓰는 것과 **같은 엔진** 이라, 어느 쪽으로 만들어도 결과가
같습니다. 편한 쪽을 쓰시면 됩니다.

## 사용법 (대화로)

대화로 요청하면 됩니다. 몇 가지 예:

| 하고 싶은 것 | 이렇게 말하면 됩니다 |
|---|---|
| 진행만 추천받기 | "A마이너로 감성적인 발라드 진행 8마디 추천해줘" |
| 보이싱 비교 | "Dm7 G7 Cmaj7 를 close / drop2 / rootless_a 로 비교해서 음이름 보여줘" |
| 파일 만들기 | "그 진행을 로즈로 drop2 보이싱, 보사노바 리듬, 132BPM으로 만들어줘" |
| 리하모나이즈 | "C Am F G 에 세컨더리 도미넌트랑 텐션 넣어서 다시 짜줘" |
| 조옮김 | "이 진행 Eb키로 옮겨줘" |
| 한 마디 2코드 | "코드 하나당 2박씩 넣어줘" |
| 도수로 입력 | "C키로 I-V-vi-IV 진행 만들어줘" |
| 리듬 직접 그리기 | "리듬은 x--x-x-- 로 해줘" |
| 연주감 조절 | "피아노 발라드 느낌으로 사람이 친 것처럼 해줘" |
| 그루브 조절 | "좀 더 뒤로 끄는(레이드백) 느낌으로" |
| 설치 점검 | "설치 잘 됐는지 확인해줘" |
| 부분 수정 | "방금 그거 휴머나이즈 빼줘" |
| 부분 수정 | "보이싱만 rootless_a 로 다시" |

### 도구 목록

| 도구 | 하는 일 |
|---|---|
| `list_capabilities` | 지원하는 보이싱/리듬/진행/베이스/악기 전체 목록 |
| `analyze_chords` | 코드 구성음 + 조성 안에서의 역할(로마숫자) 분석 |
| `suggest_progression` | 장르에 맞는 코드 진행 제안 (파일 X) |
| `preview_voicing` | 보이싱을 음이름으로 미리보기 (파일 X) |
| `preview_rhythm` | 리듬을 박 단위로 펼쳐서 미리보기 (파일 X) |
| `reharmonize_progression` | 리하모나이제이션 (파일 X) |
| `transpose_progression` | 조옮김 (파일 X) |
| **`create_chord_midi`** | **코드+보이싱+리듬 → MIDI 파일 (핵심)** |
| `create_progression_midi` | 조성/장르만 주면 진행 생성부터 파일까지 한 번에 |
| `set_output_folder` | 저장 폴더 변경 |
| `list_output_files` | 만든 파일 목록 |
| `get_settings` | 현재 설정 확인 |
| `check_setup` | 설치 상태 자가 진단 |
| `set_cubase_import_key` | Cubase 가져오기 단축키 등록 |
| `send_to_cubase` | 만든 파일을 Cubase 로 바로 보내기 |
| **`revise_midi`** | **만든 파일을 바꿀 것만 바꿔 다시 만들기** |

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

### 코드 입력 — 심볼 또는 도수

두 가지 방식을 섞어 쓸 수 있습니다.

```
Cmaj7 | Am7 | Dm7 | G7      코드 심볼
C; I-V-vi-IV                조성 접두사 + 도수(로마숫자)
I V vi IV                   도수 (key 인자와 함께)
Am; i-bVI-bVII-V            단조
F; ii7-V7-Imaj7             7화음
C; V7/ii                    세컨더리 도미넌트
I V Am7 IV                  섞어 쓰기
```

`bVII` 처럼 변화표가 붙은 도수는 **평행 장조** 기준으로 계산합니다. 대중음악
표기에서 단조의 `bVII` 은 자연단음계의 VII 을 뜻하기 때문입니다.

> `C-7` 은 Cm7 입니다. 하이픈이 도수 구분자와 겹치지만, 나눈 결과가 **전부
> 로마숫자일 때만** 구분자로 취급하므로 두 표기가 충돌하지 않습니다.

### 리듬 입력 — 프리셋 또는 그리드

프리셋 42종을 이름으로 부르거나, 그리드 문자열로 직접 그릴 수 있습니다.

```
X   세게 치기 (악센트)
x   치기
o   여리게 치기 (고스트)
-   쉬기 (앞 음이 여기서 끊깁니다)      . 도 같음
~   앞 음을 이어서 늘리기               _ 도 같음
|   마디 구분
```

칸 수가 분할을 정합니다. 4/4 에서 8칸이면 8분음표, 16칸이면 16분음표입니다.

```
x-x-x-x-              8비트 균등
X~~-x~~-              2박씩 길게, 첫 박 악센트
x--x--x-              당김 (찰스턴 계열)
X-o-x-o-              악센트와 고스트 섞기
X-o-x-o- | x-x-xxx-   두 마디 패턴
x--x--x--x--          12칸 = 셋잇단
```

칸 수가 박에 맞지 않으면(예: 4/4 에 9칸) **조용히 넘어가지 않고** 쓸 수 있는
칸 수를 알려 줍니다. 칸을 하나 빠뜨려서 9잇단음표가 나오는 사고를 막기 위해서입니다.

`preview_rhythm` 으로 파일을 만들기 전에 확인할 수 있습니다.

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

### Microsoft Store 로 설치한 Claude Desktop
Store 버전은 앱이 격리되어 있어, `%APPDATA%\Claude` 에 쓴 설정을 **읽지 못합니다.**
실제 위치는 아래처럼 리디렉션됩니다.

```
%LOCALAPPDATA%\Packages\Claude_xxxxxxxxx\LocalCache\Roaming\Claude\
```

설치 마법사가 두 위치를 모두 확인해서 **앱 데이터가 실제로 살아 있는 폴더**에
등록하므로 보통은 신경 쓰지 않아도 됩니다. 어디에 쓸지 미리 보려면:

```powershell
python -m cubase_mcp.setup_wizard --where
```

앱에서 확인하려면 **설정 → 데스크톱 앱 → 개발자 → 로컬 MCP 서버** 에
`cubase` 가 보이면 됩니다.

### 만든 것을 부분만 고치기

`revise_midi` 는 **바꿀 것만 바꿔서 다시 만듭니다.**

```
"방금 그거 휴머나이즈 빼줘"        → 나머지는 그대로, 그리드에 딱 맞게
"보이싱만 rootless_a 로"          → 코드·리듬·연주감 유지
"연주감을 절반만"                  → humanize_amount 0.4
"템포만 120 으로, 베이스는 빼고"   → 여러 개 동시에도 됩니다
```

만들 때 쓴 설정을 출력 폴더의 `_recipes.json` 에 적어 두기 때문에 가능합니다.
MIDI 를 되읽어 원래 그리드를 **추측하지 않으므로** 바꾸지 않은 부분은 정확히
같습니다. 새 파일로 저장되니 원본과 비교할 수 있습니다.

스튜디오에서는 만든 파일 목록의 **↺** 를 누르면 그때 설정이 폼에 그대로
채워집니다(리듬 격자 포함). 한 가지만 바꿔 다시 만들면 됩니다.

> 직접 연주해 넣었거나 다른 데서 가져온 트랙은 기록이 없어 이 방식으로는
> 고칠 수 없습니다. 그건 MIDI 읽기가 생긴 뒤의 일입니다.

### Cubase 로 바로 보내기 (Windows)

드래그 없이 Cubase 로 곧장 가져올 수 있습니다. **한 번만** 준비하면 됩니다.

1. Cubase 에서 **[편집 > 키보드 단축키]** 를 엽니다
2. **`Import MIDI File`** (한국어판 **`MIDI 파일 가져오기`**) 을 찾습니다
3. 다른 기능과 겹치지 않는 키를 지정합니다 (예: `Ctrl+Alt+I`)
4. 스튜디오의 *Cubase 로 바로 보내기 설정* 에 그 키를 적거나,
   대화로 `set_cubase_import_key` 를 씁니다

그다음부터는 스튜디오의 **[Cubase로 보내기]** 버튼이나
`send_to_cubase` 로 바로 들어갑니다.

> **Windows 의 포커스 제한.** 뒤에서 도는 프로그램은 다른 창을 앞으로
> 가져올 수 없습니다. 그래서 Cubase 가 활성화되지 않고 작업 표시줄에서
> 깜빡이기만 할 수 있습니다. 스튜디오의 **[Cubase 를 직접 클릭할 시간 주기]**
> 를 켜 두면(기본값), 4초 카운트다운 동안 Cubase 창을 클릭해 이 제한을
> 피할 수 있습니다.

> **Cubase 에 프로젝트가 열려 있어야 합니다.** 열린 프로젝트가 없으면 Cubase 가
> 파일 창 대신 "새 프로젝트를 만들까요?" 라고 되묻고, 가져오기가 진행되지
> 않습니다. 이 경우 진단이 그 물음을 그대로 보여 줍니다.

처음에는 **[이 키가 먹히는지 확인]** 을 눌러 보세요. 키를 눌러 보기만 하고
글자는 입력하지 않으므로 안전하며, 어디까지 됐는지 단계별로 알려 줍니다.

메뉴를 더듬지 않고 키 커맨드를 쓰는 이유는, 메뉴 이름이 한국어판/영문판이
다르고 버전마다 바뀌지만 사용자가 정한 키는 그렇지 않기 때문입니다.

**안전장치** — 키를 대신 보내는 방식이라 엉뚱한 창에 들어가면 곤란합니다.
그래서 키를 보내기 **직전마다** 맨 앞 창이 Cubase 인지 다시 확인하고,
아니면 즉시 멈춥니다. 파일 대화상자가 뜨지 않으면 경로를 입력하지 않습니다.
실패해도 MIDI 파일은 그대로 남으니 직접 드래그하시면 됩니다.

처음에는 **미리보기(dry run)** 로 무엇을 할지 먼저 보세요.

### Cubase 안의 기존 트랙을 고치지는 못합니다
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
  bridge/            Cubase 창 직접 조작
    plan.py          조작 순서와 안전장치 (운영체제 무관, 테스트 가능)
    win32.py         Windows 구현 (ctypes, 의존성 없음)
    fake.py          테스트용 가짜 드라이버
  studio.py          마우스로 쓰는 로컬 화면 (표준 라이브러리 웹서버)
  studio.html        그 화면
  recipes.py         만든 설정 기록 (부분 수정용)
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
