"""STEP 3 · 问答闭环 TDD：mock LLM → 结构化落库/历史/删除/限额/降级。"""
import pytest

from app.services.agents import qa_agent
from app.services.llm.client import LLMError

VALID_QA = {
    "core_secret": "五花肉先焯透再煸油，肥而不腻的关键。",
    "ingredients": ["五花肉", "冰糖", "姜"],
    "steps": ["冷水下锅焯透", "小火炒糖色", "加热水焖 40 分钟"],
    "avoid_pitfalls": ["不要大火焯水，肉会柴"],
    "sources": ["https://example.com/hongshaorou"],
}


def _mock_ainvoke(monkeypatch, payload):
    async def _fake(**kwargs):
        return payload(kwargs) if callable(payload) else payload

    monkeypatch.setattr(qa_agent, "ainvoke_json", _fake)


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
