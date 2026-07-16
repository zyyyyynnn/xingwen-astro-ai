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
| uv | 0.7.8 基线，Python 依赖和虚拟环境管理 |
| PostgreSQL | Docker 使用 `postgres:17-alpine` |

## 2. 环境变量

```powershell
Copy-Item .env.example .env
```

本地必须填写：

```text
DASHSCOPE_API_KEY=
```

按论文源是否需要鉴权决定：

```text
PAPER_SOURCE_API_KEY=
```

本地模板允许 `POSTGRES_PASSWORD=postgres`，但生产环境会拒绝默认密码。禁止提交 `.env`。

`VITE_API_BASE_URL` 是浏览器地址。本地默认：

```text
http://localhost:8000/api/v1
```

不能写成 `http://api:8000/...`，因为浏览器无法解析 Docker 内部服务名。

## 3. Docker Compose 启动

```powershell
docker compose up --build
```

默认服务：

| 服务 | 容器职责 | 地址 |
| --- | --- | --- |
| `api` | FastAPI 后端 | `http://127.0.0.1:8000` |
| `postgres` | PostgreSQL 17 | `127.0.0.1:5432` |
| `web` | Vue 3 + Vite 前端 | `http://127.0.0.1:5173` |

启动顺序由 healthcheck 控制：PostgreSQL → API → Web。

API 文档：`http://127.0.0.1:8000/api/v1/docs`

停止：

```powershell
docker compose down
```

重建：

```powershell
docker compose up --build --force-recreate
```

仅校验 Compose：

```powershell
Copy-Item .env.example .env
docker compose config
```

## 4. 前端本机调试

包管理器只允许 pnpm。

```powershell
cd apps/web
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

禁止 `npm install`、`yarn install`、`bun install`。

前端必须遵守：

- Vue 3 + TypeScript + Vite。
- shadcn-vue + reka-ui + Tailwind CSS 4。
- Pinia + Vue Router。
- Vue Flow 用于证据图谱。
- fixtures 只在开发模式使用，并通过共享契约校验。
- 前端不直连模型、论文源或天文数据源。

## 5. 后端本机调试

```powershell
cd apps/api
uv sync --frozen
uv run pytest
uv run uvicorn app.main:app --reload
```

导出 Schema：

```powershell
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated
```

禁止使用裸 `pip install -r requirements.txt` 作为主流程。

## 6. CI 与基建检查

本地可先执行：

```powershell
python scripts/check_foundation.py
```

PR CI 当前覆盖：

```text
required files / forbidden lockfiles / .env / env keys
pnpm install --frozen-lockfile
pnpm build
uv sync --frozen
uv run pytest
Pydantic JSON Schema export
docker compose config
```

CI 失败时先按 job 区分：Foundation、Backend、Frontend。

## 7. 本地验收顺序

1. `python scripts/check_foundation.py` 通过。
2. `docker compose config` 通过。
3. `docker compose up --build` 成功。
4. 前端首页可打开。
5. 后端 `/api/v1/health` 正常。
6. API 文档可打开。
7. 创建任务接口返回 `task_id`。
8. 页面可展示数据、论文获取、文献、推理、图谱 Mock 或真实结果。
9. 页面能区分实时、失败和缓存状态。
10. `.env` 未被 Git 跟踪，无额外 lockfile。

## 8. 常见问题

| 问题 | 处理 |
| --- | --- |
| Docker 启动失败 | `docker compose down` 后重新 build |
| Web 请求 `api` 域名失败 | 将 `VITE_API_BASE_URL` 改为 localhost/宿主机/公网 URL |
| API Key 报错 | 检查后端 `.env`，不要写入前端 |
| 论文源报错 | 检查 source URL/key，必要时使用真实运行缓存 |
| CORS 报错 | 同时检查 `localhost`、`127.0.0.1` 或实际前端域名 |
| 数据库连不上 | 检查 `DATABASE_URL`、容器健康和端口 |
| 前端依赖异常 | 删除 node_modules，重新 frozen install |
| 后端依赖异常 | 使用 `uv sync --frozen` 重建 |
| Schema 漂移 | 修正 `app.schemas` 后重新导出，不手改 generated |
| Demo 需要稳定展示 | 开启缓存并准备真实运行缓存及来源记录 |
