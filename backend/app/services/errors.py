"""
Error taxonomy.

Turns raw yt-dlp error text into an actionable Japanese message plus a remedy.
This is what makes a failure self-explanatory instead of a dead end: every
error the user can see carries both "what happened" and "what to do about it".

Also keeps a small ring buffer of recent failures for the /api/diagnostics
endpoint, so a future breakage can be diagnosed from the UI alone.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    """Stable machine-readable failure reasons shared with the extension."""

    BOT_CHECK = "BOT_CHECK"
    OUTDATED_YTDLP = "OUTDATED_YTDLP"
    HTTP_FORBIDDEN = "HTTP_FORBIDDEN"
    POSTPROCESS_ERROR = "POSTPROCESS_ERROR"
    AGE_RESTRICTED = "AGE_RESTRICTED"
    PRIVATE_VIDEO = "PRIVATE_VIDEO"
    UNAVAILABLE = "UNAVAILABLE"
    GEO_BLOCKED = "GEO_BLOCKED"
    LIVE_NOT_ENDED = "LIVE_NOT_ENDED"
    FFMPEG_MISSING = "FFMPEG_MISSING"
    FORMAT_UNAVAILABLE = "FORMAT_UNAVAILABLE"
    COOKIE_LOCKED = "COOKIE_LOCKED"
    NETWORK = "NETWORK"
    DISK_ERROR = "DISK_ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ClassifiedError:
    """A yt-dlp failure translated for a human."""

    code: ErrorCode
    message: str  # 何が起きたか
    remedy: str  # どうすればいいか
    raw: str  # 元のyt-dlpメッセージ（診断用）
    action: str = ""  # UI が出すボタンの種類（下記 ACTION_* のいずれか）


# Actions the popup can offer alongside an error. Each maps to one button.
ACTION_UPDATE = "update_ytdlp"
ACTION_INSTALL_FFMPEG = "install_ffmpeg"
ACTION_LOGIN = "login_youtube"
ACTION_AUTO_FORMAT = "choose_auto_format"
ACTION_RETRY = "retry"
ACTION_DIAGNOSTICS = "open_diagnostics"


# Codes worth retrying with a different extraction strategy. A private or
# deleted video will fail identically no matter which client we ask with, so
# retrying those only wastes the user's time.
RETRYABLE: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.BOT_CHECK,
        ErrorCode.OUTDATED_YTDLP,
        ErrorCode.HTTP_FORBIDDEN,
        ErrorCode.AGE_RESTRICTED,
        ErrorCode.NETWORK,
        ErrorCode.UNKNOWN,
    }
)


# Order matters: the first match wins, so narrower patterns come first.
# "Sign in to confirm your age" must be read as AGE_RESTRICTED before the
# broader "Sign in to confirm" bot-check pattern can claim it.
_RULES: list[tuple[ErrorCode, re.Pattern[str]]] = [
    # First, because it is both the most specific and the most common cause of a
    # failure that only shows up at download time (info extraction needs no ffmpeg).
    (
        ErrorCode.FFMPEG_MISSING,
        re.compile(
            r"(ffmpeg|ffprobe)(\s+is)?\s+not\s+(installed|found|available)"
            r"|requested merging of multiple formats but ffmpeg"
            r"|ffmpeg is required|postprocessing:.*ffmpeg not",
            re.I,
        ),
    ),
    (
        ErrorCode.AGE_RESTRICTED,
        re.compile(r"confirm your age|age[- ]restricted|inappropriate for some users", re.I),
    ),
    (
        ErrorCode.COOKIE_LOCKED,
        re.compile(
            r"cookie.{0,20}database|could not (find|copy|open|read).{0,30}cookie"
            r"|database is locked|failed to decrypt|permission denied.*cookies"
            r"|no such (browser|profile)|unsupported browser",
            re.I,
        ),
    ),
    (
        ErrorCode.BOT_CHECK,
        re.compile(
            r"not a bot|sign in to confirm|confirm you'?re not|unusual traffic"
            r"|too many requests|http error 429",
            re.I,
        ),
    ),
    (
        ErrorCode.OUTDATED_YTDLP,
        re.compile(
            r"\bnsig\b|signature extraction|failed to extract any player response"
            r"|unable to extract (yt initial data|player version|js player|nsig|signature)"
            r"|only images are available|player response",
            re.I,
        ),
    ),
    (
        ErrorCode.PRIVATE_VIDEO,
        re.compile(r"private video|members[- ]only|join this channel|requires payment", re.I),
    ),
    (
        ErrorCode.GEO_BLOCKED,
        re.compile(r"not available in your country|geo[- ]?restricted|blocked it in your country", re.I),
    ),
    (
        ErrorCode.LIVE_NOT_ENDED,
        re.compile(r"live event will begin|is currently live|premieres in|live stream recording", re.I),
    ),
    (
        ErrorCode.UNAVAILABLE,
        re.compile(
            r"video unavailable|has been removed|been terminated|does not exist"
            r"|this video is unavailable|removed by the uploader",
            re.I,
        ),
    ),
    (
        ErrorCode.HTTP_FORBIDDEN,
        re.compile(r"http error 403|403:? forbidden", re.I),
    ),
    (
        ErrorCode.POSTPROCESS_ERROR,
        re.compile(r"postprocessing:|audio conversion failed|error opening output file", re.I),
    ),
    (
        ErrorCode.FORMAT_UNAVAILABLE,
        re.compile(r"requested format is not available|no video formats found|no such format", re.I),
    ),
    (
        ErrorCode.DISK_ERROR,
        re.compile(
            r"no space left|errno 28|errno 13|read-only file system"
            r"|winerror 5\b|winerror 206|filename too long",
            re.I,
        ),
    ),
    (
        ErrorCode.NETWORK,
        re.compile(
            r"unable to download (webpage|video data)|timed out|timeout"
            r"|connection (reset|refused|aborted|error)|name resolution"
            r"|http error 5\d\d|urlopen error|network is unreachable",
            re.I,
        ),
    ),
]


_MESSAGES: dict[ErrorCode, tuple[str, str, str]] = {
    ErrorCode.FFMPEG_MISSING: (
        "ffmpegがインストールされていません。",
        "高画質の動画は映像と音声が別ファイルで配信されるため、結合にffmpegが必要です。"
        "MP3への変換にも必要です。PowerShellで winget install ffmpeg を実行し、"
        "PowerShellを開き直してからサーバーを再起動してください。",
        ACTION_INSTALL_FFMPEG,
    ),
    ErrorCode.BOT_CHECK: (
        "YouTubeにbot（自動プログラム）と判定されました。",
        "ChromeのCookieを使って自動的に再試行しましたが失敗しました。"
        "ChromeでYouTubeにログインしてから、もう一度お試しください。",
        ACTION_LOGIN,
    ),
    ErrorCode.OUTDATED_YTDLP: (
        "YouTubeの仕様変更に追随できていません（yt-dlpが古い可能性があります）。",
        "「yt-dlpを更新」を押して最新版にしてから、サーバーを再起動してください。",
        ACTION_UPDATE,
    ),
    ErrorCode.HTTP_FORBIDDEN: (
        "YouTubeにアクセスを拒否されました（HTTP 403）。",
        "yt-dlpが古いと発生しやすいエラーです。「yt-dlpを更新」を押して"
        "最新版にしてから、サーバーを再起動してください。",
        ACTION_UPDATE,
    ),
    ErrorCode.POSTPROCESS_ERROR: (
        "ダウンロードは成功しましたが、変換処理に失敗しました。",
        "ffmpegが正しくインストールされているか確認してください。"
        "音声形式をM4Aに変えると変換なしで保存できます。",
        ACTION_INSTALL_FFMPEG,
    ),
    ErrorCode.AGE_RESTRICTED: (
        "年齢制限つきの動画です。",
        "ChromeでYouTubeにログインした状態にしてから、もう一度お試しください。",
        ACTION_LOGIN,
    ),
    ErrorCode.PRIVATE_VIDEO: (
        "非公開またはメンバー限定の動画です。",
        "この動画を視聴できるアカウントでChromeにログインしている必要があります。",
        ACTION_LOGIN,
    ),
    ErrorCode.UNAVAILABLE: (
        "動画が削除されているか、利用できません。",
        "YouTube上でこの動画が再生できるか確認してください。",
        "",
    ),
    ErrorCode.GEO_BLOCKED: (
        "お住まいの地域では視聴できない動画です。",
        "地域制限のため、この動画はダウンロードできません。",
        "",
    ),
    ErrorCode.LIVE_NOT_ENDED: (
        "配信中、または配信予定の動画です。",
        "配信が終了してアーカイブが公開されてから、もう一度お試しください。",
        "",
    ),
    ErrorCode.FORMAT_UNAVAILABLE: (
        "選択した画質が取得できませんでした。",
        "画質を「自動（最高画質）」に変更して、もう一度お試しください。",
        ACTION_AUTO_FORMAT,
    ),
    ErrorCode.COOKIE_LOCKED: (
        "ブラウザのCookieを読み取れませんでした。",
        "Chromeを完全に終了してから、もう一度お試しください"
        "（タスクトレイに常駐している場合はそちらも終了してください）。"
        "Chromeを使っていない場合は、環境変数 YTC_COOKIE_BROWSER で"
        "firefox / edge などを指定してください。",
        ACTION_RETRY,
    ),
    ErrorCode.NETWORK: (
        "通信エラーが発生しました。",
        "ネットワーク接続を確認して、もう一度お試しください。",
        ACTION_RETRY,
    ),
    ErrorCode.DISK_ERROR: (
        "ファイルの保存に失敗しました。",
        "保存先の空き容量と書き込み権限を確認してください。"
        "保存先は「診断情報」で確認できます。",
        ACTION_DIAGNOSTICS,
    ),
    ErrorCode.UNKNOWN: (
        "原因を特定できないエラーが発生しました。",
        "「診断情報」を開いて詳細を確認してください。yt-dlpの更新で直ることもあります。",
        ACTION_DIAGNOSTICS,
    ),
}


def _strip_noise(text: str) -> str:
    """Drop yt-dlp's ERROR:/WARNING: prefixes and ANSI codes for readability."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"^\s*(ERROR|WARNING):\s*", "", text, flags=re.I | re.M)
    return text.strip()


def classify(exc: BaseException | str) -> ClassifiedError:
    """Translate a yt-dlp failure into a user-facing message and remedy."""
    raw = _strip_noise(str(exc))
    code: ErrorCode | None = None

    # Some failures never produce a yt-dlp message, so check the type first.
    if isinstance(exc, TimeoutError):
        code = ErrorCode.NETWORK
    elif isinstance(exc, OSError) and exc.errno in (13, 28):
        code = ErrorCode.DISK_ERROR

    if code is None:
        for candidate, pattern in _RULES:
            if pattern.search(raw):
                code = candidate
                break

    code = code or ErrorCode.UNKNOWN
    message, remedy, action = _MESSAGES[code]
    if code is ErrorCode.UNKNOWN and raw:
        # Nothing matched, so the raw text is the only real information we have.
        message = f"{message}\n{raw[:300]}"

    return ClassifiedError(code=code, message=message, remedy=remedy, raw=raw, action=action)


# --- Diagnostics ring buffer -------------------------------------------------

_recent: deque[dict] = deque(maxlen=5)


def record(error: ClassifiedError, context: str = "") -> None:
    """Remember a failure so /api/diagnostics can show it later."""
    _recent.append(
        {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "code": error.code.value,
            "message": error.message,
            "raw": error.raw[:500],
            "context": context,
        }
    )


def recent_errors() -> list[dict]:
    """Most recent failures, newest first."""
    return list(reversed(_recent))
