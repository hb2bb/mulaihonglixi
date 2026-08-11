#!/usr/bin/env python3
"""Validate shared and role-specific character evaluation datasets."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


HERE = Path(__file__).resolve().parent
EVALS_DIR = HERE.parent
PROJECT_ROOT = EVALS_DIR.parent
ROLES_DIR = EVALS_DIR / "roles"
SHARED_CORE = EVALS_DIR / "shared" / "datasets" / "dialogue-core.json"
REPORT = EVALS_DIR / "shared" / "dataset-audit.json"
ALLOWED_EXPECT_FIELDS = {
    "consistency_with",
    "exact",
    "forbid_unverified_long_numbers",
    "max_chars",
    "max_emoji",
    "max_questions",
    "max_sentences",
    "min_chars",
    "must_include_all",
    "must_include_any",
    "must_not_include",
    "numbered_items",
}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def normalized(text: str) -> str:
    return "".join(text.split()).strip("，。！？!?：:；;\"'“”‘’")


def validate_assessment(
    items: list[dict[str, Any]], errors: list[str], min_items: int = 1
) -> dict[str, Any]:
    require(len(items) >= min_items, f"人格选择题少于{min_items}条", errors)
    ids = [item.get("id") for item in items]
    require(len(ids) == len(set(ids)), "人格选择题存在重复ID", errors)
    facets = Counter(item.get("facet") for item in items)
    scenarios = [normalized(str(item.get("scenario", ""))) for item in items]
    require(len(scenarios) == len(set(scenarios)), "人格选择题存在完全重复情境", errors)
    best_letters: Counter[str] = Counter()
    best_lengths: list[int] = []
    other_lengths: list[int] = []
    for item in items:
        choices = item.get("choices", {})
        require(set(choices) == {"A", "B", "C", "D"}, f"{item.get('id')}选项不完整", errors)
        expected = item.get("expected", {})
        best = expected.get("best")
        require(best in choices, f"{item.get('id')}最优答案无效", errors)
        require(bool(expected.get("rationale")), f"{item.get('id')}缺少评分理由", errors)
        if best in choices:
            best_letters[best] += 1
            best_lengths.append(len(choices[best]))
            other_lengths.extend(len(value) for key, value in choices.items() if key != best)
    if best_letters:
        require(
            max(best_letters.values()) - min(best_letters.values()) <= 2,
            f"最优答案位置不均衡：{dict(best_letters)}",
            errors,
        )
    return {
        "items": len(items),
        "facets": len(facets),
        "items_per_facet": dict(facets),
        "best_letter_distribution": dict(best_letters),
        "average_best_option_chars": round(mean(best_lengths), 2),
        "average_other_option_chars": round(mean(other_lengths), 2),
        "exact_duplicate_scenarios": len(scenarios) - len(set(scenarios)),
    }


def validate_dialogue(
    cases: list[dict[str, Any]], errors: list[str], min_items: int = 200
) -> dict[str, Any]:
    require(len(cases) >= min_items, f"日常对话用例少于{min_items}条", errors)
    ids = [case.get("id") for case in cases]
    require(len(ids) == len(set(ids)), "日常对话存在重复ID", errors)
    categories = Counter(case.get("category") for case in cases)
    stress_tags: Counter[str] = Counter()
    history_lengths: Counter[int] = Counter()
    signatures: list[str] = []
    for case in cases:
        turns = case.get("turns")
        require(isinstance(turns, list) and bool(turns), f"{case.get('id')}没有有效轮次", errors)
        expect = case.get("expect")
        require(isinstance(expect, dict), f"{case.get('id')}缺少确定性规则", errors)
        if isinstance(expect, dict):
            unknown_expect = set(expect) - ALLOWED_EXPECT_FIELDS
            require(not unknown_expect, f"{case.get('id')}含未知expect字段：{sorted(unknown_expect)}", errors)
            consistency_index = expect.get("consistency_with")
            if consistency_index is not None:
                require(isinstance(consistency_index, int), f"{case.get('id')}的consistency_with必须是整数", errors)
                if isinstance(consistency_index, int) and isinstance(turns, list):
                    require(0 <= consistency_index < len(turns) - 1, f"{case.get('id')}的consistency_with未指向此前回复", errors)
        semantic = case.get("semantic_expect")
        if semantic is not None:
            require(isinstance(semantic, dict), f"{case.get('id')}语义规则必须是对象", errors)
        if isinstance(semantic, dict):
            require(bool(semantic.get("must_demonstrate")), f"{case.get('id')}缺少正向语义标准", errors)
            require(bool(semantic.get("must_avoid")), f"{case.get('id')}缺少负向语义标准", errors)
        signatures.append(normalized("|".join(str(turn) for turn in turns or [])))
        stress_tags.update(str(tag) for tag in case.get("stress_tags", []))
        history = case.get("history", [])
        require(isinstance(history, list), f"{case.get('id')}历史消息必须是数组", errors)
        if isinstance(history, list):
            history_lengths[len(history)] += 1
            previous_role = None
            for index, message in enumerate(history):
                require(isinstance(message, dict), f"{case.get('id')}第{index + 1}条历史无效", errors)
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                require(role in {"user", "assistant"}, f"{case.get('id')}历史角色无效", errors)
                require(isinstance(message.get("content"), str) and bool(message.get("content", "").strip()), f"{case.get('id')}历史内容为空", errors)
                if previous_role is not None:
                    require(role != previous_role, f"{case.get('id')}历史角色未交替", errors)
                previous_role = role
            if history:
                require(history[0].get("role") == "user", f"{case.get('id')}历史必须从user开始", errors)
                require(history[-1].get("role") == "assistant", f"{case.get('id')}历史必须以assistant结束", errors)
    require(len(signatures) == len(set(signatures)), "日常对话存在完全重复对话", errors)
    return {
        "items": len(cases),
        "categories": len(categories),
        "items_per_category": dict(categories),
        "single_turn": sum(len(case["turns"]) == 1 for case in cases),
        "multi_turn": sum(len(case["turns"]) > 1 for case in cases),
        "expanded_cases": sum(str(case.get("id", "")).startswith("dx-") for case in cases),
        "stress_tag_distribution": dict(stress_tags),
        "history_length_distribution": {str(key): value for key, value in sorted(history_lengths.items())},
        "long_context_cases": sum(len(case.get("history", [])) >= 10 for case in cases),
        "exact_duplicate_dialogues": len(signatures) - len(set(signatures)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计共享评测集与所有角色 profile")
    parser.add_argument(
        "--profile",
        type=Path,
        action="append",
        default=[],
        help="只检查指定 profile；可重复。默认检查 evals/roles 下全部 profile",
    )
    parser.add_argument("--report", type=Path, default=REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    errors: list[str] = []
    profile_paths = args.profile or sorted(ROLES_DIR.glob("*.json"))
    require(bool(profile_paths), "没有找到角色 profile", errors)
    dataset_reports: dict[str, Any] = {}
    profile_reports: dict[str, Any] = {}
    checked_paths: set[Path] = set()

    for profile_path in profile_paths:
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"无法读取 profile {profile_path}：{exc}")
            continue
        profile_id = str(profile.get("id", profile_path.stem))
        skill = (PROJECT_ROOT / str(profile.get("skill", ""))).resolve()
        require(profile.get("schema_version") == 1, f"{profile_id}的schema_version必须为1", errors)
        require(bool(re.fullmatch(r"[a-z0-9-]+", profile_id)), f"{profile_id}不是合法profile id", errors)
        require(bool(profile.get("character_name")), f"{profile_id}缺少character_name", errors)
        require((skill / "SKILL.md").is_file(), f"{profile_id}的Skill不存在：{skill}", errors)
        datasets = profile.get("datasets")
        require(isinstance(datasets, dict), f"{profile_id}的datasets必须是对象", errors)
        if not isinstance(datasets, dict):
            continue
        unknown_modes = set(datasets) - {"core", "assessment", "dialogue", "regression"}
        require(not unknown_modes, f"{profile_id}含未知数据集类型：{sorted(unknown_modes)}", errors)
        require(datasets.get("core") == "evals/shared/datasets/dialogue-core.json", f"{profile_id}未使用共享core数据集", errors)
        profile_reports[profile_id] = {
            "character_name": profile.get("character_name"),
            "skill": str(profile.get("skill", "")),
            "datasets": sorted(datasets),
        }
        for mode, relative in datasets.items():
            dataset_path = (PROJECT_ROOT / str(relative)).resolve()
            require(dataset_path.is_relative_to(PROJECT_ROOT), f"{profile_id}.{mode}路径越界", errors)
            if dataset_path in checked_paths:
                continue
            checked_paths.add(dataset_path)
            try:
                items = json.loads(dataset_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"无法读取数据集 {dataset_path}：{exc}")
                continue
            require(isinstance(items, list), f"{relative}必须是JSON数组", errors)
            if not isinstance(items, list):
                continue
            local_errors: list[str] = []
            if mode == "assessment":
                report = validate_assessment(items, local_errors)
            else:
                report = validate_dialogue(items, local_errors, min_items=1)
            if local_errors:
                errors.extend(f"{relative}: {message}" for message in local_errors)
            dataset_reports[str(relative)] = {"mode": mode, **report}

    if SHARED_CORE.is_file():
        shared_text = SHARED_CORE.read_text(encoding="utf-8")
        for role_name in ("闻昭", "沈听雨", "宁知夏", "葛城真冬", "真冬"):
            require(role_name not in shared_text, f"共享core仍硬编码角色名：{role_name}", errors)
        placeholders = set(re.findall(r"\{\{([a-z_][a-z0-9_]*)\}\}", shared_text))
        require(placeholders <= {"character_name"}, f"共享core含未知变量：{sorted(placeholders)}", errors)

    report = {
        "passed": not errors,
        "errors": errors,
        "profiles": profile_reports,
        "datasets": dataset_reports,
        "interpretation_limits": [
            "这是Skill回归集，不是具有常模、信效度和临床解释力的心理量表。",
            "选择题容易受到选项社会赞许度和长度线索影响，必须与自由对话结果联合解释。",
            "语义评审模型可能有自身偏差，失败项需要查看原始回复后再决定是否修改Skill。",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
