"""社区冒烟：登录态造用户 → 发布(本地存图) → 广场 → 详情 → 点赞 → 分享卡。"""
import asyncio

import httpx
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.user import User

# 1x1 透明 PNG
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
BASE = "http://127.0.0.1:8000/api"


async def get_token() -> tuple[str, str]:
    async with AsyncSessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.openid == "smoke-post"))
        ).scalar_one_or_none()
        if user is None:
            user = User(openid="smoke-post", nickname="冒烟猎人")
            s.add(user)
            await s.commit()
            await s.refresh(user)
        return str(user.id), create_access_token(str(user.id))


async def main() -> None:
    uid, token = await get_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=20) as c:
        # 发布（图片落本地 uploads/，内容安全降级放行）
        r = await c.post(
            f"{BASE}/posts",
            json={"content": "冒烟测试作品", "images": [PNG], "topic": "#今日晚餐"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        post = r.json()["data"]
        print(f"[1] 发布 OK  id={post['id'][:8]}  images={post['images']}  topic={post['topic']}")

        # 静态图可访问
        img_url = post["images"][0]
        img = await c.get(f"http://127.0.0.1:8000{img_url}")
        print(f"[2] 静态图 GET {img_url} -> {img.status_code}")

        # 广场分页
        r = await c.get(f"{BASE}/posts?page=1&size=5", headers=headers)
        data = r.json()["data"]
        print(f"[3] 广场 total={data['total']} first_author={data['items'][0]['author']['nickname']}")

        # 话题筛选
        r = await c.get(f"{BASE}/posts?topic=今日晚餐", headers=headers)
        print(f"[4] 话题筛选 #今日晚餐 total={r.json()['data']['total']}")

        # 详情
        r = await c.get(f"{BASE}/posts/{post['id']}", headers=headers)
        d = r.json()["data"]
        print(f"[5] 详情 is_liked={d['is_liked']} like_count={d['like_count']}")

        # 点赞 ×2（幂等）→ 取消
        r1 = await c.post(f"{BASE}/posts/{post['id']}/like", headers=headers)
        r2 = await c.post(f"{BASE}/posts/{post['id']}/like", headers=headers)
        print(f"[6] 点赞幂等 like_count={r1.json()['data']['like_count']}/{r2.json()['data']['like_count']}")
        r3 = await c.delete(f"{BASE}/posts/{post['id']}/like", headers=headers)
        print(f"[7] 取消点赞 like_count={r3.json()['data']['like_count']}")

        # 我的作品
        r = await c.get(f"{BASE}/posts/mine", headers=headers)
        print(f"[8] 我的作品 count={len(r.json()['data'])}")

        # 分享卡（二维码可能因小程序未发布降级为 null）
        r = await c.get(f"{BASE}/posts/{post['id']}/share-card", headers=headers)
        sc = r.json()["data"]
        print(f"[9] 分享卡 content={sc['content'][:10]} qrcode={'有' if sc['qrcode_base64'] else '降级为空'}")

    print("\n✅ 冒烟全部通过")


asyncio.run(main())
