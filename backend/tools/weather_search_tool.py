"""weather_search 工具：基于 Open-Meteo 的当前天气检索（免费、无需 key）。

- 通过 Open-Meteo 地理编码 API 把城市名转成经纬度。
- 再通过 Open-Meteo 天气 API 获取当前天气，返回中文可读描述。
- 带短 TTL 缓存，避免每条聊天消息都重复请求天气接口。
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from core.config import settings
from core.logger import logger

# Open-Meteo WMO weather code -> 中文描述
_WEATHER_CODE_MAP: dict[int, str] = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "毛毛雨",
    56: "冻毛毛雨",
    57: "冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "霰",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "阵雪",
    95: "雷暴",
    96: "雷暴伴冰雹",
    99: "雷暴伴冰雹",
}


class WeatherSearchTool:
    """基于 Open-Meteo 的天气检索工具（免费、无需 key）。"""

    _GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
    _FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    _HEADERS = {"User-Agent": "ai-girlfriend-demo/0.1"}

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._cache_ttl: float = settings.weather_cache_ttl
        # city -> (monotonic ts, weather_str)
        self._cache: dict[str, tuple[float, str]] = {}

    async def get_weather(self, city: str) -> str:
        """返回城市当前天气的中文描述；失败返回空串（不抛出）。"""
        city = (city or "").strip()
        if not city:
            return ""
        # 缓存命中
        hit = self._cache.get(city)
        if hit and time.monotonic() - hit[0] < self._cache_ttl:
            return hit[1]
        try:
            text = await self._fetch_weather(city)
            if text:
                self._cache[city] = (time.monotonic(), text)
            return text
        except Exception as exc:
            logger.warning(f"weather_search failed: city={city!r} err={exc}")
            return ""

    async def _fetch_weather(self, city: str) -> str:
        """执行一次完整的天气检索（地理编码 + 当前天气），返回描述文本。"""
        async with httpx.AsyncClient(
            headers=self._HEADERS, timeout=self._timeout, follow_redirects=True
        ) as client:
            lat, lon, resolved_name = await self._geocode(client, city)
            if lat is None:
                logger.warning(f"weather_search geocode empty: city={city!r}")
                return ""
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "timezone": "Asia/Shanghai",
            }
            resp = await client.get(self._FORECAST_URL, params=params)
            resp.raise_for_status()
            cur = resp.json().get("current") or {}
            return self._format(city, resolved_name, cur)

    async def _geocode(
        self, client: httpx.AsyncClient, city: str
    ) -> tuple[float | None, float | None, str]:
        """城市名 -> (latitude, longitude, 解析出的城市名)。"""
        resp = await client.get(
            self._GEO_URL,
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return None, None, city
        first = results[0]
        name = first.get("name") or city
        return first.get("latitude"), first.get("longitude"), name

    @staticmethod
    def _format(city: str, resolved_name: str, cur: dict[str, Any]) -> str:
        """把当前天气 JSON 拼成中文描述。"""
        code = cur.get("weather_code")
        desc = _WEATHER_CODE_MAP.get(int(code)) if code is not None else "未知"
        temp = cur.get("temperature_2m")
        feels = cur.get("apparent_temperature")
        humidity = cur.get("relative_humidity_2m")
        wind = cur.get("wind_speed_10m")
        parts = [desc]
        if temp is not None:
            parts.append(f"{temp:.0f}℃")
        if feels is not None:
            parts.append(f"体感{feels:.0f}℃")
        if humidity is not None:
            parts.append(f"湿度{humidity:.0f}%")
        if wind is not None:
            parts.append(f"风速{wind:.1f}m/s")
        return "，".join(parts)


def get_weather_search_tool() -> WeatherSearchTool:
    """构造天气检索工具单例。"""
    return WeatherSearchTool()


__all__ = ["WeatherSearchTool", "get_weather_search_tool"]
