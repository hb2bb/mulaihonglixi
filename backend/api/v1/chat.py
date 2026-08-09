"""对话模块接口：POST /chat 非流式，GET /chat/stream 流式 SSE。"""
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from core.exceptions import success_resp, ValidationError
from core.logger import logger
from schemas.request.chat import ChatRequest
from schemas.response.chat import ChatResponseData
from services.chat_service import ChatService
from utils.datetime_util import now_iso
from core.dependencies import get_chat_service

router = APIRouter(prefix="/chat", tags=["对话"])


@router.post("")
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
):
    """非流式对话：接收用户消息，返回完整回复。"""
    logger.info(f"POST /chat: session={request.session_id} msg_len={len(request.message)}")
    data: ChatResponseData = await chat_service.handle_chat(
        message=request.message,
        session_id=request.session_id,
    )
    return success_resp(data=data)


@router.get("/stream")
async def chat_stream(
    message: str = Query(..., min_length=1, max_length=4000, description="用户消息"),
    session_id: str | None = Query(None, description="会话 ID"),
    chat_service: ChatService = Depends(get_chat_service),
):
    """流式对话：SSE 逐 chunk 返回回复片段。

    SSE 协议：
    - chunk: data: {"chunk":"..."}\\n\\n
    - 结束: data: {"done":true,"reply":"...","session_id":"...","datetime":"..."}\\n\\n
    - 错误: data: {"error":"..."}\\n\\n
    """
    logger.info(
        f"GET /chat/stream: session={session_id} msg_len={len(message)}"
    )

    async def event_generator():
        try:
            # 先解析 session_id，用于在结束事件中返回
            resolved_sid = chat_service.resolve_session_id(session_id)
            collected: list[str] = []
            async for chunk in chat_service.handle_chat_stream(
                message=message,
                session_id=resolved_sid,
            ):
                collected.append(chunk)
                yield _sse_chunk({"chunk": chunk})
            full_reply = "".join(collected)
            yield _sse_done(
                reply=full_reply,
                session_id=resolved_sid,
                datetime=now_iso(),
            )
        except Exception as exc:
            logger.error(f"stream error: {exc}")
            yield _sse_error(str(exc))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_chunk(data: dict) -> str:
    """构造 chunk SSE 事件。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_done(reply: str, session_id: str, datetime: str) -> str:
    """构造结束 SSE 事件。"""
    payload = {
        "done": True,
        "reply": reply,
        "session_id": session_id,
        "datetime": datetime,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_error(msg: str) -> str:
    """构造错误 SSE 事件。"""
    return f"data: {json.dumps({'error': msg}, ensure_ascii=False)}\n\n"


__all__ = ["router"]
