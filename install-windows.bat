@echo off
chcp 65001 >nul
setlocal
title Cubase 코드/보이싱/리듬 MCP 설치

echo ==============================================================
echo   Cubase 코드/보이싱/리듬 MCP - 설치
echo ==============================================================
echo.

set PY=
for %%C in (py python) do (
    if not defined PY (
        %%C -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
        if not errorlevel 1 set PY=%%C
    )
)

if not defined PY (
    echo [X] 파이썬 3.10 이상을 찾지 못했습니다.
    echo.
    echo     https://www.python.org/downloads/ 에서 설치해 주세요.
    echo     설치 화면에서 "Add Python to PATH" 를 꼭 체크하셔야 합니다.
    echo.
    pause
    exit /b 1
)
echo [O] 파이썬을 찾았습니다 ^(%PY%^)
echo.

echo 필요한 것을 설치하는 중입니다. 잠시 기다려 주세요...
%PY% -m pip install --upgrade pip >nul 2>&1
%PY% -m pip install -e "%~dp0."
if errorlevel 1 (
    echo.
    echo [X] 설치에 실패했습니다. 위의 메시지를 그대로 복사해서 문의해 주세요.
    pause
    exit /b 1
)
echo [O] 설치 완료
echo.
echo [!] 이 폴더는 옮기거나 지우지 마세요. 프로그램이 계속 참조합니다:
echo     %~dp0
echo.

%PY% -m cubase_mcp.setup_wizard
if errorlevel 1 (
    echo.
    echo [X] 등록에 실패했습니다. 위의 메시지를 확인해 주세요.
    pause
    exit /b 1
)

echo.
pause
