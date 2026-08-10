"""烹饪挑战路由（原型 05 屏4）：创建/列表/加入/进度/排行榜。无 AI 调用。"""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.challenge import Challenge
from app.models.challenge_participant import ChallengeParticipant
from app.models.user import User

router = APIRouter(prefix="/challenges", tags=["challenges"])


class ChallengeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=64)
    budget: int = Field(ge=0, le=100000)
    description: str | None = None


class ProgressRequest(BaseModel):
    spend: int = Field(ge=0, le=100000)
    meal_count: int = Field(default=0, ge=0, le=1000)


async def _get_challenge_or_404(db: AsyncSession, challenge_id: UUID) -> Challenge:
    chal = await db.get(Challenge, challenge_id)
    if chal is None:
        raise AppError("挑战不存在", code=404, status_code=404)
    return chal


async def _get_participant_or_404(
    db: AsyncSession, challenge_id: UUID, user_id: UUID
) -> ChallengeParticipant:
    row = await db.execute(
        select(ChallengeParticipant).where(
            ChallengeParticipant.challenge_id == challenge_id,
            ChallengeParticipant.user_id == user_id,
        )
    )
    p = row.scalar_one_or_none()
    if p is None:
        raise AppError("尚未加入该挑战", code=404, status_code=404)
    return p


def _challenge_out(c: Challenge) -> dict:
    return {
        "id": str(c.id),
        "title": c.title,
        "budget": c.budget,
        "description": c.description,
        "status": c.status,
        "participant_count": c.participant_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.post("")
async def create_challenge(
    body: ChallengeCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """创建挑战（如"一周只花 50 元"）。"""
    chal = Challenge(
        creator_id=user.id,
        title=body.title,
        budget=body.budget,
        description=body.description,
    )
    db.add(chal)
    await db.commit()
    await db.refresh(chal)
    return ok(_challenge_out(chal))


@router.get("")
async def list_challenges(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """进行中的挑战列表。"""
    rows = await db.execute(
        select(Challenge).where(Challenge.status == "active").order_by(Challenge.created_at.desc()).limit(50)
    )
    items = [_challenge_out(c) for c in rows.scalars()]
    return ok({"items": items})


@router.post("/{challenge_id}/join")
async def join_challenge(
    challenge_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """加入挑战（幂等，计数不叠加）。"""
    chal = await _get_challenge_or_404(db, challenge_id)
    exists = await db.execute(
        select(ChallengeParticipant.id).where(
            ChallengeParticipant.challenge_id == challenge_id,
            ChallengeParticipant.user_id == user.id,
        )
    )
    if exists.scalar_one_or_none() is None:
        db.add(ChallengeParticipant(challenge_id=challenge_id, user_id=user.id))
        chal.participant_count += 1
        await db.commit()
        await db.refresh(chal)
        return ok({**_challenge_out(chal), "joined": True})
    await db.refresh(chal)
    return ok({**_challenge_out(chal), "joined": False})


@router.put("/{challenge_id}/progress")
async def update_progress(
    challenge_id: UUID,
    body: ProgressRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """更新我在挑战中的花费与餐数。"""
    await _get_challenge_or_404(db, challenge_id)
    p = await _get_participant_or_404(db, challenge_id, user.id)
    p.spend = body.spend
    p.meal_count = body.meal_count
    await db.commit()
    await db.refresh(p)
    return ok({"challenge_id": str(challenge_id), "spend": p.spend, "meal_count": p.meal_count})


@router.get("/{challenge_id}/leaderboard")
async def leaderboard(
    challenge_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """排行榜：按"花得越少、餐数越多"排名（花费升序，餐数降序）。"""
    await _get_challenge_or_404(db, challenge_id)
    rows = await db.execute(
        select(ChallengeParticipant)
        .where(ChallengeParticipant.challenge_id == challenge_id)
        .order_by(ChallengeParticipant.spend.asc(), ChallengeParticipant.meal_count.desc())
    )
    items = []
    for p in rows.scalars():
        owner = await db.get(User, p.user_id)
        nickname = owner.nickname if owner and owner.nickname else "美食猎人"
        items.append(
            {
                "user_id": str(p.user_id),
                "nickname": nickname,
                "spend": p.spend,
                "meal_count": p.meal_count,
                "is_me": p.user_id == user.id,
            }
        )
    return ok({"items": items})
