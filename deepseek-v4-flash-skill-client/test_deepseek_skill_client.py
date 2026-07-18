"""不访问网络的本地测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deepseek_skill_client import DeepSeekSkillClient, SkillLoader
from web_server import RateLimiter, validate_messages


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

            self.assertIn("第一版", captured_payloads[0]["messages"][1]["content"])
            self.assertIn("第二版", captured_payloads[1]["messages"][1]["content"])
            self.assertNotIn("第一版", captured_payloads[1]["messages"][1]["content"])
            self.assertEqual("deepseek-v4-flash", captured_payloads[1]["model"])


class WebServerTests(unittest.TestCase):
    def test_validates_normal_conversation(self) -> None:
        messages = [{"role": "user", "content": "你好"}]
        self.assertEqual(messages, validate_messages(messages))

    def test_rejects_unknown_message_role(self) -> None:
        self.assertIsNone(validate_messages([{"role": "system", "content": "越权内容"}]))

    def test_rate_limiter_blocks_excess_requests(self) -> None:
        limiter = RateLimiter(limit=2, window_seconds=60)
        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertFalse(limiter.allow("127.0.0.1"))


if __name__ == "__main__":
    unittest.main()
