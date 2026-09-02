from __future__ import annotations

from copy import deepcopy

from app.api.gameplay import purge_branch
from app.models import (
    Branch,
    Game,
    MediaAsset,
    RollingSummary,
    StateSnapshot,
    Turn,
)
from app.schemas import MemoryCandidate
from app.services.memory import (
    DEFAULT_STATE,
    apply_thread_updates,
    compile_context,
    lineage,
    merge_state,
    persist_memories,
    refresh_summary,
    retrieve_memories,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def add_turn(
    db: Session,
    game: Game,
    parent: Turn | None,
    narrative: str,
    location: str = "旧校舍",
) -> Turn:
    state = deepcopy(parent.snapshot.data if parent else DEFAULT_STATE)
    state["location"] = location
    snapshot = StateSnapshot(game_id=game.id, data=state)
    db.add(snapshot)
    db.flush()
    turn = Turn(
        game_id=game.id,
        parent_turn_id=parent.id if parent else None,
        state_snapshot_id=snapshot.id,
        turn_index=(parent.turn_index + 1) if parent else 0,
        narrative=narrative,
        scene=location,
        choices=[
            {"id": "a", "text": "继续调查", "tags": ["调查"]},
            {"id": "b", "text": "离开现场", "tags": ["谨慎"]},
        ],
        unlocked=True,
    )
    db.add(turn)
    db.flush()
    snapshot.turn_id = turn.id
    return turn


def test_state_delta_and_thread_limits() -> None:
    state = merge_state(
        DEFAULT_STATE,
        {
            "location": "钟楼",
            "relationships": {"林澄": 12},
            "unexpected_system_field": "ignored",
        },
    )
    assert state["location"] == "钟楼"
    assert state["relationships"]["林澄"] == 12
    assert "unexpected_system_field" not in state

    updated = apply_thread_updates(
        state,
        [
            {"id": "first", "action": "open", "summary": "第一条新线索"},
            {"id": "second", "action": "open", "summary": "本回合不应再新增"},
            {
                "id": "missing-senior-message",
                "action": "advance",
                "summary": "短信来自旧校舍的离线终端",
            },
        ],
    )
    ids = {item["id"] for item in updated["open_threads"]}
    assert "first" in ids
    assert "second" not in ids
    advanced = next(
        item for item in updated["open_threads"] if item["id"] == "missing-senior-message"
    )
    assert advanced["progress"] == 25


def test_branch_ancestor_memory_isolation_and_shared_media(db: Session) -> None:
    game = Game(title="测试", premise="一场雨夜调查")
    db.add(game)
    db.flush()
    root = add_turn(db, game, None, "雨夜收到短信")
    main_turn = add_turn(db, game, root, "主线发现红色钥匙")
    fork_turn = add_turn(db, game, root, "分支发现蓝色磁带")
    main = Branch(game_id=game.id, name="主线", head_turn_id=main_turn.id)
    fork = Branch(game_id=game.id, name="分支", head_turn_id=fork_turn.id)
    db.add_all([main, fork])
    db.add(
        MediaAsset(
            turn_id=root.id,
            kind="image",
            provider="mock",
            content_hash="shared-root",
            size_bytes=20,
        )
    )
    persist_memories(
        db,
        game.id,
        main_turn.id,
        [MemoryCandidate(content="主线持有红色钥匙", tags=["钥匙"], importance=0.9)],
    )
    persist_memories(
        db,
        game.id,
        fork_turn.id,
        [MemoryCandidate(content="分支持有蓝色磁带", tags=["磁带"], importance=0.9)],
    )
    db.commit()

    main_ids = {turn.id for turn in lineage(db, main.head_turn_id)}
    recalled = retrieve_memories(db, game.id, main_ids, "钥匙 磁带", limit=4)
    assert [item.content for item in recalled] == ["主线持有红色钥匙"]
    assert lineage(db, main.head_turn_id)[0].media_assets[0].content_hash == "shared-root"
    assert lineage(db, fork.head_turn_id)[0].media_assets[0].content_hash == "shared-root"
    assert db.scalar(select(MediaAsset).where(MediaAsset.content_hash == "shared-root")) is not None


def test_summary_updates_every_five_lineage_nodes(db: Session) -> None:
    game = Game(title="测试", premise="连续故事")
    db.add(game)
    db.flush()
    head: Turn | None = None
    for index in range(5):
        head = add_turn(db, game, head, f"第{index}段剧情")
    assert head
    branch = Branch(game_id=game.id, name="主线", head_turn_id=head.id)
    db.add(branch)
    db.flush()
    refresh_summary(db, branch)
    db.commit()
    summary = db.scalar(select(RollingSummary).where(RollingSummary.branch_id == branch.id))
    assert summary
    assert summary.turn_count == 5
    assert "第4段剧情" in summary.content


def test_purge_archived_branch_only_deletes_unshared_suffix(db: Session) -> None:
    game = Game(title="清理测试", premise="分支媒体引用")
    db.add(game)
    db.flush()
    root = add_turn(db, game, None, "公共开场")
    main_turn = add_turn(db, game, root, "主线后续")
    orphan_turn = add_turn(db, game, root, "归档分支后续")
    main = Branch(game_id=game.id, name="主线", head_turn_id=main_turn.id)
    archived = Branch(
        game_id=game.id,
        name="旧分支",
        head_turn_id=orphan_turn.id,
        archived=True,
    )
    db.add_all([main, archived])
    db.add_all(
        [
            MediaAsset(
                turn_id=root.id,
                kind="image",
                provider="mock",
                content_hash="shared",
                size_bytes=10,
            ),
            MediaAsset(
                turn_id=orphan_turn.id,
                kind="video",
                provider="mock",
                content_hash="orphan",
                size_bytes=20,
            ),
        ]
    )
    db.commit()

    result = purge_branch(archived.id, confirm=True, db=db)

    assert result == {"ok": True, "deleted_turns": 1, "deleted_media": 1}
    assert db.get(Turn, root.id) is not None
    assert db.get(Turn, main_turn.id) is not None
    assert db.get(Turn, orphan_turn.id) is None
    assert db.scalar(select(MediaAsset).where(MediaAsset.content_hash == "shared")) is not None
    assert db.scalar(select(MediaAsset).where(MediaAsset.content_hash == "orphan")) is None


def test_context_builder_respects_budget(db: Session) -> None:
    game = Game(
        title="预算测试",
        premise="世界设定" * 5000,
        world_rules="规则" * 8000,
        art_style="画风" * 2000,
    )
    db.add(game)
    db.flush()
    head: Turn | None = None
    for index in range(8):
        head = add_turn(db, game, head, f"第{index}回合" + "长剧情" * 3000)
    assert head
    head.snapshot.data = {
        **deepcopy(DEFAULT_STATE),
        "clues": ["非常长的线索" * 1000 for _ in range(30)],
        "world_flags": {f"flag-{index}": "状态" * 1000 for index in range(40)},
    }
    branch = Branch(game_id=game.id, name="主线", head_turn_id=head.id)
    db.add(branch)
    db.commit()

    context = compile_context(db, game, branch, "继续调查" * 1000)

    assert len(context) <= 32_000
    assert "canonical_state" in context
    assert "attempted_action" in context
