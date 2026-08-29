"""설치 마법사 — Claude Desktop 설정에 이 서버를 등록해 줍니다.

파이썬을 모르는 사람도 쓸 수 있게 만든 것이라, **기존 설정을 절대 덮어쓰지
않는 것** 을 최우선으로 합니다. 항상 백업을 먼저 만들고, 이미 있는 다른 MCP
서버 항목은 그대로 둔 채 우리 항목만 추가/갱신합니다.

    python -m cubase_mcp.setup_wizard              # 등록
    python -m cubase_mcp.setup_wizard --dry-run    # 뭘 할지 보기만
    python -m cubase_mcp.setup_wizard --remove     # 등록 해제
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SERVER_KEY = "cubase"


def claude_config_path() -> Path:
    """Claude Desktop 설정 파일의 표준 위치."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "Claude" / "claude_desktop_config.json"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def default_music_dir() -> Path:
    docs = Path.home() / "Documents"
    return (docs if docs.is_dir() else Path.home()) / "CubaseMCP"


def _load(path: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    """설정을 읽습니다. 돌려주는 두 번째 값은 문제가 있을 때의 설명입니다."""
    if not path.exists():
        return {}, None
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {}, f"설정 파일을 읽을 수 없습니다: {exc}"
    if not text.strip():
        return {}, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, (f"설정 파일이 올바른 JSON 이 아닙니다 ({exc}). "
                    f"직접 고치셨다면 문법을 확인해 주세요. "
                    f"안전을 위해 아무것도 바꾸지 않았습니다.")
    if not isinstance(data, dict):
        return {}, "설정 파일의 최상위가 객체(JSON object)가 아닙니다."
    return data, None


def _backup(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.stem}.backup-{stamp}{path.suffix}")
    shutil.copy2(path, target)
    return target


def server_entry(output_dir: Path, python: Optional[str] = None) -> Dict[str, Any]:
    return {
        "command": python or sys.executable,
        "args": ["-m", "cubase_mcp.server"],
        "env": {"CUBASE_MCP_OUTPUT_DIR": str(output_dir)},
    }


def self_test(output_dir: Path) -> Tuple[bool, str]:
    """실제로 MIDI 파일이 만들어지는지 확인합니다."""
    try:
        from .midi.smf import write as write_midi
        from .render import build_arrangement
        from .theory.chords import parse_progression

        output_dir.mkdir(parents=True, exist_ok=True)
        arrangement = build_arrangement(
            parse_progression("Cmaj7 Am7 Dm7 G7"),
            voicing="drop2", rhythm="pop_ballad", humanize="piano_natural",
            include_bass=True, tempo=100, seed=1,
        )
        path = output_dir / "설치확인.mid"
        write_midi(arrangement.midi, str(path))
        notes = sum(len(t.notes) for t in arrangement.midi.tracks)
        return True, f"테스트 파일을 만들었습니다: {path} (노트 {notes}개)"
    except Exception as exc:                     # pragma: no cover - 방어적
        return False, f"MIDI 생성에 실패했습니다: {exc}"


def install(config_path: Path, output_dir: Path, *, dry_run: bool = False,
            python: Optional[str] = None) -> int:
    print("=" * 62)
    print(" Cubase 코드/보이싱/리듬 MCP - 설치")
    print("=" * 62)
    print(f"  파이썬      : {sys.version.split()[0]}  ({sys.executable})")
    print(f"  설정 파일   : {config_path}")
    print(f"  저장 폴더   : {output_dir}")
    print()

    if sys.version_info < (3, 10):
        print("[X] 파이썬 3.10 이상이 필요합니다. 최신 버전을 설치한 뒤 다시 실행해 주세요.")
        return 1

    try:
        import mcp  # noqa: F401
    except ImportError:
        print("[X] 'mcp' 패키지가 없습니다. 먼저 아래 명령을 실행해 주세요:")
        print("      pip install -e .")
        return 1
    print("[O] mcp 패키지 확인")

    ok, message = self_test(output_dir)
    print(f"[{'O' if ok else 'X'}] {message}")
    if not ok:
        return 1

    data, error = _load(config_path)
    if error:
        print(f"[X] {error}")
        return 1

    servers = data.get("mcpServers")
    if servers is None:
        servers = {}
    elif not isinstance(servers, dict):
        print("[X] 설정의 mcpServers 항목이 객체가 아닙니다. 안전을 위해 중단합니다.")
        return 1

    others = [k for k in servers if k != SERVER_KEY]
    if others:
        print(f"[i] 이미 등록된 다른 서버 {len(others)}개는 그대로 둡니다: {', '.join(others)}")
    already = SERVER_KEY in servers

    entry = server_entry(output_dir, python)
    if dry_run:
        print("\n[미리보기] 아래 내용을 추가/갱신합니다 (실제로 쓰지 않았습니다):")
        print(json.dumps({SERVER_KEY: entry}, indent=2, ensure_ascii=False))
        return 0

    backup = _backup(config_path)
    if backup:
        print(f"[O] 기존 설정을 백업했습니다: {backup.name}")

    servers[SERVER_KEY] = entry
    data["mcpServers"] = servers
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    except OSError as exc:
        print(f"[X] 설정 파일을 저장할 수 없습니다: {exc}")
        return 1

    print(f"[O] '{SERVER_KEY}' 서버를 {'갱신' if already else '등록'}했습니다.")
    print()
    print("-" * 62)
    print(" 이제 Claude Desktop 을 완전히 종료했다가 다시 실행하세요.")
    print(" (창만 닫으면 안 됩니다. 작업 표시줄 트레이 아이콘에서 종료)")
    print()
    print(" 다시 켠 뒤 이렇게 말해 보세요:")
    print('   "설치 잘 됐는지 확인해줘"')
    print('   "C키로 시티팝 8마디 만들어줘"')
    print("-" * 62)
    return 0


def remove(config_path: Path, *, dry_run: bool = False) -> int:
    data, error = _load(config_path)
    if error:
        print(f"[X] {error}")
        return 1
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or SERVER_KEY not in servers:
        print(f"[i] '{SERVER_KEY}' 항목이 없습니다. 지울 것이 없습니다.")
        return 0
    if dry_run:
        print(f"[미리보기] '{SERVER_KEY}' 항목을 지웁니다 (실제로 지우지 않았습니다).")
        return 0
    backup = _backup(config_path)
    if backup:
        print(f"[O] 기존 설정을 백업했습니다: {backup.name}")
    del servers[SERVER_KEY]
    data["mcpServers"] = servers
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(f"[O] '{SERVER_KEY}' 등록을 해제했습니다. Claude Desktop 을 다시 시작하세요.")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cubase-mcp-setup",
        description="Claude Desktop 에 Cubase MCP 서버를 등록합니다.",
    )
    parser.add_argument("--config", type=Path, default=None,
                        help="claude_desktop_config.json 경로 (기본: 표준 위치)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="MIDI 파일을 저장할 폴더 (기본: 내 문서/CubaseMCP)")
    parser.add_argument("--python", default=None,
                        help="설정에 적을 파이썬 실행 파일 경로 (기본: 지금 실행 중인 것)")
    parser.add_argument("--dry-run", action="store_true", help="바꾸지 않고 보기만")
    parser.add_argument("--remove", action="store_true", help="등록 해제")
    args = parser.parse_args(argv)

    config_path = args.config or claude_config_path()
    if args.remove:
        return remove(config_path, dry_run=args.dry_run)
    return install(config_path, args.output_dir or default_music_dir(),
                   dry_run=args.dry_run, python=args.python)


if __name__ == "__main__":
    raise SystemExit(main())
