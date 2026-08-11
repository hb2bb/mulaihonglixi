#!/usr/bin/env python3
"""
Extract all test questions and model outputs for human review.
Generates consolidated markdown files for each test category.
"""

import json
import os
from pathlib import Path
from collections import defaultdict

RESULTS_DIR = Path(__file__).parent.parent / "results"
OUTPUT_DIR = Path(__file__).parent


def load_jsonl(filepath):
    """Load a JSONL file and return list of records."""
    records = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_json(filepath):
    """Load a JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_dialogue_record(record, index):
    """Format a dialogue record as markdown."""
    lines = []
    lines.append(f"### {record.get('id', f'item-{index}')}")
    lines.append(f"- **类别**: {record.get('category', 'N/A')}")
    lines.append(f"- **来源**: {record.get('source', 'N/A')}")

    if record.get('history_messages'):
        lines.append(f"- **历史消息数**: {record['history_messages']}")

    lines.append("")
    lines.append("**用户输入:**")
    for turn in record.get('user_turns', []):
        lines.append(f"> {turn}")

    lines.append("")
    lines.append("**模型输出:**")
    for output in record.get('model_outputs', []):
        lines.append(f"```\n{output}\n```")

    if record.get('human_verdict'):
        verdict = record['human_verdict']
        verdict_emoji = {
            'pass': '✅',
            'minor': '⚠️',
            'major': '❌',
            'test_issue': '🔧'
        }.get(verdict, '❓')
        lines.append(f"\n**人工判定**: {verdict_emoji} {verdict}")

    if record.get('scores_1_to_5'):
        scores = record['scores_1_to_5']
        lines.append(f"**评分**: 内容={scores.get('content', 'N/A')} | 人格={scores.get('persona', 'N/A')} | 自然度={scores.get('naturalness', 'N/A')}")

    if record.get('issues'):
        lines.append(f"**问题**: {', '.join(record['issues'])}")

    if record.get('issue'):
        lines.append(f"**问题**: {record['issue']}")

    if record.get('suggestion'):
        lines.append(f"**建议**: {record['suggestion']}")

    if record.get('automatic_check_passed') is not None:
        auto = "✅ 通过" if record['automatic_check_passed'] else "❌ 未通过"
        lines.append(f"**自动检查**: {auto}")

    lines.append("\n---\n")
    return "\n".join(lines)


def format_assessment_record(record, index):
    """Format an assessment record as markdown."""
    lines = []
    lines.append(f"### {record.get('id', f'item-{index}')}")
    lines.append(f"- **领域**: {record.get('domain', 'N/A')}")
    lines.append(f"- **侧面**: {record.get('facet', 'N/A')}")

    lines.append("")
    lines.append("**场景:**")
    lines.append(f"> {record.get('scenario', 'N/A')}")

    lines.append("")
    lines.append(f"**模型选择**: {record.get('model_choice', 'N/A')}")
    lines.append(f"**选择理由**: {record.get('model_reason', 'N/A')}")

    if record.get('human_verdict'):
        verdict = record['human_verdict']
        verdict_emoji = {
            'pass': '✅',
            'minor': '⚠️',
            'major': '❌',
            'test_issue': '🔧'
        }.get(verdict, '❓')
        lines.append(f"\n**人工判定**: {verdict_emoji} {verdict}")

    if record.get('content_score_1_to_5'):
        lines.append(f"**内容评分**: {record['content_score_1_to_5']}/5")

    if record.get('issues'):
        lines.append(f"**问题**: {', '.join(record['issues'])}")

    if record.get('suggestion'):
        lines.append(f"**建议**: {record['suggestion']}")

    lines.append("\n---\n")
    return "\n".join(lines)


def generate_summary_report():
    """Generate the main summary report."""
    lines = []
    lines.append("# 闻昭人格评测 - 人工审核汇总报告")
    lines.append("")
    lines.append("> 生成时间: 2026-08-11")
    lines.append("> 模型: deepseek-v4-flash")
    lines.append("> 审核方式: DeepSeek 生成候选回复，主审逐条人工判定，未使用模型裁判")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Load summary data
    summary_file = RESULTS_DIR / "manual-review-summary.json"
    if summary_file.exists():
        summary = load_json(summary_file)
        lines.append("## 总体统计")
        lines.append("")
        lines.append(f"- **总测试条数**: {summary['total_items']}")
        lines.append("")

        # Assessment stats
        assessment = summary['assessment']
        lines.append("### 人格选择题 (260条)")
        lines.append("")
        lines.append(f"| 判定 | 数量 | 占比 |")
        lines.append(f"|------|------|------|")
        for verdict, count in assessment['verdicts'].items():
            pct = f"{count/assessment['items']*100:.1f}%"
            emoji = {'pass': '✅', 'minor': '⚠️'}.get(verdict, '❓')
            lines.append(f"| {emoji} {verdict} | {count} | {pct} |")
        lines.append("")
        lines.append(f"> ⚠️ **局限性**: {assessment['limitation']}")
        lines.append("")

        # Dialogue stats
        dialogue = summary['dialogue']
        lines.append("### 对话题 (520条)")
        lines.append("")
        lines.append(f"| 判定 | 数量 | 占比 |")
        lines.append(f"|------|------|------|")
        for verdict, count in dialogue['verdicts'].items():
            pct = f"{count/dialogue['items']*100:.1f}%"
            emoji = {'pass': '✅', 'minor': '⚠️', 'major': '❌', 'test_issue': '🔧'}.get(verdict, '❓')
            lines.append(f"| {emoji} {verdict} | {count} | {pct} |")
        lines.append("")

        # By source
        lines.append("#### 按数据来源")
        lines.append("")
        lines.append("| 来源 | ✅通过 | ⚠️小问题 | ❌严重问题 | 🔧测试设计问题 |")
        lines.append("|------|--------|----------|-----------|---------------|")
        for source, stats in dialogue['by_source'].items():
            lines.append(f"| {source} | {stats.get('pass', 0)} | {stats.get('minor', 0)} | {stats.get('major', 0)} | {stats.get('test_issue', 0)} |")
        lines.append("")

        # By category
        lines.append("#### 按测试类别")
        lines.append("")
        lines.append("| 类别 | ✅通过 | ⚠️小问题 | ❌严重问题 | 🔧测试设计问题 |")
        lines.append("|------|--------|----------|-----------|---------------|")
        for category, stats in dialogue['by_category'].items():
            lines.append(f"| {category} | {stats.get('pass', 0)} | {stats.get('minor', 0)} | {stats.get('major', 0)} | {stats.get('test_issue', 0)} |")
        lines.append("")

        # Issue counts
        lines.append("### 主要问题分布")
        lines.append("")
        lines.append("| 问题类型 | 出现次数 |")
        lines.append("|----------|----------|")
        for issue, count in dialogue['issue_counts'].items():
            lines.append(f"| {issue} | {count} |")
        lines.append("")

    # Postfix summary
    postfix_file = RESULTS_DIR / "manual-review-postfix-summary.json"
    if postfix_file.exists():
        postfix = load_json(postfix_file)
        lines.append("## 修改后定向回归测试")
        lines.append("")
        lines.append("| 轮次 | ✅通过 | ⚠️小问题 | ❌严重问题 |")
        lines.append("|------|--------|----------|-----------|")
        for round_name, stats in postfix['rounds'].items():
            lines.append(f"| {round_name} | {stats.get('pass', 0)} | {stats.get('minor', 0)} | {stats.get('major', 0)} |")
        lines.append("")
        lines.append(f"> **最终状态**: {postfix['final_targeted_status']}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 详细数据文件")
    lines.append("")
    lines.append("本文件夹包含以下详细审核文件：")
    lines.append("")
    lines.append("1. **assessment-review.md** - 260条人格选择题逐条审核")
    lines.append("2. **dialogue-baseline-review.md** - 260条基础对话逐条审核")
    lines.append("3. **dialogue-stress-review.md** - 压力对话逐条审核")
    lines.append("4. **dialogue-long-context-review.md** - 长上下文对话逐条审核")
    lines.append("5. **postfix-review.md** - 修改后定向回归测试逐条审核")
    lines.append("")
    lines.append("每条记录包含：用户输入、模型输出、人工判定、评分、问题和建议。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 判定标准")
    lines.append("")
    lines.append("- **pass** ✅: 当前回复可直接保留，不代表同类场景永远稳定")
    lines.append("- **minor** ⚠️: 内容大体成立，但自然度、格式或人物辨识度需要收紧")
    lines.append("- **major** ❌: 存在事实/记忆/安全/边界/现实能力或核心语义错误")
    lines.append("- **test_issue** 🔧: 题目要求了当前纯聊天产品无法兑现的能力")

    return "\n".join(lines)


def generate_assessment_review():
    """Generate assessment review file."""
    records = load_jsonl(RESULTS_DIR / "manual-review-assessment-260.jsonl")

    lines = []
    lines.append("# 人格选择题审核 (260条)")
    lines.append("")
    lines.append("> 每条记录包含：场景、模型选择、选择理由、人工判定和评分")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Group by domain
    by_domain = defaultdict(list)
    for r in records:
        by_domain[r.get('domain', '未分类')].append(r)

    for domain, items in by_domain.items():
        lines.append(f"## {domain}")
        lines.append("")
        for i, record in enumerate(items, 1):
            lines.append(format_assessment_record(record, i))
        lines.append("")

    return "\n".join(lines)


def generate_dialogue_review(source_filter=None, title_suffix=""):
    """Generate dialogue review file."""
    records = load_jsonl(RESULTS_DIR / "manual-review-dialogue-520.jsonl")

    if source_filter:
        records = [r for r in records if r.get('source') == source_filter]

    lines = []
    lines.append(f"# 对话题审核{title_suffix} ({len(records)}条)")
    lines.append("")
    lines.append("> 每条记录包含：用户输入、模型输出、人工判定、评分、问题和建议")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Group by category
    by_category = defaultdict(list)
    for r in records:
        by_category[r.get('category', '未分类')].append(r)

    for category, items in by_category.items():
        lines.append(f"## {category}")
        lines.append("")
        for i, record in enumerate(items, 1):
            lines.append(format_dialogue_record(record, i))
        lines.append("")

    return "\n".join(lines)


def generate_postfix_review():
    """Generate postfix review file."""
    records = load_jsonl(RESULTS_DIR / "manual-review-postfix-73.jsonl")

    lines = []
    lines.append(f"# 修改后定向回归测试审核 ({len(records)}条)")
    lines.append("")
    lines.append("> 包含 v4/v5/v6 三轮修改后的复测结果")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Group by round
    by_round = defaultdict(list)
    for r in records:
        by_round[r.get('round', 'unknown')].append(r)

    for round_name, items in by_round.items():
        lines.append(f"## {round_name}")
        lines.append("")
        for i, record in enumerate(items, 1):
            lines.append(format_dialogue_record(record, i))
        lines.append("")

    return "\n".join(lines)


def main():
    """Generate all review files."""
    print("Generating human review files...")

    # Summary report
    summary = generate_summary_report()
    with open(OUTPUT_DIR / "00-汇总报告.md", 'w', encoding='utf-8') as f:
        f.write(summary)
    print("✅ 00-汇总报告.md")

    # Assessment review
    assessment = generate_assessment_review()
    with open(OUTPUT_DIR / "01-人格选择题审核.md", 'w', encoding='utf-8') as f:
        f.write(assessment)
    print("✅ 01-人格选择题审核.md")

    # Dialogue baseline review
    baseline = generate_dialogue_review(source_filter='baseline', title_suffix=' - 基础对话')
    with open(OUTPUT_DIR / "02-基础对话审核.md", 'w', encoding='utf-8') as f:
        f.write(baseline)
    print("✅ 02-基础对话审核.md")

    # Dialogue stress review
    stress = generate_dialogue_review(source_filter='stress', title_suffix=' - 压力对话')
    with open(OUTPUT_DIR / "03-压力对话审核.md", 'w', encoding='utf-8') as f:
        f.write(stress)
    print("✅ 03-压力对话审核.md")

    # Dialogue long context review
    long_context = generate_dialogue_review(source_filter='long_context', title_suffix=' - 长上下文对话')
    with open(OUTPUT_DIR / "04-长上下文对话审核.md", 'w', encoding='utf-8') as f:
        f.write(long_context)
    print("✅ 04-长上下文对话审核.md")

    # Postfix review
    postfix = generate_postfix_review()
    with open(OUTPUT_DIR / "05-修改后回归测试审核.md", 'w', encoding='utf-8') as f:
        f.write(postfix)
    print("✅ 05-修改后回归测试审核.md")

    print("\n✅ 所有审核文件已生成到:", OUTPUT_DIR)
    print("\n文件列表:")
    for f in sorted(OUTPUT_DIR.glob("*.md")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
