"""时令食材日历：按月份返回当季食材与推荐搭配（原型 05 屏3）。

纯静态数据（无 AI、无数据库），基于中国主流时令常识。
每项结构：{ name, emoji, level: "应季"|"正当时", note }
pairing：{ ingredients: [..], dish, note } 推荐搭配，食材应出现在当月 items 中。
"""
from datetime import datetime

# month -> { label, season, items, pairing }
SEASONAL = {
    1: {
        "label": "1 月 · 深冬",
        "items": [
            {"name": "白菜", "emoji": "🥬", "level": "应季", "note": "耐寒易储"},
            {"name": "萝卜", "emoji": "🥕", "level": "应季", "note": "清甜水润"},
            {"name": "冬笋", "emoji": "🎍", "level": "应季", "note": "鲜嫩脆爽"},
            {"name": "莲藕", "emoji": "🪷", "level": "应季", "note": "粉糯微甜"},
            {"name": "羊肉", "emoji": "🍖", "level": "应季", "note": "温补驱寒"},
            {"name": "柑橘", "emoji": "🍊", "level": "正当时", "note": "酸甜多汁"},
        ],
        "pairing": {
            "ingredients": ["白菜", "羊肉"],
            "dish": "羊肉炖白菜",
            "note": "1 月正当季 · 暖身一锅端",
        },
    },
    2: {
        "label": "2 月 · 早春",
        "items": [
            {"name": "菠菜", "emoji": "🥬", "level": "应季", "note": "叶嫩根甜"},
            {"name": "韭菜", "emoji": "🌱", "level": "应季", "note": "春韭最香"},
            {"name": "春笋", "emoji": "🎍", "level": "应季", "note": "鲜嫩少渣"},
            {"name": "草莓", "emoji": "🍓", "level": "应季", "note": "香甜红润"},
            {"name": "豌豆尖", "emoji": "🫛", "level": "应季", "note": "清甜回甘"},
            {"name": "鲈鱼", "emoji": "🐟", "level": "正当时", "note": "肉质细嫩"},
        ],
        "pairing": {
            "ingredients": ["春笋", "猪肉"],
            "dish": "油焖春笋",
            "note": "2 月正当季 · 爽脆开胃",
        },
    },
    3: {
        "label": "3 月 · 仲春",
        "items": [
            {"name": "荠菜", "emoji": "🌿", "level": "应季", "note": "山野清香"},
            {"name": "香椿", "emoji": "🌳", "level": "应季", "note": "一年一遇"},
            {"name": "蚕豆", "emoji": "🫛", "level": "应季", "note": "粉糯清甜"},
            {"name": "青团艾草", "emoji": "🍡", "level": "应季", "note": "时令点心"},
            {"name": "河虾", "emoji": "🦐", "level": "应季", "note": "壳薄肉嫩"},
            {"name": "菠萝", "emoji": "🍍", "level": "正当时", "note": "酸甜香浓"},
        ],
        "pairing": {
            "ingredients": ["香椿", "鸡蛋"],
            "dish": "香椿炒蛋",
            "note": "3 月正当季 · 错过等一年",
        },
    },
    4: {
        "label": "4 月 · 暮春",
        "items": [
            {"name": "豌豆", "emoji": "🫛", "level": "应季", "note": "鲜嫩清甜"},
            {"name": "芦笋", "emoji": "💚", "level": "应季", "note": "清脆多汁"},
            {"name": "马兰头", "emoji": "🌿", "level": "应季", "note": "清爽微苦"},
            {"name": "樱桃", "emoji": "🍒", "level": "应季", "note": "红润多汁"},
            {"name": "蚕豆米", "emoji": "🫛", "level": "正当时", "note": "粉糯入口"},
            {"name": "鳜鱼", "emoji": "🐟", "level": "正当时", "note": "桃花鳜鱼肥"},
        ],
        "pairing": {
            "ingredients": ["豌豆", "虾仁"],
            "dish": "豌豆炒虾仁",
            "note": "4 月正当季 · 鲜上加鲜",
        },
    },
    5: {
        "label": "5 月 · 初夏",
        "items": [
            {"name": "枇杷", "emoji": "🍋", "level": "应季", "note": "金黄甜润"},
            {"name": "桑葚", "emoji": "🫐", "level": "应季", "note": "紫黑酸甜"},
            {"name": "土豆", "emoji": "🥔", "level": "应季", "note": "粉糯绵密"},
            {"name": "蚕豆", "emoji": "🫛", "level": "应季", "note": "正当季"},
            {"name": "黄瓜", "emoji": "🥒", "level": "正当时", "note": "脆嫩清香"},
            {"name": "蒜薹", "emoji": "🧄", "level": "应季", "note": "爽脆微辣"},
        ],
        "pairing": {
            "ingredients": ["土豆", "鸡翅"],
            "dish": "可乐土豆鸡翅",
            "note": "5 月正当季 · 一锅满足",
        },
    },
    6: {
        "label": "6 月 · 盛夏",
        "items": [
            {"name": "荔枝", "emoji": "🍒", "level": "应季", "note": "晶莹剔透"},
            {"name": "杨梅", "emoji": "🍓", "level": "应季", "note": "酸甜爆汁"},
            {"name": "苦瓜", "emoji": "🥒", "level": "应季", "note": "清热解暑"},
            {"name": "冬瓜", "emoji": "🥒", "level": "应季", "note": "清润化湿"},
            {"name": "丝瓜", "emoji": "🥒", "level": "应季", "note": "滑嫩多汁"},
            {"name": "空心菜", "emoji": "🥬", "level": "应季", "note": "爽脆清香"},
        ],
        "pairing": {
            "ingredients": ["苦瓜", "鸡蛋"],
            "dish": "苦瓜炒蛋",
            "note": "6 月正当季 · 解暑不苦口",
        },
    },
    7: {
        "label": "7 月 · 盛夏",
        "items": [
            {"name": "西瓜", "emoji": "🍉", "level": "应季", "note": "沙瓤多汁"},
            {"name": "毛豆", "emoji": "🫛", "level": "应季", "note": "清香粉糯"},
            {"name": "莲子", "emoji": "🪷", "level": "应季", "note": "清心降火"},
            {"name": "茄子", "emoji": "🍆", "level": "正当时", "note": "肉厚软糯"},
            {"name": "绿豆", "emoji": "🫘", "level": "应季", "note": "清热解暑"},
            {"name": "黄鳝", "emoji": "🐟", "level": "应季", "note": "小暑黄鳝赛人参"},
        ],
        "pairing": {
            "ingredients": ["茄子", "土豆"],
            "dish": "地三鲜",
            "note": "7 月正当季 · 下饭王者",
        },
    },
    8: {
        "label": "8 月 · 盛夏",
        "items": [
            {"name": "番茄", "emoji": "🍅", "level": "应季", "note": "酸甜多汁"},
            {"name": "黄瓜", "emoji": "🥒", "level": "应季", "note": "清火解腻"},
            {"name": "茄子", "emoji": "🍆", "level": "应季", "note": "肉厚软糯"},
            {"name": "玉米", "emoji": "🌽", "level": "应季", "note": "鲜甜爆汁"},
            {"name": "基围虾", "emoji": "🦐", "level": "应季", "note": "肉质紧实"},
            {"name": "水蜜桃", "emoji": "🍑", "level": "正当时", "note": "香气浓郁"},
        ],
        "pairing": {
            "ingredients": ["黄瓜", "基围虾"],
            "dish": "虾仁凉拌黄瓜",
            "note": "8 月正当季 · 10 分钟快手 · 清爽开胃",
        },
    },
    9: {
        "label": "9 月 · 初秋",
        "items": [
            {"name": "南瓜", "emoji": "🎃", "level": "应季", "note": "粉糯香甜"},
            {"name": "莲藕", "emoji": "🪷", "level": "应季", "note": "清甜脆嫩"},
            {"name": "柚子", "emoji": "🍊", "level": "应季", "note": "清香微苦"},
            {"name": "石榴", "emoji": "🍎", "level": "应季", "note": "籽粒晶莹"},
            {"name": "芋头", "emoji": "🥔", "level": "应季", "note": "软糯绵密"},
            {"name": "螃蟹", "emoji": "🦀", "level": "正当时", "note": "九月圆脐十月尖"},
        ],
        "pairing": {
            "ingredients": ["莲藕", "排骨"],
            "dish": "莲藕排骨汤",
            "note": "9 月正当季 · 清润入秋",
        },
    },
    10: {
        "label": "10 月 · 深秋",
        "items": [
            {"name": "柿子", "emoji": "🍅", "level": "应季", "note": "红软甜糯"},
            {"name": "板栗", "emoji": "🌰", "level": "应季", "note": "香甜粉糯"},
            {"name": "山药", "emoji": "🥔", "level": "应季", "note": "健脾养胃"},
            {"name": "芹菜", "emoji": "🥬", "level": "应季", "note": "脆嫩清香"},
            {"name": "红薯", "emoji": "🍠", "level": "应季", "note": "流蜜软糯"},
            {"name": "大闸蟹", "emoji": "🦀", "level": "应季", "note": "膏满黄肥"},
        ],
        "pairing": {
            "ingredients": ["板栗", "鸡"],
            "dish": "板栗烧鸡",
            "note": "10 月正当季 · 深秋暖锅",
        },
    },
    11: {
        "label": "11 月 · 初冬",
        "items": [
            {"name": "白萝卜", "emoji": "🥕", "level": "应季", "note": "清甜多汁"},
            {"name": "西兰花", "emoji": "🥦", "level": "应季", "note": "爽脆营养"},
            {"name": "冬枣", "emoji": "🍎", "level": "应季", "note": "嘎嘣脆甜"},
            {"name": "金橘", "emoji": "🍊", "level": "应季", "note": "皮甜肉酸"},
            {"name": "白菜", "emoji": "🥬", "level": "正当时", "note": "清甜耐寒"},
            {"name": "带鱼", "emoji": "🐟", "level": "应季", "note": "肉质紧实"},
        ],
        "pairing": {
            "ingredients": ["白萝卜", "羊肉"],
            "dish": "白萝卜羊肉汤",
            "note": "11 月正当季 · 暖身滋补",
        },
    },
    12: {
        "label": "12 月 · 深冬",
        "items": [
            {"name": "冬笋", "emoji": "🎍", "level": "应季", "note": "鲜嫩清甜"},
            {"name": "塔菜", "emoji": "🥬", "level": "应季", "note": "霜打更甜"},
            {"name": "荸荠", "emoji": "🟤", "level": "应季", "note": "清甜脆爽"},
            {"name": "金针菇", "emoji": "🍄", "level": "应季", "note": "鲜滑爽口"},
            {"name": "牛肉", "emoji": "🥩", "level": "正当时", "note": "暖身滋补"},
            {"name": "苹果", "emoji": "🍎", "level": "应季", "note": "脆甜多汁"},
        ],
        "pairing": {
            "ingredients": ["冬笋", "咸肉"],
            "dish": "腌笃鲜",
            "note": "12 月正当季 · 江浙一绝",
        },
    },
}


def get_month(month: int | None = None) -> dict:
    """返回指定月份（1-12）的时令数据；不传默认当前月。"""
    if month is None:
        month = datetime.now().month
    month = max(1, min(12, month))
    data = dict(SEASONAL[month])
    data["month"] = month
    return data
