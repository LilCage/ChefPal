"""语音烹饪助手路由（EXT-14.1）：POST /api/cook-assistant/query。

前端录音 → /voice/transcribe 转文字 → 携菜谱 id + 文字到这里，AI 基于菜谱步骤回答。
复用 voice 的 ASR 链路与 rate_limit 风控记账。
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.recipe import Recipe
from app.models.user import User
from app.services import cook_assistant as cook_service
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/cook-assistant", tags=["cook-assistant"])
settings = get_settings()


class CookQueryRequest(BaseModel):
    recipe_id: UUID = Field(description="菜谱 id（须属于当前用户）")
    question: str = Field(min_length=1, max_length=200, description="已转文字的语音提问")


@router.post("/query")
async def cook_query(
    body: CookQueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """基于菜谱上下文回答做饭提问。"""
    if not body.question.strip():
        raise AppError("没有听到问题，请再说一次", code=400, status_code=400)

    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    row = await db.execute(
        select(Recipe).where(Recipe.id == body.recipe_id, Recipe.user_id == user.id)
    )
    rec = row.scalar_one_or_none()
    if rec is None:
        raise AppError("菜谱不存在", code=404, status_code=404)

    try:
        data = await cook_service.answer_cooking_question(rec.title, rec.steps, body.question)
    except cook_service.CookAssistantError as exc:
        raise AppError(str(exc), code=502, status_code=502) from exc

    await record_ai_call(db, user.id, "cook_assistant", settings.DEEPSEEK_MODEL)
    await db.commit()
    return ok({"answer": data["answer"], "current_step": data["current_step"], "title": rec.title})
