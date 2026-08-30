"""MCP 서버 — Cubase 용 코드/보이싱/리듬 자동 생성.

생성 결과는 표준 MIDI 파일로 저장됩니다. Cubase 에서는 파일을 트랙으로
드래그하거나 [파일 > 가져오기 > MIDI 파일] 로 불러오면 됩니다.
"""

from __future__ import annotations

import datetime as _dt
import functools
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

try:                                          # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError as _ToolError
except ImportError:                           # mcp 1.x (FastMCP)
    from mcp.server.fastmcp import FastMCP as _Server            # type: ignore[no-redef]
    from mcp.server.fastmcp.exceptions import ToolError as _ToolError  # type: ignore[no-redef]

from . import __version__
from .config import SETTINGS, safe_filename, unique_path
from .humanize import PROFILES as HUMANIZE_PROFILES, list_humanize_profiles
from .midi.smf import write as write_midi
from .render import BASS_STYLES, GM_PROGRAMS, build_arrangement
from .targets import TargetUnavailable, deliver, environment_report, list_targets
from .theory.chords import Chord, ChordError, parse_chord, parse_progression
from .theory.notes import note_name
from .theory.progression import (REHARM_MOVES, TEMPLATES, analyze, from_template,
                                 generate, list_genres, list_progression_templates,
                                 reharmonize)
from .theory.rhythm import (GRID_HELP, RHYTHM_PATTERNS, list_rhythm_patterns,
                            render_bar, resolve_pattern)
from .theory.scales import (SCALES, Key, diatonic_chords, parse_chords, parse_key,
                            roman_of)
from .theory.voicing import VOICING_STYLES, list_voicing_styles, voice_progression

INSTRUCTIONS = """\
Cubase 용 코드 진행 / 보이싱 / 리듬을 MIDI 파일로 만들어 주는 서버입니다.

작업 순서 권장:
1. `suggest_progression` 또는 `preview_voicing` 으로 먼저 소리와 코드를 확인
2. 마음에 들면 `create_chord_midi` 로 .mid 파일 생성
3. Cubase 에서 파일을 트랙에 드래그 (또는 파일 > 가져오기 > MIDI 파일)

음이름 표기는 Cubase 기본값인 C3 = MIDI 60 을 씁니다.
사용 가능한 스타일/패턴/템플릿 목록은 `list_capabilities` 로 확인하세요.
"""

mcp = _Server(
    name="cubase-chord-voicing",
    version=__version__,
    instructions=INSTRUCTIONS,
)


# --------------------------------------------------------------------------- #
# 공통 도우미
# --------------------------------------------------------------------------- #

def _expected(fn):
    """예상 가능한 입력 오류를 MCP 클라이언트가 읽을 수 있는 형태로 바꿉니다.

    이 래퍼가 없으면 SDK 가 예외를 "Error executing tool ..." 로 감춰서
    무엇이 잘못됐는지(어떤 코드 심볼이 틀렸는지 등)가 모델에게 전달되지 않습니다.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _ToolError:
            raise
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise _ToolError(str(exc) or exc.__class__.__name__) from exc
    return wrapper


def _chords_from(value: Union[str, Sequence[str]],
                 key: Optional[str] = None) -> List[Chord]:
    """코드 심볼과 도수 표기를 함께 받습니다."""
    chords, _key, _roman = parse_chords(value, key)
    return chords


def _timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _describe_voicings(chords: Sequence[Chord], voicings: Sequence[Sequence[int]],
                       flats: bool = False) -> List[Dict[str, Any]]:
    return [
        {
            "chord": c.symbol,
            "notes": [note_name(p, SETTINGS.middle_c_octave, flats) for p in v],
            "midi": list(v),
        }
        for c, v in zip(chords, voicings)
    ]





# --------------------------------------------------------------------------- #
# 정보 조회
# --------------------------------------------------------------------------- #

@mcp.tool()
@_expected
def list_capabilities() -> Dict[str, Any]:
    """이 서버가 지원하는 모든 보이싱/리듬/진행/베이스/악기 목록을 돌려줍니다.

    무엇을 만들 수 있는지 처음 확인할 때 이 도구를 먼저 부르세요.
    """
    return {
        "voicing_styles": list_voicing_styles(),
        "rhythm_patterns": list_rhythm_patterns(),
        "progression_templates": list_progression_templates(),
        "genres": list_genres(),
        "bass_styles": [{"name": k, "description": v} for k, v in BASS_STYLES.items()],
        "humanize_profiles": list_humanize_profiles(),
        "rhythm_grid_notation": GRID_HELP,
        "chord_input_formats": [
            "코드 심볼: 'Cmaj7 | Am7 | Dm7 | G7'",
            "도수(로마숫자): 'C; I-V-vi-IV' 또는 key='C' 와 함께 'I V vi IV'",
            "섞어 쓰기: 'I V Am7 IV' (key 필요)",
        ],
        "delivery_targets": list_targets(),
        "reharmonization_moves": [{"name": k, "description": v} for k, v in REHARM_MOVES.items()],
        "scales": sorted(SCALES),
        "instruments": sorted(GM_PROGRAMS),
        "output_dir": str(SETTINGS.output_dir),
        "note_naming": f"C{SETTINGS.middle_c_octave} = MIDI 60 (Cubase 기본)",
    }


@mcp.tool()
@_expected
def get_settings() -> Dict[str, Any]:
    """현재 출력 폴더와 기본값을 확인합니다."""
    return {
        "output_dir": str(SETTINGS.output_dir),
        "output_dir_exists": SETTINGS.output_dir.is_dir(),
        "default_tempo": SETTINGS.tempo,
        "default_time_signature": f"{SETTINGS.time_signature[0]}/{SETTINGS.time_signature[1]}",
        "middle_c_octave": SETTINGS.middle_c_octave,
        "cubase_import_key": SETTINGS.import_key or None,
        "version": __version__,
    }


@mcp.tool()
@_expected
def set_output_folder(path: str, middle_c_octave: Optional[int] = None) -> Dict[str, Any]:
    """MIDI 파일을 저장할 폴더를 바꿉니다.

    Args:
        path: 저장 폴더의 절대 경로. 예) ``C:\\Users\\나\\Documents\\CubaseMCP``
        middle_c_octave: 가운데 도의 옥타브 표기. Cubase 기본은 3 (C3=60).
            Cubase 환경설정에서 C4=60 으로 바꿨다면 4 를 넣으세요.
    """
    target = Path(path).expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"폴더를 만들 수 없습니다: {target} ({exc})") from exc
    SETTINGS.output_dir = target
    if middle_c_octave is not None:
        if not -2 <= middle_c_octave <= 8:
            raise ValueError("middle_c_octave 는 -2 ~ 8 사이여야 합니다")
        SETTINGS.middle_c_octave = middle_c_octave
    return {"output_dir": str(SETTINGS.output_dir),
            "middle_c_octave": SETTINGS.middle_c_octave,
            "message": f"이제 생성한 파일은 {SETTINGS.output_dir} 에 저장됩니다."}


@mcp.tool()
@_expected
def check_setup() -> Dict[str, Any]:
    """설치가 제대로 됐는지 스스로 점검합니다. 문제가 생기면 이걸 먼저 부르세요.

    출력 폴더에 쓸 수 있는지, 어떤 출력 경로를 쓸 수 있는지, 실제로 파일이
    만들어지는지까지 확인하고 사람이 읽을 수 있는 진단 결과를 돌려줍니다.
    """
    report = environment_report()
    checks: List[Dict[str, Any]] = []

    checks.append({
        "name": "출력 폴더 쓰기",
        "ok": report["output_dir_writable"],
        "detail": (f"{report['output_dir']} 에 저장할 수 있습니다."
                   if report["output_dir_writable"]
                   else f"{report['output_dir']} 에 쓸 수 없습니다. "
                        f"set_output_folder 로 다른 폴더를 지정하세요."),
    })

    try:
        probe = build_arrangement(parse_progression("Cmaj7 G7"), humanize="piano_natural")
        note_count = sum(len(t.notes) for t in probe.midi.tracks)
        checks.append({"name": "MIDI 생성 엔진", "ok": note_count > 0,
                       "detail": f"테스트 편곡에서 노트 {note_count}개를 만들었습니다."})
    except Exception as exc:                     # pragma: no cover - 방어적
        checks.append({"name": "MIDI 생성 엔진", "ok": False, "detail": str(exc)})

    usable = [t["korean"] for t in report["targets"] if t["available"]]
    checks.append({
        "name": "출력 경로",
        "ok": bool(usable),
        "detail": f"지금 쓸 수 있는 경로: {', '.join(usable) or '없음'}",
    })

    all_ok = all(c["ok"] for c in checks)
    return {
        "ok": all_ok,
        "summary": ("모두 정상입니다. 바로 쓰시면 됩니다."
                    if all_ok else "문제가 있습니다. 아래 detail 을 확인하세요."),
        "checks": checks,
        "platform": report["platform"],
        "python": report["python"],
        "output_dir": report["output_dir"],
        "version": __version__,
        "counts": {
            "voicing_styles": len(VOICING_STYLES),
            "rhythm_patterns": len(RHYTHM_PATTERNS),
            "progression_templates": len(TEMPLATES),
            "humanize_profiles": len(HUMANIZE_PROFILES),
        },
    }


@mcp.tool()
@_expected
def set_cubase_import_key(shortcut: str) -> Dict[str, Any]:
    """Cubase 의 'MIDI 파일 가져오기' 단축키를 알려 줍니다. (직접 가져오기 준비)

    Cubase 창을 직접 조작해서 파일을 가져오려면 이 설정이 필요합니다.
    메뉴 이름은 한국어판/영문판이 다르고 버전마다 바뀌지만, 사용자가 정한
    키 커맨드는 그렇지 않아서 이 방식을 씁니다.

    Cubase 에서 설정하는 법:
      1. [편집 > 키보드 단축키] 를 엽니다
      2. 검색창에 'Import MIDI' (한국어판은 'MIDI 파일 가져오기') 를 칩니다
      3. 원하는 키를 지정합니다. 다른 기능과 겹치지 않는 조합을 고르세요
      4. 그 키를 이 도구로 알려 주세요

    Args:
        shortcut: 지정한 키 조합. 예) ``"ctrl+alt+i"``, ``"shift+f11"``.
            비우면 설정을 해제합니다.
    """
    from .bridge.win32 import parse_keys

    value = (shortcut or "").strip()
    if value:
        parse_keys(value)          # 쓸 수 없는 키면 여기서 걸립니다
    SETTINGS.import_key = value
    return {
        "import_key": SETTINGS.import_key or None,
        "message": (f"'{value}' 로 설정했습니다. 이제 target='cubase_import' 로 "
                    f"바로 가져올 수 있습니다."
                    if value else "단축키 설정을 해제했습니다."),
        "targets": list_targets(),
    }


@mcp.tool()
@_expected
def send_to_cubase(filename: Optional[str] = None,
                   dry_run: bool = False) -> Dict[str, Any]:
    """이미 만들어 둔 MIDI 파일을 Cubase 창을 조작해 가져옵니다.

    Cubase 를 앞으로 가져와 'MIDI 파일 가져오기' 단축키를 누르고, 파일 경로를
    입력해 불러옵니다. 조작 도중 다른 창이 앞으로 나오면 **즉시 멈춥니다.**

    처음 쓰신다면 ``dry_run=True`` 로 무엇을 할지 먼저 보세요.

    Args:
        filename: 출력 폴더 안의 파일 이름. 비우면 가장 최근 파일.
        dry_run: 실제로 조작하지 않고 계획만 보여줍니다.
    """
    from .bridge import BridgeError, describe, import_midi_plan, run

    folder = SETTINGS.output_dir
    if filename:
        path = folder / safe_filename(filename)
        if not path.is_file():
            raise ValueError(f"출력 폴더에 그런 파일이 없습니다: {path.name}")
    else:
        candidates = sorted(folder.glob("*.mid"), key=lambda p: p.stat().st_mtime,
                            reverse=True) if folder.is_dir() else []
        if not candidates:
            raise ValueError("아직 만든 MIDI 파일이 없습니다.")
        path = candidates[0]

    if not SETTINGS.import_key:
        raise ValueError(
            "먼저 set_cubase_import_key 로 Cubase 의 'MIDI 파일 가져오기' 단축키를 "
            "알려 주세요. Cubase [편집 > 키보드 단축키] 에서 지정할 수 있습니다."
        )

    steps = import_midi_plan(path, SETTINGS.import_key)
    if dry_run:
        return {"dry_run": True, "file": str(path), "planned_steps": describe(steps),
                "note": "실제로는 아무것도 하지 않았습니다."}

    from .bridge.win32 import Win32Driver
    try:
        result = run(steps, Win32Driver())
    except BridgeError as exc:
        raise _ToolError(
            f"{exc}\n\n파일은 그대로 있으니 직접 드래그하셔도 됩니다: {path}"
        ) from exc
    return {"file": str(path), "imported": True,
            "cubase_window": result.get("window"), "log": result.get("log", []),
            "message": "Cubase 로 가져왔습니다. 프로젝트 창을 확인해 주세요."}


@mcp.tool()
@_expected
def list_output_files(limit: int = 20) -> Dict[str, Any]:
    """출력 폴더에 만들어 둔 MIDI 파일 목록을 최신순으로 봅니다."""
    if not SETTINGS.output_dir.is_dir():
        return {"output_dir": str(SETTINGS.output_dir), "files": [],
                "message": "출력 폴더가 아직 없습니다. 파일을 하나 만들면 생성됩니다."}
    files = sorted(SETTINGS.output_dir.rglob("*.mid"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:max(1, limit)]
    return {
        "output_dir": str(SETTINGS.output_dir),
        "files": [
            {
                "name": f.name,
                "path": str(f),
                "size_bytes": f.stat().st_size,
                "modified": _dt.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
            }
            for f in files
        ],
    }


# --------------------------------------------------------------------------- #
# 분석 / 미리보기
# --------------------------------------------------------------------------- #

@mcp.tool()
@_expected
def analyze_chords(chords: str, key: str = "C") -> Dict[str, Any]:
    """코드 심볼을 해석해 구성음과 조성 안에서의 역할(로마숫자)을 보여줍니다.

    Args:
        chords: ``"Cmaj7 | Am7 | Dm7 | G7"`` 처럼 공백/막대/쉼표로 구분한 코드.
        key: 분석 기준 조성. ``"C"``, ``"Am"``, ``"Bb dorian"`` 등.
    """
    k = parse_key(key)
    parsed = _chords_from(chords, key)
    return {
        "key": k.name,
        "mode": k.mode,
        "chords": analyze(parsed, k),
        "diatonic_chords": [c.symbol for c in diatonic_chords(k)],
    }


@mcp.tool()
@_expected
def suggest_progression(
    key: str = "C",
    genre: str = "pop",
    bars: int = 4,
    template: Optional[str] = None,
    seed: Optional[int] = None,
    adapt: str = "relative",
) -> Dict[str, Any]:
    """장르에 어울리는 코드 진행을 제안합니다 (파일은 만들지 않습니다).

    Args:
        key: 조성. ``"C"``, ``"Am"``, ``"F# minor"`` 등.
        genre: ``list_capabilities`` 의 genres 중 하나. pop/kpop/jazz/citypop/rnb/rock 등.
        bars: 마디 수. 템플릿보다 길면 반복하고, 짧으면 잘라냅니다.
        template: 특정 템플릿을 직접 지정 (예: ``"axis"``, ``"canon"``, ``"ii_v_i"``).
        seed: 같은 값을 주면 같은 결과가 나옵니다.
        adapt: 템플릿의 장/단조와 조성이 다를 때 처리 방식.
            ``"relative"``(나란한조, 기본) / ``"parallel"``(같은 으뜸음조) / ``"none"``.
    """
    p = generate(key=key, genre=genre, bars=bars, template=template, seed=seed, adapt=adapt)
    return {
        "key": p.key.name,
        "template": p.template,
        "template_korean": TEMPLATES[p.template].korean if p.template else None,
        "chords": p.symbols,
        "chords_text": p.describe(),
        "romans": p.romans,
        "bars": len(p.chords),
        "note": p.adapted_note,
    }


@mcp.tool()
@_expected
def preview_voicing(
    chords: str,
    key: Optional[str] = None,
    voicing: str = "close",
    low: str = "C2",
    high: str = "C5",
    max_notes: Optional[int] = None,
    add_tensions: bool = False,
    voice_leading: bool = True,
) -> Dict[str, Any]:
    """보이싱을 실제 음이름으로 미리 봅니다 (파일은 만들지 않습니다).

    파일을 만들기 전에 스타일을 비교할 때 쓰세요.

    Args:
        chords: 코드 진행. 심볼(``"Dm7 G7 Cmaj7"``) 또는 도수(``"C; ii-V-I"``).
        key: 도수 표기를 쓸 때의 조성. ``"C; ii-V-I"`` 처럼 앞에 붙여도 됩니다.
        voicing: 보이싱 스타일 이름. ``list_capabilities`` 참고.
        low: 사용할 최저음 (예: ``"C2"``). Cubase 표기 기준.
        high: 사용할 최고음 (예: ``"C5"``).
        max_notes: 코드당 최대 음 수. 비우면 제한 없음.
        add_tensions: 9th/13th 를 관용적으로 덧붙일지.
        voice_leading: 앞 코드와 부드럽게 이어지도록 자리바꿈을 고를지.
    """
    from .theory.notes import parse_note
    parsed = _chords_from(chords, key)
    lo = parse_note(low, SETTINGS.middle_c_octave)
    hi = parse_note(high, SETTINGS.middle_c_octave)
    if lo >= hi:
        raise ValueError(f"low({low}) 는 high({high}) 보다 낮아야 합니다")
    voicings = voice_progression(parsed, style=voicing, low=lo, high=hi,
                                 max_notes=max_notes, voice_leading=voice_leading,
                                 add_tensions=add_tensions)
    from .theory.voicing import voicing_movement
    style = VOICING_STYLES[voicing.lower()] if voicing.lower() in VOICING_STYLES else None
    return {
        "voicing": voicing,
        "voicing_korean": style.korean if style else None,
        "description": style.description if style else None,
        "range": f"{low} ~ {high}",
        "voicings": _describe_voicings(parsed, voicings),
        "average_movement_semitones": round(voicing_movement(voicings), 2),
    }


@mcp.tool()
@_expected
def preview_rhythm(
    rhythm: str,
    time_signature: str = "4/4",
    rhythm_mode: str = "block",
    tempo: float = 120.0,
) -> Dict[str, Any]:
    """리듬을 박 단위로 펼쳐서 미리 봅니다 (파일은 만들지 않습니다).

    프리셋 이름이든 직접 쓴 그리드 문자열이든 받습니다. 파일을 만들기 전에
    "이 리듬이 내가 생각한 게 맞나" 를 확인할 때 쓰세요.

    Args:
        rhythm: 프리셋 이름 또는 그리드 문자열 (``"x--x-x--"`` 등).
        time_signature: ``"4/4"``, ``"3/4"`` 등.
        rhythm_mode: 그리드일 때 block / arp / strum.
        tempo: 밀리초 환산에 쓰입니다.
    """
    num, den = _parse_time_signature(time_signature)
    bar_beats = num * 4.0 / den
    pattern = resolve_pattern(rhythm, beats_per_bar=bar_beats, mode=rhythm_mode)
    beat_ms = 60000.0 / tempo

    hits = []
    for start, duration, velocity in pattern.events:
        bar = int(start // bar_beats) + 1
        beat_in_bar = start % bar_beats
        hits.append({
            "bar": bar,
            "beat": round(beat_in_bar + 1, 4),
            "position": _beat_label(beat_in_bar),
            "length_beats": round(duration, 4),
            "length_ms": round(duration * beat_ms, 1),
            "velocity_ratio": round(velocity, 3),
        })

    return {
        "name": pattern.name,
        "korean": pattern.korean,
        "description": pattern.description,
        "source": "그리드 직접 입력" if "직접입력" in pattern.tags else "프리셋",
        "mode": pattern.mode,
        "length_beats": pattern.beats_per_bar,
        "length_bars": round(pattern.beats_per_bar / bar_beats, 3),
        "hit_count": len(pattern.events),
        "default_swing": pattern.swing,
        "hits": hits,
        "grid_help": GRID_HELP if "직접입력" in pattern.tags else None,
    }


def _beat_label(beat_in_bar: float) -> str:
    """0.0 -> '1', 1.5 -> '2와', 2.25 -> '3e' 처럼 읽기 쉬운 위치 표시."""
    beat = int(beat_in_bar) + 1
    fraction = beat_in_bar - int(beat_in_bar)
    if fraction < 0.01:
        return str(beat)
    if abs(fraction - 0.5) < 0.01:
        return f"{beat}와"
    if abs(fraction - 0.25) < 0.01:
        return f"{beat}e"
    if abs(fraction - 0.75) < 0.01:
        return f"{beat}a"
    if abs(fraction - 1 / 3) < 0.02:
        return f"{beat}셋2"
    if abs(fraction - 2 / 3) < 0.02:
        return f"{beat}셋3"
    return f"{beat}+{fraction:.2f}"


@mcp.tool()
@_expected
def reharmonize_progression(
    chords: str,
    key: str = "C",
    moves: Optional[List[str]] = None,
    strength: float = 0.6,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """코드 진행을 리하모나이즈합니다 (파일은 만들지 않습니다).

    Args:
        chords: 원래 코드 진행.
        key: 조성.
        moves: 적용할 기법 목록. sevenths / tensions / tritone / secondary /
            relative / passing_dim / modal / sus 중에서 고릅니다.
        strength: 0~1. 각 기법을 얼마나 자주 적용할지.
        seed: 같은 값을 주면 같은 결과.
    """
    if not 0.0 <= strength <= 1.0:
        raise ValueError("strength 는 0.0 ~ 1.0 사이여야 합니다")
    k = parse_key(key)
    parsed = _chords_from(chords, key)
    out = reharmonize(parsed, k, moves=tuple(moves or ["sevenths"]),
                      strength=strength, seed=seed)
    return {
        "key": k.name,
        "before": [c.symbol for c in parsed],
        "after": [c.symbol for c in out],
        "after_text": " | ".join(c.symbol for c in out),
        "romans_after": [roman_of(c, k) for c in out],
        "bar_count_changed": len(out) != len(parsed),
    }


@mcp.tool()
@_expected
def transpose_progression(chords: str, semitones: int = 0,
                          to_key: Optional[str] = None,
                          from_key: str = "C") -> Dict[str, Any]:
    """코드 진행을 조옮김합니다.

    Args:
        chords: 원래 코드 진행.
        semitones: 옮길 반음 수 (``to_key`` 를 주면 무시).
        to_key: 목표 조성. 주면 ``from_key`` 에서의 차이만큼 옮깁니다.
        from_key: 원래 조성 (``to_key`` 를 쓸 때만 필요).
    """
    parsed = _chords_from(chords, from_key)
    if to_key:
        semitones = (parse_key(to_key).tonic - parse_key(from_key).tonic) % 12
    flats = parse_key(to_key).prefers_flats if to_key else False
    from .theory.notes import pitch_class_name
    out = []
    for c in parsed:
        root = pitch_class_name((c.root + semitones) % 12, flats)
        suffix = c.symbol
        # 원래 심볼에서 근음 부분만 갈아끼웁니다.
        i = 1
        while i < len(suffix) and suffix[i] in "#b♯♭x":
            i += 1
        rest = suffix[i:]
        if c.bass is not None:
            base, _, _ = rest.rpartition("/")
            rest = base + "/" + pitch_class_name((c.bass + semitones) % 12, flats)
        out.append(parse_chord(root + rest).symbol)
    return {
        "semitones": semitones,
        "before": [c.symbol for c in parsed],
        "after": out,
        "after_text": " | ".join(out),
        "to_key": to_key,
    }


# --------------------------------------------------------------------------- #
# MIDI 생성
# --------------------------------------------------------------------------- #

@mcp.tool()
@_expected
def create_chord_midi(
    chords: str,
    voicing: str = "close",
    rhythm: str = "quarter",
    rhythm_mode: str = "block",
    arp_order: str = "up",
    strum_ms: float = 18.0,
    tempo: float = 120.0,
    time_signature: str = "4/4",
    key: Optional[str] = None,
    beats_per_chord: Optional[float] = None,
    repeat: int = 1,
    low: str = "C2",
    high: str = "C5",
    max_notes: Optional[int] = None,
    add_tensions: bool = False,
    voice_leading: bool = True,
    swing: Optional[float] = None,
    humanize: str = "subtle",
    humanize_amount: float = 1.0,
    bass_humanize: Optional[str] = None,
    humanize_timing_ms: Optional[float] = None,
    humanize_velocity: Optional[float] = None,
    velocity: int = 90,
    duration_scale: float = 1.0,
    let_ring: bool = False,
    target: str = "midi_file",
    include_bass: bool = False,
    bass_style: str = "root",
    instrument: Optional[str] = None,
    bass_instrument: str = "finger_bass",
    add_markers: bool = True,
    filename: Optional[str] = None,
    subfolder: Optional[str] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """코드 진행을 보이싱·리듬과 함께 MIDI 파일로 만듭니다. (핵심 도구)

    Args:
        chords: 두 가지 방식으로 쓸 수 있습니다.
            **코드 심볼** — ``"Cmaj7 | Am7 | Dm7 | G7"``. ``%`` 는 앞 코드 반복.
            **도수(로마숫자)** — ``"C; I-V-vi-IV"`` 또는 ``key`` 를 주고 ``"I V vi IV"``.
            ``bVII``, ``V7/ii``, ``iiø7`` 같은 표기도 됩니다. 섞어 써도 됩니다.
        voicing: 보이싱 스타일 (close/drop2/rootless_a/quartal/pad/guitar/piano 등).
        rhythm: 프리셋 이름(quarter/charleston/bossa/funk16/arp_up 등) 또는
            **그리드 문자열** 로 직접 입력. ``x``=치기, ``X``=세게, ``o``=여리게,
            ``-``=쉬기, ``~``=앞 음 늘리기, ``|``=마디 구분.
            예) ``"x-x-x-x-"`` 8비트, ``"X~~-x~~-"`` 2박씩 길게,
            ``"x--x--x-"`` 당김. 칸 수가 분할을 정합니다(8칸=8분음표).
        rhythm_mode: 그리드로 입력할 때 ``block``(화음 동시) / ``arp``(아르페지오)
            / ``strum``(긁기).
        arp_order: ``rhythm_mode="arp"`` 일 때 음 순서 (up/down/updown/alberti 등).
        strum_ms: ``rhythm_mode="strum"`` 일 때 음 사이 간격(밀리초).
        tempo: BPM.
        time_signature: ``"4/4"``, ``"3/4"``, ``"6/8"`` 형식.
        key: 조성. 주면 MIDI 에 조표를 기록합니다.
        beats_per_chord: 코드 하나가 차지하는 박. 비우면 한 마디.
            한 마디에 코드 2개를 넣으려면 4/4 에서 2 를 주세요.
        repeat: 진행 전체를 몇 번 반복할지.
        low, high: 보이싱을 배치할 음역 (Cubase 표기, 예 ``"C2"`` ~ ``"C5"``).
        max_notes: 코드당 최대 음 수.
        add_tensions: 9th/13th 를 관용적으로 덧붙일지.
        voice_leading: 코드 간 이동을 최소화할지.
        swing: 스윙 정도. 0.5=스트레이트, 0.66≈트리플렛. 비우면 패턴 기본값.
        humanize: 연주 습관 프로파일. 악기/장르에 맞춰 미세 타이밍과 악센트를
            함께 조절합니다. ``off``(정확한 그리드) / ``subtle``(범용, 기본) /
            ``piano_natural`` / ``piano_ballad`` / ``rhodes`` / ``guitar_strum`` /
            ``guitar_finger`` / ``organ`` / ``strings`` / ``laid_back``(뒤로 끌기) /
            ``pushed``(앞으로 밀기) / ``jazz_loose`` / ``lofi_sloppy`` 등.
            전체 목록은 ``list_capabilities`` 참고.
        humanize_amount: 0~1. 프로파일 효과의 세기를 줄일 때.
        bass_humanize: 베이스 트랙용 프로파일. 비우면 코드 느낌에 맞춰 자동 선택.
        humanize_timing_ms: 타이밍 흔들림만 직접 지정(밀리초 표준편차).
        humanize_velocity: 벨로시티 흔들림만 직접 지정(표준편차).
        velocity: 기준 벨로시티 1~127.
        duration_scale: 노트 길이 배율. 0.5 면 더 스타카토.
        let_ring: 코드가 바뀌어도 소리를 끊지 않고 겹치게 할지.
        target: 출력 경로. 지금은 ``midi_file`` 만 동작합니다
            (``list_capabilities`` 의 delivery_targets 참고).
        include_bass: 베이스 트랙을 함께 만들지.
        bass_style: 베이스 스타일 (root/walking/eighth/root_fifth 등).
        instrument: 코드 트랙 GM 악기 이름 (예: ``"electric_piano"``). 비우면 프로그램 체인지 없음.
        bass_instrument: 베이스 트랙 GM 악기 이름.
        add_markers: 코드 심볼을 마커로 기록할지 (Cubase 마커 트랙에 표시됨).
        filename: 저장할 파일명. 비우면 자동 생성.
        subfolder: 출력 폴더 아래 하위 폴더 이름.
        seed: 휴머나이즈/워킹베이스 난수 고정값.
    """
    from .theory.notes import parse_note

    parsed, resolved_key, used_roman = parse_chords(chords, key)
    k = resolved_key if resolved_key is not None else (parse_key(key) if key else None)
    ts = _parse_time_signature(time_signature)
    lo = parse_note(low, SETTINGS.middle_c_octave)
    hi = parse_note(high, SETTINGS.middle_c_octave)
    if lo >= hi:
        raise ValueError(f"low({low}) 는 high({high}) 보다 낮아야 합니다")
    if not 1 <= velocity <= 127:
        raise ValueError("velocity 는 1 ~ 127 사이여야 합니다")

    result = build_arrangement(
        parsed,
        key=k,
        tempo=tempo,
        time_signature=ts,
        beats_per_chord=beats_per_chord,
        repeat=repeat,
        voicing=voicing,
        low=lo,
        high=hi,
        max_notes=max_notes,
        add_tensions=add_tensions,
        voice_leading=voice_leading,
        rhythm=rhythm,
        rhythm_mode=rhythm_mode,
        arp_order=arp_order,
        strum_ms=strum_ms,
        swing=swing,
        humanize=humanize,
        humanize_amount=humanize_amount,
        bass_humanize=bass_humanize,
        humanize_timing_ms=humanize_timing_ms,
        humanize_velocity=humanize_velocity,
        velocity=velocity,
        duration_scale=duration_scale,
        let_ring=let_ring,
        include_bass=include_bass,
        bass_style=bass_style,
        chord_program=instrument,
        bass_program=bass_instrument if include_bass else None,
        add_markers=add_markers,
        seed=seed,
    )

    stem = f"{voicing}-{rhythm}-{_timestamp()}"
    try:
        delivered = deliver(result, target, filename=filename, subfolder=subfolder,
                            default_stem=stem)
    except TargetUnavailable as exc:
        raise _ToolError(str(exc)) from exc
    note_count = sum(len(t.notes) for t in result.midi.tracks)
    return {
        **delivered,
        "chords": [c.symbol for c in parsed],
        "bars": round(result.total_bars, 3),
        "beats": result.total_beats,
        "tempo": tempo,
        "time_signature": f"{ts[0]}/{ts[1]}",
        "voicing": voicing,
        "rhythm": rhythm,
        "rhythm_detail": result.rhythm_description,
        "input_style": "도수(로마숫자)" if used_roman else "코드 심볼",
        "key": k.name if k else None,
        "humanize": result.humanize,
        "bass_humanize": result.bass_humanize if include_bass else None,
        "tracks": [t.name for t in result.midi.tracks],
        "note_count": note_count,
        "voicings": _describe_voicings([s.chord for s in result.slots],
                                       [s.voicing for s in result.slots]),
        "warnings": result.warnings,
    }


@mcp.tool()
@_expected
def create_progression_midi(
    key: str = "C",
    genre: str = "pop",
    bars: int = 8,
    template: Optional[str] = None,
    voicing: str = "close",
    rhythm: str = "quarter",
    tempo: float = 120.0,
    time_signature: str = "4/4",
    include_bass: bool = True,
    bass_style: str = "root",
    add_tensions: bool = False,
    humanize: str = "subtle",
    filename: Optional[str] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """조성과 장르만 주면 진행 생성부터 MIDI 저장까지 한 번에 합니다.

    "C키로 시티팝 8마디 만들어줘" 같은 요청에 쓰기 좋은 도구입니다.
    세부 조정이 필요하면 `suggest_progression` + `create_chord_midi` 로 나눠 쓰세요.

    Args:
        key: 조성.
        genre: 장르 (pop/kpop/citypop/jazz/rnb/rock/lofi/bossa/blues/gospel 등).
        bars: 마디 수.
        template: 진행 템플릿을 직접 지정하고 싶을 때.
        voicing: 보이싱 스타일.
        rhythm: 리듬 패턴.
        tempo: BPM.
        time_signature: ``"4/4"`` 등.
        include_bass: 베이스 트랙 포함 여부.
        bass_style: 베이스 스타일.
        add_tensions: 9th/13th 자동 추가.
        humanize: 연주 습관 프로파일 (기본 ``subtle``).
        filename: 파일명.
        seed: 난수 고정값.
    """
    p = generate(key=key, genre=genre, bars=bars, template=template, seed=seed)
    result = create_chord_midi(
        chords=" ".join(p.symbols),
        voicing=voicing,
        rhythm=rhythm,
        tempo=tempo,
        time_signature=time_signature,
        key=key,
        include_bass=include_bass,
        bass_style=bass_style,
        add_tensions=add_tensions,
        humanize=humanize,
        filename=filename,
        seed=seed,
    )
    result["template"] = p.template
    result["romans"] = p.romans
    result["genre"] = genre
    result["key"] = p.key.name
    if p.adapted_note:
        result["warnings"] = list(result.get("warnings", [])) + [p.adapted_note]
    return result


def _parse_time_signature(text: str) -> tuple:
    parts = str(text).replace(" ", "").split("/")
    if len(parts) != 2:
        raise ValueError(f"박자표는 '4/4' 형식이어야 합니다: {text!r}")
    try:
        num, den = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(f"박자표는 '4/4' 형식이어야 합니다: {text!r}") from exc
    if not 1 <= num <= 32:
        raise ValueError(f"박자표 분자가 이상합니다: {num}")
    if den not in (1, 2, 4, 8, 16, 32):
        raise ValueError(f"박자표 분모는 2의 거듭제곱이어야 합니다: {den}")
    return num, den


def main() -> None:
    """stdio 로 MCP 서버를 실행합니다."""
    mcp.run()


if __name__ == "__main__":
    main()
