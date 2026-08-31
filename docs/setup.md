# Local Setup

| 元数据    | 值                                         |
| --------- | ------------------------------------------ |
| Authority | 本地与 Docker 启动方式、环境变量与调试命令 |

本地开发默认只由 Docker Compose 管理 PostgreSQL，API 与两个前端应用在本机进程中运行。
完整容器栈仍可通过 Docker Compose 直接启动。

## 1. 环境要求

| 工具       | 版本口径                   | 说明                        |
| ---------- | -------------------------- | --------------------------- |
| Windows    | Windows 11 + PowerShell 7+ | UTF-8 编码                  |
| Docker     | Docker Desktop             | 包含 Docker Compose         |
| Node.js    | 24.18.0                    | `engines.node` 限定 Node 24 |
| pnpm       | 11.13.1                    | 由 Corepack 固定            |
| Python     | 3.13                       | 仅用于后端本机调试          |
| uv         | 0.7.8                      | 管理 Python 依赖与虚拟环境  |
| PostgreSQL | postgres:17-alpine         | Docker Compose 镜像         |

## 2. 环境变量

```powershell
Copy-Item .env.example .env
```

`.env.example` 只声明当前运行时实际消费的配置。严禁提交 `.env`、密钥、Cookie 或其他凭据。

真实研究助手使用千问 AI 平台的 OpenAI 兼容接口。根目录 `.env` 或 Windows 用户
环境变量使用平台官方名称 `DASHSCOPE_API_KEY`，并显式设置 `DASHSCOPE_MODEL`。
仓库没有默认模型；可用型号由运行环境选择。`DASHSCOPE_EXPLICIT_MODEL_REVISION` 可选，
提供时须与显式模型身份一致；浮动别名的 revision 保持为空。这些变量只由 API 读取，
不得使用 `PUBLIC_*` 或 `VITE_*` 前缀。应用可在未配置模型时启动；研究助手同时具备
密钥与模型身份才进入 `ready`。`start-dev.bat` 的真实研究健康门禁要求该状态。

development/test/integration 也可在 Workspace 顶栏“模型服务”中配置默认 DashScope Qwen，或自定义
OpenAI Chat Completions-compatible 服务。Base URL 始终可见；该配置是实例级、跨 Project 复用的
PostgreSQL override，保存前会调用 `/chat/completions`
验证；入口不会自动打断工作台，“后续配置”直接关闭弹窗。production 只显示部署配置状态，不允许匿名 Session 修改。

| 变量                               | 默认值                                | 作用                                                        |
| ---------------------------------- | ------------------------------------- | ----------------------------------------------------------- |
| `PUBLIC_WORKSPACE_URL`             | `http://localhost:5173/workspace`     | Site 主入口链接                                             |
| `VITE_API_BASE_URL`                | `http://localhost:8000`               | Workspace 可访问的 API origin                               |
| `VITE_SITE_URL`                    | `http://localhost:4321`               | Workspace “退出系统”返回的 Brand Site origin                |
| `SESSION_COOKIE_SECURE`            | `false`                               | 本地 HTTP 设为 false，生产部署必须显式为 true               |
| `SESSION_TTL_SECONDS`              | `86400`                               | 匿名 Session 有效期                                         |
| `SESSION_RETENTION_SECONDS`        | `2592000`                             | 无 Project 引用的过期/撤销 Session 保留期                   |
| `SHARE_RETENTION_SECONDS`          | `2592000`                             | 过期/撤销 ShareSnapshot 保留期                              |
| `CURSOR_SIGNING_KEY`               | `development-only-cursor-signing-key` | 不透明分页 cursor HMAC 密钥                                 |
| `DATABASE_URL`                     | Docker Compose PostgreSQL URL         | ResearchRun、Artifact、Evidence 与 ResearchInput 的权威存储 |
| `DASHSCOPE_TIMEOUT_SECONDS`        | `300`                                 | Qwen 单次长结构化生成的超时秒数                            |
| `DASHSCOPE_MAX_RETRIES`            | `0`                                   | Provider SDK 不内嵌重试；恢复由 ResearchRun Step 负责      |
| `RESEARCH_INPUT_UPLOAD_DIR`        | `.data/research-inputs`               | ResearchInput 内容寻址存储目录                              |
| `URL_FETCH_ALLOWED_HOSTS`          | 空                                    | URL ResearchInput host allowlist；空值 fail closed          |
| `MODEL_PROVIDER_CONFIG_KEY`        | 空                                    | 实例级模型凭据加密根密钥；空值回退稳定 `CURSOR_SIGNING_KEY` |
| `MODEL_PROVIDER_ALLOWED_HOSTS`     | 空                                    | custom OpenAI-compatible 远程 host allowlist                |
| `MODEL_PROVIDER_CONFIG_RATE_LIMIT` | `10`                                  | 每 Session 模型配置写限流                                   |
| `PADDLEOCR_VL_BASE_URL`            | 空                                    | 远程 PaddleOCR-VL HTTP 服务 origin                          |
| `PADDLEOCR_VL_MODEL_REVISION`      | 空                                    | 远程模型的明确 revision；必须与 Base URL 成对配置           |
| `PADDLEOCR_VL_LOCAL_BUNDLE`        | 空                                    | 已验证本地模型 bundle 路径                                  |
| `PADDLEOCR_VL_TIMEOUT_SECONDS`     | `60`                                  | 单页远程视觉解析超时                                        |

PaddleOCR-VL 远程配置与本地 bundle 严格互斥：远程模式必须同时设置 Base URL 与
model revision；本地模式只设置 bundle。两者同时设置会在 Settings 校验阶段直接失败，
两者均未设置时 native 解析仍可运行，但请求 hybrid/paired 视觉执行会 fail closed。

## 3. Docker Compose 启动

```powershell
docker compose up --build --wait
```

需要使用仓库根目录下已验证、未纳入 Git 的 `models/` 本地 PaddleOCR-VL bundle 时，
选择带视觉依赖的 API target 并只读挂载模型：

```powershell
docker compose -f docker-compose.yml -f docker-compose.paddle-local.yml up --build --wait
```

该覆盖层仍启动同一个 API、`HybridScientificDocumentParser` 和 Publisher，只改变视觉
backend 的部署依赖；模型权重不会复制进镜像。远程 Paddle 服务不需要覆盖层，只需在
`.env` 配置 `PADDLEOCR_VL_BASE_URL` 与 `PADDLEOCR_VL_MODEL_REVISION`。

### Windows 一键启动

在 Windows 11 + Docker Desktop 环境中，可从仓库根目录运行：

```powershell
.\start-dev.bat
```

脚本使用三个窗口：当前窗口执行工具、依赖、PostgreSQL 与当前 schema 前置检查；Backend
窗口运行 FastAPI；Frontend 窗口运行 Brand Site 与 Workspace。后端可访问后才启动前端，
两个前端均可访问后自动打开 Brand Site 首页。脚本会停止同一 Compose project 中占用应用
端口的容器，但保留 PostgreSQL 与数据卷。关闭本地服务时，在 Backend/Frontend 窗口按
`Ctrl+C`，再执行 `docker compose -p xingwen-astro-ai-dev stop postgres`。

| 服务        | 职责                              | 默认地址                |
| ----------- | --------------------------------- | ----------------------- |
| `site`      | Astro Brand Site                  | `http://localhost:4321` |
| `workspace` | React Research Workspace          | `http://localhost:5173` |
| `api`       | FastAPI `/api`                    | `http://localhost:8000` |
| `schema`    | 当前 SQLAlchemy 模型建表 one-shot | 无端口                  |
| `postgres`  | PostgreSQL 17                     | `localhost:5432`        |

完整容器栈的依赖顺序为 `postgres healthy -> schema exited 0 -> api healthy -> workspace`。
分窗口启动时，前置检查显式从当前 SQLAlchemy 模型建立 schema，应用进程不隐式改表。

## 4. 前端本机调试

```powershell
corepack enable
corepack prepare pnpm@11.13.1 --activate
pnpm install --frozen-lockfile
pnpm dev
```

常用根验证命令：

```powershell
pnpm format:check
pnpm check:docs
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e
pnpm check
```

## 5. 后端本机调试

```powershell
Set-Location apps/api
uv sync --frozen
uv run pytest
uv run uvicorn app.main:app --reload
```

本机使用已验证的 PaddleOCR-VL bundle 时安装同一项目的可选视觉依赖组：

```powershell
uv sync --frozen --group visual
$env:PADDLEOCR_VL_LOCAL_BUNDLE = (Resolve-Path (Join-Path (Get-Location) "..\..\models"))
uv run uvicorn app.main:app --reload
```

数据库 Schema：

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/xingwen_astro_ai"
uv run python -m app.db.schema
```

当前 SQLAlchemy 模型与 PostgreSQL 不变量是唯一 schema 权威；开发数据库发生结构变化时直接重建。

Schema 导出：

```powershell
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas
```

## 6. Release Candidate 门禁

真实 Qwen 闭环的最终验证在隔离的 Release Candidate Compose 栈中运行
`tests/e2e-integration/release-candidate-live.spec.ts`，不复用开发栈、不触碰既有数据卷。

前置条件：

- 工作区干净，`HEAD` 即待验证的精确 source commit；
- 已认证的 GitHub CLI 可读取该提交的 CI 与 CodeQL 成功结果；
- 根目录存在 `.env` 与本地 PaddleOCR-VL `models` 捆绑；
- 当前 shell 显式提供 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_MODEL`；
- `URL_FETCH_ALLOWED_HOSTS` 明确包含 `arxiv.org`，用于关联选中论文的开放全文；
- `DASHSCOPE_EXPLICIT_MODEL_REVISION` 可选，提供时与模型身份一致。

URL ResearchInput 使用来源 allowlist 和公网 DNS 地址校验。使用 Fake-IP 代理的开发网络，
需为已授权的全文来源配置真实 DNS 解析，使宿主机与容器均获得公网地址。

运行（PowerShell）：

```powershell
$env:DASHSCOPE_MODEL = "<当前账户可用的 Qwen 模型>"
$env:DASHSCOPE_EXPLICIT_MODEL_REVISION = ""
$env:URL_FETCH_ALLOWED_HOSTS = "arxiv.org"
$env:RELEASE_CANDIDATE_SOURCE_COMMIT = git rev-parse HEAD
pnpm release-candidate
```

脚本先校验 `HEAD` 与 `RELEASE_CANDIDATE_SOURCE_COMMIT` 完全一致且工作区干净，随后以唯一
Compose project（`xingwen-rc-<sha8>-<pid>`）`up --build --wait`，安装 Chromium 并执行 live
门禁；结束后 `down --volumes --remove-orphans` 清理该隔离项目自身的容器与临时卷。API Key、
原始 provider 响应与私有 reasoning 不写入门禁产物。

每次执行的证据保存在 `.artifacts/release-candidate/<source_commit>/<execution_time>/`：
NASA 查询、目标选择与来源快照，文献与科学结果，ProducerExecution，活跃任务恢复和浏览器结果。
同目录的 `handoff-manifest.json` 从根目录能力清单生成，填入精确提交、生成时间和各项实际验证结果；
缺失或失败的证据保持未验证。运行时 Chromium 与临时文件也位于仓库 `.artifacts/tooling/`。

## 7. 常见问题

| 问题                | 处理方式                                                                 |
| ------------------- | ------------------------------------------------------------------------ |
| Docker 启动失败     | 查看 `docker compose ps` 与 `docker compose logs <service>`              |
| 浏览器请求 API 失败 | 将 `VITE_API_BASE_URL` 设为可访问 origin；Workspace 与 API 统一 hostname |
| CORS 报错           | 核对 Workspace 实际 origin 与后端 `CORS_ORIGINS` 配置                    |
| 前端依赖异常        | 删除 `node_modules` 后执行 `pnpm install --frozen-lockfile`              |
| 后端依赖异常        | 执行 `uv sync --frozen` 重建虚拟环境                                     |
| E2E 缺少浏览器      | 执行 `pnpm exec playwright install chromium`                             |
