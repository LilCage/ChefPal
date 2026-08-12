"""AI 口味记忆 TDD：信号记录 / 画像聚合 / 注入文本 / 端点 / 埋点触发 / 注入生效。"""
from app.services import taste_memory as taste_service


# ---------- 服务：信号记录 ----------
def test_record_signal_success(monkeypatch):
    class FakeDB:
        def add(self, sig):
            self.sig = sig

        async def flush(self):
            pass

    db = FakeDB()
    import asyncio

    sig = asyncio.run(taste_service.record_signal(db, "u1", "favorite_recipe", "  浓香下饭  "))
    assert sig.value == "浓香下饭"
    assert sig.signal_type == "favorite_recipe"
    assert sig.user_id == "u1"


def test_record_signal_blank_value_raises():
    import asyncio

    try:
        asyncio.run(taste_service.record_signal(None, "u1", "favorite_recipe", "   "))
        assert False, "应为空值抛错"
    except ValueError:
        pass


# ---------- 服务：画像聚合 ----------
def test_summarize_taste_aggregates(monkeypatch):
    """多条信号 → top 风味 / top 话题按次数排序。"""
    import asyncio

    class FakeDB:
        async def execute(self, stmt):
            # 模拟 recent-first 的 (signal_type, value) 行
            rows = [
                ("favorite_recipe", "浓香下饭"),
                ("favorite_recipe", "浓香下饭"),
                ("favorite_recipe", "清爽快手"),
                ("like_post", "#减脂餐"),
                ("like_post", "#减脂餐"),
                ("like_post", "#一人食"),
                ("favorite_qa", "红烧肉怎么不腻"),
            ]
            return FakeResult(rows)

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    profile = asyncio.run(taste_service.summarize_taste(FakeDB(), "u1"))
    assert profile["preferred_styles"][0] == "浓香下饭"
    assert profile["preferred_topics"][0] == "#减脂餐"
    assert profile["total_signals"] == 7
    assert len(profile["recent_qa_keywords"]) >= 1


def test_summarize_taste_empty(monkeypatch):
    import asyncio

    class FakeResult:
        def all(self):
            return []

    class FakeDB:
        async def execute(self, stmt):
            return FakeResult()

    profile = asyncio.run(taste_service.summarize_taste(FakeDB(), "u1"))
    assert profile == {"preferred_styles": [], "preferred_topics": [], "recent_qa_keywords": [], "total_signals": 0}


# ---------- 服务：注入文本 ----------
def test_build_injection_text_enough_signals():
    profile = {"preferred_styles": ["浓香下饭", "香辣过瘾"], "preferred_topics": ["#减脂餐"], "total_signals": 5}
    text = taste_service.build_injection_text(profile)
    assert "浓香下饭" in text
    assert "#减脂餐" in text


def test_build_injection_text_not_enough():
    profile = {"preferred_styles": ["浓香下饭"], "preferred_topics": [], "total_signals": 2}
    assert taste_service.build_injection_text(profile) == ""


def test_build_injection_text_empty():
    assert taste_service.build_injection_text({"preferred_styles": [], "preferred_topics": [], "total_signals": 0}) == ""


# ---------- 端点：GET / DELETE ----------
def test_taste_memory_get_empty(client, auth_headers):
    res = client.get("/api/users/me/taste-memory", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"] == {
        "preferred_styles": [],
        "preferred_topics": [],
        "recent_qa_keywords": [],
        "total_signals": 0,
    }


def test_taste_memory_requires_auth(client):
    assert client.get("/api/users/me/taste-memory").status_code == 401


def test_taste_memory_clear(client, auth_headers):
    res = client.delete("/api/users/me/taste-memory", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["deleted"] == 0


# ---------- 埋点：收藏菜谱记 style ----------
def test_favorite_recipe_records_style_signal(client, auth_headers, monkeypatch):
    from app.routers import recipes as recipes_router
    from app.models.user import User

    async def _fake_recipe(ingredients, prefs):
        return {
            "result": {
                "recipes": [
                    {
                        "name": "红烧肉",
                        "match_score": 90,
                        "time_minutes": 60,
                        "difficulty": "较难",
                        "style": "浓香下饭",
                        "missing_seasonings": [],
                        "steps": [{"title": "焯水", "detail": "冷水下锅"}],
                        "tips": ["糖色宁浅勿深"],
                    }
                ]
            },
            "error": None,
        }

    monkeypatch.setattr(recipes_router.recipe_agent, "run_recipe", _fake_recipe)
    from sqlalchemy import select

    from app.models.recipe import Recipe

    # 生成菜谱
    res = client.post(
        "/api/recipes/generate",
        json={"ingredients": ["五花肉"]},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    rid = res.json()["data"][0]["id"]

    # 收藏 → 触发口味埋点
    res = client.post("/api/favorites", json={"content_type": "recipe", "content_id": rid}, headers=auth_headers)
    assert res.status_code == 200, res.text

    # 画像应出现 浓香下饭
    data = client.get("/api/users/me/taste-memory", headers=auth_headers).json()["data"]
    assert "浓香下饭" in data["preferred_styles"]
    assert data["total_signals"] == 1


def test_favorite_qa_records_signal(client, auth_headers, monkeypatch):
    from app.routers import qa as qa_router

    async def _fake_qa(question, history=None, enable_search=True):
        return {
            "result": {
                "core_secret": "小火慢炖",
                "ingredients": ["五花肉"],
                "steps": ["焯水"],
                "avoid_pitfalls": ["别加冷水"],
                "sources": None,
            },
            "error": None,
        }

    async def _fake_router(question, history=None):
        return {"intent": "general", "dish_name": "", "needs_full_recipe": False, "confidence": "high"}

    monkeypatch.setattr(qa_router.qa_agent, "run_qa", _fake_qa)
    monkeypatch.setattr(qa_router.qa_agent, "route_intent", _fake_router)
    res = client.post("/api/qa/ask", json={"question": "红烧肉怎么不腻"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    qid = res.json()["data"]["id"]

    client.post("/api/favorites", json={"content_type": "qa", "content_id": qid}, headers=auth_headers)

    data = client.get("/api/users/me/taste-memory", headers=auth_headers).json()["data"]
    assert data["total_signals"] == 1
    assert "红烧肉" in "".join(data["recent_qa_keywords"])


def test_like_post_records_topic_signal(client, auth_headers, make_headers):
    # 造一篇带话题的作品
    author = make_headers("openid-author")
    client.post(
        "/api/posts",
        json={"content": "减脂餐打卡", "topic": "减脂餐"},
        headers=author,
    )
    posts = client.get("/api/posts", headers=auth_headers).json()["data"]["items"]
    pid = posts[0]["id"]

    client.post(f"/api/posts/{pid}/like", headers=auth_headers)
    data = client.get("/api/users/me/taste-memory", headers=auth_headers).json()["data"]
    assert "#减脂餐" in data["preferred_topics"]
    assert data["total_signals"] == 1


# ---------- 注入：口味记忆进入生成 Prompt ----------
def test_generate_injects_taste_memory(client, auth_headers, monkeypatch):
    from app.routers import recipes as recipes_router

    captured = {}

    async def _fake_recipe(ingredients, prefs):
        captured["prefs"] = prefs
        return {
            "result": {
                "recipes": [
                    {
                        "name": "测试菜",
                        "match_score": 80,
                        "time_minutes": 20,
                        "difficulty": "简单",
                        "style": "清爽快手",
                        "missing_seasonings": [],
                        "steps": [{"title": "切", "detail": "切好"}],
                        "tips": [],
                    }
                ]
            },
            "error": None,
        }

    monkeypatch.setattr(recipes_router.recipe_agent, "run_recipe", _fake_recipe)

    # 先造 3 条收藏信号（满足注入阈值）
    async def _seed():
        from app.models.taste_signal import TasteSignal
        from tests.conftest import TestSessionLocal
        from sqlalchemy import select
        from app.models.user import User

        async with TestSessionLocal() as s:
            u = (await s.execute(select(User))).scalars().first()
            for v in ["浓香下饭", "浓香下饭", "香辣过瘾"]:
                s.add(TasteSignal(user_id=u.id, signal_type="favorite_recipe", value=v))
            await s.commit()

    import asyncio

    asyncio.run(_seed())

    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert "taste_memory" in captured["prefs"]
    assert "浓香下饭" in captured["prefs"]["taste_memory"]


def test_generate_skips_injection_when_not_enough(client, auth_headers, monkeypatch):
    from app.routers import recipes as recipes_router

    captured = {}

    async def _fake_recipe(ingredients, prefs):
        captured["prefs"] = prefs
        return {
            "result": {
                "recipes": [
                    {
                        "name": "测试菜",
                        "match_score": 80,
                        "time_minutes": 20,
                        "difficulty": "简单",
                        "style": "清爽快手",
                        "missing_seasonings": [],
                        "steps": [{"title": "切", "detail": "切好"}],
                        "tips": [],
                    }
                ]
            },
            "error": None,
        }

    monkeypatch.setattr(recipes_router.recipe_agent, "run_recipe", _fake_recipe)
    res = client.post("/api/recipes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert "taste_memory" not in captured["prefs"]  # 0 信号不注入
