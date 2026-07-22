# Local Setup

| 元数据         | 值                                                |
| -------------- | ------------------------------------------------- |
| Status         | Implemented                                       |
| Authority      | 当前本地、Docker 启动方式、环境变量与验证命令     |
| Implementation | Current                                           |

本地开发采用 Docker-first。Compose 运行 `site`、`workspace`、`api`、`postgres` 四个服务；前端本机调试统一从仓库根目录执行。

## 1. 环境要求

| 工具       | 固定口径                                        |
| ---------- | ----------------------------------------------- |
| Windows    | Windows 11 + PowerShell 7+ + UTF-8              |
| Docker     | Docker Desktop + Docker Compose                 |
| Node.js    | 24.18.0；`engines.node` 限定 Node 24            |
| pnpm       | 11.13.1，由 Corepack 和根 `packageManager` 固定 |
| Python     | 3.13，仅用于后端本机调试                        |
| uv         | 0.7.8 基线，管理 Python 依赖和虚拟环境          |
| PostgreSQL | Compose 使用 `postgres:17-alpine`               |

TypeScript 当前锁定 6.0.3：TypeScript 7 超出 `typescript-eslint@8.64.0` 与 `@astrojs/check@0.9.9` 的共同 peer 范围。两者均声明支持 TypeScript 7 后再升级。

## 2. 环境变量

```powershell
Copy-Item .env.example .env
```

本地按实际调用填写 `DASHSCOPE_API_KEY`；论文源需要鉴权时再填写 `PAPER_SOURCE_API_KEY`。禁止提交 `.env`。

浏览器公开变量：

| 变量                   | 默认值                            | 用途                        |
| ---------------------- | --------------------------------- | --------------------------- |
| `PUBLIC_WORKSPACE_URL` | `http://localhost:5173/workspace` | Site 主入口链接             |
| `VITE_API_BASE_URL`    | `http://localhost:8000/api/v1`    | Workspace 可访问的 API 基址 |

这些变量会进入浏览器输出，只能包含非敏感配置。浏览器地址不能使用 Docker 内部服务名。

Session 服务端变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `SESSION_COOKIE_SECURE` | `false` | 本地 HTTP 默认关闭；Production 必须显式设为 `true` 并使用 HTTPS |
| `SESSION_TTL_SECONDS` | `86400` | 匿名 Session 有效期 |
| `SESSION_CREATE_RATE_LIMIT` | `30` | 单客户端每分钟创建 Session 的上限 |
| `SHARE_CREATE_RATE_LIMIT` | `20` | 单 Session 每分钟创建 ShareSnapshot 的上限 |

Production 必须保持 `SESSION_COOKIE_SECURE=true`。Session 与 CSRF token 不得写入浏览器持久化存储或日志。

## 3. Docker Compose

```powershell
docker compose config
docker compose up --build --wait
```

| 服务        | 容器职责                 | 默认地址                |
| ----------- | ------------------------ | ----------------------- |
| `site`      | Astro Brand Site         | `http://127.0.0.1:4321` |
| `workspace` | React Research Workspace | `http://127.0.0.1:5173` |
| `api`       | FastAPI `/api/v1`        | `http://127.0.0.1:8000` |
| `postgres`  | PostgreSQL 17            | `127.0.0.1:5432`        |

启动依赖为 PostgreSQL → API → Workspace；Site 可独立启动。四个服务均配置 healthcheck。

```powershell
docker compose ps
docker compose down
```

Compose 前端镜像固定 `node:24.18.0-bookworm-slim` 与 pnpm 11.13.1，并在根 workspace 执行 frozen install。源码变化后重新 `docker compose up --build`。

## 4. 前端本机调试

```powershell
corepack enable
corepack prepare pnpm@11.13.1 --activate
pnpm install --frozen-lockfile
pnpm dev
```

常用根命令：

```powershell
pnpm format:check
pnpm check:docs
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm check:architecture
pnpm check:legacy
pnpm test:e2e
pnpm check
```

`pnpm dev` 同时启动 Site 与 Workspace。A-01 入口不请求业务数据；`@xingwen/data-access`、`@xingwen/workspace-core` 和 `@xingwen/visual-engine` 仅提供公开边界。

禁止使用 npm、yarn 或 bun 生成依赖状态。前端不得直连模型、论文源或天文数据源。

## 5. 后端本机调试

```powershell
Set-Location apps/api
uv sync --frozen
uv run pytest
uv run uvicorn app.main:app --reload
```

PostgreSQL migration 由 Alembic 管理，应用启动不会自动修改 Schema：

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/xingwen_astro_ai"
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

Repository 集成测试只允许连接数据库名包含 `test` 的隔离数据库：

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/xingwen_astro_ai_test"
uv run pytest tests/test_db_postgres_integration.py
```

导出 Schema：

```powershell
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas
```

Pydantic 是生产 Schema 的唯一编写源；禁止手改生成结果或用 requirements 替代主流程。

## 6. CI 与基建检查

PR CI 执行：

```text
python scripts/check_foundation.py
docker compose config
pnpm install --frozen-lockfile
pnpm format:check / check:docs / lint / typecheck / test / build
pnpm check:architecture / check:legacy / test:e2e
uv sync --frozen / pytest / Pydantic JSON Schema export
```

Site 与 Workspace 分别构建；所有共享包参与 typecheck。E2E 覆盖 Site、Workspace、共享深链接和 Not Found。

## 7. 本地验收顺序

1. `python scripts/check_foundation.py` 通过。
2. `pnpm check` 通过。
3. `pnpm test:e2e` 通过。
4. `docker compose config` 通过。
5. `docker compose up --build --wait` 后四服务均为 healthy。
6. Site、Workspace 深链接和 `/api/v1/health` 可访问。
7. `.env` 未被 Git 跟踪，仓库只有根 `pnpm-lock.yaml`。

## 8. 常见问题

| 问题                | 处理                                                        |
| ------------------- | ----------------------------------------------------------- |
| Node 版本不符       | 使用 Node 24.18.0，或直接通过 Compose 验证                  |
| Docker 启动失败     | 查看 `docker compose ps` 与 `docker compose logs <service>` |
| 浏览器请求 API 失败 | 将 `VITE_API_BASE_URL` 设为宿主机或公网可访问 URL           |
| CORS 报错           | 同时核对实际 Workspace origin 与后端 `CORS_ORIGINS`         |
| 前端依赖异常        | 删除本地 `node_modules` 后重新 frozen install               |
| 后端依赖异常        | 使用 `uv sync --frozen` 重建                                |
| E2E 缺少浏览器      | 执行 `pnpm exec playwright install chromium`                |
| Schema 漂移         | 修改 Pydantic authoring source 后重新导出                   |
