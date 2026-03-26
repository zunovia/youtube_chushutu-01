"""FastAPI application setup."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.video import router as video_router

app = FastAPI(
    title="YouTube Chushutu Backend",
    version="1.0.0",
    docs_url="/docs",
)

# CORS: allow requests from Chrome extension and localhost
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|http://localhost(:\d+)?)$",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video_router)
