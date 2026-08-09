"""STEP 2 · 登录闭环 TDD：code2Session(mock) → JWT → 建/查用户 → 鉴权。"""
import uuid

import pytest

from app.services import wechat as wechat_service


def _mock_code2session(openid: str):
    async def _fake(code: str) -> dict:
        assert code == "test-code"
        return {"openid": openid, "session_key": "mock-session-key"}

    return _fake


def test_login_creates_user_and_returns_token(client, monkeypatch):
    monkeypatch.setattr(wechat_service, "code2session", _mock_code2session("openid-1"))
    res = client.post("/api/auth/login", json={"code": "test-code"})
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    assert body["data"]["token"]
    # openid 不暴露给前端，UserOut 不含该字段
    assert "openid" not in body["data"]["user"]
    assert body["data"]["user"]["id"]


def test_login_second_time_returns_same_user(client, monkeypatch):
    """同一 openid 二次登录返回同一 user_id。"""
    fake = _mock_code2session("openid-stable")
    monkeypatch.setattr(wechat_service, "code2session", fake)
    first = client.post("/api/auth/login", json={"code": "test-code"}).json()["data"]
    second = client.post("/api/auth/login", json={"code": "test-code"}).json()["data"]
    assert first["user"]["id"] == second["user"]["id"]


def test_login_wechat_error_returns_401(client, monkeypatch):
    async def _error(code: str):
        raise wechat_service.WeChatError("invalid code")

    monkeypatch.setattr(wechat_service, "code2session", _error)
    res = client.post("/api/auth/login", json={"code": "bad-code"})
    assert res.status_code == 401
    assert res.json()["code"] == 401


def test_login_missing_code_returns_422(client):
    res = client.post("/api/auth/login", json={})
    assert res.status_code == 422


def test_get_me_with_token(client, monkeypatch):
    """带 JWT 访问 /api/users/me 返回当前用户。"""
    monkeypatch.setattr(wechat_service, "code2session", _mock_code2session("openid-me"))
    token = client.post("/api/auth/login", json={"code": "test-code"}).json()["data"]["token"]
    res = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["data"]["id"]


def test_get_me_without_token_returns_401(client):
    res = client.get("/api/users/me")
    assert res.status_code == 401


def test_get_me_with_invalid_token_returns_401(client):
    res = client.get("/api/users/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


def test_preferences_update_and_read_back(client, monkeypatch):
    """PUT preferences 落库并可回读。"""
    monkeypatch.setattr(wechat_service, "code2session", _mock_code2session("openid-pref"))
    token = client.post("/api/auth/login", json={"code": "test-code"}).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.put(
        "/api/users/me/preferences",
        json={"allergies": ["花生"], "spiciness": 1, "saltiness": "适中", "skill": "厨房小白"},
        headers=headers,
    )
    assert res.status_code == 200
    prefs = res.json()["data"]["preferences"]
    assert prefs["allergies"] == ["花生"]
    assert prefs["spiciness"] == 1

    # 回读
    me = client.get("/api/users/me", headers=headers).json()["data"]
    assert me["preferences"]["saltiness"] == "适中"


def test_preferences_custom_allergy_cleaned(client, monkeypatch):
    """自定义忌口：去空白/去重/丢弃超长项，保留顺序。"""
    monkeypatch.setattr(wechat_service, "code2session", _mock_code2session("openid-custom"))
    token = client.post("/api/auth/login", json={"code": "test-code"}).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.put(
        "/api/users/me/preferences",
        json={"allergies": [" 蘑菇 ", "蘑菇", "洋葱", "长" * 30, "", "   "]},
        headers=headers,
    )
    assert res.status_code == 200
    prefs = res.json()["data"]["preferences"]
    assert prefs["allergies"] == ["蘑菇", "洋葱"]


def test_preferences_allergy_count_capped(client, monkeypatch):
    """忌口最多保留 10 项。"""
    monkeypatch.setattr(wechat_service, "code2session", _mock_code2session("openid-cap"))
    token = client.post("/api/auth/login", json={"code": "test-code"}).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.put(
        "/api/users/me/preferences",
        json={"allergies": [f"忌口{i}" for i in range(15)]},
        headers=headers,
    )
    assert res.status_code == 200
    assert len(res.json()["data"]["preferences"]["allergies"]) == 10
