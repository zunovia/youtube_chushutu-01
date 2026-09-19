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
# [default] にはチャレンジ解決スクリプト (yt-dlp-ejs) が含まれる。
"$VENV_PIP" install --upgrade "yt-dlp[default]" -q
# それを動かすJSランタイム。64bit以外には無いので失敗しても続行。
"$VENV_PIP" install --upgrade deno -q || echo "[WARN] Denoを導入できませんでした（Node.js 22以上でも代用可）"

echo ""
echo "更新後のバージョン:"
"$VENV_PYTHON" -c "import yt_dlp; print(f'  {yt_dlp.version.__version__}')"

echo ""
echo "完了! バックエンドサーバーを再起動してください。"
echo "（拡張機能も含めた全体の更新は update.sh を使ってください）"
echo ""
