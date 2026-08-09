"""
Pydantic models — the stable contract between backend and extension.

These deliberately contain no yt-dlp types. extractor.py converts yt-dlp's
internal dicts into these models at the boundary, so a YouTube change that
reshapes yt-dlp's output never propagates past that one file.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.errors import ErrorCode


class FormatOption(BaseModel):
    """A single downloadable format."""

    format_id: str
    ext: str
    resolution: str | None = None  # "1080p" など。音声のみは None
    height: int | None = None  # 並べ替え用の数値（文字列だと720p>1080pになる）
    fps: int | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize_approx: int | None = None  # bytes
    is_audio_only: bool = False
    needs_merge: bool = False  # 映像のみ＝音声との結合にffmpegが必要
    quality_label: str = ""  # UI表示用のラベル


class VideoInfo(BaseModel):
    """Metadata returned by /api/info."""

    video_id: str
    title: str
    thumbnail_url: str
    duration_seconds: int
    channel: str
    formats: list[FormatOption]


class DownloadRequest(BaseModel):
    """Request body for /api/download."""

    url: str
    format_id: str | None = None  # None なら最高画質を自動選択
    audio_only: bool = False
    audio_format: str = "mp3"  # mp3 または m4a


class DownloadTask(BaseModel):
    """Progress and outcome of a download."""

    task_id: str
    status: str = "pending"  # pending | downloading | converting | done | error
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    file_path: str | None = None
    warnings: list[str] = []  # 成功したが注意が必要な点（ffmpeg無しで画質低下など）

    # 再試行の進捗。UI に「再試行中 (2/5): Cookie使用」と出すために使う。
    attempt: int = 1
    max_attempts: int = 1
    attempt_note: str = ""

    # 失敗時のみ埋まる。error_code で UI が分岐し、remedy をそのまま表示する。
    error_code: ErrorCode | None = None
    error: str | None = None
    remedy: str | None = None
    action: str = ""
    error_detail: str | None = None
    attempts: list[str] = []

    created_at: float = 0.0
    updated_at: float = 0.0


class ErrorDetail(BaseModel):
    """Structured error body returned by /api/info and /api/download on failure."""

    error_code: ErrorCode
    message: str
    remedy: str
    action: str = ""
    detail: str | None = None
    attempts: list[str] = []


class UpdateInfo(BaseModel):
    """yt-dlp version status for /api/update-check and /api/update-ytdlp."""

    current: str
    latest: str | None = None
    update_available: bool = False
    checked_at: float = 0.0  # unix time
    from_cache: bool = False
    restart_required: bool = False
    note: str = ""


class DiagnosticsResponse(BaseModel):
    """Everything needed to debug a breakage without reading the terminal."""

    yt_dlp_version: str
    ffmpeg_available: bool
    ffmpeg_path: str | None = None
    cookie_browser: str
    download_dir: str
    python_version: str
    platform: str
    recent_errors: list[dict] = []


class HealthResponse(BaseModel):
    """Lightweight liveness check for the popup's status dot."""

    status: str = "ok"
    yt_dlp_version: str = ""
    ffmpeg_available: bool = False
    cookies_configured: bool = False
    download_dir: str = ""
