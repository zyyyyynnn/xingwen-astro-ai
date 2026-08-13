# API Contract

| 元数据    | 值                                                 |
| --------- | -------------------------------------------------- |
| Authority | HTTP 资源、传输结构、错误、授权语义与 API 演进规范 |

本文定义无版本前缀的单一 `/api/*` 接口面：当前 Research resource surface 与明确的 system endpoints（例如 `/api/health`）。系统不维护旧 API、并行 API、兼容 API 或 Task API；尚未实现的目标能力不暴露空命令。具体 Endpoints、DTOs 与字段由 Pydantic 编写源、OpenAPI 与生成的 Contract 权威定义。

## 1. 设计原则

- URI 使用复数资源名与 `snake_case` 字段。
- 单资源成功响应使用 `Envelope`，集合成功响应使用 `CollectionEnvelope`；失败响应统一遵循 RFC 9457 `ProblemDetails`。
- 集合接口使用不透明 cursor 分页（默认 20，最大 100）。
- 写操作通过 `Idempotency-Key` 或版本前置条件确保幂等。
- `execution_mode`（demo_replay / live）与 `source_mode`（fixture / live / cached）分离。
- 前端组件不直接依赖 Transport DTO，必须经由 Repository Adapter 校验与映射。
- API 严禁返回模型私有思维过程；ReasoningTrace 仅包含可审查依据与引用。

## 2. API 演进规则

- 维护单一当前 Contract；端点、字段和语义在同一变更中同步编写源、生成 Contract、前端 Adapter 与测试。
- API 只维护当前契约面，不引入并行接口或字段分支。
- 破坏性变更必须在 PR 中明确调用方影响，并以当前 Contract 的端到端验证收口。
- 严禁通过在 URL 中增加版本号段进行断代演进。

## 3. 会话、安全与授权

- **匿名 Session**：服务端自动签发高熵标识与 Cookie（`Secure`、`HttpOnly`、`SameSite`）。
- **Ownership 校验**：所有 Project、Run、ArtifactVersion、WorkspaceSnapshot 与 ShareSnapshot 在服务端强制校验 Session ownership。
- **只读分享**：
  - ShareSnapshot 锁定不可变 ArtifactVersion 与可公开 Evidence 范围。
  - Share token 服务端仅存 hash；公开读取不授予写权限或敏感调试信息。
- **未授权保护**：会话缺失/过期返回 `401`；无权访问或不存在的私有资源统一返回 `404`（不泄露资源存在性）；CSRF 校验失败返回 `403`。

## 4. 通用响应结构

### 4.1 成功 Envelope

单资源：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_01J...",
    "schema_version": "2.0.0",
    "generated_at": "2026-07-16T08:00:00Z"
  },
  "links": {
    "self": "/api/projects/proj_01J..."
  }
}
```

集合使用 `CollectionEnvelope`，并额外包含 `page: { "next_cursor": "...", "has_more": false, "limit": 20 }`。

### 4.2 Problem Details 错误响应

```json
{
  "type": "https://xingwen.example/errors/contract-invalid",
  "title": "Research Contract is invalid",
  "status": 422,
  "detail": "requested_fields must contain at least one supported field",
  "instance": "/api/contracts/drafts/rcd_01J...",
  "code": "CONTRACT_INVALID",
  "request_id": "req_01J..."
}
```

## 5. 核心资源结构与流向

```text
Session -> Project -> ResearchThreadEntry -> ContractDraft / Contract -> Run -> RunStep / RunEvent
                         -> ModelExecutionRecord (pre-run assistant analysis only)
                                                      -> ArtifactVersion -> Evidence -> SourceSnapshot
Project -> WorkspaceSnapshot
Project -> ShareSnapshot -> ArtifactVersion
Project -> ResearchInput -> ContractDraft / Run (仅引用绑定)
```

- **Project**：表示持续研究上下文，并通过 `active_draft_id` 指向当前待审 Draft；不得用 latest Draft 推断当前状态。
- **ResearchThreadEntry**：Project-owned、按 Project 严格递增 `sequence` 的公开研究记录。它承载用户消息、助手公开分析、澄清问题/回答、Contract、Plan 与 Run Record 的投影，不复制 Contract、Run 或 Artifact 事实。
- **ModelExecutionRecord**：Research assistant 的 pre-run 执行 provenance。保存 provider/model/prompt identity、安全规范化 Prompt/input/validated output/parameters snapshot 及 hash、status/token/latency/request identity/error；内部持有执行租约以回收进程中断遗留的活跃记录，但不公开完整数据库 snapshot；不保存 raw provider body、凭据或私有推理。
- **Contract**：固定研究目标、字段与质量约束（确认后不可变）。
- **Run**：表示一次具体执行，管理进度与事件。
- **ArtifactVersion**：不可变的科研产物快照，绑定 Evidence 与 SourceSnapshot。
- **WorkspaceSnapshot**：工作台私有恢复布局状态。
- **ShareSnapshot**：冻结的公开只读投影。
- **ResearchInput**：受控输入边界（URL / PDF / CSV / JSON / 图片 / 文本）的不可变引用与溯源；二进制内容与全文永不进入公开 DTO。

- **PaperCandidate 到 ResearchInput**：选中的 PaperCollection candidate 通过
  `POST /api/artifact-versions/{version_id}/paper-candidates/{candidate_id}/research-input`
  桥接到既有 ResearchInput 摄取边界。请求必须带 `Idempotency-Key` 与
  `X-CSRF-Token`，且只能选择 `selected=true` 的 candidate。`mode=open_access_url`
  要求无凭据 HTTPS `access_url` 以及 `publisher_open_access`、
  `repository_open_access` 或 `author_provided` 的显式 access evidence；URL 下载仍
  复用 ResearchInput 的 allowlist、SSRF、重定向、大小、MIME、哈希、CAS、ownership
  与幂等规则。`mode=existing_research_input` 只引用同一 Session/Project 已拥有的
  ResearchInput，并保留其 content hash；`mode=metadata_only` 必须给出稳定 reason，
  不声明 access evidence、ResearchInput 或全文。Fixture、recorded、cached candidate
  只能走 metadata-only，synthetic candidate 不能创建输入。响应绑定是不可变的，返回
  `accepted` 或 `metadata_only` outcome；幂等重放以 `reused=true` 表示并返回相同绑定，
  不使用第三种持久化 outcome。服务端必须在 URL fetch、CAS 或 ResearchInput 创建前原子
  预留 Project-scoped bridge `Idempotency-Key`；不同请求复用同一 key 必须在副作用前冲突，
  相同并发请求最多只有一个 lease owner 执行摄取，完成 binding 时原子关闭 reservation。
  任何未证明访问、paywall、受限/部分元数据、非法 URL、
  SSRF、redirect、MIME、大小、超时或上游失败均 fail closed，且不执行 parser。

## 6. Research Turn

- `GET /api/projects/{project_id}/research-turns?cursor=...&limit=...` 按 Thread `sequence` 稳定分页，返回 Project-owned entries；cursor 使用 HMAC 签名并绑定 Project、集合与排序锚点。
- `GET /api/projects/{project_id}/research-catalog` 返回由当前 Case/Field Manifest 与 ArtifactKind Authority 生成的 Contract authoring 目录；前端不得复制目录。
- `POST /api/projects/{project_id}/research-turns` 接受 `message` 与可选 `answer_to_question_id`，必须带 `Idempotency-Key`；一次请求只能创建一个用户消息和一个真实助手 outcome。
- 同一 Project 同时只允许一个 active Research assistant execution；并发显式发送返回 `409 RESEARCH_ASSISTANT_BUSY`，不创建第二个 Thread entry。相同文本的两次显式发送使用不同 action identity，形成两个独立 Turn。
- response 返回新增 entries、`clarification_required | draft_ready | partial | unsupported | refused` outcome 与 active draft reference；不得返回 raw provider response、private reasoning 或假运行事件。
- 缺少 provider credentials、超时、限流、5xx 或无法解析/验证模型输出时，持久化失败 provenance 并返回稳定的 `MODEL_RUNTIME_UNAVAILABLE` 或对应公开错误；禁止模板或 fixture 冒充成功。
- `PATCH /api/projects/{project_id}` 使用 `If-Match` 更新名称；`DELETE` 使用 `If-Match` 永久删除 Project 及其 owned Thread/Execution/Draft/Run 数据，成功返回 `204`。
- `GET /api/runs/{run_id}/steps` 只读取 RunStep 权威状态；前端不得根据事件数量或百分比合成进度。
- Project list/read 携带由服务端批量计算的最小 `thread_summary`（是否有消息、最新 actor、是否存在未回答澄清）；它只用于非当前 Project 导航状态，不能持久化或复制 workflow/presentation state。当前 Project 仍以完整 Research Thread 为事实源，并由唯一 presentation mapper 得出同一状态。
- `POST /api/projects/{project_id}/runs` 从 confirmed Contract 的 requested outputs 确定性冻结最小依赖闭包；未映射产物返回 `409 RUN_PLAN_UNSUPPORTED_OUTPUT`，不得生成虚假 Step。

## 6. Research Input 摄取契约

- **内容寻址**：摄取内容以 `sha256:<hex>` 内容哈希冻结，服务端按哈希校验写入且不覆盖既有 blob。
- **MIME 不可信**：客户端声明不具效力；所有字节先经 magic bytes 嗅探，声明类型、客户端 MIME 与嗅探结果三方一致才接受，否则 `415`。
- **文件名净化**：路径穿越与分隔符在服务端剥离，仅保留显示用 basename；扩展名与内容类型不一致返回 `415`。
- **URL 抓取失败关闭**：协议与主机 allowlist、SSRF 拒绝内网地址、每次重定向重新校验、流式大小上限、超时、不转发凭据。
- **错误码**：`RESEARCH_INPUT_INVALID`（400，载荷组合非法）、`RESEARCH_INPUT_TOO_LARGE`（413）、`RESEARCH_INPUT_MIME_REJECTED`（415）、`RESEARCH_INPUT_FILENAME_INVALID`（400）、`RESEARCH_INPUT_NOT_FOUND`（404）、`URL_FETCH_BLOCKED`（422，策略拒绝）、`URL_FETCH_TOO_LARGE` / `URL_FETCH_FAILED`（502，上游失败）。
- **绑定语义**：`POST /api/research-inputs/{input_id}/bind` 只绑定引用，不产生所有权转移；输入删除后既有绑定不受影响。
- **状态语义**：稳定生命周期为 `accepted | unsupported_processing | failed_ingestion`。摄取端点只在成功时创建 `accepted` 资源；失败使用 Problem Details 且不创建失败输入。其他状态只能由实际观察到对应结果的 writer 持久化。`accepted` 只证明内容已安全摄取并冻结，不表示内容已被理解。

## 7. 文献 Claim、Relation 与 Trace 读取

在不可变 ArtifactVersion 边界提供以下无版本端点：

- `GET /api/artifact-versions/{version_id}/literature-claims`
- `GET /api/artifact-versions/{version_id}/literature-claims/{claim_id}`
- `GET /api/artifact-versions/{version_id}/literature-relations`
- `GET /api/artifact-versions/{version_id}/literature-relations/{relation_id}`
- `GET /api/artifact-versions/{version_id}/reasoning-traces`
- `GET /api/artifact-versions/{version_id}/reasoning-traces/{trace_id}`

集合端点支持 `status`、不透明 HMAC cursor 与 `limit`（默认 20、最大 100）。cursor 绑定 ArtifactVersion、集合、过滤条件与 `stable_id.asc` 排序；跨 scope、悬空 ID 或签名篡改返回 `400 INVALID_CURSOR`。响应使用 `Cache-Control: no-store`。

Claim 读取必须先通过已验证的 PaperSummary 权威边界，再闭合 PaperSummary、ProducerExecution、Evidence 与 SourceSnapshot。Relation 读取必须把每个 Claim 精确绑定到声明的 Claim ArtifactVersion 和 PaperSummary ArtifactVersion。仅当 Relation 为 `accepted`，双方 Claim 为 `accepted`，且 Trace、Evidence、SourceSnapshot 全部闭合时，`graph_eligible` 才为 `true`。

Pipeline ID 与 PostgreSQL UUID 属于不同命名空间。文学 Artifact 发布必须在同一 fenced transaction 内创建 ArtifactVersion 与其 Evidence，并验证所引用 SourceSnapshot 的 Project、source identity、version 与 content hash；禁止发布后补写 provenance。ReasoningTrace 只作为 LiteratureRelations 内容的一部分读取，不允许独立发布。API 不返回私有 chain-of-thought、原始模型响应、凭据或受限全文。

## 8. Evidence Graph 读取

在不可变 ArtifactVersion 边界提供以下无版本端点：

- `GET /api/artifact-versions/{version_id}/graph`
- `GET /api/artifact-versions/{version_id}/graph/nodes`
- `GET /api/artifact-versions/{version_id}/graph/nodes/{node_id}`
- `GET /api/artifact-versions/{version_id}/graph/edges`
- `GET /api/artifact-versions/{version_id}/graph/edges/{edge_id}`

Graph 元数据端点只返回固定的 taxonomy、policies、scope、integrity report、progressive input、layout hint 与 node/edge/Evidence-use 计数；nodes 与 edges 经有界分页读取，元数据端点不内联整图。集合端点支持 `node_type`（nodes）、`edge_type` 与 `node_id`（edges）、不透明 HMAC cursor 与 `limit`（默认 20、最大 100）。cursor 绑定 ArtifactVersion、集合、过滤条件与稳定 identity 排序；跨版本、跨 filter、跨 collection、悬空 ID 或签名篡改返回 `400 INVALID_CURSOR`。响应使用 `Cache-Control: no-store`。

读取边界重新闭合整个 provenance graph：Graph ArtifactVersion 的 kind、schema、content/input hash、Project 与 ProducerExecution 必须与 typed Graph content 一致；每个 frozen input ArtifactVersion reference 必须解析回同 Project 的持久化版本，并逐项核对 artifact/version identity、kind、schema、content/input/output hash、source mode 与 producer identity。node version bindings、Evidence-use upstream version 与 literature edge Relation version 只能引用该已验证 registry 及其由可信上游 content 声明的传递版本。

Graph-owned Evidence-use 与持久化 Evidence / SourceSnapshot 必须精确一一对应。Evidence locator 闭合 `upstream_evidence_id`、`upstream_artifact_version_id`、`upstream_target_type`、`upstream_target_id` 与 `upstream_evidence_hash`；任一缺失、重复、跨 Project、跨 Version 或 producer/hash 漂移返回 `403 PROVENANCE_SCOPE_VIOLATION`。

scientific relation 与 layout hint 分层投影。structural edge 不携带 Relation/Trace；literature edge 必须携带 `relation_trace`，且投影出的 LiteratureRelation 必须是同一 Project 下、由 frozen ArtifactVersion reference 固定的 `accepted` Relation，其 relation type、方向两端 Claim、ReasoningTrace、Trace Evidence closure 与 `graph_eligible` 必须和 Graph 声明一致，否则返回 `403 PROVENANCE_SCOPE_VIOLATION`。API 只投影已发布科研事实与既有 layout hint，不生成关系、不计算坐标、不修补无效 Graph。

错误使用统一 Problem Details：会话缺失返回 `401`；非本 Session 的 ArtifactVersion 返回不泄露存在性的 `404 ARTIFACT_VERSION_NOT_FOUND`；未知 node/edge 返回 `404 GRAPH_NODE_NOT_FOUND` / `404 GRAPH_EDGE_NOT_FOUND`；非 graph kind 返回 `409 ARTIFACT_KIND_MISMATCH`；content 不是合法 Graph candidate 或 ProducerExecution 与 Graph publication identity 不一致返回 `422 GRAPH_SCHEMA_INVALID`；超出读取尺寸上限返回 `413 GRAPH_ARTIFACT_SIZE_LIMIT_EXCEEDED`。
