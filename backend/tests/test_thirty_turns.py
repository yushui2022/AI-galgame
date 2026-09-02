from __future__ import annotations

from copy import deepcopy

import pytest
from app.models import Branch, Game, PlayerProfile, RollingSummary, StateSnapshot, Turn
from app.schemas import ProviderConfig, ProviderSettings, TurnRequest
from app.services.memory import DEFAULT_STATE, lineage
from app.services.orchestrator import story_orchestrator
from app.services.settings_store import ProviderSettingsStore
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.mark.asyncio
async def test_thirty_turns_with_periodic_forks(
    db: Session, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = ProviderConfig(kind="mock", base_url="", model="mock", enabled=True)
    store = ProviderSettingsStore(tmp_path / "providers.json")
    store.save(ProviderSettings(llm=mock, image=mock, video=mock))
    monkeypatch.setattr("app.services.orchestrator.provider_settings_store", store)

    game = Game(title="旧校舍", premise="雨夜校园谜案", world_rules="事实必须连续")
    db.add(game)
    db.flush()
    snapshot = StateSnapshot(game_id=game.id, data=deepcopy(DEFAULT_STATE))
    db.add(snapshot)
    db.flush()
    root = Turn(
        game_id=game.id,
        state_snapshot_id=snapshot.id,
        turn_index=0,
        scene="门厅",
        narrative="收到失踪学姐的短信。",
        choices=[
            {"id": "inspect", "text": "继续调查", "tags": ["调查"]},
            {"id": "comfort", "text": "安慰林澄", "tags": ["关系"]},
        ],
        unlocked=True,
    )
    db.add(root)
    db.flush()
    snapshot.turn_id = root.id
    branch = Branch(game_id=game.id, name="主线", head_turn_id=root.id)
    db.add(branch)
    db.commit()

    forks: list[Branch] = []
    for index in range(30):
        current_id = branch.head_turn_id
        turn = await story_orchestrator.create_turn(
            db,
            branch,
            TurnRequest(
                input_type="suggested",
                text="继续调查",
                choice_id="inspect",
                expected_head_turn_id=current_id,
            ),
        )
        turn.unlocked = True
        db.commit()
        if (index + 1) % 5 == 0:
            fork = Branch(
                game_id=game.id,
                name=f"第{index + 1}回合分支",
                head_turn_id=turn.id,
            )
            db.add(fork)
            db.commit()
            forks.append(fork)

    assert len(lineage(db, branch.head_turn_id)) == 31
    assert len(forks) == 6
    assert all(len(lineage(db, item.head_turn_id)) <= 31 for item in forks)
    summary = db.scalar(select(RollingSummary).where(RollingSummary.branch_id == branch.id))
    assert summary and summary.turn_count == 30
    profile = db.get(PlayerProfile, "default")
    assert profile and profile.choice_tendencies["调查"] == pytest.approx(3.0)
