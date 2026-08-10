"""社区作品 TDD：发布 / 广场分页 / 详情 / 点赞 / 我的作品 / 分享卡 / 级联删除。"""
import asyncio
import uuid

from sqlalchemy import func, select

from app.services import storage as storage_service
from app.services import wechat as wechat_service
from app.services.storage import StorageError

from .conftest import TestSessionLocal

IMG = "data:image/png;base64,aGVsbG8="  # 合法 base64（存储已 mock，不做真实解码）


async def _count_rows(model):
    async with TestSessionLocal() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


def _mock_storage_and_check(monkeypatch, *, allow: bool = True):
    """默认 mock 图片存储与内容安全，返回图片 URL 列表。

    注意：save_images 在路由内经 asyncio.to_thread 调用，故 mock 必须是同步函数。
    """

    def _fake_save(images: list[str]) -> list[str]:
        return [f"/static/posts/{i}.png" for i in range(len(images))]

    async def _fake_check(content: str, openid: str, scene: int = 3) -> bool:
        return allow

    monkeypatch.setattr(storage_service, "save_images", _fake_save)
    monkeypatch.setattr(wechat_service, "check_text", _fake_check)


def _create_post(client, auth_headers, monkeypatch, **overrides):
    _mock_storage_and_check(monkeypatch)
    body = {
        "content": "跟做成功！皮脆肉嫩～",
        "images": [IMG, IMG],
        **overrides,
    }
    res = client.post("/api/posts", json=body, headers=auth_headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _me_id(client, headers) -> str:
    return client.get("/api/users/me", headers=headers).json()["data"]["id"]


# ---------- 发布 ----------
def test_create_post_basic(client, auth_headers, monkeypatch):
    data = _create_post(client, auth_headers, monkeypatch)
    assert data["content"] == "跟做成功！皮脆肉嫩～"
    assert data["images"] == ["/static/posts/0.png", "/static/posts/1.png"]
    assert data["like_count"] == 0
    assert data["is_liked"] is False
    assert data["author"]["nickname"] == "美食猎人"  # 未设置昵称
    assert data["topic"] is None


def test_create_post_requires_auth(client):
    res = client.post("/api/posts", json={"content": "hello", "images": []})
    assert res.status_code == 401


def test_create_post_requires_content_or_image(client, auth_headers, monkeypatch):
    _mock_storage_and_check(monkeypatch)
    res = client.post("/api/posts", json={"content": "  ", "images": []}, headers=auth_headers)
    assert res.status_code == 400
    assert res.json()["code"] == 400


def test_create_post_content_only(client, auth_headers, monkeypatch):
    _mock_storage_and_check(monkeypatch)
    res = client.post(
        "/api/posts", json={"content": "纯文字心得", "images": []}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["data"]["images"] == []


def test_create_post_invalid_image_400(client, auth_headers, monkeypatch):
    _mock_storage_and_check(monkeypatch)  # 先 mock check_text，避免真实网络调用

    def _boom(images: list[str]):
        raise StorageError("仅支持 jpeg/png/webp 图片")

    monkeypatch.setattr(storage_service, "save_images", _boom)
    res = client.post(
        "/api/posts", json={"content": "x", "images": ["not-a-data-url"]}, headers=auth_headers
    )
    assert res.status_code == 400
    assert "仅支持" in res.json()["message"]


def test_create_post_too_many_images_422(client, auth_headers, monkeypatch):
    _mock_storage_and_check(monkeypatch)
    res = client.post(
        "/api/posts", json={"content": "x", "images": [IMG] * 10}, headers=auth_headers
    )
    assert res.status_code == 422


def test_create_post_topic_normalized(client, auth_headers, monkeypatch):
    data = _create_post(client, auth_headers, monkeypatch, topic="今日晚餐")
    assert data["topic"] == "#今日晚餐"


def test_create_post_security_blocks(client, auth_headers, monkeypatch):
    _mock_storage_and_check(monkeypatch, allow=False)
    res = client.post(
        "/api/posts", json={"content": "违规内容", "images": []}, headers=auth_headers
    )
    assert res.status_code == 400


# ---------- 关联菜谱 ----------
def _create_recipe(client, auth_headers, monkeypatch):
    from app.services.agents import recipe_agent

    valid_set = {
        "recipes": [
            {
                "name": "番茄炒蛋", "match_score": 92, "time_minutes": 20, "difficulty": "简单",
                "style": "浓香下饭",
                "missing_seasonings": [], "steps": [{"title": "打蛋", "detail": "打散"}], "tips": [],
            },
            {
                "name": "番茄鸡蛋面", "match_score": 98, "time_minutes": 15, "difficulty": "简单",
                "style": "清爽快手",
                "missing_seasonings": ["葱末"], "steps": [{"title": "煮面", "detail": "水开下面"}],
                "tips": ["西红柿加盐炒出沙，汤底才浓郁"],
            },
            {
                "name": "葱油拌面", "match_score": 85, "time_minutes": 10, "difficulty": "简单",
                "style": "清爽快手",
                "missing_seasonings": [], "steps": [{"title": "煮面", "detail": "水开下面"}], "tips": [],
            },
        ]
    }

    async def _fake(**kwargs):
        return valid_set

    monkeypatch.setattr(recipe_agent, "ainvoke_json", _fake)
    res = client.post(
        "/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=auth_headers
    )
    return res.json()["data"][0]


def test_create_post_with_recipe_link(client, auth_headers, monkeypatch):
    rec = _create_recipe(client, auth_headers, monkeypatch)
    data = _create_post(client, auth_headers, monkeypatch, recipe_id=rec["id"])
    assert data["recipe_id"] == rec["id"]


def test_create_post_recipe_not_owned_404(client, auth_headers, make_headers, monkeypatch):
    rec = _create_recipe(client, auth_headers, monkeypatch)  # openid-test 的菜谱
    other = make_headers("openid-other")
    _mock_storage_and_check(monkeypatch)
    # 引用他人菜谱 → 404
    res = client.post(
        "/api/posts",
        json={"content": "x", "images": [], "recipe_id": rec["id"]},
        headers=other,
    )
    assert res.status_code == 404


# ---------- 广场 ----------
def test_list_posts_pagination_and_author(client, auth_headers, make_headers, monkeypatch):
    other = make_headers("openid-other")
    for i in range(3):
        _create_post(client, auth_headers, monkeypatch, content=f"我的作品 {i}")
    _create_post(client, other, monkeypatch, content="别人的作品")

    res = client.get("/api/posts?page=1&size=2", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] == 4
    assert len(data["items"]) == 2
    assert data["has_more"] is True
    # 倒序：最新（别人的作品）在前
    assert data["items"][0]["content"] == "别人的作品"
    assert data["items"][0]["author"]["nickname"] == "美食猎人"
    assert data["items"][1]["content"] == "我的作品 2"
    # 我点赞了某条后再列表应显示 is_liked
    first_id = data["items"][0]["id"]
    client.post(f"/api/posts/{first_id}/like", headers=auth_headers)
    res2 = client.get("/api/posts?page=1&size=2", headers=auth_headers)
    assert res2.json()["data"]["items"][0]["is_liked"] is True


def test_list_posts_topic_filter(client, auth_headers, monkeypatch):
    _create_post(client, auth_headers, monkeypatch, content="晚餐", topic="#今日晚餐")
    _create_post(client, auth_headers, monkeypatch, content="减脂", topic="#减脂餐")
    res = client.get("/api/posts?topic=今日晚餐", headers=auth_headers)
    data = res.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["content"] == "晚餐"
    assert data["items"][0]["topic"] == "#今日晚餐"


def test_list_posts_requires_auth(client):
    assert client.get("/api/posts").status_code == 401


# ---------- 详情 ----------
def test_get_post_detail(client, auth_headers, monkeypatch):
    data = _create_post(client, auth_headers, monkeypatch)
    res = client.get(f"/api/posts/{data['id']}", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["id"] == data["id"]
    assert body["is_liked"] is False


def test_get_post_404(client, auth_headers):
    res = client.get(
        f"/api/posts/{uuid.uuid4()}", headers=auth_headers
    )
    assert res.status_code == 404


# ---------- 点赞 ----------
def test_like_post_idempotent(client, auth_headers, monkeypatch):
    data = _create_post(client, auth_headers, monkeypatch)
    url = f"/api/posts/{data['id']}/like"
    r1 = client.post(url, headers=auth_headers).json()["data"]
    assert r1 == {"liked": True, "like_count": 1}
    r2 = client.post(url, headers=auth_headers).json()["data"]  # 幂等
    assert r2 == {"liked": True, "like_count": 1}


def test_unlike_post(client, auth_headers, make_headers, monkeypatch):
    data = _create_post(client, auth_headers, monkeypatch)
    other = make_headers("openid-other")
    client.post(f"/api/posts/{data['id']}/like", headers=other)
    client.post(f"/api/posts/{data['id']}/like", headers=other)
    # 点赞后详情 like_count 应为 1（幂等）
    detail = client.get(f"/api/posts/{data['id']}", headers=auth_headers).json()["data"]
    assert detail["like_count"] == 1
    res = client.delete(f"/api/posts/{data['id']}/like", headers=other).json()["data"]
    assert res == {"liked": False, "like_count": 0}
    # 幂等取消
    res2 = client.delete(f"/api/posts/{data['id']}/like", headers=other).json()["data"]
    assert res2 == {"liked": False, "like_count": 0}


def test_like_requires_auth(client, monkeypatch, auth_headers):
    data = _create_post(client, auth_headers, monkeypatch)
    assert client.post(f"/api/posts/{data['id']}/like").status_code == 401
    assert client.delete(f"/api/posts/{data['id']}/like").status_code == 401


# ---------- 我的作品 ----------
def test_my_posts(client, auth_headers, make_headers, monkeypatch):
    _create_post(client, auth_headers, monkeypatch, content="我的A")
    _create_post(client, auth_headers, monkeypatch, content="我的B")
    _create_post(client, make_headers("openid-other"), monkeypatch, content="别人")
    res = client.get("/api/posts/mine", headers=auth_headers)
    items = res.json()["data"]
    assert len(items) == 2
    assert {i["content"] for i in items} == {"我的A", "我的B"}


# ---------- 分享卡 ----------
def test_post_share_card(client, auth_headers, monkeypatch):
    data = _create_post(client, auth_headers, monkeypatch, content="分享卡片测试")

    captured = {}

    async def _fake_qr(scene: str, page: str, width: int = 430):
        captured["scene"] = scene
        captured["page"] = page
        return b"\x89PNG-fake-png-bytes"

    monkeypatch.setattr(wechat_service, "get_unlimited_qrcode", _fake_qr)

    res = client.get(f"/api/posts/{data['id']}/share-card", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["id"] == data["id"]
    assert body["content"] == "分享卡片测试"
    assert body["qrcode_base64"].startswith("data:image/png;base64,")
    assert captured["scene"] == data["id"].replace("-", "")
    assert captured["page"] == "pages/post-detail/index"


def test_post_share_card_qrcode_failure_degrades(client, auth_headers, monkeypatch):
    data = _create_post(client, auth_headers, monkeypatch)

    async def _boom(scene: str, page: str, width: int = 430):
        raise wechat_service.WeChatError("mock qr fail")

    monkeypatch.setattr(wechat_service, "get_unlimited_qrcode", _boom)

    res = client.get(f"/api/posts/{data['id']}/share-card", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["qrcode_base64"] is None


def test_post_share_card_404(client, auth_headers):
    res = client.get(f"/api/posts/{uuid.uuid4()}/share-card", headers=auth_headers)
    assert res.status_code == 404


# ---------- 级联删除 ----------
def test_delete_account_cascades_posts_and_likes(client, auth_headers, make_headers, monkeypatch):
    from app.models.like import Like
    from app.models.post import Post

    data = _create_post(client, auth_headers, monkeypatch)
    other = make_headers("openid-other")
    client.post(f"/api/posts/{data['id']}/like", headers=other)

    assert asyncio.run(_count_rows(Post)) == 1
    assert asyncio.run(_count_rows(Like)) == 1

    res = client.delete("/api/users/me", headers=auth_headers)
    assert res.status_code == 200

    assert asyncio.run(_count_rows(Post)) == 0
    assert asyncio.run(_count_rows(Like)) == 0  # 作者删除 → 作品级联 → 点赞级联


# ---------- 话题聚合（话题广场） ----------
def test_list_posts_topics_aggregation(client, auth_headers, monkeypatch):
    _create_post(client, auth_headers, monkeypatch, content="晚餐A", topic="今日晚餐")
    _create_post(client, auth_headers, monkeypatch, content="晚餐B", topic="今日晚餐")
    _create_post(client, auth_headers, monkeypatch, content="减脂", topic="减脂餐")
    res = client.get("/api/posts/topics", headers=auth_headers)
    assert res.status_code == 200
    items = res.json()["data"]
    counts = {t["topic"]: t["count"] for t in items}
    assert counts == {"#今日晚餐": 2, "#减脂餐": 1}
    # 按数量倒序
    assert items[0]["topic"] == "#今日晚餐"


def test_list_posts_topics_aggregation_excludes_none(client, auth_headers, monkeypatch):
    _create_post(client, auth_headers, monkeypatch, content="无话题")
    res = client.get("/api/posts/topics", headers=auth_headers)
    assert res.json()["data"] == []


def test_list_posts_topics_aggregation_requires_auth(client):
    assert client.get("/api/posts/topics").status_code == 401


# ---------- 按作者筛选（作者主页） ----------
def test_list_posts_filter_by_user(client, auth_headers, make_headers, monkeypatch):
    other = make_headers("openid-other")
    other_id = _me_id(client, other)
    _create_post(client, auth_headers, monkeypatch, content="我的作品")
    _create_post(client, other, monkeypatch, content="TA 的作品 1")
    _create_post(client, other, monkeypatch, content="TA 的作品 2")
    res = client.get(f"/api/posts?user_id={other_id}", headers=auth_headers)
    data = res.json()["data"]
    assert data["total"] == 2
    assert {i["content"] for i in data["items"]} == {"TA 的作品 1", "TA 的作品 2"}
