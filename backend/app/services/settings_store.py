from __future__ import annotations

import json
import threading
from pathlib import Path

from app.config import get_settings
from app.schemas import ProviderConfig, ProviderSettings

MASK = "••••••••"


class ProviderSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_settings().secrets_path
        self._lock = threading.Lock()

    def load(self) -> ProviderSettings:
        with self._lock:
            if not self.path.exists():
                return ProviderSettings()
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return ProviderSettings.model_validate(raw)

    def save(self, incoming: ProviderSettings) -> ProviderSettings:
        with self._lock:
            current = self._load_unlocked()
            merged = ProviderSettings(
                llm=self._merge_secret(current.llm, incoming.llm),
                image=self._merge_secret(current.image, incoming.image),
                video=self._merge_secret(current.video, incoming.video),
                embedding=(
                    self._merge_secret(current.embedding, incoming.embedding)
                    if current.embedding and incoming.embedding
                    else incoming.embedding
                ),
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(merged.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return merged

    def redacted(self) -> ProviderSettings:
        settings = self.load()
        for config in (settings.llm, settings.image, settings.video, settings.embedding):
            if config and config.api_key:
                config.api_key = MASK
        return settings

    def _load_unlocked(self) -> ProviderSettings:
        if not self.path.exists():
            return ProviderSettings()
        return ProviderSettings.model_validate_json(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _merge_secret(current: ProviderConfig | None, incoming: ProviderConfig) -> ProviderConfig:
        if incoming.api_key == MASK and current:
            incoming.api_key = current.api_key
        return incoming


provider_settings_store = ProviderSettingsStore()
