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
```

- **Project**：表示持续研究上下文。
- **Contract**：固定研究目标、字段与质量约束（确认后不可变）。
- **Run**：表示一次具体执行，管理进度与事件。
- **ArtifactVersion**：不可变的科研产物快照，绑定 Evidence 与 SourceSnapshot。
- **WorkspaceSnapshot**：工作台私有恢复布局状态。
- **ShareSnapshot**：冻结的公开只读投影。
