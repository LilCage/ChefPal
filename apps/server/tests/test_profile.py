"""用户资料编辑 TDD：PUT /api/users/me/profile（昵称/base64 头像，合并更新）。"""
VALID_AVATAR = "data:image/jpeg;base64," + "A" * 200


def test_update_nickname_and_readback(client, auth_headers):
    res = client.put("/api/users/me/profile", json={"nickname": "美食猎人阿安"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["code"] == 0
    assert res.json()["data"]["nickname"] == "美食猎人阿安"

    me = client.get("/api/users/me", headers=auth_headers).json()["data"]
    assert me["nickname"] == "美食猎人阿安"


def test_update_avatar(client, auth_headers):
    res = client.put("/api/users/me/profile", json={"avatar_url": VALID_AVATAR}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["avatar_url"] == VALID_AVATAR


def test_update_partial_preserves_preferences(client, auth_headers):
    client.put("/api/users/me/preferences", json={"allergies": ["花生"], "spiciness": 1}, headers=auth_headers)
    res = client.put("/api/users/me/profile", json={"nickname": "小安"}, headers=auth_headers)
    assert res.status_code == 200
    me = res.json()["data"]
    assert me["preferences"]["allergies"] == ["花生"]
    assert me["preferences"]["spiciness"] == 1


def test_clear_avatar_with_empty_string(client, auth_headers):
    client.put("/api/users/me/profile", json={"avatar_url": VALID_AVATAR}, headers=auth_headers)
    res = client.put("/api/users/me/profile", json={"avatar_url": ""}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["avatar_url"] is None


def test_nickname_too_long_422(client, auth_headers):
    res = client.put("/api/users/me/profile", json={"nickname": "长" * 65}, headers=auth_headers)
    assert res.status_code == 422


def test_avatar_must_be_data_url_422(client, auth_headers):
    res = client.put(
        "/api/users/me/profile", json={"avatar_url": "https://example.com/a.png"}, headers=auth_headers
    )
    assert res.status_code == 422


def test_profile_requires_auth_401(client):
    res = client.put("/api/users/me/profile", json={"nickname": "x"})
    assert res.status_code == 401
