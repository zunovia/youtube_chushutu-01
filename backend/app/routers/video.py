"""API routes: video info, downloads, progress, updates, diagnostics."""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.config import settings
from app.models.schemas import (
    DiagnosticsResponse,
    DownloadRequest,
    DownloadTask,
    ErrorDetail,
    HealthResponse,
    UpdateInfo,
    VideoInfo,
)
from app.services import updater
from app.services.downloader import download_manager, ffmpeg_blocking_reason
from app.services.errors import ErrorCode, classify, recent_errors, record
from app.services.extractor import ExtractionError, get_yt_dlp_version

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
extractor = download_manager.extractor


def _error_response(detail: ErrorDetail, status_code: int = 400) -> JSONResponse:
    """Return the error as the top-level body so the client can read error_code."""
    return JSONResponse(status_code=status_code, content=detail.model_dump())


def _from_extraction_error(exc: ExtractionError) -> ErrorDetail:
    error = exc.classified
    return ErrorDetail(
        error_code=error.code,
        message=error.message,
        remedy=error.remedy,
        action=error.action,
        detail=error.raw[:2000],
        attempts=exc.attempts,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness plus the two facts the popup needs up front."""
    extractor.refresh_ffmpeg()
    return HealthResponse(
        status="ok",
        yt_dlp_version=get_yt_dlp_version(),
        ffmpeg_available=extractor.ffmpeg_available,
        cookies_configured=extractor.cookies_configured(),
        download_dir=settings.download_dir,
    )


@router.get("/info", response_model=VideoInfo)
async def get_video_info(url: str = Query(..., description="YouTube video URL")):
    """Fetch video metadata and available formats."""
    try:
        # yt-dlp is blocking; without the threadpool this stalls every other
        # request (including /health) for the whole extraction.
        return await run_in_threadpool(extractor.get_info, url)
    except ExtractionError as exc:
        return _error_response(_from_extraction_error(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("info failed")
        error = classify(exc)
        record(error, context="info")
        return _error_response(
            ErrorDetail(
                error_code=error.code,
                message=error.message,
                remedy=error.remedy,
                action=error.action,
                detail=error.raw[:2000],
            )
        )


@router.post("/download")
async def start_download(request: DownloadRequest):
    """Start a download task. Returns a task_id for progress polling."""
    extractor.refresh_ffmpeg()

    blocked = ffmpeg_blocking_reason(request)
    if blocked is ErrorCode.FFMPEG_MISSING:
        error = classify("ffmpeg is not installed")
        record(error, context="download / ffmpeg事前チェック")
        return _error_response(
            ErrorDetail(
                error_code=error.code,
                message="MP3への変換にはffmpegが必要です。",
                remedy=error.remedy + " すぐに保存したい場合は形式をM4Aにしてください。",
                action=error.action,
            )
        )

    task_id = download_manager.start_download(request)
    return {"task_id": task_id}


@router.get("/progress/{task_id}", response_model=DownloadTask)
async def get_progress(task_id: str) -> DownloadTask:
    """Get download progress. 404 means the task is gone (e.g. server restart)."""
    task = download_manager.get_progress(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/update-check", response_model=UpdateInfo)
async def update_check(force: bool = Query(False)) -> UpdateInfo:
    """Compare the installed yt-dlp with the latest release (cached 24h)."""
    return await run_in_threadpool(updater.check_for_update, force)


@router.post("/update-ytdlp", response_model=UpdateInfo)
async def update_ytdlp() -> UpdateInfo:
    """Upgrade yt-dlp via pip. Requires a server restart to take effect."""
    return await run_in_threadpool(updater.apply_update)


@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def diagnostics() -> DiagnosticsResponse:
    """Everything needed to explain a breakage without reading the terminal."""
    extractor.refresh_ffmpeg()
    return DiagnosticsResponse(
        yt_dlp_version=get_yt_dlp_version(),
        ffmpeg_available=extractor.ffmpeg_available,
        ffmpeg_path=extractor.ffmpeg_path,
        cookie_browser=settings.cookies_file or settings.cookie_browser,
        download_dir=settings.download_dir,
        python_version=sys.version.split()[0],
        platform=f"{platform.system()} {platform.release()}",
        recent_errors=recent_errors(),
    )


@router.post("/open-file")
async def open_file(body: dict = Body(...)) -> dict:
    """Reveal a downloaded file in the OS file manager."""
    raw_path = body.get("path", "")
    if not raw_path or not isinstance(raw_path, str):
        raise HTTPException(status_code=400, detail="パスが指定されていません")

    target = Path(raw_path).resolve()
    root = Path(settings.download_dir).resolve()
    # This endpoint is reachable from any page that can talk to localhost, so
    # it must only ever reveal files we ourselves downloaded.
    if not target.is_relative_to(root):
        raise HTTPException(status_code=403, detail="保存先フォルダの外は開けません")

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        elif sys.platform == "win32":
            # explorer needs /select and the path as one argument string.
            subprocess.Popen(f'explorer /select,"{target}"')
        else:
            subprocess.Popen(["xdg-open", str(target.parent)])
        return {"status": "ok"}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
