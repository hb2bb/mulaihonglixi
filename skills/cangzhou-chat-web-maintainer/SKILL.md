---
name: cangzhou-chat-web-maintainer
description: 维护 deepseek-v4-flash-skill-client 的聊天、记忆、状态、回复审查、Debug 与构建同步逻辑。修改该网页项目的模型调用、提示词、运行规则或相关测试时使用，并确保模型自然语言不被硬编码进业务代码。
---

# 沧州聊天网页维护

## 修改前

1. 完整阅读 `skills/cangzhou-chat-runtime/SKILL.md`。
2. 完整阅读 `skills/cangzhou-chat-runtime/references/runtime-text.json`。
3. 检查 Next/Vinext 与零依赖 Python 两套网页实现，保持行为一致。

## 模型文本必须归入 Skill

- 禁止在 `.ts`、`.tsx`、`.js` 或 `.py` 业务代码中新增或复制给模型阅读的自然语言规则、角色提示、审查标准、记忆标准、心情规则、重试反馈或选择指令。
- 把所有这类中文文本写入 `cangzhou-chat-runtime/references/runtime-text.json`，并在 `cangzhou-chat-runtime/SKILL.md` 中说明重要流程与边界。
- 代码只负责稳定的流程控制、模板变量填充、消息角色、字段结构、次数限制、校验、错误处理和 API 调用。
- UI 标签、接口错误、日志、无障碍文案和测试夹具不是模型提示，可以留在代码中；若文本会进入模型的 `messages`，则必须移入运行时 Skill。
- 不得在模型文本缺失时于代码中设置中文备用提示。缺少必需键时应在构建或启动阶段明确失败。

## 同步方式

- `scripts/sync_skills.py` 必须从运行时 Skill 读取文本，并生成 TypeScript 可导入常量。
- Python 网页服务必须直接从同一运行时 Skill 资源读取，不能维护第二份提示副本。
- 项目维护 Skill 只约束开发过程，不得注入角色聊天或审查模型的运行时上下文。
- 新增模板变量时，同时更新资源、两套渲染函数与测试；模板只能使用显式允许的变量。

## 审查调用约束

- 首稿生成不能接收审查输出。
- 审查模型不能改写候选，只能通过、拒绝并总结问题，或在最终阶段选择编号。
- 最多重试两次，总候选数最多三份。
- Debug 可显示各模型输出，但不得返回密钥、系统提示词或完整请求体。

## 验证

1. 运行 Skill 校验。
2. 运行 Python 语法检查与单元测试。
3. 运行静态网页 JavaScript 语法检查。
4. 运行正式网站构建，确认生成的 Skill 与运行时文本已同步。
