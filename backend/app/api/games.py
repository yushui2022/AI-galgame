from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Branch, Character, Game, LoreEntry, StateSnapshot, Turn
from app.schemas import GameCreate, GameRead, ImageSpec
from app.services.media_worker import media_worker
from app.services.memory import DEFAULT_STATE
from app.services.providers import ProviderError, create_image_provider
from app.services.settings_store import provider_settings_store
from app.services.storage import persist_remote_media

from .serializers import game_read

router = APIRouter(prefix="/api/games", tags=["games"])


TEMPLATE_CHARACTERS = [
    {
        "name": "林澄",
        "role": "同班同学，旧校舍事件的目击者",
        "personality": "外表安静克制，观察细致，面对重要的人会突然变得勇敢",
        "appearance": "黑色及肩发，灰蓝眼睛，深色校服外套，银色旧钥匙挂坠",
        "background": "曾在失踪学姐管理的文学社做记录员，隐瞒着最后一次见面的细节",
    },
    {
        "name": "苏遥",
        "role": "失踪的高三学姐",
        "personality": "温和坚定，擅长用谜语隐藏重要信息",
        "appearance": "栗色长发，白色发带，旧式浅色校服",
        "background": "一年前在旧校舍封闭当晚失踪，如今手机却再次发出讯息",
    },
    {
        "name": "顾屿",
        "role": "学生会档案管理员",
        "personality": "理性谨慎，说话直接，对校史异常敏感",
        "appearance": "短黑发，金属框眼镜，整洁的学生会制服",
        "background": "能够接触封存档案，似乎知道旧校舍停用的真实原因",
    },
]


def _query_game(db: Session, game_id: str) -> Game | None:
    return db.scalar(
        select(Game)
        .where(Game.id == game_id)
        .options(selectinload(Game.characters), selectinload(Game.branches))
    )


@router.get("", response_model=list[GameRead])
def list_games(db: Session = Depends(get_db)) -> list[GameRead]:
    games = db.scalars(
        select(Game)
        .options(selectinload(Game.characters), selectinload(Game.branches))
        .order_by(Game.updated_at.desc())
    ).all()
    return [game_read(game) for game in games]


@router.get("/{game_id}", response_model=GameRead)
def get_game(game_id: str, db: Session = Depends(get_db)) -> GameRead:
    game = _query_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="游戏不存在")
    return game_read(game)


@router.post("", response_model=GameRead)
async def create_game(payload: GameCreate, db: Session = Depends(get_db)) -> GameRead:
    providers = provider_settings_store.load()
    if not (providers.llm.enabled and providers.image.enabled and providers.video.enabled):
        raise HTTPException(status_code=400, detail="请先完成 LLM、图片和视频供应商配置")
    game = Game(
        title=payload.title,
        genre=payload.genre,
        premise=payload.premise,
        world_rules=payload.world_rules,
        art_style=payload.art_style,
    )
    db.add(game)
    db.flush()
    characters = payload.characters or [SimpleNamespace(**item) for item in TEMPLATE_CHARACTERS]
    for item in characters[:3]:
        db.add(
            Character(
                game_id=game.id,
                name=item.name,
                role=item.role,
                personality=item.personality,
                appearance=item.appearance,
                background=item.background,
            )
        )
    db.add_all(
        [
            LoreEntry(
                game_id=game.id,
                title="旧校舍",
                content="旧校舍一年前因电路事故封闭，传闻每逢雨夜会出现第七次钟声。",
                keywords=["旧校舍", "钟声", "雨夜"],
                always_on=True,
                priority=100,
            ),
            LoreEntry(
                game_id=game.id,
                title="失踪学姐苏遥",
                content="苏遥失踪前是文学社社长，最后留下的是一本缺少第七码的借阅记录。",
                keywords=["苏遥", "学姐", "文学社", "借阅"],
                priority=80,
            ),
        ]
    )
    snapshot = StateSnapshot(game_id=game.id, data=DEFAULT_STATE)
    db.add(snapshot)
    db.flush()
    root = Turn(
        game_id=game.id,
        state_snapshot_id=snapshot.id,
        turn_index=0,
        player_input_type="system",
        scene="教学楼门厅",
        narrative="放学后的雨还没有停。你的手机忽然亮起，屏幕上出现一条来自失踪一年的学姐苏遥的短信：不要让林澄独自去旧校舍。",
        dialogue=[{"speaker": "林澄", "text": "你也收到那条短信了吗？", "emotion": "不安"}],
        choices=[
            {"id": "tell_truth", "text": "把短信内容告诉林澄", "tags": ["坦诚", "关系"]},
            {"id": "check_sender", "text": "先检查短信的发送来源", "tags": ["调查", "谨慎"]},
        ],
        state_delta={},
        thread_updates=[],
        memory_candidates=[],
        media_brief={
            "visual_summary": "雨夜教学楼门厅，黑发少女林澄站在窗边，手机屏幕映亮她不安的脸",
            "motion": "林澄缓慢回头，窗外雨水流过玻璃，手机冷光轻微闪烁",
            "camera": "slow cinematic push-in",
            "mood": "mysterious and tender",
            "visible_characters": ["林澄"],
        },
        media_status="queued",
        unlocked=False,
    )
    db.add(root)
    db.flush()
    snapshot.turn_id = root.id
    db.add(Branch(game_id=game.id, name="主线", head_turn_id=root.id))
    db.commit()
    await media_worker.enqueue_turn(root.id)
    game = _query_game(db, game.id)
    assert game
    return game_read(game)


@router.post("/{game_id}/characters/generate", response_model=GameRead)
async def generate_character_references(game_id: str, db: Session = Depends(get_db)) -> GameRead:
    game = _query_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="游戏不存在")
    missing = [character for character in game.characters if not character.reference_image_path]
    if not missing:
        return game_read(game)

    config = provider_settings_store.load().image
    try:
        provider = create_image_provider(config)
        for character in missing:
            prompt = (
                f"{game.art_style}。Galgame角色设定立绘，单人半身像，纯净低干扰背景，"
                f"角色名：{character.name}；身份：{character.role}；性格：{character.personality}；"
                f"外观：{character.appearance}。人物正面或轻微侧身，面部清晰，服装完整，"
                "角色设计一致性参考图，全年龄，无文字，无水印。"
            )
            job = await provider.submit(
                ImageSpec(
                    prompt=prompt,
                    setting="纯净低干扰的角色设定背景",
                    composition="单人半身像，角色居中",
                    lighting="柔和电影光",
                    mood="符合角色设定",
                    art_style=game.art_style,
                )
            )
            polls = 0
            while job.status in {"queued", "running"} and polls < 120:
                await asyncio.sleep(2)
                job = await provider.poll(job)
                polls += 1
            if job.status != "succeeded" or not job.result_url:
                raise ProviderError(job.error or f"{character.name} 的参考图生成失败")
            path, _, _ = await persist_remote_media(
                job.result_url, "image", f"character-{character.id}"
            )
            character.reference_image_path = str(path)
            db.commit()
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    game = _query_game(db, game_id)
    assert game
    return game_read(game)


@router.post("/{game_id}/characters/{character_id}/reference", response_model=GameRead)
async def upload_character_reference(
    game_id: str,
    character_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> GameRead:
    if file.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=400, detail="只支持 PNG、JPEG 或 WebP")
    character = db.get(Character, character_id)
    if not character or character.game_id != game_id:
        raise HTTPException(status_code=404, detail="角色不存在")
    suffix = Path(file.filename or "reference.png").suffix.lower()
    target = get_settings().media_dir / "uploads" / f"{character.id}{suffix}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    character.reference_image_path = str(target)
    db.commit()
    game = _query_game(db, game_id)
    assert game
    return game_read(game)
