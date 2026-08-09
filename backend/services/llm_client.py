"""LLM 客户端封装：定义 LLMClient 协议 + MockLLMClient 实现。

DEMO 阶段使用 MockLLMClient，返回符合宁知夏人格口吻的预置回复。
未来接入真实 LLM（Claude / DeepSeek 等）时，新增实现类并在
core/dependencies.py 中按 settings.llm_provider 切换即可。
"""
import asyncio
import random
from typing import AsyncIterator, Protocol, runtime_checkable

from langchain_core.messages import BaseMessage

from core.logger import logger


@runtime_checkable
class LLMClient(Protocol):
    """LLM 客户端协议：业务层只依赖此接口，不感知具体实现。"""

    async def chat(self, messages: list[BaseMessage]) -> str:
        """非流式对话，返回完整回复。"""
        ...

    async def stream_chat(self, messages: list[BaseMessage]) -> AsyncIterator[str]:
        """流式对话，逐 chunk 返回回复片段。"""
        ...


# ---- Mock 回复池（8-35 字，符合 persona spec）----
_GREETING_REPLIES: tuple[str, ...] = (
    "嗯，在的",
    "哟，来了",
    "嗯嗯，刚忙完",
    "在呢，怎么了",
    "来了来了，怎么了",
)

_CURIOUS_REPLIES: tuple[str, ...] = (
    "这个我还真不太清楚",
    "你猜",
    "嗯？为什么这么问",
    "我也不知道诶",
    "说起来我也不太懂",
)

_CARING_REPLIES: tuple[str, ...] = (
    "先歇会儿吧",
    "喝口水再继续",
    "别硬撑，早点睡",
    "今天怎么这么累",
    "嗯，先顾好自己",
)

_DEFAULT_REPLIES: tuple[str, ...] = (
    "行吧",
    "嗯，听到了",
    "然后呢",
    "你说得对",
    "真的假的",
    "好啦好啦",
    "欸，是吗",
    "我倒是没想到",
    "嗯，有点意思",
    "行，我记下了",
)

# 关键词路由规则（按顺序匹配，命中即停）
_ROUTING_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("你好", "嗨", "hello", "在吗", "在不在", "哈喽"), _GREETING_REPLIES),
    (("?", "？", "怎么", "为什么", "什么", "怎么办", "如何"), _CURIOUS_REPLIES),
    (("累", "烦", "困", "难过", "不开心", "emo", "崩溃"), _CARING_REPLIES),
)


class MockLLMClient:
    """Mock LLM 客户端：不接真实模型，按关键词路由返回预置回复。

    所有回复均符合宁知夏人格 spec：
    - 8-35 字
    - 无 AI/模型/系统/程序 元语言
    - 无括号舞台提示
    - 无 markdown 排版
    """

    def __init__(self) -> None:
        # 记录上次回复，避免连续重复
        self._last_reply: str = ""

    async def chat(self, messages: list[BaseMessage]) -> str:
        """根据最后一条用户消息路由到回复池，随机返回一条。"""
        user_text = self._extract_last_user_text(messages)
        reply = self._route_reply(user_text)
        logger.debug(
            f"mock chat: user_text='{user_text[:50]}' -> reply='{reply}' "
            f"(messages={len(messages)})"
        )
        return reply

    async def stream_chat(self, messages: list[BaseMessage]) -> AsyncIterator[str]:
        """流式返回：把完整回复切成 2-4 字的 chunk，带打字延迟。"""
        reply = self._route_reply(self._extract_last_user_text(messages))
        # 切 chunk：每 2-4 字一段，随机
        chunk_size = random.randint(2, 4)
        chunks = [reply[i : i + chunk_size] for i in range(0, len(reply), chunk_size)]
        if not chunks:
            chunks = [reply]
        logger.debug(f"mock stream: reply='{reply}' -> {len(chunks)} chunks")
        for chunk in chunks:
            await asyncio.sleep(random.uniform(0.1, 0.3))
            yield chunk

    def _extract_last_user_text(self, messages: list[BaseMessage]) -> str:
        """从消息列表中提取最后一条 HumanMessage 的文本内容。"""
        from langchain_core.messages import HumanMessage

        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                return content if isinstance(content, str) else str(content)
        # 没有用户消息时返回空串，走默认回复
        return ""

    def _route_reply(self, user_text: str) -> str:
        """根据用户消息关键词路由到回复池，随机选取（避免连续重复）。"""
        text_lower = user_text.lower()
        pool = _DEFAULT_REPLIES
        for keywords, target_pool in _ROUTING_RULES:
            if any(kw in text_lower for kw in keywords):
                pool = target_pool
                break
        # 随机选一条，避免与上次相同
        candidates = [r for r in pool if r != self._last_reply]
        if not candidates:
            candidates = list(pool)
        reply = random.choice(candidates)
        self._last_reply = reply
        return reply


class DeepSeekLLMClient:
    """DeepSeek LLM 客户端：基于 langchain_openai.ChatOpenAI 接入 DeepSeek API。

    DeepSeek 提供 OpenAI 兼容接口，base_url=https://api.deepseek.com，
    模型名 deepseek-v4-flash（V4-Flash 非思考模式，适合实时聊天）。

    通过 LLMClient Protocol 暴露 chat / stream_chat 两个方法，
    业务层无感知底层实现切换。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        max_tokens: int = 512,
        temperature: float = 0.8,
    ) -> None:
        from langchain_openai import ChatOpenAI

        self._client: ChatOpenAI = ChatOpenAI(
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            streaming=False,
        )
        # 流式专用实例（streaming=True 让 ChatOpenAI 走 SSE 通道）
        self._stream_client: ChatOpenAI = ChatOpenAI(
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            streaming=True,
        )
        logger.info(
            f"DeepSeekLLMClient initialized: model={model} base_url={base_url} "
            f"max_tokens={max_tokens} temperature={temperature}"
        )

    async def chat(self, messages: list[BaseMessage]) -> str:
        """非流式对话：调用 DeepSeek API 返回完整回复。"""
        try:
            response = await self._client.ainvoke(messages)
            content = response.content
            reply = content if isinstance(content, str) else str(content)
            logger.debug(
                f"deepseek chat: messages={len(messages)} reply_len={len(reply)}"
            )
            return reply
        except Exception as exc:
            logger.error(f"deepseek chat failed: {exc}")
            raise

    async def stream_chat(self, messages: list[BaseMessage]) -> AsyncIterator[str]:
        """流式对话：通过 SSE 逐 chunk 返回回复片段。"""
        try:
            collected_len = 0
            async for chunk in self._stream_client.astream(messages):
                content = chunk.content
                text = content if isinstance(content, str) else str(content)
                if text:
                    collected_len += len(text)
                    yield text
            logger.debug(
                f"deepseek stream done: messages={len(messages)} total_len={collected_len}"
            )
        except Exception as exc:
            logger.error(f"deepseek stream failed: {exc}")
            raise


__all__ = ["LLMClient", "MockLLMClient", "DeepSeekLLMClient"]
