"""HowToCook markdown 解析器：菜谱/技巧文件 → 结构化条目。

HowToCook（Anduin2017，The Unlicense）菜谱格式（见 docs 内 01 样本）：
    # 菜名.做法
    简介段落
    预估烹饪难度：★★
    预估卡路里：XXX 大卡
    ## 必备原料和工具   → * 食材
    ## 计算             → 份量换算（忽略）
    ## 操作             → 1. 步骤
    ## 附加内容         → * 技巧
    ## 成品图           → 忽略
技巧文件（tips/**）为自由 markdown：H1 标题 + 正文，整体作为 content。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# 目录 → 中文分类
CATEGORY_MAP: dict[str, str] = {
    "aquatic": "水产",
    "breakfast": "早餐",
    "condiment": "佐料",
    "dessert": "甜点",
    "drink": "饮品",
    "meat_dish": "肉菜",
    "semi-finished": "半成品",
    "soup": "汤",
    "staple": "主食",
    "vegetable_dish": "素菜",
    "tips/learn": "新手技巧",
    "tips/advanced": "进阶技巧",
    "tips": "厨房基础",
}

# 星级 → 难度等级（HowToCook 用 ★ 计，最多 ~4 星）
_DIFFICULTY_BY_STARS = {1: "简单", 2: "中等", 3: "较难", 4: "较难"}

_TITLE_SUFFIX = re.compile(r"\.?(的做法|做法|菜谱)?\s*$")
_STAR_LINE = re.compile(r"^\s*预估烹饪难度[：:]\s*(★+)\s*$")
_CAL_LINE = re.compile(r"^\s*预估卡路里[：:]\s*(\d+)\s*大卡\s*$")
_BULLET = re.compile(r"^\s*[\-*]\s+(.+)$")
_STEP = re.compile(r"^\s*(\d+)[.、)]\s*(.+)$")
_SECTION = re.compile(r"^##\s+(.+)$")
# markdown 图片 ![...](...)：HowToCook 每个菜都配成品图，答案里不需要（但详情页可展示）
_IMAGE_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _extract_images(md: str, source_id: str) -> list[str]:
    """从 markdown 提取成品图相对路径，解析为仓库内相对路径（如 dishes/xxx/1.jpeg）。"""
    # as_posix 保证正斜杠（Windows str(Path.parent) 是反斜杠，会破坏图片 URL）
    base = Path(source_id).parent.as_posix() if source_id else ""
    out: list[str] = []
    for m in _IMAGE_LINK.finditer(md):
        raw = m.group(1).strip()
        if raw.startswith(("http://", "https://", "//")):
            continue  # 外部链接跳过
        rel = raw.lstrip("./")
        out.append(f"{base}/{rel}" if base else rel)
    # 去重保序
    return list(dict.fromkeys(out))
# 原料小节里的元信息行（不是食材）
_META_LABEL = re.compile(r"^(注|注意|工具|要求|说明|小贴士)[：:]")
# 主料/辅料等标签行：'主料：`大肉`、`鸡蛋`（可选）'
_LABELED_ITEMS = re.compile(r"^(主料|辅料|食材|原料|材料)[：:]\s*(.+)$")


def _extract_ingredients(line: str) -> list[str]:
    """从原料 bullet 提取食材名列表（去反引号、跳过元信息、顿号拆分）。

    '黄瓜'                        → ['黄瓜']
    '主料：`大肉`、`鸡蛋`（可选）'   → ['大肉', '鸡蛋（可选）']
    '注：请把刀磨利'               → []
    """
    line = line.strip().replace("`", "")
    if _META_LABEL.match(line):
        return []
    m = _LABELED_ITEMS.match(line)
    if m:
        return [it.strip() for it in m.group(2).split("、") if it.strip()]
    return [line] if line else []


def _clean_inline(text: str) -> str:
    """去掉行内 markdown 图片与反引号强调，返回纯文本。"""
    text = _IMAGE_MD.sub("", text)
    return text.replace("`", "").strip()


# ---------- 步骤切分：食材处理 vs 烹饪步骤 ----------
# HowToCook 部分菜有 ### 子节（原材料准备/开始制作…），命名不统一 → 关键词归类
PREP_SUB_KEYWORDS = ("准备", "处理", "腌", "焯", "裹", "预处理", "切", "配菜", "备")
COOK_SUB_KEYWORDS = ("制作", "步骤", "烹饪", "烤", "炖", "煮", "煎", "炸", "成品", "上菜", "火候", "微波炉", "方法", "收尾", "开始", "复炸", "蒸")
# 无子节的扁平菜谱：按步骤文本关键词逐条归类
# 强食材处理动作（优先）：命中且无强烹饪动词 → prep
STRONG_PREP_STEP = (
    "切", "洗", "淘", "削", "剥", "腌", "泡", "焯", "剁", "裹", "打散", "打蛋",
    "沥干", "擦干", "洗净", "去皮", "去壳", "去骨", "去籽", "去腥", "解冻", "摘",
    "剪", "拍", "切块", "切片", "切丝", "切丁", "切末", "切条", "化冻", "处理", "剁碎",
)
# 强烹饪动词：命中即视为烹饪步骤
STRONG_COOK_STEP = (
    "炒", "煮", "蒸", "炖", "煎", "炸", "焖", "烧", "烤", "卤", "烩", "下锅", "入锅",
    "出锅", "起锅", "装盘", "上桌", "煎至", "煮至", "收汁", "勾芡", "翻炒", "关火",
    "开火", "热油", "油温", "翻面", "盛出", "炖煮", "翻炒至",
)


def _classify_subsection(name: str) -> str:
    """按子节名归类：'原材料准备/腌制'→prep，'开始制作/炖煮'→cook，默认 cook。"""
    if any(k in name for k in PREP_SUB_KEYWORDS):
        return "prep"
    if any(k in name for k in COOK_SUB_KEYWORDS):
        return "cook"
    return "cook"


def _classify_step(text: str) -> str:
    """按步骤文本关键词归类：有强食材处理动作且无强烹饪动词→prep；否则 cook。

    泛用词（放入/加入/倒入/加盐等）不判烹饪，避免"放入白糖腌制 15 分钟"被误判。
    """
    if any(k in text for k in STRONG_COOK_STEP):
        return "cook"
    if any(k in text for k in STRONG_PREP_STEP):
        return "prep"
    return "cook"


@dataclass
class HowToCookDish:
    """解析出的结构化条目（一道菜或一篇技巧）。"""

    title: str
    kind: str  # recipe | tip
    category: str
    summary: str = ""
    content: str = ""  # tip 全文
    difficulty: str = "简单"
    calories: str = ""  # "107 大卡"（展示用）
    ingredients: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    prep_steps: list[str] = field(default_factory=list)  # 食材处理（切/洗/腌/焯等）
    cook_steps: list[str] = field(default_factory=list)  # 烹饪步骤（下锅/调味/出锅等）
    tips: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)  # 成品图仓库内相对路径
    time_minutes: int = 0  # HowToCook 无明确时长字段
    source_id: str = ""  # 仓库内相对路径，用于溯源


def _clean_title(raw: str) -> str:
    title = raw.strip().strip("#").strip()
    title = _TITLE_SUFFIX.sub("", title).strip()
    return title


def parse_dish_markdown(md: str, *, category: str = "", source_id: str = "") -> HowToCookDish:
    """解析菜谱 markdown → HowToCookDish(kind=recipe)。"""
    lines = md.splitlines()
    title = ""
    summary_lines: list[str] = []
    difficulty = "简单"
    calories = ""
    ingredients: list[str] = []
    steps: list[str] = []
    prep_steps: list[str] = []
    cook_steps: list[str] = []
    tips: list[str] = []

    current_section: str | None = None
    current_sub: str | None = None  # 操作小节里的 ### 子节
    has_ops_sub = False  # 操作是否有 ### 子节（有则按子节归类，无则按步骤关键词）
    in_intro = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        # H1 标题
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = _clean_title(stripped)
            in_intro = True
            continue

        # 小节标题（## 级）
        m = _SECTION.match(stripped)
        if m:
            current_section = m.group(1).strip()
            current_sub = None
            in_intro = False
            continue

        # 操作内的 ### 子节（原材料准备 / 开始制作…）
        if current_section == "操作" and stripped.startswith("### "):
            current_sub = stripped[4:].strip()
            has_ops_sub = True
            continue

        if stripped == "":
            continue

        # 难度 / 卡路里（可能出现在简介之前）
        m = _STAR_LINE.match(stripped)
        if m:
            stars = len(m.group(1))
            difficulty = _DIFFICULTY_BY_STARS.get(stars, "中等")
            continue
        m = _CAL_LINE.match(stripped)
        if m:
            calories = f"{int(m.group(1))} 大卡"
            continue

        if current_section is None and in_intro:
            if _IMAGE_MD.search(stripped):
                continue  # 跳过成品图 markdown
            summary_lines.append(stripped)
            continue

        if current_section == "必备原料和工具" or current_section == "所需原材料":
            m = _BULLET.match(stripped)
            if m:
                ingredients.extend(_extract_ingredients(m.group(1)))
            continue

        if current_section == "操作":
            m = _STEP.match(stripped)
            if m:
                step_text = f"{m.group(1)}. {_clean_inline(m.group(2))}"
                steps.append(step_text)
                # 切分：有 ### 子节按子节归类，否则按步骤关键词
                if has_ops_sub:
                    (prep_steps if _classify_subsection(current_sub or "") == "prep" else cook_steps).append(step_text)
                elif _classify_step(step_text) == "prep":
                    prep_steps.append(step_text)
                else:
                    cook_steps.append(step_text)
            continue

        if current_section == "附加内容":
            m = _BULLET.match(stripped)
            if m:
                text = _clean_inline(m.group(1))
                if text:
                    tips.append(text)
            continue

        # 其它小节（计算/成品图/备注等）忽略

    return HowToCookDish(
        title=title or _fallback_title(source_id),
        kind="recipe",
        category=category,
        summary="\n".join(summary_lines),
        difficulty=difficulty,
        calories=calories,
        ingredients=ingredients,
        steps=steps,
        prep_steps=prep_steps,
        cook_steps=cook_steps,
        tips=tips,
        images=_extract_images(md, source_id),
        source_id=source_id,
    )


def parse_tip_markdown(md: str, *, category: str = "", source_id: str = "") -> HowToCookDish:
    """解析技巧 markdown → HowToCookDish(kind=tip)。正文整体作为 content。"""
    lines = md.splitlines()
    title = ""
    body_lines: list[str] = []
    in_body = False
    for raw in lines:
        stripped = raw.rstrip()
        if not title and stripped.startswith("# "):
            title = stripped.strip("#").strip()
            in_body = True
            continue
        if in_body:
            body_lines.append(stripped)
    return HowToCookDish(
        title=title or _fallback_title(source_id),
        kind="tip",
        category=category,
        content="\n".join(body_lines).strip(),
        summary="",  # 技巧的简介由 content 承担
        source_id=source_id,
    )


def _fallback_title(source_id: str) -> str:
    return Path(source_id).stem or "未命名"


def classify_category(rel_path: str) -> str:
    """按相对路径（dishes/aquatic/xxx.md）归类为中文分类。"""
    p = Path(rel_path)
    parts = p.parts
    if parts and parts[0] == "dishes" and len(parts) >= 2:
        return CATEGORY_MAP.get(parts[1], parts[1])
    if parts and parts[0] == "tips":
        return CATEGORY_MAP.get("/".join(parts[:2]), CATEGORY_MAP.get("tips", "厨房基础"))
    return ""
