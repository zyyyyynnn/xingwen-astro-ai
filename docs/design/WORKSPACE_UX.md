# Research Workspace UX

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 科研工作台信息架构、上游骨架映射、核心交互与响应式合同 |

本文定义科研工作台的产品结构与交互。工作台必须基于固定版本的 OpenHands 前端源码进行移植和改造，不接受“参考后手写相似页面”。

## 1. 上游产品骨架

固定基线：

```text
OpenHands/OpenHands 1.8.0
frontend/
openhands-ui/
```

采用的成熟能力：

- App Shell 与全局 Header；
- Conversation / Session Sidebar 的分组、Pin、Recent、搜索、状态与折叠；
- Agent Thread 的流式事件、长任务反馈、错误和恢复；
- Composer 的输入、附件、提交、取消、重试和键盘行为；
- Workspace Panel Host、面板切换、关闭、调整和窄屏行为；
- Loading、Empty、Error、Disconnected 和 Archived 状态；
- Command Palette、焦点管理与键盘导航。

不进入星文智析的模块：

- Terminal、VS Code、Git Diff、Repository 文件管理；
- Sandbox、Coding Agent 设置和软件工程专属 Action；
- `enterprise/` 目录中的任何源码；
- OpenHands 默认品牌、主题和 Coding Domain 文案。

## 2. 产品对象映射

| OpenHands 对象 | 星文智析对象 |
| --- | --- |
| Conversation | Research Mission |
| Agent Session / Run | Research Run |
| Message Thread | Research Thread / Storyline |
| User Message | Research Intent |
| Agent Message | Plan、Research Step、Checkpoint 或 Artifact Delivery |
| Tool Call | Tool Execution |
| File / Workspace Item | Scientific Artifact |
| File Preview | Artifact Review |
| Diff / Commit | Scientific Version Diff |
| Details / Workspace Panel | Evidence、Source、Version 与 Execution Context |
| New Conversation | New Mission / Derived Mission |

映射只发生在 Presentation Adapter；不新增第二套持久化 Domain。

## 3. 最终页面结构

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Global Header: Brand | Project / Mission | Command | Export | Share    │
├──────────────────┬──────────────────────────────────┬───────────────────┤
│ Mission Sidebar  │ Primary Workspace                │ Context Panel     │
│                  │                                  │                   │
│ Mission / Run    │ Thread / Artifact / Source /     │ Evidence / Review │
│ groups           │ Compare / Completion             │ Version / Source  │
│                  │                                  │                   │
│                  ├──────────────────────────────────┤                   │
│                  │ Research Composer / Action Bar   │                   │
└──────────────────┴──────────────────────────────────┴───────────────────┘
```

三部分直接沿用上游成熟 Shell 机制：Sidebar、Primary Workspace、Context Panel Host。星文智析只替换业务对象、内容 Renderer 和视觉 Token。

## 4. Global Header

固定内容：

- 星文智析 Brand；
- Project / Mission breadcrumb；
- 当前 Run 状态或当前阶段的紧凑表达；
- Command Palette；
- Export；
- Share。

Header 不承载 Fixture、Adapter、Hash、模型参数或调试信息。

## 5. Mission Sidebar

Sidebar 使用上游真实 Session / Conversation 导航机制改造。

信息结构：

```text
新建研究

正在进行
待复核
已完成
失败

Projects
最近访问
固定项目
```

Mission 项必须展示：

- 人类可读研究标题；
- 用户状态：Draft / Running / Needs review / Completed / Failed；
- 当前阶段；
- 最近更新时间；
- 待复核或失败提示。

Sidebar 不使用聊天未读数，不显示内部 Run ID。当前项保留上游选中、Pin、分组和折叠行为。

## 6. Primary Workspace

Primary Workspace 是唯一主视觉焦点，使用上游 Workspace / Conversation 主区域的布局、滚动和状态机制。

视图由 Presentation ViewModel 决定：

```text
ResearchBrief
ActiveResearchThread
CheckpointReview
ArtifactReview
SourceReview
ArtifactCompare
CompletionSummary
```

用户不通过“主舞台视图”下拉框选择页面。

### 6.1 Draft

展示 Research Question、Protocol、Source Scope、Expected Artifact 与 Agent Plan。主动作是确认并启动。

### 6.2 Running

默认展示 Research Thread / Storyline：

- Research Goal；
- Agent Plan；
- Current Phase；
- 对科研有意义的事件；
- 生成中的 Artifact；
- 待用户决策。

事件类型：

```text
User Instruction
Plan
Research Step
Tool Execution
Approval Request
Artifact Produced
Evidence Added
Conflict Detected
Revision Produced
Error
Completion
```

原始 Tool 参数和 JSON 进入展开层或 Execution Context。

### 6.3 Needs review

默认打开当前 Checkpoint，不把 Review 隐藏在日志中。支持接受、修改、查看证据和继续执行。

### 6.4 Artifact Review

Artifact 在主区域完整渲染。每个 Statement、数据单元格、Claim 或 Relation 可打开 Evidence Context。

### 6.5 Completed

默认展示 Completion Summary：

- 研究问题；
- 最终结论；
- 最终 Artifacts；
- 关键 Evidence；
- 冲突与局限；
- 未解决问题；
- 推荐下一步；
- 可复现研究包状态。

Completed Mission 底部显示动作栏：继续研究、请求修订、派生新 Mission、导出、分享。不得显示禁用聊天框或“Agent 不可用”。

## 7. Context Panel

Context Panel 复用上游 Workspace / Details Panel Host，不手写静态卡片栏。

驱动对象：

```text
Statement
Evidence
SourceSnapshot
Artifact
ArtifactVersion
Checkpoint
Tool Execution
```

状态：

```text
hidden
summary
detail
```

Summary 每次最多三个可操作摘要。Detail 同时只打开一个对象，顶部提供返回、固定和关闭。Context History 支持：

```text
Statement → Evidence → SourceSnapshot → ArtifactVersion → Back
```

Evidence Detail 至少展示：

- 当前对象；
- Supported / Conflicted / Unresolved；
- 原文或原始数据摘录；
- 来源位置；
- 纳入或排除理由；
- SourceSnapshot；
- ArtifactVersion；
- 打开完整 Source Review。

## 8. Research Composer

Composer 沿用上游成熟输入、附件、提交、取消、重试和键盘机制，但提交对象改为结构化 Research Intent：

```text
continue_research
revise_artifact
verify_statement
change_source_scope
resolve_checkpoint
derive_mission
```

Composer 的作用范围必须进入 Command / Controller。Completed 状态默认使用动作栏；Running 与 Review 状态显示 Composer。

## 9. Artifact Renderer

必须提供类型专属 Renderer：

```text
Dataset
Field Dictionary
Source Collection
Paper Collection
Literature Summary
Literature Comparison
Literature Claims
Literature Relations
Reasoning Trace
Candidate Dossier
Evidence Graph（真实 Contract 可用后）
```

未知类型显示明确的 unsupported state；Hash 和内部 ID 只在技术详情中出现。

## 10. 响应式

### ≥ 1440 px

Sidebar 常驻；Context Summary 常驻；Detail 使用上游 Panel Overlay 或宽屏分栏机制。

### 768–1439 px

Sidebar 可折叠；Context Detail 以覆盖式 Panel 打开，Primary Workspace 不被压缩到不可读。

### < 768 px

Sidebar 使用 Drawer；Context 使用全屏 Sheet；Primary Workspace 全宽；Composer 固定在安全区域内；Compare 使用 A/B 切换或上下对照。

必须验证 1440×900、1280×800、390×844、keyboard-only 和 200% 字体。

## 11. 产品语言

默认界面使用中文。论文标题、DOI、Artifact Kind 和标准术语可保留英文。正式界面不得出现 `A-17 CANVAS`、`Preview`、泛化 `Context`、内部 Fixture、Adapter、Execution Mode 或调试 Route 文案。

## 12. 视觉验收门

首次编码前必须提交并由用户确认：

1. 原版 OpenHands Sidebar / Thread / Panel / Composer 截图；
2. Upstream → Local 文件级移植矩阵；
3. 改造后的 Completed Mission；
4. Running Mission Thread；
5. Artifact Review；
6. Evidence Detail；
7. 390×844 视图。

实现者不得自行宣布视觉 PASS。
