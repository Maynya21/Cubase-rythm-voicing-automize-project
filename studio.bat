@echo off
setlocal
cd /d "%~dp0"
title Cubase MCP Studio

set "PY="
for %%C in (py python python3) do (
    if not defined PY (
        %%C -c "import cubase_mcp.studio" >nul 2>&1
        if not errorlevel 1 set "PY=%%C"
    )
)

if not defined PY (
    echo [X] Not installed yet.
    echo.
    echo     Run install-windows.bat first,
    echo     or open a command prompt in this folder and run:
    echo.
    echo         py -m pip install -e .
    echo.
    pause
    exit /b 1
)

%PY% -m cubase_mcp.studio
if errorlevel 1 (
    echo.
    echo [X] Stopped with an error. See the messages above.
    pause
    exit /b 1
)
