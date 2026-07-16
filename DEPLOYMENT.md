# Deployment

## 1. 部署目标

MVP 部署目标是提供稳定公网 Demo，而不是生产级大规模服务。

必须满足：

- 前端公网可访问。
- 后端 API 可被前端浏览器访问。
- PostgreSQL 可连接。
- Qwen / 百炼 API Key 只存在于后端或部署平台 Secrets。
- 论文源凭据只存在于后端或部署平台 Secrets。
- 主案例有真实运行缓存兜底，覆盖数据、论文获取、文献总结、跨文献推理和图谱。
- 关键结果可定位到 Evidence、运行版本与来源快照。

## 2. 技术与镜像基线

| 层级 | 固定口径 |
| --- | --- |
| 前端容器 | `node:24-alpine` |
| 前端包管理 | pnpm 10.x，`pnpm-lock.yaml` 必须提交 |
| 前端构建 | Vue 3 + TypeScript + Vite + shadcn-vue + Tailwind CSS 4 |
| 后端容器 | `python:3.13-slim` |
| 后端依赖 | uv + `pyproject.toml` + `uv.lock` |
| 数据库容器 | `postgres:17-alpine` |
| 本地编排 | Docker Compose：`web`、`api`、`postgres` |

M1 暂不引入 Redis、Celery、MinIO、Nginx、RabbitMQ。任务链路先由 FastAPI、PostgreSQL 状态机和 BackgroundTasks 支撑。

## 3. 推荐部署方案

| 模块 | 推荐 | 说明 |
| --- | --- | --- |
| 前端 | Vercel / Netlify / 阿里云静态托管 | Vue 静态资源独立部署，浏览器 API URL 指向公网后端 |
| 后端 | Render / Railway / 阿里云 ECS / 容器服务 | FastAPI 独立部署，隔离密钥和论文源访问 |
| 数据库 | Supabase Postgres / Neon / 阿里云 RDS | 公网 Demo 优先托管 Postgres；本地使用 Compose |
| 文件导出 | 后端临时文件或对象存储 | MVP 先保证 CSV/JSON/报告可下载 |

本地 Compose 中 `api` 是容器服务名，只供容器间通信。`VITE_API_BASE_URL` 在浏览器运行，必须使用 `localhost`、宿主机地址或公网后端域名。

## 4. 环境划分

| 环境 | 用途 | GitHub Environment |
| --- | --- | --- |
| local | 本地 Docker Compose 开发 | 不使用 GitHub Secrets |
| preview | PR 或测试部署 | `preview` |
| production | 正式公网 Demo | `production` |

## 5. 环境变量

见 [.env.example](.env.example)。

敏感项：

```text
DATABASE_URL
POSTGRES_PASSWORD
DASHSCOPE_API_KEY
PAPER_SOURCE_API_KEY
```

非敏感项：

```text
APP_ENV
DEBUG
DEMO_CASE_KEY
CORS_ORIGINS
WEB_PORT
API_PORT
POSTGRES_PORT
VITE_API_BASE_URL
POSTGRES_DB
POSTGRES_USER
QWEN_BASE_URL
QWEN_MODEL
QWEN_TIMEOUT_SECONDS
PAPER_SOURCE_BASE_URL
PAPER_SEARCH_TIMEOUT_SECONDS
PAPER_SEARCH_MAX_RESULTS
ENABLE_DEMO_CACHE
CACHE_TTL_SECONDS
```

生产要求：

- `APP_ENV=production`
- `DEBUG=false`
- `POSTGRES_PASSWORD` 不得为空或使用 `postgres`
- `DASHSCOPE_API_KEY` 不得为空或使用模板占位值
- `CORS_ORIGINS` 只包含实际前端域名
- `VITE_API_BASE_URL` 指向浏览器可访问的 HTTPS API

## 6. 健康与启动顺序

本地 Compose：

1. PostgreSQL 通过 `pg_isready`。
2. API 启动并通过 `/api/v1/health`。
3. Web 在 API 健康后启动。

公网部署至少配置：

- API readiness/liveness；
- 数据库连接失败告警；
- 外部模型和论文源超时；
- 请求 ID；
- 关键 Workflow Step 失败计数。

## 7. 部署验收

| 检查项 | 标准 |
| --- | --- |
| 首页 | 可打开，无控制台严重报错 |
| API | `/api/v1/health` 可访问 |
| CORS | 正式前端域名可请求，其他来源被拒绝 |
| 任务 | 固定主案例可创建并查询状态 |
| 数据 | 可展示数据表、来源、质量与版本信息 |
| 论文获取 | 可展示检索参数、候选论文、去重和排序 |
| 文献总结 | 可展示 PaperSummary 与 Evidence |
| 跨文献推理 | 可展示 Claim、Relation、ReasoningTrace |
| 图谱 | 可展示证据图谱和推理链详情 |
| 导出 | CSV、数据字典、溯源报告、论文与推理 JSON 可下载 |
| 缓存 | 外部失败时展示真实缓存，并标注来源与版本 |
| 安全 | 源码、日志、截图、构建产物不暴露密钥 |
| 配置 | 生产安全校验通过，默认密码无法启动 |

## 8. CI 预检

合并前必须通过：

```text
python scripts/check_foundation.py
pnpm install --frozen-lockfile
pnpm build
uv sync --frozen
uv run pytest
Pydantic Schema export
docker compose config
```

公网部署前补充环境特定 smoke test。

## 9. 部署前禁止事项

- 不把 `.env` 提交到仓库。
- 不把 API Key、数据库密码、论文源凭据写入前端构建变量。
- 不混用 npm/yarn/bun 生成额外 lockfile。
- 不用 requirements.txt 替代 uv 主流程。
- 不开放无限制任意模型调用入口。
- 不开放无限制论文检索入口。
- 不把手写假数据或 seed list 作为缓存结果。
- 不在生产启用 DEBUG、默认数据库密码或通配 CORS。
