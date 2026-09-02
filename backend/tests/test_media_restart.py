from __future__ import annotations

from copy import deepcopy

import pytest
from app.models import Game, GenerationJob, MediaAsset, StateSnapshot, Turn
from app.schemas import ProviderConfig, ProviderSettings
from app.services import media_worker as worker_module
from app.services.media_worker import MediaWorker
from app.services.memory import DEFAULT_STATE
from app.services.settings_store import ProviderSettingsStore
from app.services.storage import file_data_url
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.mark.asyncio
async def test_running_video_job_resumes_without_regenerating_image(
    db: Session, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_path = tmp_path / "first-frame.svg"
    image_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='9'></svg>",
        encoding="utf-8",
    )
    game = Game(title="恢复测试", premise="测试视频任务恢复")
    db.add(game)
    db.flush()
    snapshot = StateSnapshot(game_id=game.id, data=deepcopy(DEFAULT_STATE))
    db.add(snapshot)
    db.flush()
    turn = Turn(
        game_id=game.id,
        state_snapshot_id=snapshot.id,
        narrative="雨夜",
        scene="旧校舍",
        media_brief={"visual_summary": "旧校舍", "motion": "窗帘轻动"},
        media_status="generating_video",
    )
    db.add(turn)
    db.flush()
    snapshot.turn_id = turn.id
    db.add(
        MediaAsset(
            turn_id=turn.id,
            kind="image",
            provider="mock",
            local_path=str(image_path),
            content_hash="first-frame",
            size_bytes=image_path.stat().st_size,
        )
    )
    job = GenerationJob(
        turn_id=turn.id,
        kind="media_pipeline",
        provider="mock+mock",
        status="running",
        provider_task_id="remote-video-task",
        request_json={
            "phase": "video",
            "provider_task_id": "remote-video-task",
            "provider_progress": 0.4,
        },
    )
    db.add(job)
    db.commit()

    test_sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(worker_module, "SessionLocal", test_sessions)
    config = ProviderConfig(kind="mock", base_url="", model="mock", enabled=True)
    store = ProviderSettingsStore(tmp_path / "providers.json")
    store.save(ProviderSettings(llm=config, image=config, video=config))
    monkeypatch.setattr(worker_module, "provider_settings_store", store)

    def image_should_not_run(_config):  # type: ignore[no-untyped-def]
        raise AssertionError("恢复视频轮询时不应重新生成图片")

    class ResumeVideoProvider:
        async def submit(self, _spec):  # type: ignore[no-untyped-def]
            raise AssertionError("已有供应商任务 ID 时不应重复提交")

        async def poll(self, provider_job):  # type: ignore[no-untyped-def]
            return provider_job.model_copy(
                update={
                    "status": "succeeded",
                    "progress": 1,
                    "result_url": file_data_url(str(image_path)),
                    "metadata": {"mock_image_fallback": True},
                }
            )

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr(worker_module, "create_image_provider", image_should_not_run)
    monkeypatch.setattr(
        worker_module, "create_video_provider", lambda _config: ResumeVideoProvider()
    )
    monkeypatch.setattr(worker_module.asyncio, "sleep", no_wait)

    await MediaWorker()._process(job.id)

    db.expire_all()
    assert db.get(GenerationJob, job.id).status == "succeeded"
    assert db.get(Turn, turn.id).media_status == "ready"
    image_count = db.scalar(
        select(func.count())
        .select_from(MediaAsset)
        .where(MediaAsset.turn_id == turn.id, MediaAsset.kind == "image")
    )
    video_count = db.scalar(
        select(func.count())
        .select_from(MediaAsset)
        .where(MediaAsset.turn_id == turn.id, MediaAsset.kind == "video")
    )
    assert image_count == 1
    assert video_count == 1
