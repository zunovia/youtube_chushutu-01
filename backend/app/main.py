"""FastAPI application setup."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.video import router as video_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="YouTube Chushutu Backend",
    version="2.0.0",
    docs_url="/docs",
)

# Requests come from the extension's chrome-extension:// origin, and from
# localhost when testing with curl or the /docs page.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|http://(localhost|127\.0\.0\.1)(:\d+)?)$",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video_router)
