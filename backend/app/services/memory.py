from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (
    Branch,
    Game,
    LoreEntry,
    MemoryRecord,
    PlayerProfile,
    RollingSummary,
    Turn,
)
from app.schemas import MemoryCandidate, PlayerProfileData

DEFAULT_STATE: dict[str, Any] = {
    "location": "校门口的樱花树下",
    "time": "新学期清晨",
    "character_status": {},
    "relationships": {"林澄": 0, "夏栀": 0, "苏晚": 0},
    "clues": [],
    "inventory": [],
    "world_flags": {},
    "promises": [],
    "open_threads": [
        {
            "id": "spring-photo-exhibition",
            "summary": "帮助林澄准备摄影社春季展",
            "status": "open",
            "progress": 0,
        }
    ],
}
MAX_CONTEXT_CHARS = 32_000


def _clip(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _compact_value(
    value: Any, string_limit: int = 1200, list_limit: int = 20, dict_limit: int = 30
) -> Any:
    if isinstance(value, str):
        return _clip(value, string_limit)
    if isinstance(value, list):
        return [
            _compact_value(item, string_limit, list_limit, dict_limit)
            for item in value[-list_limit:]
        ]
    if isinstance(value, dict):
        return {
            key: _compact_value(item, string_limit, list_limit, dict_limit)
            for key, item in list(value.items())[-dict_limit:]
        }
    return value


def _compact_state(state: dict[str, Any]) -> dict[str, Any]:
    return {key: _compact_value(value) for key, value in state.items()}


def ensure_profile(db: Session) -> PlayerProfile:
    profile = db.get(PlayerProfile, "default")
    if not profile:
        profile = PlayerProfile(id="default")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def profile_to_schema(profile: PlayerProfile) -> PlayerProfileData:
    return PlayerProfileData(
        preferred_themes=profile.preferred_themes,
        preferred_character_traits=profile.preferred_character_traits,
        pacing=profile.pacing,
        choice_tendencies=profile.choice_tendencies,
        character_affinities=profile.character_affinities,
        watched_videos=profile.watched_videos,
        skipped_videos=profile.skipped_videos,
        notes=profile.notes,
    )


def lineage(db: Session, head_turn_id: str | None, limit: int | None = None) -> list[Turn]:
    turns: list[Turn] = []
    current_id = head_turn_id
    while current_id and (limit is None or len(turns) < limit):
        current = db.get(Turn, current_id)
        if not current:
            break
        turns.append(current)
        current_id = current.parent_turn_id
    turns.reverse()
    return turns


def _keywords(query: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,8}", query)
    return list(dict.fromkeys(words))[:8]


def triggered_lore(db: Session, game_id: str, query: str) -> list[LoreEntry]:
    entries = db.scalars(
        select(LoreEntry).where(LoreEntry.game_id == game_id).order_by(LoreEntry.priority.desc())
    ).all()
    lowered = query.lower()
    return [
        entry
        for entry in entries
        if entry.always_on or any(keyword.lower() in lowered for keyword in entry.keywords)
    ][:8]


def retrieve_memories(
    db: Session,
    game_id: str,
    allowed_turn_ids: set[str],
    query: str,
    limit: int = 4,
    query_embedding: list[float] | None = None,
) -> list[MemoryRecord]:
    found_ids: list[str] = []
    terms = _keywords(query)
    if terms:
        match_query = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)
        try:
            rows = db.execute(
                text(
                    "SELECT memory_id FROM memory_fts "
                    "WHERE game_id=:game_id AND memory_fts MATCH :query LIMIT :limit"
                ),
                {"game_id": game_id, "query": match_query, "limit": limit * 3},
            ).all()
            found_ids = [row[0] for row in rows]
        except Exception:
            found_ids = []

    records: list[MemoryRecord] = []
    if found_ids:
        records = list(db.scalars(select(MemoryRecord).where(MemoryRecord.id.in_(found_ids))).all())
    if len(records) < limit:
        recent = db.scalars(
            select(MemoryRecord)
            .where(MemoryRecord.game_id == game_id)
            .order_by(MemoryRecord.importance.desc(), MemoryRecord.created_at.desc())
            .limit(limit * 3)
        ).all()
        seen = {record.id for record in records}
        records.extend(record for record in recent if record.id not in seen)
    records = [record for record in records if record.source_turn_id in allowed_turn_ids]
    if query_embedding:
        semantic_pool = db.scalars(
            select(MemoryRecord).where(
                MemoryRecord.game_id == game_id,
                MemoryRecord.source_turn_id.in_(allowed_turn_ids),
                MemoryRecord.embedding.is_not(None),
            )
        ).all()

        def cosine(record: MemoryRecord) -> float:
            vector = record.embedding or []
            if len(vector) != len(query_embedding):
                return -1
            dot = sum(a * b for a, b in zip(vector, query_embedding, strict=True))
            left = math.sqrt(sum(value * value for value in vector))
            right = math.sqrt(sum(value * value for value in query_embedding))
            return dot / (left * right) if left and right else -1

        semantic = sorted(semantic_pool, key=cosine, reverse=True)[: limit * 2]
        ranks: dict[str, float] = {}
        by_id: dict[str, MemoryRecord] = {}
        for index, record in enumerate(records):
            ranks[record.id] = ranks.get(record.id, 0) + 1 / (60 + index)
            by_id[record.id] = record
        for index, record in enumerate(semantic):
            ranks[record.id] = ranks.get(record.id, 0) + 1 / (60 + index)
            by_id[record.id] = record
        records = [by_id[item_id] for item_id in sorted(ranks, key=ranks.get, reverse=True)]
    return records[:limit]


def compile_context(
    db: Session,
    game: Game,
    branch: Branch,
    action: str,
    query_embedding: list[float] | None = None,
) -> str:
    all_turns = lineage(db, branch.head_turn_id)
    recent = all_turns[-8:]
    allowed_ids = {turn.id for turn in all_turns}
    latest_state = all_turns[-1].snapshot.data if all_turns else deepcopy(DEFAULT_STATE)
    summary = db.scalar(select(RollingSummary).where(RollingSummary.branch_id == branch.id))
    lore = triggered_lore(db, game.id, action + " " + " ".join(t.narrative for t in recent[-3:]))
    memories = retrieve_memories(db, game.id, allowed_ids, action, query_embedding=query_embedding)
    profile = ensure_profile(db)
    characters = [
        {
            "name": _clip(character.name, 80),
            "role": _clip(character.role, 200),
            "personality": _clip(character.personality, 500),
            "appearance": _clip(character.appearance, 500),
            "background": _clip(character.background, 1000),
        }
        for character in game.characters
    ]
    recent_payload = [
        {
            "turn": turn.turn_index,
            "player_action": _clip(turn.player_action, 800),
            "scene": _clip(turn.scene, 160),
            "narrative": _clip(turn.narrative, 1500),
            "dialogue": turn.dialogue[:4],
        }
        for turn in recent
    ]
    sections = {
        "world": {
            "premise": _clip(game.premise, 2500),
            "rules": _clip(game.world_rules, 3000),
            "art_style": _clip(game.art_style, 1000),
            "safety": "全年龄 SFW，不得出现色情、露骨暴力或未成年人不当内容",
        },
        "characters": characters,
        "canonical_state": _compact_state(latest_state),
        "lore": [
            {"title": _clip(item.title, 160), "content": _clip(item.content, 1500)} for item in lore
        ],
        "rolling_summary": _clip(summary.content, 6000) if summary else "",
        "recalled_memories": [_clip(record.content, 800) for record in memories],
        "recent_turns": recent_payload,
        "player_profile": profile_to_schema(profile).model_dump(),
        "attempted_action": _clip(action, 2000),
    }
    serialized = json.dumps(sections, ensure_ascii=False, indent=2)
    if len(serialized) <= MAX_CONTEXT_CHARS:
        return serialized

    sections["lore"] = sections["lore"][:4]
    sections["rolling_summary"] = _clip(str(sections["rolling_summary"]), 3000)
    sections["recent_turns"] = recent_payload[-4:]
    for turn in sections["recent_turns"]:
        turn["narrative"] = _clip(str(turn["narrative"]), 800)
        turn["dialogue"] = turn["dialogue"][:2]
    serialized = json.dumps(sections, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) <= MAX_CONTEXT_CHARS:
        return serialized

    sections["canonical_state"] = _compact_value(
        sections["canonical_state"], string_limit=400, list_limit=8, dict_limit=15
    )
    sections["characters"] = [
        _compact_value(item, string_limit=400, list_limit=5, dict_limit=10)
        for item in sections["characters"]
    ]
    sections["player_profile"] = _compact_value(
        sections["player_profile"], string_limit=500, list_limit=10, dict_limit=20
    )
    sections["recent_turns"] = sections["recent_turns"][-2:]
    sections["lore"] = sections["lore"][:2]
    sections["recalled_memories"] = sections["recalled_memories"][:2]
    return json.dumps(sections, ensure_ascii=False, separators=(",", ":"))


def merge_state(previous: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "location",
        "time",
        "character_status",
        "relationships",
        "clues",
        "inventory",
        "world_flags",
        "promises",
        "open_threads",
    }
    result = deepcopy(previous)
    for key, value in delta.items():
        if key not in allowed:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key].update(value)
        else:
            result[key] = value
    return result


def apply_thread_updates(state: dict[str, Any], updates: list[dict[str, Any]]) -> dict[str, Any]:
    result = deepcopy(state)
    threads = {thread["id"]: dict(thread) for thread in result.get("open_threads", [])}
    open_count = 0
    for update in updates:
        action = update.get("action")
        thread_id = update.get("id")
        if not thread_id:
            continue
        if action == "open":
            if open_count >= 1:
                continue
            threads[thread_id] = {
                "id": thread_id,
                "summary": update.get("summary", "新的未解事件"),
                "status": "open",
                "progress": 0,
            }
            open_count += 1
        elif thread_id in threads and action == "advance":
            threads[thread_id]["summary"] = update.get("summary", threads[thread_id]["summary"])
            threads[thread_id]["progress"] = min(
                100, int(threads[thread_id].get("progress", 0)) + 25
            )
        elif thread_id in threads and action == "resolve":
            threads[thread_id]["status"] = "resolved"
            threads[thread_id]["progress"] = 100
            threads[thread_id]["summary"] = update.get("summary", threads[thread_id]["summary"])
    result["open_threads"] = list(threads.values())
    return result


def persist_memories(
    db: Session,
    game_id: str,
    turn_id: str,
    candidates: list[MemoryCandidate],
    embeddings: list[list[float]] | None = None,
) -> None:
    for index, candidate in enumerate(candidates):
        record = MemoryRecord(
            game_id=game_id,
            source_turn_id=turn_id,
            content=candidate.content,
            category=candidate.category,
            emotion=candidate.emotion,
            importance=candidate.importance,
            tags=candidate.tags,
            embedding=embeddings[index] if embeddings and index < len(embeddings) else None,
        )
        db.add(record)
        db.flush()
        db.execute(
            text(
                "INSERT INTO memory_fts(memory_id, game_id, content, tags) "
                "VALUES (:memory_id, :game_id, :content, :tags)"
            ),
            {
                "memory_id": record.id,
                "game_id": game_id,
                "content": record.content,
                "tags": " ".join(record.tags),
            },
        )


def update_profile_from_choice(db: Session, tags: list[str], visible_characters: list[str]) -> None:
    profile = ensure_profile(db)
    tendencies = dict(profile.choice_tendencies)
    for tag in tags:
        tendencies[tag] = round(tendencies.get(tag, 0) + 0.1, 2)
    affinities = dict(profile.character_affinities)
    for character in visible_characters:
        affinities[character] = round(affinities.get(character, 0) + 0.03, 2)
    profile.choice_tendencies = tendencies
    profile.character_affinities = affinities


def refresh_summary(db: Session, branch: Branch) -> None:
    turns = lineage(db, branch.head_turn_id)
    if not turns or len(turns) % 5:
        return
    summary = db.scalar(select(RollingSummary).where(RollingSummary.branch_id == branch.id))
    if not summary:
        summary = RollingSummary(game_id=branch.game_id, branch_id=branch.id)
        db.add(summary)
    selected = turns[-10:]
    lines = []
    for turn in selected:
        dialogue = "；".join(
            f"{item.get('speaker')}：{item.get('text')}" for item in turn.dialogue[:2]
        )
        lines.append(f"第{turn.turn_index}回合：{turn.narrative} {dialogue}".strip())
    summary.content = "\n".join(lines)[-6000:]
    summary.through_turn_id = turns[-1].id
    summary.turn_count = len(turns)
