# Schema Package

| 元数据    | 值                         |
| --------- | -------------------------- |
| Status    | Accepted                   |
| Authority | 当前 Schema 导出与消费边界 |

本目录记录当前 Pydantic Schema 的导出与消费规则。生成结果是本地或 CI Artifact，默认不提交。HTTP 资源和传输语义见 [API Contract](../../docs/architecture/API_CONTRACT.md)，领域实体见 [Data Model](../../docs/architecture/DATA_MODEL.md)。

## 1. 编写源

当前唯一编写源：

```text
apps/api/src/app/schemas
```

Pydantic v2 模型生成 JSON Schema / OpenAPI。生成目录不得手工编辑，也不得在前端或 Pipeline 复制同名生产类型。

## 2. 导出

```powershell
Set-Location apps/api
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas
```

需要验证已提交生成物时：

```powershell
Set-Location apps/api
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas --check
```

`/api` 核心契约的已提交漂移基线使用独立目录：

```powershell
Set-Location apps/api
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated/core --include ResearchProject --include ResearchContractDraft --include ResearchContract --include ResearchRun --include RunEvent --include ResearchArtifact --include ArtifactVersion --include ResearchArtifactDetail --include ArtifactVersionDetail --include PaperSummaryArtifactContent --include PaperCollectionRead --include PaperCollectionCandidateRead --include EvidenceRead --include SourceSnapshotDetail --check
uv run python ../../scripts/export_openapi.py --output ../../packages/schemas/generated/core/openapi.json --check
```

`app.contracts.core` 仅用于生成完整目标 OpenAPI，不直接挂载到运行应用。挂载范围与运行事实源接入以对应实现 Issue 与运行 Router 为准。

CI 可以使用临时目录执行导出和 stale diff；是否提交生成文件由对应实现 Issue 决定。

## 3. 消费边界

- 后端：引用 Pydantic 编写源和生成 OpenAPI，不复制 DTO。
- 前端 Contract 边界：A-03 实现后从 OpenAPI / JSON Schema 生成 Transport Type，经 validation 和 mapper 转为 Domain Model。
- Pipeline：按领域输入输出 Schema 返回结构化内容，不依赖页面 DTO。
- Fixture / recorded response：通过同一 Schema，并明确数据等级。
- 文档：描述资源与不变量，不成为机器 Contract 的第二编写源。

### Benchmark / Pipeline Contract

- `Benchmark*` Pydantic 模型属于 **Benchmark / Pipeline Contract**，会进入全量 JSON Schema 导出。
- `PaperCollection`、完整 `SourceSnapshot` 与 `ProducerExecution` 是 Pipeline content Contract；HTTP 投影直接组合这些模型与 provenance DTO，不复制第二套 PaperCollection，也不承担 Publisher。
- Benchmark Contract 不是 HTTP Transport API；只有被 FastAPI Router 引用的模型才会自动进入当前 OpenAPI。
- `Benchmark*` Schema 不改变现有 Phase 0 `/api` DTO 或路由；Schema 导出不等于运行 Pipeline 已接线。
- Pydantic Contract 的统一编写源仍为 `apps/api/src/app/schemas`，Pipeline 和文档不得复制同名生产 Schema 形成第二事实源。

## 4. 编写源与生成边界

- Phase 0 `/api` Schema 继续用于回归；核心资源及 Workspace/Share Contract 的 Pydantic / OpenAPI 由编写源生成。
- 契约字段集以 `packages/schemas/generated/core/openapi.json` 与 `packages/contracts/src/generated/core/dto.ts` 为权威来源；本文不维护里程碑级状态叙述，实时状态见 GitHub Issues。
- `packages/contracts` 是前端 Contract 包边界：从生成 Schema 得到 Transport Type，经 validation 与 mapper 转为 Domain Model。
- 独立手写 IDL 未采用；改变编写源需要新 ADR。

后续 Contract 实现不得复制当前 generated 文件作为第二编写源，必须由后端编写源、生成流程和前端 Contract package 共同落地。

## 5. 变更门禁

Schema 变更至少验证：

- Pydantic 模型和 OpenAPI/JSON Schema 可重复生成；
- operationId、枚举、错误、cursor 和版本字段完整；
- generated Type 无 stale diff；
- Fixture / HTTP Adapter 的 Domain 一致性；
- `/api` 适用回归；
- API Contract、Data Model、Workflow 或 Version 文档按职责同步。
