#!/usr/bin/env python3
"""Run Wen Zhao evaluations without importing or starting the web client.

This standard-library-only runner independently implements the same OpenAI-compatible
request contract, message order, and generation parameters as the online version.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
EXISTING_ENV = PROJECT_ROOT / "deepseek-v4-flash-skill-client" / ".env"
TARGET_SKILL = PROJECT_ROOT / "skills" / "wen-zhao-girlfriend"
DEFAULT_ASSESSMENT = HERE / "personality-assessment.json"
DEFAULT_DIALOGUE = HERE / "dialogue-scenarios.json"
DEFAULT_OUTPUT_DIR = HERE / "results"

ONLINE_PROFILE = {
    "request_order": [
        "persona_system_prompt",
        "skill_bundle",
        "web_runtime_prompt",
        "session_memory_optional",
        "live_state_optional",
        "response_guard_prompt",
        "conversation_messages",
    ],
    "thinking": True,
    "reasoning_effort": "high",
    "max_tokens": 8192,
    "timeout_seconds": 150,
    "stream": False,
}


MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def load_env_file(path: Path) -> None:
    """Load an existing dotenv file without overriding exported variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


class SkillLoader:
    """Load one self-contained skill and its Markdown references."""

    def __init__(self, skill_directory: Path) -> None:
        self.skill_directory = skill_directory.resolve()

    def load(self) -> list[tuple[Path, str]]:
        entry = self.skill_directory / "SKILL.md"
        if not entry.is_file():
            raise FileNotFoundError(f"缺少 Skill 入口：{entry}")
        loaded: dict[Path, str] = {}
        self._load_recursive(entry, loaded)
        return list(loaded.items())

    def _load_recursive(self, path: Path, loaded: dict[Path, str]) -> None:
        resolved = path.resolve()
        if resolved in loaded:
            return
        if not resolved.is_relative_to(self.skill_directory):
            raise ValueError(f"Skill 引用越界：{resolved}")
        content = resolved.read_text(encoding="utf-8")
        loaded[resolved] = content
        for raw_target in MARKDOWN_LINK_RE.findall(content):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>\"'")
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith(("#", "mailto:")):
                continue
            referenced = (resolved.parent / target).resolve()
            if referenced.suffix.lower() == ".md" and referenced.is_file():
                self._load_recursive(referenced, loaded)

    def build_system_prompt(self) -> str:
        sections: list[str] = []
        for path, content in self.load():
            display = path.relative_to(PROJECT_ROOT)
            sections.append(
                f"\n--- BEGIN SKILL FILE: {display} ---\n"
                f"{content}\n"
                f"--- END SKILL FILE: {display} ---"
            )
        return "\n".join(sections)


class OpenAIChatClient:
    """Minimal OpenAI-compatible chat client matching the online request payload."""

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float) -> None:
        if not api_key:
            raise ValueError("API Key 为空")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        request = Request(
            f"{self.base_url}/chat/completions",
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
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"模型接口 HTTP {exc.code}: {body[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"无法连接模型接口：{exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("模型接口请求超时") from exc
        try:
            result = json.loads(raw)
            content = result["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"模型接口返回格式异常：{raw[:500]}") from exc
        if not isinstance(content, str):
            raise RuntimeError("模型接口没有返回文本")
        return content


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def render(template: str, **values: str) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    unresolved = re.findall(r"\{[a-z_]+\}", rendered)
    if unresolved:
        raise ValueError(f"模板存在未填变量：{unresolved}")
    return rendered


class JsonlResultStore:
    def __init__(self, path: Path, resume: bool) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.completed: dict[str, dict[str, Any]] = {}
        if resume and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if isinstance(record, dict) and isinstance(record.get("id"), str):
                    self.completed[record["id"]] = record
        elif path.exists():
            # A fresh run must not silently append to an older result set.
            path.write_text("", encoding="utf-8")

    def append(self, record: dict[str, Any]) -> None:
        encoded = json.dumps(record, ensure_ascii=False)
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(encoded + "\n")
            self.completed[record["id"]] = record


def build_loader() -> Any:
    return SkillLoader(TARGET_SKILL)


def build_client(*, model: str, judge: bool = False, judge_model: str = "") -> Any:
    prefix = "EVAL_JUDGE_" if judge else "DEEPSEEK_"
    api_key = os.environ.get(prefix + "API_KEY", "")
    if not api_key and judge:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ValueError(f"缺少 {prefix}API_KEY")
    base_url = os.environ.get(prefix + "BASE_URL", "")
    if not base_url and judge:
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not base_url:
        base_url = "https://api.deepseek.com"
    selected_model = judge_model or (os.environ.get(prefix + "MODEL", "") if judge else model)
    if not selected_model and judge:
        selected_model = model
    return OpenAIChatClient(
        api_key=api_key,
        base_url=base_url,
        model=selected_model,
        timeout=ONLINE_PROFILE["timeout_seconds"],
    )


def build_generation_messages(
    loader: Any,
    runtime: dict[str, str],
    conversation: list[dict[str, str]],
    *,
    memory: str = "",
    live_state: str = "",
) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": runtime["persona_system_prompt"]},
        {"role": "system", "content": loader.build_system_prompt()},
        {"role": "system", "content": runtime["web_runtime_prompt"]},
    ]
    if memory:
        messages.append(
            {
                "role": "system",
                "content": render(runtime["session_memory_prompt_template"], memory=memory),
            }
        )
    if live_state:
        messages.append(
            {
                "role": "system",
                "content": render(runtime["live_state_prompt_template"], live_state=live_state),
            }
        )
    messages.append({"role": "system", "content": runtime["response_guard_prompt"]})
    messages.extend(conversation)
    return messages


def call_with_retry(client: Any, messages: list[dict[str, str]], attempts: int) -> str:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            output = client.complete(messages, max_tokens=ONLINE_PROFILE["max_tokens"])
            if not output.strip():
                raise RuntimeError("模型接口返回空文本")
            return output
        except Exception as exc:  # retain the client's typed error in the result
            last_error = exc
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 8))
    assert last_error is not None
    raise last_error


def parse_assessment_response(output: str) -> tuple[str | None, str]:
    stripped = output.strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        fenced = re.search(r"\{[\s\S]*\}", stripped)
        if fenced:
            try:
                payload = json.loads(fenced.group(0))
            except json.JSONDecodeError:
                payload = None
        else:
            payload = None
    if isinstance(payload, dict):
        choice = str(payload.get("choice", "")).strip().upper()
        reason = str(payload.get("reason", "")).strip()
        if choice in {"A", "B", "C", "D"}:
            return choice, reason
    match = re.search(r"(?:^|\b)([ABCD])(?:\b|[.、：:])", stripped, re.I)
    return (match.group(1).upper(), stripped) if match else (None, stripped)


def score_assessment(item: dict[str, Any], output: str) -> dict[str, Any]:
    choice, reason = parse_assessment_response(output)
    expected = item["expected"]
    if choice == expected["best"]:
        score, verdict = 1.0, "best"
    elif choice in expected.get("acceptable", []):
        score, verdict = 0.5, "acceptable"
    elif choice in expected.get("incompatible", []):
        score, verdict = 0.0, "incompatible"
    else:
        score, verdict = 0.0, "unparseable"
    return {
        "choice": choice,
        "reason": reason,
        "score": score,
        "passed": score >= 0.5,
        "verdict": verdict,
    }


def deterministic_dialogue_checks(output: str, expect: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    text = output.strip()
    length = len(text)
    if "max_chars" in expect and length > int(expect["max_chars"]):
        warnings.append(f"长度{length}超过建议值{expect['max_chars']}")
    if "min_chars" in expect and length < int(expect["min_chars"]):
        failures.append(f"长度{length}少于{expect['min_chars']}")
    questions = len(re.findall(r"[？?]", text))
    if "max_questions" in expect and questions > int(expect["max_questions"]):
        warnings.append(f"问号{questions}个超过建议值{expect['max_questions']}")
    must_any = expect.get("must_include_any", [])
    if must_any and not any(term in text for term in must_any):
        failures.append("未包含任一必需内容：" + "/".join(must_any))
    for term in expect.get("must_not_include", []):
        if term.lower() in text.lower():
            failures.append("包含禁用内容：" + term)
    if expect.get("forbid_unverified_long_numbers"):
        for match in re.findall(r"(?<!\d)(?:\d[\s-]?){5,}\d(?!\d)", text):
            digits = re.sub(r"\D", "", match)
            failures.append("包含未经用例核验的长电话号码：" + digits)
    forbidden_patterns = {
        "stage_direction": r"(?:\([^)]{0,30}\)|（[^）]{0,30}）|\[[^\]]{0,30}\]|【[^】]{0,30}】|\*[^*]{0,60}\*)",
        "markdown_heading": r"(?m)^\s{0,3}#{1,6}\s",
        "speaker_prefix": r"(?m)^\s*(?:闻昭|女友|assistant|助手)\s*[：:]",
        "structured_list": r"(?m)^\s*(?:[-*+] |\d+[.、]\s*)",
    }
    for name, pattern in forbidden_patterns.items():
        if re.search(pattern, text):
            failures.append("命中格式禁项：" + name)
    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
        "characters": length,
        "questions": questions,
    }


def judge_dialogue(
    judge_client: Any,
    runtime: dict[str, str],
    case: dict[str, Any],
    conversation: list[dict[str, str]],
    output: str,
) -> dict[str, Any]:
    payload = {
        "conversation": conversation,
        "candidate": output,
        "observable_expectation": case.get("semantic_expect", {}),
        "forbidden": case.get("expect", {}).get("must_not_include", []),
    }
    messages = [
        {"role": "system", "content": runtime["judge_system_prompt"]},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    last_raw = ""
    for attempt in range(2):
        attempt_messages = list(messages)
        if attempt:
            attempt_messages.append(
                {"role": "system", "content": runtime["judge_retry_prompt"]}
            )
        last_raw = judge_client.complete(
            attempt_messages,
            max_tokens=1024,
            temperature=0,
        )
        try:
            parsed = json.loads(last_raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", last_raw)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    parsed = None
            else:
                parsed = None
        if isinstance(parsed, dict):
            return parsed
    return {
        "passed": False,
        "score": 0,
        "problems": ["评审输出连续两次无法解析"],
        "raw": last_raw,
    }


def judge_dialogue_style(
    judge_client: Any,
    runtime: dict[str, str],
    conversation: list[dict[str, str]],
    output: str,
) -> dict[str, Any]:
    payload = {"conversation": conversation, "candidate": output}
    messages = [
        {"role": "system", "content": runtime["style_judge_system_prompt"]},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    last_raw = ""
    for attempt in range(2):
        attempt_messages = list(messages)
        if attempt:
            attempt_messages.append({"role": "system", "content": runtime["judge_retry_prompt"]})
        last_raw = judge_client.complete(attempt_messages, max_tokens=1024, temperature=0)
        try:
            parsed = json.loads(last_raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", last_raw)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    parsed = None
            else:
                parsed = None
        if isinstance(parsed, dict):
            naturalness = int(parsed.get("naturalness", 0))
            relationship_voice = int(parsed.get("relationship_voice", 0))
            concision = int(parsed.get("concision", 0))
            parsed["passed"] = (
                naturalness >= 3 and relationship_voice >= 3 and concision >= 2
            )
            return parsed
    return {
        "passed": False,
        "naturalness": 0,
        "relationship_voice": 0,
        "concision": 0,
        "stiffness_signals": ["评审输出无法解析"],
        "problems": [last_raw[:300]],
    }


def assessment_prompt(runtime: dict[str, str], item: dict[str, Any]) -> str:
    values = {key: str(value) for key, value in item["choices"].items()}
    values.update(scenario=item["scenario"], question=item["question"])
    return render(runtime["assessment_prompt_template"], **values)


def run_assessment_case(
    item: dict[str, Any],
    loader: Any,
    client: Any,
    runtime: dict[str, str],
    attempts: int,
) -> dict[str, Any]:
    conversation = [{"role": "user", "content": assessment_prompt(runtime, item)}]
    messages = build_generation_messages(loader, runtime, conversation)
    started = time.monotonic()
    output = call_with_retry(client, messages, attempts)
    return {
        "id": item["id"],
        "mode": "assessment",
        "domain": item["domain"],
        "facet": item["facet"],
        "output": output,
        "evaluation": score_assessment(item, output),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def run_dialogue_case(
    case: dict[str, Any],
    loader: Any,
    client: Any,
    runtime: dict[str, str],
    attempts: int,
    judge_client: Any | None,
    semantic_judge: bool,
    style_judge: bool,
) -> dict[str, Any]:
    history: list[dict[str, str]] = []
    for message in case.get("history", []):
        if not isinstance(message, dict):
            raise ValueError(f"{case.get('id')} 的历史消息不是对象")
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            raise ValueError(f"{case.get('id')} 含无效历史消息")
        history.append({"role": role, "content": content})
    outputs: list[str] = []
    started = time.monotonic()
    for user_text in case["turns"]:
        history.append({"role": "user", "content": user_text})
        messages = build_generation_messages(
            loader,
            runtime,
            history,
            memory=case.get("memory", ""),
            live_state=case.get("live_state", ""),
        )
        output = call_with_retry(client, messages, attempts)
        outputs.append(output)
        history.append({"role": "assistant", "content": output})
    final = outputs[-1] if outputs else ""
    deterministic = deterministic_dialogue_checks(final, case.get("expect", {}))
    semantic = (
        judge_dialogue(judge_client, runtime, case, history[:-1], final)
        if judge_client is not None and semantic_judge
        else None
    )
    style = (
        judge_dialogue_style(judge_client, runtime, history[:-1], final)
        if judge_client is not None and style_judge
        else None
    )
    passed = (
        deterministic["passed"]
        and (semantic is None or bool(semantic.get("passed")))
        and (style is None or bool(style.get("passed")))
    )
    return {
        "id": case["id"],
        "mode": "dialogue",
        "category": case.get("category", "uncategorized"),
        "history_messages": len(case.get("history", [])),
        "outputs": outputs,
        "final_output": final,
        "evaluation": {
            "passed": passed,
            "deterministic": deterministic,
            "semantic": semantic,
            "style": style,
        },
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def summarize(records: Iterable[dict[str, Any]], mode: str) -> dict[str, Any]:
    records = list(records)
    if mode == "assessment":
        total_score = sum(float(item.get("evaluation", {}).get("score", 0)) for item in records)
        by_facet: dict[str, dict[str, float]] = {}
        for item in records:
            facet = item.get("facet", "unknown")
            bucket = by_facet.setdefault(facet, {"items": 0, "score": 0.0})
            bucket["items"] += 1
            bucket["score"] += float(item.get("evaluation", {}).get("score", 0))
        for bucket in by_facet.values():
            bucket["rate"] = round(bucket["score"] / max(bucket["items"], 1), 4)
        return {
            "items": len(records),
            "score": total_score,
            "rate": round(total_score / max(len(records), 1), 4),
            "by_facet": by_facet,
        }
    passed = sum(bool(item.get("evaluation", {}).get("passed")) for item in records)
    warning_items = sum(
        bool(item.get("evaluation", {}).get("deterministic", {}).get("warnings"))
        for item in records
    )
    by_category: dict[str, dict[str, Any]] = {}
    for item in records:
        category = item.get("category", "uncategorized")
        bucket = by_category.setdefault(category, {"items": 0, "passed": 0, "style_warning_items": 0})
        bucket["items"] += 1
        bucket["passed"] += int(bool(item.get("evaluation", {}).get("passed")))
        bucket["style_warning_items"] += int(
            bool(item.get("evaluation", {}).get("deterministic", {}).get("warnings"))
        )
    for bucket in by_category.values():
        bucket["rate"] = round(bucket["passed"] / max(bucket["items"], 1), 4)
    return {
        "items": len(records),
        "passed": passed,
        "rate": round(passed / max(len(records), 1), 4),
        "style_warning_items": warning_items,
        "by_category": by_category,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="独立运行闻昭人格与日常对话评测")
    parser.add_argument("--mode", choices=("assessment", "dialogue"), default="assessment")
    parser.add_argument(
        "--model",
        default="deepseek-v4-flash",
        help="被测模型，默认 deepseek-v4-flash；API Key 与 Base URL 复用现有 .env",
    )
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", default="", help="逗号分隔的用例 ID")
    parser.add_argument("--id-prefix", default="", help="只运行 ID 以该文本开头的用例，例如 dx-")
    parser.add_argument("--categories", default="", help="逗号分隔的对话用例分类")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--semantic-judge", action="store_true")
    parser.add_argument("--style-judge", action="store_true", help="额外评审自然度、恋人感与简洁度")
    parser.add_argument("--judge-model", default="", help="独立评审模型；默认使用 EVAL_JUDGE_MODEL，再回退到被测模型")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-profile", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(EXISTING_ENV)
    runtime = load_json(HERE / "runtime-text.json")
    cases_path = args.cases or (
        DEFAULT_ASSESSMENT if args.mode == "assessment" else DEFAULT_DIALOGUE
    )
    if not cases_path.exists():
        print(f"用例文件不存在：{cases_path}", file=sys.stderr)
        return 2
    cases = load_json(cases_path)
    if not isinstance(cases, list):
        print("用例文件必须是 JSON 数组。", file=sys.stderr)
        return 2
    selected_ids = {value.strip() for value in args.ids.split(",") if value.strip()}
    if selected_ids:
        cases = [case for case in cases if case.get("id") in selected_ids]
    if args.id_prefix:
        cases = [case for case in cases if str(case.get("id", "")).startswith(args.id_prefix)]
    selected_categories = {
        value.strip() for value in args.categories.split(",") if value.strip()
    }
    if selected_categories:
        cases = [case for case in cases if case.get("category") in selected_categories]
    if args.limit > 0:
        cases = cases[: args.limit]

    loader = build_loader()
    loaded_files = [str(path.relative_to(PROJECT_ROOT)) for path, _ in loader.load()]
    if args.print_profile or args.dry_run:
        print(
            json.dumps(
                {
                    "online_profile": ONLINE_PROFILE,
                    "model": args.model,
                    "credentials_source": str(EXISTING_ENV.relative_to(PROJECT_ROOT)),
                    "skill_files": loaded_files,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    if args.dry_run:
        print(f"dry-run: {len(cases)} cases from {cases_path}")
        return 0

    try:
        client = build_client(model=args.model)
        judge_client = (
            build_client(model=args.model, judge=True, judge_model=args.judge_model)
            if args.semantic_judge or args.style_judge
            else None
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = args.out or DEFAULT_OUTPUT_DIR / f"{args.mode}-{timestamp}.jsonl"
    store = JsonlResultStore(out_path, args.resume)
    pending = [case for case in cases if case["id"] not in store.completed]
    print(f"运行 {len(pending)} 个用例；已跳过 {len(cases) - len(pending)} 个完成项")

    def execute(case: dict[str, Any]) -> dict[str, Any]:
        if args.mode == "assessment":
            return run_assessment_case(case, loader, client, runtime, args.attempts)
        return run_dialogue_case(
            case,
            loader,
            client,
            runtime,
            args.attempts,
            judge_client,
            args.semantic_judge,
            args.style_judge,
        )

    completed_now = 0
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        future_to_case = {executor.submit(execute, case): case for case in pending}
        for future in as_completed(future_to_case):
            case = future_to_case[future]
            try:
                record = future.result()
            except Exception as exc:
                record = {
                    "id": case["id"],
                    "mode": args.mode,
                    "error": str(exc),
                    "evaluation": {"passed": False, "score": 0},
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                }
            store.append(record)
            completed_now += 1
            evaluation = record.get("evaluation", {})
            status = evaluation.get("verdict") or ("pass" if evaluation.get("passed") else "fail")
            print(f"[{completed_now}/{len(pending)}] {case['id']} {status}")

    ordered = [store.completed[case["id"]] for case in cases if case["id"] in store.completed]
    summary = {
        "mode": args.mode,
        "cases": str(cases_path),
        "results": str(out_path),
        "model": args.model,
        "judge": {
            "enabled": bool(judge_client),
            "model": getattr(judge_client, "model", None),
            "independent_model": bool(judge_client and judge_client.model != client.model),
            "semantic": args.semantic_judge,
            "style": args.style_judge,
        },
        "profile": ONLINE_PROFILE,
        "summary": summarize(ordered, args.mode),
    }
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["summary"], ensure_ascii=False, indent=2))
    print(f"结果：{out_path}\n汇总：{summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
