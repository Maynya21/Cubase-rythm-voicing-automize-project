#!/usr/bin/env bash
# macOS / Linux 설치 스크립트
set -euo pipefail
cd "$(dirname "$0")"

echo "=============================================================="
echo "  Cubase 코드/보이싱/리듬 MCP - 설치"
echo "=============================================================="
echo

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
        PY="$candidate"; break
    fi
done

if [ -z "$PY" ]; then
    echo "[X] 파이썬 3.10 이상을 찾지 못했습니다. https://www.python.org/downloads/"
    exit 1
fi
echo "[O] 파이썬을 찾았습니다 ($PY)"
echo

"$PY" -m pip install -e .
echo "[O] 설치 완료"
echo

"$PY" -m cubase_mcp.setup_wizard
