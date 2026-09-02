from __future__ import annotations

from app.models import Character, Game, MediaAsset, Turn
from app.schemas import CharacterRead, GameRead, MediaAssetRead, TurnRead
from app.services.storage import media_url


def character_read(character: Character) -> CharacterRead:
    return CharacterRead(
        id=character.id,
        name=character.name,
        role=character.role,
        personality=character.personality,
        appearance=character.appearance,
        background=character.background,
        reference_image_url=media_url(character.reference_image_path),
    )


def game_read(game: Game) -> GameRead:
    return GameRead(
        id=game.id,
        title=game.title,
        genre=game.genre,
        premise=game.premise,
        world_rules=game.world_rules,
        art_style=game.art_style,
        safety_level=game.safety_level,
        status=game.status,
        created_at=game.created_at,
        characters=[character_read(item) for item in game.characters],
        branches=game.branches,
    )


def media_asset_read(asset: MediaAsset) -> MediaAssetRead:
    return MediaAssetRead(
        id=asset.id,
        kind=asset.kind,
        provider=asset.provider,
        url=media_url(asset.local_path),
        size_bytes=asset.size_bytes,
    )


def turn_read(turn: Turn) -> TurnRead:
    return TurnRead(
        id=turn.id,
        game_id=turn.game_id,
        parent_turn_id=turn.parent_turn_id,
        turn_index=turn.turn_index,
        player_input_type=turn.player_input_type,
        player_action=turn.player_action,
        scene=turn.scene,
        narrative=turn.narrative,
        dialogue=turn.dialogue,
        choices=turn.choices,
        media_status=turn.media_status,
        unlocked=turn.unlocked,
        media_assets=[media_asset_read(asset) for asset in turn.media_assets],
        created_at=turn.created_at,
    )
