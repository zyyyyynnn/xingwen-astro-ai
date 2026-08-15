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
- **Workflow capacity**：`WORKFLOW_MAX_NONTERMINAL_GLOBAL` / `PER_PROJECT` 限制 Live 非终态总量，`WORKFLOW_MAX_QUEUED_GLOBAL` / `PER_PROJECT` 进一步限制 queue admission，`WORKFLOW_MAX_ACTIVE_GLOBAL` / `PER_PROJECT` 控制跨进程有效 lease，`WORKFLOW_WORKER_CAPACITY` 是单进程并发上限，`WORKFLOW_QUEUE_TIMEOUT_SECONDS` 与 `WORKFLOW_QUEUE_RETRY_AFTER_SECONDS` 固定排队超时及拒绝重试建议。Project 上限不得超过 global，上述值必须在所有 API/Worker 实例保持一致。
- 生产环境严禁使用 DEBUG 模式、默认数据库密码、占位密钥或通配 CORS。

## 4. 数据库迁移

- 数据库迁移（Alembic）在应用实例启动前独立执行 (`migrate` one-shot 成功退出后启动 API)。
- 运行应用进程不得隐式执行结构破坏性 migration。
- 破坏性迁移必须具备先备份、可回滚或双读过渡方案。

## 5. 健康检查与可观测性

- **Health**：
  - API liveness (`/api/health`) 检查进程响应，不依赖外部模型；
  - `research_assistant.status=configured` 只证明密钥与模型配置存在，不声称上游
    额度、网络或实时服务可用；真实可用性以受控调用结果与 Provider 指标为准；
  - `workflow_worker.status` 投影 PostgreSQL 中的 accepting/draining/stopped；draining 表示不再领取新 Run，但不使 API liveness 失败；
  - API readiness 校验数据库连接与 migration 状态；
  - 数据库使用 `pg_isready` 或健康检查命令。
- **Observability**：
  - 日志必须包含 request id、Run id、step key、error code 与延迟；
  - 严禁记录 Secrets、Cookie、share 原 token、受限全文或模型私有推理。

模型请求收到 `MODEL_QUOTA_EXHAUSTED` 时，应检查百炼账户认证、余额与“免费额度用完
即停”策略。系统只保存稳定错误码、安全摘要、延迟和 provider request identity，不保存
上游响应正文；不得通过自动关闭费用保护或静默切换模型来绕过。

## 6. 发布与验证

- 发布流程：锁定 Commit/Contract -> 自动化 CI 通过 -> Preview smoke -> 数据库 migration -> 部署前端/后端 -> 生产 smoke。
- 验证要点：
  - 静态首屏、`/workspace` SPA 路由与刷新；
  - `/api/health` 与 Core APIs 契约完整性；
  - Session、CSRF、401/403/404 与 Share 撤销/过期逻辑；
  - PostgreSQL migration 与数据完整性。

## 7. 内容存储巡检

巡检只读 PostgreSQL 权威引用与 `RESEARCH_INPUT_UPLOAD_DIR` 指向的同一内容寻址
存储，不扫描任意操作系统路径，不提供删除参数：

```powershell
$repoRoot = (Resolve-Path .).Path
$env:PYTHONPATH = $repoRoot
uv run --project apps/api python -m app.commands.content_storage_audit
```

- 退出码 `0` 表示引用、hash、size 与存储结构闭合；报告仍会列出 orphan 数量与字节
  影响，但不会删除。
- 退出码 `2` 表示 authority extraction、missing、hash/size、storage ref 或未知条目
  存在问题；先修复权威事实或恢复 blob，不得手工清理。
- 报告只包含相对 storage ref、hash、资源 ID 与大小，不输出数据库凭据或绝对主机路径。
- 当前不支持执行 GC。writer 先发布 blob、后提交引用；在两者与 collector 共享原子
  协调/隔离机制和可恢复 quarantine 生命周期前，按 mtime/grace period 直接删除仍有
  publication race，禁止作为运维步骤。
