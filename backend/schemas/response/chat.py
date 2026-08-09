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


class ChatHistoryItem(BaseModel):
    """单条历史消息（用于历史记录分页展示）。"""

    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    datetime: str


class ChatHistoryData(BaseModel):
    """历史记录分页响应 data 字段结构。

    消息按时间正序返回（旧 -> 新），limit 表示每页条数。
    首次请求 offset=0 返回最新的一页；向上滚动时增大 offset 加载更早的消息。
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    messages: list[ChatHistoryItem]
    total: int
    offset: int
    limit: int
    has_more: bool
