"""用户模块接口（DEMO stub）：GET /user/profile 返回固定用户。"""
from fastapi import APIRouter

from core.exceptions import success_resp
from services.user_service import get_user_profile

router = APIRouter(prefix="/user", tags=["用户"])


@router.get("/profile")
async def get_profile():
    """获取当前用户信息（DEMO 阶段返回固定数据）。"""
    data = await get_user_profile()
    return success_resp(data=data)


__all__ = ["router"]
