"""菜谱知识库路由：查询详情 / 按菜名查库 / 未收录时 AI 现生成。

- GET  /api/kb/recipes?q=菜名  → 多菜推荐"菜名点详情"用，精确/后缀兜底查库
- GET  /api/kb/{id}            → 按 id 取条目
- POST /api/kb/generate        → 菜名未收录时 AI 现生成完整做法并入库
"""
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai import QASchema
from app.services import kb as kb_service
from app.services.llm.client import LLMError, ainvoke_json
from app.services.llm.embedding import EmbeddingError
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/kb", tags=["kb"])
settings = get_settings()

KB_GENERATE_SYSTEM = """你是资深中餐厨师。用户给出一道菜名，请生成这道菜的完整做法。
只输出 JSON，不要多余文字。JSON 结构：
{
  "dish_name": "菜名",
  "core_secret": "核心秘诀，一句话点破关键",
  "ingredients": ["食材1", "食材2"],
  "steps": ["1. 步骤（明确火候与大致时长）", "2. ...", "3. ..."],
  "avoid_pitfalls": ["避坑1", "避坑2"]
}
硬性要求：步骤至少 3 步，写给厨房小白；严格规避常见过敏原并在避坑中提示。
安全要求：输出为通用烹饪建议，不构成医疗/营养处方。"""


class KBGenerateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=50)
    # 已收录但无完整步骤（AI 推荐条目标签）时传 true：重新生成完整做法并覆盖补全
    force: bool = False


def _out(entry) -> dict:
    return kb_service.to_kb_out(entry)


@router.get("/recipes")
async def recipe_by_title(
    q: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """按菜名查知识库菜谱（多菜推荐点详情用）。未收录返回 404 引导现生成。"""
    entry = await kb_service.get_kb_entry_by_title(db, q, kind="recipe")
    if entry is None:
        raise AppError("菜谱暂未收录，可尝试让美食库生成", code=404, status_code=404)
    await kb_service.increment_hit(db, entry)
    await db.commit()
    return ok(_out(entry))


@router.get("/{entry_id}")
async def get_entry(
    entry_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    entry = await kb_service.get_kb_entry(db, entry_id)
    if entry is None:
        raise AppError("条目不存在", code=404, status_code=404)
    return ok(_out(entry))


@router.post("/generate")
async def generate(
    body: KBGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """菜名未收录时，AI 现生成完整做法并入库；已收录（非 HowToCook）且 force=true 时重新生成补全步骤。

    force 场景：知识库里的"推荐条目"（AI 多做法/多菜推荐入库，只有一句摘要、无步骤）——
    前端 kb-detail 检测到无步骤时传 force=true，AI 生成完整做法覆盖补全。
    """
    existing = await kb_service.get_kb_entry_by_title(db, body.title, kind="recipe")
    if existing is not None and (not body.force or existing.source_type == kb_service.SOURCE_HOWTOCOOK):
        await kb_service.increment_hit(db, existing)
        await db.commit()
        return ok({**_out(existing), "from_kb": True})

    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)
    try:
        data = await ainvoke_json(
            model=settings.DEEPSEEK_MODEL,
            system=KB_GENERATE_SYSTEM,
            user=f"请生成「{body.title}」这道菜的完整做法",
            enable_search=False,
        )
    except LLMError as exc:
        raise AppError(str(exc), code=502, status_code=502) from exc

    try:
        parsed = QASchema.model_validate(data)
    except Exception:  # noqa: BLE001
        parsed = None
    if parsed is None or not parsed.dish_name.strip() or len(parsed.steps) < 1:
        raise AppError("菜谱生成失败，请稍后重试", code=502, status_code=502)

    # 覆盖补全时沿用原条目标题（AI 返回的菜名可能略有出入，避免新建一条）
    title = (existing.title if existing else parsed.dish_name.strip()) or body.title
    try:
        entry = await kb_service.upsert_kb_entry(
            db,
            kind="recipe",
            title=title,
            summary=parsed.core_secret,
            ingredients=parsed.ingredients,
            steps=parsed.steps,
            tips=parsed.avoid_pitfalls,
            source_type=kb_service.SOURCE_AI_RECIPE,
            source_id=str(uuid.uuid4()),
        )
    except EmbeddingError as exc:
        raise AppError(str(exc), code=502, status_code=502) from exc

    await record_ai_call(db, user.id, "kb_generate", settings.DEEPSEEK_MODEL)
    await db.commit()
    return ok({**_out(entry), "from_kb": False})
