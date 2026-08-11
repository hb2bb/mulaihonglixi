#!/usr/bin/env python3
"""Convert v3 author-facing rating tables from numbers to named text bands."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
template = ROOT / "templates" / "persona-runtime-template-v3.md"
example = ROOT / "examples" / "女友示例-沈听雨.md"


def convert_template(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    in_rating_table = False
    converted_tables = 0
    converted_rows = 0

    for line in lines:
        if line == "| 等级 | 预设词 | 行为锚点 |":
            output.append("| 文字档位 | 行为锚点 |")
            in_rating_table = True
            converted_tables += 1
            continue
        if in_rating_table and line == "|---:|---|---|":
            output.append("|---|---|")
            continue
        if in_rating_table:
            match = re.fullmatch(r"\| [1-9] \| ([^|]+?) \| (.+) \|", line)
            if match:
                output.append(f"| {match.group(1).strip()} | {match.group(2).strip()} |")
                converted_rows += 1
                continue
            in_rating_table = False
        output.append(line)

    if converted_tables != 57 or converted_rows != 513:
        raise RuntimeError(
            f"unexpected rating-table shape: {converted_tables} tables, {converted_rows} rows"
        )

    text = "\n".join(output) + "\n"
    text = text.replace("**九级行为锚点**", "**九档文字行为锚点**")
    text = text.replace("九级行为锚点", "九档文字行为锚点")
    text = text.replace("九级词典", "九档文字词典")
    text = text.replace("九级量表", "九档文字量表")
    text = text.replace("九级量化", "九档文字定位")
    text = text.replace("统一的九级强度词", "统一的九档程度词")
    text = text.replace("九级定位", "文字档位定位")
    text = text.replace("证据响应性第 6 级", "证据响应性：略响应")
    text = text.replace("九级中的第 6 级", "略响应档")
    text = text.replace("相邻等级", "相邻档位")
    text = text.replace("极端等级", "两端档位")
    text = text.replace("分级描述", "文字分档描述")
    return text


def convert_example(text: str) -> str:
    text, count = re.subn(
        r"\*\*等级选择\*\*：\d+（([^）]+)）",
        lambda match: f"**文字档位**：{match.group(1)}",
        text,
    )
    if count != 45:
        raise RuntimeError(f"expected 45 example ratings, got {count}")
    text = text.replace("等级选择", "文字档位")
    return text


template.write_text(convert_template(template.read_text(encoding="utf-8")), encoding="utf-8")
example.write_text(convert_example(example.read_text(encoding="utf-8")), encoding="utf-8")
print("converted v3 template and example to named text ratings")
