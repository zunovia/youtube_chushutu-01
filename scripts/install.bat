@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM YouTube Chushutu - インストーラー (Windows)
REM ダブルクリックで実行OK。仮想環境を自動作成します。
REM ============================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "BACKEND_DIR=%PROJECT_DIR%\backend"
set "VENV_DIR=%BACKEND_DIR%\.venv"

echo.
echo =========================================
echo   YouTube Chushutu インストーラー
echo =========================================
echo.

REM --- Python チェック ---
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Pythonが見つかりません。
    echo.
    echo   https://www.python.org/downloads/ からインストールしてください。
    echo   インストール時に「Add Python to PATH」にチェックを入れてください。
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [OK] %PYTHON_VER%

REM --- ffmpeg チェック ---
where ffmpeg >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] ffmpeg が見つかりました
) else (
    echo [WARN] ffmpegが見つかりません。音声変換(MP3等)にはffmpegが必要です。
    echo.
    echo   インストール方法:
    echo     1. https://www.gyan.dev/ffmpeg/builds/ から「ffmpeg-release-essentials.zip」をダウンロード
    echo     2. 解凍して bin フォルダ内の ffmpeg.exe のパスを環境変数PATHに追加
    echo.
    echo   ffmpegなしでも動画ダウンロードは可能です。後からインストールできます。
    echo.
)

REM --- 仮想環境の作成 ---
echo.
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo [OK] 仮想環境は既に存在します
) else (
    echo 仮想環境を作成中...
    python -m venv "%VENV_DIR%"
    echo [OK] 仮想環境を作成しました
)

REM --- パッケージインストール ---
echo パッケージをインストール中...
"%VENV_DIR%\Scripts\pip.exe" install --upgrade pip -q
"%VENV_DIR%\Scripts\pip.exe" install -e "%BACKEND_DIR%" -q
echo [OK] パッケージのインストール完了

REM --- バージョン確認 ---
echo.
echo --- インストール済みバージョン ---
"%VENV_DIR%\Scripts\python.exe" -c "import yt_dlp, fastapi, pydantic; print(f'  yt-dlp:   {yt_dlp.version.__version__}'); print(f'  FastAPI:  {fastapi.__version__}'); print(f'  Pydantic: {pydantic.__version__}')"

REM --- 完了メッセージ ---
echo.
echo =========================================
echo   インストール完了!
echo =========================================
echo.
echo 【バックエンド起動方法】
echo   %PROJECT_DIR%\start.bat をダブルクリック
echo.
echo 【Chrome拡張の読み込み方法】
echo   1. Chromeで chrome://extensions を開く
echo   2. 「デベロッパーモード」をONにする
echo   3. 「パッケージ化されていない拡張機能を読み込む」をクリック
echo   4. 次のフォルダを選択: %PROJECT_DIR%\extension
echo.
echo 【yt-dlp更新方法】(YouTubeの仕様変更時)
echo   %PROJECT_DIR%\scripts\update-ytdlp.bat をダブルクリック
echo.
pause
