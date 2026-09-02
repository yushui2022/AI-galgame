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
        "role": "同班同桌，校园摄影社成员",
        "personality": "安静细腻，熟悉后会露出温柔又有点调皮的一面",
        "appearance": "黑色及肩发，灰蓝眼睛，浅色校服外套，随身带一台小相机",
        "background": "正在为摄影社春季展收集照片，喜欢记录别人没有留意到的校园瞬间",
    },
    {
        "name": "夏栀",
        "role": "青梅竹马，班级文艺委员",
        "personality": "开朗直率，行动力强，关心别人时总装作若无其事",
        "appearance": "栗色高马尾，琥珀色眼睛，校服领口系着暖黄色丝带",
        "background": "负责筹备班级文化祭节目，总想拉你一起参加",
    },
    {
        "name": "苏晚",
        "role": "高三学姐，文学社社长",
        "personality": "成熟温柔，表达感情时坦率而从容",
        "appearance": "深棕色长发，白色发带，浅色针织开衫与整洁校服",
        "background": "在毕业前策划最后一期文学社刊物，希望为校园生活留下值得珍惜的记录",
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
                title="春日校园生活",
                content="新学期刚刚开始，樱花季仍在继续。校园里开放着摄影社、文学社、运动场、天台花园和放学后的商店街，六周后将举办校园文化祭。",
                keywords=["校园", "樱花", "社团", "放学", "文化祭"],
                always_on=True,
                priority=100,
            ),
            LoreEntry(
                game_id=game.id,
                title="摄影社春季展",
                content="林澄正在为摄影社春季展收集校园照片，最喜欢放学后的樱花小路，却还没有选好展览的主题。",
                keywords=["林澄", "摄影社", "照片", "春季展", "樱花小路"],
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
        scene="校门口的樱花树下",
        narrative="新学期第一天，樱花被春风吹过校门。你刚停下脚步，林澄抱着几本摄影集从树下走来，其中一本差点滑落。她看见你，先是一怔，随后露出浅浅的笑。",
        dialogue=[{"speaker": "林澄", "text": "早安。正好……要不要一起去教室？", "emotion": "期待"}],
        choices=[
            {
                "id": "walk_together",
                "text": "接过她怀里的书，和她一起走进校园",
                "tags": ["体贴", "陪伴"],
            },
            {
                "id": "invite_after_school",
                "text": "答应她，并约她放学后一起逛摄影社",
                "tags": ["主动", "浪漫"],
            },
        ],
        state_delta={},
        thread_updates=[],
        memory_candidates=[],
        media_brief={
            "visual_summary": "春日清晨的校园门口，樱花随风飘落，黑色及肩发的少女林澄抱着摄影集站在树下，向第一视角露出浅浅的笑",
            "motion": "林澄轻轻扶稳怀里的书，樱花花瓣随风掠过发梢，她抬眼看向镜头",
            "camera": "gentle cinematic push-in from first-person view",
            "mood": "warm, youthful and romantic",
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
