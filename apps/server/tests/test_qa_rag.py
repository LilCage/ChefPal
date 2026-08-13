"""RAG 集成测试：知识库命中直接返回 / 未命中 AI 生成并入库 / 命中不占限额。

知识库检索（search_kb）用 mock 注入命中列表；真实插入 RecipeKB 行供回显。
AI 结果入库用 mock embedding（确定性向量），不调真实 API。
"""
import json

import pytest
from sqlalchemy import func, select

from app.models.ai_call import AICall
from app.models.recipe_kb import RecipeKB
from app.routers import qa as qa_router
from app.services import kb as kb_service
from app.services.agents import qa_agent

DIM = 1024


def _v(*idx: int) -> list[float]:
    v = [0.0] * DIM
    for i in idx:
        v[i] = 1.0
    return v


async def _make_entry(
    db,
    *,
    title: str,
    kind: str = "recipe",
    summary: str = "简介",
    steps: list[str] | None = None,
    prep_steps: list[str] | None = None,
    cook_steps: list[str] | None = None,
    ingredients: list[str] | None = None,
    tips: list[str] | None = None,
    category: str = "肉菜",
) -> RecipeKB:
    e = RecipeKB(
        kind=kind,
        title=title,
        summary=summary if kind == "recipe" else "",  # 技巧条目 summary 为空，用 content
        content="" if kind == "recipe" else "技巧正文",
        ingredients=ingredients or [],
        steps=steps or [],
        prep_steps=prep_steps or [],
        cook_steps=cook_steps or [],
        tips=tips or [],
        time_minutes=10,
        difficulty="简单",
        style="",
        category=category,
        source_type="howtocook",
        source_id=f"dishes/x/{title}.md",
        hit_count=0,
        embedding=_v(0),
    )
    db.add(e)
    return e


def _mock_hits(monkeypatch, hits: list[dict]):
    async def _fake(db, query, **kw):
        return hits

    monkeypatch.setattr(kb_service, "search_kb", _fake)


def _mock_router(monkeypatch, intent: str, dish: str = ""):
    """mock 意图路由智能体（避免真实调 DeepSeek）。"""

    async def _fake(question, history=None):
        return {"intent": intent, "dish_name": dish, "needs_full_recipe": False, "confidence": "high"}

    monkeypatch.setattr(qa_agent, "route_intent", _fake)


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        events.append(json.loads(line[len("data:"):].strip()))
    return events


# ---------- 单菜命中 ----------


async def test_ask_single_recipe_hit_returns_kb(client, auth_headers, db, monkeypatch):
    e = await _make_entry(
        db, title="红烧肉",
        steps=["切块", "焯水", "小火焖 40 分钟"],
        prep_steps=["1. 切块", "2. 焯水"],
        cook_steps=["1. 小火焖 40 分钟"],
        tips=["不要大火焯水"],
    )
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": e, "similarity": 0.8}])
    _mock_router(monkeypatch, "recipe_lookup", "红烧肉")

    res = client.post("/api/qa/ask", json={"question": "红烧肉怎么做不腻"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kb_hit"] is True
    assert data["kb_id"] == str(e.id)
    ans = data["answer"]
    assert ans["dish_name"] == "红烧肉"
    # 步骤切分为 食材处理 / 烹饪步骤
    assert ans["prep_steps"] == ["1. 切块", "2. 焯水"]
    assert ans["cook_steps"] == ["1. 小火焖 40 分钟"]
    assert ans["avoid_pitfalls"] == ["不要大火焯水"]
    assert ans["recommendations"] is None

    # 命中不调 AI（ai_calls 为空）
    assert (await db.execute(select(func.count()).select_from(AICall))).scalar() == 0
    # 已入历史且带 kb_hit
    hist = client.get("/api/qa/history", headers=auth_headers).json()["data"]
    assert hist and hist[0]["kb_hit"] is True


# ---------- 多菜命中 ----------


async def test_ask_multi_dish_routes_to_ai_with_kb_context(client, auth_headers, db, monkeypatch):
    """'推荐几道' 不再由 KB 直答 → 走 AI，且检索到的知识库菜作为上下文喂给模型。"""
    e1 = await _make_entry(db, title="凉拌黄瓜", summary="拍碎后杀水", steps=["拍", "拌"], category="素菜")
    e2 = await _make_entry(db, title="凉拌木耳", summary="焯水过凉", steps=["焯", "拌"], category="素菜")
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": e, "similarity": 0.70 - i * 0.01} for i, e in enumerate([e1, e2])])
    _mock_router(monkeypatch, "recommend_dishes")

    seen = {}

    async def _fake_run_qa(question, history=None, enable_search=True):
        seen["question"] = question
        seen["enable_search"] = enable_search
        return {
            "result": {
                "core_secret": "好嘞！我帮你挑了几道～",
                "dish_name": "",
                "ingredients": [],
                "steps": [],
                "avoid_pitfalls": [],
                "sources": [],
                "recommendations": [
                    {"name": "凉拌黄瓜", "core_secret": "拍碎杀水更脆", "time_minutes": 10, "ingredients": ["黄瓜"]},
                    {"name": "凉拌木耳", "core_secret": "焯水过凉更爽口", "time_minutes": 15, "ingredients": ["木耳"]},
                ],
            },
            "error": None,
        }

    monkeypatch.setattr(qa_agent, "run_qa", _fake_run_qa)

    async def _fake_emb(texts, *, input_type="document"):
        return [[0.5] * DIM for _ in texts]

    monkeypatch.setattr(kb_service, "aembed_texts", _fake_emb)

    res = client.post("/api/qa/ask", json={"question": "推荐几道凉拌菜"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kb_hit"] is False  # 走 AI，不是直答
    recs = data["answer"]["recommendations"]
    assert [r["name"] for r in recs] == ["凉拌黄瓜", "凉拌木耳"]
    # 检索到的知识库菜被作为上下文喂给了模型
    assert "凉拌黄瓜" in seen["question"]
    assert "美食库" in seen["question"]
    # KB 覆盖到 → 不联网（enable_search=False）
    assert seen["enable_search"] is False
    # AI 结果已入库（按菜名）
    cnt = (
        await db.execute(select(func.count()).select_from(RecipeKB).where(RecipeKB.title == "凉拌黄瓜"))
    ).scalar()
    assert cnt == 1


# ---------- 多菜推荐：类别分散（避免一桌全是汤/面） ----------


async def test_pick_diverse_recipes_covers_categories(db):
    """多菜挑选要类别分散（硬菜+素菜+汤+主食），不能取相似度 top4 全同类。"""
    soup1 = await _make_entry(db, title="金针菇汤", category="汤", summary="汤a")
    soup2 = await _make_entry(db, title="罗宋汤", category="汤", summary="汤b")
    noodle1 = await _make_entry(db, title="汤面", category="主食", summary="面c")
    noodle2 = await _make_entry(db, title="蒸卤面", category="主食", summary="面d")
    hard = await _make_entry(db, title="农家一碗香", category="肉菜", summary="硬菜")
    veg = await _make_entry(db, title="虎皮青椒", category="素菜", summary="素e")
    await db.commit()
    hits = [
        {"entry": e, "similarity": s}
        for e, s in [
            (soup1, 0.63), (soup2, 0.62), (noodle1, 0.61), (noodle2, 0.60),
            (hard, 0.59), (veg, 0.58),
        ]
    ]
    picked = qa_router._pick_diverse_recipes(hits, 4)
    # 硬菜+素菜+汤+主食 各一，而不是相似度前 4 名（全是汤/面）
    assert [p["entry"].title for p in picked] == ["农家一碗香", "虎皮青椒", "金针菇汤", "汤面"]


async def test_ask_multi_dish_quota_exhausted_falls_back_to_kb(client, auth_headers, db, monkeypatch):
    """AI 限额用尽时，'推荐一桌' 类问题降级为知识库多菜直答（免费兜底、类别分散）。"""
    soup1 = await _make_entry(db, title="金针菇汤", category="汤", summary="汤a")
    soup2 = await _make_entry(db, title="罗宋汤", category="汤", summary="汤b")
    noodle1 = await _make_entry(db, title="汤面", category="主食", summary="面c")
    noodle2 = await _make_entry(db, title="蒸卤面", category="主食", summary="面d")
    hard = await _make_entry(db, title="农家一碗香", category="肉菜", summary="硬菜")
    veg = await _make_entry(db, title="虎皮青椒", category="素菜", summary="素e")
    await db.commit()
    _mock_hits(monkeypatch, [
        {"entry": e, "similarity": s}
        for e, s in [
            (soup1, 0.63), (soup2, 0.62), (noodle1, 0.61), (noodle2, 0.60),
            (hard, 0.59), (veg, 0.58),
        ]
    ])
    _mock_router(monkeypatch, "table_menu")

    from app.core.response import AppError

    async def _over_limit(db, user_id, limit):
        raise AppError("今日调用已达上限", code=429, status_code=429)

    monkeypatch.setattr(qa_router, "ensure_within_limit", _over_limit)

    res = client.post(
        "/api/qa/ask",
        json={"question": "周末招待朋友，推荐一桌有面子的家常菜"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kb_hit"] is True  # 降级为知识库直答（不再报 429）
    names = [r["name"] for r in data["answer"]["recommendations"]]
    assert names == ["农家一碗香", "虎皮青椒", "金针菇汤", "汤面"]
    # 降级路径不占 AI 额度
    assert (await db.execute(select(func.count()).select_from(AICall))).scalar() == 0


# ---------- "怎么做某菜"且有多做法 → 返回多做法列表 ----------


async def test_ask_howto_multi_variant_hit_returns_recs(client, auth_headers, db, monkeypatch):
    """'红烧肉怎么做' 且知识库有多个红烧肉变体 → 列出多种做法，而非单菜全量步骤。"""
    e1 = await _make_entry(db, title="南派红烧肉", summary="咸甜口，熬糖色慢炖 1.5 小时", steps=["炖"], category="肉菜")
    e2 = await _make_entry(db, title="简易红烧肉", summary="电饭煲一锅出，省心省力", steps=["焖"], category="肉菜")
    e3 = await _make_entry(db, title="徽派红烧肉", summary="炒糖色出油，Q 弹软糯", steps=["煸"], category="肉菜")
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": e, "similarity": 0.80 - i * 0.01} for i, e in enumerate([e1, e2, e3])])
    _mock_router(monkeypatch, "recipe_lookup", "红烧肉")

    res = client.post("/api/qa/ask", json={"question": "红烧肉怎么做"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kb_hit"] is True
    ans = data["answer"]
    recs = ans["recommendations"]
    assert len(recs) == 3
    assert [r["name"] for r in recs] == ["南派红烧肉", "简易红烧肉", "徽派红烧肉"]
    assert all(r["kb_id"] for r in recs)
    # 不展开单菜全量步骤（各做法只需简要介绍）
    assert ans["steps"] == []
    assert ans["dish_name"] == ""
    # 卡片 intro 用确定性模板（点名菜名+做法数）
    assert "红烧肉" in ans["core_secret"]
    assert "3" in ans["core_secret"]
    # 多做法命中也不占限额
    assert (await db.execute(select(func.count()).select_from(AICall))).scalar() == 0


async def test_ask_howto_single_variant_still_single(client, auth_headers, db, monkeypatch):
    """'怎么做某菜'但知识库只有 1 个变体 → 仍返回单菜全量（无第二个做法可选）。"""
    e = await _make_entry(
        db, title="红烧肉",
        steps=["切块", "焯水", "小火焖 40 分钟"],
        prep_steps=["1. 切块", "2. 焯水"],
        cook_steps=["1. 小火焖 40 分钟"],
        tips=["不要大火焯水"],
    )
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": e, "similarity": 0.8}])
    _mock_router(monkeypatch, "recipe_lookup", "红烧肉")

    res = client.post("/api/qa/ask", json={"question": "红烧肉怎么做"}, headers=auth_headers)
    assert res.status_code == 200
    ans = res.json()["data"]["answer"]
    assert ans["dish_name"] == "红烧肉"
    assert ans["recommendations"] is None
    assert len(ans["steps"]) >= 1


# ---------- 秘诀/技巧 → AI 给诀窍 + 追问提示 ----------


async def test_ask_technique_tips_routes_to_ai_with_followup(client, auth_headers, db, monkeypatch):
    """'蒸蛋怎么蒸才嫩滑' 是问秘诀 → 走 AI 给诀窍（不展开菜谱）+ 追问"需要查菜谱吗"。"""
    t = await _make_entry(db, title="去腥", kind="tip", category="新手技巧")
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": t, "similarity": 0.8}])
    _mock_router(monkeypatch, "technique_tips", "蒸蛋")

    seen = {}

    async def _fake_run_qa(question, history=None, enable_search=True):
        seen["enable_search"] = enable_search
        return {
            "result": {
                "dish_name": "蒸蛋",
                "core_secret": "水开再上锅；蛋液加温水过筛；盖盖留缝防起蜂窝。",
                "ingredients": [],
                "steps": [],
                "avoid_pitfalls": [],
                "sources": [],
                "recommendations": None,
                "followup": "需要我帮你查找「蒸蛋」的完整菜谱吗？",
            },
            "error": None,
        }

    monkeypatch.setattr(qa_agent, "run_qa", _fake_run_qa)

    async def _fake_emb(texts, *, input_type="document"):
        return [[0.5] * DIM for _ in texts]

    monkeypatch.setattr(kb_service, "aembed_texts", _fake_emb)

    res = client.post("/api/qa/ask", json={"question": "蒸蛋怎么蒸才嫩滑"}, headers=auth_headers)
    assert res.status_code == 200
    ans = res.json()["data"]["answer"]
    assert ans["dish_name"] == "蒸蛋"
    assert "水开再上锅" in ans["core_secret"]  # 给诀窍
    assert ans["steps"] == []                  # 不展开菜谱
    assert "菜谱" in ans["followup"]           # 追问提示
    # KB 覆盖到（有 tip 命中）→ 不联网
    assert seen["enable_search"] is False


# ---------- 未命中 → AI 生成并入库 ----------


async def test_ask_miss_generates_and_stores_to_kb(client, auth_headers, db, monkeypatch):
    _mock_hits(monkeypatch, [])
    _mock_router(monkeypatch, "general")
    async def _fake(**kwargs):
        return {
            "dish_name": "新菜X",
            "core_secret": "核心秘诀",
            "ingredients": ["食材a"],
            "steps": ["步骤1", "步骤2"],
            "avoid_pitfalls": ["坑1"],
            "sources": [],
            "recommendations": None,
        }

    monkeypatch.setattr(qa_agent, "ainvoke_json", _fake)

    async def _fake_emb(texts, *, input_type="document"):
        return [[0.5] * DIM for _ in texts]

    monkeypatch.setattr(kb_service, "aembed_texts", _fake_emb)

    res = client.post("/api/qa/ask", json={"question": "某个知识库没有的菜怎么做"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kb_hit"] is False
    assert data["answer"]["dish_name"] == "新菜X"

    # AI 结果已入库（按菜名）
    cnt = (
        await db.execute(select(func.count()).select_from(RecipeKB).where(RecipeKB.title == "新菜X"))
    ).scalar()
    assert cnt == 1
    # 占用 AI 限额（ai_calls 记录）
    assert (await db.execute(select(func.count()).select_from(AICall))).scalar() == 1


async def test_ask_miss_recs_stores_each_dish(client, auth_headers, db, monkeypatch):
    _mock_hits(monkeypatch, [])
    _mock_router(monkeypatch, "recommend_dishes")
    async def _fake(**kwargs):
        return {
            "core_secret": "",
            "dish_name": "",
            "ingredients": [],
            "steps": [],
            "avoid_pitfalls": [],
            "sources": [],
            "recommendations": [
                {"name": "菜甲", "core_secret": "做法甲", "time_minutes": 10, "ingredients": ["a"]},
                {"name": "菜乙", "core_secret": "做法乙", "time_minutes": 20, "ingredients": ["b"]},
            ],
        }

    monkeypatch.setattr(qa_agent, "ainvoke_json", _fake)

    async def _fake_emb(texts, *, input_type="document"):
        return [[0.5] * DIM for _ in texts]

    monkeypatch.setattr(kb_service, "aembed_texts", _fake_emb)

    res = client.post("/api/qa/ask", json={"question": "推荐两个没收录的菜"}, headers=auth_headers)
    assert res.status_code == 200
    for name in ("菜甲", "菜乙"):
        cnt = (
            await db.execute(select(func.count()).select_from(RecipeKB).where(RecipeKB.title == name))
        ).scalar()
        assert cnt == 1


# ---------- 流式：命中直接 done ----------


async def test_stream_kb_hit_returns_done_only(client, auth_headers, db, monkeypatch):
    e = await _make_entry(db, title="蒸蛋", summary="水开再上锅", steps=["打蛋"], tips=["小火"])
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": e, "similarity": 0.8}])
    _mock_router(monkeypatch, "recipe_lookup", "蒸蛋")

    res = client.post("/api/qa/stream", json={"question": "蒸蛋怎么做"}, headers=auth_headers)
    assert res.status_code == 200
    events = _parse_sse(res.text)
    # 命中 → 无打字机 delta，直接一个 done
    assert len(events) == 1
    done = events[0]
    assert done["type"] == "done"
    assert done["data"]["kb_hit"] is True
    assert done["data"]["answer"]["dish_name"] == "蒸蛋"


# ---------- 流式：KB 多做法命中 → 先 delta 过渡语（打字机），再 done 卡片 ----------


async def test_stream_kb_multi_hit_transition_then_done(client, auth_headers, db, monkeypatch):
    """知识库多做法命中：先发 delta 过渡语（打字机即时反馈），再发 done 卡片（无 opening）。"""
    e1 = await _make_entry(db, title="南派红烧肉", summary="咸甜口慢炖", steps=["炖"], category="肉菜")
    e2 = await _make_entry(db, title="简易红烧肉", summary="电饭煲一锅出", steps=["焖"], category="肉菜")
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": e, "similarity": 0.8 - i * 0.01} for i, e in enumerate([e1, e2])])
    _mock_router(monkeypatch, "recipe_lookup", "红烧肉")

    res = client.post("/api/qa/stream", json={"question": "红烧肉怎么做"}, headers=auth_headers)
    assert res.status_code == 200
    events = _parse_sse(res.text)
    types = [e["type"] for e in events]
    assert types[0] == "delta"  # 过渡语先出（打字机）
    assert types[-1] == "done"  # 卡片随后
    assert "opening" not in types
    transition_text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert "红烧肉" in transition_text  # 过渡语点名菜名
    # 卡片 intro 用确定性模板（完成时）
    assert "红烧肉" in events[-1]["data"]["answer"]["core_secret"]
    # intro 已回写记录（历史里能读到）
    hist = client.get("/api/qa/history", headers=auth_headers).json()["data"]
    assert hist and "红烧肉" in hist[0]["answer"]["core_secret"]


# ---------- 流式：限额用尽 → 降级为知识库多菜直答 ----------


async def test_stream_multi_dish_quota_exhausted_falls_back(client, auth_headers, db, monkeypatch):
    """流式：'推荐' 类问题限额用尽时降级为知识库多菜直答（yield done 而非 error）。"""
    hard = await _make_entry(db, title="农家一碗香", category="肉菜", summary="硬菜")
    veg = await _make_entry(db, title="虎皮青椒", category="素菜", summary="素")
    soup = await _make_entry(db, title="金针菇汤", category="汤", summary="汤")
    noodle = await _make_entry(db, title="汤面", category="主食", summary="面")
    snack = await _make_entry(db, title="煎饺", category="早餐", summary="煎")
    await db.commit()
    _mock_hits(monkeypatch, [
        {"entry": e, "similarity": s}
        for e, s in [(soup, 0.63), (noodle, 0.61), (snack, 0.60), (hard, 0.59), (veg, 0.58)]
    ])
    _mock_router(monkeypatch, "table_menu")

    from app.core.response import AppError

    async def _over_limit(db, user_id, limit):
        raise AppError("今日调用已达上限", code=429, status_code=429)

    monkeypatch.setattr(qa_router, "ensure_within_limit", _over_limit)

    res = client.post(
        "/api/qa/stream",
        json={"question": "周末招待朋友，推荐一桌有面子的家常菜"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    events = _parse_sse(res.text)
    assert events and all(e["type"] == "done" for e in events)  # 降级直答，非 error
    names = [r["name"] for r in events[0]["data"]["answer"]["recommendations"]]
    assert names == ["农家一碗香", "虎皮青椒", "金针菇汤", "汤面"]


# ---------- 命中不占限额（即使 AI 完全禁用） ----------


async def test_kb_hit_works_even_at_zero_ai_limit(client, auth_headers, db, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "DAILY_AI_LIMIT", 0)  # 限额 0 = AI 完全禁用
    e = await _make_entry(db, title="西红柿炒鸡蛋", steps=["打蛋", "炒"], category="素菜")
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": e, "similarity": 0.9}])
    _mock_router(monkeypatch, "recipe_lookup", "西红柿炒鸡蛋")

    res = client.post("/api/qa/ask", json={"question": "西红柿炒鸡蛋怎么做"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["kb_hit"] is True
    assert (await db.execute(select(func.count()).select_from(AICall))).scalar() == 0
