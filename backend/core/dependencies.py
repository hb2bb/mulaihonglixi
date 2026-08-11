"""全局依赖注入：提供 LLMClient、PromptService、ChatService 单例。

通过 Depends() 机制注入，便于测试时替换 mock。
"""
from functools import lru_cache

from services.chat_service import ChatService
from services.llm_client import DeepSeekLLMClient, LLMClient, MockLLMClient
from services.prompt_service import PromptService
from tools.web_search_tool import WebSearchTool, get_web_search_tool
from tools.weather_search_tool import WeatherSearchTool, get_weather_search_tool
from core.config import settings


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """根据 settings.llm_provider 返回对应 LLM 客户端单例。

    支持的 provider：
    - mock: MockLLMClient（DEMO 用，不调真实 API）
    - deepseek: DeepSeekLLMClient（基于 langchain_openai.ChatOpenAI）
    """
    provider = settings.llm_provider.lower()
    if provider == "mock":
        return MockLLMClient()
    elif provider == "deepseek":
        if not settings.llm_api_key:
            raise ValueError("LLM_PROVIDER=deepseek 但 LLM_API_KEY 为空，请检查 .env")
        return DeepSeekLLMClient(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "deepseek-v4-flash",
            base_url=settings.llm_base_url or "https://api.deepseek.com",
        )
    # 未来扩展：
    # elif provider == "claude":
    #     return ClaudeLLMClient(api_key=settings.llm_api_key, model=settings.llm_model)
    raise ValueError(f"unsupported llm_provider: {provider}")


@lru_cache(maxsize=1)
def get_prompt_service() -> PromptService:
    """返回 PromptService 单例。"""
    return PromptService()


def get_chat_service() -> ChatService:
    """构造 ChatService，注入 llm_client、prompt_service、web_search_tool、weather_search_tool。"""
    return ChatService(
        llm_client=get_llm_client(),
        prompt_service=get_prompt_service(),
        web_search_tool=get_web_search_tool(),
        weather_search_tool=get_weather_search_tool(),
    )


__all__ = ["get_llm_client", "get_prompt_service", "get_chat_service"]
