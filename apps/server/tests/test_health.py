"""STEP 1 · 健康检查与统一响应契约。"""


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    # 统一响应契约 { code, message, data }
    assert set(body.keys()) == {"code", "message", "data"}
    assert body["code"] == 0
    assert body["data"]["status"] == "up"


def test_unknown_route_returns_404(client):
    res = client.get("/api/nope")
    assert res.status_code == 404
