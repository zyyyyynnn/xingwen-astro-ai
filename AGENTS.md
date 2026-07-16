# AGENTS

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | Agent 执行顺序、修改纪律、Git 安全与最低验证 |

本文件只规定 Agent 如何在本仓库执行任务。产品、架构、设计和工程事实应从 [Docs Index](docs/README.md) 定位；Git、Issue 和 PR 流程见 [Contributing](CONTRIBUTING.md)。

## 1. 事实来源优先级

处理冲突时按以下顺序：

1. 用户明确指令、当前 Issue 和 PR 已批准范围；
2. 核心规范：PRD、DESIGN、API、Data Model、Workflow、Version、ADR；
3. 专项规范：前端、视觉、AI、测试、安全和部署；
4. Roadmap、Backlog、Acceptance、Review 等执行治理；
5. README 摘要；
6. references / archive 中的参考或历史资料。

不得用低权威文档覆盖高权威事实。详细规则见 [Documentation Governance](docs/DOCUMENTATION_GOVERNANCE.md)。

## 2. 默认执行协议

1. 读取当前 Issue、相关规范和实际代码。
2. 确认 Current / Target / Pending 边界。
3. 检查工作区或目标分支，保护无关修改。
4. 只实施任务要求的最小完整范围。
5. 同步被本次改动实际影响的唯一事实来源。
6. 运行适用验证并记录命令、结果和未执行原因。
7. 通过分支和 PR 交付，不直接推送 `main`。

需求明确时直接执行。只询问会改变范围、风险、数据安全或验收结果的问题。

## 3. 当前与目标边界

- 当前可运行前端为 `apps/web`；目标为 Astro Brand Site、React Workspace 和共享包。
- 当前 API 为 `/api/v1` Task 基线；目标为 `/api/v2` Project / Run / Artifact / Version。
- 目标架构不得写成已实现能力。
- A-01 开始后，旧前端只做阻塞性修复和迁移读取，不新增业务。
- 新旧前端不得长期双写同一功能。
- 无对应 Issue 时不得安装目标前端运行时、创建 Tauri 应用或修改 Docker 拓扑。

完整迁移边界见 [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md)。

## 4. 不可违反的工程约束

- 前端使用 Node.js 24 LTS、pnpm、单一 `pnpm-lock.yaml` 和 TypeScript strict。
- 后端使用 Python 3.13、uv、`pyproject.toml` 和 `uv.lock`。
- 禁止 npm/yarn/bun lockfile 和以 requirements.txt 替代 uv 主流程。
- Pydantic / OpenAPI 是 Transport Contract 的编写源，不手写第二套同名生产 DTO。
- 前端不直连模型、论文源或天文数据源，不保存密钥。
- 生产 Prompt 只位于 `packages/prompts`，已使用版本不可原地改写。
- 未经 ADR 和实际负载证明，不引入 Redis、Celery、MinIO、RabbitMQ、Neo4j 或向量数据库。

详细模块边界见 [Module Boundaries](docs/architecture/MODULES.md)。

## 5. 科研可信约束

- Fixture、Live、Cached 和 Revision 必须按真实语义表达。
- Cached 只能引用真实历史 Run、ArtifactVersion 和 SourceSnapshot。
- Seed 只用于 benchmark、Fixture 或人工校验。
- 模型输出先通过 JSON、Schema、Evidence 和领域准入校验。
- 无 Evidence / Trace 的关系只能作为候选。
- GraphEdge 必须绑定 Evidence；跨文献边额外绑定 Relation 和 ReasoningTrace。
- 不保存或展示模型私有 chain-of-thought。
- 反馈和修订不得原地覆盖 ArtifactVersion。
- 未实现能力只能写为 Proposed、Pending 或后续扩展。

## 6. Git 与修改安全

- 从 `main` 创建任务分支，不直接写入 `main`。
- 不 reset、force push 或改写远端历史。
- 工作区存在无关修改时，不擅自暂存、删除或提交。
- Commit 一个主要目的，使用 `feat`、`fix`、`docs` 或 `chore` 前缀。
- PR 关联 Issue，说明范围、验证及契约、数据、UI、部署、安全和材料影响。
- CI 或必要审查失败时不得合并。

## 7. 文档同步

只更新真正受影响的唯一事实来源。常见映射：

| 改动 | 权威文档 |
| --- | --- |
| 产品范围、用户、主流程 | `PRD.md` |
| 设计原则、体验域 | `DESIGN.md` |
| 接口、错误、授权 | `docs/architecture/API_CONTRACT.md` |
| 实体、字段、不变量 | `docs/architecture/DATA_MODEL.md` |
| 状态、事件、重试、派生 | `docs/architecture/WORKFLOW_DESIGN.md` |
| 版本、缓存、修订、分享 | `docs/architecture/DATA_VERSIONING.md` |
| 模块输入输出与依赖 | `docs/architecture/MODULES.md` |
| 前端工程、视觉、交互 | 对应 frontend/design 专项文档 |
| 模型、Prompt、推理准入 | `docs/ai/*` 与 `packages/prompts` |
| 测试、安全、部署 | 对应 engineering / SECURITY / DEPLOYMENT 文档 |

新增、移动、合并或删除文档时同步 `docs/README.md`。

## 8. 最低验证

| 改动类型 | 最低验证 |
| --- | --- |
| 所有 PR | `python scripts/check_foundation.py` 与适用静态检查 |
| 当前前端 | frozen install + build |
| 目标前端 | lint、typecheck、test、build 与适用 E2E |
| 后端 | `uv sync --locked`、pytest、Schema/OpenAPI 检查 |
| Docker / 部署 | `docker compose config` 与适用 smoke test |
| Contract | 生成产物 stale check、Fixture/HTTP 一致性、错误和授权测试 |
| 文档 | `git diff --check`、标题/代码块/表格、链接、Mermaid 和索引覆盖 |

无法执行某项验证时，明确记录原因和替代验证，不得写“应该可以”。