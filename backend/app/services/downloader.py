"""Download task management and progress tracking."""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from app.config import settings
from app.models.schemas import DownloadRequest, DownloadTask
from app.services.extractor import Extractor

logger = logging.getLogger(__name__)


class DownloadManager:
    """Manages download tasks with progress tracking."""

    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_downloads
        )
        self._extractor = Extractor()

    def start_download(self, request: DownloadRequest) -> str:
        """Start a download in a background thread. Returns task_id."""
        task_id = str(uuid.uuid4())
        task = DownloadTask(task_id=task_id, status="pending")

        with self._lock:
            self._tasks[task_id] = task

        self._executor.submit(self._run_download, task_id, request)
        return task_id

    def get_progress(self, task_id: str) -> DownloadTask | None:
        """Get current progress for a task."""
        with self._lock:
            return self._tasks.get(task_id)

    def _make_progress_callback(self, task_id: str):
        """Create a yt-dlp progress hook bound to a task_id."""

        def callback(d: dict) -> None:
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return

                status = d.get("status", "")
                if status == "downloading":
                    task.status = "downloading"
                    # yt-dlp gives downloaded_bytes and total_bytes
                    total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                    downloaded = d.get("downloaded_bytes", 0)
                    if total and total > 0:
                        task.percent = round((downloaded / total) * 100, 1)

                    speed = d.get("speed")
                    if speed:
                        speed_mb = speed / (1024 * 1024)
                        task.speed = f"{speed_mb:.1f} MB/s"

                    eta = d.get("eta")
                    if eta is not None:
                        mins, secs = divmod(int(eta), 60)
                        task.eta = f"{mins}:{secs:02d}"

                elif status == "finished":
                    task.status = "converting"
                    task.percent = 100.0

        return callback

    def _run_download(self, task_id: str, request: DownloadRequest) -> None:
        """Execute the download (runs in background thread)."""
        try:
            with self._lock:
                task = self._tasks.get(task_id)
                if task:
                    task.status = "downloading"

            progress_cb = self._make_progress_callback(task_id)

            if request.audio_only:
                result_path = self._extractor.download_audio(
                    url=request.url,
                    audio_format=request.audio_format,
                    output_dir=settings.download_dir,
                    progress_callback=progress_cb,
                )
            else:
                result_path = self._extractor.download(
                    url=request.url,
                    format_id=request.format_id,
                    output_dir=settings.download_dir,
                    progress_callback=progress_cb,
                )

            with self._lock:
                task = self._tasks.get(task_id)
                if task:
                    task.status = "done"
                    task.percent = 100.0
                    task.file_path = str(result_path)

        except Exception as e:
            logger.exception("Download failed for task %s", task_id)
            with self._lock:
                task = self._tasks.get(task_id)
                if task:
                    task.status = "error"
                    task.error = str(e)


# Singleton instance
download_manager = DownloadManager()
