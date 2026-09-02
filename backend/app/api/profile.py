from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PlayerProfile
from app.schemas import PlayerProfileData
from app.services.memory import ensure_profile, profile_to_schema

router = APIRouter(prefix="/api/player-profile", tags=["profile"])


@router.get("", response_model=PlayerProfileData)
def get_profile(db: Session = Depends(get_db)) -> PlayerProfileData:
    return profile_to_schema(ensure_profile(db))


@router.put("", response_model=PlayerProfileData)
def update_profile(payload: PlayerProfileData, db: Session = Depends(get_db)) -> PlayerProfileData:
    profile = ensure_profile(db)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile_to_schema(profile)


@router.delete("", response_model=PlayerProfileData)
def reset_profile(db: Session = Depends(get_db)) -> PlayerProfileData:
    current = db.get(PlayerProfile, "default")
    if current:
        db.delete(current)
        db.commit()
    return profile_to_schema(ensure_profile(db))
