"""语音输入路由：POST /api/voice/transcribe 上传音频 → 百炼 ASR 转文字。"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.user import User
from app.services import asr as asr_service
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/voice", tags=["voice"])
settings = get_settings()

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10MB


@router.post("/transcribe")
async def transcribe_voice(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """上传录音文件（mp3/wav 等），返回识别文字。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    audio = await file.read()
    if not audio:
        raise AppError("音频为空", code=400, status_code=400)
    if len(audio) > MAX_AUDIO_BYTES:
        raise AppError("音频过大（超过 10MB），请缩短录音", code=400, status_code=400)

    mime_type = file.content_type or "audio/mpeg"
    try:
        text = await asr_service.transcribe_audio(audio, mime_type)
    except asr_service.ASRError as exc:
        raise AppError(str(exc), code=502, status_code=502) from exc

    await record_ai_call(db, user.id, "voice", settings.BAILIAN_ASR_MODEL)
    await db.commit()
    return ok({"text": text})
