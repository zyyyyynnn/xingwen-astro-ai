# Reference Integration

| 元数据 | 值 |
| --- | --- |
| Authority | 第三方/参考项目能力审计、迁移、吸收、转化与深度集成 |

本文定义 Xingwen 如何使用外部 Reference 源码和产品机制。目标是**尽可能多地吸收成熟能力，同时尽可能少地保留拼接感、重复系统和上游项目边界**。

## 1. 基本命题

Reference 不是插件市场，也不是把多个项目并排运行。正确路径是：

```text
Reference capability
→ source audit
→ current-main gap analysis
→ choose adoption depth
→ map to existing Xingwen authority
→ transform to Xingwen domain semantics
→ integrate into existing runtime / artifact / evidence / UX
→ remove temporary seams
→ verify from real user entry
```

任何 Reference 都不能成为第二套产品事实源。集成完成后，生产事实由 Xingwen 当前 Domain、Workflow、Publisher、ArtifactVersion、Evidence、Renderer 与 Workspace 管理。

## 2. 当前审计输入

用户提供的 Reference archive 当前包含三组源码输入：

### AutoAstro

归档中可见 Apache License 2.0。源码包含研究任务规划/执行、数据与图像分析、cross-match、异常/错误修正、机器学习/深度学习执行、时间序列相关处理与 benchmark 数据入口。

这些能力与 Xingwen 当前的数据整合、实体对齐、Scientific Skills、模型执行和 Artifact/Evidence 链存在明显重叠。后续实现不得按目录搬运；必须先逐能力比较当前 `main`，只补真正缺失或明显弱于 Reference 的行为。

### inosum

归档中为单体论文分析/总结脚本，包含论文切分以及 background、methodology、experiment/conclusion、dataset、discussion、limitations、questions 等结构化抽取路径。

提供的归档根部未观察到独立 license 文件，因此在许可证确认前，仅作为行为、输出结构、Prompt 组织和缺口分析输入；不得把“本地能读取源码”当作源码复制授权。

### mavis

归档中包含多 Agent 任务拆解、工具选择、代码执行、天文数据/星历/FITS 工具、Astropy/Skyfield/Photutils 能力、WWT 交互、Qwen/DashScope 与多 provider 调用、以及 WebSocket/前端实验代码。

当前 Xingwen 已存在 astronomy、astro acquisition、time-series、eclipse geometry、data analysis、inference/modeling、WWT capabilities、ResearchRun/Worker/Publisher 等生产能力。MAVIS 应作为**能力库和交互/工具编排参考**，而不是新的 Agent runtime 或 WWT sidecar 架构来源。提供的归档根部未观察到独立 license 文件，源码级复制前必须另行确认许可证。

以上归档是审计输入，不是仓库 Authority，也不是“未完成能力列表”。当前 `main` 始终先于 Reference 目录结构决定生产架构。

## 3. Capability Gap Matrix

任何大型 Reference Integration PR 在编码前必须形成一份临时工作矩阵，至少包含：

| 字段 | 含义 |
| --- | --- |
| Reference capability | 上游真实能力，不按文件名猜测 |
| Current Xingwen owner | 当前生产 Authority / module / service |
| Current state | absorbed / partial / missing / superseded / reject |
| User value | 对主案例或科研工作流的真实价值 |
| Adoption depth | source / algorithm / protocol-data / UX-mechanic / benchmark / none |
| Integration target | 唯一 Domain / Workflow / Skill / Renderer / UX seam |
| Evidence impact | 是否需要 Evidence / SourceSnapshot / provenance |
| Reachability | 用户从哪里发现并使用 |
| Verification | unit / integration / browser / benchmark / live proof |
| Removal | 迁移完成后应删除的临时或重复实现 |

矩阵只用于实现决策，不要求把大体积阶段性清单永久提交到 Git。稳定结论写入对应 Authority；工作状态留在 PR。

## 4. Adoption Depth

按以下优先级选择最深且合法、可维护的采用方式：

1. **Source-level adoption**：许可证兼容、依赖可控、源码质量与当前架构适配时，允许直接采用并做 Xingwen 化改造；必须固定来源 revision 并保留必要 attribution/NOTICE。
2. **Algorithm / behavior adoption**：保留成熟算法、流程或失败语义，重写接口与状态所有权以接入现有 Authority。
3. **Protocol / data adoption**：吸收数据结构、工具 schema、benchmark、catalog、Prompt 输出约束或科学常量，不复制上游 runtime。
4. **UX mechanic adoption**：复用成熟交互机制，再映射到 Xingwen Domain；OpenHands Shell 属于这一类的源码级特殊采用。
5. **Benchmark-only**：仅用于对照或回归，不进入生产决策链。
6. **Reject**：能力与赛道、产品目标、安全、许可证或 current-only 架构不一致时明确不采用。

“能复制”不等于“应该复制”；“已经有类似代码”也不等于“已经吸收能力”。判断标准是行为质量、科学正确性、可复现性、用户可达性和维护成本。

## 5. 深度集成规则

Reference capability 进入生产后必须：

- 使用 Xingwen 领域名、Artifact kind、Evidence 和错误语义；
- 从现有 Research Intent / Contract / Run / Activity / Artifact 路径进入，不增加“Reference 模式”；
- 由现有 ScientificStepService / registry / admission / Publisher 等唯一执行链承载；
- 复用现有 SourceSnapshot、Evidence、Revision、Cache、Renderer Registry、Fullscreen Result Workspace 与 Public Share；
- 对用户呈现一个连续科研过程，而不是“先进入 A 工具，再切 B 页面，再看 C 结果”；
- Reference 特有参数只有在真实影响科研判断且用户需要控制时才上升为产品控制项；其余保持内部实现细节；
- 临时 bridge 在收口前删除，不能演变为永久双模型/双 DTO/双状态同步。

## 6. Anti-stitching

以下模式视为拼接型集成，默认禁止：

- 按上游项目建立永久 `reference_*`、`mavis_*`、`autoastro_*` 生产子系统；
- Reference service 作为旁路 sidecar 写入自己的结果库，再由 Xingwen 二次导入；
- 第二套 Planner / Agent runtime / Worker / Publisher / Evidence store / Graph backend / Revision engine；
- 第二套 Workspace Shell、工具面板、结果详情、Renderer Registry 或公共分享 renderer family；
- raw JSON 作为长期跨系统语义总线；
- wrapper 套 wrapper，只为兼容上游函数签名而保留多层 adapter；
- 为上游历史行为保留 current production 不需要的 compatibility layer；
- 在 UI 中暴露 Reference 项目名、内部工具名或模块边界，让用户理解系统拼装结构。

## 7. Product Reachability

迁移的能力只有同时满足以下条件才算被 Xingwen 吸收：

1. 有真实用户入口或由 Agent 在明确任务中自动触发；
2. 走正式 Repository / Workflow / Scientific runtime；
3. 输出进入 typed Artifact / Evidence / SourceSnapshot / Activity；
4. 用户能在统一 Workspace 中理解结果与失败；
5. 必要时可比较、修订、导出或分享；
6. 有 Browser 或真实纵向验证证明它不是隐藏库函数；
7. 不要求用户理解上游项目结构才能使用。

只有 backend 函数、单测、benchmark 或静态 demo 不满足“已集成”。

## 8. 科学与竞赛边界

Reference 的模型调用、benchmark 数字或实验结果不能自动成为 Xingwen 的竞赛证据。竞赛主案例仍必须通过 Xingwen 自己的 Contract、合格 Qwen 调用、ResearchRun、ProducerExecution、ArtifactVersion、Evidence 与复现实验形成闭环。

参考项目可以提高能力和质量，但最终差异化应来自 Xingwen 的整合：**多源科学数据 + 科学文档 + 文献 Claim/Relation + Evidence Graph + 版本化 Artifact + 人类 Revision + 可验证 Agent Workspace**，而不是对 Reference 项目数量的展示。

## 9. Review 要求

Reference Integration Review 必须回答：

- 当前 `main` 已经具有什么，是否重复实现；
- 为什么选择当前 adoption depth；
- 源码/许可证/provenance 是否满足采用边界；
- 新能力进入哪个唯一 Authority；
- 是否产生第二 runtime/store/renderer/schema；
- 是否有临时 seam 未删除；
- 是否真正提升主案例或产品差异化；
- 用户能否从正式 Workspace 路径使用；
- 是否有真实 Evidence、Browser 或 benchmark 证明；
- 是否存在更简单、复用更多的实现。
