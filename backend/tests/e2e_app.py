from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "backend"))
os.environ["AI_GALGAME_DATA_DIR"] = str(project_root / ".e2e-data")

from app.schemas import ProviderConfig, ProviderSettings  # noqa: E402
from app.services.settings_store import provider_settings_store  # noqa: E402

mock = ProviderConfig(kind="mock", base_url="", api_key="", model="mock", enabled=True)
provider_settings_store.save(ProviderSettings(llm=mock, image=mock, video=mock))
app = importlib.import_module("app.main").app
