# Local Setup

| 元数据 | 值 |
| --- | --- |
| Status | Implemented |
| Authority | 当前本地启动、调试、验证命令和故障排查 |
| Applies to | `apps/web` Vue baseline、FastAPI `/api/v1`、PostgreSQL Compose |

本文只描述当前可运行基线。目标 Astro/React Monorepo 的命令在 A-01 实施并验证后再加入；当前文档不得预告尚不可运行的目标命令。

## 1. 环境要求

| 工具 | 当前基线 |
| --- | --- |
| Windows | Windows 11、PowerShell 7+、UTF-8 |
| Docker | Docker Desktop + Docker Compose |
| Node.js | 24 LTS，仅用于本机前端调试 |
| pnpm | 10.x，通过 Corepack / `packageManager` 固定 |
| Python | 3.13，仅用于本机后端调试 |
| uv | 由 `uv.lock` 和项目配置约束 |
| PostgreSQL | Compose 使用 `postgres:17-alpine` |

Docker Compose 是默认入口；裸机命令只用于调试。

## 2. 环境变量

```powershell
Copy-Item .env.example .env
```

当前 Fixture-backed v1 基线可使用模板占位配置启动。只有执行真实模型或论文来源调用时，才需要填写对应凭据。

规则：

- 不提交 `.env`；
- `VITE_*` 会进入浏览器，只允许非敏感配置；
- 本地允许模板数据库密码，Production 必须覆盖；
- `VITE_API_BASE_URL` 是浏览器可访问地址，不能使用 Docker 内部服务名 `api`；
- 真实模型、论文和数据源配置只提供给后端。

本地默认 API base：

```text
http://localhost:8000/api/v1
```

## 3. Docker Compose

启动：

```powershell
docker compose up --build
```

| 服务 | 当前职责 | 地址 |
| --- | --- | --- |
| `web` | Vue 3 + Vite 回退前端 | `http://127.0.0.1:5173` |
| `api` | FastAPI `/api/v1` | `http://127.0.0.1:8000` |
| `postgres` | PostgreSQL 17 | `127.0.0.1:5432` |

API 文档：`http://127.0.0.1:8000/api/v1/docs`

停止：

```powershell
docker compose down
```

重建：

```powershell
docker compose up --build --force-recreate
```

只验证配置：

```powershell
Copy-Item .env.example .env
docker compose config
```

## 4. 当前前端调试

```powershell
cd apps/web
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

- 只使用 pnpm；
- 当前 Vue 应用是迁移回退基线，不新增目标业务；
- Fixture 必须通过当前共享 Schema，并明确不是 Live/Cached；
- 前端不直连模型、论文源或数据源。

目标前端结构和迁移边界见 [Frontend Architecture](architecture/FRONTEND_ARCHITECTURE.md)。

## 5. 后端调试

```powershell
cd apps/api
uv sync --frozen
uv run pytest
uv run uvicorn app.main:app --reload
```

导出当前 Schema：

```powershell
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated
```

不手改 generated Schema，不以裸 `pip install -r requirements.txt` 替代 uv。

## 6. 基础验证

```powershell
python scripts/check_foundation.py
docker compose config
```

当前 CI 覆盖：

```text
foundation and forbidden files
pnpm frozen install + build
uv frozen sync + pytest
Pydantic JSON Schema export
docker compose config
```

测试层级和后续阶段门见 [Test Strategy](engineering/TEST_STRATEGY.md)。

## 7. 本地 Smoke

1. Foundation check 通过。
2. Compose config 通过。
3. `docker compose up --build` 成功。
4. 首页可访问。
5. `/api/v1/health` 返回成功。
6. `/api/v1/docs` 可访问。
7. 创建 Task 返回 `task_id`。
8. Fixture 页面明确标记，不冒充 Live 或 Cached。
9. `.env` 未被 Git 跟踪，仓库无额外 lockfile。

当前 Smoke 不证明目标 `/api/v2`、真实 Pipeline 或新前端已实现。

## 8. 常见问题

| 问题 | 处理 |
| --- | --- |
| Compose 启动失败 | `docker compose down` 后重新 build，查看具体 service 日志 |
| 浏览器请求 `api` 域名失败 | 使用 localhost、宿主机地址或公网 API URL |
| 模型调用失败 | 检查后端环境与来源配置，不把凭据写入前端 |
| 论文来源失败 | 检查 endpoint、访问范围和后端配置；不要用 seed 冒充结果 |
| CORS 失败 | 检查实际浏览器 origin 与 `CORS_ORIGINS` |
| 数据库连接失败 | 检查 `DATABASE_URL`、容器健康和 migration 状态 |
| 前端依赖异常 | 清理本地安装目录后重新 frozen install |
| 后端依赖异常 | 使用 `uv sync --frozen` 重建环境 |
| Schema 漂移 | 修正 Pydantic 编写源后重新导出，不改 generated |
| Demo 需要稳定复现 | 使用明确 Fixture；真实缓存必须来自可定位历史 Run |