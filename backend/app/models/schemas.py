"""Pydantic models — stable API schema regardless of yt-dlp internals."""

from __future__ import annotations

from pydantic import BaseModel


class FormatOption(BaseModel):
    """A single downloadable format."""

    format_id: str
    ext: str
    resolution: str | None = None  # e.g. "1080p", None for audio-only
    fps: int | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize_approx: int | None = None  # bytes
    is_audio_only: bool = False
    quality_label: str = ""  # human-readable label for the UI


class VideoInfo(BaseModel):
    """Metadata returned by the /api/info endpoint."""

    video_id: str
    title: str
    thumbnail_url: str
    duration_seconds: int
    channel: str
    formats: list[FormatOption]


class DownloadRequest(BaseModel):
    """Request body for /api/download."""

    url: str
    format_id: str | None = None  # None → best
    audio_only: bool = False
    audio_format: str = "mp3"  # mp3 or m4a


class DownloadTask(BaseModel):
    """Progress info for a running download."""

    task_id: str
    status: str = "pending"  # pending | downloading | converting | done | error
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    file_path: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Response for /api/health."""

    status: str = "ok"
    yt_dlp_version: str = ""
    ffmpeg_available: bool = False
