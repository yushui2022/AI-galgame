from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.api import gameplay, games, profile, settings
from app.config import get_settings
from app.database import init_database
from app.services.events import event_broker
from app.services.media_worker import media_worker

app_settings = get_settings()
logging.basicConfig(
    level=getattr(logging, app_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    init_database()
    await media_worker.start()
    yield
    await media_worker.stop()


app = FastAPI(
    title="AI-galgame",
    version="0.1.0",
    description="边玩边生成图片与视频的本地 AI Galgame",
    lifespan=lifespan,
)
app.include_router(settings.router)
app.include_router(games.router)
app.include_router(gameplay.router)
app.include_router(profile.router)


@app.get("/api/health")
def health():  # type: ignore[no-untyped-def]
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/events")
async def events():  # type: ignore[no-untyped-def]
    return StreamingResponse(event_broker.stream(), media_type="text/event-stream")


app.mount("/media", StaticFiles(directory=app_settings.media_dir), name="media")

if app_settings.frontend_dist.exists():
    assets_dir = app_settings.frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def frontend(full_path: str):  # type: ignore[no-untyped-def]
        requested = app_settings.frontend_dist / full_path
        if full_path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(app_settings.frontend_dist / "index.html")
