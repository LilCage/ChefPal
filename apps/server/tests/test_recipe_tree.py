"""菜谱DNA进化树 TDD：fork 分支 / 进化树查询（原型 05 屏6）。"""
import uuid

from app.services.agents import recipe_agent

VALID_SET = {
    "recipes": [
        {"name": "经典番茄炒蛋", "match_score": 95, "time_minutes": 15, "difficulty": "简单",
         "style": "酸甜口", "missing_seasonings": ["葱"],
         "steps": [{"title": "打蛋", "detail": "打散"}], "tips": ["先炒蛋再炒番茄"]},
        {"name": "番茄鸡蛋面", "match_score": 90, "time_minutes": 20, "difficulty": "简单",
         "style": "清爽快手", "missing_seasonings": [], "steps": [{"title": "煮面", "detail": "水开下面"}], "tips": []},
        {"name": "葱油拌面", "match_score": 85, "time_minutes": 10, "difficulty": "简单",
         "style": "清爽快手", "missing_seasonings": [], "steps": [{"title": "煮面", "detail": "水开下面"}], "tips": []},
    ]
}


def _create_recipe(client, auth_headers, monkeypatch):
    async def _fake(**kwargs):
        return VALID_SET

    monkeypatch.setattr(recipe_agent, "ainvoke_json", _fake)
    return client.post(
        "/api/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=auth_headers
    ).json()["data"][0]


# ---------- fork ----------
def test_fork_recipe_creates_branch(client, auth_headers, monkeypatch):
    """基于原菜谱 fork 出新版本（我的分支）。"""
    rec = _create_recipe(client, auth_headers, monkeypatch)
    res = client.post(
        f"/api/recipes/{rec['id']}/fork",
        json={"changes": "起锅前加半勺糖 + 一点番茄酱"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["recipe_id"] == rec["id"]
    assert data["changes"] == "起锅前加半勺糖 + 一点番茄酱"
    assert data["version_label"].startswith("v")


def test_fork_requires_recipe(client, auth_headers):
    """菜谱不存在 → 404。"""
    res = client.post(
        f"/api/recipes/{uuid.uuid4()}/fork", json={"changes": "x"}, headers=auth_headers
    )
    assert res.status_code == 404


def test_fork_requires_auth(client, monkeypatch):
    """未登录 → 401。"""
    res = client.post(
        f"/api/recipes/{uuid.uuid4()}/fork", json={"changes": "x"}
    )
    assert res.status_code == 401


def test_fork_empty_changes_ok(client, auth_headers, monkeypatch):
    """changes 可空。"""
    rec = _create_recipe(client, auth_headers, monkeypatch)
    res = client.post(f"/api/recipes/{rec['id']}/fork", json={}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["changes"] == ""


# ---------- 进化树 ----------
def test_tree_root_is_original(client, auth_headers, monkeypatch):
    """未 fork 时进化树只有一个根节点（原版）。"""
    rec = _create_recipe(client, auth_headers, monkeypatch)
    res = client.get(f"/api/recipes/{rec['id']}/tree", headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["recipe_id"] == rec["id"]
    assert data["title"] == "经典番茄炒蛋"
    assert len(data["versions"]) == 1
    assert data["versions"][0]["version_label"] == "v1.0"
    assert data["versions"][0]["is_root"] is True


def test_tree_after_fork_has_chain(client, auth_headers, monkeypatch):
    """fork 后进化树包含根 + 分支，分支 changes 正确。"""
    rec = _create_recipe(client, auth_headers, monkeypatch)
    client.post(
        f"/api/recipes/{rec['id']}/fork", json={"changes": "少油不腻"}, headers=auth_headers
    )

    res = client.get(f"/api/recipes/{rec['id']}/tree", headers=auth_headers)
    data = res.json()["data"]
    assert len(data["versions"]) == 2
    v0, v1 = data["versions"]
    assert v0["is_root"] is True
    assert v1["version_label"] == "v2.0"
    assert v1["changes"] == "少油不腻"
    assert v1["parent_id"] == v0["id"]


def test_tree_requires_recipe_404(client, auth_headers):
    res = client.get(f"/api/recipes/{uuid.uuid4()}/tree", headers=auth_headers)
    assert res.status_code == 404


def test_tree_requires_auth(client):
    res = client.get(f"/api/recipes/{uuid.uuid4()}/tree")
    assert res.status_code == 401


# ---------- 多分支 ----------
def test_tree_multiple_forks(client, auth_headers, monkeypatch):
    """多次 fork 形成分支链：根 v1 → 分支 v2 → 再分支 v3。"""
    rec = _create_recipe(client, auth_headers, monkeypatch)
    v2 = client.post(
        f"/api/recipes/{rec['id']}/fork", json={"changes": "少油不腻版"}, headers=auth_headers
    ).json()["data"]
    v3 = client.post(
        f"/api/recipes/{v2['id']}/fork", json={"changes": "加糖提鲜版"}, headers=auth_headers
    ).json()["data"]

    # 从 v3 向上查询整棵树
    res = client.get(f"/api/recipes/{v3['id']}/tree", headers=auth_headers)
    assert res.status_code == 200
    versions = res.json()["data"]["versions"]
    assert [v["version_label"] for v in versions] == ["v1.0", "v2.0", "v3.0"]
    assert versions[1]["changes"] == "少油不腻版"
    assert versions[2]["changes"] == "加糖提鲜版"
