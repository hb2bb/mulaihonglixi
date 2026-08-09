"""全局中间件：CORS、请求日志、异常捕获处理。"""
import time
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings
from core.exceptions import ApiResponse, BizException
from core.logger import logger


def setup_middlewares(app: FastAPI) -> None:
    """注册所有全局中间件与异常处理器。"""

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # 请求日志中间件
    app.add_middleware(RequestLoggingMiddleware)

    # 异常处理器
    @app.exception_handler(BizException)
    async def biz_exception_handler(request: Request, exc: BizException):
        logger.warning(f"biz error: {request.method} {request.url.path} -> code={exc.code} msg={exc.msg}")
        resp = ApiResponse(code=exc.code, msg=exc.msg, data=exc.data)
        return JSONResponse(status_code=200, content=resp.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(f"validation error: {request.method} {request.url.path} -> {exc.errors()}")
        resp = ApiResponse(code=4001, msg="参数校验失败", data=exc.errors())
        return JSONResponse(status_code=200, content=resp.model_dump())

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            f"unhandled error: {request.method} {request.url.path} -> {exc}\n"
            f"{traceback.format_exc()}"
        )
        resp = ApiResponse(code=5000, msg="internal error", data=None)
        return JSONResponse(status_code=200, content=resp.model_dump())


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件：记录每个请求的 method、path、耗时。"""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        method = request.method
        path = request.url.path
        logger.info(f"-> {method} {path}")
        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.error(f"<- {method} {path} ERROR {elapsed_ms}ms: {exc}")
            raise
        elapsed_ms = int((time.time() - start) * 1000)
        logger.info(f"<- {method} {path} {response.status_code} {elapsed_ms}ms")
        return response


__all__ = ["setup_middlewares", "RequestLoggingMiddleware"]
