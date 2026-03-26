"""API routes for video info, download, and progress."""

from __future__ import annotations

import shutil
import subprocess
import sys

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    DownloadRequest,
    DownloadTask,
    HealthResponse,
    VideoInfo,
)
from app.services.downloader import download_manager
from app.services.extractor import Extractor, get_yt_dlp_version

router = APIRouter(prefix="/api")
extractor = Extractor()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check backend health, yt-dlp version, and ffmpeg availability."""
    ffmpeg_available = shutil.which("ffmpeg") is not None
    return HealthResponse(
        status="ok",
        yt_dlp_version=get_yt_dlp_version(),
        ffmpeg_available=ffmpeg_available,
    )


@router.get("/info", response_model=VideoInfo)
async def get_video_info(url: str = Query(..., description="YouTube video URL")) -> VideoInfo:
    """Fetch video metadata and available formats."""
    try:
        return extractor.get_info(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/download")
async def start_download(request: DownloadRequest) -> dict:
    """Start a download task. Returns a task_id for progress polling."""
    task_id = download_manager.start_download(request)
    return {"task_id": task_id}


@router.get("/progress/{task_id}", response_model=DownloadTask)
async def get_progress(task_id: str) -> DownloadTask:
    """Get download progress for a task."""
    task = download_manager.get_progress(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/open-file")
async def open_file(body: dict) -> dict:
    """Open a file or its containing folder in the OS file manager."""
    path = body.get("path", "")
    if not path:
        raise HTTPException(status_code=400, detail="No path provided")

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", path])
        else:
            subprocess.Popen(["xdg-open", str(__import__("pathlib").Path(path).parent)])
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
