#!/usr/bin/env python3
"""Entry point — starts the backend server. Can be run from any directory."""

import os
import sys
from pathlib import Path

# Make the backend directory importable so `app` resolves no matter where the
# user launched this from (double-clicked start.bat, a shell elsewhere, ...).
backend_dir = Path(__file__).resolve().parent
os.chdir(backend_dir)
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import uvicorn  # noqa: E402

from app.config import settings  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        # Auto-reload restarts the server whenever a file changes, which kills
        # in-flight downloads and loses their progress. Off unless requested.
        reload=settings.reload,
    )
