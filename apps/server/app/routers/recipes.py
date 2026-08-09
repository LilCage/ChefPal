"""菜谱路由：POST /api/recipes/generate、GET /api/recipes/{id}、GET /api/recipes/{id}/share-card。"""
import base64
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
from app.services import wechat as wechat_service
from app.services.agents import recipe_agent
from app.services.rate_limit import ensure_within_limit, record_ai_call
from app.services.wechat import WeChatError

router = APIRouter(prefix="/recipes", tags=["recipes"])
settings = get_settings()


class RecipeGenerateRequest(BaseModel):
    ingredients: list[str] = Field(min_length=1, max_length=20)
    prefs: dict | None = None  # 可选：前端临时覆盖口味偏好


def _recipe_out(rec: Recipe) -> dict:
    return {
        "id": str(rec.id),
        "title": rec.title,
        "ingredients": rec.ingredients,
        "match_score": rec.match_score,
        "time_minutes": rec.time_minutes,
        "difficulty": rec.difficulty,
        "steps": rec.steps,
        "tips": rec.tips,
        "missing_seasonings": rec.missing_seasonings,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }


@router.post("/generate")
async def generate(
    body: RecipeGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """食材魔方：输入食材 → AI 生成 TOP3 菜谱并落库。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    prefs = body.prefs if body.prefs is not None else (user.preferences or {})
    out = await recipe_agent.run_recipe(body.ingredients, prefs)
    if out["error"] or out["result"] is None:
        raise AppError(out["error"] or "菜谱生成失败，请稍后重试", code=502, status_code=502)

    data = out["result"]
    ingredients_have = [{"name": name, "is_have": True} for name in body.ingredients]
    prompt_snapshot = (
        f"ingredients={body.ingredients}; prefs={prefs}"
    )

    created: list[Recipe] = []
    for r in data["recipes"]:
        rec = Recipe(
            user_id=user.id,
            title=r["name"],
            ingredients=ingredients_have,
            match_score=r["match_score"],
            time_minutes=r["time_minutes"],
            difficulty=r["difficulty"],
            steps=r["steps"],
            tips=r.get("tips", []),
            missing_seasonings=r.get("missing_seasonings", []),
            raw_prompt=prompt_snapshot,
        )
        db.add(rec)
        created.append(rec)

    await record_ai_call(db, user.id, "recipe", settings.DEEPSEEK_MODEL)
    await db.commit()
    for rec in created:
        await db.refresh(rec)

    return ok([_recipe_out(rec) for rec in created])


@router.get("/{recipe_id}")
async def get_recipe(
    recipe_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """菜谱详情（仅本人可见）。"""
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id, Recipe.user_id == user.id)
    )
    rec = result.scalar_one_or_none()
    if rec is None:
        raise AppError("菜谱不存在", code=404, status_code=404)
    return ok(_recipe_out(rec))


@router.get("/{recipe_id}/share-card")
async def get_share_card(
    recipe_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """分享卡片数据：菜谱信息 + 小程序码（scene=32 位 hex，page=菜谱详情页）。"""
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id, Recipe.user_id == user.id)
    )
    rec = result.scalar_one_or_none()
    if rec is None:
        raise AppError("菜谱不存在", code=404, status_code=404)

    qrcode_base64 = None
    try:
        scene = rec.id.hex  # UUID 去横线 → 32 位，满足 scene 长度限制
        png = await wechat_service.get_unlimited_qrcode(
            scene=scene, page="pages/recipe-detail/index"
        )
        qrcode_base64 = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    except WeChatError:
        # 小程序未发布/access_token 失败等场景降级：码为空，卡片仍可生成
        qrcode_base64 = None

    return ok(
        {
            "title": rec.title,
            "match_score": rec.match_score,
            "time_minutes": rec.time_minutes,
            "difficulty": rec.difficulty,
            "core_secret": rec.tips[0] if rec.tips else None,
            "steps_count": len(rec.steps),
            "qrcode_base64": qrcode_base64,
        }
    )
