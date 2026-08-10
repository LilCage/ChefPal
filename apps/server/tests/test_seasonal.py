"""时令食材日历 TDD：GET /api/seasonal?month=N 返回当月时令食材 + 推荐搭配。"""
from app.services import seasonal


def test_seasonal_defaults_current_month(client, auth_headers):
    """不传 month 时默认返回当前月份数据。"""
    res = client.get("/api/seasonal", headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert 1 <= data["month"] <= 12
    assert "label" in data and "盛夏" in data["label"]
    assert isinstance(data["items"], list) and len(data["items"]) > 0


def test_seasonal_returns_month_structure(client, auth_headers):
    """指定 8 月：返回 label / items（含 emoji、level、note）/ pairing 推荐。"""
    res = client.get("/api/seasonal?month=8", headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["month"] == 8
    assert data["label"] == "8 月 · 盛夏"

    item = data["items"][0]
    assert {"name", "emoji", "level", "note"} <= set(item.keys())
    assert item["level"] in ("应季", "正当时")

    pairing = data["pairing"]
    assert "ingredients" in pairing and "dish" in pairing and "note" in pairing


def test_seasonal_month_boundary(client, auth_headers):
    """月份边界：1 与 12 均合法；0 / 13 返回 422。"""
    assert client.get("/api/seasonal?month=1", headers=auth_headers).status_code == 200
    assert client.get("/api/seasonal?month=12", headers=auth_headers).status_code == 200
    assert client.get("/api/seasonal?month=0", headers=auth_headers).status_code == 422
    assert client.get("/api/seasonal?month=13", headers=auth_headers).status_code == 422


def test_seasonal_items_have_valid_emoji_and_level(client, auth_headers):
    """所有月份的食材项都有 emoji 且等级合法。"""
    for m in range(1, 13):
        data = seasonal.get_month(m)
        for item in data["items"]:
            assert item["emoji"], f"月{m} 项 {item['name']} 缺 emoji"
            assert item["level"] in ("应季", "正当时")


def test_seasonal_pairing_references_seasonal_items(client, auth_headers):
    """推荐搭配的食材应出现在当月 items 中（基于真实季节的合理推荐）。"""
    data = seasonal.get_month(8)
    names = {i["name"] for i in data["items"]}
    for ing in data["pairing"]["ingredients"]:
        assert ing in names, f"推荐搭配食材 {ing} 不在 8 月食材列表中"


def test_seasonal_requires_auth(client):
    """公开数据仍需登录态（与全应用一致）。"""
    assert client.get("/api/seasonal").status_code == 401
