"""时令食材日历路由：GET /api/seasonal?month=N（原型 05 屏3）。

纯静态数据服务，无 AI 调用、无数据库。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import ok
from app.db.session import get_db
from app.models.user import User
from app.services import seasonal

router = APIRouter(prefix="/seasonal", tags=["seasonal"])


@router.get("")
async def get_seasonal(
    month: int | None = Query(default=None, ge=1, le=12, description="1-12 月，缺省为当前月"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回指定月份（默认当前月）的时令食材与推荐搭配。"""
    data = seasonal.get_month(month)
    return ok(data)
