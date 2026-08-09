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
    cors_origins: list[str] = ["http://localhost:5173"]

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
