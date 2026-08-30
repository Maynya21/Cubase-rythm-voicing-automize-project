"""서버 설정 — 출력 폴더, 기본값."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ENV_OUTPUT_DIR = "CUBASE_MCP_OUTPUT_DIR"

#: 파일 이름에 쓸 수 없는 문자 (Windows 기준으로 넉넉하게)
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def default_output_dir() -> Path:
    """기본 출력 폴더.

    ``CUBASE_MCP_OUTPUT_DIR`` 환경변수가 있으면 그것을,
    없으면 ``~/Documents/CubaseMCP`` (없으면 ``~/CubaseMCP``) 를 씁니다.
    """
    env = os.environ.get(ENV_OUTPUT_DIR)
    if env:
        return Path(env).expanduser()
    docs = Path.home() / "Documents"
    base = docs if docs.is_dir() else Path.home()
    return base / "CubaseMCP"


@dataclass
class Settings:
    output_dir: Path = field(default_factory=default_output_dir)
    tempo: float = 120.0
    time_signature: tuple = (4, 4)
    middle_c_octave: int = 3          # Cubase 기본 표기 (C3 = 60)
    #: Cubase 에서 'MIDI 파일 가져오기' 에 할당한 단축키.
    #: 메뉴 이름은 판본마다 다르지만 키 커맨드는 사용자가 정하므로 안정적입니다.
    import_key: str = ""

    def resolve(self, filename: str, subfolder: Optional[str] = None) -> Path:
        """안전한 절대 경로를 만들고 폴더를 생성합니다."""
        directory = self.output_dir
        if subfolder:
            directory = directory / safe_filename(subfolder)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / safe_filename(filename)


def safe_filename(name: str, default: str = "output", max_len: int = 120) -> str:
    """파일 이름으로 쓸 수 있게 정리합니다 (경로 이탈 방지 포함)."""
    name = str(name).strip()
    name = name.replace("/", "-").replace("\\", "-")
    name = _UNSAFE.sub("_", name)
    name = name.strip(". ")
    if not name:
        return default
    stem, dot, ext = name.rpartition(".")
    check = (stem if dot else name).upper()
    if check in _RESERVED:
        name = "_" + name
    if len(name) > max_len:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            name = stem[: max_len - len(ext) - 1] + "." + ext
        else:
            name = name[:max_len]
    return name


def unique_path(path: Path) -> Path:
    """같은 이름이 있으면 ``-2``, ``-3`` 을 붙여 덮어쓰기를 막습니다."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(2, 1000):
        candidate = path.with_name(f"{stem}-{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"이름이 겹치는 파일이 너무 많습니다: {path}")


SETTINGS = Settings()
