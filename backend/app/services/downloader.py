"""Download task management and progress tracking."""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from app.config import settings
from app.models.schemas import DownloadRequest, DownloadTask
from app.services.errors import ErrorCode, classify, record
from app.services.extractor import Extractor, ExtractionError

logger = logging.getLogger(__name__)

_TERMINAL = frozenset({"done", "error"})


class DownloadManager:
    """Runs downloads in background threads and exposes their progress."""

    def __init__(self, extractor: Extractor | None = None) -> None:
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_downloads,
            thread_name_prefix="ytc-download",
        )
        self._extractor = extractor or Extractor()

    @property
    def extractor(self) -> Extractor:
        return self._extractor

    # --- Task lifecycle -----------------------------------------------------

    def start_download(self, request: DownloadRequest) -> str:
        """Queue a download and return its task id."""
        self._evict()

        task_id = str(uuid.uuid4())
        now = time.time()
        with self._lock:
            self._tasks[task_id] = DownloadTask(
                task_id=task_id, status="pending", created_at=now, updated_at=now
            )

        self._executor.submit(self._run, task_id, request)
        return task_id

    def get_progress(self, task_id: str) -> DownloadTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            # Copy under the lock: the caller serializes this outside it, while
            # a worker thread may still be writing to the live object.
            return task.model_copy() if task else None

    def _evict(self) -> None:
        """Drop old finished tasks. Running tasks are never evicted."""
        cutoff = time.time() - settings.task_retention_seconds
        with self._lock:
            stale = [
                tid
                for tid, task in self._tasks.items()
                if task.status in _TERMINAL and task.updated_at < cutoff
            ]
            for tid in stale:
                del self._tasks[tid]

            if len(self._tasks) > settings.max_tasks:
                finished = sorted(
                    (t for t in self._tasks.values() if t.status in _TERMINAL),
                    key=lambda t: t.updated_at,
                )
                for task in finished[: len(self._tasks) - settings.max_tasks]:
                    self._tasks.pop(task.task_id, None)

    def _update(self, task_id: str, **fields) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            for key, value in fields.items():
                setattr(task, key, value)
            task.updated_at = time.time()

    # --- Callbacks fed to the extractor -------------------------------------

    def _progress_hook(self, task_id: str):
        def hook(payload: dict) -> None:
            status = payload.get("status", "")
            if status == "downloading":
                total = payload.get("total_bytes") or payload.get("total_bytes_estimate") or 0
                downloaded = payload.get("downloaded_bytes") or 0
                fields: dict = {"status": "downloading"}
                if total > 0:
                    fields["percent"] = round(downloaded / total * 100, 1)

                speed = payload.get("speed")
                if speed:
                    fields["speed"] = f"{speed / (1024 * 1024):.1f} MB/s"

                eta = payload.get("eta")
                if eta is not None:
                    minutes, seconds = divmod(int(eta), 60)
                    fields["eta"] = f"{minutes}:{seconds:02d}"

                self._update(task_id, **fields)
            elif status == "finished":
                # yt-dlp has the bytes; ffmpeg merge/convert may still follow.
                self._update(task_id, status="converting", percent=100.0, speed="", eta="")

        return hook

    def _attempt_hook(self, task_id: str):
        def hook(index: int, total: int, name: str) -> None:
            note = "" if index == 1 else f"再試行中 ({index}/{total}): {name}"
            # Reset progress so a retry does not appear to run backwards.
            self._update(
                task_id,
                attempt=index,
                max_attempts=total,
                attempt_note=note,
                percent=0.0,
                speed="",
                eta="",
            )

        return hook

    # --- Worker -------------------------------------------------------------

    def _run(self, task_id: str, request: DownloadRequest) -> None:
        self._update(task_id, status="downloading")
        progress = self._progress_hook(task_id)
        attempt = self._attempt_hook(task_id)

        try:
            if request.audio_only:
                result = self._extractor.download_audio(
                    url=request.url,
                    audio_format=request.audio_format,
                    output_dir=settings.download_dir,
                    progress_callback=progress,
                    on_attempt=attempt,
                )
            else:
                result = self._extractor.download(
                    url=request.url,
                    format_id=request.format_id,
                    output_dir=settings.download_dir,
                    progress_callback=progress,
                    on_attempt=attempt,
                )

            self._update(
                task_id,
                status="done",
                percent=100.0,
                file_path=str(result.path),
                warnings=result.warnings,
                attempt_note="",
                speed="",
                eta="",
            )

        except ExtractionError as exc:
            logger.warning("task %s failed: %s", task_id, exc.classified.code.value)
            self._fail(task_id, exc.classified, exc.attempts)

        except Exception as exc:  # noqa: BLE001 — nothing may escape unreported
            logger.exception("task %s failed unexpectedly", task_id)
            error = classify(exc)
            record(error, context="download")
            self._fail(task_id, error, [])

    def _fail(self, task_id: str, error, attempts: list[str]) -> None:
        self._update(
            task_id,
            status="error",
            error_code=error.code,
            error=error.message,
            remedy=error.remedy,
            action=error.action,
            error_detail=error.raw[:2000],
            attempts=attempts,
            attempt_note="",
            speed="",
            eta="",
        )


download_manager = DownloadManager()


def ffmpeg_blocking_reason(request: DownloadRequest) -> ErrorCode | None:
    """Return a code when the request cannot possibly succeed without ffmpeg.

    Checked before a task is created so the user gets the answer immediately
    rather than after a poll cycle.
    """
    if download_manager.extractor.ffmpeg_available:
        return None
    if request.audio_only and request.audio_format != "m4a":
        return ErrorCode.FFMPEG_MISSING
    return None
