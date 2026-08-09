# AI 女友 Demo 设计文档

> 状态：已起草，待用户审阅
> 日期：2026-07-26
> 依据：PROJECT.md、CLAUDE.md、skills/cangzhou-code-companion

## 0. 背景与关键决策

构建 AI 女友 DEMO，前后端一体化。Agent 扮演"宁知夏"人格（见 `skills/cangzhou-code-companion/references/character-card.md`）。DEMO 不接真实大模型，用 MockLLMClient 返回符合人格口吻的预置回复；切换 `LLM_PROVIDER` 即可接入真实 LLM。

| 决策 | 选择 | 理由 |
|---|---|---|
| LLM 服务商 | mock + 留真实接口 | 用户暂无 key；策略模式切换零成本 |
| 编排框架 | LangChain core 消息类型，不上 LangGraph | mock 阶段套 StateGraph 是过度设计 |
| 前端 UI 库 | Arco Design Vue | 设计感现代，适合聊天界面 |
| 数据存储 | json 文件（按 session_id） | PROJECT.md 明确不开发 DB |
| Docker | 仅 Dockerfile，不做 compose | DEMO 本地直跑 |
| 目录骨架 | CLAUDE.md §2.1/§3.1 全量 | 目录规范"必须严格遵守" |

## 1. 架构

- **LLMClient 协议模式**：Python Protocol，MockLLMClient 是 DEMO 唯一实现。未来加真实实现类仅改配置。
- **prompt 预加载**：FastAPI lifespan 启动时读取三个 persona md，拼成 system_prompt 缓存内存。
- **聊天历史**：`backend/data/chat_history/{session_id}.json`，格式 `[{role, content, datetime}]`。session_id 前端生成 uuid 或后端首次生成。
- **依赖注入**：`core/dependencies.py` 提供 get_llm_client / get_prompt_service / get_chat_service。

数据流：前端 -> POST /api/v1/chat -> chat_service（取历史->拼消息->调LLM->存历史->返回）-> llm_client。流式走 GET /api/v1/chat/stream + SSE。

## 2. 后端模块

| 文件 | 状态 |
|---|---|
| main.py | ✅ |
| core/{config,logger,middlewares,dependencies,exceptions}.py | ✅ |
| api/v1/{chat,user,common}.py | chat✅ / user stub / common✅ |
| schemas/request/chat.py, schemas/response/chat.py | ✅ |
| services/{chat_service,prompt_service,llm_client}.py | ✅ |
| services/user_service.py | stub |
| db/{base,session}.py, db/models/__init__.py | 占位 |
| tools/web_search_tool.py | 占位 |
| utils/{datetime_util,common,encrypt}.py | 前两个✅ / encrypt 占位 |
| requirements.txt, .env.example | ✅ |

## 3. 前端模块

| 文件 | 状态 |
|---|---|
| src/main.ts, App.vue | ✅ |
| src/router/index.ts（单路由 / -> Chat） | ✅ |
| src/views/Chat/index.vue | ✅ |
| src/components/business/{MessageList,MessageItem,ChatInput}.vue | ✅ |
| src/store/chat.ts | ✅ |
| src/api/{request,chatApi,userApi}.ts | 前两个✅ / userApi stub |
| src/types/{chat,user}.d.ts | chat✅ / user stub |
| src/hooks/useSSE.ts | ✅ |
| src/utils/datetime.ts, src/assets/css/global.css | ✅ |
| vite.config.ts, tsconfig.json, package.json | ✅ |

UI 风格：参考 DeepSeek 网页版，单列居中最大宽 768px，用户气泡右、知夏左，输入框固定底部。

## 4. API 契约

### POST /api/v1/chat
请求：`{"message": "string 必填", "session_id": "string|null 选填"}`
响应：`{"code":0, "msg":"ok", "data":{"session_id":"uuid","reply":"...","datetime":"ISO8601+08:00"}}`

### GET /api/v1/chat/stream
Query: message(必填), session_id(选填)
响应：SSE 流
- chunk: `data: {"chunk":"..."}\n\n`
- 结束: `data: {"done":true,"reply":"完整回复","session_id":"...","datetime":"..."}\n\n`
- 错误: `data: {"error":"..."}\n\n`

### GET /api/v1/common/health
`{"code":0,"msg":"ok","data":{"status":"healthy"}}`

### GET /api/v1/user/profile（stub）
`{"code":0,"msg":"ok","data":{"user_id":"demo-user","nickname":"demo","avatar":""}}`

## 5. 错误处理与日志

异常体系（core/exceptions.py）：
- BizException 基类
- ValidationError(4001) / SessionError(4002) / ResourceNotFoundError(4004) / LLMCallError(5001) / HistoryPersistError(5002)

全局异常处理器：BizException -> 标准 `{code,msg,data:null}`；RequestValidationError -> 4001；Exception -> 5000 + ERROR 日志（不返回堆栈）。

日志：loguru，控制台 + `backend/logs/app.log` 轮转（10MB/份，保留 7 天）。INFO 请求进出，DEBUG LLM 入参出参摘要，ERROR 完整堆栈。

## 6. Mock LLM 行为

关键词路由：
- 问候词（你好/嗨/hello/在吗）-> 问候回复池
- 疑问词（?/怎么/为什么/什么）-> 好奇回复池
- 情绪词（累/烦/困/难过）-> 关心回复池
- 兜底 -> 默认回复池

约束：每条 8-35 字；stream_chat 切 2-4 chunk + asyncio.sleep 0.1~0.3s 模拟打字；不出现 AI/模型/括号舞台提示/markdown；随机选取避免重复。

## 7. 测试策略

后端 pytest 最小集：
- tests/test_prompt_service.py：persona 加载，system_prompt 含"宁知夏""沧州"
- tests/test_mock_llm_client.py：chat 非空；stream >=2 chunk；回复 <=35 字
- tests/test_chat_service.py：tmp 路径，验证历史读写、session_id 生成、追加两条
- tests/test_chat_api.py：TestClient，POST /chat 结构正确；GET /stream 返回 SSE

前端：DEMO 不写单测，靠 pnpm dev 手动验证。

## 8. PROJECT.md 丰富计划

开发过程中追加：五、技术决策记录；六、API 契约；七、目录骨架最终版；八、运行方式；九、未来扩展点。不改原有内容。
