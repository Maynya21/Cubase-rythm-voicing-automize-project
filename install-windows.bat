@echo off
setlocal
cd /d "%~dp0"

echo ==============================================================
echo   Cubase Chord / Voicing / Rhythm MCP - Installer
echo ==============================================================
echo.

rem --- find a usable Python 3.10+ -------------------------------------
set "PY="
for %%C in (py python python3) do (
    if not defined PY (
        %%C -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
        if not errorlevel 1 set "PY=%%C"
    )
)

if not defined PY (
    echo [X] Python 3.10 or newer was not found.
    echo.
    echo     1. Download it from  https://www.python.org/downloads/
    echo     2. IMPORTANT: tick "Add Python to PATH" on the first setup screen
    echo     3. Run this installer again
    echo.
    pause
    exit /b 1
)

echo [OK] Python found ^(%PY%^)
echo.

rem --- install dependencies -------------------------------------------
echo Installing packages, this may take a minute...
%PY% -m pip --version >nul 2>&1
if errorlevel 1 %PY% -m ensurepip --upgrade
%PY% -m pip install -e .
if errorlevel 1 (
    echo.
    echo [X] Installation failed. Please copy the messages above and send them.
    echo.
    pause
    exit /b 1
)
echo [OK] Packages installed
echo.
echo [!] Keep this folder where it is - do not move or delete it:
echo     %~dp0
echo.

rem --- register with Claude Desktop -----------------------------------
rem     From here on the Python script prints Korean guidance.
%PY% -m cubase_mcp.setup_wizard
if errorlevel 1 (
    echo.
    echo [X] Registration failed. See the messages above.
    pause
    exit /b 1
)

echo.
pause
