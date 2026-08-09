"""图片存储抽象：腾讯云 COS 优先，未配置则回落本地磁盘（uploads/ + /static）。

- `parse_data_url`：校验并解析 `data:image/...;base64,` → (mime, bytes)，限制类型与单张大小。
- `save_image`：按当前配置上传到 COS 或本地，返回可公开访问的 URL。
- `delete_image`：按 URL 清理本地文件（COS 对象删除暂留待后续）。

测试无需联网：单测直接测 `parse_data_url`；路由层通过 monkeypatch `save_image` 返回假 URL。
"""
import base64
import os
import re
import uuid
from pathlib import Path

from app.core.config import get_settings

ALLOWED_MIME: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
# 单张图片上限（base64 解码后字节数）
MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2MB
MAX_IMAGES_PER_POST = 9


class StorageError(Exception):
    """图片存储/校验失败。"""


def parse_data_url(data_url: str) -> tuple[str, bytes]:
    """校验并解析 data URL → (mime, bytes)。非法类型/超限抛 StorageError。"""
    m = re.match(r"^data:(image/\w+);base64,([A-Za-z0-9+/=]+)$", data_url.strip())
    if not m:
        raise StorageError("图片必须是 data:image/...;base64 形式")
    mime, b64 = m.group(1), m.group(2)
    if mime not in ALLOWED_MIME:
        raise StorageError("仅支持 jpeg/png/webp 图片")
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:  # noqa: BLE001
        raise StorageError("图片 base64 解码失败") from exc
    if not raw:
        raise StorageError("图片内容为空")
    if len(raw) > MAX_IMAGE_BYTES:
        raise StorageError("单张图片不能超过 2MB")
    return mime, raw


def cos_configured() -> bool:
    """COS 四项配置是否齐全。"""
    s = get_settings()
    return bool(s.COS_SECRET_ID and s.COS_SECRET_KEY and s.COS_REGION and s.COS_BUCKET)


def _save_to_cos(key: str, raw: bytes, mime: str) -> str:
    from qcloud_cos import CosConfig, CosS3Client  # 惰性导入：未配置 COS 时无需安装

    s = get_settings()
    config = CosConfig(Region=s.COS_REGION, SecretId=s.COS_SECRET_ID, SecretKey=s.COS_SECRET_KEY)
    client = CosS3Client(config, retry=3)
    client.put_object(Bucket=s.COS_BUCKET, Key=key, Body=raw, ContentType=mime)
    return f"https://{s.COS_BUCKET}.cos.{s.COS_REGION}.myqcloud.com/{key}"


def _save_to_local(key: str, raw: bytes) -> str:
    s = get_settings()
    path = Path(s.UPLOAD_DIR) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)
    return f"/static/{key}"


def save_image(data_url: str) -> str:
    """校验并保存一张图片，返回可访问 URL。"""
    mime, raw = parse_data_url(data_url)
    key = f"posts/{uuid.uuid4().hex}.{ALLOWED_MIME[mime]}"
    if cos_configured():
        return _save_to_cos(key, raw, mime)
    return _save_to_local(key, raw)


def save_images(data_urls: list[str]) -> list[str]:
    """批量保存图片（≤ MAX_IMAGES_PER_POST 张），失败则回滚已上传并抛错。"""
    if not 1 <= len(data_urls) <= MAX_IMAGES_PER_POST:
        raise StorageError(f"图片数量需在 1~{MAX_IMAGES_PER_POST} 张之间")
    urls: list[str] = []
    try:
        for url in data_urls:
            urls.append(save_image(url))
    except Exception:
        # 回滚本次已保存的图片，避免残留孤儿文件
        for u in urls:
            delete_image(u)
        raise
    return urls


def delete_image(url: str) -> None:
    """按 URL 删除本地磁盘图片（COS 删除待后续实现）。"""
    if not url.startswith("/static/"):
        return
    s = get_settings()
    rel = url.removeprefix("/static/")
    if "/" in rel and not rel.startswith("posts/"):
        return  # 仅允许清理 uploads/posts/ 下文件，防路径穿越
    try:
        path = Path(s.UPLOAD_DIR) / rel
        if path.is_file() and path.resolve().is_relative_to(Path(s.UPLOAD_DIR).resolve()):
            os.remove(path)
    except OSError:
        pass
