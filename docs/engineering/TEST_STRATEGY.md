# Test Strategy

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 测试分层、测试数据等级、环境、门禁与证据格式 |

本文定义系统的测试架构与质量校验规范。阶段退出见 [Acceptance](../product/ACCEPTANCE.md)，单个 PR 检查见 [Review Checklist](../quality/REVIEW_CHECKLIST.md)。

## 1. 测试原则

- 优先保护数据完整性、来源可追溯性、权限边界与版本不可变性。
- 领域规则与契约约束优先于简单的页面快照。
- Research Adapter 独立校验，不依赖页面伪造数据。
- Fixture 与 HTTP 共享同一组件路径与 Domain ViewModel。
- 测试失败不得通过降低 Evidence 覆盖、Schema 准入或删除断言解决。

## 2. 测试分层

### Upstream Contract

覆盖选定上游 Agent 骨架的 Navigation、Agent Activity、Workspace、Composer、Command、Loading / Empty / Error、Cancel / Retry 与 Responsive 行为。

### Unit

**领域与 Pipeline 规则：**
- Case / Field Manifest 与单位转换；
- 实体匹配、去重、排序与质量评估；
- Run 状态机、重试策略与 CacheSelector；
- Schema、Mapper、Hash 计算、版本号与 Supersedes 关系；
- Evidence、Relation 与 Graph 完整性准入。

**前端 Adapter 与 Renderer 映射：**
- Domain -> UI ViewModel、Run Event -> Research Event 转换；
- Composer Input -> Research Intent 映射；
- Artifact Kind -> Renderer 路由映射与失败退役。

### Component

- Navigation 选择、Pin、Collapse；
- Agent Activity 流式事件、Tool、Deliverable、Error 与 Checkpoint；
- Artifact Workspace 视图、Focus、Compare；
- Context Inspector 恢复；
- Keyboard、Screen Reader、Reduced Motion 与 200% 字体缩放。

### Integration

- FastAPI Router -> Application Service -> Repository 链路；
- Workflow -> Pipeline Adapter -> ArtifactVersion 发布；
- PostgreSQL 事务、锁租约与 Event 登记；
- Session、CSRF、Ownership 与 Share 校验；
- Repository Port -> Domain -> Research Adapter 一致性。

### Contract

- Pydantic 生成 OpenAPI 3.1 / JSON Schema 准确性与无 Stale Diff；
- generated DTO -> Domain Mapper 完整性；
- API 协议无退化回归。

### End-to-end (E2E)

覆盖从进入 Workspace -> 创建/选择 Project -> 确认 Contract -> 启动 Run -> 审查 Agent Activity 与 Artifact -> 定位 Evidence -> 提议修订 -> 查看新 ArtifactVersion -> Compare -> Export / Share 的完整用户路径。

### Visual & Accessibility

- 固定视口 (1440×900, 1280×800, 390×844) 视觉校验；
- 覆盖 Empty, Running, Needs Review, Completed, Error 等核心界面状态；
- 无障能力（键盘、焦点、屏读）符合标准。

## 3. 测试数据等级

| 等级 | 用途 | 真实性标识 |
| --- | --- | --- |
| Fixture | Unit、组件与视觉回归 | 必须包含 scenario 与 schema version 标识 |
| Recorded response | 稳定集成测试 | 标记为录制的外部上游响应 |
| Benchmark / seed | 算法评估与科研审查校验 | 版本化 Seed 数据，不可充当 Live |
| Live result | Live smoke 与真实运行 | 保存真实 Run、SourceSnapshot、时间与参数 |
| Real run cache | Live 失败兜底 | 必须标记为 Cached 并关联 origin Run |

## 4. 环境矩阵

| 环境 | 主要用途 | 外部服务 |
| --- | --- | --- |
| local | 快速开发与单元/组件测试 | 默认 Stub / Fixture |
| CI | 契约、PostgreSQL 集成与 E2E 自动化 | Stub / Recorded + fresh Compose |
| preview | 部署 Smoke 与授权验证 | 隔离配置与测试凭据 |
| production | 生产环境 | 受限主案例与配额 |

## 5. 测试证据格式

PR 或阶段测试报告必须提供：
- 运行环境与具体测试命令；
- Commit SHA、Contract 版本与 Fixture 版本；
- 通过、失败与跳过用例数量；
- 使用的数据等级（Live / Fixture / Cached）；
- 未执行项的原因说明与已知风险。
