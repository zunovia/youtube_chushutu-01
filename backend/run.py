#!/usr/bin/env python3
"""Entry point — starts the backend server. Can be run from any directory."""

import os
import sys
from pathlib import Path

# Ensure the backend directory is on sys.path so 'app' package is importable
backend_dir = Path(__file__).resolve().parent
os.chdir(backend_dir)
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
