# Contributing Guide

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 贡献流程、分支契约、提交规范与合入基线 |

本指南规定本仓库的 GitHub 协作流程、分支规范、提交格式与 PR 审验基线。

## 1. 分支与提交

- **禁止直接推送 `main`**：所有改动必须通过 Draft PR 提交并经 CI / Review 验证。
- **分支命名**：
  ```text
  feat/research-canvas
  fix/contract-drift
  docs/authority-consolidation
  ```
- **Commit 前缀**：
  ```text
  feat: add artifact version endpoint
  fix: preserve evidence on revision conflict
  docs: align workflow and issue boundaries
  chore: update generated contracts
  ```
- **提交原则**：一个 Commit 表达一个独立主要目的，不混入无关格式化或无关改动。

## 2. Issue 与 PR 规则

- **一对一关系**：一个 Task / Bug 仅对应一个主要交付 PR；一个交付 PR 对应一个主要 Task / Bug。
- **单 Open PR 规则**：同一 Issue 同时只能存在一个有效 Open PR。若为替代 PR，须记录 supersede 关系。
- **直接授权**：用户在当前会话明确授权的治理或维护任务，可在 PR 描述中记录授权背景。
- **PR 必填内容**：
  - 授权背景与主要关联 Issue / 任务；
  - 改动范围 (Scope) 与明确非目标 (Non-Goals)；
  - 验证命令与实际结果；
  - 契约、数据模型、工作流、安全或部署影响。

## 3. 正式技术 Review 责任

- **Review 门禁**：合并前必须取得符合 [Review Checklist](docs/quality/REVIEW_CHECKLIST.md) 的正式技术 Review 通告。
- **结论一致性**：Review 结论为 `PASS` 对应 GitHub `APPROVED` 或正文包含 `verdict: PASS`；`BLOCKED` 对应 `CHANGES_REQUESTED` 或正文包含 `verdict: BLOCKED`。
- **Commit 效期**：Review 结果绑定特定 Commit SHA。代码发生新 Commit 时旧 Review 自动视为 Stale，须在新 HEAD 上重新审查。

## 4. 合并标准

PR 同时满足以下条件方可合并：
- 对应单一 Task / Bug / 用户直接授权；
- 相关自动化 CI 全部成功通过；
- 最新正式技术 Review 结论为 `PASS`；
- 目标分支无冲突，代码与权威文档无漂移；
- 不暴露敏感凭据，不虚构未实现能力。

仓库默认使用 **Squash merge**，合并后删除已合并分支并关闭对应 Issue。
