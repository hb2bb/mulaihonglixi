#!/usr/bin/env python3
"""DeepSeek V4 Flash 客户端：每次请求都自动注入当前可用的 Skills。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# 匹配 Markdown 中指向本地文件的普通链接，例如 [角色卡](references/card.md)。
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class DeepSeekError(RuntimeError):
    """DeepSeek API 调用失败。"""


@dataclass(frozen=True)
class LoadedFile:
    """一个将被注入模型输入的 Skill 文件。"""

    path: Path
    content: str


class SkillLoader:
    """发现并加载项目级、用户级 Skills 及其本地 Markdown 引用。"""

    def __init__(
        self,
        project_root: Path,
        include_user_skills: bool = True,
        extra_roots: Sequence[Path] = (),
    ) -> None:
        self.project_root = project_root.expanduser().resolve()
        self.include_user_skills = include_user_skills
        self.extra_roots = tuple(path.expanduser().resolve() for path in extra_roots)

    def skill_roots(self) -> list[Path]:
        """返回可能存放 Skill 的目录；不存在的目录会在扫描时自动忽略。"""
        roots = [
            self.project_root / "skills",
            self.project_root / ".agents" / "skills",
            self.project_root / ".deepcode" / "skills",
            self.project_root / ".codex" / "skills",
        ]
        if self.include_user_skills:
            roots.extend(
                [
                    Path.home() / ".agents" / "skills",
                    Path.home() / ".codex" / "skills",
                ]
            )
        roots.extend(self.extra_roots)

        # 使用解析后的绝对路径去重，避免同一个 Skill 被重复注入。
        unique: dict[Path, None] = {}
        for root in roots:
            unique[root.expanduser().resolve()] = None
        return list(unique)

    def discover_skill_files(self) -> list[Path]:
        """查找所有名为 SKILL.md 的文件。"""
        found: set[Path] = set()
        for root in self.skill_roots():
            if root.is_dir():
                found.update(path.resolve() for path in root.rglob("SKILL.md") if path.is_file())
        return sorted(found, key=str)

    def load(self) -> list[LoadedFile]:
        """读取 Skills；每次 API 调用都会重新执行，因此修改可立即生效。"""
        loaded: dict[Path, LoadedFile] = {}
        for skill_file in self.discover_skill_files():
            # 引用文件只能位于当前 Skill 的目录内，避免 Markdown 链接越界读取任意文件。
            skill_directory = skill_file.parent.resolve()
            self._load_file_and_references(skill_file, skill_directory, loaded)
        return list(loaded.values())

    def _load_file_and_references(
        self,
        file_path: Path,
        allowed_directory: Path,
        loaded: dict[Path, LoadedFile],
    ) -> None:
        resolved = file_path.resolve()
        if resolved in loaded or not resolved.is_file():
            return
        if not resolved.is_relative_to(allowed_directory):
            return

        try:
            content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise DeepSeekError(f"读取 Skill 文件失败：{resolved}: {exc}") from exc

        loaded[resolved] = LoadedFile(path=resolved, content=content)

        # 递归加载 Skill 中引用的本地 Markdown 文件；远程 URL、锚点和图片会被忽略。
        for raw_target in MARKDOWN_LINK_RE.findall(content):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>\"'")
            target = target.split("#", maxsplit=1)[0]
            if not target or "://" in target or target.startswith(("#", "mailto:")):
                continue
            referenced = (resolved.parent / target).resolve()
            if referenced.suffix.lower() == ".md":
                self._load_file_and_references(referenced, allowed_directory, loaded)

    def build_system_prompt(self) -> str:
        """把当前所有 Skill 文件拼成一个明确分隔的系统提示词。"""
        files = self.load()
        if not files:
            return "当前没有发现可用的 Skill。"

        sections = [
            "以下是本次请求可用的 Skills。请遵守其中与用户任务相关的指令；"
            "若指令冲突，优先遵守更高优先级的系统和开发者指令。"
        ]
        for loaded_file in files:
            try:
                display_path = loaded_file.path.relative_to(self.project_root)
            except ValueError:
                display_path = loaded_file.path
            sections.append(
                f"\n--- BEGIN SKILL FILE: {display_path} ---\n"
                f"{loaded_file.content}\n"
                f"--- END SKILL FILE: {display_path} ---"
            )
        return "\n".join(sections)


class DeepSeekSkillClient:
    """通过 OpenAI 兼容接口调用 DeepSeek，并在每次请求中注入 Skills。"""

    def __init__(
        self,
        api_key: str,
        skill_loader: SkillLoader,
        *,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        timeout: float = 120.0,
        thinking: bool = True,
        reasoning_effort: str = "high",
    ) -> None:
        if not api_key:
            raise ValueError("api_key 不能为空")
        if reasoning_effort not in {"high", "max"}:
            raise ValueError("reasoning_effort 只能是 high 或 max")

        self.api_key = api_key
        self.skill_loader = skill_loader
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        system_prompt: str = "你是一个可靠的代码助手。",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """发送一次对话请求，并返回助手文本。

        关键点：这里不是在初始化时缓存 Skill，而是在每次调用 chat() 时重新加载。
        因此运行期间新增或修改 SKILL.md，下一次请求就会带上最新内容。
        """
        if not messages:
            raise ValueError("messages 不能为空")

        skill_prompt = self.skill_loader.build_system_prompt()
        request_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": skill_prompt},
            *messages,
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            "stream": False,
            "thinking": {"type": "enabled" if self.thinking else "disabled"},
            "reasoning_effort": self.reasoning_effort,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        response = self._post_json("/chat/completions", payload)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError(f"API 返回格式异常：{response}") from exc
        if not isinstance(content, str):
            raise DeepSeekError(f"API 未返回文本内容：{response}")
        return content

    def _post_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送 JSON POST 请求；只使用 Python 标准库，不要求安装第三方 SDK。"""
        request = Request(
            f"{self.base_url}{endpoint}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise DeepSeekError(f"DeepSeek API 返回 HTTP {exc.code}: {error_body}") from exc
        except URLError as exc:
            raise DeepSeekError(f"无法连接 DeepSeek API：{exc.reason}") from exc
        except TimeoutError as exc:
            raise DeepSeekError("DeepSeek API 请求超时") from exc

        try:
            result = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise DeepSeekError(f"DeepSeek API 返回了无效 JSON：{raw_body[:500]}") from exc
        if not isinstance(result, dict):
            raise DeepSeekError(f"DeepSeek API 返回类型异常：{type(result).__name__}")
        return result


def parse_extra_skill_roots(raw_value: str) -> list[Path]:
    """从环境变量读取额外 Skill 根目录，多个目录使用系统路径分隔符。"""
    return [Path(item) for item in raw_value.split(os.pathsep) if item.strip()]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="调用 DeepSeek V4 Flash，并在每次请求中自动注入现有 Skills。"
    )
    parser.add_argument("prompt", nargs="?", help="单次提问；不传时进入交互模式")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="项目根目录，默认是本程序目录的上一级",
    )
    parser.add_argument("--no-user-skills", action="store_true", help="不加载用户级 Skills")
    parser.add_argument("--show-skills", action="store_true", help="只列出本次会加载的 Skill 文件")
    parser.add_argument("--no-thinking", action="store_true", help="关闭思考模式")
    parser.add_argument("--reasoning-effort", choices=("high", "max"), default="high")
    parser.add_argument("--max-tokens", type=int, default=None)
    return parser


def run_interactive(client: DeepSeekSkillClient, max_tokens: int | None) -> None:
    """简单的多轮命令行对话；每一轮请求仍会重新加载 Skills。"""
    history: list[dict[str, str]] = []
    print("已连接 DeepSeek V4 Flash。输入 /exit 退出，/clear 清空对话。")
    while True:
        try:
            user_input = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return
        if not user_input:
            continue
        if user_input == "/exit":
            return
        if user_input == "/clear":
            history.clear()
            print("对话已清空。")
            continue

        history.append({"role": "user", "content": user_input})
        try:
            answer = client.chat(history, max_tokens=max_tokens)
        except DeepSeekError:
            # 请求失败时撤回当前用户消息，避免重试时意外重复。
            history.pop()
            raise
        history.append({"role": "assistant", "content": answer})
        print(f"\nDeepSeek> {answer}")


def main(argv: Iterable[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    extra_roots = parse_extra_skill_roots(os.environ.get("EXTRA_SKILL_ROOTS", ""))
    loader = SkillLoader(
        args.project_root,
        include_user_skills=not args.no_user_skills,
        extra_roots=extra_roots,
    )

    if args.show_skills:
        files = loader.load()
        if not files:
            print("没有发现 Skill 文件。")
        for loaded_file in files:
            print(loaded_file.path)
        return 0

    if not api_key:
        print("错误：请先设置 DEEPSEEK_API_KEY。")
        return 2

    client = DeepSeekSkillClient(
        api_key=api_key,
        skill_loader=loader,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        thinking=not args.no_thinking,
        reasoning_effort=args.reasoning_effort,
    )
    try:
        if args.prompt:
            answer = client.chat(
                [{"role": "user", "content": args.prompt}],
                max_tokens=args.max_tokens,
            )
            print(answer)
        else:
            run_interactive(client, args.max_tokens)
    except DeepSeekError as exc:
        print(f"调用失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
