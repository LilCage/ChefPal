"""新功能冒烟：评论 / 膳食规划 / 购物清单 / 拍照识食材（真实 AI 调用，注意每日限额）。"""
import asyncio

import httpx
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.post import Post
from app.models.user import User

# 1x1 透明 PNG（评论/发布用；视觉识别用此图验证接口连通，不一定识别出食材）
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
BASE = "http://127.0.0.1:8000/api"


async def get_token() -> tuple[str, str]:
    async with AsyncSessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.openid == "smoke-new"))
        ).scalar_one_or_none()
        if user is None:
            user = User(openid="smoke-new", nickname="新功能冒烟")
            s.add(user)
            await s.commit()
            await s.refresh(user)
        return str(user.id), create_access_token(str(user.id))


async def main() -> None:
    uid, token = await get_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=120) as c:
        # 0) 发布作品（评论的载体；纯文字绕开 COS 存储，避免既有 COS 密钥问题干扰）
        r = await c.post(f"{BASE}/posts", json={"content": "冒烟评论载体", "images": []}, headers=headers)
        assert r.status_code == 200, r.text
        post = r.json()["data"]
        print(f"[0] 发布作品 OK id={post['id'][:8]}")

        # 1) 评论：发表 → 列表 → 评论点赞
        r = await c.post(f"{BASE}/posts/{post['id']}/comments", json={"content": "冒烟评论"}, headers=headers)
        assert r.status_code == 200, r.text
        cmt = r.json()["data"]
        assert cmt["is_owner"] is True
        print(f"[1] 发表评论 OK content={cmt['content']} is_owner={cmt['is_owner']}")

        r = await c.post(f"{BASE}/comments/{cmt['id']}/like", headers=headers)
        assert r.json()["data"]["liked"] is True
        r = await c.get(f"{BASE}/posts/{post['id']}/comments", headers=headers)
        data = r.json()["data"]
        assert data["total"] == 1 and data["items"][0]["is_liked"] is True
        print(f"[2] 评论列表/点赞 OK total={data['total']} like_count={data['items'][0]['like_count']}")

        # 3) 3 天膳食规划（真实 DeepSeek 调用）
        r = await c.post(f"{BASE}/plans/generate", json={}, headers=headers)
        assert r.status_code == 200, r.text
        plan = r.json()["data"]
        days = plan["data"]["days"]
        print(f"[3] 膳食规划 OK days={len(days)} 首日={days[0]['day_label']} "
              f"千卡={days[0]['total_kcal']} 蛋白={days[0]['protein_g']}g")

        # 4) 购物清单（真实 DeepSeek 调用，从最新计划汇总）
        r = await c.post(f"{BASE}/shopping-list/generate", json={}, headers=headers)
        assert r.status_code == 200, r.text
        sl = r.json()["data"]
        cats = sl["data"]["categories"]
        first = cats[0]["items"][0]
        print(f"[4] 购物清单 OK 分类={len(cats)} 首项={first['name']} {first['quantity']}")

        # 5) 勾选持久化
        r = await c.put(
            f"{BASE}/shopping-list/{sl['id']}/items/{first['item_id']}/checked",
            json={"checked": True},
            headers=headers,
        )
        assert r.json()["data"]["checked"] is True
        r = await c.get(f"{BASE}/shopping-list/latest", headers=headers)
        persisted = r.json()["data"]["data"]["categories"][0]["items"][0]
        assert persisted["checked"] is True
        print(f"[5] 勾选持久化 OK item={persisted['name']} checked={persisted['checked']}")

        # 6) 拍照识食材（真实智谱 GLM 调用，1x1 图仅验证接口连通）
        r = await c.post(f"{BASE}/vision/recognize", json={"image_base64": PNG}, headers=headers)
        assert r.status_code == 200, r.text
        ing = r.json()["data"]["ingredients"]
        print(f"[6] 视觉识别 OK 接口连通 ingredients={ing}")

        print("\n✅ 新功能冒烟全部通过（真实 AI 调用：膳食规划/购物清单/视觉识别 各 1 次）")


if __name__ == "__main__":
    asyncio.run(main())
