"""对话式首页 · 多轮会话 TDD：session_id 落库 + 历史上下文注入 + 会话查询 + 用户隔离。"""
import json

import pytest

from app.services import kb as kb_service
from app.services.agents import qa_agent

VALID_QA = {
    "dish_name": "红烧肉",
    "core_secret": "五花肉先焯透再煸油，肥而不腻的关键。",
    "ingredients": ["五花肉", "冰糖", "姜"],
    "steps": ["冷水下锅焯透", "小火炒糖色", "加热水焖 40 分钟"],
    "avoid_pitfalls": ["不要大火焯水，肉会柴"],
    "sources": [],
    "recommendations": None,
}

SID = "11111111-1111-1111-1111-111111111111"
SID2 = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """本文件：KB 检索恒未命中 + 结果不入库（免真实 embedding）。"""

    async def _miss(db, query, **kw):
        return []

    async def _no_store(db, answer, record_id):
        return None

    async def _router(question, history=None):
        return {"intent": "general", "dish_name": "", "needs_full_recipe": False, "confidence": "high"}

    monkeypatch.setattr(kb_service, "search_kb", _miss)
    monkeypatch.setattr(kb_service, "store_generated_answer_to_kb", _no_store)
    monkeypatch.setattr(qa_agent, "route_intent", _router)


def _install_run_qa(monkeypatch, calls):
    async def _fake_run_qa(question, history=None, enable_search=True):
        calls.append((question, history, enable_search))
        return {"result": dict(VALID_QA), "error": None}

    monkeypatch.setattr(qa_agent, "run_qa", _fake_run_qa)


def test_first_turn_no_history_second_injects(client, auth_headers, monkeypatch):
    calls = []
    _install_run_qa(monkeypatch, calls)

    r1 = client.post(
        "/api/qa/ask", json={"question": "红烧肉怎么做不腻？", "session_id": SID}, headers=auth_headers
    )
    assert r1.status_code == 200
    assert calls[-1][1] == []  # 首轮会话内还没有历史 → 空列表

    r2 = client.post(
        "/api/qa/ask", json={"question": "那糖色怎么炒不苦？", "session_id": SID}, headers=auth_headers
    )
    assert r2.status_code == 200
    hist = calls[-1][1]
    assert hist and len(hist) >= 2
    assert hist[0]["role"] == "user" and "红烧肉" in hist[0]["content"]
    assert hist[1]["role"] == "assistant" and "红烧肉" in hist[1]["content"]


def test_new_session_no_history(client, auth_headers, monkeypatch):
    calls = []
    _install_run_qa(monkeypatch, calls)
    client.post("/api/qa/ask", json={"question": "Q1", "session_id": SID}, headers=auth_headers)
    client.post("/api/qa/ask", json={"question": "Q2", "session_id": SID2}, headers=auth_headers)
    assert calls[-1][1] == []  # 新会话不带上一个会话的上下文 → 空列表


# ---------- 自动优化提示词（'怎么做X' → 要求列多种做法简要介绍） ----------


def test_howto_question_prompt_is_optimized(client, auth_headers, monkeypatch):
    calls = []
    _install_run_qa(monkeypatch, calls)
    client.post("/api/qa/ask", json={"question": "红烧肉怎么做", "session_id": SID}, headers=auth_headers)
    q, _, _ = calls[-1]
    assert "自动优化提示" in q
    assert "红烧肉" in q
    assert "2~4 种不同做法" in q


def test_howto_prefix_question_prompt_is_optimized(client, auth_headers, monkeypatch):
    calls = []
    _install_run_qa(monkeypatch, calls)
    client.post("/api/qa/ask", json={"question": "怎么做红烧肉更好吃", "session_id": SID}, headers=auth_headers)
    q, _, _ = calls[-1]
    assert "自动优化提示" in q
    assert "红烧肉" in q


def test_non_howto_question_prompt_unchanged(client, auth_headers, monkeypatch):
    calls = []
    _install_run_qa(monkeypatch, calls)
    client.post("/api/qa/ask", json={"question": "推荐几道凉拌菜", "session_id": SID}, headers=auth_headers)
    q, _, _ = calls[-1]
    assert "自动优化提示" not in q


def test_technique_question_prompt_not_optimized(client, auth_headers, monkeypatch):
    """技巧类问题（'怎么去腥'）不做多做法优化，避免误提取非菜名。"""
    calls = []
    _install_run_qa(monkeypatch, calls)
    client.post("/api/qa/ask", json={"question": "炖肉怎么去腥增香，肉质更软烂", "session_id": SID}, headers=auth_headers)
    q, _, _ = calls[-1]
    assert "自动优化提示" not in q


def test_no_session_id_still_works(client, auth_headers, monkeypatch):
    calls = []
    _install_run_qa(monkeypatch, calls)
    r = client.post("/api/qa/ask", json={"question": "单轮问题"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["session_id"] is None


def test_session_endpoint_orders_messages(client, auth_headers, monkeypatch):
    _install_run_qa(monkeypatch, [])
    client.post("/api/qa/ask", json={"question": "第一个问题", "session_id": SID}, headers=auth_headers)
    client.post("/api/qa/ask", json={"question": "第二个问题", "session_id": SID}, headers=auth_headers)
    r = client.get(f"/api/qa/session/{SID}", headers=auth_headers)
    data = r.json()["data"]
    assert [d["question"] for d in data] == ["第一个问题", "第二个问题"]
    assert all(d["session_id"] == SID for d in data)


def test_session_scoped_to_user(client, auth_headers, make_headers, monkeypatch):
    _install_run_qa(monkeypatch, [])
    client.post("/api/qa/ask", json={"question": "Q1", "session_id": SID}, headers=auth_headers)
    other = make_headers("openid-other")
    r = client.get(f"/api/qa/session/{SID}", headers=other)
    assert r.json()["data"] == []


def test_stream_injects_history_and_saves_session(client, auth_headers, monkeypatch):
    from app.routers import qa as qa_router

    seen = {}

    async def _fake_stream(**kwargs):
        seen["history"] = kwargs.get("history")
        full = json.dumps(VALID_QA, ensure_ascii=False)
        for ch in full:
            yield ch

    monkeypatch.setattr(qa_router, "astream_text", _fake_stream)
    _install_run_qa(monkeypatch, [])

    client.post(
        "/api/qa/ask", json={"question": "红烧肉怎么做不腻？", "session_id": SID}, headers=auth_headers
    )
    r = client.post(
        "/api/qa/stream", json={"question": "那糖色呢？", "session_id": SID}, headers=auth_headers
    )
    assert r.status_code == 200
    hist = seen["history"]
    assert hist and hist[0]["role"] == "user" and "红烧肉" in hist[0]["content"]
    # 流式结果已落库到该会话
    g = client.get(f"/api/qa/session/{SID}", headers=auth_headers)
    assert len(g.json()["data"]) == 2


# ---------- 会话聚合列表 + 删除会话 ----------


def test_sessions_aggregates_by_session(client, auth_headers, monkeypatch):
    """GET /api/qa/sessions：按会话聚合（标题=首问、消息数、最后问题）。"""
    _install_run_qa(monkeypatch, [])
    client.post("/api/qa/ask", json={"question": "会话1首问", "session_id": SID}, headers=auth_headers)
    client.post("/api/qa/ask", json={"question": "会话1追问", "session_id": SID}, headers=auth_headers)
    client.post("/api/qa/ask", json={"question": "会话2首问", "session_id": SID2}, headers=auth_headers)

    r = client.get("/api/qa/sessions", headers=auth_headers)
    data = r.json()["data"]
    assert len(data) == 2
    by_sid = {d["session_id"]: d for d in data}
    s1 = by_sid[SID]
    assert s1["title"] == "会话1首问"
    assert s1["last_question"] == "会话1追问"
    assert s1["msg_count"] == 2
    assert s1["last_at"]  # 最后活动时间非空
    s2 = by_sid[SID2]
    assert s2["title"] == "会话2首问"
    assert s2["msg_count"] == 1


def test_delete_session_removes_all(client, auth_headers, monkeypatch):
    """DELETE /api/qa/session/{id}：删整个会话，会话与历史里都不再出现。"""
    _install_run_qa(monkeypatch, [])
    client.post("/api/qa/ask", json={"question": "Q1", "session_id": SID}, headers=auth_headers)
    client.post("/api/qa/ask", json={"question": "Q2", "session_id": SID}, headers=auth_headers)

    r = client.delete(f"/api/qa/session/{SID}", headers=auth_headers)
    assert r.status_code == 200

    g = client.get(f"/api/qa/session/{SID}", headers=auth_headers)
    assert g.json()["data"] == []
    sess = client.get("/api/qa/sessions", headers=auth_headers).json()["data"]
    assert all(d["session_id"] != SID for d in sess)
    hist = client.get("/api/qa/history", headers=auth_headers).json()["data"]
    assert all(h["session_id"] != SID for h in hist)


def test_sessions_scoped_to_user(client, auth_headers, make_headers, monkeypatch):
    """会话列表只含当前用户，其他用户看不到。"""
    _install_run_qa(monkeypatch, [])
    client.post("/api/qa/ask", json={"question": "Q1", "session_id": SID}, headers=auth_headers)
    other = make_headers("openid-other")
    sess = client.get("/api/qa/sessions", headers=other).json()["data"]
    assert all(d["session_id"] != SID for d in sess)
