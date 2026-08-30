"""Cubase MCP 스튜디오 — 마우스로 쓰는 로컬 화면.

리듬을 ``x--x-x--`` 처럼 머릿속으로 세는 대신 **격자를 눌러 그리고**, 코드와
보이싱을 골라 바로 MIDI 를 뽑는 화면입니다. 표준 라이브러리만 써서 로컬에
작은 웹 서버를 띄우고 브라우저로 엽니다. tkinter 는 파이썬 설치 방식에 따라
빠져 있을 수 있어 쓰지 않았습니다.

    python -m cubase_mcp.studio

바깥에서 접근할 수 없도록 127.0.0.1 에만 바인딩하고, 페이지에 심어 둔 토큰이
있는 요청만 받습니다. 다른 프로그램이나 웹페이지가 이 서버를 건드릴 수 없게
하기 위해서입니다.
"""

from __future__ import annotations

import argparse
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from . import __version__
from .config import SETTINGS
from .humanize import list_humanize_profiles
from .render import BASS_STYLES, GM_PROGRAMS, build_arrangement
from .targets import deliver
from .theory.notes import note_name, parse_note
from .theory.progression import (analyze, generate, list_genres,
                                 list_progression_templates)
from .theory.rhythm import (GRID_HELP, RHYTHM_PATTERNS, list_rhythm_patterns,
                            pattern_to_grid, resolve_pattern)
from .theory.scales import parse_chords, parse_key
from .theory.voicing import list_voicing_styles, voice_progression, voicing_movement

PAGE = Path(__file__).with_name("studio.html")

#: 한 번에 받을 수 있는 요청 본문 크기 (장난스러운 큰 요청 차단)
MAX_BODY = 256 * 1024


class StudioError(ValueError):
    """화면에 그대로 보여 줄 오류."""


# --------------------------------------------------------------------------- #
# 요청 처리 — 음악 계산은 전부 기존 엔진을 그대로 씁니다
# --------------------------------------------------------------------------- #

def _time_signature(text: str) -> tuple:
    parts = str(text or "4/4").replace(" ", "").split("/")
    if len(parts) != 2:
        raise StudioError(f"박자표는 '4/4' 형식이어야 합니다: {text!r}")
    try:
        num, den = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise StudioError(f"박자표는 '4/4' 형식이어야 합니다: {text!r}") from exc
    if not 1 <= num <= 32 or den not in (1, 2, 4, 8, 16, 32):
        raise StudioError(f"쓸 수 없는 박자표입니다: {text!r}")
    return num, den


def api_capabilities() -> Dict[str, Any]:
    """화면을 채울 목록들."""
    return {
        "version": __version__,
        "output_dir": str(SETTINGS.output_dir),
        "voicings": list_voicing_styles(),
        "rhythms": list_rhythm_patterns(),
        "humanize": list_humanize_profiles(),
        "bass_styles": [{"name": k, "description": v} for k, v in BASS_STYLES.items()],
        "instruments": sorted(GM_PROGRAMS),
        "genres": list_genres(),
        "templates": list_progression_templates(),
        "grid_help": GRID_HELP,
    }


def api_preview(payload: Dict[str, Any]) -> Dict[str, Any]:
    """파일을 만들지 않고 코드·보이싱·리듬을 확인합니다."""
    key_text = payload.get("key") or None
    chords, resolved_key, used_roman = parse_chords(payload.get("chords") or "", key_text)
    key_obj = resolved_key or (parse_key(key_text) if key_text else parse_key("C"))

    num, den = _time_signature(payload.get("time_signature"))
    bar_beats = num * 4.0 / den
    pattern = resolve_pattern(payload.get("rhythm") or "quarter",
                              beats_per_bar=bar_beats,
                              mode=payload.get("rhythm_mode") or "block")

    low = parse_note(payload.get("low") or "C2", SETTINGS.middle_c_octave)
    high = parse_note(payload.get("high") or "C5", SETTINGS.middle_c_octave)
    if low >= high:
        raise StudioError("최저음이 최고음보다 낮아야 합니다")

    voicings = voice_progression(
        chords,
        style=payload.get("voicing") or "close",
        low=low, high=high,
        max_notes=payload.get("max_notes") or None,
        add_tensions=bool(payload.get("add_tensions")),
    )
    flats = key_obj.prefers_flats
    return {
        "key": key_obj.name,
        "input_style": "도수" if used_roman else "심볼",
        "chords": [
            {
                **info,
                "voicing": [note_name(p, SETTINGS.middle_c_octave, flats) for p in v],
                "midi": list(v),
            }
            for info, v in zip(analyze(chords, key_obj), voicings)
        ],
        "movement": round(voicing_movement(voicings), 2),
        "rhythm": {
            "name": pattern.name,
            "description": pattern.description,
            "source": "그리드" if "직접입력" in pattern.tags else "프리셋",
            "mode": pattern.mode,
            "length_beats": pattern.beats_per_bar,
            "grid": pattern_to_grid(pattern, int(payload.get("division") or 2), bar_beats),
            "bars": max(1, int(round(pattern.beats_per_bar / bar_beats))),
            "hits": [
                {"start": round(s, 4), "length": round(d, 4), "velocity": round(v, 3)}
                for s, d, v in pattern.events
            ],
        },
    }


def api_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """실제로 MIDI 파일을 만듭니다."""
    key_text = payload.get("key") or None
    chords, resolved_key, used_roman = parse_chords(payload.get("chords") or "", key_text)
    key_obj = resolved_key or (parse_key(key_text) if key_text else None)
    ts = _time_signature(payload.get("time_signature"))

    low = parse_note(payload.get("low") or "C2", SETTINGS.middle_c_octave)
    high = parse_note(payload.get("high") or "C5", SETTINGS.middle_c_octave)
    if low >= high:
        raise StudioError("최저음이 최고음보다 낮아야 합니다")

    result = build_arrangement(
        chords,
        key=key_obj,
        tempo=float(payload.get("tempo") or 120),
        time_signature=ts,
        beats_per_chord=payload.get("beats_per_chord") or None,
        repeat=int(payload.get("repeat") or 1),
        voicing=payload.get("voicing") or "close",
        low=low, high=high,
        max_notes=payload.get("max_notes") or None,
        add_tensions=bool(payload.get("add_tensions")),
        rhythm=payload.get("rhythm") or "quarter",
        rhythm_mode=payload.get("rhythm_mode") or "block",
        humanize=payload.get("humanize") or "subtle",
        humanize_amount=float(payload.get("humanize_amount", 1.0)),
        velocity=int(payload.get("velocity") or 90),
        include_bass=bool(payload.get("include_bass")),
        bass_style=payload.get("bass_style") or "root",
        chord_program=payload.get("instrument") or None,
        bass_program=payload.get("bass_instrument") or "finger_bass",
        seed=payload.get("seed"),
    )
    delivered = deliver(result, "midi_file",
                        filename=payload.get("filename") or None,
                        default_stem=f"studio-{payload.get('voicing') or 'close'}")
    flats = key_obj.prefers_flats if key_obj else False
    romans = ([info["roman"] for info in analyze(chords, key_obj)] if key_obj
              else [""] * len(chords))
    return {
        **delivered,
        "chords": [c.symbol for c in chords],
        "input_style": "도수" if used_roman else "심볼",
        "bars": round(result.total_bars, 3),
        "note_count": sum(len(t.notes) for t in result.midi.tracks),
        "tracks": [t.name for t in result.midi.tracks],
        "humanize": result.humanize,
        "rhythm_detail": result.rhythm_description,
        "warnings": result.warnings,
        "voicings": [
            {"chord": s.chord.symbol,
             "roman": romans[i % len(romans)] if romans else "",
             "notes": [note_name(p, SETTINGS.middle_c_octave, flats) for p in s.voicing]}
            for i, s in enumerate(result.slots)
        ],
    }


def api_suggest(payload: Dict[str, Any]) -> Dict[str, Any]:
    """장르/템플릿으로 진행을 추천받습니다."""
    progression = generate(
        key=payload.get("key") or "C",
        genre=payload.get("genre") or "pop",
        bars=int(payload.get("bars") or 4),
        template=payload.get("template") or None,
        seed=payload.get("seed"),
    )
    return {
        "chords": progression.symbols,
        "chords_text": " ".join(progression.symbols),
        "romans": progression.romans,
        "romans_text": "-".join(progression.romans),
        "template": progression.template,
        "note": progression.adapted_note,
    }


def api_files(_: Dict[str, Any]) -> Dict[str, Any]:
    folder = SETTINGS.output_dir
    if not folder.is_dir():
        return {"output_dir": str(folder), "files": []}
    files = sorted(folder.glob("*.mid"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
    return {
        "output_dir": str(folder),
        "files": [{"name": f.name, "size": f.stat().st_size} for f in files],
    }


ROUTES: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "/api/capabilities": lambda _: api_capabilities(),
    "/api/preview": api_preview,
    "/api/generate": api_generate,
    "/api/suggest": api_suggest,
    "/api/files": api_files,
}


# --------------------------------------------------------------------------- #
# 로컬 웹 서버
# --------------------------------------------------------------------------- #

class _Handler(BaseHTTPRequestHandler):
    server_version = f"CubaseStudio/{__version__}"
    token = ""
    shutdown_hook: Optional[Callable[[], None]] = None

    def log_message(self, *args) -> None:      # 콘솔을 조용하게
        pass

    # -- 보안: 로컬에서 온 요청인지 확인 -----------------------------------
    def _local_only(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "[::1]", "::1"):
            return False
        origin = self.headers.get("Origin")
        if origin:
            hostname = urlparse(origin).hostname
            if hostname not in ("127.0.0.1", "localhost", "::1"):
                return False
        return True

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Dict[str, Any]) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if not self._local_only():
            self._json(403, {"error": "로컬 요청만 받습니다"})
            return
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                html = PAGE.read_text(encoding="utf-8")
            except OSError as exc:
                self._send(500, f"화면 파일을 읽을 수 없습니다: {exc}".encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            html = html.replace("{{TOKEN}}", self.token)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        self._json(404, {"error": "없는 주소입니다"})

    def do_POST(self) -> None:
        if not self._local_only():
            self._json(403, {"error": "로컬 요청만 받습니다"})
            return
        if self.headers.get("X-Studio-Token") != self.token:
            self._json(403, {"error": "토큰이 올바르지 않습니다"})
            return

        path = urlparse(self.path).path
        if path == "/api/quit":
            self._json(200, {"ok": True})
            if self.shutdown_hook:
                threading.Thread(target=self.shutdown_hook, daemon=True).start()
            return

        handler = ROUTES.get(path)
        if handler is None:
            self._json(404, {"error": "없는 주소입니다"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._json(413, {"error": "요청이 너무 큽니다"})
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise StudioError("요청 형식이 올바르지 않습니다")
        except (json.JSONDecodeError, StudioError) as exc:
            self._json(400, {"error": str(exc)})
            return

        try:
            self._json(200, handler(payload))
        except (ValueError, KeyError, OSError) as exc:
            # 예상 가능한 입력 오류는 화면에 그대로 보여 줍니다.
            self._json(400, {"error": str(exc) or exc.__class__.__name__})
        except Exception as exc:                  # pragma: no cover - 방어적
            self._json(500, {"error": f"예상하지 못한 오류: {exc}"})


def build_server(port: int = 0) -> ThreadingHTTPServer:
    """127.0.0.1 에만 바인딩된 서버를 만듭니다. ``port=0`` 이면 빈 포트 자동 선택."""
    handler = type("_BoundHandler", (_Handler,), {"token": secrets.token_urlsafe(24)})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    handler.shutdown_hook = server.shutdown
    return server


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cubase-studio",
        description="마우스로 리듬을 그리고 코드를 골라 MIDI 를 만드는 로컬 화면",
    )
    parser.add_argument("--port", type=int, default=0, help="포트 (기본: 자동)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않음")
    args = parser.parse_args(argv)

    server = build_server(args.port)
    host, port = server.server_address[:2]
    url = f"http://127.0.0.1:{port}/"

    print("=" * 62)
    print(" Cubase MCP 스튜디오")
    print("=" * 62)
    print(f"  주소       : {url}")
    print(f"  저장 폴더  : {SETTINGS.output_dir}")
    print()
    print("  브라우저에서 리듬을 그리고 [만들기] 를 누르면 저장됩니다.")
    print("  이 창을 닫거나 Ctrl+C 를 누르면 종료됩니다.")
    print("=" * 62)

    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
