---
name: Task / Chore
about: 原子实现、维护或治理工作
labels: ["type:task"]
---

## 目标

完成后交付什么可观察、可验证的结果。

## Completed baseline

只填写已经在 `main`、已合并 PR、当前 Contract、当前测试或真实运行中可核验的输入。
Issue、Draft/Open PR、目标架构、Fixture、Benchmark、Recorded 和未来 handoff 不得写成
完成基线。

-

## Planned handoff

明确本 Task 计划交付的模块、边界、测试与文档；以下内容均是未来工作，不表示已经实现。

-

## 依赖

只填写真正阻塞该交付的外部 Issue、Contract、Artifact 或环境条件；父 Issue/Epic
或普通协作关系不是阻塞。真实阻塞使用 GitHub 原生 blocked-by。

- 无 /

## 输入与输出

**输入**

-

**输出**

-

## 技术范围

- 一个主要模块、一个主要负责人、一个可观察交付物。
- 明确不修改的边界、公共接口、数据版本与失败语义。

## 核心不变量

-

## 验收标准

- [ ] 每项验收都能通过测试、运行、Contract 或可复核材料观察。
- [ ] 覆盖正常路径、关键边界和失败/拒绝路径。
- [ ] 版本、Evidence、ownership、权限和错误语义没有回退。
- [ ] 提供真实验证命令、结果与未验证项。

## PR 交付计划

单一交付 PR：主要实现、Contract、针对性测试、完整消费路径、回归、文档与交接证据
必须在同一最终 HEAD 完成。标准 CI 和正式技术 Review 通过后再合并；可独立交付的
后续能力应在开工前拆分为新 Task。

## 边界

- 明确不做什么。
- 不夹带无关功能、依赖升级或重构。

## 治理要求

必须添加 `type:task`、适用的 `area:*` 与一个 `priority:p0/p1/p2`。一个 PR 只能有一个
主要 Task、Bug 或 Gate；同一 Issue 的真实阻塞使用原生依赖，不在正文维护第二套
动态状态。
