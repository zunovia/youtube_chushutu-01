"""
yt-dlp version checking and one-click updating.

YouTube changes often enough that a downloader which cannot update itself will
break every few months. This module makes the update visible in the UI and one
click away, which is the whole point: the fix should not require remembering a
command line months after setup.

Deliberately depends on nothing beyond the standard library, and never raises
for network problems — being offline must not slow down or break startup.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from app.config import settings
from app.models.schemas import UpdateInfo
from app.services.extractor import get_yt_dlp_version

logger = logging.getLogger(__name__)

_memo: UpdateInfo | None = None


def _cache_path() -> Path:
    return Path(settings.cache_dir) / "update_check.json"


def _parse_version(text: str) -> tuple[int, ...]:
    """Turn '2026.03.17' into (2026, 3, 17) for comparison.

    yt-dlp uses date-based versions, sometimes with a nightly suffix. Comparing
    the numeric parts avoids a `packaging` dependency and handles both.
    """
    return tuple(int(part) for part in re.findall(r"\d+", text)) or (0,)


def _is_newer(latest: str, current: str) -> bool:
    a, b = _parse_version(latest), _parse_version(current)
    length = max(len(a), len(b))
    return a + (0,) * (length - len(a)) > b + (0,) * (length - len(b))


def _read_cache() -> dict | None:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # Valid JSON of the wrong shape (a list, a string) would sail past the
    # exception guard and then blow up on .get(), taking the update check —
    # the app's whole recovery story — down with it.
    return data if isinstance(data, dict) else None


def _write_cache(payload: dict) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.debug("could not write update cache: %s", exc)


def _fetch_latest() -> str | None:
    """Ask PyPI for the newest yt-dlp release. Returns None if unreachable."""
    try:
        with urllib.request.urlopen(settings.pypi_url, timeout=5) as response:
            payload = json.load(response)
        return str(payload["info"]["version"])
    except Exception as exc:  # noqa: BLE001 — offline is a normal state here
        logger.debug("update check failed: %s", exc)
        return None


def check_for_update(force: bool = False) -> UpdateInfo:
    """Compare the installed yt-dlp against PyPI, caching for a day."""
    global _memo

    current = get_yt_dlp_version()
    now = time.time()

    if not force and _memo is not None and now - _memo.checked_at < settings.update_cache_ttl:
        return _memo.model_copy(update={"current": current, "from_cache": True})

    cached = _read_cache()
    if not force and cached and now - cached.get("checked_at", 0) < settings.update_cache_ttl:
        latest = cached.get("latest")
        info = UpdateInfo(
            current=current,
            latest=latest,
            update_available=bool(latest) and _is_newer(latest, current),
            checked_at=cached.get("checked_at", now),
            from_cache=True,
        )
        _memo = info
        return info

    latest = _fetch_latest()
    if latest is None:
        # Fall back to whatever we knew before; otherwise report "unknown"
        # rather than inventing an answer or surfacing an error.
        stale = cached.get("latest") if cached else None
        return UpdateInfo(
            current=current,
            latest=stale,
            update_available=bool(stale) and _is_newer(stale, current),
            checked_at=now,
            from_cache=True,
            note="PyPIに接続できなかったため、更新の有無を確認できませんでした。",
        )

    _write_cache({"latest": latest, "checked_at": now})
    info = UpdateInfo(
        current=current,
        latest=latest,
        update_available=_is_newer(latest, current),
        checked_at=now,
    )
    _memo = info
    return info


def apply_update() -> UpdateInfo:
    """Run pip to upgrade yt-dlp in this interpreter's environment."""
    global _memo

    before = get_yt_dlp_version()
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return UpdateInfo(
            current=before,
            checked_at=time.time(),
            note="更新がタイムアウトしました（5分）。回線を確認するか、"
            "scripts/update-ytdlp を直接実行してください。",
        )
    except OSError as exc:
        return UpdateInfo(
            current=before,
            checked_at=time.time(),
            note=f"pipを起動できませんでした: {exc}",
        )

    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-5:]
        # A signal-killed pip can produce no output at all; without the exit
        # code the message would end at the colon and say nothing.
        detail = " / ".join(tail) if tail else f"pip が終了コード {completed.returncode} で失敗しました"
        return UpdateInfo(
            current=before,
            checked_at=time.time(),
            note="更新に失敗しました: " + detail,
        )

    _memo = None  # force a fresh comparison next time
    latest = _fetch_latest()

    # The already-imported yt_dlp module still holds the old code, so the new
    # version only takes effect once the server process is restarted.
    return UpdateInfo(
        current=before,
        latest=latest,
        update_available=False,
        checked_at=time.time(),
        restart_required=True,
        note="更新しました。サーバーを再起動すると新しいバージョンが有効になります。",
    )
