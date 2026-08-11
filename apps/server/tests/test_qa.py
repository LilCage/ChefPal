"""STEP 3 · 问答闭环 TDD：mock LLM → 结构化落库/历史/删除/限额/降级/流式SSE。"""
import json

import pytest

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
    # 前面有 delta 打字机事件
    deltas = [e for e in events[:-1] if json.loads(e)["type"] == "delta"]
    assert len(deltas) > 0
    typing_text = "".join(json.loads(d)["text"] for d in deltas)
    assert "红烧肉" in typing_text

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
    assert "凉拌黄瓜" in typing_text
    assert "小伴为你推荐" in typing_text


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
