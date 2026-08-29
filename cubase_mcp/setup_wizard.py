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


CONFIG_NAME = "claude_desktop_config.json"


def _windows_candidates() -> List[Path]:
    """Windows 에서 Claude Desktop 설정이 있을 수 있는 위치들.

    설치 방식에 따라 위치가 다릅니다.

    * 일반 설치 -> ``%APPDATA%\\Claude``
    * **Microsoft Store 설치** -> Store 앱은 파일 접근이 격리되어 있어
      ``%APPDATA%`` 쓰기가
      ``%LOCALAPPDATA%\\Packages\\<패키지명>\\LocalCache\\Roaming\\Claude``
      로 리디렉션됩니다. 그래서 ``%APPDATA%\\Claude`` 에 파일을 써 두면
      앱이 영영 읽지 못합니다.
    """
    out: List[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        out.append(Path(appdata) / "Claude" / CONFIG_NAME)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        packages = Path(local) / "Packages"
        if packages.is_dir():
            for entry in sorted(packages.glob("*laude*")):
                out.append(entry / "LocalCache" / "Roaming" / "Claude" / CONFIG_NAME)
        out.append(Path(local) / "Claude" / CONFIG_NAME)
    return out


def config_candidates() -> List[Path]:
    """플랫폼별로 확인해 볼 설정 파일 경로 목록."""
    system = platform.system()
    if system == "Windows":
        return _windows_candidates()
    if system == "Darwin":
        return [Path.home() / "Library" / "Application Support" / "Claude" / CONFIG_NAME]
    return [Path.home() / ".config" / "Claude" / CONFIG_NAME]


def _looks_live(path: Path) -> bool:
    """그 폴더가 **실제로 앱이 쓰고 있는** 데이터 폴더인지.

    설정 파일만 덩그러니 있는 폴더는 우리가 예전에 잘못 만든 빈 폴더일 수
    있습니다. 앱이 쓰는 폴더에는 Cache, logs, Local Storage 같은 것이 함께
    있으므로 그걸로 구분합니다.
    """
    folder = path.parent
    if not folder.is_dir():
        return False
    others = [e for e in folder.iterdir() if e.name != CONFIG_NAME]
    return bool(others)


def claude_config_path() -> Path:
    """앱이 실제로 읽을 설정 파일 경로를 하나 고릅니다."""
    return (resolve_config_targets() or config_candidates())[0]


def resolve_config_targets() -> List[Path]:
    """등록해야 할 설정 파일들.

    앱 데이터가 실제로 살아 있는 폴더를 우선하고, 그런 곳이 여러 군데면
    (일반 설치와 Store 설치를 함께 쓰는 경우) 전부 등록합니다.
    """
    candidates = config_candidates()
    live = [p for p in candidates if _looks_live(p)]
    if live:
        return live
    existing = [p for p in candidates if p.exists()]
    return existing or candidates[:1]


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
                        help="claude_desktop_config.json 경로 (기본: 자동 감지)")
    parser.add_argument("--where", action="store_true",
                        help="설정 파일을 어디서 찾는지만 보여주기")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="MIDI 파일을 저장할 폴더 (기본: 내 문서/CubaseMCP)")
    parser.add_argument("--python", default=None,
                        help="설정에 적을 파이썬 실행 파일 경로 (기본: 지금 실행 중인 것)")
    parser.add_argument("--dry-run", action="store_true", help="바꾸지 않고 보기만")
    parser.add_argument("--remove", action="store_true", help="등록 해제")
    args = parser.parse_args(argv)

    if args.where:
        return _report_locations()

    targets = [args.config] if args.config else resolve_config_targets()
    if args.remove:
        return max(remove(path, dry_run=args.dry_run) for path in targets)

    if len(targets) > 1:
        print(f"[i] 설정 파일을 {len(targets)}군데에서 찾았습니다. 모두 등록합니다.\n")
    output_dir = args.output_dir or default_music_dir()
    codes = [install(path, output_dir, dry_run=args.dry_run, python=args.python)
             for path in targets]
    return max(codes)


def _report_locations() -> int:
    """어떤 경로를 보고 있는지 그대로 보여줍니다 (문제 해결용)."""
    print("확인하는 위치:")
    chosen = set(resolve_config_targets())
    for path in config_candidates():
        if _looks_live(path):
            state = "앱이 사용 중"
        elif path.exists():
            state = "파일은 있지만 앱 데이터가 없음"
        elif path.parent.is_dir():
            state = "폴더만 있음"
        else:
            state = "없음"
        mark = "->" if path in chosen else "  "
        print(f"  {mark} [{state}] {path}")
    print()
    print("'->' 표시된 곳에 등록합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
