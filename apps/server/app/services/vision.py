"""智谱 GLM 视觉识别：拍照识食材（免费模型，OpenAI 兼容多模态）。

- 走 `AsyncOpenAI(api_key=ZHIPU_API_KEY, base_url=ZHIPU_BASE_URL)` 发多模态消息
- 消息 content 数组含 image_url（data:image/...;base64,）与 text 提示词
- 提示词要求输出 JSON {"ingredients": [...]}，用 client._extract_json 兜底解析
"""
import json

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.llm.client import _extract_json

settings = get_settings()

RECOGNIZE_PROMPT = (
    "你是一个食材识别助手。识别这张厨房照片中的每一种可食用食材，"
    "只输出 JSON，格式：{\"ingredients\": [\"西红柿\", \"鸡蛋\", \"生菜\"]}。"
    "要求：1) 每项用中文名；2) 去掉重复项；3) 只列出能明确识别出的食材，不确定的宁可少列；"
    "4) 只输出 JSON，不要多余文字。"
)

DIAGNOSE_PROMPT = (
    "你是一位耐心的中式家常菜补救专家。用户上传了做菜的翻车现场照片（成品或半成品），"
    "请从照片中判断最可能的 1~3 个问题，并给出具体、可执行的补救方案。"
    "只输出 JSON，格式：{\"issues\": [{\"title\": \"问题名\", \"detail\": \"为什么会这样（简短）\", \"fix\": \"补救方案（具体做法）\"}]}。"
    "要求：1) 每条 fix 是一条明确的补救动作，不要用'建议'开头；"
    "2) 如果照片没有明显翻车迹象，issues 返回空数组；"
    "3) 只输出 JSON，不要多余文字。"
)


async def _chat_vision(image_data_url: str, prompt: str) -> dict:
    """通用 GLM-4v 多模态调用：发图 + 提示词 → 解析 JSON 对象。

    未配置 ZHIPU_API_KEY 时抛 VisionError。返回解析后的 dict（调用方负责字段校验）。
    """
    if not settings.ZHIPU_API_KEY:
        raise VisionError("未配置 ZHIPU_API_KEY，请先在 apps/server/.env 中填入智谱 Key")

    client = _client()
    messages = [
        {"role": "system", "content": "你是视觉识别助手，严格按用户要求的格式输出。"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": prompt},
            ],
        },
    ]
    try:
        resp = await client.chat.completions.create(
            model=settings.ZHIPU_VISION_MODEL,
            messages=messages,
            max_tokens=1024,  # glm-4v-flash 的 max_tokens 上限是 1024
        )
    except Exception as exc:  # noqa: BLE001
        raise VisionError(f"视觉识别调用失败: {exc}") from exc

    content = resp.choices[0].message.content or ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        try:
            data = json.loads(_extract_json(content))
        except Exception as exc:  # noqa: BLE001
            raise VisionError("视觉识别结果解析失败，请重试") from exc

    if not isinstance(data, dict):
        raise VisionError("视觉识别结果格式异常，请重试")
    return data


class VisionError(Exception):
    """视觉识别调用/解析失败。"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.ZHIPU_API_KEY,
        base_url=settings.ZHIPU_BASE_URL,
        timeout=settings.AI_TIMEOUT_SECONDS,
    )


async def recognize_ingredients(image_data_url: str) -> list[str]:
    """识别图片中的食材，返回去重后的中文名列表。

    未配置 ZHIPU_API_KEY 时抛 VisionError（提示先填 .env），便于本地 mock 测试与集成测试区分。
    """
    data = await _chat_vision(image_data_url, RECOGNIZE_PROMPT)
    raw = data.get("ingredients")
    if not isinstance(raw, list):
        raise VisionError("视觉识别结果格式异常，请重试")

    # 清洗：去空白/去重/限长/限数量
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in raw:
        name = str(item).strip()
        if name and name not in seen and len(name) <= 20:
            seen.add(name)
            cleaned.append(name)
        if len(cleaned) >= 30:
            break
    return cleaned


async def diagnose_dish(image_data_url: str) -> dict:
    """黑暗料理拯救：诊断翻车现场照片，返回 {"issues": [{title, detail, fix}]}。

    未配置 ZHIPU_API_KEY 时抛 VisionError。
    """
    data = await _chat_vision(image_data_url, DIAGNOSE_PROMPT)
    issues = data.get("issues")
    if not isinstance(issues, list):
        raise VisionError("视觉识别结果格式异常，请重试")

    cleaned: list[dict] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        fix = str(item.get("fix") or "").strip()
        if title and detail and fix:
            cleaned.append({"title": title, "detail": detail, "fix": fix})
        if len(cleaned) >= 3:
            break
    return {"issues": cleaned}
