# Deployment

| 元数据 | 值 |
| --- | --- |
| Authority | 环境拓扑、配置边界、迁移、健康检查与发布验证 |

本文定义系统在本地与生产环境的部署、运行与发布规范。安全要求见 [Security](SECURITY.md)，退出标准见 [Acceptance](docs/product/ACCEPTANCE.md)，本地开发命令见 [Setup](docs/setup.md)。

## 1. 部署拓扑

```text
Browser -> Static Brand Site (Astro)
Browser -> Workspace SPA (React)
Workspace SPA -> FastAPI Backend (/api/*)
FastAPI Backend -> PostgreSQL 17
FastAPI Backend -> Model Provider / Data Sources / Paper Sources
```

- Brand Site 输出静态 HTML/CSS，工作台输出 SPA 静态资源。
- 后端服务托管 FastAPI 单一 `/api/*` 面，连接 PostgreSQL 权威事实源。
- 外部模型、论文与数据源凭据严格锁定在后端环境，前端仅通过 API 交互。

## 2. 环境矩阵

| 环境 | 主要用途 | 数据与外部调用 |
| --- | --- | --- |
| local | 本地开发与测试 | Fixture、stub、recorded，按需 Live |
| preview | PR 浏览器、路由、安全与部署 smoke | 隔离配置、受控 Live 或测试凭据 |
| production | 生产环境 | 受限主案例、配额与只读来源范围 |

## 3. 配置与 Secrets

- **Browser-visible**：仅包含 API 公开 origin、公开配置与 `VITE_` / `PUBLIC_` 变量，均视为公开信息。
- **Backend-only**：包含数据库连接、模型 API Key、Session/Share 散列密钥与限流配置。
- 生产环境严禁使用 DEBUG 模式、默认数据库密码、占位密钥或通配 CORS。

## 4. 数据库迁移

- 数据库迁移（Alembic）在应用实例启动前独立执行 (`migrate` one-shot 成功退出后启动 API)。
- 运行应用进程不得隐式执行结构破坏性 migration。
- 破坏性迁移必须具备先备份、可回滚或双读过渡方案。

## 5. 健康检查与可观测性

- **Health**：
  - API liveness (`/api/health`) 检查进程响应，不依赖外部模型；
  - API readiness 校验数据库连接与 migration 状态；
  - 数据库使用 `pg_isready` 或健康检查命令。
- **Observability**：
  - 日志必须包含 request id、Run id、step key、error code 与延迟；
  - 严禁记录 Secrets、Cookie、share 原 token、受限全文或模型私有推理。

## 6. 发布与验证

- 发布流程：锁定 Commit/Contract -> 自动化 CI 通过 -> Preview smoke -> 数据库 migration -> 部署前端/后端 -> 生产 smoke。
- 验证要点：
  - 静态首屏、`/workspace` SPA 路由与刷新；
  - `/api/health` 与 Core APIs 契约完整性；
  - Session、CSRF、401/403/404 与 Share 撤销/过期逻辑；
  - PostgreSQL migration 与数据完整性。
