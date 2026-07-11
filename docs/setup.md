# Local Setup

本地开发采用 Docker-first。成员默认通过 Docker Compose 启动 `web`、`api`、`postgres`，避免 Windows 本机依赖和版本不一致。

## 1. 环境要求

| 工具 | 固定口径 |
| --- | --- |
| Windows | Windows 11 + PowerShell 7+ + UTF-8 |
| Docker | Docker Desktop + Docker Compose |
| Node.js | 24 LTS，仅用于本机前端调试 |
| pnpm | 10.x，通过 Corepack 或项目 `packageManager` 固定 |
| Python | 3.13，仅用于本机后端调试 |
| uv | Python 依赖和虚拟环境管理 |
| PostgreSQL | Docker 使用 `postgres:17-alpine` |

## 2. 环境变量

```powershell
Copy-Item .env.example .env
```

必须本地填写：

```text
DASHSCOPE_API_KEY=
```

按论文源是否需要鉴权决定是否填写：

```text
PAPER_SOURCE_API_KEY=
```

禁止提交 `.env`。

## 3. Docker Compose 启动

本地统一入口为：

```powershell
docker compose up --build
```

默认服务：

| 服务 | 容器职责 | 地址 | 状态 |
| --- | --- | --- | --- |
| `api` | FastAPI 后端 | `http://127.0.0.1:8000` | 已就绪 |
| `postgres` | PostgreSQL 17 | `127.0.0.1:5432` | 已就绪 |
| `web` | Vue 3 + Vite + shadcn-vue 前端 | `http://127.0.0.1:5173` | 已就绪 |

三服务均通过 `docker compose up --build` 启动。前端开发也可用 `pnpm dev` 本机调试。

API 文档：`http://127.0.0.1:8000/api/v1/docs`

停止服务：

```powershell
docker compose down
```

重建服务：

```powershell
docker compose up --build --force-recreate
```

## 4. 前端本机调试

仅在需要快速调试 Web 页面时使用本机命令。包管理器只允许 pnpm。

```powershell
cd apps/web
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

禁止：

```powershell
npm install
yarn install
bun install
```

前端必须遵守：

- Vue 3 + TypeScript + Vite。
- shadcn-vue + reka-ui + Tailwind CSS 4。
- Pinia + Vue Router。
- Vue Flow 用于证据图谱。
- 后端未完成时可使用开发 fixtures，但字段必须对齐 `API_CONTRACT.md`。

## 5. 后端本机调试

仅在需要快速调试 API 时使用本机命令。Python 依赖只允许 uv 管理。

```powershell
cd apps/api
uv sync
uv run uvicorn app.main:app --reload
```

禁止使用裸 `pip install -r requirements.txt` 作为主流程。需要导出 requirements 时只能作为部署兼容产物，不能替代 `pyproject.toml` 和 `uv.lock`。

## 6. CI 与依赖漂移检查

`X-05` 完成后，PR 必须通过最小 CI 卡口。卡口至少覆盖：

```text
package-lock.json / yarn.lock / bun.lock 不存在
pnpm-lock.yaml 存在
uv.lock 存在
.env 未提交
.env.example 关键变量存在
```

`X-04`、`A-01`、`B-01` 完成后，CI 继续补齐：

```powershell
pnpm install --frozen-lockfile
pnpm build
uv sync --locked
uv run pytest
docker compose config
```

如当前阶段尚无前端、后端或 Compose 文件，CI 可以先做静态漂移检查，并在 PR 说明中写明暂未启用的检查项。

## 7. 本地验收顺序

1. `docker compose up --build` 成功。
2. 前端首页可打开。
3. 后端 `/api/v1/health` 正常。
4. API 文档可打开。
5. 创建任务接口返回 `task_id`。
6. 任务流程页可展示数据、论文获取、文献、推理、图谱 Mock 或真实结果。
7. 页面能标注缓存状态。
8. `.env` 未被 Git 跟踪。
9. 未出现 npm/yarn/bun lockfile。
10. X-05 完成后，PR CI 通过。

## 8. 常见问题

| 问题 | 处理 |
| --- | --- |
| Docker 启动失败 | 先执行 `docker compose down`，再 `docker compose up --build` |
| API Key 报错 | 检查 `.env` 中 `DASHSCOPE_API_KEY`，不要写到前端 |
| 论文源报错 | 检查 `PAPER_SOURCE_BASE_URL` 和 `PAPER_SOURCE_API_KEY`，必要时使用真实运行缓存 |
| CORS 报错 | 检查 `CORS_ORIGINS` 是否包含前端地址 |
| 数据库连不上 | 检查 `DATABASE_URL`、postgres 容器和端口映射 |
| 前端依赖异常 | 删除 `node_modules`，使用 `pnpm install --frozen-lockfile` |
| 后端依赖异常 | 使用 `uv sync` 重建环境 |
| Demo 需要稳定展示 | 开启 `ENABLE_DEMO_CACHE=true` 并准备真实运行缓存 |
