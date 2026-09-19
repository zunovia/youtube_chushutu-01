#!/bin/bash
# ============================================================
# YouTube Chushutu - バックエンド起動スクリプト (macOS / Linux)
# どこからでも実行OK
# ============================================================

# プロジェクトルートを特定
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

# 仮想環境が存在するかチェック
if [ ! -f "$VENV_PYTHON" ]; then
    echo "[ERROR] 仮想環境が見つかりません。先にインストーラーを実行してください:"
    echo "  $SCRIPT_DIR/scripts/install.sh"
    exit 1
fi

echo ""
echo "========================================="
echo "  YouTube Chushutu バックエンド"
echo "========================================="
echo ""

# ヘルス情報表示
cd "$BACKEND_DIR"
"$VENV_PYTHON" -c "
import shutil, sys
sys.path.insert(0, '.')
import yt_dlp
from app.config import settings
from app.services.extractor import detect_js_runtime
rt = detect_js_runtime()
print(f'  yt-dlp:  {yt_dlp.version.__version__}')
print('  Deno:    ' + (rt.summary if rt else 'NOT FOUND — YouTubeに必要です。update.sh を実行してください'))
print(f\"  ffmpeg:  {shutil.which('ffmpeg') or 'NOT FOUND — MP3変換と1080p以上は不可'}\")
print(f'  URL:     http://localhost:{settings.port}')
print(f'  API Doc: http://localhost:{settings.port}/docs')
"
echo ""
echo "更新するには（YouTubeの仕様変更・エラー時）: update.sh を実行"
echo "停止するには Ctrl+C を押してください"
echo "========================================="
echo ""

# サーバー起動
"$VENV_PYTHON" "$BACKEND_DIR/run.py"
