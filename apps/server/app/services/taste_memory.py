"""AI 口味记忆服务（EXT-13.1/13.2）：记录行为信号 → 聚合口味画像 → 注入推荐。

三类信号（表 taste_signals）：
- favorite_recipe：收藏 AI 菜谱时记 style（风味标签）
- like_post：点赞社区作品时记 topic（话题）
- favorite_qa：收藏问答时记 question 关键词

聚合输出画像（供 recipe_agent 注入，EXT-13.2）：
- preferred_styles：top N 常收藏风味
- preferred_topics：top N 常点赞话题
注入策略：仅当画像足够丰富（累计信号 ≥3 条）才注入，避免噪音。
"""
from collections import Counter
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.taste_signal import TasteSignal

# 聚合窗口：最近 30 天
SIGNAL_WINDOW_DAYS = 30
# 注入阈值：至少累计 N 条信号才注入画像（防早期噪音）
INJECT_MIN_SIGNALS = 3
# 画像各维度保留 top N
TOP_N = 3


async def record_signal(
    db: AsyncSession, user_id: UUID, signal_type: str, value: str
) -> TasteSignal:
    """记录一条口味信号（去空格、限长）。空值跳过。"""
    v = value.strip()
    if not v:
        raise ValueError("信号值不能为空")
    sig = TasteSignal(user_id=user_id, signal_type=signal_type, value=v[:64])
    db.add(sig)
    await db.flush()
    return sig


async def summarize_taste(
    db: AsyncSession, user_id: UUID
) -> dict:
    """聚合近 30 天信号 → 口味画像 {preferred_styles, preferred_topics, total_signals}。"""
    rows = await db.execute(
        select(TasteSignal.signal_type, TasteSignal.value)
        .where(TasteSignal.user_id == user_id)
        .order_by(TasteSignal.created_at.desc())
    )
    pairs = [(t, v) for t, v in rows.all()]

    styles: list[str] = [v for t, v in pairs if t == "favorite_recipe"]
    topics: list[str] = [v for t, v in pairs if t == "like_post"]
    qa_words: list[str] = [v for t, v in pairs if t == "favorite_qa"]

    def top(items: list[str], n: int) -> list[str]:
        return [v for v, _ in Counter(items).most_common(n)]

    return {
        "preferred_styles": top(styles, TOP_N),
        "preferred_topics": top(topics, TOP_N),
        "recent_qa_keywords": top(qa_words, 5),
        "total_signals": len(pairs),
    }


def build_injection_text(profile: dict) -> str:
    """把口味画像转成可注入 recipe_agent 的自然语言片段；信号不足返回空串。"""
    if profile.get("total_signals", 0) < INJECT_MIN_SIGNALS:
        return ""
    parts = []
    styles = profile.get("preferred_styles") or []
    topics = profile.get("preferred_topics") or []
    if styles:
        parts.append("根据你的收藏习惯，你更喜欢这些风味：" + "、".join(styles))
    if topics:
        parts.append("你常关注的话题：" + "、".join(topics))
    return "；".join(parts)


async def clear_signals(db: AsyncSession, user_id: UUID) -> int:
    """清空用户全部口味信号，返回删除条数。"""
    rows = await db.execute(
        select(TasteSignal).where(TasteSignal.user_id == user_id)
    )
    sigs = list(rows.scalars())
    for s in sigs:
        await db.delete(s)
    await db.flush()
    return len(sigs)


async def count_signals(db: AsyncSession, user_id: UUID) -> int:
    """当前用户累计信号数。"""
    row = await db.execute(
        select(func.count()).select_from(TasteSignal).where(TasteSignal.user_id == user_id)
    )
    return row.scalar_one()
