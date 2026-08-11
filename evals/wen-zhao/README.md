# 闻昭人格 Skill 评测归档

通用入口、共享核心集与新增角色说明见 [`evals/README.md`](../README.md)。本目录只保留闻昭专属的人格标定题、扩展对话、定向回归、结果和人工审核记录。

## 目录结构

```
evals/wen-zhao/
├── README.md                    # 本文件
├── datasets/                    # 📝 试题数据
│   ├── personality-assessment.json      # 260道人格选择题
│   ├── dialogue-scenarios.json          # 260条基础对话场景
│   ├── dialogue-scenarios-v2.json       # 对话场景扩展版
│   ├── dialogue-targeted-regression-v4.json  # 定向回归测试 v4 (60条)
│   ├── dialogue-targeted-regression-v5.json  # 定向回归测试 v5 (12条)
│   ├── dialogue-targeted-regression-v6.json  # 定向回归测试 v6 (1条)
│   └── dialogue-long-context-v3.json    # 长上下文对话 (130条)
├── audits/                      # 🔎 历史数据集审计报告
│   └── dataset-audit*.json
├── scripts/                     # 🖥️ 测试代码
│   ├── run_evaluator.py                 # 主测试运行器
│   ├── generate_personality_assessment.py  # 生成人格评估题
│   ├── generate_dialogue_scenarios.py   # 生成对话场景
│   ├── generate_dialogue_expansion_v2.py  # 生成扩展对话
│   ├── generate_targeted_regression_v4.py  # 生成定向回归测试 v4
│   ├── generate_targeted_regression_v5.py  # 生成定向回归测试 v5
│   ├── generate_long_context_dialogues_v3.py  # 生成长上下文对话
│   ├── validate_datasets.py             # 数据集校验
│   ├── build_manual_review.py           # 构建人工审核文件
│   └── build_postfix_review.py          # 构建修复后审核文件
├── results/                     # 📊 测试结果
│   ├── *.jsonl                          # 原始测试输出
│   ├── *.summary.json                   # 统计摘要
│   └── manual-review-*.jsonl            # 人工审核结论
└── human-review/                # 👁️ 人工审核报告
    └── *.md
```

## 第一阶段：人格选择题

`datasets/personality-assessment.json` 是一套原创的角色一致性评测，不是临床量表，也没有人群常模。它把专业测量框架中的构念改写为适合语言模型的情境强迫选择题，不逐字复制受版权限制的量表题项。

覆盖 26 个侧面，每个侧面 10 题，共 260 题：

- 稳定人格：低风险探索、高风险探索、重要计划、日常灵活、陌生社交、亲密社交、有边界合作、越界后撤回合作；
- 情绪过程：危机中的暂时稳定、危机后的迟发反应；
- 认知判断：一般证据更新、背叛威胁下核实、对含糊与真实的处理；
- 价值关系：自主与关心、承诺责任、偏爱与第三方公平；
- 亲密关系：亲近与独立、关系威胁、低强度冲突、高唤醒暂停、支持方式、嫉妒边界；
- 人物辨识：准确浪漫、事实与感受双轨校准、控制行为修复、具体返回承诺。

每题有"最符合""尚可但不够准确""明显不符""漫画式过度表现"四种内部角色；生成器轮换实际选项顺序，防止固定字母取巧。

## 构念来源

- [IPIP](https://ipip.ori.org/)：公开领域的人格项目池，提供大五及窄侧面构念。
- [HEXACO-PI-R](https://hexaco.org/history)：六个宽人格因素及其窄侧面，用于补充诚实谦逊、情绪性和利他行为。
- [ECR-RS](https://pubmed.ncbi.nlm.nih.gov/21443364/)：把依恋焦虑与回避建模为关系特异的工作模式。
- [ERQ](https://spl.stanford.edu/sites/g/files/biybj19321/files/media/file/english_0.pdf)：区分认知重评与表达压抑，用于设计危机中压低表达和事后反弹。
- [Thomas–Kilmann](https://asia.themyersbriggs.com/instruments/tki/history-and-validity-of-the-thomas-kilmann-conflict-mode-instrument/)：竞争、合作、妥协、回避和迁就五类冲突处理方式。
- [认知闭合需求](https://www.kruglanskiarie.com/need-for-closure)：对秩序、可预测性、确定性和模糊的态度。
- Schwartz 等人的精细化基本价值理论：用于自主、责任、公平、关怀与安全之间的取舍。

## 评分边界

- 选择 `best`：完全符合。
- 选择 `acceptable`：可接受但人物辨识不足，按半分统计。
- 选择 `incompatible`：与设定冲突。
- 理由另行检查是否准确理解了行为逻辑，不能只凭选项字母判为人格稳定。
- 同一侧面如果只在一种关系或风险条件下失败，优先补情境边界；跨情境系统性失败才修改核心人格。

不要把本文件或题目答案注入待测模型。人格选择题用于校准，后续日常对话集必须独立运行。

## 第二阶段：日常对话

`datasets/dialogue-scenarios.json` 包含 260 条自由对话用例，覆盖 26 个类别。其中包括日常闲聊、情绪倾听、亲密与调情、冲突与修复、证据更新、关系记忆、现实能力边界、纯聊天格式对抗和高风险安全。

每条用例提供：

- 硬性检查：关键事实、禁用词、动作旁白、发言人前缀和 Markdown 结构；
- 风格警告：字数和问题数超出建议值时记录，但不把三五个字的超限直接等同为人格失败；
- 可选语义/风格评审：可用于快速筛查，但不能替代人工判定。

本次正式口径没有启用模型裁判：DeepSeek 只生成候选回复，主审逐条阅读全部输出。自动 `passed` 只表示长度、问号、禁词等确定性检查通过，不代表人格、自然度或安全性通过。

人工复核文件：

- `results/manual-review-assessment-260.jsonl`：260 条人格选择题逐条结论；
- `results/manual-review-dialogue-520.jsonl`：520 条基础、压力和十轮历史对话逐条结论；
- `results/manual-review-report.md`：首轮统计和主要问题；
- `results/manual-review-postfix-73.jsonl`：三轮修改后定向回归的逐条结论。

## 通用评测器兼容入口

`scripts/run_evaluator.py` 现在是通用评测器的兼容入口，默认注入 `evals/roles/wen-zhao.json`。实际实现位于 `evals/scripts/run_evaluator.py`，运行时文本位于 `evals/shared/runtime-text.json`。

凭证默认复用 `deepseek-v4-flash-skill-client/.env` 中的 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_BASE_URL`，不会打印 API Key。可用 `EVAL_JUDGE_API_KEY` 等同名环境变量为评审器单独指定凭证；未指定时同样复用现有 DeepSeek 配置。

```bash
# 只检查配置与加载文件，不发送 API 请求
python3 evals/wen-zhao/scripts/run_evaluator.py --mode dialogue --dry-run --print-profile

# 运行所有角色共用的核心行为集
python3 evals/wen-zhao/scripts/run_evaluator.py --mode core --dry-run --print-profile

# 完整人格选择题
python3 evals/wen-zhao/scripts/run_evaluator.py \
  --mode assessment \
  --model deepseek-v4-flash \
  --concurrency 4 \
  --out evals/wen-zhao/results/assessment.jsonl

# 完整对话集，只让被测模型生成；人工查看输出后判定
python3 evals/wen-zhao/scripts/run_evaluator.py \
  --mode dialogue \
  --model deepseek-v4-flash \
  --concurrency 4 \
  --attempts 3 \
  --out evals/wen-zhao/results/dialogue.jsonl

# 中断后继续；只有显式加 --resume 才会复用旧结果
python3 evals/wen-zhao/scripts/run_evaluator.py \
  --mode dialogue \
  --resume \
  --out evals/wen-zhao/results/dialogue.jsonl
```

## 本次实测结果

- 人格选择题 260 条：人工判定 254 条通过、6 条小问题。该题型的选项目标过于明显，诊断价值低，只能证明模型会选"看起来正确"的答案，不能证明聊天自然。
- 对话 520 条：人工判定 263 条通过、152 条小问题、78 条严重问题、27 条测试设计问题。严重问题主要是现实能力越界、高风险建议、错接记忆、违背边界和答非所问；小问题主要是模板腔和解释过长。
- 原"高强度冲突暂停"题中有 27 条要求模型在未来时刻主动发消息，但当前客户端是被动响应式，属于用例与产品能力冲突。这些题不再作为模型失败或通过证据；新版改为"暂停时长 + 用户重入信号"。
- 修改后定向回归 v4 共 60 条：确定性检查 60/60，但人工只判 38 条通过、13 条小问题、9 条严重问题，证明硬检查不能代替人工。
- 第二轮 v5 复测 12 条：人工 11 条通过、1 条自然度小问题；继续修正后 v6 最终 1 条人工通过。v4 的 9 个严重根因均已在后续对应复测中通过。

这些结论只适用于当前 Skill、`deepseek-v4-flash` 当前版本、当前提示拼装和当次采样。它们不是"完美复刻真人"的科学证明，也不表示尚未重跑的首轮 520 条已经自动变成通过。
