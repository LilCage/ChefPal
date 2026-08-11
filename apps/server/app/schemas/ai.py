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
    """一天的计划：三餐 + 全天合计 + 宏量营养（蛋白/脂肪/碳水）。"""

    day_label: str                             # 今天 / 明天 / 后天 或 周一~周日
    meals: list[PlanMeal] = Field(min_length=3, max_length=3)  # 早中晚三顿
    total_kcal: int = Field(ge=0, le=10000)
    protein_g: int = Field(ge=0, le=1000)
    fat_g: int = Field(default=0, ge=0, le=1000)    # 脂肪（g），7 天营养分析用
    carbs_g: int = Field(default=0, ge=0, le=1000)  # 碳水（g），7 天营养分析用


class MealPlanSchema(BaseModel):
    """膳食计划集合：3 天（今天/明天/后天）或 7 天（周一~周日）。"""

    days: list[PlanDay] = Field(min_length=1, max_length=7)


class VoteOptionsSchema(BaseModel):
    """家庭口味投票的候选菜选项（原型 05 屏2）。"""

    options: list[str] = Field(min_length=3, max_length=3)


class ShopItem(BaseModel):
    """购物清单中的一项。"""

    name: str
    quantity: str = Field(default="", description="如 2 个 / 300g / 1 瓶")


class NutritionistOut(BaseModel):
    """营养师 Agent 输出（原型 05 屏5）：热量/蛋白/搭配建议/忌口规避。"""

    calories_kcal: int = Field(ge=0, le=10000)   # 今日建议热量（千卡）
    protein_g: int = Field(ge=0, le=1000)        # 建议蛋白质（克）
    advice: str                                   # 搭配建议
    avoided_allergens: list[str] = Field(default_factory=list)  # 已避开的忌口/过敏原


class ChefOut(BaseModel):
    """大厨 Agent 输出：推荐菜 + 烹饪技法 + 摆盘建议。"""

    dish_name: str                                # 推荐菜
    technique: str                                # 核心技法
    plating: str = ""                             # 摆盘建议（可空）


class ShopperCategory(BaseModel):
    """采购清单中的一个品类。"""

    name: str
    items: list[ShopItem] = Field(min_length=1)


class ShopperOut(BaseModel):
    """采购 Agent 输出：省钱采购清单 + 省钱小贴士。"""

    categories: list[ShopperCategory] = Field(min_length=1)
    tips: str = ""


class CollaborateSchema(BaseModel):
    """多智能体协作总输出：营养师 + 大厨 + 采购。"""

    nutritionist: NutritionistOut
    chef: ChefOut
    shopper: ShopperOut


class ShopCategory(BaseModel):
    """按品类分组的购物清单。"""

    name: str                                     # 蔬菜水果 / 蛋奶肉禽 / 调料辅料 ...
    items: list[ShopItem] = Field(min_length=1)


class ShoppingListSchema(BaseModel):
    """从膳食计划汇总的分类购物清单。"""

    categories: list[ShopCategory] = Field(min_length=1)


class FridgeSuggestion(BaseModel):
    """冰箱管家组合推荐（原型 04 屏6）：用临期食材做的一道菜。"""

    ingredients: list[str] = Field(min_length=1)
    dish: str
    time_minutes: int = Field(ge=0, le=1440)
    match_score: int = Field(ge=0, le=100)


class FridgeAdviceSchema(BaseModel):
    """冰箱管家 AI 组合建议：优先消耗即将过期食材。"""

    suggestions: list[FridgeSuggestion] = Field(min_length=1, max_length=3)
    note: str = ""  # 补充建议（如"还有 1 份挂面，可加做 XX 双保险"）


class CookAnswerSchema(BaseModel):
    """语音烹饪助手回答（EXT-14.1）：基于当前菜谱上下文回答用户提问。"""

    answer: str = Field(min_length=1)          # 直接回答（口语化，简短）
    current_step: int = Field(default=0, ge=0)  # 用户当前进行到的步骤序号（1 起，0=未知）
