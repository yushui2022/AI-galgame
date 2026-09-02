from __future__ import annotations

from app.schemas import ProviderConfig, ProviderSettings
from app.services.settings_store import MASK, ProviderSettingsStore


def test_ark_image_and_video_can_share_a_saved_api_key(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = ProviderSettingsStore(tmp_path / "providers.json")
    settings = ProviderSettings(
        image=ProviderConfig(
            kind="ark",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="",
            model="seedream",
        ),
        video=ProviderConfig(
            kind="seedance",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="ark-secret",
            model="seedance",
        ),
    )
    store.save(settings)

    redacted = store.redacted()
    redacted.image.api_key = MASK
    store.save(redacted)

    loaded = store.load()
    assert loaded.image.api_key == "ark-secret"
    assert loaded.video.api_key == "ark-secret"
