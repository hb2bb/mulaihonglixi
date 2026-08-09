"""全局依赖注入：提供 LLMClient、PromptService、ChatService 单例。

通过 Depends() 机制注入，便于测试时替换 mock。
"""
from functools import lru_cache

from services.chat_service import ChatService
from services.llm_client import LLMClient, MockLLMClient
from services.prompt_service import PromptService
from core.config import settings


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """根据 settings.llm_provider 返回对应 LLM 客户端单例。

    DEMO 阶段仅支持 mock，未来扩展 claude/deepseek 时在此分支。
    """
    provider = settings.llm_provider.lower()
    if provider == "mock":
        return MockLLMClient()
    # 未来扩展：
    # elif provider == "claude":
    #     return ClaudeLLMClient(api_key=settings.llm_api_key, model=settings.llm_model)
    # elif provider == "deepseek":
    #     return DeepSeekLLMClient(...)
    raise ValueError(f"unsupported llm_provider: {provider}")


@lru_cache(maxsize=1)
def get_prompt_service() -> PromptService:
    """返回 PromptService 单例。"""
    return PromptService()


def get_chat_service() -> ChatService:
    """构造 ChatService，注入 llm_client 和 prompt_service。"""
    return ChatService(
        llm_client=get_llm_client(),
        prompt_service=get_prompt_service(),
    )


__all__ = ["get_llm_client", "get_prompt_service", "get_chat_service"]
