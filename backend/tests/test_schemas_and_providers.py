from __future__ import annotations

import pytest
from app.schemas import ImageSpec, ProviderConfig, TurnResult, VideoSpec
from app.services.providers import (
    ArkImageProvider,
    MockImageProvider,
    MockTextProvider,
    MockVideoProvider,
    ProviderError,
    create_image_provider,
    create_text_provider,
    create_video_provider,
)
from pydantic import ValidationError


def test_turn_result_requires_exactly_two_distinct_choices() -> None:
    base = {
        "scene": "走廊",
        "narrative": "钟声响起。",
        "dialogue": [],
        "state_delta": {},
        "thread_updates": [],
        "memory_candidates": [],
        "media_brief": {
            "visual_summary": "雨夜走廊",
            "motion": "窗帘轻动",
        },
    }
    with pytest.raises(ValidationError):
        TurnResult.model_validate(
            {**base, "choices": [{"id": "one", "text": "只有一个", "tags": []}]}
        )
    with pytest.raises(ValidationError):
        TurnResult.model_validate(
            {
                **base,
                "choices": [
                    {"id": "one", "text": "相同", "tags": []},
                    {"id": "two", "text": "相同", "tags": []},
                ],
            }
        )


@pytest.mark.asyncio
async def test_mock_provider_contract() -> None:
    text = create_text_provider(
        ProviderConfig(kind="mock", base_url="", model="mock", enabled=True)
    )
    image = create_image_provider(
        ProviderConfig(kind="mock", base_url="", model="mock", enabled=True)
    )
    video = create_video_provider(
        ProviderConfig(kind="mock", base_url="", model="mock", enabled=True)
    )
    assert isinstance(text, MockTextProvider)
    assert isinstance(image, MockImageProvider)
    assert isinstance(video, MockVideoProvider)

    result = await text.generate_structured("system", "第1回合", TurnResult)
    assert isinstance(result, TurnResult)
    image_job = await image.submit(
        ImageSpec(
            prompt="雨夜校园",
            setting="校园",
            composition="远景",
            lighting="月光",
            mood="悬疑",
            art_style="动画",
        )
    )
    assert image_job.status == "succeeded"
    assert image_job.result_url and image_job.result_url.startswith("data:image/svg+xml")
    video_job = await video.submit(
        VideoSpec(
            prompt="缓慢推进",
            first_frame_url=image_job.result_url,
            action="回头",
            camera="推进",
            mood="悬疑",
        )
    )
    assert (await video.poll(video_job)).status == "succeeded"


def test_unknown_provider_is_rejected() -> None:
    config = ProviderConfig(kind="unknown", base_url="", model="unknown")
    with pytest.raises(ProviderError):
        create_image_provider(config)


def test_ark_image_provider_factory() -> None:
    provider = create_image_provider(
        ProviderConfig(
            kind="ark",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="test",
            model="doubao-seedream-test",
        )
    )
    assert isinstance(provider, ArkImageProvider)
