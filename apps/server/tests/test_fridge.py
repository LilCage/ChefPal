"""冰箱管家 TDD：食材添加 / 临期列表 / 做掉删除 / AI 组合推荐。"""
import asyncio
import copy
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.fridge_item import FridgeItem
from app.routers import fridge as fridge_router
from app.services import fridge as fridge_service
from app.services.fridge import compute_status, infer_shelf_days
from tests.conftest import TestSessionLocal

VALID_ADVICE = {
    "suggestions": [
        {"ingredients": ["西红柿", "鸡蛋"], "dish": "番茄炒蛋", "time_minutes": 20, "match_score": 92},
        {"ingredients": ["挂面"], "dish": "西红柿鸡蛋面", "time_minutes": 25, "match_score": 88},
    ],
    "note": "还有 1 份挂面，可加做「番茄鸡蛋面」双保险",
}


# ---------- 服务：保质期推断 / 状态计算 ----------
def test_infer_shelf_days():
    assert infer_shelf_days("西红柿") == 6
    assert infer_shelf_days("鸡蛋") == 14
    assert infer_shelf_days("大西红柿") == 6  # 关键词包含匹配
    assert infer_shelf_days("神秘果") == 7  # 兜底


def test_compute_status_boundaries():
    now = datetime.now(timezone.utc)
    # 已放 5 天 / 保质 6 天 → 剩 1 天 → now
    assert compute_status(now - timedelta(days=5), 6) == {"days_stored": 5, "days_left": 1, "status": "now"}
    # 已放 6 天 / 保质 6 天 → 剩 0 天 → now
    assert compute_status(now - timedelta(days=6), 6) == {"days_stored": 6, "days_left": 0, "status": "now"}
    # 已放 4 天 / 保质 6 天 → 剩 2 天 → warn
    assert compute_status(now - timedelta(days=4), 6) == {"days_stored": 4, "days_left": 2, "status": "warn"}
    # 已放 3 天 / 保质 6 天 → 剩 3 天 → ok
    assert compute_status(now - timedelta(days=3), 6) == {"days_stored": 3, "days_left": 3, "status": "ok"}
    # 刚放 → ok
    st = compute_status(now, 7)
    assert st["status"] == "ok" and st["days_stored"] == 0 and st["days_left"] == 7


# ---------- 服务：AI 组合推荐 ----------
def test_generate_advice_success(monkeypatch):
    async def _fake(**kwargs):
        return copy.deepcopy(VALID_ADVICE)

    monkeypatch.setattr(fridge_service, "ainvoke_json", _fake)
    result = asyncio.run(fridge_service.generate_advice(["西红柿", "鸡蛋"], ["西红柿", "鸡蛋", "挂面"]))
    assert result["suggestions"][0]["dish"] == "番茄炒蛋"
    assert result["note"]


def test_generate_advice_no_expiring_raises():
    with pytest.raises(fridge_service.FridgeAdviceError):
        asyncio.run(fridge_service.generate_advice(["  "]))


def test_generate_advice_invalid_output_raises(monkeypatch):
    async def _fake(**kwargs):
        return {"suggestions": []}  # 结构不完整

    monkeypatch.setattr(fridge_service, "ainvoke_json", _fake)
    with pytest.raises(fridge_service.FridgeAdviceError):
        asyncio.run(fridge_service.generate_advice(["西红柿"]))


# ---------- 工具：添加 / 列表 / 删除 ----------
def _add(client, auth_headers, name, emoji="", best_before_days=None):
    body = {"name": name}
    if emoji:
        body["emoji"] = emoji
    if best_before_days is not None:
        body["best_before_days"] = best_before_days
    res = client.post("/api/fridge", json=body, headers=auth_headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _backdate(item_id: str, days: int):
    async def do():
        async with TestSessionLocal() as s:
            res = await s.execute(select(FridgeItem).where(FridgeItem.id == uuid.UUID(item_id)))
            item = res.scalar_one()
            item.added_at = datetime.now(timezone.utc) - timedelta(days=days)
            await s.commit()

    asyncio.run(do())


def test_add_fridge_item_infers_shelf_days(client, auth_headers):
    data = _add(client, auth_headers, "西红柿")
    assert data["name"] == "西红柿"
    assert data["best_before_days"] == 6
    assert data["status"] == "ok"
    assert data["days_stored"] == 0


def test_add_fridge_item_with_shelf_days(client, auth_headers):
    data = _add(client, auth_headers, "牛奶", emoji="🥛", best_before_days=10)
    assert data["best_before_days"] == 10
    assert data["emoji"] == "🥛"


def test_add_fridge_item_fallback_shelf_7(client, auth_headers):
    data = _add(client, auth_headers, "神秘果")
    assert data["best_before_days"] == 7


def test_add_fridge_item_blank_name_400(client, auth_headers):
    res = client.post("/api/fridge", json={"name": "   "}, headers=auth_headers)
    assert res.status_code == 400


def test_add_fridge_item_requires_auth(client):
    assert client.post("/api/fridge", json={"name": "西红柿"}).status_code == 401


def test_list_fridge_expiring_grouping(client, auth_headers):
    # 西红柿 剩1天(now) / 鸡蛋 剩2天(warn) / 生菜 剩3天(ok)
    a = _add(client, auth_headers, "西红柿")
    b = _add(client, auth_headers, "鸡蛋")
    c = _add(client, auth_headers, "生菜")
    _backdate(a["id"], 5)   # 6-5=1 → now
    _backdate(b["id"], 12)  # 14-12=2 → warn
    _backdate(c["id"], 3)   # 6-3=3 → ok

    res = client.get("/api/fridge", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["expiring_count"] == 2
    names = [i["name"] for i in data["items"]]
    assert names == ["西红柿", "鸡蛋", "生菜"]  # 紧迫度升序
    assert data["items"][0]["status"] == "now"
    assert data["items"][0]["days_left"] == 1
    assert data["items"][1]["status"] == "warn"
    assert data["items"][2]["status"] == "ok"


def test_list_fridge_empty(client, auth_headers):
    res = client.get("/api/fridge", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"] == {"items": [], "expiring_count": 0}


def test_remove_fridge_item(client, auth_headers, make_headers):
    data = _add(client, auth_headers, "西红柿")
    res = client.delete(f"/api/fridge/{data['id']}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["data"]["removed"] is True
    # 已删除 → 列表为空
    assert client.get("/api/fridge", headers=auth_headers).json()["data"]["items"] == []
    # 再删 → 404
    assert client.delete(f"/api/fridge/{data['id']}", headers=auth_headers).status_code == 404
    # 他人删除 → 404
    other = make_headers("openid-other")
    data2 = _add(client, auth_headers, "鸡蛋")
    assert client.delete(f"/api/fridge/{data2['id']}", headers=other).status_code == 404


# ---------- AI 组合推荐 ----------
def _mock_advice(monkeypatch, result=VALID_ADVICE, error=None, capture=None):
    async def _fake(expiring, all_items=None):
        if capture is not None:
            capture["expiring"] = expiring
        if error:
            raise error
        return copy.deepcopy(result)

    monkeypatch.setattr(fridge_service, "generate_advice", _fake)
    return _fake


def test_advice_success(client, auth_headers, monkeypatch):
    a = _add(client, auth_headers, "西红柿")
    _add(client, auth_headers, "挂面")
    _backdate(a["id"], 5)  # 剩1天 → 临期

    capture = {}
    _mock_advice(monkeypatch, capture=capture)
    res = client.post("/api/fridge/advice", headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["suggestions"][0]["dish"] == "番茄炒蛋"
    assert "note" in data
    assert capture["expiring"] == ["西红柿"]


def test_advice_no_expiring_400(client, auth_headers, monkeypatch):
    _add(client, auth_headers, "西红柿")  # 刚放 → ok，不临期
    _mock_advice(monkeypatch)
    res = client.post("/api/fridge/advice", headers=auth_headers)
    assert res.status_code == 400
    assert "过期" in res.json()["message"]


def test_advice_service_error_502(client, auth_headers, monkeypatch):
    a = _add(client, auth_headers, "西红柿")
    _backdate(a["id"], 5)
    _mock_advice(monkeypatch, error=fridge_service.FridgeAdviceError("mock 生成失败"))
    res = client.post("/api/fridge/advice", headers=auth_headers)
    assert res.status_code == 502


def test_advice_requires_auth(client):
    assert client.post("/api/fridge/advice").status_code == 401


def test_advice_rate_limit(client, auth_headers, monkeypatch):
    from app.core.response import AppError

    a = _add(client, auth_headers, "西红柿")
    _backdate(a["id"], 5)
    _mock_advice(monkeypatch)

    async def _over(db, user_id, limit):
        raise AppError("今日调用已达上限，明日再来吧", code=429, status_code=429)

    monkeypatch.setattr(fridge_router, "ensure_within_limit", _over)
    res = client.post("/api/fridge/advice", headers=auth_headers)
    assert res.status_code == 429
    assert "上限" in res.json()["message"]
