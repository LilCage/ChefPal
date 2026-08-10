"""3 天膳食规划 TDD：生成（mock LLM）/ latest / 偏好注入 / 校验 / 风控。"""
from app.services.agents import planner_agent

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
        {
            "day_label": "明天",
            "meals": [
                {"name": "早餐", "total_kcal": 360, "dishes": [{"name": "豆浆 + 全麦馒头"}]},
                {"name": "午餐", "total_kcal": 580, "dishes": [{"name": "鸡胸藜麦碗"}]},
                {"name": "晚餐", "total_kcal": 440, "dishes": [{"name": "清炒时蔬"}, {"name": "米饭"}]},
            ],
            "total_kcal": 1380,
            "protein_g": 60,
        },
        {
            "day_label": "后天",
            "meals": [
                {"name": "早餐", "total_kcal": 350, "dishes": [{"name": "水煮蛋 + 玉米"}]},
                {"name": "午餐", "total_kcal": 590, "dishes": [{"name": "牛肉面"}]},
                {"name": "晚餐", "total_kcal": 430, "dishes": [{"name": "番茄炖牛腩(去油)"}]},
            ],
            "total_kcal": 1370,
            "protein_g": 58,
        },
    ]
}


def _mock_planner(monkeypatch, result=VALID_PLAN):
    async def _fake(prefs: dict | None = None) -> dict:
        return {"result": result, "error": None}

    monkeypatch.setattr(planner_agent, "run_planner", _fake)
    return _fake


# ---------- 生成 ----------
def test_generate_plan(client, auth_headers, monkeypatch):
    _mock_planner(monkeypatch)
    res = client.post("/api/plans/generate", json={}, headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert len(data["data"]["days"]) == 3
    assert data["data"]["days"][0]["day_label"] == "今天"
    assert len(data["data"]["days"][0]["meals"]) == 3


def test_generate_plan_injects_prefs(client, auth_headers, monkeypatch):
    captured = {}
    async def _fake(prefs: dict | None = None) -> dict:
        captured["prefs"] = prefs
        return {"result": VALID_PLAN, "error": None}

    monkeypatch.setattr(planner_agent, "run_planner", _fake)

    # 先在「我的」设置偏好
    client.put(
        "/api/users/me/preferences",
        json={"allergies": ["花生"], "spiciness": 2, "saltiness": "偏淡", "skill": "厨房小白"},
        headers=auth_headers,
    )
    res = client.post("/api/plans/generate", json={}, headers=auth_headers)
    assert res.status_code == 200
    assert captured["prefs"]["allergies"] == ["花生"]
    assert captured["prefs"]["spiciness"] == 2


def test_generate_plan_body_prefs_override(client, auth_headers, monkeypatch):
    captured = {}
    async def _fake(prefs: dict | None = None) -> dict:
        captured["prefs"] = prefs
        return {"result": VALID_PLAN, "error": None}

    monkeypatch.setattr(planner_agent, "run_planner", _fake)
    res = client.post(
        "/api/plans/generate", json={"prefs": {"saltiness": "偏咸"}}, headers=auth_headers
    )
    assert res.status_code == 200
    assert captured["prefs"]["saltiness"] == "偏咸"


def test_generate_plan_failure_502(client, auth_headers, monkeypatch):
    async def _fake(prefs: dict | None = None) -> dict:
        return {"result": None, "error": "mock 生成失败"}

    monkeypatch.setattr(planner_agent, "run_planner", _fake)
    res = client.post("/api/plans/generate", json={}, headers=auth_headers)
    assert res.status_code == 502
    assert "失败" in res.json()["message"]


def test_generate_plan_requires_auth(client):
    assert client.post("/api/plans/generate", json={}).status_code == 401


def test_generate_plan_rate_limit(client, auth_headers, monkeypatch, make_headers):
    from app.core.response import AppError
    from app.routers import plans as plans_router

    _mock_planner(monkeypatch)

    async def _over(db, user_id, limit):
        raise AppError("今日 AI 调用已达上限，明日再来吧", code=429, status_code=429)

    monkeypatch.setattr(plans_router, "ensure_within_limit", _over)
    res = client.post("/api/plans/generate", json={}, headers=auth_headers)
    assert res.status_code == 429
    assert "上限" in res.json()["message"]


# ---------- latest ----------
def test_latest_plan(client, auth_headers, monkeypatch):
    _mock_planner(monkeypatch)
    client.post("/api/plans/generate", json={}, headers=auth_headers)
    res = client.get("/api/plans/latest", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()["data"]["data"]["days"]) == 3


def test_latest_plan_empty_404(client, auth_headers):
    res = client.get("/api/plans/latest", headers=auth_headers)
    assert res.status_code == 404


def test_latest_plan_isolated_per_user(client, auth_headers, make_headers, monkeypatch):
    _mock_planner(monkeypatch)
    client.post("/api/plans/generate", json={}, headers=auth_headers)
    other = make_headers("openid-other")
    res = client.get("/api/plans/latest", headers=other)
    assert res.status_code == 404


def test_latest_plan_requires_auth(client):
    assert client.get("/api/plans/latest").status_code == 401
