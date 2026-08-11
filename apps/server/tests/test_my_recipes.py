"""个人菜谱创作 TDD：创建/列表/详情/编辑/删除 + 发布到社区。"""
import uuid

from sqlalchemy import select

from app.models.post import Post
from tests.conftest import TestSessionLocal

BASE = "/api/my-recipes"

VALID = {
    "title": "祖传红烧肉",
    "cover_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    "servings": 4,
    "ingredients": [{"name": "五花肉", "note": "500g，选带皮五花"}, {"name": "冰糖", "note": "适量"}],
    "prep_steps": [{"title": "切块", "detail": "五花肉切 3cm 见方块"}, {"title": "焯水", "detail": "冷水下锅煮 3 分钟去浮沫"}],
    "cook_steps": [{"title": "炒糖色", "detail": "小火炒至琥珀色"}, {"title": "慢炖", "detail": "转小火炖 40 分钟"}],
    "seasonings": [{"name": "生抽", "amount": "2勺"}, {"name": "食用油", "amount": "适量"}],
    "tips": ["糖色宁浅勿深"],
    "style": "浓香下饭",
    "time_minutes": 90,
    "difficulty": "较难",
}


def _create(client, headers, **overrides):
    body = {**VALID, **overrides}
    res = client.post(BASE, json=body, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


# ---------- 创建 ----------
def test_create_my_recipe(client, auth_headers):
    data = _create(client, auth_headers)
    assert data["title"] == "祖传红烧肉"
    assert len(data["ingredients"]) == 2
    assert data["ingredients"][0]["note"] == "500g，选带皮五花"
    assert data["servings"] == 4
    assert data["prep_steps"][0]["title"] == "切块"
    assert data["cook_steps"][0]["title"] == "炒糖色"
    assert data["seasonings"][0]["name"] == "生抽"
    assert data["style"] == "浓香下饭"
    assert data["time_minutes"] == 90
    assert data["cover_image"]  # data URL 已存储 → 返回可访问 URL


def test_create_my_recipe_requires_auth(client):
    assert client.post(BASE, json=VALID).status_code == 401


def test_create_my_recipe_blank_title_400(client, auth_headers):
    body = {**VALID, "title": "   "}
    res = client.post(BASE, json=body, headers=auth_headers)
    assert res.status_code == 400


def test_create_my_recipe_cover_url_passthrough(client, auth_headers):
    data = _create(client, auth_headers, cover_image="https://example.com/cover.png")
    assert data["cover_image"] == "https://example.com/cover.png"


def test_create_my_recipe_invalid_data_url_400(client, auth_headers, monkeypatch):
    from app.services import storage as storage_service
    from app.services.storage import StorageError

    def _bad(url):
        raise StorageError("图片格式不支持")

    monkeypatch.setattr(storage_service, "save_image", _bad)
    res = client.post(BASE, json=VALID, headers=auth_headers)
    assert res.status_code == 400


# ---------- 列表 / 详情 ----------
def test_list_my_recipes(client, auth_headers, make_headers):
    _create(client, auth_headers)
    _create(client, auth_headers, title="清炒时蔬")
    res = client.get(BASE, headers=auth_headers)
    assert res.status_code == 200
    items = res.json()["data"]
    assert len(items) == 2
    assert items[0]["title"] == "清炒时蔬"  # 最新在前

    other = make_headers("openid-other")
    assert client.get(BASE, headers=other).json()["data"] == []


def test_list_my_recipes_empty(client, auth_headers):
    assert client.get(BASE, headers=auth_headers).json()["data"] == []


def test_get_my_recipe_detail(client, auth_headers, make_headers):
    data = _create(client, auth_headers)
    res = client.get(f"{BASE}/{data['id']}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "祖传红烧肉"

    other = make_headers("openid-other")
    assert client.get(f"{BASE}/{data['id']}", headers=other).status_code == 404
    assert client.get(f"{BASE}/{uuid.uuid4()}", headers=auth_headers).status_code == 404


# ---------- 编辑 ----------
def test_update_my_recipe(client, auth_headers, make_headers):
    data = _create(client, auth_headers)
    res = client.put(
        f"{BASE}/{data['id']}",
        json={"title": "升级版红烧肉", "time_minutes": 120},
        headers=auth_headers,
    )
    assert res.status_code == 200
    updated = res.json()["data"]
    assert updated["title"] == "升级版红烧肉"
    assert updated["time_minutes"] == 120
    assert len(updated["ingredients"]) == 2  # 未传字段保持不变

    other = make_headers("openid-other")
    assert client.put(f"{BASE}/{data['id']}", json={"title": "x"}, headers=other).status_code == 404
    assert client.put(f"{BASE}/{uuid.uuid4()}", json={"title": "x"}, headers=auth_headers).status_code == 404


# ---------- 删除 ----------
def test_delete_my_recipe(client, auth_headers, make_headers):
    data = _create(client, auth_headers)
    other = make_headers("openid-other")
    assert client.delete(f"{BASE}/{data['id']}", headers=other).status_code == 404

    res = client.delete(f"{BASE}/{data['id']}", headers=auth_headers)
    assert res.status_code == 200
    assert client.get(BASE, headers=auth_headers).json()["data"] == []
    assert client.get(f"{BASE}/{data['id']}", headers=auth_headers).status_code == 404


# ---------- 发布到社区 ----------
def test_publish_my_recipe(client, auth_headers):
    data = _create(client, auth_headers)
    res = client.post(
        f"{BASE}/{data['id']}/publish",
        json={"content": "今天做成功了！", "topic": "跟做打卡"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    pub = res.json()["data"]
    assert pub["post_id"]
    assert pub["my_recipe_id"] == data["id"]
    assert pub["title"] == "祖传红烧肉"

    # 广场可见，且带 my_recipe_id 关联
    posts = client.get("/api/posts", headers=auth_headers).json()["data"]["items"]
    assert any(p["my_recipe_id"] == data["id"] for p in posts)


def test_publish_requires_content_or_image(client, auth_headers):
    data = _create(client, auth_headers)
    res = client.post(f"{BASE}/{data['id']}/publish", json={}, headers=auth_headers)
    assert res.status_code == 400
    assert "至少" in res.json()["message"]


def test_publish_other_user_404(client, auth_headers, make_headers):
    data = _create(client, auth_headers)
    other = make_headers("openid-other")
    res = client.post(
        f"{BASE}/{data['id']}/publish", json={"content": "x"}, headers=other
    )
    assert res.status_code == 404


def test_publish_content_safety_blocked(client, auth_headers, monkeypatch):
    from app.services import wechat as wechat_service

    async def _not_allowed(text, openid):
        return False

    monkeypatch.setattr(wechat_service, "check_text", _not_allowed)
    data = _create(client, auth_headers)
    res = client.post(
        f"{BASE}/{data['id']}/publish", json={"content": "违规词"}, headers=auth_headers
    )
    assert res.status_code == 400
    assert "违规" in res.json()["message"]


def test_publish_persists_post_row(client, auth_headers):
    data = _create(client, auth_headers)
    client.post(
        f"{BASE}/{data['id']}/publish",
        json={"content": "分享我的菜谱", "topic": "#一人食"},
        headers=auth_headers,
    )

    async def check():
        async with TestSessionLocal() as s:
            rows = (await s.execute(select(Post))).scalars().all()
            assert len(rows) == 1
            assert rows[0].my_recipe_id == uuid.UUID(data["id"])
            assert rows[0].recipe_id is None
            assert rows[0].topic == "#一人食"

    import asyncio

    asyncio.run(check())
