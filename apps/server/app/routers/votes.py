"""家庭口味投票路由（原型 05 屏2）。

- POST /api/votes/generate {ingredients} → AI 生成 3 道菜选项，建投票
- GET  /api/votes/{id} → 详情 + 各选项票数 + 我已投项
- POST /api/votes/{id}/vote {option_index} → 投票（重复投票 = 改票）
- GET  /api/votes/{id}/share-card → 分享卡片（带小程序码 scene=vote id）
"""
import base64
import copy
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.family_vote import FamilyVote
from app.models.family_vote_record import FamilyVoteRecord
from app.models.user import User
from app.schemas.ai import VoteOptionsSchema
from app.services import wechat as wechat_service
from app.services.agents import vote_agent
from app.services.rate_limit import ensure_within_limit, record_ai_call
from app.services.wechat import WeChatError

router = APIRouter(prefix="/votes", tags=["votes"])
settings = get_settings()


class VoteGenerateRequest(BaseModel):
    ingredients: list[str] = Field(min_length=1, max_length=20)


class VoteRequest(BaseModel):
    option_index: int = Field(ge=0)


async def _get_vote_or_404(db: AsyncSession, vote_id: UUID) -> FamilyVote:
    vote = await db.get(FamilyVote, vote_id)
    if vote is None:
        raise AppError("投票不存在", code=404, status_code=404)
    return vote


async def _my_choice(db: AsyncSession, vote_id: UUID, user_id: UUID) -> int | None:
    row = await db.execute(
        select(FamilyVoteRecord.option_index).where(
            FamilyVoteRecord.vote_id == vote_id, FamilyVoteRecord.user_id == user_id
        )
    )
    return row.scalar_one_or_none()


def _vote_out(vote: FamilyVote, my_choice: int | None, total_count: int) -> dict:
    return {
        "id": str(vote.id),
        "status": vote.status,
        "ingredients": vote.ingredients,
        "options": vote.options,
        "my_choice": my_choice,
        "total_count": total_count,
        "created_at": vote.created_at.isoformat() if vote.created_at else None,
    }


async def _count_total(db: AsyncSession, vote_id: UUID) -> int:
    from sqlalchemy import func

    row = await db.execute(
        select(func.count())
        .select_from(FamilyVoteRecord)
        .where(FamilyVoteRecord.vote_id == vote_id)
    )
    return int(row.scalar_one())


@router.post("/generate")
async def generate_vote(
    body: VoteGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """基于冰箱食材 AI 生成 3 道菜选项，创建家庭投票。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    prefs = user.preferences or {}
    out = await vote_agent.run_vote(body.ingredients, prefs)
    if out["error"] or out["result"] is None:
        raise AppError(out["error"] or "选项生成失败，请稍后重试", code=502, status_code=502)

    try:
        parsed = VoteOptionsSchema.model_validate(out["result"])
        names = parsed.options
    except Exception:  # noqa: BLE001
        raise AppError("选项生成失败，请稍后重试", code=502, status_code=502)

    options = [{"name": name, "count": 0} for name in names]
    vote = FamilyVote(user_id=user.id, ingredients=body.ingredients, options=options)
    await record_ai_call(db, user.id, "vote", settings.DEEPSEEK_MODEL)
    db.add(vote)
    await db.commit()
    await db.refresh(vote)
    return ok(_vote_out(vote, None, 0))


@router.get("/{vote_id}")
async def get_vote(
    vote_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """投票详情：选项/票数/我已投项/总票数。"""
    vote = await _get_vote_or_404(db, vote_id)
    my_choice = await _my_choice(db, vote_id, user.id)
    total = await _count_total(db, vote_id)
    return ok(_vote_out(vote, my_choice, total))


@router.post("/{vote_id}/vote")
async def cast_vote(
    vote_id: UUID,
    body: VoteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """投票/改票：先减旧选项票数，再加新选项；未投过则新增记录。"""
    vote = await _get_vote_or_404(db, vote_id)
    if len(vote.options) <= body.option_index:
        raise AppError("无效的选项", code=400, status_code=400)

    # 已投过 → 改票：减旧、改记录；未投过 → 新增记录
    row = await db.execute(
        select(FamilyVoteRecord).where(
            FamilyVoteRecord.vote_id == vote_id, FamilyVoteRecord.user_id == user.id
        )
    )
    record = row.scalar_one_or_none()

    new_options = copy.deepcopy(vote.options)  # JSONB 就地修改不落库，必须深拷贝副本
    if record is not None:
        new_options[record.option_index]["count"] = max(0, new_options[record.option_index]["count"] - 1)
        record.option_index = body.option_index
    else:
        db.add(FamilyVoteRecord(vote_id=vote_id, user_id=user.id, option_index=body.option_index))

    new_options[body.option_index]["count"] = new_options[body.option_index]["count"] + 1
    vote.options = new_options

    await db.commit()
    await db.refresh(vote)
    my_choice = await _my_choice(db, vote_id, user.id)
    total = await _count_total(db, vote_id)
    return ok(_vote_out(vote, my_choice, total))


@router.get("/{vote_id}/share-card")
async def vote_share_card(
    vote_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """分享卡片数据：投票标题 + 选项数 + 小程序码（scene=vote id 32位hex）。"""
    vote = await _get_vote_or_404(db, vote_id)

    qrcode_base64 = None
    try:
        scene = vote.id.hex  # 32 位，满足 scene 长度限制
        png = await wechat_service.get_unlimited_qrcode(
            scene=scene, page="pages/family-vote/index"
        )
        qrcode_base64 = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    except WeChatError:
        # 小程序未发布等场景降级：码为空，卡片仍可生成
        qrcode_base64 = None

    return ok(
        {
            "title": "今晚吃什么？",
            "options": [o["name"] for o in vote.options],
            "options_count": len(vote.options),
            "qrcode_base64": qrcode_base64,
        }
    )
