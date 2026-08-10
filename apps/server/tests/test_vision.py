"""拍照识食材 TDD：识别（mock）/ 输入校验 / 未配置 Key / 风控。"""
import base64

from app.core.config import get_settings
from app.services import vision as vision_service

IMG = "data:image/png;base64," + base64.b64encode(b"fake-png-bytes").decode("ascii")


def _mock_recognize(monkeypatch, ingredients=None, error=None):
    async def _fake(image_data_url: str) -> list[str]:
        if error:
            raise error
        return ingredients or []

    monkeypatch.setattr(vision_service, "recognize_ingredients", _fake)
    return _fake


# ---------- 识别 ----------
def test_recognize_ingredients(client, auth_headers, monkeypatch):
    _mock_recognize(monkeypatch, ingredients=["西红柿", "鸡蛋", "生菜"])
    res = client.post("/api/vision/recognize", json={"image_base64": IMG}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["ingredients"] == ["西红柿", "鸡蛋", "生菜"]


def test_recognize_requires_auth(client):
    res = client.post("/api/vision/recognize", json={"image_base64": IMG})
    assert res.status_code == 401


def test_recognize_empty_result(client, auth_headers, monkeypatch):
    _mock_recognize(monkeypatch, ingredients=[])
    res = client.post("/api/vision/recognize", json={"image_base64": IMG}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["ingredients"] == []


# ---------- 输入校验 ----------
def test_recognize_invalid_data_url_400(client, auth_headers, monkeypatch):
    _mock_recognize(monkeypatch, ingredients=["西红柿"])
    res = client.post(
        "/api/vision/recognize", json={"image_base64": "not-a-data-url"}, headers=auth_headers
    )
    assert res.status_code == 400
    assert "data:image" in res.json()["message"]


def test_recognize_wrong_mime_400(client, auth_headers, monkeypatch):
    _mock_recognize(monkeypatch, ingredients=["西红柿"])
    res = client.post(
        "/api/vision/recognize",
        json={"image_base64": "data:image/gif;base64,aGVsbG8="},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "仅支持" in res.json()["message"]


def test_recognize_too_large_400(client, auth_headers, monkeypatch):
    _mock_recognize(monkeypatch, ingredients=["西红柿"])
    big = base64.b64encode(b"x" * (2 * 1024 * 1024 + 1)).decode("ascii")
    res = client.post(
        "/api/vision/recognize",
        json={"image_base64": f"data:image/png;base64,{big}"},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "2MB" in res.json()["message"]


# ---------- 未配置 Key / 识别失败 ----------
def test_recognize_missing_key_502(client, auth_headers, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ZHIPU_API_KEY", "")
    # recognize_ingredients 未 mock：真实逻辑在无 Key 时应抛 VisionError
    res = client.post("/api/vision/recognize", json={"image_base64": IMG}, headers=auth_headers)
    assert res.status_code == 502
    assert "ZHIPU_API_KEY" in res.json()["message"]


def test_recognize_service_error_502(client, auth_headers, monkeypatch):
    _mock_recognize(monkeypatch, error=vision_service.VisionError("视觉识别调用失败: mock"))
    res = client.post("/api/vision/recognize", json={"image_base64": IMG}, headers=auth_headers)
    assert res.status_code == 502


# ---------- 风控 ----------
def test_recognize_rate_limit(client, auth_headers, monkeypatch):
    from app.core.response import AppError
    from app.routers import vision as vision_router

    _mock_recognize(monkeypatch, ingredients=["西红柿"])

    async def _over(db, user_id, limit):
        raise AppError("今日 AI 调用已达上限，明日再来吧", code=429, status_code=429)

    monkeypatch.setattr(vision_router, "ensure_within_limit", _over)
    res = client.post("/api/vision/recognize", json={"image_base64": IMG}, headers=auth_headers)
    assert res.status_code == 429
