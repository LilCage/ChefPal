"""STEP 3 · 问答闭环 TDD：mock LLM → 结构化落库/历史/删除/限额/降级/流式SSE。

RAG 说明：本文件只测 AI 生成路径，默认 mock 掉知识库检索（未命中）与入库，
避免真实 embedding API 调用；知识库命中路径在 test_qa_rag.py 单独覆盖。
"""
import json

import pytest

from app.services import kb as kb_service
from app.services.agents import qa_agent
from app.services.llm.client import LLMError

VALID_QA = {
    "dish_name": "红烧肉",
    "core_secret": "五花肉先焯透再煸油，肥而不腻的关键。",
    "ingredients": ["五花肉", "冰糖", "姜"],
    "steps": ["冷水下锅焯透", "小火炒糖色", "加热水焖 40 分钟"],
    "avoid_pitfalls": ["不要大火焯水，肉会柴"],
    "sources": ["https://example.com/hongshaorou"],
    "recommendations": None,
}

RECS_QA = {
    "core_secret": "",
    "dish_name": "",
    "ingredients": [],
    "steps": [],
    "avoid_pitfalls": [],
    "sources": None,
    "recommendations": [
        {"name": "凉拌黄瓜", "core_secret": "拍碎后先加盐杀水再拌", "time_minutes": 10, "ingredients": ["黄瓜", "蒜"]},
        {"name": "凉拌木耳", "core_secret": "木耳焯水后过凉水更脆", "time_minutes": 15, "ingredients": ["木耳", "小米椒"]},
    ],
}


def _mock_ainvoke(monkeypatch, payload):
    async def _fake(**kwargs):
        return payload(kwargs) if callable(payload) else payload

    monkeypatch.setattr(qa_agent, "ainvoke_json", _fake)


@pytest.fixture(autouse=True)
def _kb_off(monkeypatch):
    """本文件只测 AI 路径：KB 检索恒未命中，AI 结果不入库（免真实 embedding）。"""
    async def _miss(db, query, **kw):
        return []

    async def _no_store(db, **kw):
        return None

    async def _router(question, history=None):
        return {"intent": "general", "dish_name": "", "needs_full_recipe": False, "confidence": "high"}

    monkeypatch.setattr(kb_service, "search_kb", _miss)
    monkeypatch.setattr(kb_service, "upsert_kb_entry", _no_store)
    monkeypatch.setattr(qa_agent, "route_intent", _router)


def test_ask_success_saves_and_lists(client, auth_headers, monkeypatch):
    _mock_ainvoke(monkeypatch, VALID_QA)

    res = client.post("/api/qa/ask", json={"question": "红烧肉怎么不腻"}, headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["answer"]["core_secret"] == VALID_QA["core_secret"]
    assert data["sources"] == VALID_QA["sources"]

    # 历史可查
    hist = client.get("/api/qa/history", headers=auth_headers).json()["data"]
    assert len(hist) == 1
    assert hist[0]["question"] == "红烧肉怎么不腻"


def test_ask_without_auth_returns_401(client):
    res = client.post("/api/qa/ask", json={"question": "蒸蛋怎么嫩"})
    assert res.status_code == 401


def test_ask_llm_error_returns_502(client, auth_headers, monkeypatch):
    async def _boom(**kwargs):
        raise LLMError("mock LLM 崩溃")

    monkeypatch.setattr(qa_agent, "ainvoke_json", _boom)
    res = client.post("/api/qa/ask", json={"question": "蒸蛋怎么嫩"}, headers=auth_headers)
    assert res.status_code == 502
    assert res.json()["code"] == 502


def test_ask_invalid_structure_falls_back_502(client, auth_headers, monkeypatch):
    """模型始终返回缺字段的 JSON → 重试后降级 502。"""
    _mock_ainvoke(monkeypatch, {"core_secret": "只有一句话"})
    res = client.post("/api/qa/ask", json={"question": "炖肉去腥"}, headers=auth_headers)
    assert res.status_code == 502


def test_history_limits_to_20(client, auth_headers, monkeypatch):
    _mock_ainvoke(monkeypatch, VALID_QA)
    for i in range(25):
        client.post("/api/qa/ask", json={"question": f"问题 {i}"}, headers=auth_headers)
    hist = client.get("/api/qa/history", headers=auth_headers).json()["data"]
    assert len(hist) == 20


def test_delete_own_record(client, auth_headers, monkeypatch):
    _mock_ainvoke(monkeypatch, VALID_QA)
    created = client.post("/api/qa/ask", json={"question": "待删除问题"}, headers=auth_headers).json()["data"]
    rec_id = created["id"]

    res = client.delete(f"/api/qa/{rec_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["code"] == 0

    hist = client.get("/api/qa/history", headers=auth_headers).json()["data"]
    assert all(r["id"] != rec_id for r in hist)


def test_delete_nonexistent_returns_404(client, auth_headers):
    res = client.delete("/api/qa/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert res.status_code == 404


# ---------- 流式输出（SSE 打字机 + 结构化卡片） ----------
def _mock_stream(monkeypatch, full_text, error=None):
    from app.routers import qa as qa_router

    async def _fake(**kwargs):
        # 分片 yield，模拟流式
        for i in range(0, len(full_text), 5):
            yield full_text[i:i + 5]

    async def _boom(**kwargs):
        raise LLMError("mock 流式失败")

    monkeypatch.setattr(qa_router, "astream_text", _boom if error else _fake)


def _parse_sse(text: str) -> list[dict]:
    """把 SSE 文本解析成事件列表。"""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        events.append(payload)
    return events


def test_ask_stream_single_type(client, auth_headers, monkeypatch):
    full = json.dumps(VALID_QA, ensure_ascii=False)
    _mock_stream(monkeypatch, full)
    res = client.post("/api/qa/stream", json={"question": "红烧肉怎么不腻"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(res.text)
    # 最后一个事件是 done，含完整结构化数据
    done = json.loads(events[-1])
    assert done["type"] == "done"
    assert done["data"]["answer"]["dish_name"] == "红烧肉"
    # 前面有 delta 过渡语打字机事件（确定性文案，intent=general）
    deltas = [e for e in events[:-1] if json.loads(e)["type"] == "delta"]
    assert len(deltas) > 0
    typing_text = "".join(json.loads(d)["text"] for d in deltas)
    assert "小伴这就来帮你" in typing_text

    # 已落库
    hist = client.get("/api/qa/history", headers=auth_headers).json()["data"]
    assert any(h["question"] == "红烧肉怎么不腻" for h in hist)


def test_ask_stream_recommendation_type(client, auth_headers, monkeypatch):
    full = json.dumps(RECS_QA, ensure_ascii=False)
    _mock_stream(monkeypatch, full)
    res = client.post("/api/qa/stream", json={"question": "推荐几道凉拌菜"}, headers=auth_headers)
    assert res.status_code == 200
    events = _parse_sse(res.text)
    done = json.loads(events[-1])
    assert done["type"] == "done"
    recs = done["data"]["answer"]["recommendations"]
    assert len(recs) == 2
    deltas = [json.loads(e)["text"] for e in events[:-1]]
    typing_text = "".join(deltas)
    assert "小伴这就来帮你" in typing_text  # 过渡语先行（intent=general）


def test_ask_stream_empty_shell_error(client, auth_headers, monkeypatch):
    _mock_stream(monkeypatch, '{"core_secret":"只有一句话"}')
    res = client.post("/api/qa/stream", json={"question": "炖肉去腥"}, headers=auth_headers)
    assert res.status_code == 200
    events = _parse_sse(res.text)
    last = json.loads(events[-1])
    assert last["type"] == "error"
    # 未落库
    hist = client.get("/api/qa/history", headers=auth_headers).json()["data"]
    assert hist == []


def test_ask_stream_requires_auth(client):
    res = client.post("/api/qa/stream", json={"question": "x"})
    assert res.status_code == 401


# ---------- 方案C：多菜推荐型 + 单菜菜名 ----------


def test_ask_recommendation_type_saves(client, auth_headers, monkeypatch):
    _mock_ainvoke(monkeypatch, RECS_QA)
    res = client.post("/api/qa/ask", json={"question": "天气太热了，帮我推荐几道凉拌菜"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    recs = data["answer"]["recommendations"]
    assert len(recs) == 2
    assert recs[0]["name"] == "凉拌黄瓜"
    assert recs[0]["core_secret"]
    assert recs[0]["time_minutes"] == 10


def test_ask_single_with_dish_name(client, auth_headers, monkeypatch):
    payload = {**VALID_QA, "dish_name": "红烧肉"}
    _mock_ainvoke(monkeypatch, payload)
    res = client.post("/api/qa/ask", json={"question": "红烧肉怎么不腻"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["answer"]["dish_name"] == "红烧肉"


def test_ask_empty_shell_falls_back_502(client, auth_headers, monkeypatch):
    """空壳（无推荐清单、无菜名+步骤）→ 语义校验失败 → 降级 502。"""
    _mock_ainvoke(monkeypatch, {"core_secret": "只有一句话"})
    res = client.post("/api/qa/ask", json={"question": "炖肉去腥"}, headers=auth_headers)
    assert res.status_code == 502


def test_daily_limit_429(client, auth_headers, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "DAILY_AI_LIMIT", 1)
    _mock_ainvoke(monkeypatch, VALID_QA)

    first = client.post("/api/qa/ask", json={"question": "第一次"}, headers=auth_headers)
    assert first.status_code == 200

    second = client.post("/api/qa/ask", json={"question": "第二次"}, headers=auth_headers)
    assert second.status_code == 429
    assert second.json()["code"] == 429


# ---------- kb_id 入库回填必须落到存储的 answer（回归：flush 后原地 dict 修改不标记 dirty 会丢） ----------


def test_ask_backfills_kb_id_to_stored_record(client, auth_headers, monkeypatch):
    """AI 生成的多菜推荐入库回填 kb_id 后，接口返回与历史记录都必须带 kb_id。"""
    _mock_ainvoke(monkeypatch, RECS_QA)

    async def _fake_store(db, answer, record_id):
        for r in (answer.get("recommendations") or []):
            r["kb_id"] = "11111111-2222-3333-4444-555555555555"

    monkeypatch.setattr(kb_service, "store_generated_answer_to_kb", _fake_store)

    res = client.post("/api/qa/ask", json={"question": "推荐几道凉拌菜"}, headers=auth_headers)
    assert res.status_code == 200
    recs = res.json()["data"]["answer"]["recommendations"]
    assert all(r.get("kb_id") == "11111111-2222-3333-4444-555555555555" for r in recs)

    # 落库的历史记录也必须是回填后的值（此前 commit 用的是 flush 时的旧值 → kb_id=None）
    hist = client.get("/api/qa/history", headers=auth_headers).json()["data"]
    assert hist[0]["answer"]["recommendations"][0]["kb_id"] == "11111111-2222-3333-4444-555555555555"


def test_extract_json_strips_answer_data_tags():
    """新版双标签输出：<answer> 正文 + <data> JSON，两种解析入口都能剥标签取 JSON。"""
    import json as _json

    from app.routers.qa import _extract_json_obj
    from app.services.llm.client import _extract_json

    payload = _json.dumps(VALID_QA, ensure_ascii=False)
    tagged = f"<answer>五花肉先焯透再煸油。</answer><data>{payload}</data>"
    assert _json.loads(_extract_json(tagged))["dish_name"] == "红烧肉"
    assert _extract_json_obj(tagged)["dish_name"] == "红烧肉"


def test_ask_stream_tagged_format_streams_answer(client, auth_headers, monkeypatch):
    """新版双标签格式（<answer>正文打字机 + <data>JSON卡片）：正文逐字流出、标签剥离、done 带结构化数据。"""
    full = (
        "<answer>五花肉先焯透再煸油，肥而不腻的关键是煸出油脂。"
        "做法：冷水下锅焯透、小火炒糖色、加热水焖40分钟。</answer>"
        f"<data>{json.dumps(VALID_QA, ensure_ascii=False)}</data>"
    )
    _mock_stream(monkeypatch, full)

    res = client.post("/api/qa/stream", json={"question": "红烧肉怎么不腻"}, headers=auth_headers)
    assert res.status_code == 200
    events = _parse_sse(res.text)
    # 中间有正文的 delta 打字机（标签已剥离）
    deltas = [json.loads(e) for e in events if json.loads(e)["type"] == "delta"]
    typing = "".join(d["text"] for d in deltas)
    assert "五花肉先焯透" in typing
    assert "<answer>" not in typing and "<data" not in typing
    # 最后是 done，含结构化数据
    done = json.loads(events[-1])
    assert done["type"] == "done"
    assert done["data"]["answer"]["dish_name"] == "红烧肉"


def test_ask_stream_backfills_kb_id(client, auth_headers, monkeypatch):
    """流式路径同款回归：done 事件里的 recommendations 必须带 kb_id。"""
    full = json.dumps(RECS_QA, ensure_ascii=False)
    _mock_stream(monkeypatch, full)

    async def _fake_store(db, answer, record_id):
        for r in (answer.get("recommendations") or []):
            r["kb_id"] = "11111111-2222-3333-4444-555555555555"

    monkeypatch.setattr(kb_service, "store_generated_answer_to_kb", _fake_store)

    res = client.post("/api/qa/stream", json={"question": "推荐几道凉拌菜"}, headers=auth_headers)
    events = _parse_sse(res.text)
    done = json.loads(events[-1])
    assert done["type"] == "done"
    recs = done["data"]["answer"]["recommendations"]
    assert all(r.get("kb_id") == "11111111-2222-3333-4444-555555555555" for r in recs)
