"""不访问网络的本地测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deepseek_skill_client import DeepSeekSkillClient, SkillLoader
from web_server import (
    RUNTIME_TEXT,
    RateLimiter,
    generate_reviewed_reply,
    normalize_session_memory,
    update_session_memory,
    validate_messages,
)


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class SkillLoaderTests(unittest.TestCase):
    def test_loads_skill_and_local_markdown_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_dir = root / "skills" / "demo"
            references = skill_dir / "references"
            references.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "# Demo\n请阅读 [规则](references/rules.md)。", encoding="utf-8"
            )
            (references / "rules.md").write_text("必须写测试。", encoding="utf-8")

            loader = SkillLoader(root, include_user_skills=False)
            loaded = loader.load()

            self.assertEqual(2, len(loaded))
            self.assertIn("必须写测试。", loader.build_system_prompt())

    def test_each_chat_reloads_modified_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_dir = root / "skills" / "demo"
            skill_dir.mkdir(parents=True)
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text("第一版", encoding="utf-8")
            loader = SkillLoader(root, include_user_skills=False)
            client = DeepSeekSkillClient("test-key", loader)
            captured_payloads: list[dict] = []

            def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
                captured_payloads.append(json.loads(request.data.decode("utf-8")))
                return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

            with patch("deepseek_skill_client.urlopen", side_effect=fake_urlopen):
                client.chat([{"role": "user", "content": "你好"}])
                skill_file.write_text("第二版", encoding="utf-8")
                client.chat([{"role": "user", "content": "再来一次"}])

            first_system = next(
                message["content"]
                for message in captured_payloads[0]["messages"]
                if message["role"] == "system"
            )
            second_system = next(
                message["content"]
                for message in captured_payloads[1]["messages"]
                if message["role"] == "system"
            )
            self.assertIn("第一版", first_system)
            self.assertIn("第二版", second_system)
            self.assertNotIn("第一版", second_system)
            self.assertEqual("deepseek-v4-pro", captured_payloads[1]["model"])

    def test_chat_injects_additional_runtime_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_dir = root / "skills" / "demo"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("角色规则", encoding="utf-8")
            client = DeepSeekSkillClient("test-key", SkillLoader(root, include_user_skills=False))
            captured_payloads: list[dict] = []

            def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
                captured_payloads.append(json.loads(request.data.decode("utf-8")))
                return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

            with patch("deepseek_skill_client.urlopen", side_effect=fake_urlopen):
                client.chat(
                    [{"role": "user", "content": "你好"}],
                    additional_system_messages=(
                        "- 用户喜欢推理",
                        "- 角色心情：平静",
                    ),
                )

            contents = [message["content"] for message in captured_payloads[0]["messages"]]
            self.assertTrue(any("用户喜欢推理" in content for content in contents))
            self.assertTrue(any("角色心情：平静" in content for content in contents))

    def test_generic_state_client_omits_deepseek_reasoning_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = DeepSeekSkillClient(
                "state-key",
                SkillLoader(Path(directory), include_user_skills=False),
                base_url="https://state.example.com",
                model="state-model",
                include_reasoning_options=False,
            )
            captured_payloads: list[dict] = []

            def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
                captured_payloads.append(json.loads(request.data.decode("utf-8")))
                return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

            with patch("deepseek_skill_client.urlopen", side_effect=fake_urlopen):
                client.complete([{"role": "user", "content": "生成状态"}], max_tokens=600)

            payload = captured_payloads[0]
            self.assertEqual("state-model", payload["model"])
            self.assertNotIn("thinking", payload)
            self.assertNotIn("reasoning_effort", payload)


class WebServerTests(unittest.TestCase):
    def test_validates_normal_conversation(self) -> None:
        messages = [{"role": "user", "content": "你好"}]
        self.assertEqual(messages, validate_messages(messages))

    def test_rejects_unknown_message_role(self) -> None:
        self.assertIsNone(validate_messages([{"role": "system", "content": "越权内容"}]))

    def test_accepts_up_to_200_messages(self) -> None:
        messages = [{"role": "user", "content": "x"} for _ in range(200)]
        self.assertEqual(messages, validate_messages(messages))

    def test_rejects_more_than_200_messages(self) -> None:
        messages = [{"role": "user", "content": "x"} for _ in range(201)]
        self.assertIsNone(validate_messages(messages))

    def test_rate_limiter_blocks_excess_requests(self) -> None:
        limiter = RateLimiter(limit=2, window_seconds=60)
        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertFalse(limiter.allow("127.0.0.1"))

    def test_normalizes_session_memory_to_twelve_bullets(self) -> None:
        raw = "\n".join(f"item {index}" for index in range(20))
        normalized = normalize_session_memory(raw)
        self.assertIsNotNone(normalized)
        self.assertEqual(12, len(normalized.splitlines()))
        self.assertTrue(all(line.startswith("- ") for line in normalized.splitlines()))

    def test_updates_session_memory_from_strict_json(self) -> None:
        class FakeClient:
            def complete(self, messages, max_tokens):  # type: ignore[no-untyped-def]
                self.messages = messages
                self.max_tokens = max_tokens
                return '{"memory":"- 用户喜欢推理\\n- 不喜欢长回复"}'

        client = FakeClient()
        memory = update_session_memory(
            client,  # type: ignore[arg-type]
            [{"role": "user", "content": "我喜欢推理"}],
            "",
        )
        self.assertEqual("- 用户喜欢推理\n- 不喜欢长回复", memory)
        self.assertEqual(1_200, client.max_tokens)

    def test_review_passes_first_candidate_without_regeneration(self) -> None:
        class FakeChatClient:
            def __init__(self) -> None:
                self.runtime_messages: list[list[str]] = []

            def chat(self, messages, **kwargs):  # type: ignore[no-untyped-def]
                self.runtime_messages.append(list(kwargs.get("additional_system_messages", ())))
                return "第一份候选"

        class FakeReviewClient:
            def complete(self, messages, max_tokens):  # type: ignore[no-untyped-def]
                return '{"approved":true,"problems":""}'

        chat_client = FakeChatClient()
        content, debug = generate_reviewed_reply(
            chat_client,  # type: ignore[arg-type]
            FakeReviewClient(),  # type: ignore[arg-type]
            "检测 Skill",
            [{"role": "user", "content": "你好"}],
            "",
            "",
        )
        self.assertEqual("第一份候选", content)
        self.assertEqual(1, len(chat_client.runtime_messages))
        self.assertNotIn("previous-candidate", "\n".join(chat_client.runtime_messages[0]))
        self.assertEqual(1, debug["selected_attempt"])

    def test_review_retries_twice_then_selector_picks_existing_candidate(self) -> None:
        class FakeChatClient:
            def __init__(self) -> None:
                self.runtime_messages: list[list[str]] = []

            def chat(self, messages, **kwargs):  # type: ignore[no-untyped-def]
                self.runtime_messages.append(list(kwargs.get("additional_system_messages", ())))
                return f"候选{len(self.runtime_messages)}"

        class FakeReviewClient:
            def __init__(self) -> None:
                self.review_count = 0

            def complete(self, messages, max_tokens):  # type: ignore[no-untyped-def]
                if "最终候选选择器" in messages[0]["content"]:
                    return '{"selected":2}'
                self.review_count += 1
                return '{"approved":false,"problems":"回复太长"}'

        chat_client = FakeChatClient()
        review_client = FakeReviewClient()
        content, debug = generate_reviewed_reply(
            chat_client,  # type: ignore[arg-type]
            review_client,  # type: ignore[arg-type]
            "检测 Skill",
            [{"role": "user", "content": "你好"}],
            "",
            "",
        )
        self.assertEqual("候选2", content)
        self.assertEqual(3, len(chat_client.runtime_messages))
        self.assertNotIn("回复太长", "\n".join(chat_client.runtime_messages[0]))
        self.assertIn("回复太长", "\n".join(chat_client.runtime_messages[1]))
        self.assertEqual(3, review_client.review_count)
        self.assertEqual(2, debug["selected_attempt"])
        self.assertEqual(3, len(debug["candidates"]))

    def test_runtime_model_text_comes_from_chinese_skill_resource(self) -> None:
        self.assertIn("发送前审查器", RUNTIME_TEXT["review_system_prompt"])
        self.assertIn("{candidate}", RUNTIME_TEXT["revision_feedback_template"])


if __name__ == "__main__":
    unittest.main()
