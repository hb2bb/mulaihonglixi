#!/usr/bin/env python3
"""将评测 JSONL 结果转换为可读的人工审核 Markdown 文件。

用法:
  python3 evals/scripts/build_human_review.py evals/shen-tingyu/results/core-20260812-001304.jsonl
  python3 evals/scripts/build_human_review.py evals/shen-tingyu/results/core-20260812-001304.jsonl --out evals/shen-tingyu/human-review/
  python3 evals/scripts/build_human_review.py evals/shen-tingyu/results/core-20260812-001304.jsonl --only-failed
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EVALS_DIR = PROJECT_ROOT / "evals"
SHARED_DATASETS = EVALS_DIR / "shared" / "datasets"

CATEGORY_LABELS = {
    "identity": "身份认知",
    "short": "短回复收敛",
    "fact": "事实接收",
    "emotion": "情绪承接",
    "positive": "正面回应",
    "boundary": "边界尊重",
    "memory": "记忆准确性",
    "practical": "实用指令执行",
    "safety": "安全防护",
    "consistency": "一致性",
    "hallucination": "幻觉控制",
    "tone": "语气风格",
    "multi_turn": "多轮连贯",
    "humor": "玩笑应对",
    "fallback": "兜底能力",
    "format": "格式控制",
}


def load_jsonl(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def load_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_dataset_cases(profile_path: Path | None, dataset_path: Path | None) -> dict[str, dict]:
    """加载原始数据集，建立 id -> case 的映射。"""
    if dataset_path and dataset_path.exists():
        cases = load_json(dataset_path)
        return {c["id"]: c for c in cases}

    # 尝试从 profile 推断
    if profile_path and profile_path.exists():
        profile = load_json(profile_path)
        core_path = PROJECT_ROOT / profile.get("datasets", {}).get("core", "")
        if core_path.exists():
            cases = load_json(core_path)
            # 渲染模板变量
            template_vars = profile.get("template_vars", {})
            template_vars["character_name"] = profile.get("character_name", "")
            cases = _render_vars(cases, template_vars)
            return {c["id"]: c for c in cases}

    return {}


def _render_vars(value, variables: dict[str, str]):
    import re
    if isinstance(value, str):
        def replacer(m):
            return variables.get(m.group(1), m.group(0))
        return re.sub(r"\{\{([a-z_][a-z0-9_]*)\}\}", replacer, value)
    if isinstance(value, list):
        return [_render_vars(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: _render_vars(v, variables) for k, v in value.items()}
    return value


def format_case(record: dict, case: dict | None) -> str:
    """格式化单条测试用例为 Markdown。"""
    lines = []
    case_id = record.get("id", "unknown")
    category = record.get("category", "unknown")
    category_label = CATEGORY_LABELS.get(category, category)
    passed = record.get("evaluation", {}).get("passed", False)
    status = "✅ pass" if passed else "❌ fail"

    lines.append(f"### {case_id}")
    lines.append(f"- **类别**: {category_label} (`{category}`)")
    lines.append(f"- **判定**: {status}")

    # 用户输入
    turns = case.get("turns", []) if case else []
    if turns:
        lines.append("")
        lines.append("**用户输入:**")
        for i, turn in enumerate(turns):
            lines.append(f"> {turn}")

    # 模型输出
    outputs = record.get("outputs", [])
    if outputs:
        lines.append("")
        lines.append("**模型输出:**")
        for i, output in enumerate(outputs):
            if len(outputs) > 1:
                lines.append(f"```\n[第{i+1}轮] {output}\n```")
            else:
                lines.append(f"```\n{output}\n```")

    # 自动检查详情
    det = record.get("evaluation", {}).get("deterministic", {})
    failures = det.get("failures", [])
    warnings = det.get("warnings", [])
    if failures:
        lines.append(f"\n**自动检查失败**: {'; '.join(failures)}")
    if warnings:
        lines.append(f"**自动检查警告**: {'; '.join(warnings)}")

    # 统计信息
    chars = det.get("characters", 0)
    questions = det.get("questions", 0)
    emojis = det.get("emojis", 0)
    elapsed = record.get("elapsed_seconds", 0)
    stats_parts = [f"{chars}字"]
    if questions:
        stats_parts.append(f"{questions}个问号")
    if emojis:
        stats_parts.append(f"{emojis}个emoji")
    stats_parts.append(f"{elapsed:.1f}s")
    lines.append(f"\n**统计**: {' | '.join(stats_parts)}")

    # 期望值（用于人工对照）
    if case:
        expect = case.get("expect", {})
        expect_parts = []
        if "max_chars" in expect:
            expect_parts.append(f"≤{expect['max_chars']}字")
        if "max_questions" in expect:
            expect_parts.append(f"≤{expect['max_questions']}个问号")
        if "max_sentences" in expect:
            expect_parts.append(f"≤{expect['max_sentences']}句")
        if "must_include_any" in expect:
            expect_parts.append(f"须含: {'/'.join(expect['must_include_any'])}")
        if "must_not_include" in expect:
            expect_parts.append(f"禁含: {'/'.join(expect['must_not_include'][:5])}")
        if "exact" in expect:
            expect_parts.append(f"精确: {expect['exact']}")
        if "numbered_items" in expect:
            expect_parts.append(f"编号项: {expect['numbered_items']}")
        if expect_parts:
            lines.append(f"\n**期望**: {' | '.join(expect_parts)}")

    # 人工审核占位
    lines.append(f"\n**人工判定**: _____")
    lines.append(f"**备注**: _____")

    lines.append("\n---\n")
    return "\n".join(lines)


def build_summary(records: list[dict]) -> str:
    """生成汇总报告。"""
    total = len(records)
    passed = sum(1 for r in records if r.get("evaluation", {}).get("passed"))
    failed = total - passed
    rate = passed / total * 100 if total else 0

    by_category: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in records:
        cat = r.get("category", "unknown")
        by_category[cat]["total"] += 1
        if r.get("evaluation", {}).get("passed"):
            by_category[cat]["passed"] += 1

    lines = []
    lines.append("# 评测结果人工审核报告")
    lines.append("")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 结果文件: `{total} 条`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 总体统计")
    lines.append("")
    lines.append(f"- **总数**: {total}")
    lines.append(f"- **通过**: {passed} ({rate:.1f}%)")
    lines.append(f"- **失败**: {failed} ({100-rate:.1f}%)")
    lines.append("")
    lines.append("## 按类别统计")
    lines.append("")
    lines.append("| 类别 | 通过/总数 | 通过率 |")
    lines.append("|------|-----------|--------|")
    for cat in sorted(by_category.keys()):
        d = by_category[cat]
        cat_rate = d["passed"] / d["total"] * 100 if d["total"] else 0
        label = CATEGORY_LABELS.get(cat, cat)
        flag = "⚠️" if d["passed"] < d["total"] else "✅"
        lines.append(f"| {flag} {label} | {d['passed']}/{d['total']} | {cat_rate:.0f}% |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 判定标准")
    lines.append("")
    lines.append("- **✅ pass**: 自动检查全部通过")
    lines.append("- **❌ fail**: 存在自动检查失败项（禁含内容、缺少必需内容、格式违规等）")
    lines.append("- **⚠️ warning**: 自动检查通过但有警告（字数偏多、问号偏多等）")
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def build_detail(records: list[dict], cases: dict[str, dict], only_failed: bool) -> str:
    """生成逐条详情。"""
    if only_failed:
        records = [r for r in records if not r.get("evaluation", {}).get("passed")]

    by_category: dict[str, list] = defaultdict(list)
    for r in records:
        by_category[r.get("category", "unknown")].append(r)

    lines = []
    lines.append(f"# 逐条审核 ({len(records)}条)")
    lines.append("")

    for cat in sorted(by_category.keys()):
        items = by_category[cat]
        label = CATEGORY_LABELS.get(cat, cat)
        cat_passed = sum(1 for r in items if r.get("evaluation", {}).get("passed"))
        lines.append(f"## {label} ({cat_passed}/{len(items)} 通过)")
        lines.append("")
        for record in items:
            case = cases.get(record["id"])
            lines.append(format_case(record, case))
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="将评测 JSONL 转换为人工审核 Markdown")
    parser.add_argument("result", type=Path, help="评测结果 JSONL 文件")
    parser.add_argument("--out", type=Path, default=None, help="输出目录，默认为结果文件同目录下 human-review/")
    parser.add_argument("--profile", type=Path, default=None, help="角色 profile JSON，用于加载原始数据集")
    parser.add_argument("--dataset", type=Path, default=None, help="原始数据集 JSON，直接指定")
    parser.add_argument("--only-failed", action="store_true", help="只输出失败的用例")
    args = parser.parse_args()

    if not args.result.exists():
        print(f"结果文件不存在: {args.result}", file=sys.stderr)
        return 1

    # 确定输出目录
    out_dir = args.out or args.result.parent / "human-review"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 加载数据
    records = load_jsonl(args.result)
    cases = load_dataset_cases(args.profile, args.dataset)

    # 生成汇总
    summary = build_summary(records)
    summary_path = out_dir / "00-汇总报告.md"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"✅ {summary_path.name}")

    # 生成详情
    detail = build_detail(records, cases, args.only_failed)
    suffix = "-仅失败项" if args.only_failed else ""
    detail_path = out_dir / f"01-逐条审核{suffix}.md"
    detail_path.write_text(detail, encoding="utf-8")
    print(f"✅ {detail_path.name}")

    # 生成仅失败项（如果全量模式下也想单独看）
    if not args.only_failed:
        failed_records = [r for r in records if not r.get("evaluation", {}).get("passed")]
        if failed_records:
            failed_detail = build_detail(records, cases, only_failed=True)
            failed_path = out_dir / "02-仅失败项.md"
            failed_path.write_text(failed_detail, encoding="utf-8")
            print(f"✅ {failed_path.name}")

    print(f"\n共生成 {len(records)} 条审核记录到 {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
