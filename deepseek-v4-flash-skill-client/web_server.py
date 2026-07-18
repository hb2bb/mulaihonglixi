#!/usr/bin/env python3
"""零第三方依赖的网站服务：提供静态前端和 DeepSeek API 代理。"""

from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import threading
import time
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from deepseek_skill_client import DeepSeekError, DeepSeekSkillClient, SkillLoader


SITE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SITE_ROOT.parent
WEB_ROOT = SITE_ROOT / "web"
MAX_REQUEST_BYTES = 1_000_000
MAX_MESSAGES = 30
MAX_MESSAGE_LENGTH = 12_000
MAX_TOTAL_LENGTH = 60_000


def load_dotenv(path: Path) -> None:
    """加载简单的 KEY=VALUE 配置，但不会覆盖已经存在的环境变量。"""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value)


def validate_messages(value: Any) -> list[dict[str, str]] | None:
    """限制访客输入的类型与体积，防止把任意大请求转发给付费 API。"""
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_MESSAGES:
        return None
    result: list[dict[str, str]] = []
    total_length = 0
    for item in value:
        if not isinstance(item, dict):
            return None
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            return None
        if not content.strip() or len(content) > MAX_MESSAGE_LENGTH:
            return None
        total_length += len(content)
        if total_length > MAX_TOTAL_LENGTH:
            return None
        result.append({"role": role, "content": content})
    return result


class RateLimiter:
    """进程内的轻量限流：默认每个 IP 每分钟最多 10 次模型请求。"""

    def __init__(self, limit: int = 10, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, identity: str) -> bool:
        now = time.monotonic()
        with self.lock:
            records = self.requests[identity]
            while records and now - records[0] >= self.window_seconds:
                records.popleft()
            if len(records) >= self.limit:
                return False
            records.append(now)
            return True


class FlashLabServer(ThreadingHTTPServer):
    """保存共享配置；每个 HTTP 请求仍由独立线程处理。"""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], include_user_skills: bool) -> None:
        super().__init__(address, FlashLabHandler)
        self.skill_loader = SkillLoader(PROJECT_ROOT, include_user_skills=include_user_skills)
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.access_key = os.environ.get("SITE_ACCESS_KEY", "")
        self.rate_limiter = RateLimiter()

    def create_client(self) -> DeepSeekSkillClient:
        return DeepSeekSkillClient(
            api_key=self.api_key,
            skill_loader=self.skill_loader,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            thinking=True,
            reasoning_effort="high",
        )


class FlashLabHandler(BaseHTTPRequestHandler):
    server: FlashLabServer

    def log_message(self, format_string: str, *args: object) -> None:
        # 使用统一、简短的访问日志，且不打印访客发送的提示词。
        print(f"[{self.log_date_time_string()}] {self.client_address[0]} {format_string % args}")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
        )
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 使用固定方法名
        clean_path = self.path.split("?", 1)[0]
        if clean_path == "/api/status":
            self.send_json(
                {
                    "ready": bool(self.server.api_key),
                    "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
                    "skill_file_count": len(self.server.skill_loader.load()),
                    "access_key_required": bool(self.server.access_key),
                }
            )
            return
        if clean_path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        static_files = {
            "/": WEB_ROOT / "index.html",
            "/index.html": WEB_ROOT / "index.html",
            "/app.js": WEB_ROOT / "app.js",
            # 零依赖版和可部署版复用同一套视觉样式。
            "/styles.css": SITE_ROOT / "app" / "globals.css",
        }
        target = static_files.get(clean_path)
        if target is None or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 使用固定方法名
        if self.path.split("?", 1)[0] != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self.server.api_key:
            self.send_json({"error": "服务尚未配置 DeepSeek API Key。"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if self.server.access_key and not hmac.compare_digest(
            self.headers.get("X-Flash-Lab-Access", ""), self.server.access_key
        ):
            self.send_json({"error": "体验访问码不正确。"}, HTTPStatus.UNAUTHORIZED)
            return
        if not self.server.rate_limiter.allow(self.client_address[0]):
            self.send_json({"error": "请求过于频繁，请稍后再试。"}, HTTPStatus.TOO_MANY_REQUESTS)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if not 0 < content_length <= MAX_REQUEST_BYTES:
            self.send_json({"error": "请求体为空或过大。"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self.send_json({"error": "请求不是有效的 JSON。"}, HTTPStatus.BAD_REQUEST)
            return
        messages = validate_messages(body.get("messages") if isinstance(body, dict) else None)
        if messages is None:
            self.send_json({"error": "对话内容为空、过长或格式不正确。"}, HTTPStatus.BAD_REQUEST)
            return

        try:
            # chat() 内部会在这一刻重新扫描并注入 Skills。
            content = self.server.create_client().chat(messages, max_tokens=8_192)
        except DeepSeekError as exc:
            print(f"DeepSeek 调用失败：{exc}")
            self.send_json({"error": "模型服务暂时不可用，请稍后重试。"}, HTTPStatus.BAD_GATEWAY)
            return
        self.send_json({"content": content})

    def send_json(self, value: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(content)
        except BrokenPipeError:
            # 访客点击“停止生成”时浏览器会主动断开，属于正常情况。
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="启动 Pro Lab 网页体验台")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址；公开到局域网可用 0.0.0.0")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--no-user-skills", action="store_true", help="只加载项目级 Skills")
    args = parser.parse_args()

    load_dotenv(SITE_ROOT / ".env")
    server = FlashLabServer((args.host, args.port), include_user_skills=not args.no_user_skills)
    print(f"Pro Lab 已启动：http://{args.host}:{args.port}")
    print(f"已发现 {len(server.skill_loader.load())} 个 Skill 文件。")
    if not server.api_key:
        print("提示：尚未配置 DEEPSEEK_API_KEY，页面可打开，但模型调用会被禁用。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
