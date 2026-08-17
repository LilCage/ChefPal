"""微信服务端接口封装：code2Session 换 openid / access_token / 小程序码。"""
import time

import httpx

from app.core.config import get_settings

settings = get_settings()


class WeChatError(Exception):
    """微信接口返回错误码。"""


# access_token 缓存（约 2 小时有效，提前 60s 刷新）
_access_token_cache: dict = {"token": None, "expires_at": 0}


async def get_access_token() -> str:
    """获取全局 access_token，带进程内缓存。"""
    now = time.time()
    if _access_token_cache["token"] and _access_token_cache["expires_at"] > now + 60:
        return _access_token_cache["token"]

    params = {
        "grant_type": "client_credential",
        "appid": settings.WECHAT_APPID,
        "secret": settings.WECHAT_SECRET,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://api.weixin.qq.com/cgi-bin/token", params=params)
        resp.raise_for_status()
        data = resp.json()
    if "errcode" in data and data.get("errcode") != 0:
        raise WeChatError(data.get("errmsg", "get access_token failed"))

    _access_token_cache["token"] = data["access_token"]
    _access_token_cache["expires_at"] = now + int(data.get("expires_in", 7200))
    return _access_token_cache["token"]


async def get_unlimited_qrcode(scene: str, page: str, width: int = 430) -> bytes:
    """获取不限制数量的小程序码（getwxacodeunlimit），成功返回图片二进制。"""
    token = await get_access_token()
    url = f"https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token={token}"
    payload = {
        "scene": scene,
        "page": page,
        "width": width,
        "check_path": False,
        "env_version": "release",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        # 成功返回图片二进制流；失败返回 JSON（errcode/errmsg）
        if "json" in resp.headers.get("content-type", ""):
            data = resp.json()
            raise WeChatError(data.get("errmsg", "getwxacodeunlimit failed"))
        return resp.content


async def check_text(content: str, openid: str, scene: int = 3) -> bool:
    """微信文本内容安全检测（msgSecCheck v2）。

    返回 True=放行 / False=应拦截（suggest == risky）。
    接口调用失败（网络/未开通/超时）时**降级放行**，与小程序码降级策略一致，
    避免发布链路被外部故障阻断。
    """
    url = "https://api.weixin.qq.com/wxa/msg_sec_check"
    payload = {"content": content[:2500], "version": 2, "scene": scene, "openid": openid}
    try:
        # token 获取与接口调用任一失败都降级放行，避免发布链路被外部故障阻断
        token = await get_access_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{url}?access_token={token}", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001
        return True  # 降级放行（网络/超时/未开通/token 获取失败）
    if data.get("errcode") not in (0, None):
        return True  # 微信侧错误（如未开通）→ 降级放行
    suggest = (data.get("result") or {}).get("suggest", "pass")
    return suggest != "risky"


async def code2session(code: str) -> dict:
    """调用微信 code2Session 换取 openid / session_key。

    成功返回微信原始 JSON（含 openid）；失败抛 WeChatError。
    测试中可 monkeypatch 本函数。
    """
    params = {
        "appid": settings.WECHAT_APPID,
        "secret": settings.WECHAT_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(settings.WECHAT_CODE2SESSION_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    if "errcode" in data and data.get("errcode") != 0:
        raise WeChatError(data.get("errmsg", "wechat code2session failed"))
    return data
