"""对话请求模型。"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """POST /api/v1/chat 请求体。"""

    model_config = ConfigDict(from_attributes=True)

    message: str = Field(..., min_length=1, max_length=4000, description="用户消息内容")
    session_id: Optional[str] = Field(None, description="会话 ID，为空则后端生成新会话")
