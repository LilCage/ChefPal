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

    monkeypatch.setattr(kb_service, "search_kb", _miss)
    monkeypatch.setattr(kb_service, "store_generated_answer_to_kb", _no_store)


def _install_run_qa(monkeypatch, calls):
    async def _fake_run_qa(question, history=None):
        calls.append((question, history))
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
