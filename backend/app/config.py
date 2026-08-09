"""Application configuration. Every field is overridable via a YTC_ env var."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend settings.

    Override any field with a YTC_-prefixed environment variable, e.g.
    ``YTC_PORT=9200`` or ``YTC_DOWNLOAD_DIR=D:\\Videos``.
    List-valued fields take JSON, e.g. ``YTC_PLAYER_CLIENTS='["tv","mweb"]'``.
    """

    model_config = SettingsConfigDict(env_prefix="YTC_", env_file=".env", extra="ignore")

    # --- Server ---
    port: int = 9160
    host: str = "127.0.0.1"
    # Auto-reload restarts uvicorn on any file touch, which kills in-flight
    # downloads and wipes the task table. Off unless explicitly developing.
    reload: bool = False

    # --- Downloads ---
    download_dir: str = str(Path.home() / "Downloads" / "YouTubeChushutu")
    max_concurrent_downloads: int = 3
    ffmpeg_location: str = ""  # empty → look on PATH

    # --- Extraction resilience ---
    # Fallback player clients, tried in order when the default is blocked.
    # Editable via env so a future YouTube change needs no code edit.
    player_clients: list[str] = ["tv", "web_safari", "mweb"]
    ytdl_retries: int = 5
    ytdl_fragment_retries: int = 10
    socket_timeout: int = 30
    proxy: str = ""

    # Which browser to pull cookies from when YouTube demands proof we're human.
    # Cookies are read only after a bot-check style failure, never by default.
    cookie_browser: str = "chrome"
    cookies_file: str = ""  # Netscape cookies.txt; takes priority over the browser

    # --- Task lifecycle ---
    task_retention_seconds: int = 1800
    max_tasks: int = 100

    # --- Update checking ---
    cache_dir: str = str(Path.home() / ".youtube_chushutu")
    pypi_url: str = "https://pypi.org/pypi/yt-dlp/json"
    update_cache_ttl: int = 86400  # 24h

    # --- Testing hooks (off by default) ---
    # YTC_SIMULATE_ERROR=BOT_CHECK makes every extraction fail that way, so the
    # whole error path can be verified without waiting for YouTube to block us.
    simulate_error: str = ""
    # Fail the first N attempts, then proceed for real — exercises the retry chain.
    simulate_fail_attempts: int = 0


settings = Settings()
