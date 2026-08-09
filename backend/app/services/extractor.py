"""
YouTube extraction isolation layer.

*** THIS IS THE ONLY FILE THAT IMPORTS yt-dlp. ***

Everything yt-dlp-shaped — option keys, result dicts, exception types — stops
here and is converted to the Pydantic models in app.models.schemas. When
YouTube changes and something breaks:

  1. Update yt-dlp (the popup's 更新 button, or scripts/update-ytdlp).
  2. If that is not enough, edit ONLY this file.

Two behaviours here exist specifically because YouTube keeps moving:

  * A fallback chain of extraction strategies (different player clients, then
    browser cookies) is walked whenever a failure looks retryable.
  * ffmpeg is treated as optional. High-quality YouTube streams ship video and
    audio separately, so merging normally needs ffmpeg; without it we fall back
    to a single progressive file and say so, rather than failing outright.
"""

from __future__ import annotations

import copy
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yt_dlp

from app.config import settings
from app.models.schemas import FormatOption, VideoInfo
from app.services.errors import (
    PLAIN_RETRY_ONLY,
    RETRYABLE,
    ClassifiedError,
    ErrorCode,
    classify,
    record,
)

logger = logging.getLogger(__name__)

ProgressHook = Callable[[dict], None]
AttemptHook = Callable[[int, int, str], None]


def get_yt_dlp_version() -> str:
    """Return the installed yt-dlp version string."""
    return yt_dlp.version.__version__


class ExtractionError(Exception):
    """A classified extraction failure, carrying the full attempt history."""

    def __init__(self, classified: ClassifiedError, attempts: list[str]) -> None:
        self.classified = classified
        self.attempts = attempts
        super().__init__(classified.message)


@dataclass
class DownloadResult:
    """Outcome of a successful download."""

    path: Path
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Strategy:
    """One way of asking YouTube for a video."""

    name: str
    player_client: str | None = None
    cookies: bool = False

    def apply(self, opts: dict) -> dict:
        opts = copy.deepcopy(opts)
        if self.player_client:
            opts.setdefault("extractor_args", {})["youtube"] = {
                "player_client": [self.player_client]
            }
        if self.cookies:
            if settings.cookies_file:
                opts["cookiefile"] = settings.cookies_file
            else:
                opts["cookiesfrombrowser"] = (settings.cookie_browser, None, None, None)
        return opts


def _build_strategies() -> list[_Strategy]:
    """The order in which we try to talk to YouTube.

    Cookies come after the plain attempts because reading the browser's cookie
    store is intrusive and slow; we only pay that cost once YouTube has actually
    challenged us.
    """
    strategies = [_Strategy("標準")]
    for client in settings.player_clients:
        strategies.append(_Strategy(f"クライアント:{client}", player_client=client))
    strategies.append(_Strategy("Cookie使用", cookies=True))
    if settings.player_clients:
        strategies.append(
            _Strategy(
                f"Cookie+{settings.player_clients[0]}",
                player_client=settings.player_clients[0],
                cookies=True,
            )
        )
    return strategies


def _base_opts() -> dict:
    """Options shared by every attempt."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # A URL like watch?v=X&list=RDX — which is what YouTube produces from a
        # playlist click or an autoplay Mix — is claimed by the playlist
        # extractor, not the video one. Without this, /api/info returns playlist
        # metadata with no formats and a download fetches every entry.
        "noplaylist": True,
        "retries": settings.ytdl_retries,
        "fragment_retries": settings.ytdl_fragment_retries,
        "extractor_retries": 3,
        "socket_timeout": settings.socket_timeout,
        "concurrent_fragment_downloads": 4,
        "geo_bypass": True,
        # Windows rejects ? * : " < > | in filenames and caps paths at 260 chars.
        # Japanese video titles hit both limits routinely.
        "windowsfilenames": True,
        "trim_file_name": 120,
        "ignoreerrors": False,
    }
    if settings.proxy:
        opts["proxy"] = settings.proxy
    if settings.ffmpeg_location:
        opts["ffmpeg_location"] = settings.ffmpeg_location
    return opts


def _simulated_failure(attempt_index: int) -> None:
    """Raise a canned yt-dlp-style error when a testing hook is enabled."""
    if settings.simulate_fail_attempts and attempt_index < settings.simulate_fail_attempts:
        raise yt_dlp.utils.DownloadError(
            "ERROR: [youtube] test: Sign in to confirm you're not a bot"
        )
    if not settings.simulate_error:
        return

    canned = {
        "BOT_CHECK": "ERROR: [youtube] test: Sign in to confirm you're not a bot",
        "OUTDATED_YTDLP": "ERROR: [youtube] test: nsig extraction failed",
        "HTTP_FORBIDDEN": "ERROR: unable to download video data: HTTP Error 403: Forbidden",
        "FFMPEG_MISSING": (
            "ERROR: You have requested merging of multiple formats "
            "but ffmpeg is not installed"
        ),
        "AGE_RESTRICTED": "ERROR: [youtube] test: Sign in to confirm your age",
        "PRIVATE_VIDEO": "ERROR: [youtube] test: Private video",
        "UNAVAILABLE": "ERROR: [youtube] test: Video unavailable",
        "GEO_BLOCKED": "ERROR: [youtube] test: This video is not available in your country",
        "LIVE_NOT_ENDED": "ERROR: [youtube] test: This live event will begin in 2 hours",
        "FORMAT_UNAVAILABLE": "ERROR: Requested format is not available",
        "COOKIE_LOCKED": "ERROR: could not copy Chrome cookie database",
        "NETWORK": "ERROR: Unable to download webpage: timed out",
        "DISK_ERROR": "ERROR: unable to write data: [Errno 28] No space left on device",
    }
    message = canned.get(settings.simulate_error.upper())
    if message is None:
        raise yt_dlp.utils.DownloadError(f"ERROR: simulated failure {settings.simulate_error}")
    raise yt_dlp.utils.DownloadError(message)


# Failures of our own retry machinery rather than of the video itself. Reporting
# one of these hides the real cause: if four attempts said 403 and the fifth
# could not open the cookie store, the user needs to hear about the 403.
_INFRASTRUCTURE = frozenset({ErrorCode.COOKIE_LOCKED})


def _primary_error(errors: list[ClassifiedError]) -> ClassifiedError:
    """Pick the failure that best explains why the whole chain failed."""
    substantive = [e for e in errors if e.code not in _INFRASTRUCTURE]
    if not substantive:
        return errors[-1]

    counts: dict[ErrorCode, int] = {}
    for error in substantive:
        counts[error.code] = counts.get(error.code, 0) + 1
    winner = max(counts, key=lambda code: counts[code])
    # Ties resolve to the earliest occurrence, i.e. the plainest strategy.
    return next(e for e in substantive if e.code is winner)


def _parse_format(f: dict) -> FormatOption | None:
    """Convert one yt-dlp format dict into a FormatOption."""
    ext = f.get("ext", "")
    vcodec = f.get("vcodec") or "none"
    acodec = f.get("acodec") or "none"

    # Storyboards and manifest-only entries are not downloadable media.
    if vcodec == "none" and acodec == "none":
        return None
    if ext == "mhtml":
        return None

    is_audio_only = vcodec == "none"
    height = f.get("height")
    fps = f.get("fps")
    filesize = f.get("filesize") or f.get("filesize_approx")
    # Video without audio has to be merged with a separate audio stream.
    needs_merge = not is_audio_only and acodec == "none"

    if is_audio_only:
        abr = f.get("abr")
        label = f"音声 {abr:.0f}kbps ({ext})" if abr else f"音声 ({ext})"
    else:
        label = f"{height}p" if height else "画質不明"
        if fps and fps > 30:
            label += f" {fps:.0f}fps"
        label += f" ({ext})"
        if filesize:
            label += f" 約{filesize / (1024 * 1024):.0f}MB"

    return FormatOption(
        format_id=f.get("format_id", ""),
        ext=ext,
        resolution=f"{height}p" if height else None,
        height=height,
        fps=int(fps) if fps else None,
        vcodec=None if vcodec == "none" else vcodec,
        acodec=None if acodec == "none" else acodec,
        filesize_approx=filesize,
        is_audio_only=is_audio_only,
        needs_merge=needs_merge,
        quality_label=label,
    )


def _resolve_output_path(ydl: yt_dlp.YoutubeDL, info: dict) -> Path:
    """Find where the file actually landed.

    Post-processing (merging, audio conversion) changes the extension, so the
    name yt-dlp planned up front is often not the name on disk. yt-dlp records
    the real path in requested_downloads; fall back to probing extensions.
    """
    for entry in info.get("requested_downloads") or []:
        actual = entry.get("filepath") or entry.get("_filename")
        if actual:
            return Path(actual)

    planned = Path(ydl.prepare_filename(info))
    if planned.exists():
        return planned
    for ext in (".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".opus", ".ogg"):
        candidate = planned.with_suffix(ext)
        if candidate.exists():
            return candidate
    return planned


class Extractor:
    """The isolation boundary. Only this class touches yt-dlp."""

    def __init__(self) -> None:
        self._ffmpeg_path: str | None = None
        self.refresh_ffmpeg()

    # --- ffmpeg -------------------------------------------------------------

    def refresh_ffmpeg(self) -> None:
        """Re-check for ffmpeg (it may be installed while we are running)."""
        if settings.ffmpeg_location:
            candidate = Path(settings.ffmpeg_location)
            found = shutil.which("ffmpeg", path=str(candidate)) or (
                str(candidate) if candidate.is_file() else None
            )
        else:
            found = shutil.which("ffmpeg")
        self._ffmpeg_path = found

    @property
    def ffmpeg_available(self) -> bool:
        return self._ffmpeg_path is not None

    @property
    def ffmpeg_path(self) -> str | None:
        return self._ffmpeg_path

    # --- Fallback chain -----------------------------------------------------

    def _run_with_fallback(
        self,
        run: Callable[[dict], object],
        *,
        context: str,
        on_attempt: AttemptHook | None = None,
    ) -> object:
        """Walk the strategy chain until one succeeds or a hard error appears."""
        strategies = _build_strategies()
        attempts: list[str] = []
        errors: list[ClassifiedError] = []

        for index, strategy in enumerate(strategies):
            if on_attempt:
                on_attempt(index + 1, len(strategies), strategy.name)

            opts = strategy.apply(_base_opts())
            try:
                _simulated_failure(index)
                return run(opts)
            except Exception as exc:  # noqa: BLE001 — classified immediately below
                error = classify(exc)
                errors.append(error)
                attempts.append(f"{strategy.name}:{error.code.value}")
                logger.warning(
                    "%s attempt %d/%d (%s) failed: %s — %s",
                    context,
                    index + 1,
                    len(strategies),
                    strategy.name,
                    error.code.value,
                    error.raw[:200],
                )
                if error.code not in RETRYABLE:
                    break

                nxt = index + 1
                if nxt >= len(strategies):
                    break
                # A malformed URL or a dead socket will not be fixed by reading
                # the user's cookies, so stop rather than pay for that attempt.
                if strategies[nxt].cookies and error.code in PLAIN_RETRY_ONLY:
                    break
                # Switching player client is a genuinely different request, so
                # retry it immediately. Only pause before a cookie attempt,
                # where a rate-limit style block may still be cooling off —
                # exponential backoff across the whole chain would leave the
                # user staring at a spinner for half a minute.
                if strategies[nxt].cookies:
                    time.sleep(2)

        primary = _primary_error(errors)
        record(primary, context=f"{context} / {' → '.join(attempts)}")
        raise ExtractionError(primary, attempts)

    # --- Public API ---------------------------------------------------------

    def get_info(self, url: str, on_attempt: AttemptHook | None = None) -> VideoInfo:
        """Fetch metadata and available formats without downloading."""

        def run(opts: dict) -> VideoInfo:
            opts = {**opts, "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info is None:
                raise ValueError("動画情報を取得できませんでした")
            return self._to_video_info(info)

        return self._run_with_fallback(run, context="info", on_attempt=on_attempt)  # type: ignore[return-value]

    def _to_video_info(self, info: dict) -> VideoInfo:
        formats: list[FormatOption] = []
        seen: set[str] = set()
        for raw in info.get("formats", []):
            parsed = _parse_format(raw)
            if parsed and parsed.format_id not in seen:
                seen.add(parsed.format_id)
                formats.append(parsed)

        # Sort on the numeric height, not the "1080p" string — otherwise
        # lexicographic ordering puts 720p above 1080p.
        video = sorted(
            (f for f in formats if not f.is_audio_only),
            key=lambda f: (f.height or 0, f.fps or 0, f.filesize_approx or 0),
            reverse=True,
        )
        audio = sorted(
            (f for f in formats if f.is_audio_only),
            key=lambda f: f.filesize_approx or 0,
            reverse=True,
        )

        thumbnails = info.get("thumbnails") or []
        thumbnail = thumbnails[-1].get("url", "") if thumbnails else info.get("thumbnail", "")

        return VideoInfo(
            video_id=info.get("id", ""),
            title=info.get("title", "不明"),
            thumbnail_url=thumbnail or "",
            duration_seconds=int(info.get("duration") or 0),
            channel=info.get("channel") or info.get("uploader") or "不明",
            formats=video + audio,
        )

    def download(
        self,
        url: str,
        format_id: str | None,
        output_dir: str,
        progress_callback: ProgressHook | None = None,
        on_attempt: AttemptHook | None = None,
    ) -> DownloadResult:
        """Download video (with audio). Degrades gracefully when ffmpeg is absent."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []

        if self.ffmpeg_available:
            fmt = f"{format_id}+bestaudio/{format_id}/best" if format_id else "bestvideo+bestaudio/best"
        else:
            # Without ffmpeg we cannot join separate video and audio streams, so
            # restrict the choice to formats that already contain both. That caps
            # quality around 720p, which is worth saying out loud.
            fmt = f"{format_id}[acodec!=none]/best[ext=mp4]/best" if format_id else "best[ext=mp4]/best"
            warnings.append(
                "ffmpegが無いため、映像と音声が1つになった形式で保存しました"
                "（最高でも720p程度になります）。高画質にはffmpegが必要です。"
            )

        def run(opts: dict) -> DownloadResult:
            opts = {
                **opts,
                "format": fmt,
                "outtmpl": str(output_path / "%(title)s.%(ext)s"),
            }
            if self.ffmpeg_available:
                opts["merge_output_format"] = "mp4"
            if progress_callback:
                opts["progress_hooks"] = [progress_callback]

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise ValueError("ダウンロードに失敗しました")
                path = _resolve_output_path(ydl, info)

            result_warnings = list(warnings)
            chosen = str(info.get("format_id") or "")
            if format_id and chosen and format_id not in chosen.split("+"):
                result_warnings.append(
                    f"選択した画質が使えなかったため、別の形式で保存しました（{chosen}）。"
                )
            return DownloadResult(path=path, warnings=result_warnings)

        return self._run_with_fallback(run, context="download", on_attempt=on_attempt)  # type: ignore[return-value]

    def download_audio(
        self,
        url: str,
        audio_format: str = "mp3",
        output_dir: str = ".",
        progress_callback: ProgressHook | None = None,
        on_attempt: AttemptHook | None = None,
    ) -> DownloadResult:
        """Download audio only, converting with ffmpeg when it is available."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []

        if not self.ffmpeg_available and audio_format != "m4a":
            # MP3 always requires a transcode; M4A can be saved as-is.
            # Recorded explicitly: this raise bypasses the fallback chain, which
            # is where failures normally reach the diagnostics buffer.
            error = classify("ffmpeg is not installed")
            record(error, context="audio / ffmpeg事前チェック")
            raise ExtractionError(error, ["ffmpeg事前チェック:FFMPEG_MISSING"])

        use_postprocessor = self.ffmpeg_available
        if not use_postprocessor:
            warnings.append("ffmpegが無いため、変換せずM4Aのまま保存しました。")

        def run(opts: dict) -> DownloadResult:
            opts = {
                **opts,
                "format": "bestaudio/best" if use_postprocessor else "bestaudio[ext=m4a]/bestaudio",
                "outtmpl": str(output_path / "%(title)s.%(ext)s"),
            }
            if use_postprocessor:
                opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": audio_format,
                        "preferredquality": "192",
                    }
                ]
            if progress_callback:
                opts["progress_hooks"] = [progress_callback]

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise ValueError("音声のダウンロードに失敗しました")
                path = _resolve_output_path(ydl, info)

            return DownloadResult(path=path, warnings=list(warnings))

        return self._run_with_fallback(run, context="audio", on_attempt=on_attempt)  # type: ignore[return-value]

    def cookies_configured(self) -> bool:
        """Whether a cookie source is available for the retry strategies."""
        if settings.cookies_file:
            return Path(settings.cookies_file).is_file()
        return bool(settings.cookie_browser)
