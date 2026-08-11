"""多智能体协作 TDD：POST /api/agents/collaborate 营养师+大厨+采购并行输出。

原型 05 屏5：AI 主厨团三个 Agent 同时输出，交叉校验更可靠。
"""
from app.routers import agents as agents_router
from app.services.agents import collaborate_agent

VALID_COLLAB = {
    "nutritionist": {
        "calories_kcal": 1400,
        "protein_g": 85,
        "advice": "蛋白质 + 蔬菜占比提至 60%",
        "avoided_allergens": ["花生", "海鲜"],
    },
    "chef": {
        "dish_name": "鸡胸藜麦碗",
        "technique": "鸡胸低温慢煮锁汁，藜麦提前浸泡口感更Q",
        "plating": "藜麦打底，鸡胸切条铺面，淋柠檬汁",
    },
    "shopper": {
        "categories": [
            {"name": "蛋奶肉禽", "items": [{"name": "鸡胸肉", "quantity": "300g"}]},
            {"name": "米面杂粮", "items": [{"name": "藜麦", "quantity": "200g"}]},
        ],
        "tips": "周末超市临期区采购更省钱",
    },
}


def _mock_collab(monkeypatch, result=VALID_COLLAB):
    async def _fake(ingredients: list[str], prefs: dict | None = None) -> dict:
        return {"result": result, "error": None}

    monkeypatch.setattr(collaborate_agent, "run_collaborate", _fake)
    return _fake


def test_collaborate_success(client, auth_headers, monkeypatch):
    """三 Agent 并行输出完整结果。"""
    _mock_collab(monkeypatch)
    res = client.post(
        "/api/agents/collaborate",
        json={"ingredients": ["鸡胸肉", "藜麦", "西兰花"]},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["nutritionist"]["calories_kcal"] == 1400
    assert data["chef"]["dish_name"] == "鸡胸藜麦碗"
    assert len(data["shopper"]["categories"]) == 2


def test_collaborate_injects_prefs(client, auth_headers, monkeypatch):
    """偏好注入到 agent。"""
    captured = {}

    async def _fake(ingredients: list[str], prefs: dict | None = None) -> dict:
        captured["prefs"] = prefs
        return {"result": VALID_COLLAB, "error": None}

    monkeypatch.setattr(collaborate_agent, "run_collaborate", _fake)
    client.put(
        "/api/users/me/preferences",
        json={"allergies": ["海鲜"], "spiciness": 1},
        headers=auth_headers,
    )
    res = client.post(
        "/api/agents/collaborate", json={"ingredients": ["鸡胸"]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert captured["prefs"]["spiciness"] == 1


def test_collaborate_agent_failure_502(client, auth_headers, monkeypatch):
    """任一 Agent 失败 → 502。"""

    async def _fake(ingredients: list[str], prefs: dict | None = None) -> dict:
        return {"result": None, "error": "mock 生成失败"}

    monkeypatch.setattr(collaborate_agent, "run_collaborate", _fake)
    res = client.post(
        "/api/agents/collaborate", json={"ingredients": ["鸡胸"]}, headers=auth_headers
    )
    assert res.status_code == 502


def test_collaborate_requires_ingredients(client, auth_headers):
    """空食材 → 422。"""
    res = client.post("/api/agents/collaborate", json={"ingredients": []}, headers=auth_headers)
    assert res.status_code == 422


def test_collaborate_requires_auth(client):
    """未登录 → 401。"""
    res = client.post("/api/agents/collaborate", json={"ingredients": ["鸡胸"]})
    assert res.status_code == 401


def test_collaborate_rate_limit(client, auth_headers, monkeypatch):
    """超限 → 429。"""
    from app.core.response import AppError

    _mock_collab(monkeypatch)

    async def _over(db, user_id, limit):
        raise AppError("今日调用已达上限，明日再来吧", code=429, status_code=429)

    monkeypatch.setattr(agents_router, "ensure_within_limit", _over)
    res = client.post(
        "/api/agents/collaborate", json={"ingredients": ["鸡胸"]}, headers=auth_headers
    )
    assert res.status_code == 429
    assert "上限" in res.json()["message"]


# ---------- 并行机制（agent 层） ----------
def test_collaborate_runs_three_agents_in_parallel(monkeypatch):
    """run_collaborate 内部三个子 agent 并行执行且结果合并。"""
    import asyncio

    from app.services.agents import collaborate_agent

    captured: list[str] = []

    async def _fake_ainvoke(model, system, user, enable_search):
        captured.append(user[:20])
        await asyncio.sleep(0.02)  # 模拟耗时
        # 依据 prompt 内容返回对应角色
        if "营养师" in system:
            return {"calories_kcal": 1400, "protein_g": 85, "advice": "高蛋白", "avoided_allergens": []}
        if "大厨" in system:
            return {"dish_name": "鸡胸藜麦碗", "technique": "慢煮", "plating": "藜麦打底"}
        return {"categories": [{"name": "蛋奶肉禽", "items": [{"name": "鸡胸", "quantity": "300g"}]}], "tips": "省钱"}

    monkeypatch.setattr(collaborate_agent, "ainvoke_json", _fake_ainvoke)

    async def _run():
        return await collaborate_agent.run_collaborate(["鸡胸", "藜麦"], {"spiciness": 1})

    out = asyncio.run(_run())
    assert out["error"] is None
    result = out["result"]
    assert result["nutritionist"]["protein_g"] == 85
    assert result["chef"]["dish_name"] == "鸡胸藜麦碗"
    assert result["shopper"]["categories"][0]["name"] == "蛋奶肉禽"
    assert len(captured) == 3  # 三个子 agent 各调用一次
