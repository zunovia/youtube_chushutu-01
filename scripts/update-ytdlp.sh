#!/bin/bash
# yt-dlp を最新版に更新するスクリプト
# YouTubeの仕様変更対応はこれだけでOK
set -e

echo "=== yt-dlp 更新 ==="

echo "現在のバージョン:"
python3 -c "import yt_dlp; print(f'  {yt_dlp.version.__version__}')" 2>/dev/null || echo "  (未インストール)"

echo ""
echo "最新版にアップデート中..."
pip install --upgrade yt-dlp

echo ""
echo "更新後のバージョン:"
python3 -c "import yt_dlp; print(f'  {yt_dlp.version.__version__}')"

echo ""
echo "完了! バックエンドサーバーを再起動してください。"
