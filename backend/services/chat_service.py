"""对话业务编排：取历史 -> 拼消息 -> 调 LLM -> 存历史 -> 返回。

禁止在路由层写复杂业务，所有对话逻辑集中在此处。
聊天历史存 json 文件，按 session_id 分文件。
"""
import asyncio
import json
import random
from pathlib import Path
from typing import AsyncIterator, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from core.config import settings
from core.exceptions import HistoryPersistError, SessionError
from core.logger import logger
from schemas.request.chat import ChatRequest
from schemas.response.chat import ChatResponseData
from services.llm_client import LLMClient
from services.prompt_service import PromptService
from tools.web_search_tool import (
    WebSearchTool,
    build_search_context,
    get_web_search_tool,
    pick_topic,
)
from utils.common import generate_session_id, is_valid_session_id, safe_history_path
from utils.datetime_util import now_dt, now_iso


class ChatService:
    """对话编排服务，依赖 LLMClient 和 PromptService。"""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_service: PromptService,
        history_dir: Path | None = None,
        web_search_tool: Optional[WebSearchTool] = None,
    ) -> None:
        self._llm_client: LLMClient = llm_client
        self._prompt_service: PromptService = prompt_service
        self._history_dir: Path = history_dir or settings.chat_history_path
        self._web_search_tool: Optional[WebSearchTool] = web_search_tool

    async def handle_chat(
        self,
        message: str,
        session_id: str | None,
    ) -> ChatResponseData:
        """非流式对话：完整返回一条回复。

        Args:
            message: 用户消息文本。
            session_id: 会话 ID，为空则生成新会话。

        Returns:
            ChatResponseData: 包含 session_id、reply、datetime。
        """
        session_id = self.resolve_session_id(session_id)
        history = await self._load_history(session_id)
        search_context = await self._maybe_search(message)
        messages = self._assemble_messages(history, message, search_context)
        reply = await self._llm_client.chat(messages)
        await self._persist_history(
            session_id,
            history,
            user_msg=message,
            assistant_msg=reply,
        )
        dt = now_dt()
        logger.info(
            f"chat done: session={session_id} reply_len={len(reply)} "
            f"history_len={len(history) + 2} search_ctx={len(search_context or '')}"
        )
        return ChatResponseData(session_id=session_id, reply=reply, datetime=dt)

    async def handle_chat_stream(
        self,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[str]:
        """流式对话：逐 chunk yield 回复片段，结束后持久化完整回复。

        Args:
            message: 用户消息文本。
            session_id: 会话 ID，为空则生成新会话。

        Yields:
            str: 回复片段（chunk）。
        """
        session_id = self.resolve_session_id(session_id)
        history = await self._load_history(session_id)
        search_context = await self._maybe_search(message)
        messages = self._assemble_messages(history, message, search_context)
        # 收集完整回复，流结束后持久化
        collected: list[str] = []
        async for chunk in self._llm_client.stream_chat(messages):
            collected.append(chunk)
            yield chunk
        full_reply = "".join(collected)
        await self._persist_history(
            session_id,
            history,
            user_msg=message,
            assistant_msg=full_reply,
        )
        logger.info(
            f"stream done: session={session_id} reply_len={len(full_reply)} "
            f"history_len={len(history) + 2} search_ctx={len(search_context or '')}"
        )

    def resolve_session_id(self, session_id: str | None) -> str:
        """校验或生成 session_id。"""
        if session_id is None or session_id == "":
            new_id = generate_session_id()
            logger.debug(f"generated new session_id: {new_id}")
            return new_id
        if not is_valid_session_id(session_id):
            logger.warning(f"invalid session_id received: {session_id}")
            raise SessionError(msg=f"session_id 格式非法: {session_id}")
        return session_id

    def _assemble_messages(
        self,
        history: list[dict],
        current_message: str,
    ) -> list[BaseMessage]:
        """组装 LangChain 消息列表：system + 历史 + 当前用户消息。

        Args:
            history: 历史记录列表，每项 {role, content, datetime}。
            current_message: 本次用户消息。

        Returns:
            list[BaseMessage]: LangChain 消息列表。
        """
        messages: list[BaseMessage] = [
            SystemMessage(content=self._prompt_service.get_system_prompt())
        ]
        for record in history:
            role = record.get("role", "")
            content = record.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=current_message))
        return messages

    async def _load_history(self, session_id: str) -> list[dict]:
        """从 json 文件加载聊天历史，文件不存在则返回空列表。"""
        self._history_dir.mkdir(parents=True, exist_ok=True)
        filepath = safe_history_path(self._history_dir, session_id)
        if not filepath.exists():
            return []
        # 用 to_thread 包装同步文件读取，避免阻塞事件循环
        data = await asyncio.to_thread(self._read_json_file, filepath)
        logger.debug(f"loaded history: session={session_id} records={len(data)}")
        return data

    async def list_session_ids(self) -> list[str]:
        """按最后修改时间倒序返回所有会话 ID（最新的在前）。

        用于进入页面时定位"最近会话"，或前端展示会话入口。
        """
        self._history_dir.mkdir(parents=True, exist_ok=True)
        files = [p for p in self._history_dir.glob("*.json") if p.is_file()]
        # 按 mtime 倒序
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.stem for p in files]

    async def load_history_page(
        self,
        session_id: str,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict], int, bool]:
        """分页加载历史消息（时间正序，旧 -> 新）。

        Args:
            session_id: 会话 ID。
            offset: 已从最新端跳过的条数（首次为 0，向上滚动后递增）。
            limit: 每页条数。

        Returns:
            (page, total, has_more)：page 为本页消息（正序），
            total 为历史总条数，has_more 表示是否还有更早的消息。
        """
        history = await self._load_history(session_id)
        total = len(history)
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        if offset >= total:
            return [], total, False
        # 从最新端往前取 limit 条
        end = total - offset
        start = max(0, end - limit)
        page = history[start:end]
        has_more = start > 0
        return page, total, has_more

    async def _persist_history(
        self,
        session_id: str,
        history: list[dict],
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """追加本次对话两条记录并写回 json 文件。"""
        self._history_dir.mkdir(parents=True, exist_ok=True)
        filepath = safe_history_path(self._history_dir, session_id)
        # 追加 user + assistant 两条
        history.append({"role": "user", "content": user_msg, "datetime": now_iso()})
        history.append(
            {"role": "assistant", "content": assistant_msg, "datetime": now_iso()}
        )
        try:
            await asyncio.to_thread(self._write_json_file, filepath, history)
            logger.debug(f"persisted history: session={session_id} records={len(history)}")
        except OSError as exc:
            logger.error(f"failed to persist history: session={session_id} err={exc}")
            raise HistoryPersistError(msg=f"历史写入失败: {exc}") from exc

    @staticmethod
    def _read_json_file(filepath: Path) -> list[dict]:
        """同步读取 json 文件（由 to_thread 调度）。"""
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, list):
            logger.warning(f"history file not a list, resetting: {filepath}")
            return []
        return data

    @staticmethod
    def _write_json_file(filepath: Path, data: list[dict]) -> None:
        """同步写入 json 文件（由 to_thread 调度）。"""
        text = json.dumps(data, ensure_ascii=False, indent=2)
        filepath.write_text(text, encoding="utf-8")


__all__ = ["ChatService"]
