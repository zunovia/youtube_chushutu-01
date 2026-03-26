"""Application configuration."""

import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """Backend settings. Override via environment variables prefixed with YTC_."""

    port: int = 9160
    host: str = "127.0.0.1"
    download_dir: str = os.path.join(Path.home(), "Downloads", "YouTubeChushutu")
    max_concurrent_downloads: int = 3
    cors_origins: list[str] = [
        "chrome-extension://*",
        "http://localhost",
        "http://localhost:*",
    ]


settings = Settings()
