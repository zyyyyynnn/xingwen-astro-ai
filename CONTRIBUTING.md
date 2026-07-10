# Contributing

本文件只说明 Git、Issue、PR 与合并流程。Agent 执行纪律见 [AGENTS.md](AGENTS.md)。

## 1. 开发流程

1. 从 `main` 拉取最新代码。
2. 选择或创建 Issue。
3. 从 `main` 新建分支。
4. 完成开发、自测和必要文档同步。
5. 提交 Pull Request。
6. 通过 Review 后 Squash merge。
7. 删除已合并分支。

`main` 必须保持可运行；禁止直接推送 `main`。

## 2. 分支命名

```text
feat/a-task-timeline
feat/b-task-api
feat/c-field-dictionary
feat/d-evidence-graph
docs/design-baseline
fix/api-task-status
```

规则：

- `feat/`：功能或模块任务。
- `fix/`：缺陷修复。
- `docs/`：文档调整。
- 分支名优先体现岗位或模块，不使用无意义临时名。

## 3. Commit 格式

```text
feat: add task timeline component
fix: handle qwen timeout
docs: update design baseline
chore: initialize backend structure
```

一个 commit 只表达一个主要目的。

## 4. Issue 要求

Issue 至少包含：

- 背景：为什么做。
- 目标：完成后交付什么。
- 验收标准：如何判断完成。
- 依赖：前置任务。
- 边界：不做什么。
- 影响范围：前端、后端、数据、文献、图谱、文档。

标题格式：

```text
[A] 实现任务进度时间线
[B] 初始化任务 API
[C] 确定 MVP 字段清单
[D] 构建证据图谱 JSON
[X] 前后端 Mock 联调
```

### Label 规范

每个 Issue 必须打上以下三类标签：

| 类别 | 可选值 | 说明 |
| --- | --- | --- |
| area | `area:frontend`、`area:backend`、`area:data`、`area:pipeline`、`area:graph`、`area:infra` | 工作领域 |
| priority | `priority:p0`、`priority:p1`、`priority:p2` | 优先级 |
| type | `type:task`、`type:docs`、`type:feature`、`bug`、`enhancement` | 任务类型 |

### Milestone 规范

Milestone 与 Priority 严格 1:1 对应：

| Priority | Milestone | 内容 |
| --- | --- | --- |
| P0 | M1 开发基线 | 骨架、Docker、CI、Mock 闭环 |
| P1 | M2 核心功能 | 数据/论文/文献/推理/图谱主链路 |
| P2 | M3 反馈与交付 | 缓存兜底、反馈修正、公网部署、材料交接 |

创建 Issue 时根据 Priority 自动归入对应 Milestone，不使用 `milestone:*` 标签。

## 5. PR 要求

PR 必须说明：

- 关联 Issue。
- 改动范围。
- 验证方式和结果。
- 是否改接口、数据结构、UI 基线、部署或安全口径。
- 是否影响演示截图、导出物或材料交接口径。

PR 不接受：

- 无明确任务目标。
- 无可复现验证说明。
- 接口变化但不改 `API_CONTRACT.md`。
- 数据结构变化但不改 `DATA_MODEL.md`。
- UI 基线变化但不改 `DESIGN.md`。
- 暴露密钥或宣传未实现能力。

## 6. 文档同步

| 改动 | 同步文档 |
| --- | --- |
| 接口、错误码、响应结构 | `docs/architecture/API_CONTRACT.md` |
| 数据实体、字段、枚举 | `docs/architecture/DATA_MODEL.md` |
| 模块职责、系统流程、UI 基线 | `DESIGN.md`, `docs/architecture/MODULES.md` |
| MVP 范围、验收口径 | `PRD.md`, `docs/product/ACCEPTANCE.md` |
| 部署、环境变量 | `DEPLOYMENT.md`, `.env.example` |
| 安全、密钥、日志 | `SECURITY.md` |
| 风险或技术债 | `docs/quality/RISK_REGISTER.md` |

## 7. 合并标准

PR 同时满足以下条件才可合并：

- 只解决一个明确任务。
- 验证方式可复现。
- 文档未明显过期。
- 不引入密钥泄露风险。
- 不扩大 MVP 承诺。
- Review 通过且分支可合并。