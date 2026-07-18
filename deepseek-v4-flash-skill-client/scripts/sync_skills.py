#!/usr/bin/env python3
"""把当前 Skills 编译成网站后端可导入的 TypeScript 常量。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 让脚本从 scripts/ 子目录运行时也能导入项目根目录中的客户端模块。
site_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(site_root))

# 复用命令行客户端的加载器，确保网站版和 Python 版遵守同一套扫描规则。
from deepseek_skill_client import SkillLoader


def main() -> None:
    project_root = site_root.parent
    loader = SkillLoader(project_root, include_user_skills=True)
    loaded_files = loader.load()
    bundle = loader.build_system_prompt()
    relative_names: list[str] = []
    for loaded_file in loaded_files:
        try:
            name = str(loaded_file.path.relative_to(project_root))
        except ValueError:
            name = str(loaded_file.path)
        relative_names.append(name)

    # JSON 字符串本身也是合法的 TypeScript 字符串，能安全处理换行和反引号。
    output = (
        "// 此文件由 scripts/sync_skills.py 自动生成，请勿手动修改。\n"
        f"export const SKILL_BUNDLE = {json.dumps(bundle, ensure_ascii=False)};\n"
        f"export const SKILL_FILES = {json.dumps(relative_names, ensure_ascii=False)} as const;\n"
        f"export const SKILL_FILE_COUNT = {len(relative_names)};\n"
    )
    target = site_root / "lib" / "skill-bundle.generated.ts"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(output, encoding="utf-8")
    print(f"已同步 {len(relative_names)} 个 Skill 文件。")


if __name__ == "__main__":
    main()
