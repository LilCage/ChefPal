"""菜谱知识库接口测试：菜名查库 / 按 id / 未收录 AI 现生成。"""
from sqlalchemy import func, select

from app.models.recipe_kb import RecipeKB
from app.routers import kb as kb_router
from app.services import kb as kb_service

DIM = 1024


def _v(*idx: int) -> list[float]:
    v = [0.0] * DIM
    for i in idx:
        v[i] = 1.0
    return v


async def _make_entry(db, *, title, kind="recipe", steps=None, category="肉菜") -> RecipeKB:
    e = RecipeKB(
        kind=kind,
        title=title,
        summary="简介",
        content="",
        ingredients=["a"],
        steps=steps or ["1. 步骤"],
        tips=["坑"],
        time_minutes=20,
        difficulty="简单",
        style="",
        category=category,
        source_type="howtocook",
        source_id=f"x/{title}.md",
        hit_count=0,
        embedding=_v(0),
    )
    db.add(e)
    return e


# ---------- GET /kb/recipes?q= ----------


async def test_get_recipe_by_title_found(client, auth_headers, db):
    e = await _make_entry(db, title="红烧肉", steps=["1. 焯水", "2. 焖"])
    await db.commit()

    res = client.get("/api/kb/recipes", params={"q": "红烧肉的做法"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["title"] == "红烧肉"
    assert data["kind"] == "recipe"
    assert data["steps"] == ["1. 焯水", "2. 焖"]


async def test_get_recipe_by_title_not_found_404(client, auth_headers, db):
    res = client.get("/api/kb/recipes", params={"q": "不存在的菜"}, headers=auth_headers)
    assert res.status_code == 404
    assert res.json()["code"] == 404


# ---------- GET /kb/{id} ----------


async def test_get_entry_by_id(client, auth_headers, db):
    e = await _make_entry(db, title="西红柿炒鸡蛋", category="素菜")
    await db.commit()

    res = client.get(f"/api/kb/{e.id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "西红柿炒鸡蛋"


async def test_get_entry_404(client, auth_headers, db):
    import uuid

    res = client.get(f"/api/kb/{uuid.uuid4()}", headers=auth_headers)
    assert res.status_code == 404


# ---------- POST /kb/generate ----------


async def test_generate_returns_existing_without_ai(client, auth_headers, db, monkeypatch):
    e = await _make_entry(db, title="红烧肉")
    await db.commit()

    async def _should_not_call(**kwargs):
        raise AssertionError("已收录不应调 AI")

    monkeypatch.setattr(kb_router, "ainvoke_json", _should_not_call)

    res = client.post("/api/kb/generate", json={"title": "红烧肉"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["from_kb"] is True
    assert data["title"] == "红烧肉"


async def test_generate_missing_calls_ai_and_stores(client, auth_headers, db, monkeypatch):
    async def _fake_ainvoke(**kwargs):
        assert "红烧肉" in kwargs["user"]
        return {
            "dish_name": "红烧肉",
            "core_secret": "先焯透再煸油",
            "ingredients": ["五花肉", "冰糖"],
            "steps": ["1. 焯水", "2. 炒糖色", "3. 焖 40 分钟"],
            "avoid_pitfalls": ["小火"],
            "sources": [],
            "recommendations": None,
        }

    monkeypatch.setattr(kb_router, "ainvoke_json", _fake_ainvoke)

    async def _fake_emb(texts, *, input_type="document"):
        return [[0.5] * DIM for _ in texts]

    monkeypatch.setattr(kb_service, "aembed_texts", _fake_emb)

    res = client.post("/api/kb/generate", json={"title": "红烧肉"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["from_kb"] is False
    assert data["title"] == "红烧肉"
    assert data["steps"] == ["1. 焯水", "2. 炒糖色", "3. 焖 40 分钟"]
    # 已入库
    cnt = (await db.execute(select(func.count()).select_from(RecipeKB).where(RecipeKB.title == "红烧肉"))).scalar()
    assert cnt == 1


async def test_generate_empty_shell_502(client, auth_headers, db, monkeypatch):
    async def _fake_ainvoke(**kwargs):
        return {"core_secret": "只有一句话"}

    monkeypatch.setattr(kb_router, "ainvoke_json", _fake_ainvoke)

    res = client.post("/api/kb/generate", json={"title": "某个新菜"}, headers=auth_headers)
    assert res.status_code == 502


async def test_generate_force_refills_steps_for_stub(client, auth_headers, db, monkeypatch):
    """已收录但无步骤的推荐条目标签：force=true 重新生成完整做法并覆盖补全（沿用原条目不新建）。"""
    e = RecipeKB(
        kind="recipe",
        title="凉拌毛豆",
        summary="毛豆剪角煮熟，趁热拌蒜末…",
        content="",
        ingredients=["毛豆"],
        steps=[],
        prep_steps=[],
        cook_steps=[],
        tips=[],
        time_minutes=10,
        difficulty="简单",
        style="清爽快手",
        category="素菜",
        source_type="qa_answer",
        source_id="some-qa-id",
        hit_count=0,
        embedding=_v(0),
    )
    db.add(e)
    await db.commit()
    stub_id = e.id

    async def _fake_ainvoke(**kwargs):
        return {
            "dish_name": "凉拌毛豆",
            "core_secret": "毛豆煮熟拌料",
            "ingredients": ["毛豆", "蒜"],
            "steps": ["1. 剪角", "2. 煮熟", "3. 拌料"],
            "avoid_pitfalls": ["别煮过"],
            "sources": [],
            "recommendations": None,
        }

    monkeypatch.setattr(kb_router, "ainvoke_json", _fake_ainvoke)

    async def _fake_emb(texts, *, input_type="document"):
        return [[0.5] * DIM for _ in texts]

    monkeypatch.setattr(kb_service, "aembed_texts", _fake_emb)

    res = client.post("/api/kb/generate", json={"title": "凉拌毛豆", "force": True}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["steps"] == ["1. 剪角", "2. 煮熟", "3. 拌料"]
    assert data["id"] == str(stub_id)  # 覆盖原条目，不新建
    cnt = (await db.execute(select(func.count()).select_from(RecipeKB).where(RecipeKB.id == stub_id))).scalar()
    assert cnt == 1


async def test_generate_force_does_not_override_howtocook(client, auth_headers, db, monkeypatch):
    """HowToCook 权威条目即使 force=true 也不重新生成，直接返回原条目。"""
    e = await _make_entry(db, title="清蒸鲈鱼")
    await db.commit()

    async def _should_not_call(**kwargs):
        raise AssertionError("HowToCook 不应被 force 覆盖")

    monkeypatch.setattr(kb_router, "ainvoke_json", _should_not_call)

    res = client.post("/api/kb/generate", json={"title": "清蒸鲈鱼", "force": True}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["from_kb"] is True


async def test_kb_api_requires_auth(client):
    assert client.get("/api/kb/recipes", params={"q": "红烧肉"}).status_code == 401
    assert client.post("/api/kb/generate", json={"title": "红烧肉"}).status_code == 401
