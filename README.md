# YouTube Chushutu

YouTube動画のダウンロードと音声抽出を行う、個人利用向けのChrome拡張です。

- 画質を選んで動画をダウンロード
- 音声だけをMP3 / M4Aで抽出
- ツールバーのポップアップと、YouTube動画ページ内のボタンの両方から操作可能
- **失敗したときに、原因と対処法が日本語で表示されます**

---

## 構成

Chrome拡張だけでは、映像と音声の結合やMP3変換ができません（ブラウザ内では実行不可能）。
そのため、PC上で動く小さなバックエンドと組み合わせて動作します。

```
Chrome拡張 (MV3)  ←→  localhost:9160  ←→  Pythonバックエンド
  ポップアップUI                            FastAPI
  ページ内ボタン                            yt-dlp   ← 抽出エンジン
                                            ffmpeg   ← 結合・変換
```

YouTubeは頻繁に仕様を変えます。それに追随しているのが **yt-dlp** で、
yt-dlpに触れるのは `backend/app/services/extractor.py` 1ファイルだけです。
仕様変更のほとんどは **yt-dlpを更新するだけ** で直ります。

---

## 必要なもの

| | 必須 | 用途 |
|---|---|---|
| Python 3.10以上 | 必須 | バックエンド |
| Google Chrome | 必須 | 拡張機能 |
| **ffmpeg** | ほぼ必須 | MP3変換、1080p以上の保存 |

> **ffmpegについて**
> YouTubeの高画質動画は「映像」と「音声」が別々に配信されるため、結合にffmpegが必要です。
> ffmpegが無くても720p程度までは保存できますが、**MP3変換と高画質保存はできません。**

---

## インストール

### 方法A: ZIPをダウンロード（gitが不要・おすすめ）

1. **[youtube_chushutu-01-v2.0.0.zip をダウンロード](https://github.com/zunovia/youtube_chushutu-01/archive/refs/tags/v2.0.0.zip)**
2. 展開する（`C:\YouTubeChushutu` など、日本語やスペースを含まない場所を推奨）
3. **Windows**: `scripts\install.bat` をダブルクリック
   **macOS / Linux**: `./scripts/install.sh`

常に最新版が欲しい場合はこちら:
<https://github.com/zunovia/youtube_chushutu-01/archive/refs/heads/main.zip>

### 方法B: git clone（更新が `git pull` だけで済む）

```bash
git clone https://github.com/zunovia/youtube_chushutu-01.git
cd youtube_chushutu-01
./scripts/install.sh          # Windows は scripts\install.bat
```

---

インストーラーは仮想環境の作成と依存パッケージの導入をまとめて行い、
**ffmpegが無ければ `winget` での自動インストールも提案します。**

> ZIPで導入した場合は `.git` が無いため、**本体の更新は再ダウンロード**になります。
> ただしYouTubeの仕様変更に対応するyt-dlpの更新はアプリ内のボタンで完結するので、
> 通常の運用で困ることはありません。

### Chrome拡張の読み込み

1. Chromeで `chrome://extensions` を開く
2. 右上の「デベロッパーモード」をON
3. 「パッケージ化されていない拡張機能を読み込む」をクリック
4. `extension` フォルダを選択

> 拡張はGoogleアカウント同期の対象外です。PCごとにこの手順が必要です。

---

## 使い方

1. バックエンドを起動 — **Windows**: `start.bat` / **macOS・Linux**: `./start.sh`
2. YouTubeの動画ページを開く
3. ツールバーの拡張アイコン、または動画下の赤い「↓ 保存」ボタンをクリック
4. 画質・形式を選んでダウンロード

保存先は既定で `~/Downloads/YouTubeChushutu` です（診断画面で確認できます）。

**普段使うときは `start.bat` だけでOK** です。インストールは最初の1回だけです。

---

## 更新方法（YouTubeの仕様が変わったとき）

久しぶりに使って動かなくなった場合、ほとんどはyt-dlpが古いことが原因です。

- **ポップアップに「yt-dlpの更新があります」と出たら「更新する」をクリック** → サーバーを再起動
- または `scripts/update-ytdlp.bat`（Windows）/ `scripts/update-ytdlp.sh` を実行

拡張は起動時に自動で更新の有無を確認します（結果は24時間キャッシュされ、オフラインでも問題ありません）。

---

## トラブルシューティング

まず **ポップアップ右上の「診断」** を開いてください。
yt-dlpのバージョン、ffmpegの有無、保存先、直近のエラーがまとめて確認できます。

| 表示されるエラー | 原因と対処 |
|---|---|
| **ffmpegがインストールされていません** | 最も多い原因です。PowerShellで `winget install --id Gyan.FFmpeg -e` を実行し、PowerShellを開き直してからサーバーを再起動してください。急ぐ場合は音声形式をM4Aにすると変換なしで保存できます。 |
| **YouTubeにアクセスを拒否されました（403）** | yt-dlpが古いときに起きます。「yt-dlpを更新」→ サーバー再起動。 |
| **YouTubeの仕様変更に追随できていません** | 同上。yt-dlpを更新してください。 |
| **botと判定されました** | ChromeのCookieで自動的に再試行しますが、それでも駄目な場合はChromeでYouTubeにログインしてください。 |
| **年齢制限つきの動画です** | ChromeでYouTubeにログインした状態にしてください。 |
| **ブラウザのCookieを読み取れませんでした** | Chromeを完全に終了してから再試行してください。Chrome以外を使っている場合は `YTC_COOKIE_BROWSER=firefox` のように指定します。 |
| **バックエンドに接続できません** | `start.bat` を実行してサーバーを起動してください。ポート9160が他のソフトと衝突している場合は、`YTC_PORT` でサーバー側を変更し、**同じ番号を拡張機能の「診断」画面のポート欄にも入力**してください（両方を合わせる必要があります）。 |
| **選択した画質が取得できませんでした** | 画質を「自動（最高画質）」にしてやり直してください。 |
| 動画下にボタンが出ない | YouTube側のレイアウト変更の可能性があります。ツールバーの拡張アイコンからは引き続き使えます。 |

---

## 設定

`backend/.env` または環境変数（`YTC_` 接頭辞）で変更できます。

| 変数 | 既定値 | 説明 |
|---|---|---|
| `YTC_PORT` | `9160` | バックエンドのポート（拡張機能の「診断」画面でも同じ値に設定すること） |
| `YTC_DOWNLOAD_DIR` | `~/Downloads/YouTubeChushutu` | 保存先 |
| `YTC_COOKIE_BROWSER` | `chrome` | Cookieの取得元ブラウザ |
| `YTC_COOKIES_FILE` | （空） | cookies.txt を使う場合のパス |
| `YTC_PLAYER_CLIENTS` | `["tv","web_safari","mweb"]` | 再試行時に切り替えるクライアント（JSON形式） |
| `YTC_FFMPEG_LOCATION` | （空） | ffmpegがPATHに無い場合の場所 |
| `YTC_MAX_CONCURRENT_DOWNLOADS` | `3` | 同時ダウンロード数 |

Cookieはこのbot判定対策のためだけにローカルで読み込まれ、外部には一切送信されません。

### 動作確認用

エラー表示を実際に壊さずに確認したいときに使います。

```bash
YTC_SIMULATE_ERROR=BOT_CHECK ./start.sh    # 必ずbot判定エラーになる
YTC_SIMULATE_FAIL_ATTEMPTS=2 ./start.sh    # 2回失敗してから成功する
```

指定できる値: `BOT_CHECK` `OUTDATED_YTDLP` `HTTP_FORBIDDEN` `FFMPEG_MISSING`
`AGE_RESTRICTED` `PRIVATE_VIDEO` `UNAVAILABLE` `GEO_BLOCKED` `LIVE_NOT_ENDED`
`FORMAT_UNAVAILABLE` `COOKIE_LOCKED` `NETWORK` `DISK_ERROR`

---

## 開発者向けメモ

```
backend/app/
  services/errors.py     エラー分類（正規表現 → 日本語メッセージ＋対処法）
  services/extractor.py  yt-dlpに触れる唯一のファイル。再試行の連鎖もここ
  services/updater.py    バージョン確認とpipによる更新
  services/downloader.py バックグラウンドDLとタスク管理
  routers/video.py       REST API
extension/
  popup/                 ツールバーのUI
  content/               YouTubeページ内のボタン
  lib/api-client.js      ポップアップとページ内ボタンで共有
```

**テストの実行**

```bash
backend/.venv/bin/python -m pip install -e backend[dev]   # pytest を追加
backend/.venv/bin/python -m pytest backend/tests -q
```

**設計上の約束ごと**

- yt-dlpの型・例外・オプションは `extractor.py` の外に出さない。仕様変更の影響をこの1ファイルに閉じ込めるため。
- 日本語の文言はバックエンド側（`errors.py`）に集約する。拡張は受け取って表示するだけ。
- **セクション切り替えはバナー（エラー・警告）を消してはいけない。** v1ではエラー表示直後に消していたため、失敗が一切見えなかった。

個人利用を想定しています。ダウンロードした動画の取り扱いは、各自の責任と利用規約の範囲で行ってください。
