from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Branch, GenerationJob, MediaAsset, MemoryRecord, StateSnapshot, Turn
from app.schemas import (
    BranchRead,
    ForkRequest,
    RenameBranchRequest,
    TurnRead,
    TurnRequest,
    TurnSubmission,
)
from app.services.events import event_broker
from app.services.media_worker import media_worker, unlock_turn
from app.services.memory import lineage
from app.services.orchestrator import story_orchestrator
from app.services.providers import ProviderError

from .serializers import turn_read

router = APIRouter(prefix="/api", tags=["gameplay"])


@router.get("/games/{game_id}/branches", response_model=list[BranchRead])
def list_branches(game_id: str, db: Session = Depends(get_db)) -> list[Branch]:
    return list(
        db.scalars(
            select(Branch)
            .where(Branch.game_id == game_id)
            .order_by(Branch.archived, Branch.updated_at.desc())
        ).all()
    )


@router.get("/branches/{branch_id}/turns", response_model=list[TurnRead])
def branch_turns(branch_id: str, db: Session = Depends(get_db)) -> list[TurnRead]:
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="分支不存在")
    turns = lineage(db, branch.head_turn_id)
    for turn in turns:
        _ = turn.media_assets
    return [turn_read(turn) for turn in turns]


@router.post("/branches/{branch_id}/turns", response_model=TurnSubmission)
async def submit_turn(
    branch_id: str, payload: TurnRequest, db: Session = Depends(get_db)
) -> TurnSubmission:
    branch = db.get(Branch, branch_id)
    if not branch or branch.archived:
        raise HTTPException(status_code=404, detail="分支不存在或已归档")
    head = db.get(Turn, branch.head_turn_id) if branch.head_turn_id else None
    if head and not head.unlocked:
        raise HTTPException(status_code=409, detail="请等待当前视频完成或选择跳过")
    try:
        turn = await story_orchestrator.create_turn(db, branch, payload)
        job = await media_worker.enqueue_turn(turn.id)
        await event_broker.publish(
            "turn.created", {"branch_id": branch_id, "turn_id": turn.id, "index": turn.turn_index}
        )
        return TurnSubmission(turn=turn_read(turn), job_id=job.id)
    except (ValueError, ProviderError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/branches/{branch_id}/fork", response_model=BranchRead)
def fork_branch(branch_id: str, payload: ForkRequest, db: Session = Depends(get_db)) -> Branch:
    source = db.get(Branch, branch_id)
    turn = db.get(Turn, payload.turn_id)
    if not source or not turn or turn.game_id != source.game_id:
        raise HTTPException(status_code=404, detail="分支或历史节点不存在")
    allowed_ids = {item.id for item in lineage(db, source.head_turn_id)}
    if turn.id not in allowed_ids:
        raise HTTPException(status_code=400, detail="只能从当前分支的历史节点分叉")
    branch = Branch(
        game_id=source.game_id,
        name=payload.name or f"分支 · 第{turn.turn_index}回合",
        head_turn_id=turn.id,
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


@router.put("/branches/{branch_id}", response_model=BranchRead)
def rename_branch(
    branch_id: str, payload: RenameBranchRequest, db: Session = Depends(get_db)
) -> Branch:
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="分支不存在")
    branch.name = payload.name
    db.commit()
    db.refresh(branch)
    return branch


@router.delete("/branches/{branch_id}", response_model=BranchRead)
def archive_branch(branch_id: str, db: Session = Depends(get_db)) -> Branch:
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="分支不存在")
    branch.archived = True
    db.commit()
    db.refresh(branch)
    return branch


@router.post("/branches/{branch_id}/restore", response_model=BranchRead)
def restore_branch(branch_id: str, db: Session = Depends(get_db)) -> Branch:
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="分支不存在")
    branch.archived = False
    db.commit()
    db.refresh(branch)
    return branch


@router.delete("/branches/{branch_id}/purge")
def purge_branch(
    branch_id: str,
    confirm: bool = Query(False),
    db: Session = Depends(get_db),
):  # type: ignore[no-untyped-def]
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="分支不存在")
    if not confirm:
        raise HTTPException(status_code=400, detail="永久清理需要显式确认")
    if not branch.archived:
        raise HTTPException(status_code=409, detail="只能永久清理已经归档的分支")
    remaining = db.scalars(
        select(Branch).where(Branch.game_id == branch.game_id, Branch.id != branch.id)
    ).all()
    if not remaining:
        raise HTTPException(status_code=409, detail="游戏至少需要保留一条分支")

    candidate_turns = lineage(db, branch.head_turn_id)
    retained_ids: set[str] = set()
    for item in remaining:
        retained_ids.update(turn.id for turn in lineage(db, item.head_turn_id))
    orphan_turns = [turn for turn in candidate_turns if turn.id not in retained_ids]
    orphan_ids = {turn.id for turn in orphan_turns}
    media_count = (
        db.scalar(
            select(func.count()).select_from(MediaAsset).where(MediaAsset.turn_id.in_(orphan_ids))
        )
        if orphan_ids
        else 0
    )
    memory_ids = (
        db.scalars(select(MemoryRecord.id).where(MemoryRecord.source_turn_id.in_(orphan_ids))).all()
        if orphan_ids
        else []
    )
    if memory_ids:
        for memory_id in memory_ids:
            db.execute(
                text("DELETE FROM memory_fts WHERE memory_id = :memory_id"),
                {"memory_id": memory_id},
            )

    db.delete(branch)
    db.flush()
    snapshot_ids = [turn.state_snapshot_id for turn in orphan_turns]
    for turn in sorted(orphan_turns, key=lambda item: item.turn_index, reverse=True):
        db.delete(turn)
        db.flush()
    if snapshot_ids:
        db.execute(delete(StateSnapshot).where(StateSnapshot.id.in_(snapshot_ids)))
    db.commit()
    return {"ok": True, "deleted_turns": len(orphan_turns), "deleted_media": media_count or 0}


@router.post("/turns/{turn_id}/media/retry")
async def retry_media(turn_id: str):  # type: ignore[no-untyped-def]
    try:
        job = await media_worker.retry(turn_id)
        return {"job_id": job.id, "status": job.status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/turns/{turn_id}/media/skip")
async def skip_media(turn_id: str):  # type: ignore[no-untyped-def]
    try:
        unlock_turn(turn_id, watched=False)
        await event_broker.publish("turn.unlocked", {"turn_id": turn_id, "reason": "skipped"})
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/turns/{turn_id}/media/complete")
async def complete_media(turn_id: str):  # type: ignore[no-untyped-def]
    try:
        unlock_turn(turn_id, watched=True)
        await event_broker.publish("turn.unlocked", {"turn_id": turn_id, "reason": "watched"})
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):  # type: ignore[no-untyped-def]
    job = db.get(GenerationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "id": job.id,
        "turn_id": job.turn_id,
        "kind": job.kind,
        "provider": job.provider,
        "status": job.status,
        "progress": job.progress,
        "attempts": job.attempts,
        "error": job.error,
    }
