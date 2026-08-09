"""注销账号 TDD：DELETE /api/users/me 级联删除用户及其数据。"""
from app.services.agents import qa_agent, recipe_agent

VALID_QA = {
    "core_secret": "先焯透再煸油。",
    "ingredients": ["五花肉"],
    "steps": ["冷水下锅焯透"],
    "avoid_pitfalls": ["别大火"],
    "sources": [],
}
VALID_SET = {
    "recipes": [
        {"name": "番茄鸡蛋面", "match_score": 98, "time_minutes": 15, "difficulty": "简单",
         "missing_seasonings": [], "steps": [{"title": "炒", "detail": "煸炒出沙"}], "tips": []},
        {"name": "番茄炒蛋", "match_score": 92, "time_minutes": 20, "difficulty": "简单",
         "missing_seasonings": [], "steps": [{"title": "打蛋", "detail": "打散"}], "tips": []},
        {"name": "葱油拌面", "match_score": 85, "time_minutes": 10, "difficulty": "简单",
         "missing_seasonings": [], "steps": [{"title": "煮面", "detail": "水开下面"}], "tips": []},
    ]
}


def test_delete_account_invalidates_token(client, auth_headers):
    res = client.delete("/api/users/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["code"] == 0
    assert res.json()["message"] == "账号已注销"

    me = client.get("/api/users/me", headers=auth_headers)
    assert me.status_code == 401


def test_delete_account_cascades_data_and_relogin_fresh(client, auth_headers, make_headers, monkeypatch):
    async def _fake_qa(**kwargs):
        return VALID_QA

    async def _fake_recipe(**kwargs):
        return VALID_SET

    monkeypatch.setattr(qa_agent, "ainvoke_json", _fake_qa)
    monkeypatch.setattr(recipe_agent, "ainvoke_json", _fake_recipe)

    # 造数据：问答 + 菜谱 + 各自收藏
    qa = client.post("/api/qa/ask", json={"question": "红烧肉怎么不腻"}, headers=auth_headers).json()["data"]
    rec = client.post(
        "/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=auth_headers
    ).json()["data"][0]
    client.post("/api/favorites", json={"content_type": "qa", "content_id": qa["id"]}, headers=auth_headers)
    client.post("/api/favorites", json={"content_type": "recipe", "content_id": rec["id"]}, headers=auth_headers)

    old_user_id = client.get("/api/users/me", headers=auth_headers).json()["data"]["id"]

    res = client.delete("/api/users/me", headers=auth_headers)
    assert res.status_code == 200

    # 同 openid 重新登录 → 全新用户（不同 id），且历史/收藏为空（旧数据已级联清除）
    fresh = make_headers("openid-test")
    me = client.get("/api/users/me", headers=fresh).json()["data"]
    assert me["id"] != old_user_id
    assert me["nickname"] is None
    assert client.get("/api/qa/history", headers=fresh).json()["data"] == []
    assert client.get("/api/favorites", headers=fresh).json()["data"] == []


def test_delete_account_requires_auth_401(client):
    res = client.delete("/api/users/me")
    assert res.status_code == 401


def test_delete_account_isolated_from_other_users(client, auth_headers, make_headers, monkeypatch):
    async def _fake_qa(**kwargs):
        return VALID_QA

    monkeypatch.setattr(qa_agent, "ainvoke_json", _fake_qa)

    other_headers = make_headers("openid-other")
    client.post("/api/qa/ask", json={"question": "他人问题"}, headers=other_headers)

    # 删除 openid-test，不影响 openid-other
    client.delete("/api/users/me", headers=auth_headers)
    assert client.get("/api/qa/history", headers=other_headers).json()["data"]
