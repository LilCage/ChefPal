"""RAG 集成测试：知识库命中直接返回 / 未命中 AI 生成并入库 / 命中不占限额。

知识库检索（search_kb）用 mock 注入命中列表；真实插入 RecipeKB 行供回显。
AI 结果入库用 mock embedding（确定性向量），不调真实 API。
"""
import json

import pytest
from sqlalchemy import func, select

from app.models.ai_call import AICall
from app.models.recipe_kb import RecipeKB
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


async def test_ask_multi_recipe_hit_returns_recs(client, auth_headers, db, monkeypatch):
    e1 = await _make_entry(db, title="凉拌黄瓜", summary="拍碎后杀水", steps=["拍", "拌"], category="素菜")
    e2 = await _make_entry(db, title="凉拌木耳", summary="焯水过凉", steps=["焯", "拌"], category="素菜")
    e3 = await _make_entry(db, title="凉拌莴笋", summary="切丝", steps=["切", "拌"], category="素菜")
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": e, "similarity": 0.70 - i * 0.01} for i, e in enumerate([e1, e2, e3])])

    res = client.post("/api/qa/ask", json={"question": "推荐几道凉拌菜"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kb_hit"] is True
    recs = data["answer"]["recommendations"]
    assert len(recs) == 3
    assert [r["name"] for r in recs] == ["凉拌黄瓜", "凉拌木耳", "凉拌莴笋"]
    assert recs[0]["kb_id"] == str(e1.id)
    # 多菜命中也不占限额
    assert (await db.execute(select(func.count()).select_from(AICall))).scalar() == 0


# ---------- 技巧命中 ----------


async def test_ask_tip_hit_returns_tip(client, auth_headers, db, monkeypatch):
    t = await _make_entry(db, title="去腥", kind="tip", category="新手技巧")
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": t, "similarity": 0.8}])

    res = client.post("/api/qa/ask", json={"question": "怎么给肉去腥"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kb_hit"] is True
    ans = data["answer"]
    assert ans["dish_name"] == "去腥"
    assert "技巧正文" in ans["core_secret"]


# ---------- 未命中 → AI 生成并入库 ----------


async def test_ask_miss_generates_and_stores_to_kb(client, auth_headers, db, monkeypatch):
    _mock_hits(monkeypatch, [])
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

    res = client.post("/api/qa/stream", json={"question": "蒸蛋怎么嫩"}, headers=auth_headers)
    assert res.status_code == 200
    events = _parse_sse(res.text)
    # 命中 → 无打字机 delta，直接一个 done
    assert len(events) == 1
    done = events[0]
    assert done["type"] == "done"
    assert done["data"]["kb_hit"] is True
    assert done["data"]["answer"]["dish_name"] == "蒸蛋"


# ---------- 命中不占限额（即使 AI 完全禁用） ----------


async def test_kb_hit_works_even_at_zero_ai_limit(client, auth_headers, db, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "DAILY_AI_LIMIT", 0)  # 限额 0 = AI 完全禁用
    e = await _make_entry(db, title="西红柿炒鸡蛋", steps=["打蛋", "炒"], category="素菜")
    await db.commit()
    _mock_hits(monkeypatch, [{"entry": e, "similarity": 0.9}])

    res = client.post("/api/qa/ask", json={"question": "西红柿炒鸡蛋怎么做"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["kb_hit"] is True
    assert (await db.execute(select(func.count()).select_from(AICall))).scalar() == 0
