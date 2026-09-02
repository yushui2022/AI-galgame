from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import GenerationJob, MediaAsset, PlayerProfile, Turn
from app.schemas import ProviderJob

from .events import event_broker
from .orchestrator import story_orchestrator
from .providers import ProviderError, create_image_provider, create_video_provider
from .settings_store import provider_settings_store
from .storage import file_data_url, media_url, persist_remote_media

logger = logging.getLogger(__name__)


class MediaWorker:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task:
            return
        with SessionLocal() as db:
            jobs = db.scalars(
                select(GenerationJob).where(GenerationJob.status.in_(["queued", "running"]))
            ).all()
            for job in jobs:
                job.status = "queued"
                await self.queue.put(job.id)
            db.commit()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def enqueue_turn(self, turn_id: str) -> GenerationJob:
        with SessionLocal() as db:
            turn = db.get(Turn, turn_id)
            if not turn:
                raise ValueError("回合不存在")
            settings = provider_settings_store.load()
            job = GenerationJob(
                turn_id=turn_id,
                kind="media_pipeline",
                provider=f"{settings.image.kind}+{settings.video.kind}",
                status="queued",
                request_json={"phase": "image"},
            )
            db.add(job)
            db.commit()
            db.refresh(job)
        await self.queue.put(job.id)
        await event_broker.publish("media.queued", {"turn_id": turn_id, "job_id": job.id})
        return job

    async def retry(self, turn_id: str) -> GenerationJob:
        with SessionLocal() as db:
            turn = db.get(Turn, turn_id)
            if not turn:
                raise ValueError("回合不存在")
            turn.media_status = "queued"
            turn.unlocked = False
            db.commit()
        return await self.enqueue_turn(turn_id)

    async def _run(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                await self._process(job_id)
            except Exception:
                logger.exception("media_job_unhandled job=%s", job_id)
            finally:
                self.queue.task_done()

    async def _process(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(GenerationJob, job_id)
            if not job or not job.turn_id:
                return
            turn = db.get(Turn, job.turn_id)
            if not turn:
                return
            job.status = "running"
            job.attempts += 1
            resume_video = job.request_json.get("phase") == "video"
            turn.media_status = "generating_video" if resume_video else "generating_image"
            db.commit()
            image_spec, video_spec = story_orchestrator.media_specs(db, turn)
            turn_id = turn.id
            attempts = job.attempts
            request_json = dict(job.request_json)
            existing_image = next(
                (asset for asset in reversed(turn.media_assets) if asset.kind == "image"), None
            )

        settings = provider_settings_store.load()
        try:
            if resume_video:
                if not existing_image or not existing_image.local_path:
                    raise ProviderError("恢复视频任务时找不到已生成的首帧")
                image_path = Path(existing_image.local_path)
                digest = existing_image.content_hash or ""
                size = existing_image.size_bytes
                first_frame_url = request_json.get("image_url") or file_data_url(
                    existing_image.local_path
                )
            else:
                if attempts > 1:
                    image_spec.prompt += " Simplify the composition and keep all people fully clothed in a clearly SFW scene."
                image_provider = create_image_provider(settings.image)
                image_job = await image_provider.submit(image_spec)
                while image_job.status in {"queued", "running"}:
                    await asyncio.sleep(3)
                    image_job = await image_provider.poll(image_job)
                if image_job.status != "succeeded" or not image_job.result_url:
                    raise ProviderError(image_job.error or "图片生成失败")
                image_path, digest, size = await persist_remote_media(
                    image_job.result_url, "image", turn_id
                )
                first_frame_url = image_job.result_url
                with SessionLocal() as db:
                    turn = db.get(Turn, turn_id)
                    job = db.get(GenerationJob, job_id)
                    if not turn or not job:
                        return
                    asset = MediaAsset(
                        turn_id=turn_id,
                        kind="image",
                        provider=settings.image.kind,
                        local_path=str(image_path),
                        remote_url=(
                            image_job.result_url
                            if image_job.result_url.startswith("http")
                            else None
                        ),
                        content_hash=digest,
                        size_bytes=size,
                    )
                    db.add(asset)
                    turn.media_status = "generating_video"
                    job.progress = 0.45
                    job.request_json = {"phase": "video", "image_url": image_job.result_url}
                    db.commit()
                await event_broker.publish(
                    "media.image_ready",
                    {"turn_id": turn_id, "url": media_url(str(image_path))},
                )

            video_spec.first_frame_url = first_frame_url
            if attempts > 1:
                video_spec.prompt += (
                    " Keep motion subtle, preserve the first frame, and keep the scene clearly SFW."
                )
            video_provider = create_video_provider(settings.video)
            if resume_video and request_json.get("provider_task_id"):
                video_job = ProviderJob(
                    provider_task_id=request_json["provider_task_id"],
                    status="running",
                    progress=max(0.05, float(request_json.get("provider_progress", 0.05))),
                )
            else:
                video_job = await video_provider.submit(video_spec)
                with SessionLocal() as db:
                    job = db.get(GenerationJob, job_id)
                    if job:
                        job.provider_task_id = video_job.provider_task_id
                        job.progress = 0.5
                        job.request_json = {
                            **job.request_json,
                            "phase": "video",
                            "provider_task_id": video_job.provider_task_id,
                            "provider_progress": video_job.progress,
                        }
                        db.commit()
            polls = 0
            while video_job.status in {"queued", "running"} and polls < 720:
                await asyncio.sleep(5)
                video_job = await video_provider.poll(video_job)
                polls += 1
                with SessionLocal() as db:
                    job = db.get(GenerationJob, job_id)
                    if job:
                        job.progress = 0.5 + video_job.progress * 0.45
                        job.request_json = {
                            **job.request_json,
                            "provider_progress": video_job.progress,
                        }
                        db.commit()
                await event_broker.publish(
                    "media.progress",
                    {"turn_id": turn_id, "progress": 0.5 + video_job.progress * 0.45},
                )
            if video_job.status != "succeeded" or not video_job.result_url:
                if video_job.status == "failed":
                    with SessionLocal() as db:
                        job = db.get(GenerationJob, job_id)
                        if job:
                            job.provider_task_id = None
                            job.request_json = {
                                **job.request_json,
                                "provider_task_id": None,
                                "provider_progress": 0,
                            }
                            db.commit()
                raise ProviderError(video_job.error or "视频生成超时或失败")

            if video_job.metadata.get("mock_image_fallback"):
                video_path, digest, size = image_path, digest, size
            else:
                video_path, digest, size = await persist_remote_media(
                    video_job.result_url, "video", turn_id
                )
            with SessionLocal() as db:
                turn = db.get(Turn, turn_id)
                job = db.get(GenerationJob, job_id)
                if not turn or not job:
                    return
                db.add(
                    MediaAsset(
                        turn_id=turn_id,
                        kind="video",
                        provider=settings.video.kind,
                        local_path=str(video_path),
                        remote_url=(
                            video_job.result_url
                            if video_job.result_url.startswith("http")
                            else None
                        ),
                        content_hash=digest,
                        size_bytes=size,
                        metadata_json=video_job.metadata,
                    )
                )
                turn.media_status = "ready"
                job.status = "succeeded"
                job.progress = 1
                job.result_json = {"video_url": media_url(str(video_path))}
                db.commit()
            await event_broker.publish(
                "media.video_ready", {"turn_id": turn_id, "url": media_url(str(video_path))}
            )
        except Exception as exc:
            logger.warning("media_job_failed job=%s error=%s", job_id, exc)
            with SessionLocal() as db:
                job = db.get(GenerationJob, job_id)
                turn = db.get(Turn, turn_id)
                if not job or not turn:
                    return
                job.error = str(exc)
                if job.attempts < 3:
                    job.status = "queued"
                    turn.media_status = "retrying"
                    db.commit()
                    await asyncio.sleep(2)
                    await self.queue.put(job.id)
                else:
                    job.status = "failed"
                    turn.media_status = "failed"
                    db.commit()
                    await event_broker.publish(
                        "media.failed", {"turn_id": turn_id, "error": str(exc)}
                    )


def unlock_turn(turn_id: str, watched: bool) -> None:
    with SessionLocal() as db:
        turn = db.get(Turn, turn_id)
        if not turn:
            raise ValueError("回合不存在")
        if turn.unlocked:
            return
        turn.unlocked = True
        profile = db.get(PlayerProfile, "default")
        if not profile:
            profile = PlayerProfile(id="default", watched_videos=0, skipped_videos=0)
            db.add(profile)
        if watched:
            profile.watched_videos += 1
        else:
            profile.skipped_videos += 1
        db.commit()


media_worker = MediaWorker()
