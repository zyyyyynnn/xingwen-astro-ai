# Coding Standard

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 代码组织、命名、类型、安全输入与实现边界 |

本文定义系统的编码规范与技术实现边界。模块职责见 [Module Boundaries](../architecture/MODULES.md)，前端架构见 [Frontend Architecture](../architecture/FRONTEND_ARCHITECTURE.md)。

## 1. 通用原则

- 代码仅实现当前明确授权的业务范围，无无关重构或清理。
- 遵循单向依赖与架构分层，不通过深层导入、全局单例或脚本绕过边界。
- 外部 API 输入、模型响应、缓存文件与导入文件均视为不可信输入。
- 核心领域对象统一使用稳定 ID (UUIDv7/ULID)、明确枚举与带时区 UTC ISO 8601 时间。
- 未实现能力返回明确错误，不伪造成功结果或返回空占位。

## 2. Python / Backend

- 公开函数、协议与领域模型必须具备完整的静态类型注解。
- Pydantic v2 是 Transport Schema 与领域契约的唯一编写源。
- FastAPI Router 仅负责请求解析、授权、应用服务调用与响应映射。
- Application Service 管理用例、权限、幂等与数据库事务边界。
- Workflow 管理 Run 状态机与 Event；Pipeline 纯粹实现算法，不推进 Workflow 状态。
- Repository / Adapter 集中数据访问，严禁在 Router 或 Pipeline 散落 raw SQL。
- 异常捕获保留 `from exc` 原因；公开错误统一映射为 Problem Details。

## 3. TypeScript / Frontend

- TypeScript 必须开启 Strict 模式；严禁使用 `any` 或未经校验的类型断言掩盖契约问题。
- Transport Type 由 Pydantic / OpenAPI 导出自动生成，DTO 经 Mapper 转换为 Domain Model。
- `@xingwen/domain` 不依赖 React、DOM、HTTP 或浏览器 API。
- 前端组件与页面严禁直接调用原生 `fetch` 或解析原始 Transport DTO。
- 依赖只能通过 Package 的公开 `exports` 导入，不得以深层私有路径或 `@ts-expect-error` 绕过。
- 用户输入与外部文本默认按转义文本渲染，防范 XSS 漏洞。

## 4. Pipeline 与数据流

- 输入与输出均通过版本化 Schema 校验。
- 外部请求必须记录来源、参数、时间、超时、错误分类与 `SourceSnapshot`。
- Pipeline 不推进 Run 状态、不选择缓存、不生成页面 DTO。
- 数据、Summary、Relation 和 GraphEdge 必须满足 Evidence 准入。
- Live、Fixture、Recorded 和 Cached 数据明确标识，分开存储。

## 5. 数据与版本

- `ArtifactVersion` 创建并计算哈希后，内容绝对不可修改。
- Evidence、Share 与 Export 固定引用 `version_id`，不引用动态 `latest`。
- 修订创建派生 Run 与新 `ArtifactVersion`，保留 `supersedes` 关系与历史版本。
- 数据库事务同时维护 Version、Evidence、latest 指针与 Event 一致性。
- Migration 必须具备升级、失败退出与回滚预案。

## 6. 命名与代码风格

- Python 模块/函数使用 `snake_case`，类使用 `PascalCase`。
- TypeScript 组件/类型使用 `PascalCase`，函数/变量使用 `camelCase`。
- API JSON 字段统一使用 `snake_case`。
- Prompt 文件路径、元数据与登记规则统一由 [Prompt Registry](../ai/PROMPT_REGISTRY.md) 定义。
- 示例代码、文档注释不写入具体临时任务编号或个人本地路径。
