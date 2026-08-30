"""만든 파일의 '레시피' 기록.

``휴머나이즈만 빼고 다시`` 같은 수정을 하려면 두 가지 길이 있습니다.

1. 만들어 둔 MIDI 를 다시 읽어서 흔들린 타이밍을 되돌린다 — 추론이라 완전하지
   않습니다. 원래 그리드가 무엇이었는지 확실히 알 수 없기 때문입니다.
2. **무엇을 어떻게 만들었는지 적어 두고, 바꿀 것만 바꿔 다시 만든다** —
   추론이 없어 정확합니다.

우리가 만든 파일에 대해서는 2번이 항상 낫습니다. 이 모듈이 그 기록을 맡습니다.
직접 연주해 넣은 트랙처럼 우리가 만들지 않은 것은 1번이 필요하고, 그건 MIDI
읽기가 생긴 뒤의 일입니다.

기록은 출력 폴더의 ``_recipes.json`` 하나에 모읍니다. 파일마다 사이드카를
두면 드래그할 폴더가 지저분해지기 때문입니다.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

INDEX_NAME = "_recipes.json"

#: 기록을 남길 항목. 이 목록에 없는 인자는 저장하지 않습니다.
TRACKED = (
    "chords", "key", "voicing", "rhythm", "rhythm_mode", "arp_order", "strum_ms",
    "tempo", "time_signature", "beats_per_chord", "repeat",
    "low", "high", "max_notes", "add_tensions", "voice_leading",
    "swing", "humanize", "humanize_amount", "bass_humanize",
    "velocity", "duration_scale", "let_ring",
    "include_bass", "bass_style", "instrument", "bass_instrument", "seed",
)

#: 한 폴더에 남겨 둘 최대 기록 수 (오래된 것부터 정리)
MAX_ENTRIES = 300


def index_path(folder: Path) -> Path:
    return Path(folder) / INDEX_NAME


def _load_all(folder: Path) -> Dict[str, Any]:
    path = index_path(folder)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 기록이 깨져도 음악 만드는 일이 멈추면 안 됩니다.
        return {}
    return data if isinstance(data, dict) else {}


def _order(entry: Dict[str, Any]) -> tuple:
    """정렬 기준. 같은 초에 여러 개가 저장돼도 순서가 확실해야 합니다."""
    return (int(entry.get("seq", 0)), str(entry.get("created", "")))


def save(folder: Path, filename: str, params: Dict[str, Any],
         summary: Optional[Dict[str, Any]] = None) -> None:
    """한 파일의 레시피를 남깁니다. 실패해도 조용히 넘어갑니다."""
    folder = Path(folder)
    entries = _load_all(folder)
    next_seq = max((int(e.get("seq", 0)) for e in entries.values()), default=0) + 1
    entries[str(filename)] = {
        "seq": next_seq,
        "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "params": {k: v for k, v in params.items()
                   if k in TRACKED and v is not None},
        "summary": summary or {},
    }
    if len(entries) > MAX_ENTRIES:
        for name in sorted(entries, key=lambda n: _order(entries[n]))[
                :len(entries) - MAX_ENTRIES]:
            entries.pop(name, None)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        index_path(folder).write_text(
            json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass          # 기록을 못 남겨도 파일 생성 자체는 성공한 상태입니다


def load(folder: Path, filename: str) -> Optional[Dict[str, Any]]:
    return _load_all(Path(folder)).get(str(filename))


def latest(folder: Path) -> Optional[str]:
    """가장 최근에 만든, 기록이 남아 있고 실제로 존재하는 파일 이름."""
    folder = Path(folder)
    entries = _load_all(folder)
    for name in sorted(entries, key=lambda n: _order(entries[n]), reverse=True):
        if (folder / name).is_file():
            return name
    return None


def known(folder: Path) -> List[str]:
    folder = Path(folder)
    entries = _load_all(folder)
    return [n for n in sorted(entries, key=lambda n: _order(entries[n]),
                              reverse=True) if (folder / n).is_file()]


def merge(base: Dict[str, Any], changes: Dict[str, Any]) -> Dict[str, Any]:
    """기록된 설정 위에 바꿀 것만 덮어씁니다 (None 은 '그대로 두기')."""
    merged = dict(base)
    for key, value in changes.items():
        if value is not None and key in TRACKED:
            merged[key] = value
    return merged


def changed_fields(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """무엇이 바뀌었는지 사람이 읽을 형태로."""
    out: Dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old != new:
            out[key] = {"before": old, "after": new}
    return out
