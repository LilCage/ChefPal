"""社区评论路由：发表 / 列表 / 评论点赞(幂等) / 删除。"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.comment import Comment
from app.models.comment_like import CommentLike
from app.models.post import Post
from app.models.user import User
from app.services import wechat as wechat_service

router = APIRouter(tags=["comments"])


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=200, description="评论内容")


def _comment_out(
    comment: Comment,
    author: User | None,
    is_owner: bool,
    is_liked: bool,
) -> dict:
    return {
        "id": str(comment.id),
        "content": comment.content,
        "like_count": comment.like_count,
        "is_liked": is_liked,
        "is_owner": is_owner,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "author": {
            "id": str(author.id) if author else "",
            "nickname": (author.nickname if author and author.nickname else "美食猎人"),
            "avatar_url": author.avatar_url if author else None,
        },
    }


async def _get_comment_or_404(db: AsyncSession, comment_id: UUID) -> Comment:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise AppError("评论不存在", code=404, status_code=404)
    return comment


# ---------- 发表评论 ----------
@router.post("/posts/{post_id}/comments")
async def create_comment(
    post_id: UUID,
    body: CommentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """发表评论：内容安全检测（失败降级放行），作品评论计数 +1。"""
    post = await db.get(Post, post_id)
    if post is None:
        raise AppError("作品不存在", code=404, status_code=404)

    content = body.content.strip()
    if not content:
        raise AppError("评论内容不能为空", code=400, status_code=400)

    allowed = await wechat_service.check_text(content, user.openid)
    if not allowed:
        raise AppError("评论包含违规信息，请修改后重试", code=400, status_code=400)

    comment = Comment(post_id=post.id, user_id=user.id, content=content, like_count=0)
    post.comment_count += 1
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return ok(_comment_out(comment, user, is_owner=(user.id == post.user_id), is_liked=False))


# ---------- 评论列表（时间正序，最新在最后）----------
@router.get("/posts/{post_id}/comments")
async def list_comments(
    post_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """评论列表：时间正序分页；返回作者信息、是否楼主、我的点赞态。"""
    post = await db.get(Post, post_id)
    if post is None:
        raise AppError("作品不存在", code=404, status_code=404)

    total = (
        await db.execute(select(func.count()).select_from(Comment).where(Comment.post_id == post.id))
    ).scalar_one()
    q = (
        select(Comment)
        .where(Comment.post_id == post.id)
        .order_by(Comment.created_at.asc())
        .offset((page - 1) * size)
        .limit(size)
    )
    comments = list((await db.execute(q)).scalars().all())

    author_ids = {c.user_id for c in comments}
    authors: dict[UUID, User] = {}
    if author_ids:
        rows = await db.execute(select(User).where(User.id.in_(author_ids)))
        authors = {u.id: u for u in rows.scalars()}
    liked_ids: set[UUID] = set()
    if comments:
        rows = await db.execute(
            select(CommentLike.comment_id).where(
                CommentLike.user_id == user.id,
                CommentLike.comment_id.in_([c.id for c in comments]),
            )
        )
        liked_ids = {r[0] for r in rows.all()}

    items = [
        _comment_out(c, authors.get(c.user_id), c.user_id == post.user_id, c.id in liked_ids)
        for c in comments
    ]
    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "has_more": page * size < total,
        }
    )


# ---------- 评论点赞 / 取消（幂等）----------
@router.post("/comments/{comment_id}/like")
async def like_comment(
    comment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """评论点赞（幂等：已点赞则直接返回）。"""
    comment = await _get_comment_or_404(db, comment_id)
    exists = await db.execute(
        select(CommentLike).where(CommentLike.user_id == user.id, CommentLike.comment_id == comment.id)
    )
    if exists.scalar_one_or_none() is None:
        db.add(CommentLike(user_id=user.id, comment_id=comment.id))
        comment.like_count += 1
        await db.commit()
    return ok({"liked": True, "like_count": comment.like_count})


@router.delete("/comments/{comment_id}/like")
async def unlike_comment(
    comment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """取消评论点赞（幂等）。"""
    comment = await _get_comment_or_404(db, comment_id)
    exists = await db.execute(
        select(CommentLike).where(CommentLike.user_id == user.id, CommentLike.comment_id == comment.id)
    )
    like = exists.scalar_one_or_none()
    if like is not None:
        await db.delete(like)
        comment.like_count = max(0, comment.like_count - 1)
        await db.commit()
    return ok({"liked": False, "like_count": comment.like_count})


# ---------- 删除评论（仅评论本人）----------
@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除自己的评论：评论计数 -1。"""
    comment = await _get_comment_or_404(db, comment_id)
    if comment.user_id != user.id:
        raise AppError("只能删除自己的评论", code=403, status_code=403)
    post = await db.get(Post, comment.post_id)
    await db.delete(comment)
    if post is not None:
        post.comment_count = max(0, post.comment_count - 1)
    await db.commit()
    return ok(message="评论已删除")
