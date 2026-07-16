# Coding Standard

| 元数据    | 值                                       |
| --------- | ---------------------------------------- |
| Status    | Accepted                                 |
| Authority | 代码组织、命名、类型、安全输入和实现边界 |

模块责任见 [Module Boundaries](../architecture/MODULES.md)，测试要求见 [Test Strategy](TEST_STRATEGY.md)，前端详细依赖规则见 [Frontend Architecture](../architecture/FRONTEND_ARCHITECTURE.md)。

## 1. 通用原则

- 代码只实现当前 Issue 的明确范围。
- 依赖方向遵守模块边界，不通过深层导入、全局单例或临时脚本绕过架构。
- 外部输入、模型输出、缓存和导入文件均视为不可信输入。
- 核心业务对象使用稳定 ID、明确枚举和带时区 UTC 时间。
- 公开 API、Domain、Persistence 和 UI 类型保持分层。
- 未实现能力使用明确 Pending / unsupported，不返回伪造成功结果。
- 关键规则必须可测试、可版本化、可定位 producer 和 input/output hash。

## 2. Python / FastAPI

- 使用 Python 3.13 和 uv；公开函数、协议和领域边界具备类型注解。
- Pydantic v2 是 Transport Schema 编写源；生成模型不得反向成为手工源。
- Router 只负责请求解析、授权入口、Application Service 调用和响应映射。
- Application Service 管理用例、权限、幂等和事务边界。
- Workflow 管理 Run、Step、Attempt 和 Event；Pipeline 实现科研算法。
- Repository / Adapter 集中数据访问，不在 Router 或 Pipeline 散落 SQL。
- 异步函数只用于真实异步 I/O，不为形式全部 `async`。
- 捕获异常时保留 cause；公开错误按 Error Handling 和 API Contract 映射。
- 新状态、错误、资源或版本语义必须同步契约和测试。

## 3. TypeScript / Frontend

- 当前运行时为 Astro 7 Brand Site、React 19.2 + Vite 8 Workspace 和根 pnpm Monorepo。
- 使用 Node.js 24.18.0、pnpm 11.13.1、TypeScript 6.0.3 strict 与单一根 lockfile。
- TypeScript strict；禁止用无依据 `any`、类型断言或非空断言掩盖 Contract 问题。
- Transport Type 由 Contract 生成，DTO 经 validation / mapper 转为 Domain Model。
- Domain 不依赖 React、Astro、HTTP 或浏览器 API。
- UI 和 Visual Engine 不直接调用 Repository / fetch。
- Feature 只通过公共入口跨包引用，不深层导入内部文件。
- Site 只依赖 design tokens、UI 及允许但当前未使用的 Visual Engine；Workspace 通过 workspace-core 与 data-access 消费领域边界。
- Server state、local state 和 URL state 按 Frontend Architecture 分工。
- 组件覆盖 loading、empty、partial、success、failed 和来源/修订状态。
- 用户文本与外部内容默认按文本渲染，不绕过框架转义。
- A-02/A-03 未实现能力不得通过空对象、伪数据或占位成功状态包装为 Current。

## 4. Pipeline

- 输入输出均通过版本化 Schema。
- 每个外部请求记录来源、参数、时间、超时、错误分类和 SourceSnapshot。
- Mapping、crossmatch、quality、Prompt、reasoning 和 graph producer 具备版本标识。
- Pipeline 不推进 Run 状态、不选择缓存、不返回页面 DTO。
- 关键值、Summary、Relation 和 GraphEdge 满足 Evidence 准入。
- Live、Fixture、recorded、Benchmark 和 Cached 数据分开存放、分开标识。
- 无效结构、低置信匹配和 Evidence 不足不得静默丢弃或填充。

## 5. 数据与版本

- ArtifactVersion 创建后内容不可修改。
- Evidence、Share 和 Export 引用明确 Version id，不引用动态 latest。
- 修订创建派生 Run 和新 Version，保留 supersedes、Feedback 和 producer。
- Hash 前使用稳定序列化、UTF-8 和明确日期/数字规则。
- 数据库事务同时维护 Version、Evidence、latest 指针和 Event 一致性。
- Migration 具备升级、失败和回滚边界；禁止应用启动时隐式执行破坏性迁移。

## 6. 文件与命名

- 文档与代码使用 UTF-8；仓库文本使用一致换行策略。
- Python 模块/函数使用 `snake_case`，类使用 `PascalCase`。
- TypeScript 组件/类型使用 `PascalCase`，函数/变量使用 `camelCase`。
- API JSON 字段使用 `snake_case`；前端 Domain 是否转换命名由 mapper 统一决定。
- Prompt 文件使用 `<name>/vN.md`，不得使用 `latest.md`。
- Fixture / Benchmark 文件名包含 case、scenario、schema version 和数据等级。
- Issue 编号出现在 PR、测试说明或必要注释，不大量写入业务代码。

## 7. 注释与文档

- 注释解释“为什么”或不变量，不复述代码表面行为。
- 公共 API、复杂领域规则和安全边界使用简短 docstring / TSDoc。
- TODO 包含原因和可定位 Issue；禁止永久无主 TODO。
- 示例明确标记，不得成为第二套生产 Contract。
- 修改领域事实时同步唯一权威文档，不在代码注释复制完整规范。

## 8. Review 门槛

代码 Review 至少检查：

- 是否越过模块或状态所有权边界；
- 是否新增第二套 Schema、枚举或 Prompt；
- 是否存在未经验证的外部/模型内容；
- 是否遗漏 Evidence、SourceSnapshot、版本或权限；
- 是否原地覆盖历史产物；
- 是否可能记录敏感内容；
- 是否有可复现测试和失败场景；
- 是否同步受影响的 Contract、ADR、风险或部署文档。
