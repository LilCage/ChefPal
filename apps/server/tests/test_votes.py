"""家庭口味投票 TDD：生成3菜投票 / 投票/改票 / 结果统计 / 分享卡片。

原型 05 屏2：AI 结合冰箱食材生成 3 道菜 → 分享家庭群 → 投票决定今晚吃什么。
"""
from app.routers import votes as votes_router
from app.services.agents import vote_agent

VALID_OPTIONS = {"options": ["番茄炖牛腩", "香煎三文鱼", "香菇滑鸡"]}


def _mock_vote_agent(monkeypatch, result=VALID_OPTIONS):
    async def _fake(ingredients: list[str], prefs: dict | None = None) -> dict:
        return {"result": result, "error": None}

    monkeypatch.setattr(vote_agent, "run_vote", _fake)
    return _fake


# ---------- 生成投票 ----------
def test_vote_generate_success(client, auth_headers, monkeypatch):
    """输入食材 → 生成 3 道菜选项投票。"""
    _mock_vote_agent(monkeypatch)
    res = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿", "鸡蛋", "面条"]}, headers=auth_headers
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert "id" in data
    assert len(data["options"]) == 3
    assert data["options"][0]["name"] == "番茄炖牛腩"
    assert data["status"] == "active"


def test_vote_generate_injects_prefs(client, auth_headers, monkeypatch):
    """偏好注入：读取用户口味。"""
    captured = {}

    async def _fake(ingredients: list[str], prefs: dict | None = None) -> dict:
        captured["prefs"] = prefs
        return {"result": VALID_OPTIONS, "error": None}

    monkeypatch.setattr(vote_agent, "run_vote", _fake)
    client.put(
        "/api/users/me/preferences",
        json={"allergies": ["花生"], "spiciness": 2},
        headers=auth_headers,
    )
    res = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert captured["prefs"]["spiciness"] == 2


def test_vote_generate_agent_failure_502(client, auth_headers, monkeypatch):
    """生成失败 → 502。"""

    async def _fake(ingredients: list[str], prefs: dict | None = None) -> dict:
        return {"result": None, "error": "mock 生成失败"}

    monkeypatch.setattr(vote_agent, "run_vote", _fake)
    res = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers
    )
    assert res.status_code == 502


def test_vote_generate_requires_ingredients(client, auth_headers):
    """空食材 → 422。"""
    res = client.post("/api/votes/generate", json={"ingredients": []}, headers=auth_headers)
    assert res.status_code == 422


# ---------- 投票 / 改票 ----------
def test_vote_cast_and_result(client, auth_headers, monkeypatch):
    """投票后结果含票数；同人重复投票为改票（幂等不叠加）。"""
    _mock_vote_agent(monkeypatch)
    vid = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers
    ).json()["data"]["id"]

    # 第一次投 A
    r1 = client.post(f"/api/votes/{vid}/vote", json={"option_index": 0}, headers=auth_headers)
    assert r1.status_code == 200
    assert r1.json()["data"]["options"][0]["count"] == 1

    # 改投 B：A 减回 0，B 变 1
    r2 = client.post(f"/api/votes/{vid}/vote", json={"option_index": 1}, headers=auth_headers)
    assert r2.status_code == 200
    opts = r2.json()["data"]["options"]
    assert opts[0]["count"] == 0
    assert opts[1]["count"] == 1


def test_vote_get_detail(client, auth_headers, monkeypatch):
    """GET 投票详情：选项 + 我已投项 + 总票数。"""
    _mock_vote_agent(monkeypatch)
    vid = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers
    ).json()["data"]["id"]
    client.post(f"/api/votes/{vid}/vote", json={"option_index": 2}, headers=auth_headers)

    res = client.get(f"/api/votes/{vid}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["my_choice"] == 2
    assert data["total_count"] == 1


def test_vote_option_index_out_of_range(client, auth_headers, monkeypatch):
    """非法选项索引 → 400。"""
    _mock_vote_agent(monkeypatch)
    vid = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers
    ).json()["data"]["id"]
    res = client.post(f"/api/votes/{vid}/vote", json={"option_index": 5}, headers=auth_headers)
    assert res.status_code == 400


def test_vote_not_found(client, auth_headers):
    """投票不存在 → 404。"""
    import uuid
    res = client.post(
        f"/api/votes/{uuid.uuid4()}/vote", json={"option_index": 0}, headers=auth_headers
    )
    assert res.status_code == 404


# ---------- 多用户统计 ----------
def test_vote_multiple_users_counts(client, auth_headers, make_headers, monkeypatch):
    """多用户投票：票数正确聚合，统计不看重复。"""
    _mock_vote_agent(monkeypatch)
    vid = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers
    ).json()["data"]["id"]

    other = make_headers("openid-other")
    client.post(f"/api/votes/{vid}/vote", json={"option_index": 0}, headers=auth_headers)
    client.post(f"/api/votes/{vid}/vote", json={"option_index": 0}, headers=other)
    client.post(f"/api/votes/{vid}/vote", json={"option_index": 1}, headers=other)  # 改票

    res = client.get(f"/api/votes/{vid}", headers=auth_headers)
    opts = res.json()["data"]["options"]
    assert opts[0]["count"] == 1  # 仅创建者投了 A
    assert opts[1]["count"] == 1  # other 改投 B
    assert res.json()["data"]["total_count"] == 2


# ---------- 分享卡片 ----------
def test_vote_share_card(client, auth_headers, monkeypatch):
    """分享卡片：含标题/选项数/小程序码（mock 微信）。"""
    from app.services import wechat as wechat_service

    _mock_vote_agent(monkeypatch)

    async def _fake_qr(scene: str, page: str, width: int = 430):
        return b"\x89PNG-fake-png-bytes"

    monkeypatch.setattr(wechat_service, "get_unlimited_qrcode", _fake_qr)

    vid = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers
    ).json()["data"]["id"]

    res = client.get(f"/api/votes/{vid}/share-card", headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert "title" in data
    assert data["options_count"] == 3
    assert data["qrcode_base64"].startswith("data:image/png;base64,")


def test_vote_share_card_qrcode_failure_degrades(client, auth_headers, monkeypatch):
    """小程序码失败 → 卡片仍返回，qrcode_base64 为 null。"""
    from app.services import wechat as wechat_service
    from app.services.wechat import WeChatError

    _mock_vote_agent(monkeypatch)

    async def _boom(scene: str, page: str, width: int = 430):
        raise WeChatError("mock qr fail")

    monkeypatch.setattr(wechat_service, "get_unlimited_qrcode", _boom)

    vid = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers
    ).json()["data"]["id"]
    res = client.get(f"/api/votes/{vid}/share-card", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["qrcode_base64"] is None


def test_vote_requires_auth(client):
    """未登录 → 401。"""
    assert client.post("/api/votes/generate", json={"ingredients": ["x"]}).status_code == 401
    assert client.get("/api/votes/00000000-0000-0000-0000-000000000000").status_code == 401
    assert (
        client.post(
            "/api/votes/00000000-0000-0000-0000-000000000000/vote", json={"option_index": 0}
        ).status_code
        == 401
    )


def test_vote_generate_rate_limit(client, auth_headers, monkeypatch):
    """生成投票超限 → 429。"""
    from app.core.response import AppError

    _mock_vote_agent(monkeypatch)

    async def _over(db, user_id, limit):
        raise AppError("今日调用已达上限，明日再来吧", code=429, status_code=429)

    monkeypatch.setattr(votes_router, "ensure_within_limit", _over)
    res = client.post(
        "/api/votes/generate", json={"ingredients": ["西红柿"]}, headers=auth_headers
    )
    assert res.status_code == 429
    assert "上限" in res.json()["message"]
