### 一、项目基础信息
-  项目名称：AI 女友 Demo 前后端一体化项目
-  项目功能：AI女友陪用户聊天，根据`skills/canzhou-code-companion`路径下的markdown文件，读取相关记忆及行为规范，对用户的问题进行回答。
-  后端技术栈：Python 3.10+、FastAPI、Pydantic V2、SQLAlchemy 2.0、AsyncPG/Redis、Uvicorn
-  前端技术栈：Vue 3 + Vite、TypeScript、Pinia、Vue Router、Axios、Element Plus / Arco Design
-  仓库结构：前后端分离单仓库管理，目录约定：
    ```
    project-root/
    ├── backend/        # FastAPI 后端服务
    ├── frontend/       # Vue3 前端项目
    ├── deepseek-v4-flash-skill-client      # 旧版本前后端项目，当前分支弃用并不做修改
    ├── docs/           # 接口文档、部署文档
    ├── .gitignore      # git忽略的文档
    ├── skills/cangzhou-code-companion          # 本项目中agent需要使用的提示词,`SKILL.md`为agent的基本职能,`references/character-card.md`为agent的人物设定(背景)`,`dialogue-playbook.md`为agent在与用户对话时的对话手册,规定了agent对话时需要采用的风格、内容等，`relationship-memory.md`为agent所更新的用户人格画像，记录了用户目前状况及相关聊天进展
    ├── AGENTS.md          # agent在开始与用户的聊天前需要阅读的规范，随system_prompt注入
    └── CLAUDE.md       # 本规范约束文件
    ```
> 本文件用于约束 Claude 生成、修改、重构项目代码时强制遵循编码规范、目录结构、命名、注释、工程化写法，所有代码输出必须符合本文档条款。
### 二、后端FastAPI强制编码规范(backend/)
§2.1  目录分层规范(必须严格遵守)
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
§2.2 命名规范
- 文件 / 文件夹：全部小写，下划线分隔 snake_case
- 变量 / 函数：snake_case，语义化命名，禁止单字母无意义命名（循环 i/j 除外）
- 类名：大驼峰 PascalCase（如 ChatRequest、UserModel）
- 常量：全大写下划线 MAX_TOKEN_LIMIT，统一放在 core/config.py
- 接口路由前缀：统一 /api/v1/xxx，版本强制挂载，方便后续迭代兼容

§2.3 路由 & 接口编写规范
- 所有接口必须拆分到 api/v1 下分文件管理，main.py 只汇总路由，不写接口逻辑
- 路由函数仅做三件事：参数接收 → 调用 service 层 → 返回结构化响应
- 禁止路由内直接操作数据库、调用大模型、写 if/else 业务逻辑
- HTTP 方法严格语义：
    GET：查询数据，无请求体
    POST：新增、提交对话、复杂创建
    PUT：全量更新
    PATCH：局部更新
    DELETE：删除
- 当前服务仅支持`POST`、`GET`两种请求
- 必须使用 `Pydantic` 模型校验请求参数，禁止裸 dict、body() 无校验入参

§2.4 数据模型 Pydantic V2 规范
- 请求模型存放 `schemas/request`，响应模型存放 `schemas/response`
所有模型添加 `model_config = ConfigDict(from_attributes=True)` 支持 `ORM` 自动解析
- 字段必须标注类型注解，必填项不设默认值，选填项显式 `Optional[T] | None = None`
- 接口统一返回包装结构体，禁止直接 return 数据：
    ```
    # 全局标准返回格式
    {
        "code": int,       # 0成功，非0业务错误码
        "msg": str,        # 提示信息
        "data": Any | None # 业务数据
    }
    ```
- 全局在 `core/exceptions.py` 封装 `success_resp(data, msg="ok")`、`fail_resp(code, msg)`

§2.5 数据库 SQLAlchemy 2.0 异步规范
- 全部使用异步数据库会话 `async`，禁止同步 session
- ORM 模型继承 `db/base.py` 中统一 Base 基类，自动携带主键 id、创建时间、更新时间
- 数据库增删改查逻辑全部放入 `services`，路由层绝不直接执行 SQL
- 禁止硬编码 SQL 语句，优先使用 ORM；原生 SQL 必须用参数化查询，防注入

§2.6 异常与日志规范
- 自定义业务异常继承基础异常类，区分：参数错误、鉴权失败、资源不存在、LLM 调用失败、数据库异常
- 全局注册异常中间件，捕获所有未处理异常，统一格式化返回，不暴露堆栈给前端
- 关键操作（接口入参、大模型调用、数据库修改）必须打日志，日志分级：`DEBUG/INFO/WARNING/ERROR`
- 日志输出同时控制台 + 本地文件轮转，不在业务代码手写 print
- 
§2.7 大模型（Claude）调用规范
- LLM 请求、流式输出、token 统计全部封装至 services/llm_client.py
- SSE 流式响应严格使用 FastAPI StreamingResponse，封装通用 SSE 工具类
- API Key、模型名称、上下文长度限制全部从配置文件读取，禁止硬编码密钥
- 对话历史拼接、prompt 模板统一抽离为常量或配置，路由不可直接写 Prompt
- prompt的组装相关的方法放在`services/prompt_service.py`中

§2.8 代码格式与工程约束
- 格式化工具：ruff + black，代码必须无 lint 告警
- 类型注解全覆盖：函数入参、返回值必须写 def func(a: str) -> dict:
- 单个函数代码行数不超过 80 行，超出行数必须拆分子函数
- 导入顺序：标准库 → 第三方包 → 项目内部模块，分块空行隔开
- 禁止循环导入，模块依赖单向层级：main → api → service → db/utils

§2.9 注释规范 
- 文件头部：简述本文件用途
- 类上方：说明类职责
- 复杂函数必须写 docstring（Args、Return、Raise）
- 晦涩业务逻辑行内添加单行注释，不冗余注释显而易见代码

### 三、前端 Vue3 + Vite + TS 强制编码规范(frontend/)
§3.1 目录结构约定
```
frontend/
├── src/
│   ├── main.ts               # 入口挂载
│   ├── App.vue
│   ├── router/               # VueRouter 路由配置，按页面模块拆分
│   │   ├── index.ts
│   │   └── modules/
│   ├── store/                # Pinia 状态管理，按业务分仓库
│   │   ├── chat.ts
│   │   ├── user.ts
│   │   └── index.ts
│   ├── api/                  # axios 请求封装 + 接口分组
│   │   ├── request.ts        # 基础axios实例、拦截器、错误统一处理
│   │   ├── chatApi.ts
│   │   └── userApi.ts
│   ├── views/                # 页面视图，一级页面文件夹
│   │   ├── Chat/
│   │   ├── Login/
│   │   └── Setting/
│   ├── components/           # 公共组件
│   │   ├── common/           # 全局通用基础组件（按钮、输入框、弹窗）
│   │   └── business/         # 业务组件（对话气泡、消息列表）
│   ├── types/                # TS 全局类型定义，接口入参出参Type
│   │   ├── chat.d.ts
│   │   └── user.d.ts
│   ├── utils/                # 工具函数、格式化、存储、加密
│   ├── hooks/                # 组合式hooks抽离复用逻辑
│   └── assets/               # 静态资源、样式、图标
├── vite.config.ts
├── tsconfig.json
└── package.json    
```

§3.2 命名规范
- 文件 & 文件夹：
    - 页面 / 组件目录:`PascalCase` 大驼峰
    - ts/js 工具、api 文件：`camelCase` 小驼峰
- Vue 单文件组件 .vue：文件名大驼峰 `MessageItem.vue`
- 变量 / 普通函数：小驼峰 `camelCase`
- 常量：全大写下划线 `const MAX_HISTORY_NUM = 10`
- TS 类型 / 接口：大驼峰 `interface ChatSendParams`

§3.3 Vue 语法强制规范
- 统一使用 `<script setup lang="ts"> `组合式 API，禁止 Options API
- 组件 `props` 必须使用 `defineProps` 并标注 TS 类型，开启必填校验
- 事件使用 `defineEmits` 显式声明，禁止隐式 `$emit`
- 响应式数据：基础类型用 `ref`，对象数组用 `reactive`，解构使用 `toRefs`
- `v-if` 与 `v-for` 禁止同写一个标签；`v-for` 必须绑定唯一 `key`
样式 `scoped`：所有 Vue 组件 style 添加 `scoped`，全局样式放入 `assets/css`

§3.4 TypeScript 强约束
- 所有接口请求入参、返回结果必须提前定义 `interface/type`，不允许`any`滥用
- 禁止 `let anyData: any`，确实无法定义类型使用 `unknown` 并手动类型收窄
- `Pinia` 仓库 `state`、`actions` 返回值全部标注类型
- 路由 `meta`、路由参数统一在 `types` 下声明类型

§3.5 Axios 请求与接口规范
- 仅在 `src/api/request.ts` 初始化 axios 实例，统一配置：baseURL、超时、请求头 token 携带
- 请求拦截器：自动附加 Authorization 鉴权头；响应拦截器统一处理错误码（401 登出、500 提示）
- 按业务模块拆分 api 文件，每个请求封装为 `async` 函数，返回 `Promise` 并携带 TS 类型
- SSE 流式对话单独封装 `EventSource` 工具，统一挂载错误重连、关闭销毁逻辑
接口地址与后端`/api/v1`完全对齐，路径一字不差

§3.6 `Pinia` 状态管理规范
- 一个业务模块一个 `store`（chat、user、app 设置分开）
- `state` 只存放全局共享数据，页面临时数据放在组件内 `ref/reactive`
复杂数据处理、请求逻辑封装在 `actions`，组件只调用 `action`，不直接修改 `state`
- `getters` 用于派生计算属性，不写冗余逻辑

§3.7 组件拆分原则
- 单文件 Vue 组件行数≤300 行，过长必须拆分子组件
- 可复用 UI 抽入`components/common`；业务复用抽入`components/business`
- 页面只做布局与数据分发，具体交互逻辑抽入hooks

§3.8 样式规范
- 优先使用 UI 库自带样式，自定义样式使用 CSS 变量统一主题色
- class 命名使用 BEM 规范：`block__element--modifier`
- 禁止行内大量 style，动态样式优先绑定 class
§3.9 注释与 Git 规范
- 工具函数、复杂 Hook 添加 TS Doc 注释
- 接口文件顶部标注对应后端接口地址与用途
- commit 提交规范：
  - feat: 新增功能
  - fix: 修复 bug
  - refactor: 代码重构无功能变更
  - style: 格式调整
  - docs: 文档修改
### 四、Docker 容器化部署规范
§4.1 目录结构约定
```
docker/
├── backend/
│   ├── Dockerfile          # 后端多阶段构建镜像
│   └── .dockerignore
├── frontend/
│   ├── Dockerfile          # 前端打包+Nginx静态镜像
│   └── .dockerignore
├── nginx/
│   └── nginx.conf          # Nginx反向代理配置
└── docker-compose.yml      # 本地一键启动编排文件
```
§4.2 后端 Dockerfile 强制规范（多阶段构建）

**构建阶段（builder）**
- 基础镜像固定：python:3.12
- 仅安装编译依赖、pip 依赖，缓存依赖层优化构建速度
- 禁止在最终镜像保留源码、pip 缓存、编译文件
**运行阶段（runtime）**
- 使用极简基础镜像，缩小镜像体积
- 非 root 用户运行容器，禁止 root 权限启动服务
- 暴露端口固定 8000，使用 uvicorn main:app --host 0.0.0.0 --port 8000
- 环境变量全部通过 ENV / 容器运行时 -e 注入，绝不硬编码配置
- 时区统一设置 Asia/Shanghai
- 健康检查配置 HEALTHCHECK，监控服务存活状态
- `backend/.dockerignore` 必须忽略
`__pycache__`、`.git`、`.env`、`venv`、`tests`、`docs`、`*.md`、`.ruff_cache`

§4.3 前端 Dockerfile 强制规范（双阶段）
- 构建阶段：`node:18-alpine` 执行 `pnpm install + vite build`
- 运行阶段：`nginx:alpine` 仅拷贝 dist 产物与自定义 nginx 配置
- 不携带 `node_modules`、源码、环境配置文件进最终镜像
- Nginx 监听 80 端口，开启 `gzip 压缩`、`静态资源缓存`、`SPA 路由 history 模式`兜底
- 接口反向代理统一指向后端容器服务名：8000

§4.4 `docker-compose.yml` 编写规则
- 服务拆分：backend、frontend、nginx、postgres、redis 按需声明
- 网络使用 compose 默认内网网络，数据库不对外映射端口（生产环境）
- 数据卷挂载：PG 数据、Redis 数据持久化挂载 volume，避免容器删除数据丢失
- 环境变量通过 `.env` 文件统一注入，compose 不写入明文密钥
- 区分 `dev / prod` 两套 compose 配置：
- docker-compose.dev.yml：挂载本地代码，热更新调试
- docker-compose.prod.yml：纯镜像启动，无代码挂载

§4.5 镜像标签与版本规范
- 镜像仓库前缀统一：`{registry}/{project}-{module}:{tag}`
示例：harbor.example.com/ai-demo/backend:v1.0.0
前端：harbor.example.com/ai-demo/frontend:v1.0.0
- Tag 命名规则：
    - 正式版本：v主.次.修订 如 v1.2.0
    - 开发测试版：dev-{git短哈希}
    - 最新稳定版固定 latest
    - 镜像推送前必须：构建 → 本地启动验证 → 推送仓库

§4.6 容器安全约束
- 容器禁止特权模式 `privileged: true`
限制容器 CPU、内存资源 `deploy.resources.limits`
- 敏感环境变量不打入镜像，仅运行时注入
后端容器禁止暴露数据库端口至宿主机公网
### 五、CI/CD 流水线规范（基于 GitHub Actions）(DEMO初期暂时不搞)
§5.1 流水线文件存放路径
`.github/workflows/`
```
.github/workflows/
├── lint.yml          # 代码检查流水线
├── build-image.yml   # 镜像构建&推送流水线
├── deploy-dev.yml    # 自动部署测试环境
└── deploy-prod.yml   # 手动审批部署生产环境
```

§5.2 分支管理策略（Git Flow 简化版）
|分支	|用途   |触发CI行为|
|-      |-  |   -|
|main|	生产稳定分支，受保护禁止直接 push	|手动触发构建 prod 镜像、审批后部署生产|
|develop	|开发主分支|	自动构建 dev 镜像、自动部署测试环境|
|feature/*	|功能开发分支|	仅执行代码 lint + 单元测试，不打包部署|
|hotfix/*	|线上紧急修复分支|	合并 main 后打版本 tag，推送生产镜像|

**Commit 提交规范（强制）**
```
feat: 新增对话流式接口
fix: 修复SSE断连重连bug
refactor: 重构service层目录结构
docs: 更新CLAUDE.md与部署文档
style: 格式化代码，无逻辑变更
test: 新增单元测试
ci: 优化GitHub Actions流水线
docker: 优化镜像多阶段构建
```
§5.3 各流水线职责规范
(1)`lint.yml` 代码质量检查（所有 PR/Push 必跑）:
    ①后端：`ruff lint + ruff format` 格式校验 + 类型检查 `mypy`
    ②前端：`eslint + prettier + tsc` 类型编译校验
    ③存在 Lint 错误直接阻断 PR 合并
    跳过规则仅允许工程配置文件，业务代码必须 100% 通过
(2)build-image.yml 镜像构建推送
**触发条件：**
- develop 分支 push：构建 dev-{git-sha} 镜像，推送镜像仓库
main 分支打 tag（v*..）：构建版本镜像 + latest 镜像，推送仓库
流水线步骤固定顺序：
**检出代码**
- 登录私有镜像仓库（Harbor/DockerHub），账号密钥存放 GitHub Actions Secrets
- 分别构建后端、前端 Docker 镜像
推送镜像至仓库
- 输出镜像版本信息存入流水线日志

(3)`deploy-dev.yml` 测试环境自动部署
触发：develop 分支镜像构建完成后自动触发
**步骤：**
①SSH 连接测试机服务器
②拉取最新 dev 镜像
③执行 docker-compose -f ④`docker-compose.prod.yml pull && up -d`
⑤执行容器健康探测，超时则流水线失败并发送告警
⑥清理服务器无用悬空镜像，释放磁盘空间

(4)`deploy-prod.yml` 生产环境部署
- 手动触发 + 双人审批 才可执行，禁止自动部署
- 前置校验：必须基于 main 分支正式版本 tag 镜像
- 部署前备份数据库数据
- 采用滚动更新方式重启容器，避免服务中断
- 部署完成后执行接口冒烟测试，关键接口调用验证可用性
部署失败自动回滚至上一个版本镜像

§5.4 环境与密钥管理规范
- 所有敏感信息（仓库账号、数据库密码、LLM Key、服务器 SSH 密钥）
统一存放于仓库 GitHub Actions Secrets，绝不硬编码入代码 / 配置文件
- 环境分层：
`dev`：开发测试环境
`prod`：生产正式环境
两套环境使用不同配置文件与数据库实例，数据完全隔离
禁止在镜像内嵌入任何业务密钥，全部通过运行时环境变量注入

§5.5 流水线输出与日志规范
- 每次构建打印镜像完整地址与 tag，方便追溯版本
- 部署日志持久化，关键步骤输出 Markdown 摘要
- 流水线失败触发钉钉 / 企业微信机器人告警，推送失败分支、执行人、错误信息

§5.6 可选扩展 CI 环节（按需启用）
- 单元测试：`pytest`（后端）、`vitest`（前端），PR 阶段执行测试用例
- 漏洞扫描：使用 `trivy` 扫描 Docker 镜像高危漏洞，阻断含高危漏洞镜像推送
- 制品归档：接口文档、构建产物随流水线打包归档

### 六、跨前后端协作强制约束
- 后端新增接口必须先在 ·schemas· 定义出入参结构，前端同步在 `types` 建立对应 TS 类型
- 后端修改返回字段，必须同步告知并更新前后端类型定义，禁止隐性字段变更
- 后端所有接口开启自动 OpenAPI 文档 /docs，前端对接以接口文档为准
- 环境区分：`dev` 开发环境、`test` 测试环境、`prod` 生产环境，前后端均使用环境变量配置地址，硬编码域名
- 流式对话 SSE 接口后端固定使用`text/event-stream`响应头，前端固定 `EventSource` 监听解析
- 除去流式对话外还应满足非流式对话
### 七、Claude 生成代码额外约束
- 任何新增 / 修改代码必须严格匹配上文目录结构，不得自建文件夹、随意丢文件到根目录
- 新增功能优先分层：`后端路由→Service→DB`；`前端页面→Api→Pinia→Hooks`
- 如需补充配置、依赖、安装命令，必须附带清晰可执行指令
- 若原有代码存在不符合本规范写法，优先重构对齐规范再新增逻辑，并标注修改点
- 不生成冗余无用代码，删除废弃注释、无效导入、未使用变量
- 输出代码块前可简要说明改动模块与文件路径，便于直接粘贴落地
### 八、项目禁用项
- **后端禁止**
    - 直接在路由函数写 SQL、大模型调用、大量业务逻辑
    - 明文硬编码密钥、数据库地址、敏感配置
    - 同步 IO 混用异步项目（time.sleep、同步 requests）
    - 不捕获异常直接抛出原生错误返回前端堆栈
- **前端禁止**
    - 全局随意挂载变量污染 `window`
    - 大量 DOM 操作原生 JS 绕过 Vue 响应式
    - 接口地址、token 密钥硬编码写死在业务代码
    - 组件内多层嵌套 `ifelse` 不做抽离