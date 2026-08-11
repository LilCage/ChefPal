"""黑暗料理拯救 TDD：POST /api/rescue/diagnose 诊断翻车现场照片 + 补救方案。"""
from app.routers import rescue as rescue_router
from app.services import vision as vision_service

VALID_DIAG = {
    "issues": [
        {
            "title": "蛋液没推熟",
            "detail": "火太大导致蛋白结块、蛋黄还没熟。",
            "fix": "关小火 + 翻面焖 30 秒",
        },
        {
            "title": "收汁过头发苦",
            "detail": "糖在高温下焦化了。",
            "fix": "加一勺热水和半勺醋中和",
        },
    ]
}

VALID_IMAGE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def _mock_diag(monkeypatch, result=VALID_DIAG):
    async def _fake(image_data_url: str) -> dict:
        return result

    monkeypatch.setattr(vision_service, "diagnose_dish", _fake)
    return _fake


def test_rescue_diagnose_success(client, auth_headers, monkeypatch):
    """上传翻车照 → 返回诊断问题 + 补救方案。"""
    _mock_diag(monkeypatch)
    res = client.post(
        "/api/rescue/diagnose", json={"image_base64": VALID_IMAGE}, headers=auth_headers
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert "issues" in data
    issue = data["issues"][0]
    assert {"title", "detail", "fix"} <= set(issue.keys())
    assert "补救" not in issue["fix"]  # fix 已是补救内容本体


def test_rescue_diagnose_passes_image(monkeypatch):
    """原样透传 image_base64 给视觉服务。"""
    captured = {}

    async def _fake(image_data_url: str) -> dict:
        captured["image"] = image_data_url
        return VALID_DIAG

    monkeypatch.setattr(vision_service, "diagnose_dish", _fake)
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        # 需要登录
        import importlib
        from app import services as _s

        _wechat = importlib.import_module("app.services.wechat")
        async def _fake_code2session(code: str) -> dict:
            return {"openid": "openid-diag", "session_key": "mock"}

        monkeypatch.setattr(_wechat, "code2session", _fake_code2session)
        token = client.post("/api/auth/login", json={"code": "c"}).json()["data"]["token"]
        h = {"Authorization": f"Bearer {token}"}
        res = client.post("/api/rescue/diagnose", json={"image_base64": VALID_IMAGE}, headers=h)
        assert res.status_code == 200
        assert captured["image"] == VALID_IMAGE


def test_rescue_diagnose_missing_key_502(client, auth_headers, monkeypatch):
    """未配置 ZHIPU key → 502 清晰错误。"""

    async def _fake(image_data_url: str) -> dict:
        raise vision_service.VisionError("未配置 ZHIPU_API_KEY，请先在 apps/server/.env 中填入智谱 Key")

    monkeypatch.setattr(vision_service, "diagnose_dish", _fake)
    res = client.post(
        "/api/rescue/diagnose", json={"image_base64": VALID_IMAGE}, headers=auth_headers
    )
    assert res.status_code == 502
    assert "ZHIPU" in res.json()["message"]


def test_rescue_diagnose_parse_fail_502(client, auth_headers, monkeypatch):
    """视觉服务解析失败 → 502。"""

    async def _fake(image_data_url: str) -> dict:
        raise vision_service.VisionError("视觉识别结果解析失败，请重试")

    monkeypatch.setattr(vision_service, "diagnose_dish", _fake)
    res = client.post(
        "/api/rescue/diagnose", json={"image_base64": VALID_IMAGE}, headers=auth_headers
    )
    assert res.status_code == 502


def test_rescue_diagnose_invalid_image_400(client, auth_headers, monkeypatch):
    """非法图片 data URL → 400。"""
    _mock_diag(monkeypatch)
    res = client.post(
        "/api/rescue/diagnose", json={"image_base64": "not-a-data-url"}, headers=auth_headers
    )
    assert res.status_code == 400


def test_rescue_diagnose_missing_image_422(client, auth_headers):
    """缺 image_base64 → 422。"""
    res = client.post("/api/rescue/diagnose", json={}, headers=auth_headers)
    assert res.status_code == 422


def test_rescue_diagnose_requires_auth(client):
    """未登录 → 401。"""
    assert (
        client.post("/api/rescue/diagnose", json={"image_base64": VALID_IMAGE}).status_code
        == 401
    )


def test_rescue_diagnose_rate_limit(client, auth_headers, monkeypatch):
    """超出每日 AI 限额 → 429。"""
    from app.core.response import AppError

    _mock_diag(monkeypatch)

    async def _over(db, user_id, limit):
        raise AppError("今日调用已达上限，明日再来吧", code=429, status_code=429)

    monkeypatch.setattr(rescue_router, "ensure_within_limit", _over)
    res = client.post(
        "/api/rescue/diagnose", json={"image_base64": VALID_IMAGE}, headers=auth_headers
    )
    assert res.status_code == 429
    assert "上限" in res.json()["message"]
