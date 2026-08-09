# AI 女友 Demo 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task.

**Goal:** 构建前后端一体化 AI 女友 DEMO，Agent 扮演宁知夏人格，/api/v1/chat 支持流式+非流式，DEMO 用 MockLLMClient。

**Architecture:** FastAPI（LangChain core 消息 + 策略模式 LLMClient）+ Vue3（Arco + Pinia + SSE）。历史存 json。prompt lifespan 预加载。

**Tech Stack:** Python 3.12 / FastAPI / Pydantic V2 / loguru / langchain-core / pytest | Vue3 / Vite / TS / Pinia / Vue Router / Axios / Arco Design Vue

## Global Constraints
- 后端目录严格遵守 CLAUDE.md §2.1，前端 §3.1
- 统一返回 `{code, msg, data}`，code=0 成功
- 路由前缀 `/api/v1/`，仅 GET/POST
- Pydantic V2 `ConfigDict(from_attributes=True)`
- Vue `<script setup lang="ts">` + scoped style
- TS 禁 any，用 unknown + 收窄
- 单函数 <=80 行
- Mock 回复 8-35 字，无 AI/括号/markdown
- 不开发 DB，历史存 json
- 仅 Dockerfile，无 compose

## Tasks

### Task 1: 后端基础设施
- Files: `backend/{requirements.txt, .env.example, core/__init__.py, core/config.py, core/logger.py, core/exceptions.py}`
- Produces: `Settings` (llm_provider/api_key/model/base_url, max_context_tokens, chat_history_dir, persona_dir, log_dir, cors_origins), `logger`/`setup_logger()`, `BizException` 体系 + `success_resp`/`fail_resp`
- Test: import Settings, 构造 success_resp/fail_resp

### Task 2: 后端 schemas + utils + 占位
- Files: `backend/schemas/{request, response}/chat.py`, `backend/utils/{datetime_util, common, encrypt}.py`, `backend/db/{base, session, models/__init__}.py`, `backend/tools/web_search_tool.py`, `backend/services/user_service.py`
- Produces: `ChatRequest(message: str, session_id: str|None)`, `ChatResponse(session_id, reply, datetime)`, `now_iso()`, `generate_session_id()`
- Test: ChatRequest 校验，datetime 格式

### Task 3: prompt_service
- Files: `backend/services/prompt_service.py`, `backend/tests/test_prompt_service.py`
- Produces: `PromptService` 类，`async load() -> None`, `get_system_prompt() -> str`
- 行为: 启动时读 character-card.md + dialogue-playbook.md + relationship-memory.md，拼成 system_prompt 缓存
- Test: load 后 system_prompt 含"宁知夏""沧州"，非空

### Task 4: llm_client (MockLLMClient)
- Files: `backend/services/llm_client.py`, `backend/tests/test_mock_llm_client.py`
- Produces: `LLMClient` Protocol (`async chat(messages)->str`, `async stream_chat(messages)->AsyncIterator[str]`), `MockLLMClient` 实现
- 行为: 关键词路由（问候/疑问/情绪/默认）-> 回复池随机选取，8-35 字；stream 切 2-4 chunk + sleep
- Test: chat 非空 <=35 字；stream >=2 chunk

### Task 5: chat_service
- Files: `backend/services/chat_service.py`, `backend/tests/test_chat_service.py`
- Produces: `ChatService(llm_client, prompt_service, history_dir)`, `async handle_chat(message, session_id) -> ChatResponse`, `async handle_chat_stream(message, session_id) -> AsyncIterator[str]`
- 行为: 取/建 session_id -> 读历史 json -> 拼 LangChain messages -> 调 llm -> 追加历史 -> 写回
- Test: tmp 路径，mock client，验证历史读写、session_id 生成、追加两条

### Task 6: chat API + main.py
- Files: `backend/api/v1/{chat, user, common}.py`, `backend/core/{middlewares, dependencies}.py`, `backend/main.py`, `backend/tests/test_chat_api.py`
- Produces: POST `/api/v1/chat`, GET `/api/v1/chat/stream`(SSE), GET `/api/v1/common/health`, GET `/api/v1/user/profile`(stub)
- Test: TestClient POST /chat 返回结构正确；GET /stream 返回 SSE

### Task 7: 后端 Dockerfile
- Files: `docker/backend/Dockerfile`, `docker/backend/.dockerignore`
- 多阶段构建，python:3.12-slim，非 root，8000 端口，Asia/Shanghai

### Task 8: 前端 scaffolding
- Files: `frontend/{package.json, vite.config.ts, tsconfig.json, tsconfig.node.json, index.html, src/main.ts, src/App.vue, src/env.d.ts, src/assets/css/global.css}`
- 依赖: vue3, vue-router, pinia, axios, @arco-design/web-vue
- vite proxy `/api` -> `http://localhost:8000`

### Task 9: 前端 types + api + hooks
- Files: `frontend/src/types/chat.d.ts`, `frontend/src/api/{request, chatApi, userApi}.ts`, `frontend/src/hooks/useSSE.ts`, `frontend/src/utils/datetime.ts`
- Produces: `ChatMessage`, `ChatSendParams`, `sendChat()`, `streamChat()` (EventSource 封装), `useSSE()`

### Task 10: 前端 store + components + view + router
- Files: `frontend/src/store/chat.ts`, `frontend/src/components/business/{MessageList, MessageItem, ChatInput}.vue`, `frontend/src/views/Chat/index.vue`, `frontend/src/router/index.ts`
- Produces: chatStore (messages, sendMessage, sendMessageStream), 单列聊天 UI

### Task 11: 前端 Dockerfile
- Files: `docker/frontend/Dockerfile`, `docker/frontend/.dockerignore`, `docker/nginx/nginx.conf`
- node:18-alpine 构建 + nginx:alpine 运行

### Task 12: PROJECT.md 丰富 + 端到端验证
- 追加 PROJECT.md 五~九章节
- 后端 pytest 全过
- 前端 pnpm build 过
- 手动验证 /api/v1/chat 流式+非流式

## Execution
Inline execution（executing-plans skill）。每个 Task 完成后验证。
