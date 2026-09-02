from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_GALGAME_", extra="ignore")

    data_dir: Path = Path(".data")
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"
    media_warning_bytes: int = 10 * 1024**3
    disk_free_warning_bytes: int = 5 * 1024**3

    @property
    def database_path(self) -> Path:
        return self.data_dir / "ai-galgame.sqlite3"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def secrets_path(self) -> Path:
        return self.data_dir / "settings.local.json"

    @property
    def frontend_dist(self) -> Path:
        configured = os.getenv("AI_GALGAME_FRONTEND_DIST")
        if configured:
            return Path(configured)
        return Path(__file__).resolve().parents[2] / "frontend" / "dist"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        for child in ("images", "videos", "uploads"):
            (self.media_dir / child).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> AppSettings:
    settings = AppSettings()
    if not settings.data_dir.is_absolute():
        root = Path(__file__).resolve().parents[2]
        settings.data_dir = (root / settings.data_dir).resolve()
    settings.ensure_directories()
    return settings
