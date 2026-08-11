"""个人菜谱创作路由（EXT-4.1/4.2）：创建/编辑/删除/详情 + 发布到社区。

与 recipes.py（AI 生成）区分：my_recipes 是用户主动创作的菜谱，前端漫画风表单填写。
发布到社区时：复用 posts 的发布链路（内容安全 + 图片存储），以 my_recipe_id 关联。
"""
import asyncio
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.my_recipe import MyRecipe
from app.models.post import Post
from app.models.user import User
from app.services import storage, wechat as wechat_service
from app.services.storage import StorageError

router = APIRouter(prefix="/my-recipes", tags=["my-recipes"])


class MyRecipeStep(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    detail: str = Field(min_length=1, max_length=500)


class MyRecipeIngredient(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    amount: str = Field(default="", max_length=40)


class MyRecipeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    cover_image: str | None = Field(default=None, max_length=1024, description="data URL 或 URL")
    ingredients: list[MyRecipeIngredient] = Field(min_length=1, max_length=40)
    steps: list[MyRecipeStep] = Field(min_length=1, max_length=40)
    tips: list[str] = Field(default_factory=list, max_length=20)
    style: str = Field(default="", max_length=16)
    time_minutes: int = Field(default=0, ge=0, le=1440)
    difficulty: str = Field(default="简单", max_length=16)


class MyRecipeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    cover_image: str | None = Field(default=None, max_length=1024)
    ingredients: list[MyRecipeIngredient] | None = Field(default=None, min_length=1, max_length=40)
    steps: list[MyRecipeStep] | None = Field(default=None, min_length=1, max_length=40)
    tips: list[str] | None = Field(default=None, max_length=20)
    style: str | None = Field(default=None, max_length=16)
    time_minutes: int | None = Field(default=None, ge=0, le=1440)
    difficulty: str | None = Field(default=None, max_length=16)


class MyRecipePublish(BaseModel):
    content: str = Field(default="", max_length=500, description="作品心得（与图片至少一项）")
    images: list[str] = Field(default_factory=list, max_length=9, description="base64 data URL 数组")
    topic: str | None = Field(default=None, max_length=32, description="话题标签，如 '#跟做打卡'")


async def _get_owned(db: AsyncSession, user_id: UUID, my_recipe_id: UUID) -> MyRecipe:
    """取当前用户自己的菜谱，否则 404（越权保护）。"""
    row = await db.execute(
        select(MyRecipe).where(MyRecipe.id == my_recipe_id, MyRecipe.user_id == user_id)
    )
    rec = row.scalar_one_or_none()
    if rec is None:
        raise AppError("菜谱不存在", code=404, status_code=404)
    return rec


def _out(rec: MyRecipe) -> dict:
    return {
        "id": str(rec.id),
        "title": rec.title,
        "cover_image": rec.cover_image,
        "ingredients": rec.ingredients,
        "steps": rec.steps,
        "tips": rec.tips,
        "style": rec.style,
        "time_minutes": rec.time_minutes,
        "difficulty": rec.difficulty,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }


def _normalize_topic(topic: str | None) -> str | None:
    if topic is None:
        return None
    t = topic.strip().strip("#").strip()
    return f"#{t}" if t else None


@router.post("")
async def create_my_recipe(
    body: MyRecipeCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """创建个人菜谱。封面图若是 data URL 则先存储再存 URL。"""
    title = body.title.strip()
    if not title:
        raise AppError("标题不能为空", code=400, status_code=400)

    cover = None
    if body.cover_image and body.cover_image.startswith("data:"):
        try:
            cover = await asyncio.to_thread(storage.save_image, body.cover_image)
        except StorageError as exc:
            raise AppError(str(exc), code=400, status_code=400) from exc
    elif body.cover_image:
        cover = body.cover_image

    rec = MyRecipe(
        user_id=user.id,
        title=title,
        cover_image=cover,
        ingredients=[i.model_dump() for i in body.ingredients],
        steps=[s.model_dump() for s in body.steps],
        tips=body.tips,
        style=body.style,
        time_minutes=body.time_minutes,
        difficulty=body.difficulty,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return ok(_out(rec))


@router.get("")
async def list_my_recipes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """我的菜谱列表（最新在前）。"""
    rows = await db.execute(
        select(MyRecipe).where(MyRecipe.user_id == user.id).order_by(MyRecipe.created_at.desc())
    )
    return ok([_out(rec) for rec in rows.scalars()])


@router.get("/{my_recipe_id}")
async def get_my_recipe(
    my_recipe_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """菜谱详情（仅本人可见，与 recipes 一致）。"""
    rec = await _get_owned(db, user.id, my_recipe_id)
    return ok(_out(rec))


@router.put("/{my_recipe_id}")
async def update_my_recipe(
    my_recipe_id: UUID,
    body: MyRecipeUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """编辑菜谱（仅本人）。只更新传入的非空字段。"""
    rec = await _get_owned(db, user.id, my_recipe_id)

    # 封面图：仅当传入非 None 才更新；data URL 需先存储
    if body.cover_image is not None:
        if body.cover_image.startswith("data:"):
            try:
                rec.cover_image = await asyncio.to_thread(storage.save_image, body.cover_image)
            except StorageError as exc:
                raise AppError(str(exc), code=400, status_code=400) from exc
        else:
            rec.cover_image = body.cover_image

    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise AppError("标题不能为空", code=400, status_code=400)
        rec.title = title
    if body.ingredients is not None:
        rec.ingredients = [i.model_dump() for i in body.ingredients]
    if body.steps is not None:
        rec.steps = [s.model_dump() for s in body.steps]
    if body.tips is not None:
        rec.tips = body.tips
    if body.style is not None:
        rec.style = body.style
    if body.time_minutes is not None:
        rec.time_minutes = body.time_minutes
    if body.difficulty is not None:
        rec.difficulty = body.difficulty

    await db.commit()
    await db.refresh(rec)
    return ok(_out(rec))


@router.delete("/{my_recipe_id}")
async def delete_my_recipe(
    my_recipe_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除菜谱（仅本人）。"""
    rec = await _get_owned(db, user.id, my_recipe_id)
    await db.delete(rec)
    await db.commit()
    return ok(message="已删除")


@router.post("/{my_recipe_id}/publish")
async def publish_my_recipe(
    my_recipe_id: UUID,
    body: MyRecipePublish,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """把自建菜谱发布到社区：生成一条作品（my_recipe_id 关联），复用 posts 的发布链路。"""
    rec = await _get_owned(db, user.id, my_recipe_id)

    content = body.content.strip()
    if not content and not body.images:
        raise AppError("图文至少填写一项", code=400, status_code=400)

    topic = _normalize_topic(body.topic)
    text_to_check = " ".join(x for x in (content, topic or "") if x).strip()
    if text_to_check:
        allowed = await wechat_service.check_text(text_to_check, user.openid)
        if not allowed:
            raise AppError("内容包含违规信息，请修改后重试", code=400, status_code=400)

    images: list[str] = []
    if body.images:
        try:
            images = await asyncio.to_thread(storage.save_images, body.images)
        except StorageError as exc:
            raise AppError(str(exc), code=400, status_code=400) from exc

    post = Post(
        user_id=user.id,
        content=content,
        images=images,
        recipe_id=None,
        my_recipe_id=rec.id,
        topic=topic,
        like_count=0,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    return ok(
        {
            "post_id": str(post.id),
            "my_recipe_id": str(rec.id),
            "title": rec.title,
            "content": post.content,
            "images": post.images,
            "topic": post.topic,
        }
    )
