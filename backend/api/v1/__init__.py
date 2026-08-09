"""API v1 路由聚合，统一挂载 /api/v1 前缀。"""
from fastapi import APIRouter

from api.v1 import chat, common, user

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat.router, tags=["对话"])
api_router.include_router(user.router, tags=["用户"])
api_router.include_router(common.router, tags=["公共"])

__all__ = ["api_router"]
