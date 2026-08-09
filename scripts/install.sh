#!/bin/bash
# ============================================================
# YouTube Chushutu - インストーラー (macOS / Linux)
# どこから実行してもOK。仮想環境を自動作成します。
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

echo
echo "========================================="
echo "  YouTube Chushutu インストーラー"
echo "========================================="
echo
echo "プロジェクト: $PROJECT_DIR"
echo

# --- Python ---
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] Python 3.10以上が必要です。"
    echo "    Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "    macOS:         brew install python3"
    exit 1
fi
echo "[OK] Python: $($PYTHON_CMD --version)"

# --- ffmpeg ---
# ffmpegが無いとMP3変換と1080p以上の保存ができないため、ここで強めに案内する。
if command -v ffmpeg &>/dev/null; then
    echo "[OK] ffmpeg: $(ffmpeg -version 2>&1 | head -1 | cut -c1-60)"
else
    echo "[WARN] ffmpegが見つかりません。"
    echo "       MP3変換と1080p以上の保存に必要です（無くても720p程度までは保存可）。"
    echo "         Ubuntu/Debian: sudo apt install ffmpeg"
    echo "         macOS:         brew install ffmpeg"
fi

# --- venv ---
echo
if [ -x "$VENV_DIR/bin/python" ]; then
    echo "[OK] 仮想環境は既にあります"
else
    echo "仮想環境を作成中..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo "[OK] 仮想環境を作成しました"
fi

echo "パッケージをインストール中..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip -q
"$VENV_DIR/bin/python" -m pip install -e "$BACKEND_DIR" -q
echo "[OK] インストール完了"

echo
echo "--- インストール済みバージョン ---"
"$VENV_DIR/bin/python" -c "
import shutil, fastapi, yt_dlp
print(f'  yt-dlp : {yt_dlp.version.__version__}')
print(f'  FastAPI: {fastapi.__version__}')
print(f'  ffmpeg : {shutil.which(\"ffmpeg\") or \"未インストール\"}')
"

echo
echo "========================================="
echo "  セットアップ完了"
echo "========================================="
echo
echo "1. バックエンドを起動:"
echo "     $PROJECT_DIR/start.sh"
echo
echo "2. Chrome拡張を読み込み:"
echo "     chrome://extensions を開く → デベロッパーモードON"
echo "     → 「パッケージ化されていない拡張機能を読み込む」"
echo "     → $PROJECT_DIR/extension を選択"
echo
echo "3. YouTubeの動画ページで拡張アイコン、または動画下の赤いボタンをクリック"
echo
echo "困ったときは README.md を参照してください。"
echo
