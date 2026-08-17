"""问答路由：POST /api/qa/ask、POST /api/qa/stream（SSE流式）、GET /api/qa/history、DELETE /api/qa/{id}。

RAG 集成（菜谱知识库）：
- 先向量检索 recipe_kb（HowToCook 种子 + AI 沉淀）
- 命中 → 直接返回知识库答案（免 AI 调用、不计入每日限额），响应带 kb_hit/kb_id
- 未命中 → 走 AI 联网生成，并把结果按菜名自动入库（best-effort，失败不阻断）
"""
import asyncio
import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.qa_record import QA_Record
from app.models.user import User
from app.schemas.ai import QASchema
from app.services import kb as kb_service
from app.services.agents import qa_agent
from app.services.llm.client import LLMError, astream_text
from app.services.llm.embedding import EmbeddingError
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/qa", tags=["qa"])
settings = get_settings()

# 多菜推荐意图的关键词：命中则优先返回多道菜，否则返回单道最佳命中
MULTI_HINT_KEYWORDS = ("推荐", "哪几道", "换换口味", "有什么好做", "来几道", "几道菜", "想吃")

# 「怎么做某菜」类问题的做法动词模式（长优先，避免"怎么做"吞掉"怎么做好吃/怎么做才"）
HOWTO_PATTERNS = (
    "怎么做好吃", "怎么做才", "怎么做", "如何做", "怎样做",
    "怎么弄", "怎么烧", "怎么炖", "怎么炒", "怎么蒸", "怎么煮",
    "的做法", "做法",
)

# 非菜名前缀/后缀，用于剔除"怎么做才不粘锅"这类被误提取的非菜名词
_NON_DISH_PREFIXES = ("不", "别", "想", "可以", "应该", "要不要", "怎么")
_DISH_CLEAN_SUFFIXES = ("更好吃", "才好吃", "最好吃", "比较好吃", "好吃", "最正宗", "简单")


def _clean_dish(dish: str) -> str:
    """去掉菜名里常见的语气后缀，如'红烧肉更好吃' → '红烧肉'。"""
    for suf in _DISH_CLEAN_SUFFIXES:
        if dish.endswith(suf):
            return dish[: -len(suf)]
    return dish


def _extract_dish_for_multi(question: str) -> str | None:
    """从'怎么做/做法'类问题中提取菜名（供多种做法列表与提示词优化用）。

    例：'红烧肉怎么做' → 红烧肉；'怎么做红烧肉更好吃' → 红烧肉；'蒸蛋怎么蒸才嫩' → 蒸蛋；
    '炖肉怎么去腥' → None（技巧问题，不强行提取）；'怎么做才不粘锅' → None（非菜名）。
    """
    q = question.strip().rstrip("？?。！!~～ ")
    # 1) "X怎么做…" / "X的做法"：取做法动词之前的内容作为菜名
    for pat in HOWTO_PATTERNS:
        idx = q.find(pat)
        if 0 < idx <= 12:
            dish = q[:idx].strip("，,、。：: ")
            if 1 <= len(dish) <= 12 and not dish.startswith(_NON_DISH_PREFIXES):
                return dish
    # 2) "怎么做X" / "如何做X"：动词后接菜名
    m = re.match(r"^(?:怎么做|如何做|怎样做)([一-龥]{2,10})", q)
    if m:
        dish = _clean_dish(m.group(1))
        if not dish.startswith(_NON_DISH_PREFIXES):
            return dish
    # 3) 兜底：X怎么Y，且 Y 以口感/质量词开头（如"蒸蛋怎么嫩""红烧肉怎么不腻"）→ X 为菜名。
    #    技巧操作类（"炖肉怎么去腥增香"）Y 以动词开头，不误判。
    idx = q.find("怎么")
    if 0 < idx <= 12:
        rest = re.sub(r"^(不|才|更|才能|才更|又|比较|特别)", "", q[idx + 2:])
        if rest and rest[0] in "嫩滑软脆香鲜酥韧柴硬腻腥老爽糯Q绵烂弹爽口":
            dish = q[:idx].strip("，,、。：: ")
            if 1 <= len(dish) <= 12 and not dish.startswith(_NON_DISH_PREFIXES):
                return dish
    return None


def _extract_howto_dish(question: str) -> str | None:
    """提取"做法类"问题的菜名（怎么做X / X的做法），不处理"X怎么嫩"这类口感/技巧问题。"""
    q = question.strip().rstrip("？?。！!~～ ")
    for pat in HOWTO_PATTERNS:
        idx = q.find(pat)
        if 0 < idx <= 12:
            dish = q[:idx].strip("，,、。：: ")
            if 1 <= len(dish) <= 12 and not dish.startswith(_NON_DISH_PREFIXES):
                return dish
    m = re.match(r"^(?:怎么做|如何做|怎样做)([一-龥]{2,10})", q)
    if m:
        dish = _clean_dish(m.group(1))
        if not dish.startswith(_NON_DISH_PREFIXES):
            return dish
    return None


def _optimize_prompt(question: str) -> str:
    """自动优化提示词：仅"怎么做X"做法类问题 → 提示模型列多种做法并简要介绍。

    "X怎么嫩/怎么不腻"这类技巧问题不在这里优化（走 QA_SYSTEM 的秘诀分类），
    避免被强行要求列多种做法。
    """
    dish = _extract_howto_dish(question)
    if not dish:
        return question
    return (
        f"{question}\n"
        f"（自动优化提示：请先给一句友好的口语开场白，再列出「{dish}」的 2~4 种不同做法/流派，"
        f"每种做法用 1~2 句话介绍其风味特点、关键点与预估时间，不要展开完整步骤。"
        f"仅当用户明确要求详细步骤时再输出完整做法。）"
    )


def _transition_text(intent: str, dish: str) -> str:
    """流式开头打字机过渡语（进行时，即时反馈；确定性文案，不依赖 AI）。"""
    if intent == "recipe_lookup" and dish:
        return f"小伴这就为你去寻找「{dish}」的做法…"
    if intent == "table_menu":
        return "小伴这就为你搭配一桌好菜…"
    if intent == "recommend_dishes":
        return "小伴这就为你挑几道好吃的…"
    if intent == "technique_tips" and dish:
        return f"小伴这就把「{dish}」的秘诀分享给你…"
    return "小伴这就来帮你…"


def _card_intro(question: str, answer: dict, dish: str) -> str:
    """多做法/多菜卡片 intro（完成时，写入 core_secret；确定性模板，快速稳定）。"""
    recs = answer.get("recommendations") or []
    if dish:
        return f"「{dish}」有 {len(recs)} 种经典做法，风味各不相同，小伴都帮你整理好啦"
    if recs:
        return "小伴从美食库里帮你挑了这几道，看看合不合胃口"
    return ""


class QAAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    # 多轮对话会话 id（前端生成 UUID；可空=单轮/旧客户端）
    session_id: UUID | None = None


def _qa_record_out(rec: QA_Record) -> dict:
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


def _answer_to_context(answer: dict) -> str:
    """把结构化回答压缩成一句话，作为多轮上下文的 assistant 内容。"""
    recs = answer.get("recommendations") or []
    if recs:
        items = []
        for r in recs:
            name = (r or {}).get("name") or ""
            mins = (r or {}).get("time_minutes") or 0
            items.append(f"{name}（{mins}分钟）" if mins else name)
        return "我推荐了：" + "、".join(items)
    dish = answer.get("dish_name") or ""
    secret = answer.get("core_secret") or ""
    return (f"{dish}：" if dish else "") + secret


async def _load_session_context(
    db: AsyncSession, user_id: UUID, session_id: UUID | None, limit: int = 8
) -> list[dict]:
    """读取会话最近 N 条消息，构造多轮上下文 [{"role","content"}, ...]。

    只取最近 limit 条（=limit/2 轮问答），控制 token；按时间升序返回。
    """
    if session_id is None:
        return []
    result = await db.execute(
        select(QA_Record)
        .where(QA_Record.user_id == user_id, QA_Record.session_id == session_id)
        .order_by(QA_Record.created_at.desc())
        .limit(limit)
    )
    records = list(reversed(result.scalars().all()))
    messages: list[dict] = []
    for rec in records:
        messages.append({"role": "user", "content": rec.question})
        messages.append({"role": "assistant", "content": _answer_to_context(rec.answer or {})})
    return messages


# ---------- 知识库命中 → 结构化答案 ----------

def _single_recipe_answer(entry) -> dict:
    return {
        "core_secret": entry.summary or (entry.tips[0] if entry.tips else ""),
        "dish_name": entry.title,
        "ingredients": entry.ingredients,
        "steps": entry.steps,
        "prep_steps": entry.prep_steps,
        "cook_steps": entry.cook_steps,
        "avoid_pitfalls": entry.tips,
        "sources": [],
        "recommendations": None,
        "kb_hit": True,
        "kb_id": str(entry.id),
    }


def _single_tip_answer(entry) -> dict:
    return {
        "core_secret": (entry.summary or entry.content or entry.title)[:300],
        "dish_name": entry.title,
        "ingredients": [],
        "steps": [],
        "avoid_pitfalls": [],
        "sources": [],
        "recommendations": None,
        "kb_hit": True,
        "kb_id": str(entry.id),
    }


def _multi_recipe_answer(recipes: list[dict]) -> dict:
    return {
        "core_secret": "",  # 卡片 intro 由 _card_intro 确定性模板填写（见 ask/ask_stream）
        "dish_name": "",
        "ingredients": [],
        "steps": [],
        "avoid_pitfalls": [],
        "sources": [],
        "recommendations": [
            {
                "name": e.title,
                "core_secret": e.summary or (e.tips[0] if e.tips else ""),
                "time_minutes": e.time_minutes,
                "ingredients": e.ingredients,
                "kb_id": str(e.id),
            }
            for h in recipes
            for e in [h["entry"]]
        ],
        "kb_hit": True,
        "kb_id": None,
    }


# 多菜推荐：类别按"待客一桌"的优先级排序（硬菜优先），避免 top-k 相似度全取同类
_TABLE_CATEGORY_ORDER = ("肉菜", "水产", "素菜", "汤", "主食", "早餐", "甜点", "饮品", "半成品", "佐料", "")


def _pick_diverse_recipes(recipes: list[dict], k: int = 4) -> list[dict]:
    """从相似度命中中挑 k 道类别分散、荤素搭配的菜（多菜推荐专用）。

    解决 top-k 相似度截取导致"推荐一桌"返回 4 碗汤/4 碗面这类同质结果。
    贪心：先按类别优先级轮转，每类取相似度最高的 1 道；类别不足再从剩余按相似度补足。
    多做法（同一道菜的变体，如红烧肉的几种流派）不走这里。
    """
    if len(recipes) <= k:
        return recipes
    by_cat: dict[str, list[dict]] = {}
    for h in recipes:
        by_cat.setdefault(h["entry"].category, []).append(h)
    for lst in by_cat.values():
        lst.sort(key=lambda h: h["similarity"], reverse=True)

    picked: list[dict] = []
    used: set[str] = set()
    for cat in _TABLE_CATEGORY_ORDER:
        if len(picked) >= k:
            break
        lst = by_cat.get(cat)
        if lst and cat not in used:
            picked.append(lst.pop(0))
            used.add(cat)
    leftovers = [h for lst in by_cat.values() for h in lst]
    leftovers.sort(key=lambda h: h["similarity"], reverse=True)
    for h in leftovers:
        if len(picked) >= k:
            break
        picked.append(h)
    return picked


def _kb_to_qa_answer(question: str, hits: list[dict], dish_hint: str = "") -> dict | None:
    """知识库直答（仅 recipe_lookup 意图、知识库命中时用，免 AI 秒回）。

    - 同菜名变体 ≥2 → 列出多种做法；
    - 恰好 1 个同名做法 → 单菜全量；
    - 路由确认查这道菜但无精确同名，且 top 命中为高相似度菜谱（别名/同菜，如"蒸蛋"→"蒸水蛋"）→ 单菜；
    - 其余 → None（交给 AI 生成）。
    dish_hint: 路由智能体给出的标准菜名，优先于字符串提取。
    """
    if not hits:
        return None
    dish = dish_hint or _extract_dish_for_multi(question)
    if dish:
        variants = [h for h in hits if h["entry"].kind == "recipe" and dish in h["entry"].title]
        if len(variants) >= 2:
            return _multi_recipe_answer(variants[:4])
        if len(variants) == 1:
            return _single_recipe_answer(variants[0]["entry"])
        top = hits[0]
        if top["entry"].kind == "recipe" and top["similarity"] >= 0.7:
            return _single_recipe_answer(top["entry"])
        return None
    if any(k in question for k in ("怎么", "如何", "怎样")):
        top = hits[0]
        if top["entry"].kind == "tip":
            return _single_tip_answer(top["entry"])
    return None


def _kb_context_text(hits: list[dict], limit: int = 6) -> str:
    """把检索到的知识库条目压成给 AI 的上下文参考块（组合/推荐类问题取材用）。"""
    if not hits:
        return ""
    lines = []
    for h in hits[:limit]:
        e = h["entry"]
        if e.kind == "tip":
            brief = (e.summary or e.content or "")[:80]
            lines.append(f"- 技巧「{e.title}」：{brief}")
        else:
            brief = (e.summary or "")[:80]
            time_txt = f"{e.time_minutes}分钟" if e.time_minutes else ""
            meta = e.category or "家常"
            if time_txt:
                meta += f"，{time_txt}"
            lines.append(f"- 菜「{e.title}」（{meta}）：{brief}")
    return "美食库菜谱/技巧（可优先参考）：\n" + "\n".join(lines)


def _kb_multi_fallback(question: str, hits: list[dict]) -> dict | None:
    """AI 限额用尽/不可用时的降级：'推荐几道'类问题用知识库多菜直答兜底。"""
    if not hits:
        return None
    recipes = [h for h in hits if h["entry"].kind == "recipe"]
    if any(k in question for k in MULTI_HINT_KEYWORDS) and len(recipes) >= 2:
        return _multi_recipe_answer(_pick_diverse_recipes(recipes, 4))
    return None


async def _store_generated_to_kb(db: AsyncSession, answer: dict, record_id: UUID) -> None:
    """AI 生成结果按菜名入库（best-effort，向量服务失败静默，不阻断主流程）。"""
    await kb_service.store_generated_answer_to_kb(db, answer, record_id)


async def _bump_hits(db: AsyncSession, hits: list[dict]) -> None:
    for h in hits:
        await kb_service.increment_hit(db, h["entry"])


async def _retrieve_hits(db: AsyncSession, question: str) -> list[dict]:
    """检索知识库（embedding 失败静默返回空列表）。"""
    try:
        return await kb_service.search_kb(db, question)
    except EmbeddingError:
        return []


# ---------- 接口 ----------

@router.post("/ask")
async def ask(
    body: QAAskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """提问：意图路由智能体先判断用户想问什么，再分发。

    - recipe_lookup + 知识库命中 → KB 直答秒回（多做法/单菜，免 AI）；
    - recipe_lookup + KB 缺菜 / technique_tips / recommend_dishes / table_menu / general → AI 生成，
      检索结果作为「知识库参考」喂给模型（KB 覆盖到则不联网）；
    - AI 限额用尽时降级为知识库直答/多菜兜底。
    多轮：携带 session_id 时注入最近几轮上下文（路由与生成都用），并落库到该会话。
    """
    hits = await _retrieve_hits(db, body.question)
    if hits:
        await _bump_hits(db, hits[:3])
    history = await _load_session_context(db, user.id, body.session_id)
    router = await qa_agent.route_intent(body.question, history)
    intent = router["intent"]

    # 查菜谱且知识库命中 → 免 AI 秒回
    if intent == "recipe_lookup":
        direct = (
            _kb_to_qa_answer(body.question, hits, dish_hint=router.get("dish_name") or "")
            if hits
            else None
        )
        if direct is not None:
            # 多做法/多菜：卡片 intro 用确定性模板（快速稳定，不依赖 AI）
            dish = router.get("dish_name") or _extract_dish_for_multi(body.question) or ""
            direct["core_secret"] = _card_intro(body.question, direct, dish)
            record = QA_Record(
                user_id=user.id,
                session_id=body.session_id,
                question=body.question,
                answer=direct,
                sources=None,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            return ok(_qa_record_out(record))

    # AI 路径：限额用尽时降级为知识库直答/多菜兜底
    try:
        await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)
    except AppError as exc:
        fallback = _kb_to_qa_answer(body.question, hits) or _kb_multi_fallback(body.question, hits)
        if fallback is not None:
            record = QA_Record(
                user_id=user.id,
                session_id=body.session_id,
                question=body.question,
                answer=fallback,
                sources=None,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            return ok(_qa_record_out(record))
        raise

    # 自动优化提示词（仅做法类）+ 注入知识库上下文；KB 覆盖到则不联网
    prompt = _optimize_prompt(body.question)
    ctx = _kb_context_text(hits)
    if ctx:
        prompt = f"{prompt}\n\n{ctx}"
    use_web = settings.AI_ENABLE_SEARCH and not hits
    out = await qa_agent.run_qa(prompt, history=history, enable_search=use_web)
    if out["error"] or out["result"] is None:
        raise AppError(out["error"] or "生成失败，请稍后重试", code=502, status_code=502)

    answer = out["result"]
    record = QA_Record(
        user_id=user.id,
        session_id=body.session_id,
        question=body.question,
        answer=answer,
        sources=answer.get("sources"),
    )
    db.add(record)
    await db.flush()  # 先拿到 record.id（source_id 溯源用）
    await _store_generated_to_kb(db, answer, record.id)
    # store_generated_answer_to_kb 原地修改 answer 回填 kb_id，但 SQLAlchemy flush 后不追踪
    # JSONB 列的 dict 原地修改 → 不标记 dirty 的话 commit 不会重新序列化，库里仍是旧值。
    flag_modified(record, "answer")
    await record_ai_call(db, user.id, "qa", settings.DEEPSEEK_MODEL)
    await db.commit()
    await db.refresh(record)
    return ok(_qa_record_out(record))


def _extract_json_obj(text: str) -> dict:
    """从流式累积的模型输出中提取 JSON 对象。

    兼容三种输出形态：
    - 双标签：<answer>…</answer><data>{json}</data>（新版流式）
    - markdown 代码围栏（```json … ```）
    - 纯 JSON + 尾随文字
    先剥标签/围栏整体解析；失败则从第一个 { 起，从后往前逐个 } 截断尝试（处理尾随垃圾/截断）。
    """
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    # 优先取 <data> 后的 JSON；无则剥掉 <answer> 文本
    m = re.search(r"<data>\s*(\{[\s\S]*\})", t)
    if m:
        t = m.group(1)
    else:
        t = re.sub(r"<answer>[\s\S]*", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start = t.find("{")
    if start == -1:
        raise ValueError("模型输出中未找到 JSON")
    for i in range(len(t) - 1, start, -1):
        if t[i] != "}":
            continue
        try:
            return json.loads(t[start : i + 1])
        except json.JSONDecodeError:
            continue
    raise ValueError("模型输出中未找到合法 JSON")


async def _parse_stream_result(text: str) -> dict | None:
    """流式累积文本 → 语义校验（推荐需清单/单菜需菜名+步骤）。"""
    try:
        data = _extract_json_obj(text)
    except Exception:  # noqa: BLE001
        return None
    try:
        parsed = QASchema.model_validate(data)
        has_recs = bool(parsed.recommendations)
        has_single = bool(parsed.dish_name.strip()) and len(parsed.steps) >= 1
        if has_recs or has_single:
            return data
    except Exception:  # noqa: BLE001
        pass
    return None


@router.post("/stream")
async def ask_stream(
    body: QAAskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """流式问答：意图路由智能体判断 → 查菜谱且知识库命中则直接 done（免 AI 秒回）；其余模型逐字输出 → SSE。

    SSE 事件：
      {"type":"delta","text":"核心秘诀的逐字片段"}
      {"type":"done","data":{...结构化回答...}}
      {"type":"error","message":"..."}
    """
    # 先查知识库 + 意图路由（KB 覆盖到则不联网）
    try:
        kb_hits = await kb_service.search_kb(db, body.question)
    except EmbeddingError:
        kb_hits = []
    history = await _load_session_context(db, user.id, body.session_id)
    router = await qa_agent.route_intent(body.question, history)
    intent = router["intent"]
    kb_answer = (
        _kb_to_qa_answer(body.question, kb_hits, dish_hint=router.get("dish_name") or "")
        if intent == "recipe_lookup" and kb_hits
        else None
    )

    async def event_stream():
        if kb_answer is not None:
            await _bump_hits(db, kb_hits[:3])
            dish = router.get("dish_name") or _extract_dish_for_multi(body.question) or ""
            # 多做法/多菜：先打字机过渡语（进行时即时反馈），卡片 intro 用确定性模板
            if kb_answer.get("recommendations"):
                transition = _transition_text("recipe_lookup", dish)
                for ch in transition:
                    yield f"data: {json.dumps({'type': 'delta', 'text': ch})}\n\n"
                    await asyncio.sleep(0.03)
                kb_answer["core_secret"] = _card_intro(body.question, kb_answer, dish)
            # 单菜命中：免 AI 秒出，保持一个 done（无过渡语，核心秘诀即 entry.summary）
            record = QA_Record(
                user_id=user.id,
                session_id=body.session_id,
                question=body.question,
                answer=kb_answer,
                sources=None,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            yield f"data: {json.dumps({'type': 'done', 'data': _qa_record_out(record)}, ensure_ascii=False)}\n\n"
            return

        if kb_hits:
            await _bump_hits(db, kb_hits[:3])
        # AI 路径：限额用尽时降级为知识库多菜直答（免费兜底）
        try:
            await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)
        except AppError as exc:
            fallback = _kb_multi_fallback(body.question, kb_hits)
            if fallback is not None:
                record = QA_Record(
                    user_id=user.id,
                    session_id=body.session_id,
                    question=body.question,
                    answer=fallback,
                    sources=None,
                )
                db.add(record)
                await db.commit()
                await db.refresh(record)
                yield f"data: {json.dumps({'type': 'done', 'data': _qa_record_out(record)}, ensure_ascii=False)}\n\n"
                return
            yield f"data: {json.dumps({'type': 'error', 'message': exc.message}, ensure_ascii=False)}\n\n"
            return

        # 过渡语先发：打字机即时反馈（进行时），AI 生成等待期不干等
        dish = router.get("dish_name") or _extract_dish_for_multi(body.question) or ""
        transition = _transition_text(intent, dish)
        for ch in transition:
            yield f"data: {json.dumps({'type': 'delta', 'text': ch})}\n\n"
            await asyncio.sleep(0.03)

        # 自动优化提示词 + 注入知识库上下文（AI 在真实菜谱基础上编排）；KB 覆盖到则不联网
        prompt = _optimize_prompt(body.question)
        ctx = _kb_context_text(kb_hits)
        if ctx:
            prompt = f"{prompt}\n\n{ctx}"
        use_web = settings.AI_ENABLE_SEARCH and not kb_hits

        # 有界重试：瞬时 LLM 错误/解析失败都重试（首次可联网但不强制——模型能答就不搜，大幅提速）；
        # 重试前发 reset 事件，让前端清掉半截回答再重新打字；
        # 外层兜底：任何意外异常都发 error 事件——绝不挂死连接。
        max_attempts = settings.AI_MAX_RETRIES + 1
        try:
            data = None
            for attempt in range(max_attempts):
                attempt_web = use_web and attempt == 0
                buf = ""
                fwd_pos = 0        # 已转发到 buf 的位置（<answer> 打字机用）
                answer_done = False  # 已遇到 <data>，停止转发
                try:
                    async for delta in astream_text(
                        model=settings.DEEPSEEK_MODEL,
                        system=qa_agent.QA_SYSTEM,
                        user=prompt,
                        history=history,
                        enable_search=attempt_web,
                        timeout_seconds=settings.AI_TIMEOUT_SECONDS * 2,  # 流式超时放宽
                    ):
                        buf += delta
                        # 实时转发 <answer> 内容作为打字机（遇到 <data> 即停，不转发 JSON）
                        if not answer_done:
                            di = buf.find("<data")
                            limit = di if di != -1 else len(buf)
                            if di != -1:
                                answer_done = True
                            ai = buf.find("<answer>")
                            if ai != -1:
                                start = max(ai + len("<answer>"), fwd_pos)
                                if start < limit:
                                    chunk = buf[start:limit].replace("</answer>", "")
                                    fwd_pos = limit
                                    if chunk:
                                        yield f"data: {json.dumps({'type': 'delta', 'text': chunk}, ensure_ascii=False)}\n\n"
                except LLMError as exc:
                    if attempt < max_attempts - 1:
                        yield f"data: {json.dumps({'type': 'reset'})}\n\n"
                        continue
                    yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                    return
                data = await _parse_stream_result(buf)
                if data is not None:
                    break
                if attempt < max_attempts - 1:
                    yield f"data: {json.dumps({'type': 'reset'})}\n\n"
                    continue
                yield f"data: {json.dumps({'type': 'error', 'message': 'AI 回答生成失败，请稍后重试'})}\n\n"
                return

            # 落库 + AI 生成结果入库（同步，kb_id 回填进响应）
            record = QA_Record(
                user_id=user.id,
                session_id=body.session_id,
                question=body.question,
                answer=data,
                sources=data.get("sources"),
            )
            db.add(record)
            await db.flush()  # 先拿到 record.id
            await _store_generated_to_kb(db, data, record.id)
            flag_modified(record, "answer")  # kb_id 回填是原地 dict 修改，需显式标记 dirty 以便 commit 重新序列化
            await record_ai_call(db, user.id, "qa", settings.DEEPSEEK_MODEL)
            await db.commit()
            await db.refresh(record)

            out = _qa_record_out(record)

            # 过渡语+回答正文已逐字先行，这里直接出卡片
            yield f"data: {json.dumps({'type': 'done', 'data': out}, ensure_ascii=False)}\n\n"
        except Exception:  # noqa: BLE001 兜底：任何异常都发 error 事件，不挂死 SSE 连接
            yield f"data: {json.dumps({'type': 'error', 'message': '回答生成失败，请稍后重试'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/session/{session_id}")
async def session_messages(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回某会话的全部消息（按时间升序，仅限本人），供对话页恢复历史。"""
    result = await db.execute(
        select(QA_Record)
        .where(QA_Record.user_id == user.id, QA_Record.session_id == session_id)
        .order_by(QA_Record.created_at.asc())
    )
    records = result.scalars().all()
    return ok([_qa_record_out(r) for r in records])


@router.get("/sessions")
async def sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
) -> dict:
    """最近 N 个会话（按最后活动时间降序）：标题=首条问题，含消息数/最后问题/最后时间。

    会话量小（≤20），每个会话单独取首尾问题可接受。
    """
    agg = await db.execute(
        select(
            QA_Record.session_id,
            func.count(QA_Record.id).label("msg_count"),
            func.max(QA_Record.created_at).label("last_at"),
        )
        .where(QA_Record.user_id == user.id, QA_Record.session_id.isnot(None))
        .group_by(QA_Record.session_id)
        .order_by(func.max(QA_Record.created_at).desc())
        .limit(limit)
    )
    rows = agg.all()
    out = []
    for row in rows:
        sid = row.session_id
        first = await db.scalar(
            select(QA_Record.question)
            .where(QA_Record.user_id == user.id, QA_Record.session_id == sid)
            .order_by(QA_Record.created_at.asc())
            .limit(1)
        )
        last = await db.scalar(
            select(QA_Record.question)
            .where(QA_Record.user_id == user.id, QA_Record.session_id == sid)
            .order_by(QA_Record.created_at.desc())
            .limit(1)
        )
        out.append(
            {
                "session_id": str(sid),
                "title": first or "",
                "last_question": last or "",
                "msg_count": int(row.msg_count),
                "last_at": row.last_at.isoformat() if row.last_at else None,
            }
        )
    return ok(out)


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除整个会话（仅限本人）。"""
    await db.execute(
        delete(QA_Record).where(QA_Record.user_id == user.id, QA_Record.session_id == session_id)
    )
    await db.commit()
    return ok(message="会话已删除")


@router.get("/history")
async def history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """最近 20 条问答历史。"""
    result = await db.execute(
        select(QA_Record)
        .where(QA_Record.user_id == user.id)
        .order_by(QA_Record.created_at.desc())
        .limit(20)
    )
    records = result.scalars().all()
    return ok([_qa_record_out(r) for r in records])


@router.delete("/{record_id}")
async def delete_record(
    record_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除单条历史（仅限本人）。"""
    result = await db.execute(
        select(QA_Record).where(QA_Record.id == record_id, QA_Record.user_id == user.id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise AppError("记录不存在", code=404, status_code=404)
    await db.execute(delete(QA_Record).where(QA_Record.id == record_id))
    await db.commit()
    return ok(message="已删除")
