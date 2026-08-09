"""日志统一封装：loguru 控制台 + 文件轮转，业务代码统一从此处导入 logger。"""
import sys

from loguru import logger

from core.config import settings


def setup_logger() -> None:
    """初始化日志配置：控制台彩色输出 + 文件按大小轮转。

    业务代码只需 `from core.logger import logger`，无需重复配置。
    """
    logger.remove()
    # 控制台输出
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>",
        colorize=True,
    )
    # 文件轮转：10MB/份，保留 7 天，UTF-8 编码
    log_dir = settings.log_path
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "app.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        enqueue=True,
    )


# 全局 logger 实例，供业务模块直接导入使用
__all__ = ["logger", "setup_logger"]
