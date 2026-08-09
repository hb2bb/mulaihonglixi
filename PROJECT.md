> 本markdown文件为本项目初版的功能介绍，在开发项目初版前后端骨架时，CLAUDE/CODEX需要按照本markdownw文件的需求进行开发。
### 一、项目介绍
- 一款**AI女友app**，按照设定的AGENT人格画像`skills/cangzhou-code-companion/references/character-card.md`进行角色扮演完成与用户的交流，为用户提供情绪价值。
- **项目初期**仅需实现网页端的交互与功能。
- 希望成为一些现实生活中缺少社交时间的朋友们的**心灵慰藉**与**情绪宣泄的出口**,同时给用户提供分享生活的平台,让AGENT作为一个灵动、真实的人格而存在,并不只是程序中冰冷的数据与skills。
- AI女友的主要能力是用户对话。在后续的迭代过程中需要具备**网页检索能力**,**推荐抖音视频/bilibili视频**,并通过视频总结等外部的方法扩充自己的兴趣、人格底色,进行人格的进化。

### 二、后端服务
后端服务路径如下所示(预期,不代表最终版本)
```
backend/
├── main.py                 # 项目入口，仅初始化app、挂载路由、中间件、生命周期事件
├── core/                   # 核心配置层
│   ├── config.py           # 环境变量、全局配置（pydantic-settings）
│   ├── logger.py           # 日志统一封装
│   ├── middlewares.py      # 全局中间件（跨域、请求日志、鉴权、异常捕获）
│   ├── dependencies.py     # 全局依赖注入（数据库会话、用户鉴权、限流）
│   └── exceptions.py       # 自定义业务异常 + 全局异常处理器
├── api/                    # 路由接口层，按模块分路由
│   ├── __init__.py
│   ├── v1/                 # 接口版本控制
│   │   ├── __init__.py
│   │   ├── chat.py         # AI对话模块接口
│   │   ├── user.py         # 用户模块接口
│   │   └── common.py       # 公共工具接口
├── schemas/                # Pydantic 数据模型：入参校验、出参序列化
│   ├── request/           # 请求体模型
│   └── response/          # 响应返回模型
├── db/                     # 数据库层
│   ├── base.py            # 数据库基类、异步会话工厂
│   ├── session.py         # 数据库连接、依赖注入会话
│   └── models/            # SQLAlchemy ORM 数据表模型
├── services/               # 业务逻辑层，禁止在路由函数写复杂业务
│   ├── chat_service.py
│   ├── user_service.py
│   ├── prompt_service.py   # 负责组装得到完整prompt等功能
│   └── llm_client.py      # Claude/大模型调用封装
├── tools/                  # 工具工具调用能力

├── utils/                  # 工具函数
│   ├── encrypt.py
│   ├── datetime_util.py
│   └── common.py
└── requirements.txt / pyproject.toml
```
- `FastAPI`构建线上服务端点。DEMO版本预期有`/v1/chat这一端点`。
- `pydantic`用于数据模型与数据验证
- LLM应用编排能力,以`Langchian`、`LangGraph`为基础进行开发,复用已有API,避免自研AGENT框架设计不全面、碰壁的问题。
- 工具调用能力，继承自`Langchain`相关的工具类进行开发,目前预期有`web_search_tool`这一工具用于检索网页文章，或用于查看用于转发给AGENT的链接。
- `Prompt`组装统一在prompt_service中进行，agent的人物画像`skills/cangzhou-code-companion/references/character-card.md`与会话规范`skills/cangzhou-code-companion/references/dialogue-playbook.md`通过system_prompt进行拼接，`skills/cangzhou-code-companion/references/relationship-memory.md`作为一个
- 目前留出数据库的开发路径，但是不对数据库服务进行开发。
- 目前用户的上下文对话可以存放在`.json`文件中，作为一个个，不会为严格的QA格式，以`{role:"",content:"",datetime:""}`类似的格式记录聊天信息，如果用户的prompt迫使agent需要查找详细的聊天记录时，仅需要对`.json`的聊天记录使用`grep`命令进行查找即可。
- 定时任务：可能会涉及到模糊时间的定时任务，例如agent主动向用户发消息，这一功能是合理的。定时任务还涉及到例如每天统一时间的记忆、人格画像的更新。
- 后端服务使用Docker容器化运行，并将日志挂载到宿主机上。 
- 由于API调用涉及到token，大模型服务商的api是存在一个上下文窗口的，若判定本次对话请求，会使得本次上下文窗口超限，因此需要进行上下文窗口的检测，可以通过`自定义中间件`的方式来进行,若检测到上下文窗口不足，则新开一个session，并将前面session的对话持久化增量更新到本地。另外，考虑取上一次时间的对话时间与当前时间作比较，若超过一定阈值，则视为本次对话为一次新的session(抽象来看)，但是从功能上来看对话还是连续的。
### 三、前端服务
- 自由发挥，目前的DEMO可以采用Vue作为主程序的前端设计组件，采用和常规网页版大模型相似的UI(ChatGPT,DeepSeek等)，不同的是消息列表始终只有一条消息模拟1v1的对话，用户打开页面，即可展示全部的消息。
### 四、skill路径
- 在`./skills`路径下的`cangzhou-code-companion`子目录中存放对话相关prompt、skills,其中`./skills/canzhou-code-companion/references`中存放主要skills, `character-card.md`为角色卡，`dialogue-playbook.md`为Agent回答时需要遵守的准则，`relationship-memory.md`为Agent对用户的画像以及相关的一些重点记忆的摘要。

当前服务长期记忆，即对话记录可以以.json的格式存储。增量更新由一下几种情况触发：
- 用户推出聊天
- api上下文窗口不足
- 用户聊天闲挂，经过一定时间阈值自动写入。

### 五、技术决策记录

> 本节记录 DEMO 开发过程中的关键技术决策及理由，供后续迭代参考。

#### 5.1 LLM 服务商：DEMO 阶段 mock，策略模式切换

- **决策**：`services/llm_client.py` 定义 `LLMClient` Protocol，`MockLLMClient` 为 DEMO 唯一实现。
- **理由**：用户暂无 API key；策略模式让未来切换真实 LLM 零成本——新增 `ClaudeLLMClient` / `DeepSeekLLMClient` 实现类 + 修改 `.env` 中 `LLM_PROVIDER` 即可，业务代码零改动。
- **切换方式**：`.env` 设置 `LLM_PROVIDER=claude`（或 `deepseek`），填入 `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL`，在 `core/dependencies.py` 的 `get_llm_client()` 增加对应分支。

#### 5.2 编排框架：LangChain core 消息类型，不上 LangGraph

- **决策**：仅使用 `langchain_core.messages` 的 `SystemMessage` / `HumanMessage` / `AIMessage`，不引入 LangGraph StateGraph。
- **理由**：DEMO 阶段无工具调用、无多节点编排，套 StateGraph 是过度设计。LangGraph 留扩展位（`tools/web_search_tool.py` 占位），真实 LLM + 工具调用时再引入。

#### 5.3 前端 UI 库：Arco Design Vue

- **决策**：采用 `@arco-design/web-vue`。
- **理由**：设计感现代，适合 ChatGPT-like 聊天界面；组件 API 清晰。

#### 5.4 数据存储：json 文件（按 session_id 分文件）

- **决策**：聊天历史存 `backend/data/chat_history/{session_id}.json`，格式 `[{role, content, datetime}]`。
- **理由**：PROJECT.md 明确"DEMO 不开发数据库服务"。`db/` 目录留占位，后续接入 SQLAlchemy 2.0 异步 ORM 时替换。

#### 5.5 Docker：仅 Dockerfile，不做 compose 编排

- **决策**：`docker/backend/Dockerfile` + `docker/frontend/Dockerfile` + `docker/nginx/nginx.conf`，不做 `docker-compose.yml`。
- **理由**：DEMO 阶段本地直跑（`uvicorn` + `vite dev`）。compose 编排留待后续。

#### 5.6 目录骨架：CLAUDE.md §2.1 / §3.1 全量搭出

- **决策**：后端 `core/` / `api/v1/` / `schemas/` / `db/` / `services/` / `tools/` / `utils/` 全目录；前端 `router/` / `store/` / `api/` / `views/` / `components/` / `types/` / `hooks/` / `utils/` / `assets/` 全目录。
- **理由**：CLAUDE.md 把目录结构列为"必须严格遵守"。未实现的模块（`db/`、`tools/`、`user_service`）留占位文件 + 注释说明扩展路径。

### 六、API 契约

#### 6.1 POST `/api/v1/chat`（非流式对话）

请求体：
```json
{
  "message": "string, 必填, 1-4000 字",
  "session_id": "string | null, 选填, uuid v4"
}
```

响应：
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "session_id": "uuid v4",
    "reply": "宁知夏的回复",
    "datetime": "2026-07-26T15:30:00+08:00"
  }
}
```

#### 6.2 GET `/api/v1/chat/stream`（流式对话，SSE）

Query 参数：`message`（必填）、`session_id`（选填）

响应：`text/event-stream`，每条事件 `data: {json}\n\n`

- chunk 事件：`{"chunk": "..."}`
- 结束事件：`{"done": true, "reply": "完整回复", "session_id": "...", "datetime": "..."}`
- 错误事件：`{"error": "错误信息"}`

#### 6.3 GET `/api/v1/common/health`

```json
{"code": 0, "msg": "ok", "data": {"status": "healthy"}}
```

#### 6.4 GET `/api/v1/user/profile`（stub）

```json
{"code": 0, "msg": "ok", "data": {"user_id": "demo-user", "nickname": "demo", "avatar": ""}}
```

#### 6.5 错误码

| code | 含义 |
|---|---|
| 0 | 成功 |
| 4001 | 参数校验失败 |
| 4002 | session_id 非法 |
| 4004 | 资源不存在 |
| 5001 | LLM 调用失败 |
| 5002 | 历史记录写入失败 |
| 5000 | 内部错误 |

### 七、目录骨架最终版

#### 7.1 后端

```
backend/
├── main.py                 # 入口：装配 app + lifespan 加载 persona
├── requirements.txt
├── .env.example
├── core/
│   ├── config.py           # pydantic-settings
│   ├── logger.py           # loguru 封装
│   ├── middlewares.py      # CORS + 请求日志 + 异常处理
│   ├── dependencies.py     # get_llm_client / get_prompt_service / get_chat_service
│   └── exceptions.py       # BizException 体系 + success_resp/fail_resp
├── api/v1/
│   ├── chat.py             # POST /chat, GET /chat/stream
│   ├── user.py             # GET /user/profile (stub)
│   └── common.py           # GET /common/health
├── schemas/
│   ├── request/chat.py     # ChatRequest
│   └── response/chat.py    # ChatResponseData, ChatStreamChunk
├── services/
│   ├── chat_service.py     # 编排：取历史->拼消息->调LLM->存历史
│   ├── prompt_service.py   # persona md 加载与缓存
│   ├── llm_client.py       # LLMClient Protocol + MockLLMClient
│   └── user_service.py     # stub
├── db/                     # 占位（不开发 DB）
├── tools/web_search_tool.py # 占位（未来 LangChain tool）
├── utils/
│   ├── datetime_util.py    # ISO8601 + 北京时区
│   ├── common.py           # session_id 生成与校验
│   └── encrypt.py          # 占位
├── data/chat_history/      # 运行时生成的 json 历史
└── tests/                  # 测试目录（待补）
```

#### 7.2 前端

```
frontend/
├── package.json
├── vite.config.ts          # dev proxy /api -> :8000
├── tsconfig.json
├── index.html
└── src/
    ├── main.ts             # 挂载 + 注册 Arco/Pinia/Router
    ├── App.vue
    ├── router/index.ts     # 单路由 / -> Chat
    ├── views/Chat/index.vue
    ├── components/business/
    │   ├── MessageList.vue
    │   ├── MessageItem.vue
    │   └── ChatInput.vue
    ├── store/chat.ts       # Pinia: messages + send/stream
    ├── api/
    │   ├── request.ts      # axios 实例 + 拦截器
    │   ├── chatApi.ts      # sendChat + streamChat(EventSource)
    │   └── userApi.ts      # stub
    ├── types/chat.d.ts
    ├── hooks/useSSE.ts     # EventSource 封装
    ├── utils/datetime.ts
    └── assets/css/global.css
```

#### 7.3 Docker

```
docker/
├── backend/
│   ├── Dockerfile          # 多阶段 python:3.12-slim，非 root
│   └── .dockerignore
├── frontend/
│   ├── Dockerfile          # node:18-alpine 构建 + nginx:alpine 运行
│   └── .dockerignore
└── nginx/
    └── nginx.conf          # SPA 兜底 + gzip + 静态缓存 + /api 反代
```

### 八、运行方式

#### 8.1 后端本地开发

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/Mac
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000/docs` 查看 OpenAPI 文档。

#### 8.2 前端本地开发

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`，vite dev proxy 自动把 `/api` 转发到 `http://localhost:8000`。

#### 8.3 环境变量说明

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `mock` | LLM 服务商，DEMO 仅支持 `mock` |
| `LLM_API_KEY` | （空） | 真实 LLM 的 API key |
| `LLM_MODEL` | （空） | 模型名称 |
| `LLM_BASE_URL` | （空） | LLM 服务地址 |
| `MAX_CONTEXT_TOKENS` | `32000` | 上下文窗口 token 上限 |
| `CHAT_HISTORY_DIR` | `data/chat_history` | 聊天历史 json 目录 |
| `PERSONA_DIR` | `../skills/cangzhou-code-companion/references` | persona md 目录 |
| `LOG_DIR` | `logs` | 日志目录 |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | CORS 白名单 |

### 九、未来扩展点

#### 9.1 接入真实 LLM

1. 在 `services/llm_client.py` 新增 `ClaudeLLMClient` / `DeepSeekLLMClient` 实现 `LLMClient` Protocol。
2. 在 `core/dependencies.py` 的 `get_llm_client()` 增加分支。
3. `.env` 设置 `LLM_PROVIDER=claude` + 填入 key。

#### 9.2 替换 json 为数据库

1. `db/base.py` 定义 SQLAlchemy `DeclarativeBase`。
2. `db/session.py` 定义 `async_sessionmaker` + `get_db` 依赖。
3. `db/models/` 新增 `ChatHistory` ORM 模型。
4. `services/chat_service.py` 的 `_load_history` / `_persist_history` 改为 ORM 操作。

#### 9.3 引入 LangGraph 编排

1. `services/` 新增 `agent_service.py`，定义 `StateGraph`。
2. 节点：`assemble_prompt` -> `invoke_llm` -> `tool_calling`（可选） -> `format_response`。
3. `tools/web_search_tool.py` 实现为 `BaseTool`，注册到 graph。

#### 9.4 工具调用

1. `tools/web_search_tool.py` 继承 `langchain_core.tools.BaseTool`。
2. 实现 `_run` / `_arun`。
3. 在 LLM 调用中绑定工具（LangChain `bind_tools`）。

#### 9.5 定时任务

1. 引入 `apscheduler` 或 `celery-beat`。
2. 定时任务示例：agent 主动发消息、每天统一时间记忆更新、人格画像更新。
3. 在 `main.py` 的 lifespan 中启动调度器。

#### 9.6 上下文窗口管理

1. `core/middlewares.py` 新增中间件，检测本次请求是否会超限。
2. 超限时新开 session，将前面 session 对话持久化增量更新到本地。
3. 取上一次对话时间与当前时间比较，超过阈值视为新 session。
