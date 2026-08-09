"""通用工具函数：session_id 生成、文件路径安全校验等。"""
import re
from uuid import uuid4
from pathlib import Path

# 合法 session_id：uuid 格式（带连字符的 32 位 hex）
_SESSION_ID_PATTERN = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")


def generate_session_id() -> str:
    """生成新的 session_id（uuid v4 小写）。"""
    return str(uuid4())


def is_valid_session_id(session_id: str) -> bool:
    """校验 session_id 是否为合法 uuid v4 格式。"""
    return bool(_SESSION_ID_PATTERN.match(session_id.lower()))


def safe_history_path(base_dir: Path, session_id: str) -> Path:
    """根据 session_id 构造安全的聊天历史 json 文件路径。

    防止路径穿越：校验 session_id 合法性后再拼接路径。
    """
    if not is_valid_session_id(session_id):
        raise ValueError(f"invalid session_id: {session_id}")
    return base_dir / f"{session_id}.json"


__all__ = [
    "generate_session_id",
    "is_valid_session_id",
    "safe_history_path",
]
