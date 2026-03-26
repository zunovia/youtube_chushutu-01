#!/bin/bash
# ============================================================
# yt-dlp 更新スクリプト (macOS / Linux)
# YouTubeの仕様変更時にこれを実行するだけでOK
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PIP="$(cd "$SCRIPT_DIR/../backend" && pwd)/.venv/bin/pip"
VENV_PYTHON="$(cd "$SCRIPT_DIR/../backend" && pwd)/.venv/bin/python"

if [ ! -f "$VENV_PIP" ]; then
    echo "[ERROR] 仮想環境が見つかりません。先にインストーラーを実行してください。"
    exit 1
fi

echo ""
echo "=== yt-dlp 更新 ==="
echo ""

echo "現在のバージョン:"
"$VENV_PYTHON" -c "import yt_dlp; print(f'  {yt_dlp.version.__version__}')" 2>/dev/null || echo "  (未インストール)"

echo ""
echo "最新版にアップデート中..."
"$VENV_PIP" install --upgrade yt-dlp -q

echo ""
echo "更新後のバージョン:"
"$VENV_PYTHON" -c "import yt_dlp; print(f'  {yt_dlp.version.__version__}')"

echo ""
echo "完了! バックエンドサーバーを再起動してください。"
echo ""
