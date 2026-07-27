## Summary

-

## Related Issue

Closes #

## Included scope

-

## Non-goals

-

## Validation

| Check | Result |
| ----- | ------ |
|       |        |

未执行项及原因：

## Impact review

- [ ] API / Data / Workflow / Version 已评估
- [ ] Product / UI / accessibility 已评估
- [ ] Environment / migration / deployment 已评估
- [ ] Test data level and provenance 已说明
- [ ] Documentation index 已同步（适用时）

说明：

## Evidence

- 测试报告、截图、运行或复现路径：

## Technical Review gate

```text
review_type: technical
review_purpose: pr_technical_review
review_scope:
  target_type: pull_request
  target_ids: [zyyyyynnn/xingwen-astro-ai#<PR number>]
reviewed_head_sha:
verdict: BLOCKED
blocking_findings:
non_blocking_findings:
reviewed_at:
reviewer_kind: human | codex | web_gpt | agent
reviewer_identity:
review_authorization: repository_policy | user_explicit
review_evidence_state: COMMENTED | APPROVED | CHANGES_REQUESTED
```

此处记录当前 HEAD 的正式技术 Review。合格审查者可以是人工、Codex、网页端 GPT、独立审查 Agent 或用户明确授权的其他技术审查主体；不以工具、模型、客户端或入口决定 Review 是否有效。`APPROVED` 对应 `PASS`，`CHANGES_REQUESTED` 对应 `BLOCKED`；`COMMENTED` 正文必须包含独立的 `verdict: PASS | BLOCKED` 行。`reviewed_head_sha` 必须等于 PR 当前 HEAD；新 Commit 会使旧 Review 失效，必须在新 HEAD 上重新 Review，新 Review 显式 supersede 同 scope 旧 Review。当前 HEAD 的 `pr_technical_review` 为 `PASS`、标准 CI 全部通过、PR 可合并且无未解决的真实阻塞问题前，Codex 不得转 Ready 或合并；所有合并条件满足后，可由审查者或 Codex 执行标准合并流程。

## Migration / rollback

- 不适用，或说明步骤：

## Final checklist

- [ ] Diff 与描述一致
- [ ] 当前 HEAD 的 `pr_technical_review PASS`（授权技术审查者）和适用 CI 已通过
- [ ] 不包含无关改动
- [ ] Current / Target / Pending 无混淆
- [ ] 未扩大产品承诺
