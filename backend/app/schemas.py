from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProviderConfig(BaseModel):
    kind: str
    base_url: str
    api_key: str = ""
    model: str
    enabled: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)


class ProviderSettings(BaseModel):
    llm: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(
            kind="openai", base_url="", model="MiniCPM", enabled=False
        )
    )
    image: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(
            kind="ark",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            model="",
            enabled=False,
            extra={"size": "2K"},
        )
    )
    video: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(
            kind="seedance",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            model="",
            enabled=False,
        )
    )
    embedding: ProviderConfig | None = None


class ProviderTestResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int | None = None


class CharacterInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: str = "主要角色"
    personality: str = ""
    appearance: str = ""
    background: str = ""


class CharacterRead(CharacterInput):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference_image_url: str | None = None


class GameCreate(BaseModel):
    mode: Literal["template", "custom"] = "template"
    title: str = "樱花落下之前"
    genre: str = "校园恋爱"
    premise: str = "新学期开始，你在日常相处、社团活动和校园文化祭的准备中，与三位性格不同的同学逐渐靠近。你的每个选择都会改变彼此的关系与共同回忆。"
    world_rules: str = "现代高中校园，以日常相处、社团活动、节日和恋爱关系发展为主；不主动引入悬疑、犯罪、失踪、超自然或阴谋；所有内容保持全年龄。"
    art_style: str = "日系青春恋爱动画，春日校园，樱花与暖阳，清透明亮，柔和粉蓝色调"
    characters: list[CharacterInput] = Field(default_factory=list, max_length=3)


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    head_turn_id: str | None
    archived: bool
    created_at: datetime


class GameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    genre: str
    premise: str
    world_rules: str
    art_style: str
    safety_level: str
    status: str
    created_at: datetime
    characters: list[CharacterRead] = Field(default_factory=list)
    branches: list[BranchRead] = Field(default_factory=list)


class DialogueLine(BaseModel):
    speaker: str
    text: str
    emotion: str = "neutral"


class Choice(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list)


class ThreadUpdate(BaseModel):
    id: str
    action: Literal["open", "advance", "resolve"]
    summary: str


class MemoryCandidate(BaseModel):
    content: str
    category: str = "event"
    emotion: str = "neutral"
    importance: float = Field(default=0.5, ge=0, le=1)
    tags: list[str] = Field(default_factory=list)


class MediaBrief(BaseModel):
    visual_summary: str
    motion: str
    camera: str = "medium shot, slow cinematic movement"
    mood: str = "warm, youthful and romantic"
    visible_characters: list[str] = Field(default_factory=list, max_length=3)


class TurnResult(BaseModel):
    scene: str
    narrative: str
    dialogue: list[DialogueLine] = Field(default_factory=list)
    choices: list[Choice]
    state_delta: dict[str, Any] = Field(default_factory=dict)
    thread_updates: list[ThreadUpdate] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    media_brief: MediaBrief

    @field_validator("choices")
    @classmethod
    def exactly_two_choices(cls, value: list[Choice]) -> list[Choice]:
        if len(value) != 2:
            raise ValueError("每回合必须恰好生成两个选项")
        if value[0].text.strip() == value[1].text.strip():
            raise ValueError("两个选项不能相同")
        return value


class TurnRequest(BaseModel):
    input_type: Literal["suggested", "free_text"]
    text: str = Field(min_length=1, max_length=1000)
    choice_id: str | None = None
    expected_head_turn_id: str


class ImageSpec(BaseModel):
    prompt: str
    character_reference_urls: list[str] = Field(default_factory=list)
    setting: str
    composition: str
    lighting: str
    mood: str
    art_style: str
    aspect_ratio: str = "16:9"


class VideoSpec(BaseModel):
    prompt: str
    first_frame_url: str | None = None
    character_reference_urls: list[str] = Field(default_factory=list)
    action: str
    camera: str
    mood: str
    duration: int = 6
    resolution: str = "720p"
    aspect_ratio: str = "16:9"


class ProviderJob(BaseModel):
    provider_task_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: float = 0
    result_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    provider: str
    url: str | None = None
    size_bytes: int


class TurnRead(BaseModel):
    id: str
    game_id: str
    parent_turn_id: str | None
    turn_index: int
    player_input_type: str
    player_action: str
    scene: str
    narrative: str
    dialogue: list[dict[str, Any]]
    choices: list[dict[str, Any]]
    media_status: str
    unlocked: bool
    media_assets: list[MediaAssetRead] = Field(default_factory=list)
    created_at: datetime


class TurnSubmission(BaseModel):
    turn: TurnRead
    job_id: str


class ForkRequest(BaseModel):
    turn_id: str
    name: str | None = None


class RenameBranchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PlayerProfileData(BaseModel):
    preferred_themes: list[str] = Field(default_factory=list)
    preferred_character_traits: list[str] = Field(default_factory=list)
    pacing: str = "均衡"
    choice_tendencies: dict[str, float] = Field(default_factory=dict)
    character_affinities: dict[str, float] = Field(default_factory=dict)
    watched_videos: int = 0
    skipped_videos: int = 0
    notes: str = ""


class StorageStatus(BaseModel):
    media_bytes: int
    free_bytes: int
    warning: str | None = None
