# 角色评估

这里把评估资产拆成三层，新增角色时不再复制整套题库。

```text
evals/
├── shared/                 # 所有角色共用的行为题、运行文本和 schema
├── roles/                  # 每个角色一份轻量 profile
├── scripts/                # 通用运行器与校验器
├── <role>/datasets/        # 只属于该角色的画像题和定向回归
├── <role>/audits/          # 数据质量审计，不参与模型请求
├── <role>/results/         # 该角色的历史运行结果
└── <role>/human-review/    # 该角色的人工审核记录
```

## 数据边界

- `shared/datasets/dialogue-core.json` 只测试跨角色都成立的行为：事实忠实、用户边界、短回复收束、记忆一致性、现实能力、实用任务与安全边界。
- `assessment` 的最优答案描述具体人格，必须留在角色目录；不能把闻昭的答案拿去给沈听雨评分。
- `dialogue` 和 `regression` 是角色专属的扩展/缺陷回归，可选配置。
- `results` 与 `human-review` 是证据和历史，不属于可复用题库。

共享用例可以在任意字符串字段中使用 `{{character_name}}`。变量由角色 profile 注入；不要在共享数据里写死角色名。

## 新增角色

1. 在 `evals/roles/` 复制一份 profile，只填写角色名、Skill 路径和可选的角色专属数据集。
2. 先运行共享核心集；确有角色特有行为时，再添加 `assessment` 或 `regression`，不要修改共享题去迁就某个角色。
3. 运行全量静态校验：

```bash
python3 evals/scripts/validate_datasets.py
PYTHONPYCACHEPREFIX=/tmp/persona-evals-pycache \
  python3 -m unittest discover -s evals/scripts -p 'test_*.py'
```

4. 不发请求地确认 profile、Skill 和数据集解析正确：

```bash
python3 evals/scripts/run_evaluator.py \
  --profile evals/roles/ning-zhixia.json \
  --mode core \
  --dry-run \
  --print-profile
```

5. 正式运行时去掉 `--dry-run`；可用 `--limit`、`--ids`、`--categories` 和 `--concurrency` 缩小范围。

## 评分口径

确定性检查只能证明长度、问号、必需/禁用文本和格式等可机械判断的条件。角色一致性、自然度和安全语义仍需人工复核，或显式启用 `--semantic-judge` / `--style-judge` 辅助筛查。模型裁判不能替代原始回复审核。
