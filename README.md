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
                                            Deno     ← YouTubeの署名チャレンジを解く
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
| **Deno** | 必須（**自動で入ります**） | YouTubeの再生チャレンジを解くJavaScript実行環境 |
| **ffmpeg** | ほぼ必須 | MP3変換、1080p以上の保存 |

> **Denoについて（v2.1で追加）**
> 2025年末からYouTubeは、動画URLを得るのにJavaScriptの計算問題を解くことを要求しています。
> yt-dlpはそれをDenoで解きます。**Denoが無いと、yt-dlpが最新でもダウンロードは失敗します（403）。**
> インストーラーと更新スクリプトが仮想環境の中に自動で入れるので、別途インストールは不要です。
>
> **ffmpegについて**
> YouTubeの高画質動画は「映像」と「音声」が別々に配信されるため、結合にffmpegが必要です。
> ffmpegが無くても720p程度までは保存できますが、**MP3変換と高画質保存はできません。**

---

## インストール（2段階あります）

> **ステップ1（バックエンドの導入）とステップ2（Chrome拡張の読み込み）の両方が必要です。**
> どちらか片方だけでは動きません。特に、サーバーを起動しただけでは
> **YouTubeの画面にボタンは出ません。**

### ステップ1: バックエンドの導入

#### 方法A: ZIPをダウンロード（gitが不要・おすすめ）

1. **[最新版をダウンロード](https://github.com/zunovia/youtube_chushutu-01/archive/refs/heads/main.zip)**
2. 展開する（`C:\YouTubeChushutu` など、日本語やスペースを含まない場所を推奨）
3. **Windows**: `scripts\install.bat` をダブルクリック
   **macOS / Linux**: `./scripts/install.sh`

#### 方法B: git clone（更新が `git pull` だけで済む）

```bash
git clone https://github.com/zunovia/youtube_chushutu-01.git
cd youtube_chushutu-01
./scripts/install.sh          # Windows は scripts\install.bat
```

インストーラーは仮想環境の作成と依存パッケージの導入をまとめて行い、
**ffmpegが無ければ `winget` での自動インストールも提案します。**

> 導入後の更新は、ZIP・git どちらの場合も同梱の **`update.bat`**（`update.sh`）で完結します
> （「更新方法」の節を参照）。ZIPを取り直す必要はありません。

### ステップ2: Chrome拡張の読み込み

ステップ1とは**別の作業**です。これをやらないと、サーバーが動いていても
YouTubeの画面には何も表示されません。

1. Chromeのアドレス欄に `chrome://extensions` と入力して開く
2. **右上の「デベロッパー モード」をON**（ONにしないと次のボタンが出ません）
3. 左上に現れる **「パッケージ化されていない拡張機能を読み込む」** をクリック
4. `start.bat` と同じ場所にある **`extension` フォルダ**を選択
   （フォルダを**開かずに**、選択した状態で「フォルダーの選択」を押します）
5. 一覧に「YouTube Chushutu」が表示されれば完了
6. YouTubeの動画ページを開き、**F5で再読み込み**

> 手順4で選ぶのは `manifest.json` ではなく **`extension` フォルダそのもの**です。
> フォルダの正確なパスは `start.bat` の起動画面にも表示されます。
> 手順6の再読み込みは必須です。すでに開いていたタブには拡張が入っていません。
> 拡張はGoogleアカウント同期の対象外なので、PCごとにこの手順が必要です。

---

## 使い方

> 前提: **インストールのステップ1・ステップ2の両方**が完了していること。
> ボタンが出ない場合は、まずステップ2（Chrome拡張の読み込み）を確認してください。

1. バックエンドを起動 — **Windows**: `start.bat` / **macOS・Linux**: `./start.sh`
2. YouTubeの動画ページを開く
3. ツールバーの拡張アイコン、または動画下の赤い「↓ 保存」ボタンをクリック
4. 画質・形式を選んでダウンロード

保存先は既定で `~/Downloads/YouTubeChushutu` です（診断画面で確認できます）。

**普段使うときは `start.bat` だけでOK** です。インストールは最初の1回だけです。
動かなくなったら、同じフォルダの **`update.bat`** をダブルクリックしてください（次の節）。

---

## 更新方法（YouTubeの仕様が変わったとき）

久しぶりに使って動かなくなった場合、原因はほぼ **yt-dlpが古い** か **Denoが未導入** のどちらかです。
どちらも同じ操作で直ります。

### いちばん簡単な方法: `update.bat` をダブルクリック

`start.bat` と同じフォルダにある **`update.bat`**（macOS / Linux は `update.sh`）を実行します。
次のことを全部やります：

1. GitHubから最新版を取得し、プログラムを上書き（**仮想環境・設定・ダウンロード済みの動画はそのまま**）
2. yt-dlpとチャレンジ解決スクリプトを最新にし、Denoを導入
3. 導入されたバージョンを表示

終わったら **① `start.bat` を起動** し、**② `chrome://extensions` で「YouTube Chushutu」の
更新ボタン（丸い矢印）を押して** から、YouTubeのページを再読み込みしてください。
②は拡張機能側のファイルも更新されるため必要です。

> **`update.bat` がまだ無い（v2.0.0 のまま）PCの場合**
> こちらからダウンロードして `start.bat` と同じフォルダに置き、ダブルクリックしてください：
> <https://github.com/zunovia/youtube_chushutu-01/blob/main/update.bat>
> （右上のダウンロードボタン ⤓ で保存。Chromeが警告を出したら「保存」を選ぶ）
> 以後はそのファイルを押すだけで最新になります。

> サーバー（`start.bat` の黒い画面）が開いたままだと、更新は安全のため中止されます。先に閉じてください。

### ポップアップからの更新

- ポップアップに **「yt-dlpの更新があります」** または **「Denoが未導入です」** と出たら
  **「更新する」をクリック → サーバーを再起動**
- yt-dlp・解決スクリプト・Denoがまとめて更新されます。拡張機能自体は更新されないので、
  それでも直らないときは `update.bat` を使ってください。

拡張は起動時に自動で更新の有無を確認します（結果は24時間キャッシュされ、オフラインでも問題ありません）。

---

## トラブルシューティング

まず **ポップアップ右上の「診断」** を開いてください。
yt-dlpのバージョン、Denoとffmpegの有無、保存先、直近のエラーがまとめて確認できます。

| 表示されるエラー | 原因と対処 |
|---|---|
| **ffmpegがインストールされていません** | 最も多い原因です。PowerShellで `winget install --id Gyan.FFmpeg -e` を実行し、PowerShellを開き直してからサーバーを再起動してください。急ぐ場合は音声形式をM4Aにすると変換なしで保存できます。 |
| **YouTubeの新しい仕様に対応するための部品（Deno）が入っていません** | v2.1で最も多い原因です。「更新する」を押す（またはフォルダの `update.bat`）→ サーバー再起動。診断画面の「Deno(JS実行)」行で導入済みか確認できます。 |
| **YouTubeにアクセスを拒否されました（403）** | yt-dlpが古いか、Denoが無いときに起きます。「更新する」→ サーバー再起動。 |
| **YouTubeの仕様変更に追随できていません** | 同上。更新してください。 |
| **botと判定されました** | ChromeのCookieで自動的に再試行しますが、それでも駄目な場合はChromeでYouTubeにログインしてください。 |
| **年齢制限つきの動画です** | ChromeでYouTubeにログインした状態にしてください。 |
| **ブラウザのCookieを読み取れませんでした** | Chromeを完全に終了してから再試行してください。Chrome以外を使っている場合は `YTC_COOKIE_BROWSER=firefox` のように指定します。 |
| **バックエンドに接続できません** | `start.bat` を実行してサーバーを起動してください。ポート9160が他のソフトと衝突している場合は、`YTC_PORT` でサーバー側を変更し、**同じ番号を拡張機能の「診断」画面のポート欄にも入力**してください（両方を合わせる必要があります）。 |
| **選択した画質が取得できませんでした** | 画質を「自動（最高画質）」にしてやり直してください。 |
| 動画下にボタンが出ない | **まずChromeツールバーに拡張アイコンがあるか確認してください。**無ければ拡張が読み込まれていません（インストールのステップ2）。アイコンがあるのにボタンだけ出ない場合は、ページをF5で再読み込み。それでも出ないときはYouTube側のレイアウト変更の可能性があり、ツールバーの拡張アイコンからは引き続き使えます。 |

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

指定できる値: `BOT_CHECK` `OUTDATED_YTDLP` `JS_RUNTIME_MISSING` `HTTP_FORBIDDEN` `FFMPEG_MISSING`
`AGE_RESTRICTED` `PRIVATE_VIDEO` `UNAVAILABLE` `GEO_BLOCKED` `LIVE_NOT_ENDED`
`FORMAT_UNAVAILABLE` `COOKIE_LOCKED` `NETWORK` `DISK_ERROR`

---

## 開発者向けメモ

```
backend/app/
  services/errors.py     エラー分類（正規表現 → 日本語メッセージ＋対処法）
  services/extractor.py  yt-dlpに触れる唯一のファイル。再試行の連鎖、Deno検出もここ
  services/updater.py    バージョン確認とpipによる更新（yt-dlp[default] + deno）
  services/downloader.py バックグラウンドDLとタスク管理
  routers/video.py       REST API
extension/
  popup/                 ツールバーのUI
  content/               YouTubeページ内のボタン
  lib/api-client.js      ポップアップとページ内ボタンで共有
scripts/update.ps1       update.bat の本体（最新版の取得・上書き・pip更新）
update.sh                同・macOS / Linux 版
```

**Denoについて**
yt-dlpは仮想環境の `Scripts`（`bin`）フォルダを最初に探すので、`pip install deno` だけで
PATH設定なしに見つかります。`pyproject.toml` には意図的に入れていません（64bit以外に
ホイールが無く、pipの依存解決ごと失敗するため）。スクリプトと更新ボタンがベストエフォートで入れます。

**テストの実行**

```bash
backend/.venv/bin/python -m pip install -e backend[dev]   # pytest を追加
backend/.venv/bin/python -m pytest backend/tests -q
```

**設計上の約束ごと**

- yt-dlpの型・例外・オプションは `extractor.py` の外に出さない。仕様変更の影響をこの1ファイルに閉じ込めるため。
- 日本語の文言はバックエンド側（`errors.py`）に集約する。拡張は受け取って表示するだけ。
- `.bat` は全行ASCII。`update.bat` はさらに複数行ブロックと `goto` を使わない
  （単体でダウンロードされるとLF改行になり、CMDが誤読するため）。
- **セクション切り替えはバナー（エラー・警告）を消してはいけない。** v1ではエラー表示直後に消していたため、失敗が一切見えなかった。

個人利用を想定しています。ダウンロードした動画の取り扱いは、各自の責任と利用規約の範囲で行ってください。
