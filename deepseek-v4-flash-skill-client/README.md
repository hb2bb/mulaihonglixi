# DeepSeek V4 Pro + Skills 客户端

项目现在包含 Python 命令行客户端和网页体验台。两者都会把现有 Skills 作为 `system` 消息加入模型输入；API Key 仅由服务端读取，不会发送到浏览器。

网页端还维护两份仅在当前页面有效的临时状态：

- 每累计 10 条用户或助手消息，调用独立的 DeepSeek V4 记忆接口，只合并稳定事实、偏好、边界、约定和关系里程碑等关键节点。
- 打开页面时立即获取一次北京时间和北京天气，此后每 30 分钟刷新；每次 10 条消息检查后也会结合最近对话和原有状态重新生成虚构角色心情。
- 当前 `ENABLE_REPLY_REVIEW=false`，聊天模型每次只生成一份回复，不执行审查、重试或最终候选选择。改为 `true` 后恢复完整审查流程。
- 刷新、重新进入网站或点击“清空对话”都会清空会话记忆；这些状态不会写入项目里的 `relationship-memory.md`。

天气数据来自 Open-Meteo。可通过 `.env` 中的 `LIVE_STATE_CITY`、`LIVE_STATE_LATITUDE`、`LIVE_STATE_LONGITUDE` 和 `LIVE_STATE_TIMEZONE` 修改地点。

实时心情使用独立的 OpenAI 兼容模型接口，通过 `STATE_API_KEY`、`STATE_BASE_URL` 和 `STATE_MODEL` 配置，不复用聊天与记忆整理所使用的 DeepSeek V4 接口。状态模型请求只发送标准的 `model`、`messages`、`stream` 和 `max_tokens` 字段。

回复审查由 `ENABLE_REPLY_REVIEW` 控制。当前关闭，因此不要求配置第三套接口；恢复为 `true` 时，再通过 `REVIEW_API_KEY`、`REVIEW_BASE_URL` 和 `REVIEW_MODEL` 配置审查模型。

页面中的 `Debug` 面板会显示当前会话记忆、实时状态，以及聊天、记忆、状态、审查和最终选择模型的逐次原始输出。面板不显示 API Key、系统提示词或完整请求体；所有 Debug 数据只保存在当前页面内存中，刷新或清空对话后消失。

## 运行规则的维护位置

聊天、记忆、状态、审查、重试和最终选择模型所读取的自然语言提示，统一保存在 `skills/cangzhou-chat-runtime/references/runtime-text.json`。修改中文规则后运行 `npm run sync-skills`，即可更新可部署网页使用的 TypeScript 常量；Python 网页服务直接读取同一文件。

项目维护约束位于 `skills/cangzhou-chat-web-maintainer/SKILL.md`。后续不得在 TypeScript、JavaScript 或 Python 业务代码中硬编码给模型阅读的自然语言规则；界面标签、错误提示、日志和测试夹具不属于模型提示，可以留在代码中。维护 Skill 不会被注入角色聊天运行时。

## 网页体验台

最简单的运行方式不需要安装任何依赖：

```bash
cd "/Users/didi/Desktop/牧瀬紅莉栖/deepseek-v4-flash-skill-client"
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
python3 web_server.py
```

浏览器打开 `http://127.0.0.1:8000`。需要让同一局域网中的其他人访问时：

```bash
python3 web_server.py --host 0.0.0.0 --port 8000
```

然后让对方访问 `http://你的局域网IP:8000`。公网使用时，请部署到带 HTTPS、访问控制和更严格限流的服务器，不要直接把开发端口暴露到互联网。

给别人体验前，建议在 `.env` 中同时设置 `SITE_ACCESS_KEY`。访客第一次提问时会看到访问码输入框，访问码只保存在当前浏览器会话中。

> 安全提醒：注入模型的 Skill 可能被恶意提示词套取。不要在公开站点加载包含私人记忆、密钥或内部规则的 Skill；应先复制一份适合公开体验的版本。

项目还包含可构建部署的 React/Vinext 版本。它需要 Node.js 22.13 或更新版本：

```bash
cd "/Users/didi/Desktop/牧瀬紅莉栖/deepseek-v4-flash-skill-client"
npm install
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
npm run dev
```

打开终端显示的本地地址即可使用。每次 `npm run dev` 或 `npm run build` 前，程序会同步当前 Skill 内容；网页发出的每一次模型请求都会携带这份完整内容。

生产构建：

```bash
npm run build
```

如果把网站公开给其他人使用，API 费用由服务端配置的 DeepSeek 账号承担，建议在公网入口增加访问控制或限流。

## Python 命令行客户端

命令行版本只使用 Python 标准库。它在**每次 API 调用前**重新扫描现有 Skills，因此修改 Skill 后无需重启。

## 默认扫描范围

- 项目级：`skills/`、`.agents/skills/`、`.deepcode/skills/`、`.codex/skills/`
- 用户级：`~/.agents/skills/`、`~/.codex/skills/`
- `EXTRA_SKILL_ROOTS` 指定的额外目录

程序会查找其中的 `SKILL.md`。如果 `SKILL.md` 链接了同一 Skill 目录中的本地 Markdown 文件，也会递归加载这些文件。链接不能越出该 Skill 的目录。

本程序位于项目的子目录中，默认把上一级 `/Users/didi/Desktop/牧瀬紅莉栖` 当成项目根目录。网页运行时只加载 `skills/love69-mafuyu-companion/SKILL.md` 及其引用文件，避免新旧角色规则冲突。

## 环境要求

- Python 3.9 或更新版本
- DeepSeek API Key

## 使用方法

macOS/Linux：

```bash
cd "/Users/didi/Desktop/牧瀬紅莉栖/deepseek-v4-flash-skill-client"
export DEEPSEEK_API_KEY="你的_API_Key"
python3 deepseek_skill_client.py "请写一个 Python 快速排序"
```

进入多轮交互模式：

```bash
python3 deepseek_skill_client.py
```

查看实际会加载哪些 Skill 文件，不调用 API：

```bash
python3 deepseek_skill_client.py --show-skills
```

常用选项：

```bash
# 关闭用户级 Skills，只加载项目级和额外目录
python3 deepseek_skill_client.py --no-user-skills "你好"

# 使用最大推理强度
python3 deepseek_skill_client.py --reasoning-effort max "检查这段设计"

# 关闭思考模式
python3 deepseek_skill_client.py --no-thinking "简短回答"

# 指定另一个项目根目录
python3 deepseek_skill_client.py --project-root /path/to/project "你好"
```

## 在其他 Python 代码中调用

```python
import os
from pathlib import Path

from deepseek_skill_client import DeepSeekSkillClient, SkillLoader

loader = SkillLoader(Path("/path/to/project"))
client = DeepSeekSkillClient(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    skill_loader=loader,
)

answer = client.chat([
    {"role": "user", "content": "帮我检查这段代码"},
])
print(answer)
```

## 测试

测试使用模拟响应，不会访问 DeepSeek，也不需要 API Key：

```bash
python3 -m unittest -v
```

## 安全说明

- API Key 只从环境变量读取，不会写入模型输入或日志。
- 请先用 `--show-skills` 检查将要发送的文件；Skill 内容会被传给 DeepSeek API。
- 每次调用都注入全部 Skills 会增加输入 token 和费用。若只需项目 Skills，可使用 `--no-user-skills`。

## API 信息

- Base URL：`https://api.deepseek.com`
- 模型 ID：`deepseek-v4-pro`
- 接口：OpenAI 兼容的 `POST /chat/completions`

参考：[DeepSeek API 官方文档](https://api-docs.deepseek.com/)
