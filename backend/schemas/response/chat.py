"""对话响应模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ChatResponseData(BaseModel):
    """对话响应 data 字段结构。"""

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    reply: str
    datetime: datetime


class ChatStreamChunk(BaseModel):
    """流式对话单个 chunk 的结构（SSE data 字段）。"""

    model_config = ConfigDict(from_attributes=True)

    chunk: Optional[str] = None
    done: bool = False
    reply: Optional[str] = None
    session_id: Optional[str] = None
    datetime: Optional[str] = None
    error: Optional[str] = None
