@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM YouTube Chushutu Installer for Windows
REM ============================================================

REM --- Resolve project directory properly ---
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."
set "PROJECT_DIR=%CD%"
popd
set "BACKEND_DIR=%PROJECT_DIR%\backend"
set "VENV_DIR=%BACKEND_DIR%\.venv"

echo.
echo =========================================
echo   YouTube Chushutu Installer
echo =========================================
echo.

REM --- Python check ---
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python ga mitsukarimsen.
    echo   https://www.python.org/downloads/
    echo   Install ji ni "Add Python to PATH" ni check wo irete kudasai.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [OK] %PYTHON_VER%

REM --- ffmpeg check ---
where ffmpeg >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] ffmpeg found
) else (
    echo [WARN] ffmpeg not found. Required for audio conversion.
    echo.
    echo   Download from: https://www.gyan.dev/ffmpeg/builds/
    echo   Add ffmpeg.exe to PATH.
    echo   Video download works without ffmpeg.
    echo.
)

REM --- Create virtual environment ---
echo.
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo [OK] Virtual environment already exists
) else (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    echo [OK] Virtual environment created
)

REM --- Install packages ---
echo Installing packages...
"%VENV_DIR%\Scripts\pip.exe" install --upgrade pip -q
"%VENV_DIR%\Scripts\pip.exe" install -e "%BACKEND_DIR%" -q
echo [OK] Package installation complete

REM --- Version check ---
echo.
echo --- Installed versions ---
"%VENV_DIR%\Scripts\python.exe" -c "import yt_dlp, fastapi, pydantic; print(f'  yt-dlp:   {yt_dlp.version.__version__}'); print(f'  FastAPI:  {fastapi.__version__}'); print(f'  Pydantic: {pydantic.__version__}')"

REM --- Done ---
echo.
echo =========================================
echo   Install complete!
echo =========================================
echo.
echo --- How to start backend ---
echo   Double-click: %PROJECT_DIR%\start.bat
echo.
echo --- How to load Chrome extension ---
echo   1. Open chrome://extensions in Chrome
echo   2. Enable Developer Mode
echo   3. Click "Load unpacked"
echo   4. Select folder: %PROJECT_DIR%\extension
echo.
echo --- How to update yt-dlp ---
echo   Double-click: %PROJECT_DIR%\scripts\update-ytdlp.bat
echo.
pause
