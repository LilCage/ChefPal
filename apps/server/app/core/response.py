"""统一响应结构与业务异常。契约：{ code, message, data }。"""

from typing import Any


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """成功响应：code=0。"""
    return {"code": 0, "message": message, "data": data}


def fail(code: int, message: str, data: Any = None) -> dict[str, Any]:
    """失败响应：code != 0。"""
    return {"code": code, "message": message, "data": data}


class AppError(Exception):
    """业务异常，由全局异常处理器转成统一 JSON 响应。"""

    def __init__(self, message: str, *, code: int = 400, status_code: int = 400, data: Any = None):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.data = data
        super().__init__(message)
