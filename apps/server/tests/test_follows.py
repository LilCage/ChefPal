"""关注系统 TDD：关注/取关幂等、禁自关注、双向计数、粉丝/关注列表、关注动态 feed、个人主页 is_following、级联删除。"""
import asyncio
import uuid

from sqlalchemy import func, select

from app.models.follow import Follow
from app.models.post import Post
from app.services import storage as storage_service
from app.services import wechat as wechat_service

from .conftest import TestSessionLocal


async def _count_rows(model):
    async with TestSessionLocal() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


def _mock_storage_and_check(monkeypatch, *, allow: bool = True):
    def _fake_save(images: list[str]) -> list[str]:
        return [f"/static/posts/{i}.png" for i in range(len(images))]

    async def _fake_check(content: str, openid: str, scene: int = 3) -> bool:
        return allow

    monkeypatch.setattr(storage_service, "save_images", _fake_save)
    monkeypatch.setattr(wechat_service, "check_text", _fake_check)


def _create_post(client, headers, monkeypatch, content="跟做打卡", **overrides):
    _mock_storage_and_check(monkeypatch)
    res = client.post(
        "/api/posts", json={"content": content, "images": [], **overrides}, headers=headers
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _me_id(client, headers) -> str:
    return client.get("/api/users/me", headers=headers).json()["data"]["id"]


# ---------- 关注 / 取关 ----------
def test_follow_idempotent(client, auth_headers, make_headers):
    other = make_headers("openid-other")
    other_id = _me_id(client, other)
    res = client.post(f"/api/users/{other_id}/follow", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["following"] is True
    assert data["follower_count"] == 1  # 对方粉丝 +1
    assert data["following_count"] == 1  # 我的关注 +1
    # 幂等：重复关注不重复计数
    res2 = client.post(f"/api/users/{other_id}/follow", headers=auth_headers)
    assert res2.json()["data"] == data


def test_follow_self_400(client, auth_headers):
    me = _me_id(client, auth_headers)
    res = client.post(f"/api/users/{me}/follow", headers=auth_headers)
    assert res.status_code == 400
    assert "自己" in res.json()["message"]


def test_unfollow_idempotent(client, auth_headers, make_headers):
    other = make_headers("openid-other")
    other_id = _me_id(client, other)
    client.post(f"/api/users/{other_id}/follow", headers=auth_headers)
    res = client.delete(f"/api/users/{other_id}/follow", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"] == {"following": False, "follower_count": 0, "following_count": 0}
    # 幂等：重复取关不产生负数计数
    res2 = client.delete(f"/api/users/{other_id}/follow", headers=auth_headers)
    assert res2.json()["data"]["follower_count"] == 0


def test_follow_requires_auth(client, make_headers):
    other = make_headers("openid-other")
    other_id = _me_id(client, other)
    assert client.post(f"/api/users/{other_id}/follow").status_code == 401
    assert client.delete(f"/api/users/{other_id}/follow").status_code == 401


# ---------- 双向计数 / 个人主页 ----------
def test_follow_counts_mutual(client, auth_headers, make_headers):
    a = auth_headers
    b = make_headers("openid-b")
    a_id = _me_id(client, a)
    b_id = _me_id(client, b)
    # a 关注 b
    client.post(f"/api/users/{b_id}/follow", headers=a)
    prof_b = client.get(f"/api/users/{b_id}", headers=a).json()["data"]
    assert prof_b["follower_count"] == 1
    assert prof_b["following_count"] == 0
    assert prof_b["is_following"] is True
    # b 反关 a → 互关，a 主页 from b 视角
    client.post(f"/api/users/{a_id}/follow", headers=b)
    prof_a = client.get(f"/api/users/{a_id}", headers=b).json()["data"]
    assert prof_a["following_count"] == 1
    assert prof_a["follower_count"] == 1
    assert prof_a["is_following"] is True


def test_user_profile_not_following(client, auth_headers, make_headers):
    b = make_headers("openid-b")
    b_id = _me_id(client, b)
    prof = client.get(f"/api/users/{b_id}", headers=auth_headers).json()["data"]
    assert prof["is_following"] is False
    assert prof["post_count"] == 0


def test_user_profile_404(client, auth_headers):
    res = client.get(f"/api/users/{uuid.uuid4()}", headers=auth_headers)
    assert res.status_code == 404


def test_user_profile_requires_auth(client, make_headers):
    other = make_headers("openid-other")
    other_id = _me_id(client, other)
    assert client.get(f"/api/users/{other_id}").status_code == 401


# ---------- 粉丝 / 关注列表 ----------
def test_followers_and_following_lists(client, auth_headers, make_headers):
    a = auth_headers
    b = make_headers("openid-b")
    c = make_headers("openid-c")
    a_id = _me_id(client, a)
    b_id = _me_id(client, b)
    c_id = _me_id(client, c)
    # b、c 都关注 a
    client.post(f"/api/users/{a_id}/follow", headers=b)
    client.post(f"/api/users/{a_id}/follow", headers=c)
    followers = client.get(f"/api/users/{a_id}/followers", headers=a).json()["data"]
    assert followers["total"] == 2
    assert {f["id"] for f in followers["items"]} == {b_id, c_id}
    # b 的关注列表含 a
    following = client.get(f"/api/users/{b_id}/following", headers=b).json()["data"]
    assert following["total"] == 1
    assert following["items"][0]["id"] == a_id


def test_followers_list_mutual_flag(client, auth_headers, make_headers):
    a = auth_headers
    b = make_headers("openid-b")
    a_id = _me_id(client, a)
    b_id = _me_id(client, b)
    client.post(f"/api/users/{a_id}/follow", headers=b)  # b 关注 a
    client.post(f"/api/users/{b_id}/follow", headers=a)  # a 反关 b → 互关
    items = client.get(f"/api/users/{a_id}/followers", headers=a).json()["data"]["items"]
    assert any(f["id"] == b_id and f["is_following"] is True for f in items)


def test_followers_list_empty(client, auth_headers):
    me = _me_id(client, auth_headers)
    data = client.get(f"/api/users/{me}/followers", headers=auth_headers).json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


# ---------- 关注动态 feed ----------
def test_follow_feed_only_followed(client, auth_headers, make_headers, monkeypatch):
    a = auth_headers
    b = make_headers("openid-b")
    c = make_headers("openid-c")
    b_id = _me_id(client, b)
    client.post(f"/api/users/{b_id}/follow", headers=a)  # a 只关注 b
    _create_post(client, b, monkeypatch, content="B 的作品")
    _create_post(client, c, monkeypatch, content="C 的作品")
    feed = client.get("/api/follows/feed", headers=a).json()["data"]
    assert feed["total"] == 1
    assert feed["items"][0]["content"] == "B 的作品"
    assert feed["items"][0]["author"]["is_following"] is True


def test_follow_feed_empty(client, auth_headers):
    feed = client.get("/api/follows/feed", headers=auth_headers).json()["data"]
    assert feed["total"] == 0
    assert feed["items"] == []
    assert feed["has_more"] is False


def test_follow_feed_pagination(client, auth_headers, make_headers, monkeypatch):
    a = auth_headers
    b = make_headers("openid-b")
    b_id = _me_id(client, b)
    client.post(f"/api/users/{b_id}/follow", headers=a)
    for i in range(3):
        _create_post(client, b, monkeypatch, content=f"B {i}")
    feed = client.get("/api/follows/feed?page=1&size=2", headers=a).json()["data"]
    assert feed["total"] == 3
    assert len(feed["items"]) == 2
    assert feed["has_more"] is True
    assert feed["items"][0]["content"] == "B 2"  # 最新在前


def test_follow_feed_requires_auth(client):
    assert client.get("/api/follows/feed").status_code == 401


# ---------- 作品卡 is_following ----------
def test_post_list_is_following(client, auth_headers, make_headers, monkeypatch):
    a = auth_headers
    b = make_headers("openid-b")
    b_id = _me_id(client, b)
    _create_post(client, b, monkeypatch, content="B 的作品")
    client.post(f"/api/users/{b_id}/follow", headers=a)
    items = client.get("/api/posts", headers=a).json()["data"]["items"]
    assert items[0]["author"]["is_following"] is True


def test_post_detail_is_following(client, auth_headers, make_headers, monkeypatch):
    a = auth_headers
    b = make_headers("openid-b")
    b_id = _me_id(client, b)
    post = _create_post(client, b, monkeypatch, content="B 的作品")
    client.post(f"/api/users/{b_id}/follow", headers=a)
    detail = client.get(f"/api/posts/{post['id']}", headers=a).json()["data"]
    assert detail["author"]["is_following"] is True


# ---------- 级联删除 ----------
def test_delete_account_cascades_follows(client, auth_headers, make_headers):
    a = auth_headers
    b = make_headers("openid-b")
    a_id = _me_id(client, a)
    b_id = _me_id(client, b)
    client.post(f"/api/users/{b_id}/follow", headers=a)  # a→b
    client.post(f"/api/users/{a_id}/follow", headers=b)  # b→a
    assert asyncio.run(_count_rows(Follow)) == 2
    client.delete("/api/users/me", headers=a)
    assert asyncio.run(_count_rows(Follow)) == 0  # 两条关注关系全部级联清理


def test_delete_account_cascades_follow_target(client, auth_headers, make_headers):
    """被关注者注销后，关注方侧的关注关系也应级联清理。"""
    a = auth_headers
    b = make_headers("openid-b")
    b_id = _me_id(client, b)
    client.post(f"/api/users/{b_id}/follow", headers=a)  # a→b
    assert asyncio.run(_count_rows(Follow)) == 1
    client.delete("/api/users/me", headers=b)  # b 注销
    assert asyncio.run(_count_rows(Follow)) == 0
    assert asyncio.run(_count_rows(Post)) == 0
