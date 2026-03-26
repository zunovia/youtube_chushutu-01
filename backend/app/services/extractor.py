"""
YouTube extraction isolation layer.

*** THIS IS THE ONLY FILE THAT IMPORTS yt-dlp. ***

All yt-dlp internals (dicts, exceptions, option keys) are contained here
and converted to stable Pydantic models at the boundary.  When YouTube
changes break things:
  1. Run: pip install --upgrade yt-dlp
  2. If that's not enough, edit ONLY this file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import yt_dlp

from app.models.schemas import FormatOption, VideoInfo

logger = logging.getLogger(__name__)


def get_yt_dlp_version() -> str:
    """Return the installed yt-dlp version string."""
    return yt_dlp.version.__version__


def _parse_format(f: dict) -> FormatOption | None:
    """Convert a single yt-dlp format dict to a FormatOption."""
    fmt_id = f.get("format_id", "")
    ext = f.get("ext", "")
    vcodec = f.get("vcodec", "none")
    acodec = f.get("acodec", "none")

    # Skip storyboard / manifest-only entries
    if vcodec == "none" and acodec == "none":
        return None
    if ext in ("mhtml",):
        return None

    is_audio_only = vcodec == "none" and acodec != "none"

    height = f.get("height")
    resolution = f"{height}p" if height else None
    fps = f.get("fps")

    filesize = f.get("filesize") or f.get("filesize_approx")

    # Build a human-readable quality label
    if is_audio_only:
        abr = f.get("abr", "")
        label = f"Audio {abr}kbps ({ext})" if abr else f"Audio ({ext})"
    else:
        label = resolution or "Unknown"
        if fps and fps > 30:
            label += f" {fps}fps"
        if filesize:
            size_mb = filesize / (1024 * 1024)
            label += f" (~{size_mb:.0f}MB)"
        label += f" ({ext})"

    return FormatOption(
        format_id=fmt_id,
        ext=ext,
        resolution=resolution,
        fps=fps,
        vcodec=vcodec if vcodec != "none" else None,
        acodec=acodec if acodec != "none" else None,
        filesize_approx=filesize,
        is_audio_only=is_audio_only,
        quality_label=label,
    )


class Extractor:
    """The isolation boundary. Only this class touches yt-dlp."""

    def get_info(self, url: str) -> VideoInfo:
        """Fetch metadata and available formats without downloading."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if info is None:
            raise ValueError("Could not extract video information")

        formats_raw = info.get("formats", [])
        formats = []
        seen = set()
        for f in formats_raw:
            parsed = _parse_format(f)
            if parsed and parsed.format_id not in seen:
                seen.add(parsed.format_id)
                formats.append(parsed)

        # Sort: video formats by height desc, then audio formats
        video_fmts = sorted(
            [f for f in formats if not f.is_audio_only],
            key=lambda f: (f.resolution or "", f.ext),
            reverse=True,
        )
        audio_fmts = sorted(
            [f for f in formats if f.is_audio_only],
            key=lambda f: f.filesize_approx or 0,
            reverse=True,
        )

        thumbnail = info.get("thumbnail", "")
        # Prefer maxresdefault thumbnail
        thumbnails = info.get("thumbnails", [])
        if thumbnails:
            thumbnail = thumbnails[-1].get("url", thumbnail)

        return VideoInfo(
            video_id=info.get("id", ""),
            title=info.get("title", "Unknown"),
            thumbnail_url=thumbnail,
            duration_seconds=int(info.get("duration", 0)),
            channel=info.get("channel", info.get("uploader", "Unknown")),
            formats=video_fmts + audio_fmts,
        )

    def download(
        self,
        url: str,
        format_id: str | None,
        output_dir: str,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> Path:
        """Download a specific format. Returns path to downloaded file."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        ydl_opts: dict = {
            "outtmpl": str(output_path / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }

        if format_id:
            # Request format + merge with best audio if video-only
            ydl_opts["format"] = f"{format_id}+bestaudio/best/{format_id}"
        else:
            ydl_opts["format"] = "bestvideo+bestaudio/best"

        # Prefer mp4 output for merged files
        ydl_opts["merge_output_format"] = "mp4"

        if progress_callback:
            ydl_opts["progress_hooks"] = [progress_callback]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        if info is None:
            raise ValueError("Download failed: no info returned")

        # Determine the actual output file path
        filename = ydl.prepare_filename(info)
        # After merge, extension may change to mp4
        result_path = Path(filename)
        if not result_path.exists():
            # Try with .mp4 extension
            mp4_path = result_path.with_suffix(".mp4")
            if mp4_path.exists():
                result_path = mp4_path

        return result_path

    def download_audio(
        self,
        url: str,
        audio_format: str = "mp3",
        output_dir: str = ".",
        progress_callback: Callable[[dict], None] | None = None,
    ) -> Path:
        """Download best audio and convert via ffmpeg postprocessor."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        ydl_opts: dict = {
            "format": "bestaudio/best",
            "outtmpl": str(output_path / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": "192",
                }
            ],
        }

        if progress_callback:
            ydl_opts["progress_hooks"] = [progress_callback]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        if info is None:
            raise ValueError("Audio download failed: no info returned")

        filename = ydl.prepare_filename(info)
        result_path = Path(filename).with_suffix(f".{audio_format}")

        return result_path
