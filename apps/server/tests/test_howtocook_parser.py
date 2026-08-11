"""HowToCook markdown 解析器测试：菜谱/技巧 → 结构化条目。"""
import pytest

from app.services.howtocook.parser import (
    classify_category,
    parse_dish_markdown,
    parse_tip_markdown,
)

LIANG_BAN_HUANG_GUA = """# 凉拌黄瓜的做法

这是一道清爽开胃的家常凉菜，口感脆嫩，酸香适口。黄瓜富含水分和维生素。

预估烹饪难度：★

预估卡路里：107 大卡

## 必备原料和工具

* 黄瓜
* 醋
* 酱油
* 蒜

## 计算

每次制作前需要确定计划做几份。一份正好够 1 个人食用

## 操作

1. 用菜刀将黄瓜拍扁，再剁成长 3 厘米的碎块
2. 将碎黄瓜装入碗中
3. 将醋，酱油，盐，蚝油和蒜依次倒入碗中搅拌均匀

## 附加内容

* 部分情况下黄瓜端头有苦味，请洗净切下后确认
* 做好之后直接开吃，亦可放入冰箱冷藏后食用

## 成品图

![凉拌黄瓜](images/liangban-huanggua.jpg)
"""

TIPS_QUXING = """# 去腥

大部分腥味来自动物蛋白的分解产物或脂肪氧化。

## 焯水去腥

* 冷水下锅，逐渐升温
* 血沫浮起后撇净

## 腌制去腥

* 料酒或白胡椒
* 葱姜蒜
"""


def test_parse_dish_basic():
    d = parse_dish_markdown(LIANG_BAN_HUANG_GUA, category="素菜", source_id="dishes/vegetable_dish/凉拌黄瓜.md")
    assert d.kind == "recipe"
    assert d.title == "凉拌黄瓜"
    assert d.category == "素菜"
    assert d.difficulty == "简单"
    assert d.calories == "107 大卡"
    assert d.ingredients == ["黄瓜", "醋", "酱油", "蒜"]
    assert len(d.steps) == 3
    assert d.steps[0] == "1. 用菜刀将黄瓜拍扁，再剁成长 3 厘米的碎块"
    assert d.tips == [
        "部分情况下黄瓜端头有苦味，请洗净切下后确认",
        "做好之后直接开吃，亦可放入冰箱冷藏后食用",
    ]
    # 简介取标题与第一个小节之间的段落
    assert "清爽开胃" in d.summary
    # 成品图/计算小节被忽略
    assert "计算" not in d.summary


def test_parse_dish_difficulty_stars():
    md = "# 红烧肉的做法\n\n预估烹饪难度：★★★\n\n## 操作\n\n1. 焯水"
    d = parse_dish_markdown(md)
    assert d.difficulty == "较难"


def test_parse_dish_title_suffix_variants():
    assert parse_dish_markdown("# 西红柿炒鸡蛋的做法\n\n## 操作\n\n1. 打蛋").title == "西红柿炒鸡蛋"
    assert parse_dish_markdown("# 鸡蛋羹\n\n## 操作\n\n1. 蒸").title == "鸡蛋羹"


def test_parse_extracts_images_with_posix_path():
    """成品图相对路径解析为仓库内正斜杠路径（Windows 反斜杠会破坏图片 URL）。"""
    md = "# 简易红烧肉的做法\n\n简介。\n\n![红烧肉成品](./000.jpg)\n\n![成品](./001.jpg)\n\n## 操作\n\n1. 切肉\n"
    d = parse_dish_markdown(md, source_id="dishes/meat_dish/红烧肉/简易红烧肉.md")
    assert d.images == ["dishes/meat_dish/红烧肉/000.jpg", "dishes/meat_dish/红烧肉/001.jpg"]
    assert "\\" not in d.images[0]  # 必须正斜杠


def test_parse_dish_missing_sections_ok():
    d = parse_dish_markdown("# 烤红薯的做法\n\n烤到流糖。\n\n## 操作\n\n1. 烤箱 200 度 40 分钟")
    assert d.title == "烤红薯"
    assert d.ingredients == []
    assert d.tips == []
    assert len(d.steps) == 1


def test_parse_tip():
    d = parse_tip_markdown(TIPS_QUXING, category="新手技巧", source_id="tips/learn/去腥.md")
    assert d.kind == "tip"
    assert d.title == "去腥"
    assert "焯水去腥" in d.content
    assert "料酒或白胡椒" in d.content
    # 技巧条目不产出结构化步骤
    assert d.steps == []
    assert d.ingredients == []


def test_classify_category():
    assert classify_category("dishes/meat_dish/红烧肉.md") == "肉菜"
    assert classify_category("dishes/vegetable_dish/凉拌黄瓜.md") == "素菜"
    assert classify_category("dishes/soup/番茄蛋汤.md") == "汤"
    assert classify_category("dishes/staple/扬州炒饭.md") == "主食"
    assert classify_category("tips/learn/去腥.md") == "新手技巧"
    assert classify_category("tips/advanced/火候.md") == "进阶技巧"
    assert classify_category("tips/厨房准备.md") == "厨房基础"
    assert classify_category("unknown/x.md") == ""


# ---------- 真实格式：成品图 + 主料/辅料反引号 + 注/工具元信息 ----------

REAL_RED_BRAISED = """# 简易红烧肉的做法

这道家常美味色泽红润油亮，口感软糯，肥而不腻，搭配米饭特别过瘾。从备料到出锅大约需要 1.5 小时。

![红烧肉成品](./000.jpg)

![红烧肉成品](./001.jpg)

预估烹饪难度：★★★

预估卡路里：2775 大卡

## 必备原料和工具

- 注：如果有可能，请尽量把刀磨的锋利一些。
- 主料：`大肉`、`鸡蛋`（可选）、`豆皮`（可选）
- 辅料：`生姜`、`冰糖`、`生抽`、`老抽`、`料酒`、`香叶`、`八角`、`盐`、`水`、`葱`（记得要开水）

## 计算

猪五花肉：约 3~4 斤

## 操作

### 原材料准备

1. `猪五花肉`切大块（约 4.5cm）
2. `生姜`切片
3. `水`烧开

## 附加内容

* 小火慢炖，避免糊锅
"""


def test_parse_real_format_strips_images_and_meta():
    d = parse_dish_markdown(REAL_RED_BRAISED, category="肉菜")
    assert d.title == "简易红烧肉"
    # 简介不含图片 markdown
    assert "![红烧肉成品]" not in d.summary
    assert "色泽红润油亮" in d.summary
    assert "1.5 小时" in d.summary
    # 食材：主料/辅料顿号拆分、去反引号、跳过 注/工具
    assert "注：如果有可能" not in d.ingredients
    assert "大肉" in d.ingredients
    assert "鸡蛋（可选）" in d.ingredients
    assert "生姜" in d.ingredients
    assert "葱（记得要开水）" in d.ingredients
    assert all("`" not in ing for ing in d.ingredients)
    # 步骤去反引号保留
    assert d.steps[0] == "1. 猪五花肉切大块（约 4.5cm）"
    # 附加内容保留
    assert d.tips == ["小火慢炖，避免糊锅"]


def test_parse_splits_steps_by_subsection():
    """有 ### 子节（原材料准备/开始制作）时按子节切分食材处理/烹饪步骤。"""
    md = """# 简易红烧肉的做法

## 操作

### 原材料准备

1. `猪五花肉`切大块
2. `生姜`切片

### 开始制作

1. 冷水下锅煮 15 分钟
2. 炒糖色
"""
    d = parse_dish_markdown(md)
    assert d.prep_steps == ["1. 猪五花肉切大块", "2. 生姜切片"]
    assert d.cook_steps == ["1. 冷水下锅煮 15 分钟", "2. 炒糖色"]
    # steps = 合并的全量列表
    assert d.steps == d.prep_steps + d.cook_steps


def test_parse_splits_steps_by_heuristic_without_subsection():
    """无子节的扁平菜谱：按关键词切分（切/洗/腌→食材处理，炒/煮→烹饪）。"""
    md = """# 凉拌黄瓜的做法

## 操作

1. 用菜刀将黄瓜拍扁，剁成块
2. 将蒜拍碎切成末
3. 将醋酱油蒜倒入碗中搅拌均匀
4. 放入白糖腌制 15 分钟
"""
    d = parse_dish_markdown(md)
    # 切/拍/腌制 → prep（"放入白糖腌制"含腌制动作、无强烹饪动词 → prep）
    assert d.prep_steps == [
        "1. 用菜刀将黄瓜拍扁，剁成块",
        "2. 将蒜拍碎切成末",
        "4. 放入白糖腌制 15 分钟",
    ]
    # "倒入碗中搅拌均匀"无强处理/烹饪动词 → 默认 cook
    assert len(d.cook_steps) == 1
    assert "倒入碗中搅拌均匀" in d.cook_steps[0]
