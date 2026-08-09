@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM YouTube Chushutu - Installer for Windows
REM Note: keep every echo ASCII-only. Japanese punctuation such as
REM full-width brackets breaks CMD parsing inside if/else blocks.
REM ============================================================

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

REM --- Python ---
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found.
    echo   Install it from https://www.python.org/downloads/
    echo   Be sure to tick "Add Python to PATH" during setup.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [OK] %PYTHON_VER%

REM --- ffmpeg ---
REM Without ffmpeg, high-quality downloads and MP3 conversion both fail,
REM so offer to install it right here rather than leaving it to chance.
where ffmpeg >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] ffmpeg found
    goto :venv
)

echo [WARN] ffmpeg not found.
echo        Needed for MP3 conversion and for 1080p or higher video.
echo        Without it you can still download up to about 720p.
echo.
where winget >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   winget is unavailable. Install ffmpeg manually:
    echo   https://www.gyan.dev/ffmpeg/builds/
    echo.
    goto :venv
)

set /p INSTALL_FFMPEG="Install ffmpeg now with winget? [Y/n]: "
if /i "%INSTALL_FFMPEG%"=="n" goto :venv
echo Installing ffmpeg...
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
echo.
echo [NOTE] Close and reopen this window so ffmpeg appears on PATH.
echo.

:venv
echo.
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo [OK] Virtual environment already exists
) else (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    echo [OK] Virtual environment created
)

echo Installing packages...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip -q
"%VENV_DIR%\Scripts\python.exe" -m pip install -e "%BACKEND_DIR%" -q
echo [OK] Packages installed

echo.
echo --- Installed versions ---
"%VENV_DIR%\Scripts\python.exe" -c "import yt_dlp, fastapi, shutil; print(f'  yt-dlp : {yt_dlp.version.__version__}'); print(f'  FastAPI: {fastapi.__version__}'); print(f'  ffmpeg : {shutil.which(\"ffmpeg\") or \"NOT FOUND\"}')"

echo.
echo =========================================
echo   Install complete
echo =========================================
echo.
echo 1. Start the backend:
echo      %PROJECT_DIR%\start.bat
echo.
echo 2. Load the Chrome extension:
echo      Open chrome://extensions
echo      Enable Developer Mode
echo      Click "Load unpacked"
echo      Select: %PROJECT_DIR%\extension
echo.
echo 3. Open a YouTube video page and click the extension icon,
echo    or use the red button under the video.
echo.
echo See README.md for troubleshooting.
echo.
pause
