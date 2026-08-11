"""对话业务编排：取历史 -> 拼消息 -> 调 LLM -> 存历史 -> 返回。

禁止在路由层写复杂业务，所有对话逻辑集中在此处。
聊天历史存 json 文件，按 session_id 分文件。
"""
import asyncio
import json
import random
from pathlib import Path
from typing import AsyncIterator, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from core.config import settings
from core.exceptions import HistoryPersistError, SessionError
from core.logger import logger
from schemas.request.chat import ChatRequest
from schemas.response.chat import ChatResponseData
from services.llm_client import LLMClient
from services.prompt_service import PromptService
from tools.web_search_tool import (
    RecallGroup,
    SITE_NAMES,
    WebSearchTool,
    build_recall_context,
    get_web_search_tool,
    pick_topic,
    platform_label,
)
from tools.weather_search_tool import WeatherSearchTool
from services.user_service import get_user_profile
from utils.common import generate_session_id, is_valid_session_id, safe_history_path
from utils.datetime_util import now_dt, now_iso


# 检索意图识别与查询改写 system prompt：让 LLM 结合对话历史做语义判断、改写/扩展多条检索词、选择平台
_SEARCH_INTENT_SYSTEM_PROMPT = (
    "你是对话助手的检索意图识别与查询改写模块。\n"
    "输入是对话历史（用户与AI的往来）+ 当前用户消息。\n"
    "任务：1) 判断是否值得检索；2) 若值得，结合上下文把当前话题改写/扩展成多条检索词，"
    "覆盖主话题的不同角度/主体（多路多主体召回）；3) 决定检索哪些平台。\n"
    "平台说明：\n"
    "- douyin：抖音，短视频/探店/网红/vlog/热门视频等内容\n"
    "- xiaohongshu：小红书，图文攻略/生活方式/食谱/测评等内容\n"
    "- bilibili：哔哩哔哩，长视频/教程/评测/专栏/番剧/知识视频等内容\n"
    "- zhihu：知乎，文章/专栏/深度问答/专业观点/经验分享等内容\n"
    "只输出一个 JSON 对象，不要输出任何其他内容，格式如下：\n"
    '{"should_search": true/false, "platforms": ["douyin", "xiaohongshu", "bilibili", "zhihu"], "queries": ["检索词1", "检索词2", ...]}\n'
    "规则：\n"
    "1. 闲聊、寒暄、问候、与内容探索无关时 should_search=false，platforms=[]，queries=[]。\n"
    "2. should_search 为 true 时，queries 给 3~5 条：结合对话历史与当前语义改写/扩展，"
    "从不同角度、不同主体覆盖主话题；每条 20 字内，不带平台名，避免重复。\n"
    "3. platforms 为要检索的平台子集，从 [douyin, xiaohongshu, bilibili, zhihu] 中按内容形态选择：\n"
    "   - 短视频/探店/网红/娱乐视频 -> douyin\n"
    "   - 图文攻略/生活方式/食谱/测评 -> xiaohongshu\n"
    "   - 长视频/教程/评测/技术/番剧/知识视频 -> bilibili\n"
    "   - 文章/专栏/深度问答/专业观点/经验 -> zhihu\n"
    "   多平台都相关时都选；拿不准时选最贴近的，避免全选。\n"
    "4. 拿不准时可倾向返回 false，避免过度检索。"
)

# 天气城市推断 system prompt：让 LLM 根据用户画像+历史消息推断用户所在城市
_WEATHER_CITY_SYSTEM_PROMPT = (
    "你是天气城市推断模块。根据用户画像和最近对话历史，推断用户所在城市。\n"
    "只输出一个城市名（如'上海'、'杭州'），不要输出任何其他内容。\n"
    "若无法从用户画像或历史中推断出明确城市，则输出'北京'。"
)


class ChatService:
    """对话编排服务，依赖 LLMClient 和 PromptService。"""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_service: PromptService,
        history_dir: Path | None = None,
        web_search_tool: Optional[WebSearchTool] = None,
        weather_search_tool: Optional[WeatherSearchTool] = None,
    ) -> None:
        self._llm_client: LLMClient = llm_client
        self._prompt_service: PromptService = prompt_service
        self._history_dir: Path = history_dir or settings.chat_history_path
        self._web_search_tool: Optional[WebSearchTool] = web_search_tool
        self._weather_tool: Optional[WeatherSearchTool] = weather_search_tool
        # 按会话缓存推断出的天气城市（城市在一次会话内基本不变，避免每条都调 LLM）
        self._city_cache: dict[str, str] = {}

    async def handle_chat(
        self,
        message: str,
        session_id: str | None,
    ) -> ChatResponseData:
        """非流式对话：完整返回一条回复。

        Args:
            message: 用户消息文本。
            session_id: 会话 ID，为空则生成新会话。

        Returns:
            ChatResponseData: 包含 session_id、reply、datetime。
        """
        session_id = self.resolve_session_id(session_id)
        history = await self._load_history(session_id)
        search_context = await self._maybe_search(message, history)
        dynamic_prompt = await self._build_dynamic_prompt(session_id, history)
        messages = self._assemble_messages(history, message, search_context, dynamic_prompt)
        reply = await self._llm_client.chat(messages)
        await self._persist_history(
            session_id,
            history,
            user_msg=message,
            assistant_msg=reply,
        )
        dt = now_dt()
        logger.info(
            f"chat done: session={session_id} reply_len={len(reply)} "
            f"history_len={len(history) + 2} search_ctx={len(search_context or '')}"
        )
        return ChatResponseData(session_id=session_id, reply=reply, datetime=dt)

    async def handle_chat_stream(
        self,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[str]:
        """流式对话：逐 chunk yield 回复片段，结束后持久化完整回复。

        Args:
            message: 用户消息文本。
            session_id: 会话 ID，为空则生成新会话。

        Yields:
            str: 回复片段（chunk）。
        """
        session_id = self.resolve_session_id(session_id)
        history = await self._load_history(session_id)
        search_context = await self._maybe_search(message, history)
        dynamic_prompt = await self._build_dynamic_prompt(session_id, history)
        messages = self._assemble_messages(history, message, search_context, dynamic_prompt)
        # 收集完整回复，流结束后持久化
        collected: list[str] = []
        async for chunk in self._llm_client.stream_chat(messages):
            collected.append(chunk)
            yield chunk
        full_reply = "".join(collected)
        await self._persist_history(
            session_id,
            history,
            user_msg=message,
            assistant_msg=full_reply,
        )
        logger.info(
            f"stream done: session={session_id} reply_len={len(full_reply)} "
            f"history_len={len(history) + 2} search_ctx={len(search_context or '')}"
        )

    def resolve_session_id(self, session_id: str | None) -> str:
        """校验或生成 session_id。"""
        if session_id is None or session_id == "":
            new_id = generate_session_id()
            logger.debug(f"generated new session_id: {new_id}")
            return new_id
        if not is_valid_session_id(session_id):
            logger.warning(f"invalid session_id received: {session_id}")
            raise SessionError(msg=f"session_id 格式非法: {session_id}")
        return session_id

    def _assemble_messages(
        self,
        history: list[dict],
        current_message: str,
        search_context: str | None = None,
        dynamic_prompt: str | None = None,
    ) -> list[BaseMessage]:
        """组装 LangChain 消息列表：system + [检索上下文] + 历史 + 当前用户消息。

        Args:
            history: 历史记录列表，每项 {role, content, datetime}。
            current_message: 本次用户消息。
            search_context: 检索上下文文本，非空时作为额外的 SystemMessage 注入。
            dynamic_prompt: 动态上下文（时间/天气等），非空时拼到 system prompt 最前。

        Returns:
            list[BaseMessage]: LangChain 消息列表。
        """
        system_prompt = self._prompt_service.get_system_prompt()
        if dynamic_prompt:
            system_prompt = f"{dynamic_prompt}\n\n{system_prompt}"
        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        if search_context:
            messages.append(SystemMessage(content=search_context))
        for record in history:
            role = record.get("role", "")
            content = record.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=current_message))

        # 观测日志：以单条日志打印本轮最终发给 LLM 的完整 prompt
        parts: list[str] = ["===== ASSEMBLED PROMPT (发往 LLM 的完整消息) ====="]
        for i, msg in enumerate(messages):
            content = msg.content
            if not isinstance(content, str):
                content = str(content)
            parts.append(f"[prompt {i}] role={msg.type} (len={len(content)}):\n{content}")
        parts.append("===== END PROMPT =====")
        logger.info("\n".join(parts))

        return messages

    async def _build_dynamic_prompt(self, session_id: str, history: list[dict]) -> str:
        """构建动态上下文 prompt（当前北京时间 + 天气），包在 <dynamic_prompt> 标签内。

        任一部分失败都不影响整体：时间必出，天气不可用时仅时间。
        """
        lines = ["<dynamic_prompt>"]
        lines.append(f"<time>{now_iso()}（北京时间）</time>")
        if settings.weather_enabled and self._weather_tool:
            city = await self._infer_weather_city(session_id, history)
            weather = await self._weather_tool.get_weather(city)
            if weather:
                lines.append(f"<weather>{city}：{weather}</weather>")
        lines.append("</dynamic_prompt>")
        return "\n".join(lines)

    async def _infer_weather_city(self, session_id: str, history: list[dict]) -> str:
        """根据用户画像 + 最近历史推断用户所在城市；缓存按会话；推断失败回退配置默认。"""
        cached = self._city_cache.get(session_id)
        if cached:
            return cached
        city = settings.weather_city_fallback
        try:
            profile = await get_user_profile()
            history_text = self._format_history_for_judge(history)
            user_prompt = (
                f"用户画像：{json.dumps(profile, ensure_ascii=False)}\n"
                f"最近对话：\n{history_text or '（无）'}"
            )
            messages = [
                SystemMessage(content=_WEATHER_CITY_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            raw = await self._llm_client.chat(messages)
            raw = (raw or "").strip().strip('"\'').strip()
            if raw:
                city = raw[:20]
            logger.info(f"[weather] city inferred: {city!r} (session={session_id})")
        except Exception as exc:
            logger.warning(f"[weather] city infer failed, fallback={city!r} err={exc}")
        self._city_cache[session_id] = city
        return city

    async def _maybe_search(self, user_message: str, history: list[dict]) -> str:
        """根据 LLM 语义意图决定是否检索，并返回检索上下文文本。

        触发策略（纯语义 + 上下文查询改写 + 多路多主体召回）：
        - 调用 LLM 结合对话历史做意图识别与查询改写，返回是否检索、多条检索词、
          以及要调用哪些平台工具（douyin / xiaohongshu / 两者 / 都不）。
        - LLM 判断失败/不可用 -> 回退到按概率自动触发（保持可用性）。

        Returns:
            检索上下文文本；未触发或检索失败时返回空串。
        """
        if not settings.web_search_enabled:
            logger.info("web_search skipped: disabled by config")
            return ""
        if not self._web_search_tool:
            logger.warning("web_search skipped: web_search_tool not injected")
            return ""

        # LLM 语义意图识别 + 上下文查询改写：决定是否检索、多条检索词、调用哪些平台工具
        should_search, queries, platforms = await self._llm_judge_search(
            user_message, history
        )
        logger.info(
            f"web_search trigger=llm should_search={should_search} "
            f"queries={queries} platforms={platforms} user={user_message!r}"
        )
        if should_search:
            return await self._do_search(queries, platforms)

        # 回退到概率自动触发（主动探索）：随机选平台 + 主题
        if random.random() < settings.web_search_auto_probability:
            site = random.choice(SITE_NAMES)
            topic = pick_topic(settings.web_search_topics)
            logger.info(f"web_search trigger=probabilistic site={site} topic={topic!r}")
            return await self._do_search([topic], [site])
        logger.info("web_search skipped: no trigger")
        return ""

    async def _do_search(self, queries: list[str], platforms: list[str]) -> str:
        """对指定平台执行多路检索（并发），并把各平台结果拼装成上下文文本。"""
        sites = [s for s in platforms if s in SITE_NAMES] or [SITE_NAMES[0]]
        clean_queries = [q.strip() for q in queries if q and q.strip()]
        if not clean_queries:
            clean_queries = [pick_topic(settings.web_search_topics)]
        clean_queries = clean_queries[: settings.web_search_max_queries]

        # 组合 (平台, 检索词) 搜索任务，硬上限控制成本/延迟
        tasks: list[tuple[str, str]] = []
        for site in sites:
            for q in clean_queries:
                tasks.append((site, q))
        tasks = tasks[: settings.web_search_max_recall_searches]
        logger.info(f"[tool] recall tasks={len(tasks)} sites={sites} queries={clean_queries!r}")

        results = await asyncio.gather(
            *(
                self._web_search_tool.search(q, site, settings.web_search_result_limit)
                for site, q in tasks
            ),
            return_exceptions=True,
        )

        groups: list[RecallGroup] = []
        for (site, q), res in zip(tasks, results):
            if isinstance(res, Exception):
                logger.warning(f"[tool] web_search.error site={site} query={q!r} err={res}")
                continue
            if not res:
                logger.info(f"[tool] web_search.result empty site={site} query={q!r}")
                continue
            for i, r in enumerate(res, 1):
                logger.info(
                    f"[tool] web_search.result[{i}] platform={r.platform} "
                    f"title={r.title!r} url={r.url!r} snippet_len={len(r.snippet)}"
                )
            groups.append(RecallGroup(platform=platform_label(site), query=q, results=res))

        context = build_recall_context(groups)
        logger.info(f"[tool] recall.done groups={len(groups)} context_len={len(context)}")
        return context

    async def _llm_judge_search(
        self,
        user_message: str,
        history: list[dict],
    ) -> tuple[bool, list[str], list[str]]:
        """调用 LLM 结合对话历史做检索意图识别与查询改写。

        结构化 JSON 输出：{"should_search": bool, "queries": [...], "platforms": [...]}。
        解析失败或 LLM 不可用时返回 (False, [], [])。
        """
        try:
            context_text = self._format_history_for_judge(history)
            user_prompt = (
                f"对话历史：\n{context_text}\n当前用户消息：{user_message}"
                if context_text
                else f"当前用户消息：{user_message}"
            )
            messages = [
                SystemMessage(content=_SEARCH_INTENT_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            raw = await self._llm_client.chat(messages)
            logger.info(f"[intent] llm.raw user={user_message!r} raw={raw!r}")
            decision = self._parse_intent_json(raw)
            if decision is None:
                logger.warning(f"[intent] parse.failed raw={raw!r}")
                return False, [], []
            should = bool(decision.get("should_search"))
            queries = self._sanitize_queries(decision.get("queries"))
            platforms = self._sanitize_platforms(decision.get("platforms"))
            if should and not queries:
                queries = [pick_topic(settings.web_search_topics)]
            if should and not platforms:
                platforms = [SITE_NAMES[0]]
            logger.info(
                f"[intent] decision should_search={should} queries={queries!r} "
                f"platforms={platforms} raw={raw!r}"
            )
            return should, queries, platforms
        except Exception as exc:
            logger.warning(f"[intent] judge.failed err={exc}")
            return False, [], []

    @staticmethod
    def _format_history_for_judge(history: list[dict], max_turns: int = 3) -> str:
        """把最近几轮对话历史格式化成文本（供意图识别/查询改写参考上下文）。"""
        if not history:
            return ""
        recent = history[-max_turns * 2 :]
        lines: list[str] = []
        for record in recent:
            role = "用户" if record.get("role") == "user" else "AI"
            content = str(record.get("content", ""))
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _sanitize_queries(raw: object) -> list[str]:
        """把意图返回的检索词列表清洗为合法字符串列表，去重、过滤空值。"""
        if not isinstance(raw, list):
            return []
        seen: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                continue
            q = item.strip()
            if q and q not in seen:
                seen.append(q[:50])
        return seen

    @staticmethod
    def _sanitize_platforms(raw: object) -> list[str]:
        """把意图返回的平台名清洗为合法站点名列表，去重、过滤未知值。"""
        if not isinstance(raw, list):
            return []
        seen: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                continue
            name = item.strip().lower()
            if name in SITE_NAMES and name not in seen:
                seen.append(name)
        return seen

    @staticmethod
    def _parse_intent_json(raw: str) -> dict | None:
        """从 LLM 输出中提取意图 JSON 对象；失败返回 None。"""
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    async def _load_history(self, session_id: str) -> list[dict]:
        """从 json 文件加载聊天历史，文件不存在则返回空列表。"""
        self._history_dir.mkdir(parents=True, exist_ok=True)
        filepath = safe_history_path(self._history_dir, session_id)
        if not filepath.exists():
            return []
        # 用 to_thread 包装同步文件读取，避免阻塞事件循环
        data = await asyncio.to_thread(self._read_json_file, filepath)
        logger.debug(f"loaded history: session={session_id} records={len(data)}")
        return data

    async def list_session_ids(self) -> list[str]:
        """按最后修改时间倒序返回所有会话 ID（最新的在前）。

        用于进入页面时定位"最近会话"，或前端展示会话入口。
        """
        self._history_dir.mkdir(parents=True, exist_ok=True)
        files = [p for p in self._history_dir.glob("*.json") if p.is_file()]
        # 按 mtime 倒序
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.stem for p in files]

    async def load_history_page(
        self,
        session_id: str,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict], int, bool]:
        """分页加载历史消息（时间正序，旧 -> 新）。

        Args:
            session_id: 会话 ID。
            offset: 已从最新端跳过的条数（首次为 0，向上滚动后递增）。
            limit: 每页条数。

        Returns:
            (page, total, has_more)：page 为本页消息（正序），
            total 为历史总条数，has_more 表示是否还有更早的消息。
        """
        history = await self._load_history(session_id)
        total = len(history)
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        if offset >= total:
            return [], total, False
        # 从最新端往前取 limit 条
        end = total - offset
        start = max(0, end - limit)
        page = history[start:end]
        has_more = start > 0
        return page, total, has_more

    async def _persist_history(
        self,
        session_id: str,
        history: list[dict],
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """追加本次对话两条记录并写回 json 文件。"""
        self._history_dir.mkdir(parents=True, exist_ok=True)
        filepath = safe_history_path(self._history_dir, session_id)
        # 追加 user + assistant 两条
        history.append({"role": "user", "content": user_msg, "datetime": now_iso()})
        history.append(
            {"role": "assistant", "content": assistant_msg, "datetime": now_iso()}
        )
        try:
            await asyncio.to_thread(self._write_json_file, filepath, history)
            logger.debug(f"persisted history: session={session_id} records={len(history)}")
        except OSError as exc:
            logger.error(f"failed to persist history: session={session_id} err={exc}")
            raise HistoryPersistError(msg=f"历史写入失败: {exc}") from exc

    @staticmethod
    def _read_json_file(filepath: Path) -> list[dict]:
        """同步读取 json 文件（由 to_thread 调度）。"""
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, list):
            logger.warning(f"history file not a list, resetting: {filepath}")
            return []
        return data

    @staticmethod
    def _write_json_file(filepath: Path, data: list[dict]) -> None:
        """同步写入 json 文件（由 to_thread 调度）。"""
        text = json.dumps(data, ensure_ascii=False, indent=2)
        filepath.write_text(text, encoding="utf-8")


__all__ = ["ChatService"]
