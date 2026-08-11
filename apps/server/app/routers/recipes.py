"""菜谱路由：generate / 详情 / share-card / 进化树 fork+tree（原型 05 屏6）。"""
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
from app.models.recipe_version import RecipeVersion
from app.models.user import User
from app.services import wechat as wechat_service
from app.services import taste_memory as taste_service
from app.services.agents import recipe_agent
from app.services.rate_limit import ensure_within_limit, record_ai_call
from app.services.wechat import WeChatError

router = APIRouter(prefix="/recipes", tags=["recipes"])
settings = get_settings()


async def _get_recipe_or_404(db: AsyncSession, recipe_id: UUID) -> Recipe:
    rec = await db.get(Recipe, recipe_id)
    if rec is None:
        raise AppError("菜谱不存在", code=404, status_code=404)
    return rec


def _version_out(v: RecipeVersion, is_root: bool) -> dict:
    return {
        "id": str(v.id),
        "recipe_id": str(v.recipe_id),
        "parent_id": str(v.parent_id) if v.parent_id else None,
        "version_label": v.version_label,
        "title": v.title,
        "changes": v.changes,
        "is_root": is_root,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


async def _ensure_root_version(db: AsyncSession, rec: Recipe) -> RecipeVersion:
    """菜谱首次 fork 前确保存在 v1.0 根版本（懒创建）。"""
    row = await db.execute(
        select(RecipeVersion).where(
            RecipeVersion.recipe_id == rec.id, RecipeVersion.parent_id.is_(None)
        )
    )
    root = row.scalar_one_or_none()
    if root is not None:
        return root
    root = RecipeVersion(
        recipe_id=rec.id,
        parent_id=None,
        user_id=rec.user_id,
        version_label="v1.0",
        title=rec.title,
        changes="",
    )
    db.add(root)
    await db.flush()
    return root


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
        "style": rec.style,
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
    # AI 口味记忆注入（EXT-13.2）：聚合收藏/点赞信号 → 追加到偏好 Prompt（信号不足自动跳过）
    taste_profile = await taste_service.summarize_taste(db, user.id)
    taste_text = taste_service.build_injection_text(taste_profile)
    if taste_text:
        prefs = {**prefs, "taste_memory": taste_text}
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
            style=r.get("style", ""),
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


class ForkRequest(BaseModel):
    changes: str = Field(default="", max_length=200, description="这一版改了什么")


async def _resolve_recipe_ref(
    db: AsyncSession, ref: UUID
) -> tuple[Recipe, RecipeVersion | None]:
    """ref 可能是 recipe_id 或 version_id → (recipe, parent_version)。"""
    v = await db.get(RecipeVersion, ref)
    if v is not None:
        rec = await _get_recipe_or_404(db, v.recipe_id)
        return rec, v
    rec = await _get_recipe_or_404(db, ref)
    return rec, None


def _next_label(versions: list[RecipeVersion]) -> str:
    """链上最大版本号 +1，如 [v1.0] → v2.0。"""
    nums = []
    for v in versions:
        try:
            nums.append(int(v.version_label.lstrip("v").split(".")[0]))
        except (ValueError, AttributeError):
            continue
    return f"v{max(nums) + 1 if nums else 1}.0"


async def _recipe_chain(db: AsyncSession, recipe_id: UUID) -> list[RecipeVersion]:
    """进化树链：沿 parent_id 从根走到最新（同一事务内 created_at 相同，不能按时间排序）。"""
    rows = await db.execute(select(RecipeVersion).where(RecipeVersion.recipe_id == recipe_id))
    versions = list(rows.scalars())
    if not versions:
        return []

    by_id = {v.id: v for v in versions}
    root = next((v for v in versions if v.parent_id is None), None)
    if root is None:
        return versions  # 数据异常时兜底

    chain = [root]
    cur = root
    while cur.id in by_id and any(v.parent_id == cur.id for v in versions):
        child = next(v for v in versions if v.parent_id == cur.id)
        chain.append(child)
        cur = child
        if len(chain) > len(versions):  # 防环
            break
    return chain


@router.post("/{recipe_id}/fork")
async def fork_recipe(
    recipe_id: UUID,
    body: ForkRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """菜谱DNA进化树：基于某菜谱/某版本 fork 出我的分支（原型 05 屏6）。"""
    rec, parent = await _resolve_recipe_ref(db, recipe_id)

    # 无根版本则先创建 v1.0 原版
    chain = await _recipe_chain(db, rec.id)
    if not chain:
        await _ensure_root_version(db, rec)
        await db.flush()
        chain = await _recipe_chain(db, rec.id)

    # 指定了父版本则 fork 它；否则 fork 最新版本
    parent_version = parent if parent is not None else chain[-1]
    label = _next_label(chain)

    v = RecipeVersion(
        recipe_id=rec.id,
        parent_id=parent_version.id,
        user_id=user.id,
        version_label=label,
        title=rec.title,
        changes=body.changes,
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return ok(_version_out(v, is_root=False))


@router.get("/{recipe_id}/tree")
async def recipe_tree(
    recipe_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """菜谱DNA进化树：返回该菜谱的版本链（根在前），无版本时合成 v1.0 原版。"""
    rec, _ = await _resolve_recipe_ref(db, recipe_id)
    versions = await _recipe_chain(db, rec.id)

    if not versions:
        # 尚未 fork：合成根节点（v1.0 原版，不入库）
        items = [
            {
                "id": None,
                "recipe_id": str(rec.id),
                "parent_id": None,
                "version_label": "v1.0",
                "title": rec.title,
                "changes": "",
                "is_root": True,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
            }
        ]
    else:
        items = [_version_out(v, v.parent_id is None) for v in versions]

    return ok({"recipe_id": str(rec.id), "title": rec.title, "versions": items})


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
