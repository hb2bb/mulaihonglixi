"""用户服务 stub：DEMO 阶段返回固定用户信息，后续接入数据库时补全。"""
from typing import Any


async def get_user_profile(user_id: str = "demo-user") -> dict[str, Any]:
    """返回用户信息（DEMO 阶段固定返回）。"""
    return {
        "user_id": user_id,
        "nickname": "demo",
        "avatar": "",
    }


__all__ = ["get_user_profile"]
