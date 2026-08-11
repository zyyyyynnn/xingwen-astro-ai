---
name: Gate
about: 独立验证门：只验证、不修复生产代码
labels: ["type:gate"]
---

## 目标

验证什么范围，并给出可复现的 PASS | BLOCKED 结论。

## 验证范围

- 需要验证的 capability、Artifact、Contract 与运行路径。
- 明确不验证的内容。

## 证据要求

- 固定 commit/manifest、环境与命令。
- Browser/API/Compose/worker 原始可复核结果（脱敏）。
- 版本、Evidence、ownership、权限与 hash 关联。

## 验收标准

- [ ] 真实运行路径可观察，未合并 PR / Fixture / Benchmark / Recorded / Cached 不冒充 Live。
- [ ] 至少一条失败 / 拒绝 / partial / unsupported 真实可见且不被补成 complete。
- [ ] 本 Gate 声明的验证范围内，Version、Evidence、Security、Failure 与 NFR 均有可复核证据。
- [ ] 未达预算或存在真实缺陷时标记 BLOCKED，不降低标准。

## 失败回路

- 发现生产缺陷时回到对应原子 Issue / Task 修复；Gate 自身只验证、不修。
- 报告中列出实际执行命令、观察结果、未验证项、剩余风险与对应原子 Issue。

## PR 交付计划

一个纯验证 PR：只提交验收脚本 / Fixture / Compose / Browser smoke、脱敏证据、矩阵、
风险结论和文档。不承载生产修复或新平台。

## 边界

- 不实现或修复 Workspace、Session / Query / Feed、模型、Parser、Renderer、Executor、
  Pipeline、Persistence、Share 或新基础设施。
- 不把 OpenHands interaction mechanics 当作 ResearchRun runtime，不把 seed / Fixture /
  Benchmark / Recorded / Cached 当 Live。

## 治理要求

Gate 只验证，不修生产代码。任务状态、负责人、标签、层级与阻塞关系只使用 GitHub native
metadata；依赖使用原生 blocked-by，不复制 current state、upstream Issue list 或 current DAG 到正文。
Gate 标题遵循 `CONTRIBUTING.md` 的唯一规范。
