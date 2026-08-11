# Schema Package

| 元数据    | 值                    |
| --------- | --------------------- |
| Authority | Schema 导出与消费边界 |

本目录记录 Pydantic Schema 的导出与消费规则。生成结果是本地或 CI Artifact，默认不提交。HTTP 资源和传输语义见 [API Contract](../../docs/architecture/API_CONTRACT.md)，领域实体见 [Data Model](../../docs/architecture/DATA_MODEL.md)。

## 1. 编写源

编写源统一为：

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

LiteratureClaim 领域 Pipeline 使用独立的已提交漂移基线；它不是 HTTP DTO：

```powershell
Set-Location apps/api
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated/literature_claim --include LiteratureClaimExtractionOutput --include LiteratureClaimCandidate --include LiteratureClaimAdmissionResult --include LiteratureClaimsCandidate --include LiteratureClaimBenchmarkEvaluationCase --include LiteratureClaimBenchmarkReport
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated/literature_claim --include LiteratureClaimExtractionOutput --include LiteratureClaimCandidate --include LiteratureClaimAdmissionResult --include LiteratureClaimsCandidate --include LiteratureClaimBenchmarkEvaluationCase --include LiteratureClaimBenchmarkReport --check
```

LiteratureRelation/ReasoningTrace 领域 Pipeline 同样使用独立的已提交漂移基线；它
不是 HTTP DTO：

```powershell
Set-Location apps/api
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated/literature_relation --include LiteratureRelationExtractionOutput --include LiteratureRelationCandidate --include LiteratureRelationAdmissionResult --include LiteratureRelationsCandidate --include LiteratureReasoningTraceCandidate --include LiteratureRelationBenchmarkEvaluationCase --include LiteratureRelationBenchmarkReport
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated/literature_relation --include LiteratureRelationExtractionOutput --include LiteratureRelationCandidate --include LiteratureRelationAdmissionResult --include LiteratureRelationsCandidate --include LiteratureReasoningTraceCandidate --include LiteratureRelationBenchmarkEvaluationCase --include LiteratureRelationBenchmarkReport --check
```

Evidence Graph 领域使用独立的正式导出组：

```text
packages/schemas/generated/graph/
├─ manifest.json
└─ json/*.schema.json
```

该组的 `manifest.json` 精确列出 `GraphBuildRequest`、Node/Edge、Evidence-use、integrity
report、typed candidate/admission，以及 Benchmark evaluation case/report。模型只来自
`apps/api/src/app/schemas/graph_artifact.py` 的唯一 Pydantic 编写源。process-local
publication seal、admission snapshot、repository/数据库对象与 Publisher 事务对象不进入该组。

`generated/graph` 的生成与 `--check` 必须使用同一组显式 include 集合。缺失、stale 或 orphan
Schema 均阻止合并，生成文件不得手工修改。

```powershell
Set-Location apps/api
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated/graph --include GraphBuildRequest --include GraphArtifactNode --include GraphArtifactEdge --include GraphEvidenceUse --include GraphIntegrityReport --include GraphArtifactCandidate --include GraphAdmissionResult --include GraphBenchmarkEvaluationCase --include GraphBenchmarkReport --manifest-content-hashes
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated/graph --include GraphBuildRequest --include GraphArtifactNode --include GraphArtifactEdge --include GraphEvidenceUse --include GraphIntegrityReport --include GraphArtifactCandidate --include GraphAdmissionResult --include GraphBenchmarkEvaluationCase --include GraphBenchmarkReport --manifest-content-hashes --check
```

`app.contracts.core` 只参与完整 OpenAPI 生成，不直接挂载到运行应用；运行挂载范围以 FastAPI Router 为准。

CI 使用临时目录执行导出和 stale diff。只有作为契约漂移基线的生成文件进入版本控制，其他导出作为本地或 CI Artifact。

## 3. 消费边界

- 后端：引用 Pydantic 编写源和生成 OpenAPI，不复制 DTO。
- 前端 Contract 边界：从 OpenAPI / JSON Schema 生成 Transport Type，经 validation 和 mapper 转为 Domain Model。
- Pipeline：按领域输入输出 Schema 返回结构化内容，不依赖页面 DTO。
- Fixture / recorded response：通过同一 Schema，并明确数据等级。
- 文档：描述资源与不变量，不成为机器 Contract 的第二编写源。

### Benchmark / Pipeline Contract

- `Benchmark*` Pydantic 模型属于 **Benchmark / Pipeline Contract**，会进入全量 JSON Schema 导出。
- `PaperCollection`、完整 `SourceSnapshot` 与 `ProducerExecution` 是 Pipeline content Contract；HTTP 投影直接组合这些模型与 provenance DTO，不复制第二套 PaperCollection，也不承担 Publisher。
- Benchmark Contract 不是 HTTP Transport API；只有被 FastAPI Router 引用的模型才会自动进入运行 OpenAPI。
- `generated/literature_claim` 固定唯一领域编写源的 extraction、admission、publisher candidate 与 Benchmark report；通用 ArtifactVersion 只保存不可变 JSON，文献读取使用该领域的专用 Contract，不能进入 Publisher 的通用入口。
- `generated/literature_relation` 固定唯一领域编写源的 extraction、Relation/ReasoningTrace admission、publisher candidate 与 Benchmark report；通用 ArtifactVersion 只保存不可变 JSON，Relation/ReasoningTrace 读取使用该领域的专用 Contract，不能进入 Publisher 的通用入口。
- `generated/graph` 固定 Evidence Graph 的唯一领域编写源和 Benchmark contract；它不是 HTTP DTO。Graph-owned Evidence-use、完整上游版本闭包与 Publisher handoff 必须由 typed candidate 表达，页面 Domain model 不能进入 Publisher。
- 数据产物生成 Schema 同步导出 build input、三类 typed candidate、MappingRuleSet 与 UnitConversionCatalog；`DataArtifactBuildResult`、领域投影和 publication seal 仅是进程内对象，不是公共 JSON Contract。六个公共模型均可 JSON/Pydantic round-trip，但 round-trip candidate 不恢复 publication seal。这些 Schema 是 Pipeline Contract，不会因此成为 HTTP DTO 或数据库记录。
- `Benchmark*` Schema 不改变 `/api` DTO 或路由；Schema 导出不等于运行 Pipeline 接线。
- Pydantic Contract 的统一编写源为 `apps/api/src/app/schemas`，Pipeline 和文档不得复制同名生产 Schema 形成第二事实源。

## 4. 编写源与生成边界

- 核心资源及 Workspace/Share Contract 的 Pydantic / OpenAPI 由编写源生成。
- LiteratureClaim Pipeline Schema 使用独立 tracked JSON Schema 基线，不进入 HTTP OpenAPI。
- LiteratureRelation/ReasoningTrace Pipeline Schema 使用独立 tracked JSON Schema 基线，不进入 HTTP OpenAPI。
- Evidence Graph Pipeline Schema 使用 `generated/graph` 独立 tracked JSON Schema 基线，不进入 HTTP OpenAPI；Graph 的 HTTP read projection 只有在 Router 实际引用时才进入 core OpenAPI。
- 契约字段集以 `packages/schemas/generated/core/openapi.json` 与 `packages/contracts/src/generated/core/dto.ts` 为权威来源；本文不维护状态叙述，实时状态见 GitHub Issues。
- `packages/contracts` 是前端 Contract 包边界：从生成 Schema 得到 Transport Type，经 validation 与 mapper 转为 Domain Model。
- 独立手写 IDL 未采用。

Contract 实现不得复制 generated 文件作为第二编写源，必须由后端编写源、生成流程和前端 Contract package 共同落地。

## 5. 变更门禁

Schema 变更至少验证：

- Pydantic 模型和 OpenAPI/JSON Schema 可重复生成；
- operationId、枚举、错误、cursor 和版本字段完整；
- generated Type 无 stale diff；
- Graph 导出组的 manifest、Node/Edge、typed candidate/admission 与 Benchmark case/report 集合完整且无 orphan；
- Fixture / HTTP Adapter 的 Domain 一致性；
- `/api` 适用回归；
- API Contract、Data Model、Workflow 或 Version 文档按职责同步。

### HTTP Transport projections

`LiteratureClaimRead`、`LiteratureRelationRead` 与 `LiteratureReasoningTraceRead` 是 Core OpenAPI 的 transport projections；Literature Claim/Relation Pipeline candidate 仍是唯一领域 Schema 编写源。Transport 组合候选与版本固定 provenance，不复制 Claim、Relation 或 Trace 领域类型。
