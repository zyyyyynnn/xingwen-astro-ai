# Contributing

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | Git、Issue、PR、Review 与合并流程 |

Agent 的执行纪律见 [AGENTS](AGENTS.md)；文档层级和同步规则见 [Documentation Governance](docs/DOCUMENTATION_GOVERNANCE.md)。

## 1. 标准流程

1. 从 `main` 获取最新基线。
2. 选择现有 Issue；仅在没有合适任务时创建新 Issue。
3. 从 `main` 创建任务分支。
4. 实施、测试并同步受影响的权威文档。
5. 提交 Pull Request，关联 Issue。
6. 处理 Review 和 CI 结果。
7. 使用 Squash merge，删除已合并分支。

`main` 必须保持可运行；禁止直接推送。

## 2. 分支与 Commit

分支命名：

```text
feat/a-research-canvas
feat/b-v2-artifacts
feat/c-source-crossmatch
feat/d-reasoning-admission
fix/api-version-conflict
docs/documentation-governance
```

Commit 使用明确前缀：

```text
feat: add artifact version endpoint
fix: preserve evidence on revision conflict
docs: align workflow and issue boundaries
chore: update generated contracts
```

一个 Commit 只表达一个主要目的。不得将无关格式化、依赖升级或重构混入功能提交。

## 3. Issue 规范

Issue 至少包含：

- **背景**：为什么需要该改动；
- **目标**：交付的可观察结果；
- **技术或用户范围**：涉及哪些能力；
- **验收标准**：可执行、可验证的完成条件；
- **依赖**：前置 Issue、Contract 或 Artifact；
- **边界**：明确不做什么；
- **影响范围**：代码、数据、契约、文档和材料；
- **验证**：预期命令、测试或复现证据。

标题格式：

```text
[A] A-04 构建数据产物研究画布
[B] B-05 实现数据 Artifact、分页与导出 API
[C] C-03 接入补充来源并实现跨源实体对齐
[D] D-04 实现 Claim / Relation / ReasoningTrace 准入与评测
[X] X-06 Phase 1：打通 v2 数据、论文与总结 Artifact 主链路
```

### Labels

每个任务 Issue 应有一项 priority、一项 type，并按范围添加一个或多个 area：

| 类别 | 值 |
| --- | --- |
| area | `area:frontend`、`area:backend`、`area:data`、`area:pipeline`、`area:graph`、`area:infra` |
| priority | `priority:p0`、`priority:p1`、`priority:p2` |
| type | `type:task`、`type:docs`、`type:feature`、`bug`、`enhancement` |

### Milestones

| Priority | Milestone |
| --- | --- |
| P0 | M1 开发基线 |
| P1 | M2 核心功能 |
| P2 | M3 反馈与交付 |

GitHub Issue 是任务状态的实时事实来源；[Backlog](docs/product/BACKLOG.md) 只维护范围和依赖地图，不复制实时状态。

## 4. PR 规范

PR 描述至少包含：

- 关联 Issue；
- 改动范围与明确非目标；
- 验证命令、结果和未执行原因；
- API、Data Model、Workflow、Version、UI、部署和安全影响；
- Fixture、Live、Cached、Revision 或材料口径影响；
- migration / rollback 要点（适用时）。

PR 不接受：

- 没有明确 Issue 或用户授权；
- 大量无关改动；
- 无可复现验证；
- 接口、实体或状态改变但未同步权威契约；
- 生成 Contract 与编写源漂移；
- Fixture、seed 或缓存来源表述失真；
- 密钥、token、连接串或受限内容泄露；
- 将 Pending 能力写成已实现。

## 5. Review 责任

作者负责：

- 提供可审查的范围和证据；
- 对已知风险和未验证项保持透明；
- 处理 Review 线程；
- 确保文档与实现同步。

审查者负责：

- 先检查范围、契约和不变量，再检查局部实现；
- 区分阻塞问题、建议优化和非本 PR 范围；
- 不以个人风格偏好扩大范围；
- 对安全、数据损坏、来源失真和不可逆迁移优先请求修改。

具体清单见 [Review Checklist](docs/quality/REVIEW_CHECKLIST.md)。

## 6. 合并标准

PR 同时满足以下条件才可合并：

- 解决明确任务且边界清楚；
- 适用测试和 CI 通过；
- Review 阻塞项已处理；
- 契约、生成物和文档无明显漂移；
- 不暴露敏感信息；
- 不扩大产品承诺；
- 分支可合并，目标 HEAD 未意外变化。

默认使用 Squash merge。历史或发布分支需要其他策略时，必须由仓库负责人明确批准。