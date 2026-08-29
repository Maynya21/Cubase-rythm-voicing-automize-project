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

## 설치 (Windows)

### 1. Python 설치
[python.org](https://www.python.org/downloads/) 에서 **Python 3.10 이상**을 설치합니다.
설치할 때 **"Add Python to PATH"** 를 반드시 체크하세요.

### 2. 이 저장소 받아서 설치

```powershell
git clone https://github.com/maynya21/cubase-rythm-voicing-automize-project.git
cd cubase-rythm-voicing-automize-project
pip install -e .
```

### 3. Claude Desktop 에 등록

`%APPDATA%\Claude\claude_desktop_config.json` 파일을 열어 아래 내용을 넣습니다.
(파일이 없으면 새로 만드세요. 이미 `mcpServers` 항목이 있으면 그 안에 추가합니다.)

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

`CUBASE_MCP_OUTPUT_DIR` 은 MIDI 파일이 저장될 폴더입니다.
생략하면 `내 문서\CubaseMCP` 에 저장됩니다. 대화 중에 `set_output_folder` 로 바꿀 수도 있습니다.

설정 후 Claude Desktop 을 **완전히 종료했다가 다시 실행**하세요.

### 4. Cubase 로 가져오기

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

## 라이선스

MIT
