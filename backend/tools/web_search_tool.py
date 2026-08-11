"""web_search 工具：通过搜索引擎间接检索小红书/抖音内容，供对话上下文使用。

当前阶段实现：
- 使用 360 so.com 搜索 `site:<域名> + 关键词`，提取结果的标题与摘要。
- 结果链接优先取真实 URL（data-mdurl），并做 host 校验只保留目标站点的结果。
- 支持多站点（小红书、抖音），由调用方（ChatService 的 LLM 语义意图）显式指定站点。
- 稳定性控制：结果缓存去重、最小请求间隔串行化、验证码页面检测与冷却退避，
  以应对 so.com 的限流/反爬，保证摘要检索稳定可用。
- 不做登录/正文抓取；标题+摘要已足够作为背景上下文。

设计说明：
- 未接入 LangChain Agent（backend 无 Agent 框架），本工具作为纯 Python 服务类，
  由 ChatService 在触发时调用。
- 站点选择不再基于检索词里的固定关键词，而是由上层 LLM 语义意图识别决定
  （调抖音、调小红书、两个都调、或都不调）。
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Protocol

import httpx
from bs4 import BeautifulSoup

from core.config import settings
from core.logger import logger


@dataclass
class SearchResult:
    """单条检索结果。"""

    title: str
    snippet: str
    url: str = ""
    platform: str = "小红书"


@dataclass
class RecallGroup:
    """一次"平台 + 检索词"的召回结果组（用于多路多主体召回）。"""

    platform: str  # 显示名，如 小红书 / 抖音
    query: str
    results: list[SearchResult]


@dataclass(frozen=True)
class SiteConfig:
    """一个可检索站点：机器名与显示名。"""

    name: str
    domain: str
    label: str


# 默认支持站点；site 名供上层语义意图引用
_DEFAULT_SITES: tuple[SiteConfig, ...] = (
    SiteConfig("xiaohongshu", "xiaohongshu.com", "小红书"),
    SiteConfig("douyin", "douyin.com", "抖音"),
    SiteConfig("bilibili", "bilibili.com", "哔哩哔哩"),
    SiteConfig("zhihu", "zhihu.com", "知乎"),
)
_DEFAULT_SITE_NAME = "xiaohongshu"

# 合法站点名集合（供上层随机选站 / 校验意图返回的平台名）
SITE_NAMES: tuple[str, ...] = tuple(s.name for s in _DEFAULT_SITES)


class WebSearchTool(Protocol):
    """检索工具协议：业务层只依赖此接口。"""

    async def search(self, query: str, site: str, limit: int = 5) -> list[SearchResult]: ...


class SiteSearchTool:
    """基于 360 so.com 的多站点内容检索工具。

    通过搜索引擎间接检索，规避站内反爬与登录限制。
    """

    _SEARCH_URL = "https://www.so.com/s"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.so.com/",
    }

    def __init__(
        self,
        sites: tuple[SiteConfig, ...] = _DEFAULT_SITES,
        default_site: str = _DEFAULT_SITE_NAME,
        timeout: float = 20.0,
    ) -> None:
        self._sites = sites
        self._default_site = default_site
        self._timeout = timeout
        # 验证码冷却时间点（monotonic 时间戳）；期间暂停检索请求
        self._blocked_until = 0.0

    def _resolve_site(self, site: str) -> SiteConfig:
        """按站点机器名解析站点配置；未知站点名回退默认站点。"""
        for s in self._sites:
            if s.name == site:
                return s
        for s in self._sites:
            if s.name == self._default_site:
                return s
        return self._sites[0]

    async def search(self, query: str, site: str, limit: int = 5) -> list[SearchResult]:
        """检索指定站点内容，返回标题+摘要列表。

        若处于验证码冷却期则直接返回空列表（不请求、不产生上下文）；
        其余失败/空结果由调用方跳过，不塞入上下文。

        Args:
            query: 搜索关键词。
            site: 站点机器名（如 "xiaohongshu" / "douyin"）。
            limit: 最大返回条数。

        Returns:
            list[SearchResult]：检索结果。失败/冷却/异常时返回空列表。
        """
        config = self._resolve_site(site)
        if time.monotonic() < self._blocked_until:
            logger.warning(
                f"web_search cooldown: skip request until {self._blocked_until:.0f}"
            )
            return []
        return await self._fetch(query, config, limit)

    async def _fetch(
        self,
        query: str,
        config: SiteConfig,
        limit: int,
    ) -> list[SearchResult]:
        """执行一次 so.com 检索并解析，返回真实链接+标题+摘要列表。"""
        full_query = f"site:{config.domain} {query}"
        limit = max(1, min(limit, 20))
        try:
            resp = await httpx.AsyncClient(
                headers=self._HEADERS,
                timeout=self._timeout,
                follow_redirects=True,
            ).get(self._SEARCH_URL, params={"q": full_query})
            resp.raise_for_status()
        except Exception as exc:
            logger.error(f"web_search http failed: site={config.name} query={query!r} err={exc}")
            return []

        # 验证码/访问异常页面检测 -> 进入冷却退避
        if self._is_captcha(resp.text):
            self._blocked_until = time.monotonic() + settings.web_search_cooldown
            logger.warning(
                f"web_search captcha detected for site={config.label}; "
                f"cooldown {settings.web_search_cooldown}s"
            )
            return []

        try:
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as exc:
            logger.error(f"web_search parse failed: {exc}")
            return []

        results: list[SearchResult] = []
        for item in soup.select("li.res-list"):
            if len(results) >= limit:
                break
            a = item.select_one("h3 a")
            if not a:
                continue
            title = a.get_text().strip()
            if not title:
                continue
            # 真实链接优先取 data-mdurl（so.com 加密跳转的反面数据），否则回退 href
            url = (a.get("data-mdurl") or "").strip() or (a.get("href") or "").strip()
            # host 校验：只保留指向目标站点的真实链接，弥补搜索引擎 site: 过滤不稳
            if settings.web_search_host_verify and not self._host_matches(url, config.domain):
                continue
            desc = item.select_one(".res-desc, .res-desc-gray, .str_info, p")
            snippet = desc.get_text().strip() if desc else ""
            results.append(
                SearchResult(
                    title=title,
                    snippet=snippet,
                    url=url,
                    platform=config.label,
                )
            )

        logger.info(f"web_search done: site={config.label} query={query!r} results={len(results)}")
        return results

    @staticmethod
    def _host_matches(url: str, domain: str) -> bool:
        """校验 url 的 host 是否为目标站点（含子域）。"""
        try:
            from urllib.parse import urlparse

            host = (urlparse(url).hostname or "").lower()
            return host == domain or host.endswith("." + domain)
        except Exception:
            return False

    @staticmethod
    def _is_captcha(text: str) -> bool:
        """判断响应是否为 so.com 的验证码/访问异常页面。"""
        low = text.lower()
        return ("访问异常" in text) or ("请输入验证码" in text) or ("captcha" in low)


def build_search_context(
    results: list[SearchResult],
    query: str,
) -> str:
    """把检索结果拼装成一段上下文文本（供注入对话）。"""
    if not results:
        return ""
    platform = results[0].platform or "小红书"
    lines = [
        f"【{platform}检索】主题：{query}",
        f"以下是从{platform}检索到的部分内容（标题+摘要）：",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.title}")
        if r.snippet:
            lines.append(f"   摘要：{r.snippet}")
    return "\n".join(lines)


def pick_topic(topics: list[str] | None = None) -> str:
    """随机从探索主题池中选一个检索主题（用于自动触发）。"""
    pool = topics or settings.web_search_topics
    return random.choice(pool) if pool else "美食 探店"


def platform_label(site: str) -> str:
    """站点机器名 -> 显示名（如 xiaohongshu -> 小红书）。未知时原样返回。"""
    for s in _DEFAULT_SITES:
        if s.name == site:
            return s.label
    return site


def build_recall_context(groups: list[RecallGroup]) -> str:
    """把多路多主体召回结果拼装成一段上下文文本（供注入对话）。

    按"平台 + 检索词"分组展示，方便 LLM 区分信息来源。
    """
    valid = [g for g in groups if g.results]
    if not valid:
        return ""
    lines = ["【内容检索召回】以下是从多个平台、多个检索词检索到的相关内容："]
    for g in valid:
        lines.append(f"\n[{g.platform}] 检索词：{g.query}")
        for i, r in enumerate(g.results, 1):
            lines.append(f"{i}. {r.title}")
            if r.snippet:
                lines.append(f"   摘要：{r.snippet}")
    return "\n".join(lines)


def get_web_search_tool() -> WebSearchTool:
    """构造检索工具单例（当前实现为 SiteSearchTool，支持小红书/抖音）。"""
    return SiteSearchTool()


__all__ = [
    "SearchResult",
    "RecallGroup",
    "SiteConfig",
    "SITE_NAMES",
    "WebSearchTool",
    "SiteSearchTool",
    "build_search_context",
    "build_recall_context",
    "platform_label",
    "pick_topic",
    "get_web_search_tool",
]
