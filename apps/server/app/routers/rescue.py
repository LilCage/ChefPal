"""黑暗料理拯救路由：POST /api/rescue/diagnose（翻车现场诊断，原型 05 屏1）。

复用智谱 GLM 视觉服务（diagnose_dish），与 /vision/recognize 同构：data URL 校验 + 风控 + record_ai_call。
"""
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

router = APIRouter(prefix="/rescue", tags=["rescue"])
settings = get_settings()


class DiagnoseRequest(BaseModel):
    image_base64: str = Field(
        min_length=1,
        max_length=4_000_000,
        description="data:image/...;base64 的翻车现场照片（≤2MB）",
    )


@router.post("/diagnose")
async def diagnose(
    body: DiagnoseRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """黑暗料理拯救：上传翻车照 → AI 诊断问题 + 补救方案。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    try:
        parse_data_url(body.image_base64)  # 复用 data URL 校验（MIME/大小）
    except StorageError as exc:
        raise AppError(str(exc), code=400, status_code=400) from exc

    try:
        result = await vision_service.diagnose_dish(body.image_base64)
    except VisionError as exc:
        raise AppError(str(exc), code=502, status_code=502) from exc

    await record_ai_call(db, user.id, "rescue", settings.ZHIPU_VISION_MODEL)
    await db.commit()
    return ok(result)
