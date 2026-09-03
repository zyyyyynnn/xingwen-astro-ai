# Contributing Guide

| 元数据 | 值 |
| --- | --- |
| Authority | 分支、Commit、PR 流程与合并 |

## 1. Branch 与 Commit

- `main` 只接受经 PR 审验后的集成结果。
- 从当前 `origin/main` 创建 feature/fix/docs 分支开发。
- Commit 与 PR title 使用 `<type>(<scope>)<!>: <summary>`。
- Type 允许：`feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `build`, `chore`, `perf`, `style`, `revert`。
- Scope 使用稳定系统域，例如 `repo`, `frontend`, `backend`, `api`, `contracts`, `data`, `security`, `docs`, `ci`, `deps`, `release`, `sync`。
- Summary 使用英文动作描述，不写 Issue/PR 编号、本地绝对路径、Commit SHA 或 WIP/Ready 等过程状态。
- 精确 staging；提交前审查 `git diff` 与 `git status`。

## 2. PR 流程

```text
task branch
→ implementation
→ PR
→ CI
→ code review
→ squash merge
```

- PR 正文描述 Scope / Non-Goals、验证结果与已知限制，并保持与当前 HEAD 一致。
- 一个 PR 承载一个连贯交付；多个任务属于同一垂直闭环且需要共同验证时，在正文中逐任务列出验收与证据。
- PR 的必要 CI 成功、review 通过且无冲突后才具备合并资格。
- 仓库使用 Squash merge；Issue 是否随 PR 关闭由 PR closure 语义决定。
