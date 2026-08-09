# API Contract

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | HTTP 资源、传输结构、错误、授权语义与 API 演进规范 |

本文定义无版本前缀的单一 `/api/*` 接口面。包含 Core APIs 与 Pipeline APIs（`/api/health`、`/api/tasks*`）。系统仅做加法演进，不升级 URL 版本号。具体 Endpoints、DTOs 与字段由 Pydantic 编写源、OpenAPI 与生成的 Contract 权威定义。

## 1. 设计原则

- URI 使用复数资源名与 `snake_case` 字段。
- 成功响应使用统一 Envelope；错误响应遵循 RFC 9457 Problem Details。
- 集合接口使用不透明 cursor 分页（默认 20，最大 100）。
- 写操作通过 `Idempotency-Key` 或版本前置条件确保幂等。
- `execution_mode`（demo_replay / live）与 `source_mode`（fixture / live / cached）分离。
- 前端组件不直接依赖 Transport DTO，必须经由 Repository Adapter 校验与映射。
- API 严禁返回模型私有思维过程；ReasoningTrace 仅包含可审查依据与引用。

## 2. API 演进规则 (Additive-Only)

- 仅允许新增端点、新增可选字段或新增 Query 参数。
- 严禁删除、重命名既有字段或改变现有字段语义。
- 字段废弃通过 Pydantic / OpenAPI `deprecated=True` 标记。
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

分页集合额外包含 `page: { "next_cursor": "...", "has_more": false, "limit": 20 }`。

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
Session -> Project -> ContractDraft / Contract -> Run -> RunEvent
                                                      -> ArtifactVersion -> Evidence -> SourceSnapshot
Project -> WorkspaceSnapshot
Project -> ShareSnapshot -> ArtifactVersion
Project -> ResearchInput -> ContractDraft / Run (仅引用绑定)
```

- **Project**：表示持续研究上下文。
- **Contract**：固定研究目标、字段与质量约束（确认后不可变）。
- **Run**：表示一次具体执行，管理进度与事件。
- **ArtifactVersion**：不可变的科研产物快照，绑定 Evidence 与 SourceSnapshot。
- **WorkspaceSnapshot**：工作台私有恢复布局状态。
- **ShareSnapshot**：冻结的公开只读投影。
- **ResearchInput**：受控输入边界（URL / PDF / CSV / JSON / 图片 / 文本）的不可变引用与溯源；二进制内容与全文永不进入公开 DTO。

## 6. Research Input 摄取契约

- **内容寻址**：摄取内容以 `sha256:<hex>` 内容哈希冻结，服务端按哈希校验写入且不覆盖既有 blob。
- **MIME 不可信**：客户端声明不具效力；所有字节先经 magic bytes 嗅探，声明类型、客户端 MIME 与嗅探结果三方一致才接受，否则 `415`。
- **文件名净化**：路径穿越与分隔符在服务端剥离，仅保留显示用 basename；扩展名与内容类型不一致返回 `415`。
- **URL 抓取失败关闭**：协议与主机 allowlist、SSRF 拒绝内网地址、每次重定向重新校验、流式大小上限、超时、不转发凭据。
- **错误码**：`RESEARCH_INPUT_INVALID`（400，载荷组合非法）、`RESEARCH_INPUT_TOO_LARGE`（413）、`RESEARCH_INPUT_MIME_REJECTED`（415）、`RESEARCH_INPUT_FILENAME_INVALID`（400）、`RESEARCH_INPUT_NOT_FOUND`（404）、`URL_FETCH_BLOCKED`（422，策略拒绝）、`URL_FETCH_TOO_LARGE` / `URL_FETCH_FAILED`（502，上游失败）。
- **绑定语义**：`POST /api/research-inputs/{input_id}/bind` 只绑定引用，不产生所有权转移；输入删除后既有绑定不受影响。
- **状态语义**：`accepted` 表示摄取成功且内容已冻结；`unsupported_processing` 与 `failed_ingestion` 为预留状态，摄取成功不等于已理解。

## 7. 文献 Claim、Relation 与 Trace 读取

在不可变 ArtifactVersion 边界提供以下无版本端点：

- `GET /api/artifact-versions/{version_id}/literature-claims`
- `GET /api/artifact-versions/{version_id}/literature-claims/{claim_id}`
- `GET /api/artifact-versions/{version_id}/literature-relations`
- `GET /api/artifact-versions/{version_id}/literature-relations/{relation_id}`
- `GET /api/artifact-versions/{version_id}/reasoning-traces`
- `GET /api/artifact-versions/{version_id}/reasoning-traces/{trace_id}`

集合端点支持 `status`、不透明 HMAC cursor 与 `limit`（默认 20、最大 100）。cursor 绑定 ArtifactVersion、集合、过滤条件与 `stable_id.asc.v1` 排序；跨 scope、悬空 ID 或签名篡改返回 `400 INVALID_CURSOR`。响应使用 `Cache-Control: no-store`。

Claim 读取必须先通过已验证的 PaperSummary 权威边界，再闭合 PaperSummary、ProducerExecution、Evidence 与 SourceSnapshot。Relation 读取必须把每个 Claim 精确绑定到声明的 Claim ArtifactVersion 和 PaperSummary ArtifactVersion。仅当 Relation 为 `accepted`，双方 Claim 为 `accepted`，且 Trace、Evidence、SourceSnapshot 全部闭合时，`graph_eligible` 才为 `true`。

Pipeline ID 与 PostgreSQL UUID 属于不同命名空间。文学 Artifact 发布必须在同一 fenced transaction 内创建 ArtifactVersion 与其 Evidence，并验证所引用 SourceSnapshot 的 Project、source identity、version 与 content hash；禁止发布后补写 provenance。ReasoningTrace 只作为 LiteratureRelations 内容的一部分读取，不允许独立发布。API 不返回私有 chain-of-thought、原始模型响应、凭据或受限全文。
