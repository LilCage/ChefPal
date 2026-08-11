"""STEP 5 · 收藏闭环 TDD：多态收藏（qa/recipe）增删查 + 归属校验。"""
from app.services.agents import qa_agent, recipe_agent

VALID_QA = {
    "dish_name": "红烧肉",  # 方案C起语义校验要求单菜必须 dish_name+steps
    "core_secret": "先焯透再煸油。",
    "ingredients": ["五花肉"],
    "steps": ["冷水下锅焯透"],
    "avoid_pitfalls": ["别大火"],
    "sources": [],
}
VALID_SET = {
    "recipes": [
        {"name": "番茄鸡蛋面", "match_score": 98, "time_minutes": 15, "difficulty": "简单",
         "missing_seasonings": [], "steps": [{"title": "炒", "detail": "煸炒出沙"}], "tips": [], "style": "清爽快手"},
        {"name": "番茄炒蛋", "match_score": 92, "time_minutes": 20, "difficulty": "简单",
         "missing_seasonings": [], "steps": [{"title": "打蛋", "detail": "打散"}], "tips": [], "style": "浓香下饭"},
        {"name": "葱油拌面", "match_score": 85, "time_minutes": 10, "difficulty": "简单",
         "missing_seasonings": [], "steps": [{"title": "煮面", "detail": "水开下面"}], "tips": [], "style": "清爽快手"},
    ]
}


def _mock_ainvoke_qa(monkeypatch, payload=VALID_QA):
    async def _fake(**kwargs):
        return payload

    monkeypatch.setattr(qa_agent, "ainvoke_json", _fake)


def _mock_ainvoke_recipe(monkeypatch, payload=VALID_SET):
    async def _fake(**kwargs):
        return payload

    monkeypatch.setattr(recipe_agent, "ainvoke_json", _fake)


def _create_qa(client, headers, monkeypatch):
    _mock_ainvoke_qa(monkeypatch)
    return client.post("/api/qa/ask", json={"question": "红烧肉怎么不腻"}, headers=headers).json()["data"]


def _create_recipe(client, headers, monkeypatch):
    _mock_ainvoke_recipe(monkeypatch)
    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=headers)
    return res.json()["data"][0]


def test_add_and_list_qa_favorite(client, auth_headers, monkeypatch):
    qa = _create_qa(client, auth_headers, monkeypatch)
    res = client.post("/api/favorites", json={"content_type": "qa", "content_id": qa["id"]}, headers=auth_headers)
    assert res.status_code == 200

    listed = client.get("/api/favorites?type=qa", headers=auth_headers).json()["data"]
    assert len(listed) == 1
    assert listed[0]["content"]["question"] == "红烧肉怎么不腻"


def test_add_recipe_favorite_and_list(client, auth_headers, monkeypatch):
    rec = _create_recipe(client, auth_headers, monkeypatch)
    client.post("/api/favorites", json={"content_type": "recipe", "content_id": rec["id"]}, headers=auth_headers)

    listed = client.get("/api/favorites?type=recipe", headers=auth_headers).json()["data"]
    assert len(listed) == 1
    assert listed[0]["content"]["title"] == "番茄鸡蛋面"


def test_favorite_idempotent(client, auth_headers, monkeypatch):
    qa = _create_qa(client, auth_headers, monkeypatch)
    first = client.post("/api/favorites", json={"content_type": "qa", "content_id": qa["id"]}, headers=auth_headers)
    second = client.post("/api/favorites", json={"content_type": "qa", "content_id": qa["id"]}, headers=auth_headers)
    assert first.status_code == 200 and second.status_code == 200
    listed = client.get("/api/favorites", headers=auth_headers).json()["data"]
    assert len(listed) == 1


def test_remove_favorite(client, auth_headers, monkeypatch):
    qa = _create_qa(client, auth_headers, monkeypatch)
    client.post("/api/favorites", json={"content_type": "qa", "content_id": qa["id"]}, headers=auth_headers)
    res = client.delete(f"/api/favorites?content_type=qa&content_id={qa['id']}", headers=auth_headers)
    assert res.status_code == 200
    assert client.get("/api/favorites", headers=auth_headers).json()["data"] == []


def test_favorite_others_content_returns_404(client, auth_headers, make_headers, monkeypatch):
    """不能收藏他人内容。"""
    other = _create_qa(client, auth_headers, monkeypatch)
    other_headers = make_headers("openid-other")
    res = client.post("/api/favorites", json={"content_type": "qa", "content_id": other["id"]}, headers=other_headers)
    assert res.status_code == 404


def test_favorite_nonexistent_404(client, auth_headers):
    res = client.post(
        "/api/favorites",
        json={"content_type": "qa", "content_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_favorite_invalid_type_422(client, auth_headers):
    res = client.post("/api/favorites", json={"content_type": "post", "content_id": "00000000-0000-0000-0000-000000000000"}, headers=auth_headers)
    assert res.status_code == 422


def test_favorite_requires_auth_401(client):
    res = client.get("/api/favorites")
    assert res.status_code == 401
