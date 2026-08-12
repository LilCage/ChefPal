"""链接/文档解析 API 测试（TDD）：/api/parse/url、/api/parse/document。

mock 掉提取器、LLM 与知识库入库，聚焦：解析成功落库 / 来源标记 / 会话 / 错误 / 限额。
"""
import pytest

from app.core.config import get_settings
from app.services import extractor
from app.services import kb as kb_service
from app.services.agents import parse_agent

VALID_PARSE = {
    "dish_name": "红烧肉",
    "core_secret": "先焯透再煸油，肥而不腻。",
    "ingredients": ["五花肉 500g", "冰糖 20g"],
    "steps": ["1. 五花肉切块冷水下锅焯透", "2. 干锅煸出猪油", "3. 炒糖色下肉上色", "4. 加热水焖40分钟收汁"],
    "avoid_pitfalls": ["糖色要小火，炒苦就废了"],
    "sources": [],
    "recommendations": None,
}

SID = "33333333-3333-3333-3333-333333333333"


@pytest.fixture(autouse=True)
def _parse_env(monkeypatch):
    """本文件：知识库入库 no-op（免真实 embedding），LLM 返回固定答案。"""

    async def _no_store(db, answer, record_id):
        return None

    async def _fake_run_parse(source_label, content):
        return dict(VALID_PARSE)

    monkeypatch.setattr(kb_service, "store_generated_answer_to_kb", _no_store)
    monkeypatch.setattr(parse_agent, "run_parse", _fake_run_parse)


def _mock_web_extract(monkeypatch, title="下厨房·红烧肉", text=None):
    async def _extract(url):
        return {"title": title, "text": text or "五花肉切块冷水下锅焯透，干锅煸油，炒糖色，加热水焖40分钟收汁。" * 4}

    monkeypatch.setattr(extractor, "is_video_url", lambda url: False)
    monkeypatch.setattr(extractor, "extract_web", _extract)


def test_parse_url_web_success(client, auth_headers, monkeypatch):
    _mock_web_extract(monkeypatch)
    r = client.post("/api/parse/url", json={"url": "https://example.com/recipe/1"}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["question"].startswith("解析网页：下厨房")
    assert data["answer"]["dish_name"] == "红烧肉"
    assert data["answer"]["parse_type"] == "web"
    assert data["sources"] == ["https://example.com/recipe/1"]


def test_parse_url_video_route(client, auth_headers, monkeypatch):
    async def _extract(url):
        return {"title": "B站·红烧肉视频", "text": "字幕内容：五花肉焯水煸油上色焖40分钟。" * 5, "source_note": "字幕"}

    monkeypatch.setattr(extractor, "is_video_url", lambda url: True)
    monkeypatch.setattr(extractor, "extract_video", _extract)
    r = client.post(
        "/api/parse/url", json={"url": "https://www.bilibili.com/video/BV1xx"}, headers=auth_headers
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["question"].startswith("解析视频：")
    assert data["answer"]["parse_type"] == "video"
    assert data["sources"] == ["https://www.bilibili.com/video/BV1xx"]


def test_parse_url_extract_failure_502(client, auth_headers, monkeypatch):
    async def _boom(url):
        raise extractor.ExtractorError("该网页无法读取内容（可能开启防爬验证）")

    monkeypatch.setattr(extractor, "is_video_url", lambda url: False)
    monkeypatch.setattr(extractor, "extract_web", _boom)
    r = client.post("/api/parse/url", json={"url": "https://example.com/x"}, headers=auth_headers)
    assert r.status_code == 502
    assert "防爬" in r.json()["message"]


def test_parse_url_llm_failure_502(client, auth_headers, monkeypatch):
    _mock_web_extract(monkeypatch)

    async def _fail(source_label, content):
        raise ValueError("未能识别出菜名")

    monkeypatch.setattr(parse_agent, "run_parse", _fail)
    r = client.post("/api/parse/url", json={"url": "https://example.com/1"}, headers=auth_headers)
    assert r.status_code == 502


def test_parse_url_requires_auth(client):
    r = client.post("/api/parse/url", json={"url": "https://example.com/1"})
    assert r.status_code == 401


def test_parse_document_success(client, auth_headers, monkeypatch):
    async def _extract(filename, content):
        return {"title": filename, "text": "红烧肉做法。五花肉焯水煸油炒糖色焖40分钟。" * 5}

    monkeypatch.setattr(extractor, "extract_document", _extract)
    files = {
        "file": (
            "红烧肉.docx",
            b"fake-docx-bytes",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    r = client.post("/api/parse/document", files=files, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["answer"]["parse_type"] == "doc"
    assert data["question"].startswith("解析文档：")


def test_parse_document_unsupported(client, auth_headers, monkeypatch):
    async def _boom(filename, content):
        raise extractor.ExtractorError("暂不支持该文件类型，请上传 PDF 或 Word(.docx)")

    monkeypatch.setattr(extractor, "extract_document", _boom)
    files = {"file": ("bad.xlsx", b"x", "application/vnd.ms-excel")}
    r = client.post("/api/parse/document", files=files, headers=auth_headers)
    assert r.status_code == 400


def test_parse_with_session_saves_session(client, auth_headers, monkeypatch):
    _mock_web_extract(monkeypatch)
    r = client.post(
        "/api/parse/url", json={"url": "https://example.com/1", "session_id": SID}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["session_id"] == SID
    # 该会话内能看到这条解析记录
    g = client.get(f"/api/qa/session/{SID}", headers=auth_headers)
    assert len(g.json()["data"]) == 1


def test_parse_rate_limit(client, auth_headers, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DAILY_AI_LIMIT", 1)
    _mock_web_extract(monkeypatch)
    r1 = client.post("/api/parse/url", json={"url": "https://example.com/1"}, headers=auth_headers)
    assert r1.status_code == 200
    r2 = client.post("/api/parse/url", json={"url": "https://example.com/2"}, headers=auth_headers)
    assert r2.status_code == 429
