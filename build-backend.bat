@echo off
setlocal EnableDelayedExpansion

:: =========================================================================
::  Build render-backend.exe  (PyInstaller --onefile)
::
::  Usage:
::    build-backend.bat          Build with defaults
::    build-backend.bat clean    Remove old build artifacts first
::    build-backend.bat debug    Build with --debug=all + console output
::
::  Requirements:
::    - Python 3.11+ with venv at backend\.venv
::    - PyInstaller installed in that venv
::
::  Output:
::    backend\dist\render-backend.exe
:: =========================================================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "VENV=%BACKEND%\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "PIP=%VENV%\Scripts\pip.exe"

echo.
echo ============================================================
echo   Render Studio — Backend EXE Builder
echo ============================================================
echo.

:: ─── Validate environment ────────────────────────────────────────────────
if not exist "%PYTHON%" (
    echo [ERROR] Python venv not found at %VENV%
    echo         Run: cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    goto :fail
)

:: ─── Handle "clean" argument ─────────────────────────────────────────────
if /I "%~1"=="clean" (
    echo [STEP] Cleaning old build artifacts...
    if exist "%BACKEND%\build" rmdir /s /q "%BACKEND%\build" 2>nul
    if exist "%BACKEND%\dist"  rmdir /s /q "%BACKEND%\dist"  2>nul
    echo         Done.
    echo.
)

:: ─── Ensure PyInstaller is installed ─────────────────────────────────────
echo [STEP] Checking PyInstaller...
"%PYTHON%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo         PyInstaller not found. Installing...
    "%PIP%" install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller
        goto :fail
    )
)
"%PYTHON%" -c "import PyInstaller; print(f'         PyInstaller {PyInstaller.__version__} OK')"

:: ─── Clean __pycache__ (prevents stale bytecode issues) ──────────────────
echo [STEP] Cleaning __pycache__...
for /d /r "%BACKEND%\app" %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)
echo         Done.

:: ─── Build ───────────────────────────────────────────────────────────────
echo.
echo [STEP] Building render-backend.exe ...
echo         This may take 3-8 minutes depending on your machine.
echo.

set "EXTRA_FLAGS=--clean"
if /I "%~1"=="debug" (
    set "EXTRA_FLAGS=--clean --debug=all"
    echo         ** DEBUG MODE **
    echo.
)

cd /d "%BACKEND%"
"%PYTHON%" -m playwright install chromium
if errorlevel 1 (
    echo [ERROR] Failed to install Playwright Chromium
    goto :fail
)

"%PYTHON%" -m PyInstaller %EXTRA_FLAGS% ^
    --noconfirm ^
    --onefile ^
    --name render-backend ^
    --collect-all whisper ^
    --collect-all scenedetect ^
    --collect-all playwright ^
    --collect-all openpyxl ^
    --collect-all yt_dlp ^
    --collect-all cv2 ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    run_backend_server.py

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed!
    echo.
    echo ── Common fixes ──────────────────────────────────────────
    echo  1. Missing module?  Add another --hidden-import or --collect-all
    echo  2. DLL conflict?    Retry after clearing backend\build and backend\dist
    echo  3. Out of memory?   Close other apps, try: set PYINSTALLER_COMPILE_BOOTLOADER=1
    echo  4. Anti-virus?      Add backend\dist\ to exclusion list
    echo.
    goto :fail
)

:: ─── Verify output ──────────────────────────────────────────────────────
set "EXE=%BACKEND%\dist\render-backend.exe"
if not exist "%EXE%" (
    echo [ERROR] Build completed but exe not found at %EXE%
    goto :fail
)

for %%A in ("%EXE%") do set "SIZE=%%~zA"
set /a SIZE_MB=%SIZE% / 1048576

echo.
echo ============================================================
echo   BUILD SUCCESSFUL
echo ============================================================
echo   Output: %EXE%
echo   Size:   %SIZE_MB% MB
echo.
echo   Quick test:
echo     cd backend\dist
echo     render-backend.exe
echo     (then open http://localhost:8000 in browser)
echo.
echo   Notes:
echo     - ffmpeg/ffprobe must be on PATH or set FFMPEG_BIN env
echo     - Whisper models auto-download on first run (~700MB)
echo     - Playwright browsers: npx playwright install chromium
echo ============================================================
echo.
goto :end

:fail
echo.
echo [BUILD FAILED]
echo.
exit /b 1

:end
endlocal
exit /b 0
