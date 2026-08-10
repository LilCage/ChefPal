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
    style: str = Field(min_length=1, max_length=16)  # 风味标签：浓香下饭/清爽快手/蒸煮清淡/香辣过瘾等


class RecipeSetSchema(BaseModel):
    """TOP3 菜谱集合。"""

    recipes: list[GeneratedRecipe]


class PlanDish(BaseModel):
    """计划中的一道菜/主食。"""

    name: str


class PlanMeal(BaseModel):
    """一餐（早/午/晚）：菜品列表 + 该餐估算千卡。"""

    name: str                                  # 早餐 / 午餐 / 晚餐
    total_kcal: int = Field(ge=0, le=10000)    # 该餐估算千卡
    dishes: list[PlanDish] = Field(min_length=1)


class PlanDay(BaseModel):
    """一天的计划：三餐 + 全天合计。"""

    day_label: str                             # 今天 / 明天 / 后天
    meals: list[PlanMeal] = Field(min_length=3, max_length=3)  # 早中晚三顿
    total_kcal: int = Field(ge=0, le=10000)
    protein_g: int = Field(ge=0, le=1000)


class MealPlanSchema(BaseModel):
    """3 天膳食计划集合。"""

    days: list[PlanDay] = Field(min_length=3, max_length=3)  # 3 天


class ShopItem(BaseModel):
    """购物清单中的一项。"""

    name: str
    quantity: str = Field(default="", description="如 2 个 / 300g / 1 瓶")


class ShopCategory(BaseModel):
    """按品类分组的购物清单。"""

    name: str                                     # 蔬菜水果 / 蛋奶肉禽 / 调料辅料 ...
    items: list[ShopItem] = Field(min_length=1)


class ShoppingListSchema(BaseModel):
    """从膳食计划汇总的分类购物清单。"""

    categories: list[ShopCategory] = Field(min_length=1)
