#!/bin/bash
# ============================================================
# YouTube Chushutu - 更新スクリプト (macOS / Linux)
# ダブルクリック／実行するだけで、このフォルダを最新版にします。
#   1. GitHub から最新のソースを取得して上書き
#      （仮想環境・backend/.env・ダウンロード済みの動画はそのまま）
#   2. yt-dlp（＋チャレンジ解決スクリプト）を更新し、Deno を導入
#   3. 次にやることを表示
# Windows 版は scripts/update.ps1（update.bat から起動）。
# ============================================================
set -euo pipefail

REPO="zunovia/youtube_chushutu-01"
BRANCH="${YTC_BRANCH:-main}"

# 指定 PID が自分（この update.sh）の先祖か。自分を起動したシェルの
# コマンドラインに run.py が含まれていても、サーバーと誤認しないため。
is_ancestor() {
    local p=$$
    while [ -n "$p" ] && [ "$p" -gt 1 ]; do
        [ "$p" = "$1" ] && return 0
        p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"
    done
    return 1
}

# サーバーが動いているか。run.py は起動時に backend/ へ chdir するので、
# 起動のしかた（start.sh 経由・絶対パス・相対パス）に関係なく cwd で判定できる。
server_running() {
    local venv="$1" backend="$2" pid cwd
    for pid in $(pgrep -f "$venv/bin/python" 2>/dev/null); do
        is_ancestor "$pid" || return 0
    done
    for pid in $(pgrep -f 'python[^ ]* .*run\.py' 2>/dev/null); do
        is_ancestor "$pid" && continue
        if [ -e "/proc/$pid/cwd" ]; then
            cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
        else
            cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
        fi
        [ "$cwd" = "$backend" ] && return 0
    done
    return 1
}

main() {
    local project_dir backend venv py work src d f
    project_dir="$(cd "$(dirname "$0")" && pwd)"
    backend="$project_dir/backend"
    venv="$backend/.venv"
    py="$venv/bin/python"

    if [ ! -f "$backend/pyproject.toml" ]; then
        echo "[ERROR] YouTube Chushutu のフォルダではありません: $project_dir"
        echo "        update.sh は start.sh と同じ場所に置いて実行してください。"
        exit 1
    fi

    echo
    echo "========================================="
    echo "  YouTube Chushutu 更新"
    echo "========================================="
    echo "  フォルダ: $project_dir"

    # pip は使用中のファイルを置き換えられないので、サーバー起動中は止める。
    if server_running "$venv" "$(cd "$backend" && pwd -P)"; then
        echo
        echo "[ERROR] サーバーが起動中です。start.sh を Ctrl+C で止めてから、もう一度実行してください。"
        exit 1
    fi

    work="$(mktemp -d)"
    # Expand now: the trap fires after main() returns, when the local is gone.
    # shellcheck disable=SC2064
    trap "rm -rf '$work' 2>/dev/null || true" EXIT

    echo
    echo "==> 最新版をダウンロード中 ($BRANCH)"
    if ! curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.zip" -o "$work/src.zip"; then
        echo "[ERROR] ダウンロードに失敗しました。ネットワーク接続を確認してください。"
        exit 1
    fi
    if command -v unzip >/dev/null 2>&1; then
        unzip -q "$work/src.zip" -d "$work"
    else
        python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$work/src.zip" "$work"
    fi
    src="$(find "$work" -mindepth 1 -maxdepth 1 -type d ! -name __MACOSX | head -1)"
    [ -n "$src" ] || { echo "[ERROR] ダウンロードしたアーカイブが空でした。"; exit 1; }
    echo "[OK] ダウンロード完了"

    echo
    echo "==> プログラムファイルを更新中（設定とダウンロード済みの動画はそのまま）"
    # プログラムだけのフォルダは丸ごと入れ替える。古いファイルが残ると壊れ方が分かりにくい。
    for d in backend/app backend/tests extension scripts; do
        [ -d "$src/$d" ] || continue
        rm -rf "${project_dir:?}/$d"
        cp -R "$src/$d" "$project_dir/$d"
    done
    for f in start.bat start.sh update.bat update.sh README.md .gitattributes .gitignore backend/run.py backend/pyproject.toml; do
        [ -f "$src/$f" ] && cp -f "$src/$f" "$project_dir/$f"
    done
    chmod +x "$project_dir"/*.sh "$project_dir"/scripts/*.sh 2>/dev/null || true
    echo "[OK] ファイルを更新しました"

    # 仮想環境は「作成時のPython」を指しているだけなので、そのPythonが消えると
    # ファイルはあるのに起動できなくなる。存在ではなく実行して確かめる。
    if [ ! -x "$py" ] || ! "$py" -c 'import sys' >/dev/null 2>&1; then
        echo
        if [ -d "$venv" ]; then
            echo "[WARN] 仮想環境が起動できません（作成時のPythonが削除された可能性）。作り直します。"
            rm -rf "$venv"
        fi
        echo "==> 仮想環境を作成します"
        python3 -m venv "$venv"
    fi

    echo
    echo "==> yt-dlp を更新し、Deno を導入中（数分かかります。Deno は約40MB）"
    "$py" -m pip install --upgrade pip -q --disable-pip-version-check
    "$py" -m pip install --upgrade -e "$backend" -q --disable-pip-version-check
    # [default] にはチャレンジ解決スクリプト (yt-dlp-ejs) が含まれる。素の yt-dlp だけ上げると取り残される。
    "$py" -m pip install --upgrade "yt-dlp[default]" -q --disable-pip-version-check
    # 64bit 以外にはホイールが無いので、失敗しても続行する。
    if ! "$py" -m pip install --upgrade deno -q --disable-pip-version-check; then
        echo "[WARN] Deno を導入できませんでした。Node.js 22 以上をインストールしても代わりに使えます。"
    fi
    echo "[OK] パッケージを更新しました"

    echo
    echo "--- インストール済みバージョン ---"
    (cd "$backend" && "$py" -c "
import shutil, sys
sys.path.insert(0, '.')
import yt_dlp
from app.services.extractor import detect_js_runtime
rt = detect_js_runtime()
print(f'  yt-dlp : {yt_dlp.version.__version__}')
print('  Deno   : ' + (rt.summary if rt else '未導入 — YouTube のダウンロードが失敗します'))
print('  ffmpeg : ' + (shutil.which('ffmpeg') or '未インストール — MP3変換と1080p以上は不可'))
") || echo "[WARN] バージョン表示に失敗しました（更新自体は完了しています）"

    echo
    echo "========================================="
    echo "  更新完了"
    echo "========================================="
    echo
    echo "次にやること:"
    echo "  1. サーバーを起動:  $project_dir/start.sh"
    echo "  2. Chrome拡張を再読み込み: chrome://extensions を開き、"
    echo "     「YouTube Chushutu」のカードにある更新ボタン（丸い矢印）をクリック"
    echo "  3. YouTube のページで再読み込み（F5 / Cmd+R）"
    echo
}

# 自分自身を上書きするため、bash がファイルを読み進める前に本体を関数として
# 読み切っておき、呼び出しの直後に exit する。
main "$@"; exit
