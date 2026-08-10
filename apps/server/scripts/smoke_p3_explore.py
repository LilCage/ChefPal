"""P3 趣味探索冒烟：真实服务器验证（时令日历/挑战/投票/进化树 + 真实 AI 多智能体）。

用法：.venv/Scripts/python scripts/smoke_p3_explore.py
（需后端运行在 127.0.0.1:8000；真实 AI 调用计入每日限额）
"""
import asyncio

import httpx
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.user import User

BASE = "http://127.0.0.1:8000/api"


async def get_token() -> str:
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.openid == "smoke-p3"))).scalar_one_or_none()
        if user is None:
            user = User(openid="smoke-p3", nickname="趣味探索冒烟")
            s.add(user)
            await s.commit()
            await s.refresh(user)
        return create_access_token(str(user.id))


async def main() -> None:
    token = await get_token()
    h = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=180) as c:
        # 1. 时令日历（无 AI）
        r = await c.get(f"{BASE}/seasonal?month=8", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["label"] == "8 月 · 盛夏" and len(d["items"]) == 6 and d["pairing"]["dish"]
        print("✅ 时令日历:", d["label"], "|", d["pairing"]["dish"], "| items", len(d["items"]))

        # 2. 烹饪挑战（无 AI）
        r = await c.post(f"{BASE}/challenges", json={"title": "一周只花50元", "budget": 50}, headers=h)
        assert r.status_code == 200, r.text
        cid = r.json()["data"]["id"]
        await c.post(f"{BASE}/challenges/{cid}/join", headers=h)
        await c.put(f"{BASE}/challenges/{cid}/progress", json={"spend": 38, "meal_count": 3}, headers=h)
        r = await c.get(f"{BASE}/challenges/{cid}/leaderboard", headers=h)
        assert r.json()["data"]["items"][0]["is_me"] is True
        print("✅ 烹饪挑战: 创建/加入/进度/排行榜 OK")

        # 3. 家庭投票（真实 AI）
        r = await c.post(f"{BASE}/votes/generate", json={"ingredients": ["西红柿", "鸡蛋", "面条"]}, headers=h)
        assert r.status_code == 200, r.text
        vid = r.json()["data"]["id"]
        opts = r.json()["data"]["options"]
        print("✅ 家庭投票: 生成 3 选项 =", [o["name"] for o in opts])
        r = await c.post(f"{BASE}/votes/{vid}/vote", json={"option_index": 0}, headers=h)
        assert r.json()["data"]["options"][0]["count"] == 1
        r = await c.get(f"{BASE}/votes/{vid}/share-card", headers=h)
        assert r.json()["data"]["options_count"] == 3
        print("✅ 家庭投票: 投票/结果/分享卡 OK")

        # 4. 菜谱进化树（复用菜谱生成）
        r = await c.post(f"{BASE}/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=h)
        assert r.status_code == 200, r.text
        rec = r.json()["data"][0]
        r = await c.get(f"{BASE}/recipes/{rec['id']}/tree", headers=h)
        assert r.json()["data"]["versions"][0]["is_root"] is True
        r = await c.post(f"{BASE}/recipes/{rec['id']}/fork", json={"changes": "加糖提鲜"}, headers=h)
        assert r.json()["data"]["version_label"].startswith("v")
        r = await c.get(f"{BASE}/recipes/{rec['id']}/tree", headers=h)
        assert len(r.json()["data"]["versions"]) == 2
        print("✅ 菜谱进化树: 根/fork/树链 OK")

        # 5. 多智能体（真实 AI，3 次并行）
        r = await c.post(f"{BASE}/agents/collaborate", json={"ingredients": ["鸡胸肉", "藜麦", "西兰花"]}, headers=h)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        print("✅ 多智能体: 营养师", d["nutritionist"]["calories_kcal"], "kcal | 大厨", d["chef"]["dish_name"], "| 采购", len(d["shopper"]["categories"]), "类")

        print("\n🎉 P3 趣味探索冒烟全部通过")


if __name__ == "__main__":
    asyncio.run(main())
