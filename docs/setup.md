# Local Setup

| 元数据    | 值                                         |
| --------- | ------------------------------------------ |
| Authority | 本地与 Docker 启动方式、环境变量与调试命令 |

本地开发默认只由 Docker Compose 管理 PostgreSQL，API 与两个前端应用在本机进程中运行。完整容器栈仍可通过 Docker Compose 直接启动。

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

`.env.example` 是 provider-specific 环境键、模型身份、默认端点和其他当前运行配置的唯一操作事实。治理文档不复制外部服务名称或模型标识；实际运行必须按 `.env.example` 和服务端配置校验读取，不得另建第二份配置说明。

真实研究助手必须使用赛题指定合格模型的官方服务。未配置有效凭据时，启动与运行必须明确失败，不得用 fixture、模板回答或本地假响应伪装真实 Agent。浮动模型别名不能伪造不可变 revision；只有 provider 明确提供固定 revision 时才记录。

development/test/integration 可在 Workspace 顶栏“模型服务”中安装一个经过真实连接探测的实例级 override，或使用受治理的标准兼容聊天接口。Base URL 在需要用户配置时保持可见；配置跨 Project 复用并加密持久化。production 只显示部署配置状态，不允许匿名 Session 修改。

| 变量                               | 默认值                                | 作用                                                        |
| ---------------------------------- | ------------------------------------- | ----------------------------------------------------------- |
| `PUBLIC_WORKSPACE_URL`             | `http://localhost:5173/workspace`     | Site 主入口链接                                             |
| `VITE_API_BASE_URL`                | `http://localhost:8000`               | Workspace 可访问的 API origin                               |
| `VITE_SITE_URL`                    | `http://localhost:4321`               | Workspace 返回 Brand Site 的 origin                         |
| `SESSION_COOKIE_SECURE`            | `false`                               | 本地 HTTP 设为 false，生产部署必须显式为 true               |
| `SESSION_TTL_SECONDS`              | `86400`                               | 匿名 Session 有效期                                         |
| `SESSION_RETENTION_SECONDS`        | `2592000`                             | 无 Project 引用的过期/撤销 Session 保留期                   |
| `SHARE_RETENTION_SECONDS`          | `2592000`                             | 过期/撤销 ShareSnapshot 保留期                              |
| `CURSOR_SIGNING_KEY`               | `development-only-cursor-signing-key` | 不透明分页 cursor HMAC 密钥                                 |
| `DATABASE_URL`                     | Docker Compose PostgreSQL URL         | ResearchRun、Artifact、Evidence 与 ResearchInput 的权威存储 |
| `RESEARCH_INPUT_UPLOAD_DIR`        | `.data/research-inputs`               | ResearchInput 内容寻址存储目录                              |
| `URL_FETCH_ALLOWED_HOSTS`          | 空                                    | URL ResearchInput host allowlist；空值 fail closed          |
| `MODEL_PROVIDER_CONFIG_KEY`        | 空                                    | 实例级模型凭据加密根密钥；空值回退稳定 `CURSOR_SIGNING_KEY` |
| `MODEL_PROVIDER_ALLOWED_HOSTS`     | 空                                    | 自定义兼容服务远程 host allowlist                           |
| `MODEL_PROVIDER_CONFIG_RATE_LIMIT` | `10`                                  | 每 Session 模型配置写限流                                   |

Provider-specific secret/model 环境键不在本表重复，直接以 `.env.example` 为准；它们仅由 API 读取，不得使用浏览器公开前缀。

## 3. Docker Compose 启动

```powershell
docker compose up --build --wait
```

### Windows 一键启动

在 Windows 11 + Docker Desktop 环境中，可从仓库根目录运行：

```powershell
.\start-dev.bat
```

脚本使用三个窗口：当前窗口执行工具、依赖、PostgreSQL 与当前 schema 前置检查；Backend 窗口运行 FastAPI；Frontend 窗口运行 Brand Site 与 Workspace。后端可访问后才启动前端，两个前端均可访问后自动打开 Brand Site 首页。脚本会停止同一 Compose project 中占用应用端口的容器，但保留 PostgreSQL 与数据卷。关闭本地服务时，在 Backend/Frontend 窗口按 `Ctrl+C`，再执行当前 Compose project 的数据库 stop 命令。

| 服务        | 职责                              | 默认地址                |
| ----------- | --------------------------------- | ----------------------- |
| `site`      | Astro Brand Site                  | `http://localhost:4321` |
| `workspace` | React Research Workspace          | `http://localhost:5173` |
| `api`       | FastAPI `/api`                    | `http://localhost:8000` |
| `schema`    | 当前 SQLAlchemy 模型建表 one-shot | 无端口                  |
| `postgres`  | PostgreSQL 17                     | `localhost:5432`        |

完整容器栈的依赖顺序为 `postgres healthy -> schema exited 0 -> api healthy -> workspace`。分窗口启动时，前置检查显式从当前 SQLAlchemy 模型建立 schema，应用进程不隐式改表。

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

## 6. 常见问题

| 问题                | 处理方式                                                                 |
| ------------------- | ------------------------------------------------------------------------ |
| Docker 启动失败     | 查看 `docker compose ps` 与 `docker compose logs <service>`              |
| 浏览器请求 API 失败 | 将 `VITE_API_BASE_URL` 设为可访问 origin；Workspace 与 API 统一 hostname |
| CORS 报错           | 核对 Workspace 实际 origin 与后端 `CORS_ORIGINS` 配置                    |
| 前端依赖异常        | 删除 `node_modules` 后执行 `pnpm install --frozen-lockfile`              |
| 后端依赖异常        | 执行 `uv sync --frozen` 重建虚拟环境                                     |
| E2E 缺少浏览器      | 按锁定前端工具链安装当前 Browser runtime                                 |
