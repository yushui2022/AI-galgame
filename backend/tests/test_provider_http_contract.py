from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from app.schemas import ImageSpec, ProviderConfig, VideoSpec
from app.services import providers as provider_module
from app.services import storage as storage_module
from app.services.providers import (
    ArkImageProvider,
    MiniMaxImageProvider,
    ProviderError,
    SeedanceVideoProvider,
)
from fastapi import FastAPI, Request, Response


@pytest.mark.asyncio
async def test_http_provider_submit_poll_failure_timeout_and_download(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FastAPI()
    mode = {"video": "succeeded"}

    @fake.post("/v1/image_generation")
    async def generate_image():  # type: ignore[no-untyped-def]
        return {"id": "image-task", "data": {"image_urls": ["http://fake/files/frame.png"]}}

    ark_requests: list[dict] = []

    @fake.post("/images/generations")
    async def generate_ark_image(request: Request):  # type: ignore[no-untyped-def]
        ark_requests.append(await request.json())
        return {
            "model": "doubao-seedream-test",
            "created": 123,
            "data": [{"url": "http://fake/files/frame.png", "size": "2560x1440"}],
        }

    @fake.get("/files/frame.png")
    async def image_file():  # type: ignore[no-untyped-def]
        return Response(content=b"fake-png", media_type="image/png")

    @fake.post("/contents/generations/tasks")
    async def submit_video():  # type: ignore[no-untyped-def]
        return {"id": "video-task"}

    @fake.get("/contents/generations/tasks/{task_id}")
    async def poll_video(task_id: str):  # type: ignore[no-untyped-def]
        if mode["video"] == "gateway_timeout":
            return Response(content="upstream timeout", status_code=504)
        if mode["video"] == "failed":
            return {
                "id": task_id,
                "status": "failed",
                "error": {"code": "moderation_rejected", "message": "content rejected"},
            }
        return {
            "id": task_id,
            "status": "succeeded",
            "content": {"video_url": "http://fake/files/video.mp4"},
        }

    real_async_client = httpx.AsyncClient

    def local_client(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["transport"] = httpx.ASGITransport(app=fake)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(provider_module.httpx, "AsyncClient", local_client)
    media_dir = tmp_path / "media"
    (media_dir / "images").mkdir(parents=True)
    (media_dir / "videos").mkdir(parents=True)
    monkeypatch.setattr(
        storage_module,
        "get_settings",
        lambda: SimpleNamespace(media_dir=media_dir),
    )

    image_provider = MiniMaxImageProvider(
        ProviderConfig(kind="minimax", base_url="http://fake", api_key="key", model="image")
    )
    image_job = await image_provider.submit(
        ImageSpec(
            prompt="雨夜",
            setting="校园",
            composition="远景",
            lighting="月光",
            mood="悬疑",
            art_style="动画",
        )
    )
    path, digest, size = await storage_module.persist_remote_media(
        image_job.result_url or "", "image", "contract"
    )
    assert path.read_bytes() == b"fake-png"
    assert digest
    assert size == 8

    ark_provider = ArkImageProvider(
        ProviderConfig(
            kind="ark",
            base_url="http://fake",
            api_key="key",
            model="doubao-seedream-test",
            extra={"size": "2K"},
        )
    )
    ark_job = await ark_provider.submit(
        ImageSpec(
            prompt="雨夜，16:9",
            character_reference_urls=["data:image/png;base64,ZmFrZQ=="],
            setting="校园",
            composition="远景",
            lighting="月光",
            mood="悬疑",
            art_style="动画",
        )
    )
    assert ark_job.status == "succeeded"
    assert ark_job.result_url == "http://fake/files/frame.png"
    assert ark_requests == [
        {
            "model": "doubao-seedream-test",
            "prompt": "雨夜，16:9",
            "size": "2K",
            "sequential_image_generation": "disabled",
            "stream": False,
            "response_format": "url",
            "watermark": False,
            "image": ["data:image/png;base64,ZmFrZQ=="],
        }
    ]

    video_provider = SeedanceVideoProvider(
        ProviderConfig(
            kind="seedance",
            base_url="http://fake",
            api_key="key",
            model="endpoint",
        )
    )
    queued = await video_provider.submit(
        VideoSpec(
            prompt="镜头推进",
            first_frame_url=image_job.result_url,
            action="回头",
            camera="推进",
            mood="悬疑",
        )
    )
    succeeded = await video_provider.poll(queued)
    assert succeeded.status == "succeeded"
    assert succeeded.result_url == "http://fake/files/video.mp4"

    mode["video"] = "failed"
    failed = await video_provider.poll(queued)
    assert failed.status == "failed"
    assert "moderation_rejected" in str(failed.error)

    mode["video"] = "gateway_timeout"
    with pytest.raises(ProviderError, match="查询失败"):
        await video_provider.poll(queued)
