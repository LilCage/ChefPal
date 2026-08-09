"""分享卡片 TDD：GET /api/recipes/{id}/share-card（菜谱信息 + 小程序码，mock 微信）。"""
from app.services import wechat as wechat_service
from app.services.agents import recipe_agent
from app.services.wechat import WeChatError

VALID_SET = {
    "recipes": [
        {"name": "番茄鸡蛋面", "match_score": 98, "time_minutes": 15, "difficulty": "简单",
         "missing_seasonings": ["葱末"],
         "steps": [{"title": "西红柿处理", "detail": "切块加盐煸炒出沙"}, {"title": "煮面", "detail": "水开下面"}],
         "tips": ["西红柿加盐炒出沙，汤底才浓郁"]},
        {"name": "番茄炒蛋", "match_score": 92, "time_minutes": 20, "difficulty": "简单",
         "missing_seasonings": [], "steps": [{"title": "打蛋", "detail": "打散"}], "tips": []},
        {"name": "葱油拌面", "match_score": 85, "time_minutes": 10, "difficulty": "简单",
         "missing_seasonings": [], "steps": [{"title": "煮面", "detail": "水开下面"}], "tips": []},
    ]
}


def _create_recipe(client, auth_headers, monkeypatch):
    async def _fake(**kwargs):
        return VALID_SET

    monkeypatch.setattr(recipe_agent, "ainvoke_json", _fake)
    return client.post(
        "/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=auth_headers
    ).json()["data"][0]


def test_share_card_returns_data_and_qrcode(client, auth_headers, monkeypatch):
    rec = _create_recipe(client, auth_headers, monkeypatch)

    captured = {}

    async def _fake_qr(scene: str, page: str, width: int = 430):
        captured["scene"] = scene
        captured["page"] = page
        return b"\x89PNG-fake-png-bytes"

    monkeypatch.setattr(wechat_service, "get_unlimited_qrcode", _fake_qr)

    res = client.get(f"/api/recipes/{rec['id']}/share-card", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["title"] == "番茄鸡蛋面"
    assert data["match_score"] == 98
    assert data["time_minutes"] == 15
    assert data["difficulty"] == "简单"
    assert data["core_secret"] == "西红柿加盐炒出沙，汤底才浓郁"  # tips[0]
    assert data["steps_count"] == 2
    assert data["qrcode_base64"].startswith("data:image/png;base64,")
    # scene 必须是 32 位 hex（去横线 UUID），page 指向菜谱详情页
    assert captured["scene"] == rec["id"].replace("-", "")
    assert captured["page"] == "pages/recipe-detail/index"


def test_share_card_qrcode_failure_degrades(client, auth_headers, monkeypatch):
    """小程序码生成失败 → qrcode_base64 为 null，卡片数据仍返回。"""
    rec = _create_recipe(client, auth_headers, monkeypatch)

    async def _boom(scene: str, page: str, width: int = 430):
        raise WeChatError("mock qr fail")

    monkeypatch.setattr(wechat_service, "get_unlimited_qrcode", _boom)

    res = client.get(f"/api/recipes/{rec['id']}/share-card", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["title"] == "番茄鸡蛋面"
    assert data["qrcode_base64"] is None


def test_share_card_not_owner_404(client, auth_headers, make_headers, monkeypatch):
    rec = _create_recipe(client, auth_headers, monkeypatch)
    other_headers = make_headers("openid-other")
    res = client.get(f"/api/recipes/{rec['id']}/share-card", headers=other_headers)
    assert res.status_code == 404


def test_share_card_not_found_404(client, auth_headers):
    res = client.get(
        "/api/recipes/00000000-0000-0000-0000-000000000000/share-card", headers=auth_headers
    )
    assert res.status_code == 404


def test_share_card_requires_auth_401(client):
    res = client.get("/api/recipes/00000000-0000-0000-0000-000000000000/share-card")
    assert res.status_code == 401
