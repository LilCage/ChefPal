"""AI 结构化输出 Schema：落库与前端渲染的依据（对齐方案文档 §8.2）。"""
from pydantic import BaseModel, Field


class QASchema(BaseModel):
    """问答结构化回答。"""

    core_secret: str                  # 核心秘诀（一句话）
    ingredients: list[str]            # 食材清单
    steps: list[str]                  # 步骤（序号化，含火候/时长）
    avoid_pitfalls: list[str]         # 避坑指南
    sources: list[str] | None = None  # 联网搜索来源 URL


class RecipeStep(BaseModel):
    title: str
    detail: str


class GeneratedRecipe(BaseModel):
    name: str
    match_score: int = Field(ge=0, le=100)   # 食材匹配度 0-100
    time_minutes: int = Field(ge=0, le=1440)
    difficulty: str                            # 简单/中等/较难
    missing_seasonings: list[str] = Field(default_factory=list)  # 缺什么调料/替代
    steps: list[RecipeStep]
    tips: list[str] = Field(default_factory=list)  # 避坑指南（对齐原型屏4）


class RecipeSetSchema(BaseModel):
    """TOP3 菜谱集合。"""

    recipes: list[GeneratedRecipe]
