from __future__ import annotations

import base64
import json
import math
import re
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from app.schemas import ImageSpec, ProviderConfig, ProviderJob, VideoSpec


class ProviderError(RuntimeError):
    pass


def _auth_headers(config: ProviderConfig) -> dict[str, str]:
    return {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}


def _join(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


async def _test_ark_connection(config: ProviderConfig) -> None:
    parts = urlsplit(config.base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ProviderError("火山方舟 API 地址无效")
    ping_url = f"{parts.scheme}://{parts.netloc}/ping"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(ping_url, headers=_auth_headers(config))
    if response.is_error:
        raise ProviderError(f"火山方舟连接失败 ({response.status_code}): {response.text[:500]}")


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.S)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


class TextProvider(ABC):
    @abstractmethod
    async def generate_structured(
        self, system_prompt: str, user_prompt: str, schema: type[BaseModel]
    ) -> BaseModel: ...

    @abstractmethod
    async def test(self) -> None: ...


class ImageProvider(ABC):
    @abstractmethod
    async def submit(self, spec: ImageSpec) -> ProviderJob: ...

    async def poll(self, job: ProviderJob) -> ProviderJob:
        return job

    @abstractmethod
    async def test(self) -> None: ...


class VideoProvider(ABC):
    @abstractmethod
    async def submit(self, spec: VideoSpec) -> ProviderJob: ...

    @abstractmethod
    async def poll(self, job: ProviderJob) -> ProviderJob: ...

    @abstractmethod
    async def test(self) -> None: ...


class EmbeddingProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.config.model, "input": texts}
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                _join(self.config.base_url, "/embeddings"),
                headers=_auth_headers(self.config),
                json=payload,
            )
        if response.is_error:
            raise ProviderError(
                f"Embeddings 请求失败 ({response.status_code}): {response.text[:500]}"
            )
        items = sorted(response.json().get("data", []), key=lambda item: item.get("index", 0))
        vectors = [item.get("embedding") for item in items]
        if len(vectors) != len(texts) or any(not isinstance(item, list) for item in vectors):
            raise ProviderError("Embeddings 接口返回数量或结构不正确")
        if any(not all(math.isfinite(float(value)) for value in item) for item in vectors):
            raise ProviderError("Embeddings 接口返回了无效数值")
        return vectors

    async def test(self) -> None:
        vectors = await self.embed(["语义记忆连接测试"])
        if not vectors or not vectors[0]:
            raise ProviderError("Embeddings 接口没有返回向量")


class OpenAITextProvider(TextProvider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    async def generate_structured(
        self, system_prompt: str, user_prompt: str, schema: type[BaseModel]
    ) -> BaseModel:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"{user_prompt}\n\n必须只返回符合以下 JSON Schema 的对象：\n{schema_json}",
                },
            ],
            "temperature": self.config.extra.get("temperature", 0.75),
            "max_tokens": self.config.extra.get("max_tokens", 5000),
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                _join(self.config.base_url, "/chat/completions"),
                headers=_auth_headers(self.config),
                json=payload,
            )
        if response.is_error:
            raise ProviderError(f"LLM 请求失败 ({response.status_code}): {response.text[:500]}")
        body = response.json()
        try:
            content = body["choices"][0]["message"]["content"]
            return schema.model_validate(_extract_json(content))
        except Exception as exc:
            raise ProviderError(f"LLM 返回的结构无法解析: {exc}") from exc

    async def test(self) -> None:
        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": "只回复 OK"}],
            "max_tokens": 8,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                _join(self.config.base_url, "/chat/completions"),
                headers=_auth_headers(self.config),
                json=payload,
            )
        if response.is_error:
            raise ProviderError(response.text[:500])


class OpenAIImageProvider(ImageProvider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    async def submit(self, spec: ImageSpec) -> ProviderJob:
        payload = {
            "model": self.config.model,
            "prompt": spec.prompt,
            "size": self.config.extra.get("size", "1536x1024"),
            "n": 1,
        }
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                _join(self.config.base_url, "/images/generations"),
                headers=_auth_headers(self.config),
                json=payload,
            )
        if response.is_error:
            raise ProviderError(f"图片请求失败 ({response.status_code}): {response.text[:500]}")
        item = response.json()["data"][0]
        if item.get("url"):
            result_url = item["url"]
        elif item.get("b64_json"):
            result_url = f"data:image/png;base64,{item['b64_json']}"
        else:
            raise ProviderError("图片接口没有返回 URL 或 base64")
        return ProviderJob(
            provider_task_id=str(uuid.uuid4()),
            status="succeeded",
            progress=1,
            result_url=result_url,
        )

    async def test(self) -> None:
        if not self.config.api_key or not self.config.base_url or not self.config.model:
            raise ProviderError("请完整填写图片服务地址、模型和密钥")


class ArkImageProvider(ImageProvider):
    """Volcengine Ark Seedream image generation API."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    async def submit(self, spec: ImageSpec) -> ProviderJob:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "prompt": spec.prompt,
            "size": self.config.extra.get("size", "2K"),
            "sequential_image_generation": self.config.extra.get(
                "sequential_image_generation", "disabled"
            ),
            "stream": False,
            "response_format": "url",
            "watermark": bool(self.config.extra.get("watermark", False)),
        }
        if spec.character_reference_urls:
            payload["image"] = spec.character_reference_urls[:3]

        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                _join(self.config.base_url, "/images/generations"),
                headers=_auth_headers(self.config),
                json=payload,
            )
        if response.is_error:
            raise ProviderError(
                f"火山方舟图片请求失败 ({response.status_code}): {response.text[:500]}"
            )

        body = response.json()
        items = body.get("data") or []
        if not items:
            error = body.get("error") or {}
            detail = error.get("message") if isinstance(error, dict) else str(error)
            raise ProviderError(detail or "火山方舟没有返回图片")
        item = items[0]
        if item.get("url"):
            result_url = item["url"]
        elif item.get("b64_json"):
            result_url = f"data:image/png;base64,{item['b64_json']}"
        else:
            raise ProviderError("火山方舟图片响应中没有 URL 或 base64")
        return ProviderJob(
            provider_task_id=str(body.get("created") or uuid.uuid4()),
            status="succeeded",
            progress=1,
            result_url=result_url,
            metadata={"model": body.get("model"), "size": item.get("size")},
        )

    async def test(self) -> None:
        if not self.config.base_url or not self.config.model or not self.config.api_key:
            raise ProviderError("请填写火山方舟地址、Seedream 模型 ID 和 API Key")
        await _test_ark_connection(self.config)


class MiniMaxImageProvider(ImageProvider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    async def submit(self, spec: ImageSpec) -> ProviderJob:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "prompt": spec.prompt,
            "aspect_ratio": "16:9",
            "n": 1,
        }
        refs = spec.character_reference_urls
        if refs:
            payload["subject_reference"] = [
                {"type": "character", "image_file": url} for url in refs[:3]
            ]
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                _join(self.config.base_url, "/v1/image_generation"),
                headers=_auth_headers(self.config),
                json=payload,
            )
        if response.is_error:
            raise ProviderError(f"MiniMax 图片请求失败: {response.text[:500]}")
        body = response.json()
        urls = body.get("data", {}).get("image_urls", [])
        if not urls:
            raise ProviderError(body.get("base_resp", {}).get("status_msg", "未返回图片"))
        return ProviderJob(
            provider_task_id=body.get("id", str(uuid.uuid4())),
            status="succeeded",
            progress=1,
            result_url=urls[0],
        )

    async def test(self) -> None:
        if not self.config.api_key or not self.config.model:
            raise ProviderError("请填写 MiniMax 图片模型和密钥")


class SeedanceVideoProvider(VideoProvider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    async def submit(self, spec: VideoSpec) -> ProviderJob:
        content: list[dict[str, Any]] = [{"type": "text", "text": spec.prompt}]
        if spec.first_frame_url:
            content.append({"type": "image_url", "image_url": {"url": spec.first_frame_url}})
        payload = {
            "model": self.config.model,
            "content": content,
            "ratio": "16:9",
            "resolution": "720p",
            "duration": 6,
            "watermark": False,
            "generate_audio": False,
            "safety_identifier": "local-ai-galgame-user",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                _join(self.config.base_url, "/contents/generations/tasks"),
                headers=_auth_headers(self.config),
                json=payload,
            )
        if response.is_error:
            raise ProviderError(f"Seedance 提交失败: {response.text[:500]}")
        task_id = response.json().get("id")
        if not task_id:
            raise ProviderError("Seedance 没有返回任务 ID")
        return ProviderJob(provider_task_id=task_id, status="queued", progress=0.05)

    async def poll(self, job: ProviderJob) -> ProviderJob:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                _join(self.config.base_url, f"/contents/generations/tasks/{job.provider_task_id}"),
                headers=_auth_headers(self.config),
            )
        if response.is_error:
            raise ProviderError(f"Seedance 查询失败: {response.text[:500]}")
        body = response.json()
        status = str(body.get("status", "running")).lower()
        if status == "succeeded":
            return job.model_copy(
                update={
                    "status": "succeeded",
                    "progress": 1,
                    "result_url": body.get("content", {}).get("video_url"),
                }
            )
        if status in {"failed", "cancelled", "expired"}:
            return job.model_copy(update={"status": "failed", "error": body.get("error", status)})
        return job.model_copy(
            update={"status": "running", "progress": min(job.progress + 0.04, 0.9)}
        )

    async def test(self) -> None:
        if not self.config.api_key or not self.config.model:
            raise ProviderError("请填写 Seedance Endpoint/模型 ID 和 API Key")
        await _test_ark_connection(self.config)


class MiniMaxVideoProvider(VideoProvider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    async def submit(self, spec: VideoSpec) -> ProviderJob:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "prompt": spec.prompt,
            "duration": 6,
            "resolution": self.config.extra.get("resolution", "768P"),
        }
        if spec.first_frame_url:
            payload["first_frame_image"] = spec.first_frame_url
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                _join(self.config.base_url, "/v1/video_generation"),
                headers=_auth_headers(self.config),
                json=payload,
            )
        if response.is_error:
            raise ProviderError(f"MiniMax 视频提交失败: {response.text[:500]}")
        body = response.json()
        task_id = body.get("task_id")
        if not task_id:
            raise ProviderError(body.get("base_resp", {}).get("status_msg", "未返回任务 ID"))
        return ProviderJob(provider_task_id=task_id, status="queued", progress=0.05)

    async def poll(self, job: ProviderJob) -> ProviderJob:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                _join(self.config.base_url, "/v1/query/video_generation"),
                headers=_auth_headers(self.config),
                params={"task_id": job.provider_task_id},
            )
        if response.is_error:
            raise ProviderError(f"MiniMax 视频查询失败: {response.text[:500]}")
        body = response.json()
        status = body.get("status")
        if status == "Success":
            file_id = body.get("file_id")
            async with httpx.AsyncClient(timeout=60) as client:
                file_response = await client.get(
                    _join(self.config.base_url, "/v1/files/retrieve"),
                    headers=_auth_headers(self.config),
                    params={"file_id": file_id},
                )
            if file_response.is_error:
                raise ProviderError(f"MiniMax 文件查询失败: {file_response.text[:500]}")
            file_body = file_response.json()
            url = file_body.get("file", {}).get("download_url") or file_body.get("download_url")
            return job.model_copy(update={"status": "succeeded", "progress": 1, "result_url": url})
        if status == "Fail":
            return job.model_copy(
                update={"status": "failed", "error": body.get("base_resp", {}).get("status_msg")}
            )
        return job.model_copy(
            update={"status": "running", "progress": min(job.progress + 0.04, 0.9)}
        )

    async def test(self) -> None:
        if not self.config.api_key or not self.config.model:
            raise ProviderError("请填写 MiniMax 视频模型和密钥")


class MockTextProvider(TextProvider):
    async def generate_structured(
        self, system_prompt: str, user_prompt: str, schema: type[BaseModel]
    ) -> BaseModel:
        from app.schemas import TurnResult

        if schema is TurnResult:
            turn_number = len(re.findall("回合", user_prompt)) + 1
            return TurnResult.model_validate(
                {
                    "scene": "放学后的樱花步道",
                    "narrative": f"夕阳落在樱花步道上。第{turn_number}次并肩走过这里时，林澄放慢脚步，把相机里刚拍下的照片递给你看。",
                    "dialogue": [
                        {
                            "speaker": "林澄",
                            "text": "这一张有你喜欢的感觉吗？我想把它放进春季展。",
                            "emotion": "期待",
                        }
                    ],
                    "choices": [
                        {
                            "id": "choose_photo",
                            "text": "陪林澄一起挑选春季展的照片",
                            "tags": ["陪伴", "温柔"],
                        },
                        {
                            "id": "invite_walk",
                            "text": "邀请林澄拍完后一起绕操场散步",
                            "tags": ["主动", "浪漫"],
                        },
                    ],
                    "state_delta": {"location": "樱花步道", "time": "放学后"},
                    "thread_updates": [
                        {
                            "id": "spring-photo-exhibition",
                            "action": "advance",
                            "summary": "和林澄一起准备摄影社春季展",
                        }
                    ],
                    "memory_candidates": [
                        {
                            "content": "林澄邀请玩家一起挑选春季展照片",
                            "importance": 0.7,
                            "tags": ["林澄", "摄影社", "春季展"],
                        }
                    ],
                    "media_brief": {
                        "visual_summary": "放学后的校园樱花步道，黑发少女林澄拿着相机向第一视角展示照片，夕阳温暖",
                        "motion": "少女轻轻递出相机，花瓣掠过发梢，她抬眼露出期待的笑",
                        "camera": "gentle first-person medium shot",
                        "mood": "warm, youthful, romantic",
                        "visible_characters": ["林澄"],
                    },
                }
            )
        raise ProviderError(f"Mock provider 不支持 schema {schema.__name__}")

    async def test(self) -> None:
        return None


class MockImageProvider(ImageProvider):
    async def submit(self, spec: ImageSpec) -> ProviderJob:
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720'>"
            "<rect width='1280' height='720' fill='#17192a'/><circle cx='860' cy='290' r='150' fill='#9da4ff'/>"
            "<text x='80' y='620' fill='white' font-size='42'>AI Galgame Mock Scene</text></svg>"
        )
        encoded = base64.b64encode(svg.encode()).decode()
        return ProviderJob(
            provider_task_id=str(uuid.uuid4()),
            status="succeeded",
            progress=1,
            result_url=f"data:image/svg+xml;base64,{encoded}",
        )

    async def test(self) -> None:
        return None


class MockVideoProvider(VideoProvider):
    async def submit(self, spec: VideoSpec) -> ProviderJob:
        return ProviderJob(
            provider_task_id=str(uuid.uuid4()),
            status="succeeded",
            progress=1,
            result_url=spec.first_frame_url,
            metadata={"mock_image_fallback": True},
        )

    async def poll(self, job: ProviderJob) -> ProviderJob:
        return job

    async def test(self) -> None:
        return None


def create_text_provider(config: ProviderConfig) -> TextProvider:
    if config.kind == "mock":
        return MockTextProvider()
    if config.kind in {"openai", "minicpm"}:
        return OpenAITextProvider(config)
    raise ProviderError(f"不支持的文本供应商: {config.kind}")


def create_image_provider(config: ProviderConfig) -> ImageProvider:
    if config.kind == "mock":
        return MockImageProvider()
    if config.kind == "ark":
        return ArkImageProvider(config)
    if config.kind == "minimax":
        return MiniMaxImageProvider(config)
    if config.kind == "openai":
        return OpenAIImageProvider(config)
    raise ProviderError(f"不支持的图片供应商: {config.kind}")


def create_video_provider(config: ProviderConfig) -> VideoProvider:
    if config.kind == "mock":
        return MockVideoProvider()
    if config.kind == "seedance":
        return SeedanceVideoProvider(config)
    if config.kind == "minimax":
        return MiniMaxVideoProvider(config)
    raise ProviderError(f"不支持的视频供应商: {config.kind}")


def create_embedding_provider(config: ProviderConfig) -> EmbeddingProvider:
    if config.kind in {"openai", "minicpm"}:
        return EmbeddingProvider(config)
    raise ProviderError(f"不支持的 Embeddings 供应商: {config.kind}")


async def test_provider(config: ProviderConfig, category: str) -> int:
    started = time.perf_counter()
    if category == "llm":
        await create_text_provider(config).test()
    elif category == "image":
        await create_image_provider(config).test()
    elif category == "video":
        await create_video_provider(config).test()
    elif category == "embedding":
        await create_embedding_provider(config).test()
    else:
        raise ProviderError(f"未知供应商类别: {category}")
    return int((time.perf_counter() - started) * 1000)
