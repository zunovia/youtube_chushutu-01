#!/bin/bash
# YouTube Chushutu - セットアップスクリプト
set -e

echo "=== YouTube Chushutu セットアップ ==="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 が見つかりません。インストールしてください。"
    exit 1
fi
echo "[OK] Python 3: $(python3 --version)"

# Check ffmpeg
if command -v ffmpeg &> /dev/null; then
    echo "[OK] ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "[WARN] ffmpegが見つかりません。音声抽出にはffmpegが必要です。"
    echo "  インストール方法:"
    echo "    Ubuntu/Debian: sudo apt install ffmpeg"
    echo "    macOS:         brew install ffmpeg"
    echo "    Windows:       https://ffmpeg.org/download.html"
fi

# Install Python dependencies
echo ""
echo "Pythonパッケージをインストール中..."
cd "$(dirname "$0")/../backend"
pip install -e .

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "使い方:"
echo "  1. バックエンド起動: cd backend && python run.py"
echo "  2. Chrome拡張を読み込み:"
echo "     chrome://extensions → デベロッパーモード → 「パッケージ化されていない拡張機能を読み込む」"
echo "     → extension/ フォルダを選択"
echo "  3. YouTubeの動画ページで拡張アイコンをクリック"
