"""ChefPal FastAPI 应用入口。"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.response import AppError, fail
from app.routers import (
    agents,
    auth,
    challenges,
    comments,
    cook_assistant,
    favorites,
    follows,
    fridge,
    my_recipes,
    plans,
    posts,
    qa,
    recipes,
    rescue,
    seasonal,
    shopping,
    users,
    vision,
    voice,
    votes,
)

settings = get_settings()

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

# 本地回落模式（COS 未配置时）静态图片目录；COS 配置后仍挂载，不影响测试
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=fail(exc.code, exc.message, exc.data))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content=fail(422, "参数校验失败", jsonable_encoder(exc.errors())))


@app.get("/api/health", tags=["system"])
async def health() -> dict:
    return {"code": 0, "message": "ok", "data": {"status": "up"}}


for router in (
    auth.router,
    users.router,
    qa.router,
    recipes.router,
    favorites.router,
    my_recipes.router,
    cook_assistant.router,
    posts.router,
    comments.router,
    plans.router,
    vision.router,
    shopping.router,
    seasonal.router,
    fridge.router,
    rescue.router,
    votes.router,
    voice.router,
    challenges.router,
    agents.router,
    follows.users_router,
    follows.follows_router,
):
    app.include_router(router, prefix=settings.API_PREFIX)
