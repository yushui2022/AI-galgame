from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class Game(TimestampMixin, Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(160))
    genre: Mapped[str] = mapped_column(String(120), default="校园恋爱")
    premise: Mapped[str] = mapped_column(Text)
    world_rules: Mapped[str] = mapped_column(Text, default="")
    art_style: Mapped[str] = mapped_column(Text, default="日系动画电影感，细腻光影，全年龄")
    safety_level: Mapped[str] = mapped_column(String(20), default="SFW")
    status: Mapped[str] = mapped_column(String(24), default="active")

    characters: Mapped[list[Character]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    branches: Mapped[list[Branch]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class Character(TimestampMixin, Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(120), default="主要角色")
    personality: Mapped[str] = mapped_column(Text, default="")
    appearance: Mapped[str] = mapped_column(Text, default="")
    background: Mapped[str] = mapped_column(Text, default="")
    reference_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_player: Mapped[bool] = mapped_column(Boolean, default=False)

    game: Mapped[Game] = relationship(back_populates="characters")


class StateSnapshot(TimestampMixin, Base):
    __tablename__ = "state_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Turn(TimestampMixin, Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    parent_turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("turns.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    state_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("state_snapshots.id", ondelete="RESTRICT")
    )
    turn_index: Mapped[int] = mapped_column(Integer, default=0)
    player_input_type: Mapped[str] = mapped_column(String(20), default="system")
    player_action: Mapped[str] = mapped_column(Text, default="")
    scene: Mapped[str] = mapped_column(String(160), default="")
    narrative: Mapped[str] = mapped_column(Text, default="")
    dialogue: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    choices: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    state_delta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    thread_updates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    memory_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    media_brief: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    media_status: Mapped[str] = mapped_column(String(24), default="queued")
    unlocked: Mapped[bool] = mapped_column(Boolean, default=False)

    snapshot: Mapped[StateSnapshot] = relationship()
    media_assets: Mapped[list[MediaAsset]] = relationship(
        back_populates="turn", cascade="all, delete-orphan"
    )


class Branch(TimestampMixin, Base):
    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="主线")
    head_turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("turns.id", ondelete="RESTRICT"), nullable=True
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    game: Mapped[Game] = relationship(back_populates="branches")
    head_turn: Mapped[Turn | None] = relationship()


class LoreEntry(TimestampMixin, Base):
    __tablename__ = "lore_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    always_on: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=50)


class MemoryRecord(TimestampMixin, Base):
    __tablename__ = "memory_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    source_turn_id: Mapped[str] = mapped_column(ForeignKey("turns.id", ondelete="CASCADE"))
    branch_lineage_root: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="event")
    emotion: Mapped[str] = mapped_column(String(40), default="neutral")
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)


class RollingSummary(TimestampMixin, Base):
    __tablename__ = "rolling_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), unique=True
    )
    through_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, default="")


class PlayerProfile(TimestampMixin, Base):
    __tablename__ = "player_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    preferred_themes: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_character_traits: Mapped[list[str]] = mapped_column(JSON, default=list)
    pacing: Mapped[str] = mapped_column(String(30), default="均衡")
    choice_tendencies: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    character_affinities: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    watched_videos: Mapped[int] = mapped_column(Integer, default=0)
    skipped_videos: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")


class MediaAsset(TimestampMixin, Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    turn_id: Mapped[str] = mapped_column(ForeignKey("turns.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(40))
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    turn: Mapped[Turn] = relationship(back_populates="media_assets")


class GenerationJob(TimestampMixin, Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    provider_task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
