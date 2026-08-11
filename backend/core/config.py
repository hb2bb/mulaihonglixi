"""全局配置：pydantic-settings 读取 .env，统一管理环境变量与运行参数。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置，从 .env 文件读取，字段对应环境变量（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM 相关
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    max_context_tokens: int = 32000

    # 存储相关
    chat_history_dir: str = "data/chat_history"
    persona_dir: str = "../skills/cangzhou-code-companion/references"
    log_dir: str = "logs"

    # 跨域
    cors_origins: list[str] = ["http://localhost:3000"]

    # 内容检索（web_search 工具，支持小红书/抖音）
    web_search_enabled: bool = True
    # 默认探索主题（概率自动触发时的检索主题池，平台中性；平台由随机/语义意图决定）
    web_search_topics: list[str] = [
        "露营 装备 推荐",
        "咖啡 探店",
        "旅行 攻略",
        "美食 食谱",
        "城市 探店",
        "美食 vlog",
        "露营 攻略",
        "旅行 vlog",
        "编程 学习 教程",
        "数码 产品 评测",
        "知识 科普",
        "深度 问答 观点",
    ]
    # 无关键词命中时，按此概率自动触发检索（0~1），实现主动探索。
    # 注意：有 LLM 意图识别兜底时，此值仅作为 LLM 不可用时的回退触发概率。
    web_search_auto_probability: float = 0.3
    # 每次检索返回的最大结果条数
    web_search_result_limit: int = 5
    # 是否校验结果 URL 的 host 属于目标站点（过滤搜索引擎混入的无关网页）
    web_search_host_verify: bool = True
    # 检测到验证码/访问异常后的冷却时间（秒）：期间暂停检索请求
    web_search_cooldown: float = 60.0

    # 天气检索（weather_search 工具，基于 Open-Meteo 免费接口）
    weather_enabled: bool = True
    # 无法从用户画像/历史推断城市时的回退城市
    weather_city_fallback: str = "北京"
    # 天气结果缓存 TTL（秒）：相同城市在此时间内不重复请求天气接口
    weather_cache_ttl: float = 600.0
    weather_timeout: float = 10.0
    # 每次召回最多执行的检索词数（每个平台最多跑这么多条改写后的查询）
    web_search_max_queries: int = 3
    # 每轮召回最多执行的搜索次数（硬上限 = 平台数 × 检索词数，控制成本/延迟）
    web_search_max_recall_searches: int = 6

    @property
    def chat_history_path(self) -> Path:
        """聊天历史 json 文件根目录。"""
        return Path(self.chat_history_dir)

    @property
    def persona_path(self) -> Path:
        """persona markdown 文件目录。"""
        return Path(self.persona_dir)

    @property
    def log_path(self) -> Path:
        """日志文件目录。"""
        return Path(self.log_dir)


settings = Settings()
