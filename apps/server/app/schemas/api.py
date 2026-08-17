"""API 层 Pydantic Schema（入参/出参）。"""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- 认证 ----------
class LoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256, description="wx.login 返回的临时 code")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nickname: str | None = None
    avatar_url: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    # 是否已看过新用户引导（User.onboarded 属性，取自 preferences，随账号走）
    onboarded: bool = False
    created_at: datetime


class LoginResponse(BaseModel):
    token: str
    user: UserOut


# ---------- 个人资料 ----------
class ProfileUpdate(BaseModel):
    """编辑资料：昵称 / 头像（base64）。字段可选，合并更新。"""

    model_config = ConfigDict(extra="ignore")

    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    avatar_url: str | None = Field(
        default=None,
        max_length=1_000_000,
        description="data:image/... 开头的 base64 头像，空串表示清除",
    )

    @field_validator("avatar_url")
    @classmethod
    def _validate_avatar(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if v and not v.startswith("data:image/"):
            raise ValueError("avatar_url 必须是 data:image/ 开头的 base64 数据")
        return v  # 空串保留为"清除头像"标记，路由层处理


# ---------- 口味偏好 ----------
class PreferencesUpdate(BaseModel):
    """忌口/辣度/咸淡/技能 的 JSONB 偏好。宽松结构，字段可选。"""

    model_config = ConfigDict(extra="ignore")

    allergies: list[str] = Field(default_factory=list)      # 忌口（可多选，含自定义）
    spiciness: int | None = Field(default=None, ge=0, le=3)  # 0不吃辣 1微辣 2中辣 3特辣
    saltiness: str | None = None                            # 偏淡/适中/偏咸
    skill: str | None = None                                # 厨房小白/进阶达人/实力大厨

    @field_validator("allergies")
    @classmethod
    def _clean_allergies(cls, v: list[str]) -> list[str]:
        """清洗自定义忌口：去空白/去重/限长/限数量，保留顺序。"""
        cleaned: list[str] = []
        for item in v:
            s = str(item).strip()
            if s and s not in cleaned and len(s) <= 20:
                cleaned.append(s)
            if len(cleaned) >= 10:
                break
        return cleaned
