"""包1/3/4 冒烟：个人菜谱创作+发布 / AI口味记忆 / 语音烹饪助手（真实 AI）。

用法：.venv/Scripts/python scripts/smoke_my_recipes.py
（需后端运行在 127.0.0.1:8000；真实 AI 调用计入每日限额；跑完清理用户数据）
"""
import asyncio

import httpx
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.taste_signal import TasteSignal
from app.models.user import User

BASE = "http://127.0.0.1:8000/api"
OPENID = "smoke-my-recipes"


async def get_token() -> str:
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.openid == OPENID))).scalar_one_or_none()
        if user is None:
            user = User(openid=OPENID, nickname="新功能冒烟")
            s.add(user)
            await s.commit()
            await s.refresh(user)
        return create_access_token(str(user.id))


async def cleanup() -> None:
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.openid == OPENID))).scalar_one_or_none()
        if user is not None:
            await s.execute(delete(TasteSignal).where(TasteSignal.user_id == user.id))
            await s.delete(user)  # CASCADE 清理 posts/my_recipes 等
            await s.commit()
            print("🧹 冒烟数据已清理")


async def main() -> None:
    token = await get_token()
    h = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=180) as c:
        # 1. 个人菜谱创作
        r = await c.post(
            f"{BASE}/my-recipes",
            json={
                "title": "冒烟红烧肉",
                "ingredients": [{"name": "五花肉", "amount": "500g"}],
                "steps": [{"title": "焯水", "detail": "冷水下锅 3 分钟"}, {"title": "炒糖色", "detail": "小火炒琥珀色"}],
                "tips": ["糖色宁浅勿深"],
                "style": "浓香下饭",
                "time_minutes": 90,
                "difficulty": "较难",
            },
            headers=h,
        )
        assert r.status_code == 200, r.text
        rid = r.json()["data"]["id"]
        print("✅ 个人菜谱创建:", r.json()["data"]["title"])

        r = await c.get(f"{BASE}/my-recipes", headers=h)
        assert len(r.json()["data"]) == 1
        r = await c.put(f"{BASE}/my-recipes/{rid}", json={"time_minutes": 100}, headers=h)
        assert r.json()["data"]["time_minutes"] == 100
        print("✅ 个人菜谱列表/编辑 OK")

        # 发布到社区
        r = await c.post(f"{BASE}/my-recipes/{rid}/publish", json={"content": "冒烟发布作品"}, headers=h)
        assert r.status_code == 200, r.text
        post_id = r.json()["data"]["post_id"]
        print("✅ 个人菜谱发布到社区: post", post_id)

        # 2. AI 口味记忆
        # 收藏生成的 AI 菜谱 → 记录 style 信号
        r = await c.post(f"{BASE}/recipes/generate", json={"ingredients": ["西红柿", "鸡蛋"]}, headers=h)
        assert r.status_code == 200, r.text
        ai_rid = r.json()["data"][0]["id"]
        await c.post(f"{BASE}/favorites", json={"content_type": "recipe", "content_id": ai_rid}, headers=h)
        r = await c.get(f"{BASE}/users/me/taste-memory", headers=h)
        d = r.json()["data"]
        assert d["total_signals"] >= 1
        print("✅ 口味记忆: 收藏信号", d["total_signals"], "| styles", d["preferred_styles"])

        # 3. 语音烹饪助手（真实 AI：模拟转好的文字提问）
        r = await c.post(f"{BASE}/cook-assistant/query", json={"recipe_id": ai_rid, "question": "下一步要放多少盐"}, headers=h)
        assert r.status_code == 200, r.text
        ans = r.json()["data"]
        print("✅ 语音助手: 回答 =", ans["answer"][:40])

        # 清空口味记忆
        r = await c.delete(f"{BASE}/users/me/taste-memory", headers=h)
        assert r.json()["data"]["deleted"] >= 1
        print("✅ 口味记忆清空 OK")

        print("\n🎉 包1/3/4 冒烟全部通过")

        await cleanup()


if __name__ == "__main__":
    asyncio.run(main())
