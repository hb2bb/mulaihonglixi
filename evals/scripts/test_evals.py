#!/usr/bin/env python3
"""Unit tests for the shared character evaluation framework."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import run_evaluator


class SharedEvaluationTests(unittest.TestCase):
    def test_skill_loader_always_loads_all_markdown_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill = (Path(temp_dir) / "example-skill").resolve()
            nested = skill / "references" / "nested"
            nested.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# Entry\n", encoding="utf-8")
            (skill / "references" / "a.md").write_text("# A\n", encoding="utf-8")
            (nested / "b.md").write_text("# B\n", encoding="utf-8")
            (nested / "ignored.json").write_text("{}\n", encoding="utf-8")

            loaded = run_evaluator.SkillLoader(skill).load()
            relative_paths = [path.relative_to(skill).as_posix() for path, _ in loaded]

            self.assertEqual(
                relative_paths,
                ["SKILL.md", "references/a.md", "references/nested/b.md"],
            )

    def test_every_profile_renders_the_shared_core(self) -> None:
        for profile_path in sorted(run_evaluator.DEFAULT_PROFILE.parent.glob("*.json")):
            with self.subTest(profile=profile_path.name):
                profile = run_evaluator.load_profile(profile_path)
                core_path = run_evaluator.project_path(
                    profile["datasets"]["core"], field="datasets.core"
                )
                cases = run_evaluator.render_case_value(
                    run_evaluator.load_json(core_path), profile["template_vars"]
                )
                self.assertGreaterEqual(len(cases), 70)
                self.assertNotIn("{{", str(cases))

    def test_deterministic_checks_cover_shared_schema(self) -> None:
        result = run_evaluator.deterministic_dialogue_checks(
            "1. 先做这件事\n2. 再做那件事",
            {
                "numbered_items": 2,
                "must_include_all": ["先做", "再做"],
                "must_not_include": ["第三步"],
            },
            ["测试角色", "助手"],
        )
        self.assertTrue(result["passed"])

    def test_role_speaker_prefix_is_rejected(self) -> None:
        result = run_evaluator.deterministic_dialogue_checks(
            "闻昭：知道了。", {}, ["闻昭", "助手"]
        )
        self.assertFalse(result["passed"])
        self.assertIn("命中格式禁项：speaker_prefix", result["failures"])


if __name__ == "__main__":
    unittest.main()
