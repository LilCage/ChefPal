"""社区作品路由：发布 / 广场分页 / 详情 / 点赞 / 我的作品 / 分享卡。"""
import asyncio
import base64
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.like import Like
from app.models.post import Post
from app.models.recipe import Recipe
from app.models.user import User
from app.services import storage, wechat as wechat_service
from app.services.storage import StorageError
from app.services.wechat import WeChatError

router = APIRouter(prefix="/posts", tags=["posts"])


class PostCreate(BaseModel):
    content: str = Field(default="", max_length=500, description="文字心得（与图片至少一项）")
    images: list[str] = Field(default_factory=list, max_length=9, description="base64 data URL 数组")
    recipe_id: UUID | None = Field(default=None, description="关联原 AI 菜谱（可选）")
    topic: str | None = Field(default=None, max_length=32, description="话题标签，如 '#今日晚餐'")


def _normalize_topic(topic: str | None) -> str | None:
    """话题归一化：去两侧空白与 #，统一补回 #。空值返回 None。"""
    if topic is None:
        return None
    t = topic.strip().strip("#").strip()
    return f"#{t}" if t else None


def _post_out(
    post: Post, author: User | None, is_liked: bool, followed_ids: set[UUID] | None = None
) -> dict:
    return {
        "id": str(post.id),
        "content": post.content,
        "images": post.images,
        "topic": post.topic,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "is_liked": is_liked,
        "recipe_id": str(post.recipe_id) if post.recipe_id else None,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "author": {
            "id": str(author.id) if author else "",
            "nickname": (author.nickname if author and author.nickname else "美食猎人"),
            "avatar_url": author.avatar_url if author else None,
            "is_following": (
                bool(author and followed_ids is not None and author.id in followed_ids)
            ),
        },
    }


async def _get_post_or_404(db: AsyncSession, post_id: UUID) -> Post:
    post = await db.get(Post, post_id)
    if post is None:
        raise AppError("作品不存在", code=404, status_code=404)
    return post


async def _is_liked(db: AsyncSession, user_id: UUID, post_id: UUID) -> bool:
    row = await db.execute(select(Like.id).where(Like.user_id == user_id, Like.post_id == post_id))
    return row.scalar_one_or_none() is not None


async def _my_followed_ids(db: AsyncSession, user_id: UUID) -> set[UUID]:
    """当前用户已关注的用户 id 集合（用于作品卡标注关注态）。"""
    from app.models.follow import Follow

    rows = await db.execute(select(Follow.following_id).where(Follow.follower_id == user_id))
    return {r[0] for r in rows.all()}


# ---------- 发布 ----------
@router.post("")
async def create_post(
    body: PostCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """发布作品：图文至少一项；内容安全（失败降级放行）；图片传 COS/本地。"""
    content = body.content.strip()
    if not content and not body.images:
        raise AppError("图文至少填写一项", code=400, status_code=400)

    # 关联菜谱须属于当前用户
    recipe_id = None
    if body.recipe_id:
        row = await db.execute(
            select(Recipe).where(Recipe.id == body.recipe_id, Recipe.user_id == user.id)
        )
        if row.scalar_one_or_none() is None:
            raise AppError("关联菜谱不存在", code=404, status_code=404)
        recipe_id = body.recipe_id

    topic = _normalize_topic(body.topic)

    # 内容安全：文本（心得 + 话题），接口失败降级放行
    text_to_check = " ".join(x for x in (content, topic or "") if x).strip()
    if text_to_check:
        allowed = await wechat_service.check_text(text_to_check, user.openid)
        if not allowed:
            raise AppError("内容包含违规信息，请修改后重试", code=400, status_code=400)

    # 图片存储（后台线程避免阻塞事件循环）
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
        recipe_id=recipe_id,
        topic=topic,
        like_count=0,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return ok(_post_out(post, user, is_liked=False))


# ---------- 广场分页 ----------
@router.get("")
async def list_posts(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    topic: str | None = Query(default=None),
    user_id: UUID | None = Query(default=None, description="按作者筛选（作者主页）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """作品广场：最新倒序分页，可按话题/作者筛选；返回作者信息与我的点赞态。"""
    topic_norm = _normalize_topic(topic)
    base_filter = [Post.topic == topic_norm] if topic_norm else []
    if user_id is not None:
        base_filter.append(Post.user_id == user_id)

    count_q = select(func.count()).select_from(Post)
    if base_filter:
        count_q = count_q.where(*base_filter)
    total = (await db.execute(count_q)).scalar_one()

    q = select(Post)
    if base_filter:
        q = q.where(*base_filter)
    q = q.order_by(Post.created_at.desc()).offset((page - 1) * size).limit(size)
    posts = list((await db.execute(q)).scalars().all())

    # 批量取作者与我的点赞集合
    author_ids = {p.user_id for p in posts}
    authors = {}
    if author_ids:
        rows = await db.execute(select(User).where(User.id.in_(author_ids)))
        authors = {u.id: u for u in rows.scalars()}
    liked_ids: set[UUID] = set()
    if posts:
        rows = await db.execute(
            select(Like.post_id).where(Like.user_id == user.id, Like.post_id.in_([p.id for p in posts]))
        )
        liked_ids = {r[0] for r in rows.all()}
    followed_ids = await _my_followed_ids(db, user.id)

    items = [_post_out(p, authors.get(p.user_id), p.id in liked_ids, followed_ids) for p in posts]
    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "has_more": page * size < total,
        }
    )


# ---------- 我的作品（注意：必须在 /{post_id} 之前注册）----------
@router.get("/mine")
async def my_posts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """当前用户发布的作品列表。"""
    rows = await db.execute(
        select(Post).where(Post.user_id == user.id).order_by(Post.created_at.desc())
    )
    posts = rows.scalars().all()
    return ok([_post_out(p, user, is_liked=False) for p in posts])


# ---------- 话题聚合（话题广场；必须在 /{post_id} 之前注册）----------
@router.get("/topics")
async def list_topics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """全部话题及作品数（倒序），供话题广场聚合展示。"""
    rows = await db.execute(
        select(Post.topic, func.count().label("count"))
        .where(Post.topic.is_not(None))
        .group_by(Post.topic)
        .order_by(func.count().desc(), Post.topic.asc())
    )
    return ok([{"topic": topic, "count": count} for topic, count in rows.all()])


# ---------- 作品详情 ----------
@router.get("/{post_id}")
async def get_post(
    post_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """作品详情（社区内容，登录用户可见）。"""
    post = await _get_post_or_404(db, post_id)
    author = await db.get(User, post.user_id)
    liked = await _is_liked(db, user.id, post.id)
    followed_ids = await _my_followed_ids(db, user.id)
    return ok(_post_out(post, author, liked, followed_ids))


# ---------- 点赞 / 取消 ----------
@router.post("/{post_id}/like")
async def like_post(
    post_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """点赞（幂等：已点赞则直接返回）。"""
    post = await _get_post_or_404(db, post_id)
    exists = await db.execute(
        select(Like).where(Like.user_id == user.id, Like.post_id == post.id)
    )
    if exists.scalar_one_or_none() is None:
        db.add(Like(user_id=user.id, post_id=post.id))
        post.like_count += 1
        await db.commit()
    return ok({"liked": True, "like_count": post.like_count})


@router.delete("/{post_id}/like")
async def unlike_post(
    post_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """取消点赞（幂等）。"""
    post = await _get_post_or_404(db, post_id)
    exists = await db.execute(
        select(Like).where(Like.user_id == user.id, Like.post_id == post.id)
    )
    like = exists.scalar_one_or_none()
    if like is not None:
        await db.delete(like)
        post.like_count = max(0, post.like_count - 1)
        await db.commit()
    return ok({"liked": False, "like_count": post.like_count})


# ---------- 作品分享卡 ----------
@router.get("/{post_id}/share-card")
async def post_share_card(
    post_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """作品分享卡数据：作品信息 + 小程序码（scene=post_id.hex，page=作品详情页）。"""
    post = await _get_post_or_404(db, post_id)
    author = await db.get(User, post.user_id)

    qrcode_base64 = None
    try:
        scene = post.id.hex  # UUID 去横线 → 32 位，满足 scene 长度限制
        png = await wechat_service.get_unlimited_qrcode(
            scene=scene, page="pages/post-detail/index"
        )
        qrcode_base64 = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    except WeChatError:
        qrcode_base64 = None  # 小程序未发布/失败 → 降级，卡片仍可生成

    return ok(
        {
            "id": str(post.id),
            "content": post.content,
            "image": post.images[0] if post.images else None,
            "topic": post.topic,
            "like_count": post.like_count,
            "nickname": author.nickname if author and author.nickname else "美食猎人",
            "avatar_url": author.avatar_url if author else None,
            "qrcode_base64": qrcode_base64,
        }
    )
