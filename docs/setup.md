# Local Setup

| 元数据 | 值 |
| --- | --- |
| Authority | 本地与 Docker 启动方式、环境变量与调试命令 |

本地开发采用 Docker-first 模式。Docker Compose 管理 `site`、`workspace`、`api`、`migrate`、`postgres`；前端本机调试统一在仓库根目录执行。

## 1. 环境要求

| 工具 | 版本口径 | 说明 |
| --- | --- | --- |
| Windows | Windows 11 + PowerShell 7+ | UTF-8 编码 |
| Docker | Docker Desktop | 包含 Docker Compose |
| Node.js | 24.18.0 | `engines.node` 限定 Node 24 |
| pnpm | 11.13.1 | 由 Corepack 固定 |
| Python | 3.13 | 仅用于后端本机调试 |
| uv | 0.7.8 | 管理 Python 依赖与虚拟环境 |
| PostgreSQL | postgres:17-alpine | Docker Compose 镜像 |

## 2. 环境变量

```powershell
Copy-Item .env.example .env
```

`.env.example` 只声明当前运行时实际消费的配置。严禁提交 `.env`、密钥、Cookie 或其他凭据。

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `PUBLIC_WORKSPACE_URL` | `http://localhost:5173/workspace` | Site 主入口链接 |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Workspace 可访问的 API origin |
| `SESSION_COOKIE_SECURE` | `false` | 本地 HTTP 设为 false，生产部署必须显式为 true |
| `SESSION_TTL_SECONDS` | `86400` | 匿名 Session 有效期 |
| `CURSOR_SIGNING_KEY` | `development-only-cursor-signing-key` | 不透明分页 cursor HMAC 密钥 |
| `DATABASE_URL` | Docker Compose PostgreSQL URL | ResearchRun、Artifact、Evidence 与 ResearchInput 的权威存储 |
| `RESEARCH_INPUT_UPLOAD_DIR` | `.data/research-inputs` | ResearchInput 内容寻址存储目录 |
| `URL_FETCH_ALLOWED_HOSTS` | 空 | URL ResearchInput host allowlist；空值 fail closed |

## 3. Docker Compose 启动

```powershell
docker compose up --build --wait
```

### Windows 一键启动

在 Windows 11 + Docker Desktop 环境中，可从仓库根目录运行：

```powershell
.\start-dev.bat
```

脚本会校验 Docker/Compose、在缺失时从 `.env.example` 创建本地 `.env`，启动 Compose
服务并等待 API、Workspace 与 Brand Site 可访问，最后自动打开 Workspace。启动失败时保留
容器现场并打印诊断命令，不会自动删除数据卷。需要关闭本地服务时执行
`docker compose -p xingwen-astro-ai-dev down`；该命令不会删除数据卷。

| 服务 | 职责 | 默认地址 |
| --- | --- | --- |
| `site` | Astro Brand Site | `http://localhost:4321` |
| `workspace` | React Research Workspace | `http://localhost:5173` |
| `api` | FastAPI `/api` | `http://localhost:8000` |
| `migrate` | Alembic `upgrade head` one-shot | 无端口 |
| `postgres` | PostgreSQL 17 | `localhost:5432` |

服务依赖顺序为 `postgres healthy -> migrate exited 0 -> api healthy -> workspace`。应用进程不隐式执行 migration。

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

数据库 Migration：

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/xingwen_astro_ai"
uv run alembic upgrade head
```

活动 migration 是描述当前数据库的单一 baseline；开发数据库需要跨 schema 变化时直接重建，不维护开发期升级兼容链。

Schema 导出：

```powershell
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas
```

## 6. 常见问题

| 问题 | 处理方式 |
| --- | --- |
| Docker 启动失败 | 查看 `docker compose ps` 与 `docker compose logs <service>` |
| 浏览器请求 API 失败 | 将 `VITE_API_BASE_URL` 设为可访问 origin；Workspace 与 API 统一 hostname |
| CORS 报错 | 核对 Workspace 实际 origin 与后端 `CORS_ORIGINS` 配置 |
| 前端依赖异常 | 删除 `node_modules` 后执行 `pnpm install --frozen-lockfile` |
| 后端依赖异常 | 执行 `uv sync --frozen` 重建虚拟环境 |
| E2E 缺少浏览器 | 执行 `pnpm exec playwright install chromium` |
