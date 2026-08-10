"""社区评论 TDD：发表 / 列表 / 楼主徽标 / 评论点赞(幂等) / 删除 / 级联。"""
import asyncio
import uuid

from sqlalchemy import func, select

from app.services import wechat as wechat_service
from app.services import storage as storage_service

from .conftest import TestSessionLocal

IMG = "data:image/png;base64,aGVsbG8="


def _mock_storage_and_check(monkeypatch, *, allow: bool = True):
    def _fake_save(images: list[str]) -> list[str]:
        return [f"/static/posts/{i}.png" for i in range(len(images))]

    async def _fake_check(content: str, openid: str, scene: int = 3) -> bool:
        return allow

    monkeypatch.setattr(storage_service, "save_images", _fake_save)
    monkeypatch.setattr(wechat_service, "check_text", _fake_check)


def _create_post(client, auth_headers, monkeypatch, **overrides):
    _mock_storage_and_check(monkeypatch)
    body = {"content": "跟做成功！皮脆肉嫩～", "images": [IMG], **overrides}
    res = client.post("/api/posts", json=body, headers=auth_headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _count_rows(model):
    async with TestSessionLocal() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


# ---------- 发表 ----------
def test_create_comment_basic(client, auth_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    res = client.post(
        f"/api/posts/{post['id']}/comments", json={"content": "好香！"}, headers=auth_headers
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["content"] == "好香！"
    assert data["like_count"] == 0
    assert data["is_liked"] is False
    assert data["author"]["nickname"] == "美食猎人"
    assert data["is_owner"] is True  # 评论者=作品作者 → 楼主

    # 作品评论计数 +1
    detail = client.get(f"/api/posts/{post['id']}", headers=auth_headers).json()["data"]
    assert detail["comment_count"] == 1


def test_create_comment_requires_auth(client, auth_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    assert client.post(f"/api/posts/{post['id']}/comments", json={"content": "x"}).status_code == 401


def test_create_comment_blank_content_422(client, auth_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    res = client.post(f"/api/posts/{post['id']}/comments", json={"content": ""}, headers=auth_headers)
    assert res.status_code == 422  # min_length=1 由 Pydantic 拦截


def test_create_comment_too_long_422(client, auth_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    res = client.post(
        f"/api/posts/{post['id']}/comments",
        json={"content": "长" * 201},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_create_comment_post_404(client, auth_headers):
    res = client.post(
        f"/api/posts/{uuid.uuid4()}/comments", json={"content": "x"}, headers=auth_headers
    )
    assert res.status_code == 404


def test_create_comment_security_blocks(client, auth_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    _mock_storage_and_check(monkeypatch, allow=False)
    res = client.post(
        f"/api/posts/{post['id']}/comments", json={"content": "违规内容"}, headers=auth_headers
    )
    assert res.status_code == 400


# ---------- 列表 ----------
def test_list_comments_chronological_and_owner(client, auth_headers, make_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    other = make_headers("openid-other")
    client.post(f"/api/posts/{post['id']}/comments", json={"content": "第一条"}, headers=other)
    client.post(f"/api/posts/{post['id']}/comments", json={"content": "第二条"}, headers=auth_headers)

    res = client.get(f"/api/posts/{post['id']}/comments", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] == 2
    assert [i["content"] for i in data["items"]] == ["第一条", "第二条"]  # 时间正序
    assert data["items"][0]["is_owner"] is False  # 别人评论非楼主
    assert data["items"][1]["is_owner"] is True   # 楼主评论带徽标


def test_list_comments_pagination(client, auth_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    for i in range(3):
        client.post(f"/api/posts/{post['id']}/comments", json={"content": f"评论{i}"}, headers=auth_headers)
    res = client.get(f"/api/posts/{post['id']}/comments?page=1&size=2", headers=auth_headers)
    data = res.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["has_more"] is True
    assert [i["content"] for i in data["items"]] == ["评论0", "评论1"]
    res2 = client.get(f"/api/posts/{post['id']}/comments?page=2&size=2", headers=auth_headers)
    assert res2.json()["data"]["items"][0]["content"] == "评论2"
    assert res2.json()["data"]["has_more"] is False


def test_list_comments_requires_auth(client, auth_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    assert client.get(f"/api/posts/{post['id']}/comments").status_code == 401


def test_list_comments_post_404(client, auth_headers):
    res = client.get(f"/api/posts/{uuid.uuid4()}/comments", headers=auth_headers)
    assert res.status_code == 404


# ---------- 评论点赞 ----------
def test_like_comment_idempotent(client, auth_headers, make_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    other = make_headers("openid-other")
    c = client.post(f"/api/posts/{post['id']}/comments", json={"content": "好"}, headers=other).json()["data"]
    url = f"/api/comments/{c['id']}/like"
    r1 = client.post(url, headers=auth_headers).json()["data"]
    assert r1 == {"liked": True, "like_count": 1}
    r2 = client.post(url, headers=auth_headers).json()["data"]  # 幂等
    assert r2 == {"liked": True, "like_count": 1}

    # 列表里我的点赞态
    res = client.get(f"/api/posts/{post['id']}/comments", headers=auth_headers).json()["data"]
    assert res["items"][0]["is_liked"] is True
    assert res["items"][0]["like_count"] == 1


def test_unlike_comment_idempotent(client, auth_headers, make_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    other = make_headers("openid-other")
    c = client.post(f"/api/posts/{post['id']}/comments", json={"content": "赞"}, headers=other).json()["data"]
    url = f"/api/comments/{c['id']}/like"
    client.post(url, headers=auth_headers)
    r1 = client.delete(url, headers=auth_headers).json()["data"]
    assert r1 == {"liked": False, "like_count": 0}
    r2 = client.delete(url, headers=auth_headers).json()["data"]  # 幂等
    assert r2 == {"liked": False, "like_count": 0}


def test_comment_like_404(client, auth_headers):
    assert client.post(f"/api/comments/{uuid.uuid4()}/like", headers=auth_headers).status_code == 404


# ---------- 删除评论 ----------
def test_delete_own_comment_decrements_count(client, auth_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    c = client.post(f"/api/posts/{post['id']}/comments", json={"content": "自己"}, headers=auth_headers).json()["data"]
    res = client.delete(f"/api/comments/{c['id']}", headers=auth_headers)
    assert res.status_code == 200
    detail = client.get(f"/api/posts/{post['id']}", headers=auth_headers).json()["data"]
    assert detail["comment_count"] == 0


def test_delete_others_comment_forbidden(client, auth_headers, make_headers, monkeypatch):
    post = _create_post(client, auth_headers, monkeypatch)
    other = make_headers("openid-other")
    c = client.post(f"/api/posts/{post['id']}/comments", json={"content": "别人"}, headers=other).json()["data"]
    res = client.delete(f"/api/comments/{c['id']}", headers=auth_headers)
    assert res.status_code == 403


def test_delete_comment_404(client, auth_headers):
    assert client.delete(f"/api/comments/{uuid.uuid4()}", headers=auth_headers).status_code == 404


# ---------- 级联 ----------
def test_delete_account_cascades_comments_and_likes(client, auth_headers, make_headers, monkeypatch):
    from app.models.comment import Comment
    from app.models.comment_like import CommentLike

    post = _create_post(client, auth_headers, monkeypatch)
    c = client.post(f"/api/posts/{post['id']}/comments", json={"content": "好"}, headers=auth_headers).json()["data"]
    client.post(f"/api/comments/{c['id']}/like", headers=auth_headers)

    assert asyncio.run(_count_rows(Comment)) == 1
    assert asyncio.run(_count_rows(CommentLike)) == 1

    res = client.delete("/api/users/me", headers=auth_headers)
    assert res.status_code == 200

    assert asyncio.run(_count_rows(Comment)) == 0
    assert asyncio.run(_count_rows(CommentLike)) == 0
