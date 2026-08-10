"""视觉识别路由：POST /api/vision/recognize（拍照识食材）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.user import User
from app.services import vision as vision_service
from app.services.rate_limit import ensure_within_limit, record_ai_call
from app.services.storage import StorageError, parse_data_url
from app.services.vision import VisionError

router = APIRouter(prefix="/vision", tags=["vision"])
settings = get_settings()


class RecognizeRequest(BaseModel):
    image_base64: str = Field(
        min_length=1,
        max_length=4_000_000,
        description="data:image/...;base64 的图片（parse_data_url 会校验类型与 ≤2MB）",
    )


@router.post("/recognize")
async def recognize(
    body: RecognizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """拍照识食材：识别图中的食材清单（去重）。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    try:
        parse_data_url(body.image_base64)  # 复用 storage 的 data URL 校验（MIME/大小）
    except StorageError as exc:
        raise AppError(str(exc), code=400, status_code=400) from exc

    try:
        ingredients = await vision_service.recognize_ingredients(body.image_base64)
    except VisionError as exc:
        raise AppError(str(exc), code=502, status_code=502) from exc

    await record_ai_call(db, user.id, "vision", settings.ZHIPU_VISION_MODEL)
    await db.commit()
    return ok({"ingredients": ingredients})
