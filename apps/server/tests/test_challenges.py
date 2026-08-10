"""烹饪挑战 TDD：创建/列表/加入/进度更新/排行榜（原型 05 屏4）。"""
import uuid


def _create_challenge(client, auth_headers, **over):
    body = {"title": "一周只花 50 元", "budget": 50, "description": "用 50 元预算做完一周三餐"}
    body.update(over)
    return client.post("/api/challenges", json=body, headers=auth_headers)


# ---------- 创建 ----------
def test_create_challenge(client, auth_headers):
    """创建挑战成功，返回 id + 默认状态/参与数。"""
    res = _create_challenge(client, auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["title"] == "一周只花 50 元"
    assert data["status"] == "active"
    assert data["participant_count"] == 0
    assert "id" in data


def test_create_challenge_requires_title(client, auth_headers):
    """缺标题 → 422。"""
    res = client.post("/api/challenges", json={"budget": 50}, headers=auth_headers)
    assert res.status_code == 422


def test_create_challenge_requires_auth(client):
    """未登录 → 401。"""
    res = client.post("/api/challenges", json={"title": "x"})
    assert res.status_code == 401


# ---------- 列表 ----------
def test_list_challenges(client, auth_headers):
    """列表返回进行中的挑战（含参与人数）。"""
    _create_challenge(client, auth_headers)
    res = client.get("/api/challenges", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "一周只花 50 元"


def test_list_challenges_requires_auth(client):
    assert client.get("/api/challenges").status_code == 401


# ---------- 加入 ----------
def test_join_challenge(client, auth_headers, make_headers):
    """加入挑战：参与者计数 +1；重复加入幂等。"""
    cid = _create_challenge(client, auth_headers).json()["data"]["id"]

    other = make_headers("openid-other")
    r1 = client.post(f"/api/challenges/{cid}/join", headers=other)
    assert r1.status_code == 200
    assert r1.json()["data"]["participant_count"] == 1
    assert r1.json()["data"]["joined"] is True

    # 重复加入：计数不变
    r2 = client.post(f"/api/challenges/{cid}/join", headers=other)
    assert r2.json()["data"]["participant_count"] == 1


def test_join_self_challenge_counts(client, auth_headers):
    """创建者加入自己也计入参与（不影响计数正确性）。"""
    cid = _create_challenge(client, auth_headers).json()["data"]["id"]
    res = client.post(f"/api/challenges/{cid}/join", headers=auth_headers)
    assert res.json()["data"]["participant_count"] == 1


def test_join_not_found_404(client, auth_headers):
    """挑战不存在 → 404。"""
    res = client.post(
        f"/api/challenges/{uuid.uuid4()}/join", headers=auth_headers
    )
    assert res.status_code == 404


# ---------- 进度更新 ----------
def test_update_progress(client, auth_headers):
    """更新我的花费与餐数。"""
    cid = _create_challenge(client, auth_headers).json()["data"]["id"]
    client.post(f"/api/challenges/{cid}/join", headers=auth_headers)

    res = client.put(
        f"/api/challenges/{cid}/progress",
        json={"spend": 38, "meal_count": 3},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["spend"] == 38
    assert data["meal_count"] == 3


def test_update_progress_not_joined_404(client, auth_headers):
    """未加入就更新进度 → 404。"""
    cid = _create_challenge(client, auth_headers).json()["data"]["id"]
    res = client.put(
        f"/api/challenges/{cid}/progress", json={"spend": 10}, headers=auth_headers
    )
    assert res.status_code == 404


def test_update_progress_negative_422(client, auth_headers):
    """负花费 → 422。"""
    cid = _create_challenge(client, auth_headers).json()["data"]["id"]
    client.post(f"/api/challenges/{cid}/join", headers=auth_headers)
    res = client.put(
        f"/api/challenges/{cid}/progress", json={"spend": -5}, headers=auth_headers
    )
    assert res.status_code == 422


# ---------- 排行榜 ----------
def test_leaderboard_sorted_by_savings(client, auth_headers, make_headers):
    """排行榜：按预算利用率（省得多/花得少排前），含我是否在榜。"""
    cid = _create_challenge(client, auth_headers, budget=100).json()["data"]["id"]

    u1 = make_headers("openid-u1")
    u2 = make_headers("openid-u2")
    client.post(f"/api/challenges/{cid}/join", headers=u1)
    client.post(f"/api/challenges/{cid}/join", headers=u2)

    # u1 花 30，u2 花 70 → u1（省得多）应排 u2 前面
    client.put(f"/api/challenges/{cid}/progress", json={"spend": 30, "meal_count": 5}, headers=u1)
    client.put(f"/api/challenges/{cid}/progress", json={"spend": 70, "meal_count": 5}, headers=u2)

    res = client.get(f"/api/challenges/{cid}/leaderboard", headers=auth_headers)
    assert res.status_code == 200
    items = res.json()["data"]["items"]
    assert len(items) == 2
    assert items[0]["spend"] == 30
    assert items[1]["spend"] == 70


def test_leaderboard_empty(client, auth_headers):
    """无参与者时排行榜为空。"""
    cid = _create_challenge(client, auth_headers).json()["data"]["id"]
    res = client.get(f"/api/challenges/{cid}/leaderboard", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["items"] == []


def test_leaderboard_requires_auth(client):
    assert client.get(
        f"/api/challenges/{uuid.uuid4()}/leaderboard"
    ).status_code == 401
