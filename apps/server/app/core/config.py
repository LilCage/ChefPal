"""应用配置：从 .env 读取，集中管理所有环境变量。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- 应用 ----
    APP_NAME: str = "ChefPal API"
    APP_ENV: str = "dev"  # dev / test / prod
    DEBUG: bool = True
    API_PREFIX: str = "/api"

    # ---- 数据库 ----
    # 本地 docker compose 默认 5432（宿主原生 PG 已卸载，端口已空闲）
    DATABASE_URL: str = "postgresql+asyncpg://chefpal:chefpal_dev_password@localhost:5432/chefpal"
    TEST_DATABASE_URL: str = (
        "postgresql+asyncpg://chefpal:chefpal_dev_password@localhost:5432/chefpal_test"
    )

    # ---- 安全 ----
    JWT_SECRET: str = "dev-only-jwt-secret-change-me-in-prod-0123456789"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天

    # ---- 微信小程序 ----
    WECHAT_APPID: str = ""
    WECHAT_SECRET: str = ""
    WECHAT_CODE2SESSION_URL: str = "https://api.weixin.qq.com/sns/jscode2session"

    # ---- 阿里云百炼 DeepSeek ----
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_MODEL_PRO: str = "deepseek-v4-pro"
    AI_ENABLE_SEARCH: bool = True
    AI_TIMEOUT_SECONDS: float = 60.0
    AI_MAX_RETRIES: int = 1

    # ---- 智谱 GLM 视觉（拍照识食材，免费模型）----
    # 与百炼独立；未配置时视觉识别接口返回清晰错误，不影响其他功能
    ZHIPU_API_KEY: str = ""
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_VISION_MODEL: str = "glm-4v-flash"

    # ---- 风控 ----
    DAILY_AI_LIMIT: int = 20

    # ---- 腾讯云 COS（社区作品图片存储）----
    # 未配置任何一项则自动回落本地磁盘（uploads/ + /static），便于本地开发与测试。
    # 存储桶建议开启公有读（或 CDN/自定义域名），小程序端通过公网 URL 展示图片。
    COS_SECRET_ID: str = ""
    COS_SECRET_KEY: str = ""
    COS_REGION: str = ""
    COS_BUCKET: str = ""
    # 本地回落模式的上传目录（相对后端运行目录；FastAPI StaticFiles 挂载到 /static）
    UPLOAD_DIR: str = "uploads"

    # ---- CORS ----
    CORS_ORIGINS: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
