"""购物清单 TDD：从计划生成 / 勾选切换 / latest / 错误分支。"""
import uuid

from app.services.agents import planner_agent
from app.services import shopping as shopping_service

VALID_PLAN = {
    "days": [
        {
            "day_label": "今天",
            "meals": [
                {"name": "早餐", "total_kcal": 380, "dishes": [{"name": "牛奶燕麦粥 + 水煮蛋"}]},
                {"name": "午餐", "total_kcal": 560, "dishes": [{"name": "番茄鸡蛋面"}]},
                {"name": "晚餐", "total_kcal": 420, "dishes": [{"name": "清蒸鲈鱼"}, {"name": "蒜蓉西兰花"}]},
            ],
            "total_kcal": 1360,
            "protein_g": 55,
        },
    ]
}

VALID_SHOPPING = {
    "categories": [
        {"name": "蔬菜水果", "items": [{"name": "西红柿", "quantity": "2 个"}, {"name": "西兰花", "quantity": "1 颗"}]},
        {"name": "蛋奶肉禽", "items": [{"name": "鸡蛋", "quantity": "6 枚"}, {"name": "鲈鱼", "quantity": "1 条"}]},
        {"name": "调料辅料", "items": [{"name": "小葱", "quantity": "1 把"}]},
    ]
}


def _create_plan(client, auth_headers, monkeypatch):
    async def _fake(prefs: dict | None = None, days: int = 3) -> dict:
        return {"result": VALID_PLAN, "error": None}

    monkeypatch.setattr(planner_agent, "run_planner", _fake)
    res = client.post("/api/plans/generate", json={}, headers=auth_headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _mock_shopping(monkeypatch, result=VALID_SHOPPING, error=None):
    import copy

    async def _fake(plan_data: dict) -> dict:
        if error:
            raise error
        return copy.deepcopy(result)  # 深拷贝：避免路由 _enrich_items 污染共享常量

    monkeypatch.setattr(shopping_service, "generate_shopping_list", _fake)
    return _fake


# ---------- 生成 ----------
def test_generate_shopping_from_latest_plan(client, auth_headers, monkeypatch):
    _create_plan(client, auth_headers, monkeypatch)
    _mock_shopping(monkeypatch)
    res = client.post("/api/shopping-list/generate", json={}, headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    cats = data["data"]["categories"]
    assert len(cats) == 3
    # 每项补了 item_id 与初始 checked=False
    first = cats[0]["items"][0]
    assert "item_id" in first
    assert first["checked"] is False
    assert first["name"] == "西红柿"


def test_generate_shopping_with_meal_plan_id(client, auth_headers, make_headers, monkeypatch):
    plan = _create_plan(client, auth_headers, monkeypatch)
    _mock_shopping(monkeypatch)
    res = client.post(
        "/api/shopping-list/generate", json={"meal_plan_id": plan["id"]}, headers=auth_headers
    )
    assert res.status_code == 200

    # 他人 plan id → 404
    other = make_headers("openid-other")
    res2 = client.post(
        "/api/shopping-list/generate", json={"meal_plan_id": plan["id"]}, headers=other
    )
    assert res2.status_code == 404


def test_generate_shopping_no_plan_400(client, auth_headers, monkeypatch):
    _mock_shopping(monkeypatch)
    res = client.post("/api/shopping-list/generate", json={}, headers=auth_headers)
    assert res.status_code == 400
    assert "膳食计划" in res.json()["message"]


def test_generate_shopping_service_error_502(client, auth_headers, monkeypatch):
    _create_plan(client, auth_headers, monkeypatch)
    _mock_shopping(monkeypatch, error=shopping_service.ShoppingError("mock 生成失败"))
    res = client.post("/api/shopping-list/generate", json={}, headers=auth_headers)
    assert res.status_code == 502


def test_generate_shopping_requires_auth(client):
    assert client.post("/api/shopping-list/generate", json={}).status_code == 401


# ---------- 勾选切换 ----------
def test_toggle_checked(client, auth_headers, monkeypatch):
    _create_plan(client, auth_headers, monkeypatch)
    _mock_shopping(monkeypatch)
    item = client.post("/api/shopping-list/generate", json={}, headers=auth_headers).json()["data"]
    list_id = item["id"]
    item_id = item["data"]["categories"][0]["items"][0]["item_id"]

    res = client.put(
        f"/api/shopping-list/{list_id}/items/{item_id}/checked", json={"checked": True}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["data"] == {"item_id": item_id, "checked": True}

    # 持久化：latest 里该项已勾选
    latest = client.get("/api/shopping-list/latest", headers=auth_headers).json()["data"]
    assert latest["data"]["categories"][0]["items"][0]["checked"] is True


def test_toggle_checked_404(client, auth_headers, monkeypatch):
    _create_plan(client, auth_headers, monkeypatch)
    _mock_shopping(monkeypatch)
    item = client.post("/api/shopping-list/generate", json={}, headers=auth_headers).json()["data"]
    # 不存在的 item_id
    res = client.put(
        f"/api/shopping-list/{item['id']}/items/{uuid.uuid4()}/checked",
        json={"checked": True},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_toggle_checked_not_owned_404(client, auth_headers, make_headers, monkeypatch):
    _create_plan(client, auth_headers, monkeypatch)
    _mock_shopping(monkeypatch)
    item = client.post("/api/shopping-list/generate", json={}, headers=auth_headers).json()["data"]
    other = make_headers("openid-other")
    res = client.put(
        f"/api/shopping-list/{item['id']}/items/x/checked",
        json={"checked": True},
        headers=other,
    )
    assert res.status_code == 404


# ---------- latest ----------
def test_latest_shopping(client, auth_headers, monkeypatch):
    _create_plan(client, auth_headers, monkeypatch)
    _mock_shopping(monkeypatch)
    client.post("/api/shopping-list/generate", json={}, headers=auth_headers)
    res = client.get("/api/shopping-list/latest", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()["data"]["data"]["categories"]) == 3


def test_latest_shopping_empty_404(client, auth_headers):
    res = client.get("/api/shopping-list/latest", headers=auth_headers)
    assert res.status_code == 404
