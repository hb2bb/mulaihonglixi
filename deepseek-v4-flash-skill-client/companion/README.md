# 栖语 · 本地伴侣 Demo

在当前项目已有网页之外，提供一套可直接体验的多人物本地应用。默认角色为岑野夏；后端只用 Python 标准库，前端无 CDN 或额外下载。Android 工程位于 `../android`，可构建独立运行的测试 APK。

## 启动

在 `deepseek-v4-flash-skill-client` 目录执行：

```bash
npm run demo
# 或
PYTHONPYCACHEPREFIX=/tmp/qiyu-pycache python3 local_demo.py
```

打开 http://127.0.0.1:8765 。服务只监听本机。可通过 `--port` 和 `--data` 更改端口及数据库路径。

在设置中填入有效的 DeepSeek API Key，点击保存，再测试连接。也可以复用项目现有 `.env` 中的 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_MODEL`。默认连接官方 `https://api.deepseek.com`；不需要第二个记忆、状态或精选 Key。模型名称可在设置中修改。

设置界面输入的 Key 仅保留在当前服务内存中，重启需重填。现有 `.env` 是用户自行维护的明文配置，本 Demo 不改写它。Key 不返回前端、不入数据库、不进备份。

## 功能

- 内置岑野夏聊天模板：对话人格模板常驻，背景细节按需检索；旧版未修改的默认核心自动升级并保留历史版本。
- 人物库支持创建、编辑、版本恢复、复制与删除；复制不复制记忆。
- 每张卡有独立“聊天风格”。留空按核心人格推导，也可在编辑卡片时点击“根据人物卡生成聊天风格”，确认并保存；定制向导会同时生成。风格跟随版本和备份，不共享到其他人物。
- 每个人物拥有独立对话、长期记忆和状态，同一人物可新建多段对话。
- 独立试聊不读取也不写入正式记忆；可从定制草稿先试聊再调整。
- 定制向导支持男性、女性和自定义性别，根据回答提问，支持自由描述、选项、提前生成、修改、历史草稿恢复和手动编辑。
- SQLite 保存消息和记忆。回复成功后加入持久化后台整理队列，失败最多自动尝试3次，之后可手动重试。
- 人物库可直接打开每个人物的记忆并搜索，支持来源查看、更正、删除、手动增加和全部清空。删除或更正会使旧来源退出召回，相关旧助手回复也退出上下文，避免重新引入被遗忘信息。原始记录仍可在聊天中查看；删除对话则同时删除其来源记忆。
- 每轮提供核心人格、规则、重要边界、关系、当前话题和最近最多20条有效原始消息；历史输入另有字符预算。
- 信息精选先进行本地中英文词项召回，有记忆候选时调用 DeepSeek 选择候选ID；可关闭模型精选；错误回退到本地检索。不是向量语义检索，模糊回忆可能漏召回，需继续测评优化。
- 当前时间每次从主机时区读取。心情根据成功整理的对话更新，30分钟后不再注入旧状态。天气默认关闭，启用需自行填写城市和经纬度，每30分钟从 Open-Meteo 刷新。
- 输入框旁提供32个 emoji，点选插入光标位置，确认后发送；角色可偶尔使用 emoji，尊重用户禁用要求。
- 回复生成后检查答非所问、虚构事实和违反边界等实质问题，最多生成三份候选。生成与检查使用 Flash 思考模式，预留推理预算；检查失败会在调试面板显示，额外调用会增加延迟与 API 费用。
- 本轮调试面板展示质量检查、候选、选中证据、近期消息数、耗时和输入字符数，不展示私有提示或 Key。
- JSON 备份/导入包含人物、历史版本、对话、记忆和定制草稿；导入创建新ID的独立副本，不覆盖现有数据，未完成整理恢复入队。

本地数据库默认位于 `.local-data/companion.sqlite3`，已加入 Git 忽略。备份文件包含私人聊天，请自行保管。调用 DeepSeek 时，本轮消息、相关设定和记忆会发给 API；本地存储不意味着离线推理。

## 两个入口共用同一实现

独立 Python 入口为主体验方式。现有 Next/Vinext 项目新增 `/demo` 入口，在本机转发到同一个 8765 服务，因此数据与行为一致。运行 `npm run dev` 前仍需启动 `npm run demo`。远程 Host 的 `/demo` 请求会被拒绝，不将本地数据库暴露到部署站点。

## 检查

```bash
npm run test:demo
npm test
npm run build
node --check companion/static/app.js
```

现有旧体验台与其真冬配置保持独立。Android 工程通过内置 Python 运行同一服务与 SQLite，Key 接入 Android Keystore；手机无需连接电脑。构建与安装说明见 `../android/README.md`。

## 人物还原测试

`scripts/eval_persona_only.py --live --template ../skills/cen-yexia-girlfriend/references/persona-chat-template.md --thinking --effort max --reviewed --suite validation --repeats 2 --output evals/results/persona-validation.json`

仅使用人物卡与对话做隔离测试，默认不启用记忆、精选和通用聊天提示。`--reviewed` 显式增加依据人物卡的审查；`--suite long` 测长对话；`--compose` 为未采用的实验流程。所有调用均为真实付费 API 调用。人工验收标准见 `evals/persona-acceptance.json`，自动审查通过不能证明所有情境都稳定。
