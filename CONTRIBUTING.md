# Contributing Guide

| 元数据 | 值 |
| --- | --- |
| Authority | 分支、交付模式、PR 生命周期、Review 与合并治理 |

## 1. Branch 与 Commit

- `main` 只接受经 PR 审验后的集成结果，禁止直接开发或直接推送。
- 开始开发前获取并冻结当前 `origin/main` exact SHA，从该基线创建 feature/fix/docs 分支。
- 冻结后若 `origin/main` 漂移，不自动 merge/rebase/reset/cherry-pick；先停止 mutation 并报告。
- Commit 与 PR title 使用 `<type>(<scope>)[!]: <summary>`。
- Type 允许：`feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `build`, `chore`, `perf`, `style`, `revert`。
- Scope 使用稳定系统域，例如 `repo`, `frontend`, `backend`, `api`, `contracts`, `data`, `security`, `docs`, `ci`, `deps`, `release`, `sync`；禁止过程性 scope。
- Summary 使用英文动作描述，不写 Issue/PR 编号、本地绝对路径、Commit SHA、Review ID、日期或 WIP/Ready/PASS/BLOCKED 等过程状态。
- 分支 Commit subject 不写 Issue/PR 编号。Squash merge 的集成 Commit 可由托管平台附加 PR 回链。
- 精确 staging；不要用全仓 staging 命令替代范围检查。

## 2. Delivery Mode

Issue 是稳定的原子任务契约，PR 是交付载体。

### 2.1 Atomic Delivery — 默认

默认一个 Issue 对应一个主要 PR。一个 Issue 同时最多只有一个有效 Open 主要交付 PR；替代 PR 必须明确 supersede 旧 PR。

### 2.2 Grouped Delivery — 明确授权的例外

只有用户或维护者明确授权，并满足以下条件时，允许一个 PR 同时交付多个 Issue：

- Issue 属于同一垂直产品闭环或同一 release/gate closure；
- 实现共享同一架构边界，拆分会制造重复适配、临时兼容层、反复迁移或无法独立验证的中间态；
- PR 仍能被一个清晰的 Scope / Non-Goals 定义；
- 每个 Issue 都有独立的 acceptance/evidence 记录。

Grouped Delivery 不是“体量大即可打包”的许可。无关任务、独立产品能力、顺手清理和泛重构仍应拆分。

PR 正文必须包含：

```text
Delivery mode: Atomic | Grouped
Authorization: ...
Included Issues: ...
Scope / Non-Goals
Per-Issue Acceptance Matrix
Validation / Evidence
Authority / Contract / Security impact
Known limits / Remaining risk
```

Per-Issue Acceptance Matrix 至少逐项记录：Issue、验收项、实现位置、验证证据、未完成项。Grouped Delivery 不得降低任一 Issue 的原始验收标准。

不要为了 grouped delivery 新建无产品价值的 umbrella Issue、stack 编号、阶段代号或临时 dependency graph。

## 3. PR 生命周期

标准流程：

```text
frozen main
→ task branch
→ implementation
→ Draft PR
→ exact-head CI
→ independent Technical Review
→ user / maintainer merge decision
```

- PR 默认以 Draft 创建，直到用户或维护者明确决定 Ready。
- 实现者与正式 Reviewer 是不同角色；实现完成不等于 Review 完成。
- PR body 必须真实反映当前 HEAD，而不是保留已经失效的旧验证结论。
- 同一 Authority/实现责任不得同时存在互相竞争的两个有效主要 PR。
- 用户直接授权的治理、维护或大型 vertical closure 可作为 PR 的明确授权来源。

## 4. Formal Technical Review

正式 Review 绑定 exact HEAD。Review 前必须冻结：PR HEAD、base、当前 `main`、merge-base，并审查完整 diff。

Reviewer 必须：

1. 核对 Scope / Delivery Mode / Issue acceptance；
2. 审查 correctness、architecture、current-only、security、scientific truth、user reachability、tests/CI；
3. 检查新增或迁入能力是否吸收进现有 Authority，而非形成第二系统；
4. 形成 preliminary findings；
5. 再执行一次 adversarial omission sweep；
6. 提交一个 exact-head PR Review，默认 action 为 `COMMENT`，正文明确 `verdict: PASS`、`verdict: NOT READY` 或 `verdict: BLOCKED` 及理由。

新 Commit 到达后，旧 Review、旧 exact-head CI 结论与旧修复确认自动失效；必须对新 HEAD 重新审查。除非用户要求，不用 APPROVE / REQUEST_CHANGES 代替上述 exact-head Review 纪律。

## 5. Merge 与 Issue Closure

只有以下条件同时满足时才具备可合并资格：

- Scope 与 Delivery Mode 合法；
- 每个包含 Issue 的 acceptance 已满足，或未关闭项被明确排除；
- 当前 HEAD 的必要 CI 成功；
- 当前 HEAD 的正式 Technical Review 为 PASS；
- 无 target-branch drift、冲突、凭据泄露、Authority 漂移或未解决 blocker；
- PR body 与当前实现/证据一致。

仓库默认使用 Squash merge。**不得由实现 Agent 或 Reviewer 自行 merge、mark Ready、开启 auto-merge 或扩大 Issue closure。** Issue 是否随 PR 合并关闭，由 PR 明确 closure 语义与用户/维护者决定；Grouped Delivery 尤其不能默认把所有关联 Issue 一并关闭。
