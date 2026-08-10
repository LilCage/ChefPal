"""百炼语音识别服务：音频转文字（OpenAI 兼容接口，同步返回）。

用 qwen3-asr-flash 模型 + input_audio 消息（音频 base64 data URI）做一句话识别，
无需 websocket / 异步轮询，复用项目已有的 openai 客户端与 DASHSCOPE_BASE_URL。
"""
import base64

from openai import AsyncOpenAI

from app.core.config import get_settings

settings = get_settings()


class ASRError(Exception):
    """语音识别失败。"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        timeout=settings.AI_TIMEOUT_SECONDS,
    )


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/mpeg") -> str:
    """将音频字节转写为文字；无识别内容时抛 ASRError。"""
    if not settings.DASHSCOPE_API_KEY:
        raise ASRError("未配置 DASHSCOPE_API_KEY，请先在 apps/server/.env 中填入")
    if not audio_bytes:
        raise ASRError("音频为空")

    data_uri = f"data:{mime_type};base64," + base64.b64encode(audio_bytes).decode()
    messages = [
        {
            "role": "user",
            "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}],
        }
    ]

    try:
        resp = await _client().chat.completions.create(
            model=settings.BAILIAN_ASR_MODEL,
            messages=messages,
            extra_body={"asr_options": {"enable_itn": True}},
        )
    except Exception as exc:  # noqa: BLE001
        raise ASRError(f"语音识别调用失败: {exc}") from exc

    text = (resp.choices[0].message.content or "").strip()
    # 过滤纯语气词/静音噪音（如"嗯""啊"），避免切出垃圾食材
    if not text or text in {"嗯", "嗯。", "啊", "哦", "好的", "呃", "嗯嗯"}:
        raise ASRError("未识别到语音内容，请再说一次")
    return text
