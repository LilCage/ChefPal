"""语音烹饪助手 TDD：基于菜谱上下文回答 / 菜谱归属校验 / 空问题 / 风控记账。"""
import copy

from app.services import cook_assistant as cook_service

VALID_ANSWER = {"answer": "转中火，油温六成时下锅，翻炒约 2 分钟。", "current_step": 2}


# ---------- 服务 ----------
def test_answer_ok(monkeypatch):
    import asyncio

    async def _fake(**kwargs):
        return copy.deepcopy(VALID_ANSWER)

    monkeypatch.setattr(cook_service, "ainvoke_json", _fake)
    out = asyncio.run(cook_service.answer_cooking_question("红烧肉", [{"title": "炒糖色", "detail": "小火"}], "下一步做什么"))
    assert out["answer"] == VALID_ANSWER["answer"]
    assert out["current_step"] == 2


def test_answer_blank_question_raises():
    import asyncio

    try:
        asyncio.run(cook_service.answer_cooking_question("红烧肉", [], "   "))
        assert False, "应为空问题抛错"
    except cook_service.CookAssistantError:
        pass


def test_answer_empty_output_raises(monkeypatch):
    import asyncio

    async def _fake(**kwargs):
        return {"answer": "  ", "current_step": 0}

    monkeypatch.setattr(cook_service, "ainvoke_json", _fake)
    try:
        asyncio.run(cook_service.answer_cooking_question("红烧肉", [], "下一步"))
        assert False, "应为空回答抛错"
    except cook_service.CookAssistantError:
        pass


def test_answer_llm_error_raises(monkeypatch):
    import asyncio

    from app.services.llm.client import LLMError

    async def _fake(**kwargs):
        raise LLMError("mock 调用失败")

    monkeypatch.setattr(cook_service, "ainvoke_json", _fake)
    try:
        asyncio.run(cook_service.answer_cooking_question("红烧肉", [], "下一步"))
        assert False, "应为 LLMError 抛错"
    except cook_service.CookAssistantError:
        pass


def test_steps_text_renders_numbered():
    text = cook_service._steps_text("红烧肉", [{"title": "焯水", "detail": "冷水下锅"}, {"title": "炒糖色", "detail": "小火"}])
    assert "菜名：红烧肉" in text
    assert "1. 焯水：冷水下锅" in text
    assert "2. 炒糖色：小火" in text


# ---------- 路由 ----------
def _seed_recipe(client, auth_headers, monkeypatch):
    from app.routers import recipes as recipes_router

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
                        "steps": [{"title": "焯水", "detail": "冷水下锅"}, {"title": "炒糖色", "detail": "小火"}],
                        "tips": ["糖色宁浅勿深"],
                    }
                ]
            },
            "error": None,
        }

    monkeypatch.setattr(recipes_router.recipe_agent, "run_recipe", _fake_recipe)
    res = client.post("/api/recipes/generate", json={"ingredients": ["五花肉"]}, headers=auth_headers)
    assert res.status_code == 200, res.text
    return res.json()["data"][0]["id"]


def _mock_answer(monkeypatch, result=VALID_ANSWER, error=None):
    async def _fake(title, steps, question):
        if error:
            raise error
        return copy.deepcopy(result)

    monkeypatch.setattr(cook_service, "answer_cooking_question", _fake)
    return _fake


def test_cook_query_success(client, auth_headers, monkeypatch):
    rid = _seed_recipe(client, auth_headers, monkeypatch)
    _mock_answer(monkeypatch)
    res = client.post("/api/cook-assistant/query", json={"recipe_id": rid, "question": "下一步做什么"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["answer"] == VALID_ANSWER["answer"]
    assert data["title"] == "红烧肉"
    assert data["current_step"] == 2


def test_cook_query_requires_auth(client):
    assert client.post("/api/cook-assistant/query", json={"recipe_id": "00000000-0000-0000-0000-000000000001", "question": "x"}).status_code == 401


def test_cook_query_recipe_not_found(client, auth_headers, monkeypatch):
    import uuid

    _mock_answer(monkeypatch)
    res = client.post(
        "/api/cook-assistant/query",
        json={"recipe_id": str(uuid.uuid4()), "question": "下一步"},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_cook_query_other_user_recipe_404(client, auth_headers, make_headers, monkeypatch):
    rid = _seed_recipe(client, auth_headers, monkeypatch)
    other = make_headers("openid-other")
    _mock_answer(monkeypatch)
    res = client.post(
        "/api/cook-assistant/query",
        json={"recipe_id": rid, "question": "下一步"},
        headers=other,
    )
    assert res.status_code == 404


def test_cook_query_service_error_502(client, auth_headers, monkeypatch):
    rid = _seed_recipe(client, auth_headers, monkeypatch)
    _mock_answer(monkeypatch, error=cook_service.CookAssistantError("mock 回答失败"))
    res = client.post(
        "/api/cook-assistant/query",
        json={"recipe_id": rid, "question": "下一步"},
        headers=auth_headers,
    )
    assert res.status_code == 502


def test_cook_query_blank_question_400(client, auth_headers, monkeypatch):
    rid = _seed_recipe(client, auth_headers, monkeypatch)
    res = client.post(
        "/api/cook-assistant/query",
        json={"recipe_id": rid, "question": "  "},
        headers=auth_headers,
    )
    assert res.status_code == 400  # 路由层空问题校验


def test_cook_query_rate_limit(client, auth_headers, monkeypatch):
    from app.routers import cook_assistant as cook_router
    from app.core.response import AppError

    rid = _seed_recipe(client, auth_headers, monkeypatch)
    _mock_answer(monkeypatch)

    async def _over(db, user_id, limit):
        raise AppError("今日调用已达上限，明日再来吧", code=429, status_code=429)

    monkeypatch.setattr(cook_router, "ensure_within_limit", _over)
    res = client.post(
        "/api/cook-assistant/query",
        json={"recipe_id": rid, "question": "下一步"},
        headers=auth_headers,
    )
    assert res.status_code == 429
    assert "上限" in res.json()["message"]
