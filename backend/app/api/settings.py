from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import ProviderSettings, ProviderTestResult
from app.services.providers import ProviderError, test_provider
from app.services.settings_store import provider_settings_store
from app.services.storage import storage_status

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/providers", response_model=ProviderSettings)
def get_providers() -> ProviderSettings:
    return provider_settings_store.redacted()


@router.put("/providers", response_model=ProviderSettings)
def save_providers(payload: ProviderSettings) -> ProviderSettings:
    provider_settings_store.save(payload)
    return provider_settings_store.redacted()


@router.post("/providers/{category}/test", response_model=ProviderTestResult)
async def test_provider_endpoint(category: str) -> ProviderTestResult:
    settings = provider_settings_store.load()
    config = getattr(settings, category, None)
    if category not in {"llm", "image", "video", "embedding"} or not config:
        raise HTTPException(status_code=404, detail="未知供应商类别")
    try:
        latency = await test_provider(config, category)
        return ProviderTestResult(ok=True, message="连接与配置检查通过", latency_ms=latency)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/storage")
def get_storage_status():  # type: ignore[no-untyped-def]
    return storage_status()
