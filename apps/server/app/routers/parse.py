"""链接/文档解析路由：POST /api/parse/url、POST /api/parse/document。

流程：提取内容（网页/视频/文档）→ 解析 Agent 结构化 QASchema →
落 qa_records（可入会话，历史可查可收藏）→ best-effort 收录 recipe_kb（供"查看完整菜谱"）。

鉴权：需登录；限额：每次解析计一次 AI 调用（复用每日限额）。
"""
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.qa_record import QA_Record
from app.models.user import User
from app.services import extractor
from app.services import kb as kb_service
from app.services.agents import parse_agent
from app.services.llm.client import LLMError
from app.services.llm.embedding import EmbeddingError
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/parse", tags=["parse"])
settings = get_settings()

_KIND_LABEL = {"web": "网页", "video": "视频", "doc": "文档"}


class ParseUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    session_id: UUID | None = None


def _record_out(rec: QA_Record) -> dict:
    answer = rec.answer or {}
    return {
        "id": str(rec.id),
        "question": rec.question,
        "answer": answer,
        "sources": rec.sources,
        "kb_hit": bool(answer.get("kb_hit", False)),
        "kb_id": answer.get("kb_id"),
        "session_id": str(rec.session_id) if rec.session_id else None,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }


async def _do_parse(
    *,
    db: AsyncSession,
    user: User,
    kind: str,
    source_label: str,
    content_text: str,
    sources: list[str] | None,
    session_id: UUID | None,
) -> dict:
    """提取后统一走：LLM 结构化 → 落库 → 收录知识库。"""
    try:
        answer = await parse_agent.run_parse(source_label, content_text)
    except (LLMError, ValueError) as exc:
        raise AppError(f"解析生成失败：{exc}", code=502, status_code=502) from exc

    # 记录解析来源，前端据此渲染来源横幅
    answer["parse_type"] = kind
    answer["parse_source"] = source_label

    question = f"解析{_KIND_LABEL[kind]}：{source_label}"
    record = QA_Record(
        user_id=user.id,
        session_id=session_id,
        question=question,
        answer=answer,
        sources=sources,
    )
    db.add(record)
    await db.flush()
    await kb_service.store_generated_answer_to_kb(db, answer, record.id)
    await record_ai_call(db, user.id, f"parse_{kind}", settings.DEEPSEEK_MODEL)
    await db.commit()
    await db.refresh(record)
    return _record_out(record)


@router.post("/url")
async def parse_url(
    body: ParseUrlRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """解析网页/视频链接 → 结构化菜谱。自动按域名识别类型。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    kind = "video" if extractor.is_video_url(body.url) else "web"
    try:
        if kind == "video":
            extracted = await extractor.extract_video(body.url)
        else:
            extracted = await extractor.extract_web(body.url)
    except extractor.ExtractorError as exc:
        raise AppError(str(exc), code=502, status_code=502) from exc

    label = extracted["title"]
    return ok(
        await _do_parse(
            db=db,
            user=user,
            kind=kind,
            source_label=label,
            content_text=extracted["text"],
            sources=[body.url],
            session_id=body.session_id,
        )
    )


@router.post("/document")
async def parse_document(
    file: UploadFile = File(...),
    session_id: UUID | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """上传 PDF/Word 文档 → 结构化菜谱。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    content = await file.read()
    if not content:
        raise AppError("文件为空", code=400, status_code=400)
    filename = file.filename or "文档"

    try:
        extracted = await extractor.extract_document(filename, content)
    except extractor.ExtractorError as exc:
        raise AppError(str(exc), code=400, status_code=400) from exc

    return ok(
        await _do_parse(
            db=db,
            user=user,
            kind="doc",
            source_label=extracted["title"],
            content_text=extracted["text"],
            sources=None,
            session_id=session_id,
        )
    )
