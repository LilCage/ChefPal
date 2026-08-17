"""微信服务封装单测：check_text 降级策略。

回归背景：check_text 的 access_token 获取曾在 try 外，token 失败会抛 WeChatError
阻断发布链路（无密钥的 CI 环境 3 个用例失败）。现在 token/接口任一失败都降级放行，
此文件锁住该行为。
"""
import asyncio

from app.services import wechat as wechat_service


def test_check_text_degrades_when_token_fails(monkeypatch):
    """access_token 获取失败（未配置密钥/微信侧报错）→ 降级放行 True。"""

    async def _token_boom() -> str:
        raise wechat_service.WeChatError("appid missing")

    monkeypatch.setattr(wechat_service, "get_access_token", _token_boom)
    assert asyncio.run(wechat_service.check_text("今天做了红烧肉", "openid-x")) is True


def test_check_text_degrades_when_api_fails(monkeypatch):
    """msgSecCheck 接口调用失败（网络/超时）→ 降级放行 True。"""

    async def _token() -> str:
        return "fake-token"

    async def _post(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr(wechat_service, "get_access_token", _token)
    monkeypatch.setattr(wechat_service.httpx.AsyncClient, "post", _post)
    assert asyncio.run(wechat_service.check_text("随便写点什么", "openid-x")) is True


def test_check_text_blocks_risky(monkeypatch):
    """微信明确判定 risky → 拦截 False（降级策略不破坏拦截逻辑）。"""

    async def _token() -> str:
        return "fake-token"

    class _Resp:
        @staticmethod
        def raise_for_status() -> None:
            pass

        @staticmethod
        def json() -> dict:
            return {"errcode": 0, "result": {"suggest": "risky"}}

    async def _post(*args, **kwargs):
        return _Resp()

    monkeypatch.setattr(wechat_service, "get_access_token", _token)
    monkeypatch.setattr(wechat_service.httpx.AsyncClient, "post", _post)
    assert asyncio.run(wechat_service.check_text("危险内容", "openid-x")) is False
