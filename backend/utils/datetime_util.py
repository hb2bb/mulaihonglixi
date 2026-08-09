"""时间相关工具函数，统一使用带北京时区的 ISO8601 格式。"""
from datetime import datetime, timezone, timedelta

# 东八区
BEIJING_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    """返回当前北京时间的 ISO8601 字符串。"""
    return datetime.now(BEIJING_TZ).isoformat(timespec="seconds")


def now_dt() -> datetime:
    """返回带北京时区的当前 datetime 对象。"""
    return datetime.now(BEIJING_TZ)


def format_dt(dt: datetime) -> str:
    """将 datetime 格式化为 ISO8601 字符串。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    return dt.isoformat(timespec="seconds")


__all__ = ["BEIJING_TZ", "now_iso", "now_dt", "format_dt"]
