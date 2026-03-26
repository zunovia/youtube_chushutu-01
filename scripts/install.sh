#!/bin/bash
# ============================================================
# YouTube Chushutu - インストーラー (macOS / Linux)
# どこからでも実行OK。仮想環境を自動作成します。
# ============================================================
set -e

# このスクリプトのあるディレクトリを基準にプロジェクトルートを特定
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

echo ""
echo "========================================="
echo "  YouTube Chushutu インストーラー"
echo "========================================="
echo ""
echo "プロジェクト: $PROJECT_DIR"
echo ""

# --- Python チェック ---
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &> /dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] Python 3.10以上が必要です。"
    echo ""
    echo "  インストール方法:"
    echo "    Ubuntu/Debian: sudo apt install python3"
    echo "    macOS:         brew install python3"
    echo "    https://www.python.org/downloads/"
    exit 1
fi
echo "[OK] Python: $($PYTHON_CMD --version)"

# --- ffmpeg チェック ---
if command -v ffmpeg &> /dev/null; then
    echo "[OK] ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "[WARN] ffmpegが見つかりません。音声変換(MP3等)にはffmpegが必要です。"
    echo ""
    echo "  インストール方法:"
    echo "    Ubuntu/Debian: sudo apt install ffmpeg"
    echo "    macOS:         brew install ffmpeg"
    echo ""
    echo "  ffmpegなしでも動画ダウンロードは可能です。後からインストールできます。"
    echo ""
fi

# --- 仮想環境の作成 ---
echo ""
if [ -d "$VENV_DIR" ]; then
    echo "[OK] 仮想環境は既に存在します: $VENV_DIR"
else
    echo "仮想環境を作成中..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo "[OK] 仮想環境を作成しました"
fi

# --- 仮想環境を有効化してパッケージインストール ---
echo "パッケージをインストール中..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -e "$BACKEND_DIR" -q
echo "[OK] パッケージのインストール完了"

# --- バージョン確認 ---
echo ""
echo "--- インストール済みバージョン ---"
"$VENV_DIR/bin/python" -c "
import yt_dlp, fastapi, pydantic
print(f'  yt-dlp:   {yt_dlp.version.__version__}')
print(f'  FastAPI:  {fastapi.__version__}')
print(f'  Pydantic: {pydantic.__version__}')
"

# --- 完了メッセージ ---
echo ""
echo "========================================="
echo "  インストール完了!"
echo "========================================="
echo ""
echo "【バックエンド起動方法】"
echo "  $PROJECT_DIR/start.sh"
echo ""
echo "【Chrome拡張の読み込み方法】"
echo "  1. Chromeで chrome://extensions を開く"
echo "  2. 「デベロッパーモード」をONにする"
echo "  3. 「パッケージ化されていない拡張機能を読み込む」をクリック"
echo "  4. 次のフォルダを選択: $PROJECT_DIR/extension"
echo ""
echo "【yt-dlp更新方法】(YouTubeの仕様変更時)"
echo "  $PROJECT_DIR/scripts/update-ytdlp.sh"
echo ""
