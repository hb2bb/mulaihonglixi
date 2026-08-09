"""公共工具接口：健康检查等。"""
from fastapi import APIRouter

from core.exceptions import success_resp

router = APIRouter(prefix="/common", tags=["公共"])


@router.get("/health")
async def health():
    """健康检查端点。"""
    return success_resp(data={"status": "healthy"})


__all__ = ["router"]
