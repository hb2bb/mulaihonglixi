"""Prompt 组装服务：启动时加载 persona markdown，拼成 system_prompt 缓存。

persona 文件来自 skills/cangzhou-code-companion/references/：
- character-card.md       角色设定
- dialogue-playbook.md    对话手册
- relationship-memory.md  关系与长期记忆
"""
from pathlib import Path

from core.config import settings
from core.logger import logger
from core.exceptions import ResourceNotFoundError


class PromptService:
    """加载 persona 文件并组装 system_prompt，缓存供请求时直接取用。"""

    # persona 文件名（相对 persona_dir）
    _PERSONA_FILES: tuple[str, ...] = (
        "character-card.md",
        "dialogue-playbook.md",
        "relationship-memory.md",
    )

    def __init__(self, persona_dir: Path | None = None) -> None:
        self._persona_dir: Path = persona_dir or settings.persona_path
        self._system_prompt: str = ""

    async def load(self) -> None:
        """读取所有 persona md 文件，拼成 system_prompt 并缓存。

        Raises:
            ResourceNotFoundError: 任一 persona 文件缺失时抛出。
        """
        sections: list[str] = []
        for filename in self._PERSONA_FILES:
            filepath = self._persona_dir / filename
            if not filepath.exists():
                logger.error(f"persona file missing: {filepath}")
                raise ResourceNotFoundError(msg=f"persona 文件缺失: {filename}")
            content = filepath.read_text(encoding="utf-8").strip()
            sections.append(f"# {filename}\n\n{content}")
            logger.debug(f"loaded persona file: {filename} ({len(content)} chars)")
        # 用分隔线拼接各部分
        self._system_prompt = "\n\n---\n\n".join(sections)
        logger.info(
            f"system_prompt assembled: {len(self._system_prompt)} chars from "
            f"{len(self._PERSONA_FILES)} files"
        )

    def get_system_prompt(self) -> str:
        """返回缓存的 system_prompt。

        若未 load，返回空字符串（理论上 lifespan 已保证 load 完成）。
        """
        return self._system_prompt


__all__ = ["PromptService"]
