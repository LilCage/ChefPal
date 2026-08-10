"""STEP 4 · 菜谱闭环 TDD：mock LLM → TOP3 生成/落库/详情/偏好注入/降级。"""
from app.services.agents import recipe_agent

VALID_SET = {
    "recipes": [
        {
            "name": "番茄鸡蛋面",
            "match_score": 98,
            "time_minutes": 15,
            "difficulty": "简单",
            "style": "清爽快手",
            "missing_seasonings": ["葱末"],
            "steps": [{"title": "西红柿处理", "detail": "切块加盐煸炒出沙，约3分钟"}],
            "tips": ["西红柿加盐炒出沙，汤底才浓郁"],
        },
        {
            "name": "番茄炒蛋",
            "match_score": 92,
            "time_minutes": 20,
            "difficulty": "简单",
            "style": "浓香下饭",
            "missing_seasonings": ["糖"],
            "steps": [{"title": "打蛋", "detail": "蛋液打散加少许盐"}],
            "tips": [],
        },
        {
            "name": "葱油拌面",
            "match_score": 85,
            "time_minutes": 10,
            "difficulty": "简单",
            "style": "清爽快手",
            "missing_seasonings": ["小葱"],
            "steps": [{"title": "煮面", "detail": "水开下面，中火煮5分钟"}],
            "tips": [],
        },
    ]
}


def _mock_ainvoke(monkeypatch, payload):
    async def _fake(**kwargs):
        return payload(kwargs) if callable(payload) else payload

    monkeypatch.setattr(recipe_agent, "ainvoke_json", _fake)


def test_generate_saves_three_and_detail(client, auth_headers, monkeypatch):
    _mock_ainvoke(monkeypatch, VALID_SET)
    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋", "面条"]}, headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    recipes = body["data"]
    assert len(recipes) == 3
    assert recipes[0]["title"] == "番茄鸡蛋面"
    assert recipes[0]["match_score"] == 98
    assert recipes[0]["steps"][0]["title"]

    # 详情可查
    rid = recipes[0]["id"]
    detail = client.get(f"/api/recipes/{rid}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["title"] == "番茄鸡蛋面"


def test_generate_fewer_than_3_falls_back_502(client, auth_headers, monkeypatch):
    _mock_ainvoke(monkeypatch, {"recipes": [VALID_SET["recipes"][0]]})
    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers)
    assert res.status_code == 502


def test_generate_requires_auth_401(client):
    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿"]})
    assert res.status_code == 401


def test_generate_invalid_ingredients_422(client, auth_headers):
    res = client.post("/api/recipes/generate", json={"ingredients": []}, headers=auth_headers)
    assert res.status_code == 422


def test_generate_injects_user_preferences(client, auth_headers, monkeypatch):
    """口味偏好（忌口）注入到 Agent 的 user 消息中。"""
    captured = {}

    async def _capture(**kwargs):
        captured["user"] = kwargs["user"]
        return VALID_SET

    monkeypatch.setattr(recipe_agent, "ainvoke_json", _capture)

    client.put("/api/users/me/preferences", json={"allergies": ["花生"], "spiciness": 1}, headers=auth_headers)
    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=auth_headers)
    assert res.status_code == 200
    assert "花生" in captured["user"]
    assert "微辣" in captured["user"]


def test_generate_returns_style(client, auth_headers, monkeypatch):
    """生成的菜谱带风味标签 style 并落库可查。"""
    _mock_ainvoke(monkeypatch, VALID_SET)
    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋", "面条"]}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data[0]["style"] == "清爽快手"
    assert {r["style"] for r in data} == {"清爽快手", "浓香下饭"}  # 多样性 ≥2


def test_generate_retries_when_styles_not_diverse(client, auth_headers, monkeypatch):
    """3 道同 style → 校验拒绝 → 重试（带修正指令）；重试返回多样化 → 接受。"""
    same_style = {**VALID_SET, "recipes": [{**r, "style": "浓香下饭"} for r in VALID_SET["recipes"]]}
    calls: list[str] = []

    def _payload(kwargs):
        calls.append(kwargs.get("user", ""))
        return same_style if len(calls) == 1 else VALID_SET

    _mock_ainvoke(monkeypatch, _payload)
    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert len(calls) == 2  # 首次同 style 被拒，第二次才接受
    assert "重合" in calls[1] or "风味" in calls[1]  # 重试带修正指令
    assert len({r["style"] for r in res.json()["data"]}) >= 2


def test_generate_styles_all_same_falls_back_502(client, auth_headers, monkeypatch):
    """3 道持续同 style（重试后仍不满足）→ 降级 502。"""
    same_style = {**VALID_SET, "recipes": [{**r, "style": "浓香下饭"} for r in VALID_SET["recipes"]]}
    _mock_ainvoke(monkeypatch, same_style)
    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=auth_headers)
    assert res.status_code == 502


def test_get_recipe_not_found_404(client, auth_headers):
    res = client.get("/api/recipes/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert res.status_code == 404
