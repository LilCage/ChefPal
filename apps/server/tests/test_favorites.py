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


# ---------- 知识库菜谱收藏（多做法列表"收藏"落点） ----------


async def test_add_and_list_kb_favorite(client, auth_headers, db):
    from app.models.recipe_kb import RecipeKB

    e = RecipeKB(
        kind="recipe",
        title="南派红烧肉",
        summary="咸甜口，熬糖色慢炖 1.5 小时",
        content="",
        ingredients=["五花肉"],
        steps=["炖"],
        prep_steps=[],
        cook_steps=[],
        tips=[],
        time_minutes=90,
        difficulty="中等",
        style="甜口绵绵",
        category="肉菜",
        source_type="howtocook",
        source_id="dishes/meat_dish/南派红烧肉.md",
        hit_count=5,
        embedding=[0.0] * 1024,
    )
    db.add(e)
    await db.commit()

    res = client.post(
        "/api/favorites", json={"content_type": "kb", "content_id": str(e.id)}, headers=auth_headers
    )
    assert res.status_code == 200

    listed = client.get("/api/favorites?type=kb", headers=auth_headers).json()["data"]
    assert len(listed) == 1
    assert listed[0]["content_type"] == "kb"
    assert listed[0]["content"]["title"] == "南派红烧肉"
    assert listed[0]["content"]["style"] == "甜口绵绵"
    assert listed[0]["content"]["hit_count"] == 5
    assert listed[0]["content_id"] == str(e.id)


async def test_add_kb_favorite_idempotent_and_missing_404(client, auth_headers, db):
    from app.models.recipe_kb import RecipeKB

    e = RecipeKB(
        kind="recipe",
        title="简易红烧肉",
        summary="电饭煲一锅出",
        content="",
        ingredients=[],
        steps=["焖"],
        prep_steps=[],
        cook_steps=[],
        tips=[],
        time_minutes=60,
        difficulty="简单",
        style="",
        category="肉菜",
        source_type="howtocook",
        source_id="dishes/meat_dish/简易红烧肉.md",
        hit_count=0,
        embedding=[0.0] * 1024,
    )
    db.add(e)
    await db.commit()

    r1 = client.post("/api/favorites", json={"content_type": "kb", "content_id": str(e.id)}, headers=auth_headers)
    r2 = client.post("/api/favorites", json={"content_type": "kb", "content_id": str(e.id)}, headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(client.get("/api/favorites?type=kb", headers=auth_headers).json()["data"]) == 1

    missing = client.post(
        "/api/favorites",
        json={"content_type": "kb", "content_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers,
    )
    assert missing.status_code == 404


# ---------- 知识库菜谱取消收藏（此前 DELETE Literal 缺 kb 会 422，回归） ----------


async def test_remove_kb_favorite(client, auth_headers, db):
    from app.models.recipe_kb import RecipeKB

    e = RecipeKB(
        kind="recipe",
        title="北派红烧肉",
        summary="重油慢炖",
        content="",
        ingredients=["五花肉"],
        steps=["炖"],
        prep_steps=[],
        cook_steps=[],
        tips=[],
        time_minutes=90,
        difficulty="中等",
        style="浓香下饭",
        category="肉菜",
        source_type="howtocook",
        source_id="dishes/meat_dish/北派红烧肉.md",
        hit_count=0,
        embedding=[0.0] * 1024,
    )
    db.add(e)
    await db.commit()

    client.post("/api/favorites", json={"content_type": "kb", "content_id": str(e.id)}, headers=auth_headers)
    assert len(client.get("/api/favorites?type=kb", headers=auth_headers).json()["data"]) == 1

    res = client.delete(f"/api/favorites?content_type=kb&content_id={e.id}", headers=auth_headers)
    assert res.status_code == 200, res.text
    assert client.get("/api/favorites?type=kb", headers=auth_headers).json()["data"] == []


async def test_kb_favorite_time_estimated_when_zero(client, auth_headers, db):
    """KB 条目 time_minutes=0（HowToCook 多为此）→ 收藏列表按步骤数估算时长，不显示 0 分钟。"""
    from app.models.recipe_kb import RecipeKB

    e = RecipeKB(
        kind="recipe",
        title="凉拌莴笋",
        summary="焯水断生、过凉水更脆",
        content="",
        ingredients=["莴笋"],
        steps=["1. 去皮切丝", "2. 焯水断生", "3. 过凉水", "4. 拌料"],
        prep_steps=[],
        cook_steps=[],
        tips=[],
        time_minutes=0,
        difficulty="简单",
        style="清爽快手",
        category="素菜",
        source_type="howtocook",
        source_id="dishes/veg/凉拌莴笋.md",
        hit_count=0,
        embedding=[0.0] * 1024,
    )
    db.add(e)
    await db.commit()

    client.post("/api/favorites", json={"content_type": "kb", "content_id": str(e.id)}, headers=auth_headers)
    listed = client.get("/api/favorites?type=kb", headers=auth_headers).json()["data"]
    assert len(listed) == 1
    assert listed[0]["content"]["time_minutes"] == 32  # 4 步 × 8 分钟


# ---------- 收藏状态查询（详情页星标选中态） ----------


def test_favorite_status_toggle(client, auth_headers, monkeypatch):
    qa = _create_qa(client, auth_headers, monkeypatch)

    off = client.get(
        f"/api/favorites/status?content_type=qa&content_id={qa['id']}", headers=auth_headers
    ).json()["data"]
    assert off == {"favorited": False}

    client.post("/api/favorites", json={"content_type": "qa", "content_id": qa["id"]}, headers=auth_headers)
    on = client.get(
        f"/api/favorites/status?content_type=qa&content_id={qa['id']}", headers=auth_headers
    ).json()["data"]
    assert on == {"favorited": True}

    client.delete(f"/api/favorites?content_type=qa&content_id={qa['id']}", headers=auth_headers)
    off2 = client.get(
        f"/api/favorites/status?content_type=qa&content_id={qa['id']}", headers=auth_headers
    ).json()["data"]
    assert off2 == {"favorited": False}
