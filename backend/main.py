"""项目入口：初始化 app、挂载路由、中间件、生命周期事件。

仅做装配，不写接口逻辑或业务逻辑。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.v1 import api_router
from core.config import settings
from core.dependencies import get_prompt_service
from core.logger import logger, setup_logger
from core.middlewares import setup_middlewares


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载 prompt，关闭时清理资源。"""
    setup_logger()
    logger.info("app starting, loading persona prompt...")
    prompt_service = get_prompt_service()
    await prompt_service.load()
    logger.info(f"app ready, persona loaded: {len(prompt_service.get_system_prompt())} chars")
    yield
    logger.info("app shutting down")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title="AI 女友 Demo",
        description="宁知夏 - AI 女友 DEMO 后端",
        version="0.1.0",
        lifespan=lifespan,
    )
    setup_middlewares(app)
    app.include_router(api_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
