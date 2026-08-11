#!/usr/bin/env python3
"""Validate schema, balance, coverage, and leakage risks in Wen Zhao eval sets."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


HERE = Path(__file__).resolve().parent
ASSESSMENT = HERE / "personality-assessment.json"
DIALOGUE = HERE / "dialogue-scenarios.json"
REPORT = HERE / "dataset-audit.json"


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def normalized(text: str) -> str:
    return "".join(text.split()).strip("，。！？!?：:；;\"'“”‘’")


def validate_assessment(items: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    require(len(items) >= 200, "人格选择题少于200条", errors)
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
        require(isinstance(case.get("expect"), dict), f"{case.get('id')}缺少确定性规则", errors)
        semantic = case.get("semantic_expect")
        require(isinstance(semantic, dict), f"{case.get('id')}缺少语义规则", errors)
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
    parser = argparse.ArgumentParser(description="审计闻昭人格与对话评测集")
    parser.add_argument("--assessment", type=Path, default=ASSESSMENT)
    parser.add_argument("--dialogue", type=Path, default=DIALOGUE)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--min-dialogue-items", type=int, default=200)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assessment = json.loads(args.assessment.read_text(encoding="utf-8"))
    dialogue = json.loads(args.dialogue.read_text(encoding="utf-8"))
    errors: list[str] = []
    assessment_report = validate_assessment(assessment, errors)
    dialogue_report = validate_dialogue(dialogue, errors, args.min_dialogue_items)
    assessment_text = {normalized(item["scenario"]) for item in assessment}
    dialogue_text = {normalized("|".join(case["turns"])) for case in dialogue}
    leakage_overlap = sorted(assessment_text & dialogue_text)
    require(not leakage_overlap, "人格题与日常对话存在完全相同的测试输入", errors)
    report = {
        "passed": not errors,
        "errors": errors,
        "files": {
            "assessment": str(args.assessment),
            "dialogue": str(args.dialogue),
        },
        "assessment": assessment_report,
        "dialogue": dialogue_report,
        "cross_set_exact_overlap": len(leakage_overlap),
        "interpretation_limits": [
            "这是Skill回归集，不是具有常模、信效度和临床解释力的心理量表。",
            "选择题容易受到选项社会赞许度和长度线索影响，必须与自由对话结果联合解释。",
            "语义评审模型可能有自身偏差，失败项需要查看原始回复后再决定是否修改Skill。",
        ],
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
