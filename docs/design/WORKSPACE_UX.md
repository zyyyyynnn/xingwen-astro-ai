# Research Workspace UX

| 项目状态 | 口径 |
| --- | --- |
| Status | Accepted for implementation |
| Implementation | Pending |
| Current runtime | `apps/web` 中的 Vue 3 单页骨架 |
| Target runtime | Astro Brand Site + React Guided Tour / Research Workspace |

本文定义科研工作台的信息架构、核心交互、页面状态和 Guided Tour。工作台借鉴现代 Agent Desktop 的桌面级组织能力，但不采用“聊天线程 + 工具日志”作为产品核心。

## 1. 产品差异化原则

星文智析工作台必须体现以下差异：

| 通用 Agent Desktop | 星文智析 Research Workspace |
| --- | --- |
| 项目 / 聊天线程 | ResearchProject / ResearchRun |
| 消息与工具调用 | 结构化科研产物与 Evidence |
| 文件变更审查 | 数据、论文、Claim、Relation、Graph 与版本审查 |
| Agent 日志 | TaskStep、来源快照、运行参数和错误分类 |
| 环境面板 | Provenance Observatory |
| 聊天输入框 | Research Console + Research Contract |

核心原则：**科研产物优先，AI 对话次之，执行日志降为辅助信息。**

## 2. 体验域

### 2.1 Brand Site

- 建立品牌与主案例认知。
- 用四幕式叙事解释“问题—数据—证据—工作台”。
- 提供 Demo Replay 与 Live Run 两个入口。
- 不承担复杂项目管理。

### 2.2 Guided Tour

- 默认使用版本化主案例 Demo Replay。
- 支持在 ACT 02 修改 Research Contract 并切换 Live Run。
- 通过受控镜头和焦点，依次展示关键科研产物。
- 允许暂停、跳过、返回和直接进入工作台。
- 任何回放内容都必须标注为示例研究运行。

### 2.3 Research Workspace

- 管理多个研究项目和运行。
- 支持同时查看最多三个科研产物。
- 提供来源、证据、版本和反馈审查。
- 支持分享只读结果链接。
- 不要求账号登录；使用隔离的临时研究会话。

### 2.4 首页四幕

首页是约 60–90 秒、可跳过的短叙事，不是营销长页，也不使用强制滚动劫持：

| 幕 | 内容 | 交互与可信性要求 |
| --- | --- | --- |
| ACT 01 — SIGNAL | 巨型裁切 ASCII / Dither 系外行星、中文主标、核心价值与快速入口 | 标题、说明和 CTA 必须存在于静态 DOM；WebGL 不是 LCP 前置条件 |
| ACT 02 — QUESTION | 自然语言研究意图重组为可编辑 Research Contract | 用户能暂停、编辑、跳过；不在确认前启动 Live Run |
| ACT 03 — EVIDENCE | Dataset、Paper、Claim、Evidence、Relation 逐层显现 | 视觉只解释结构，不虚构科研数据或精度 |
| ACT 04 — WORKSPACE | 场景收束为真实工作台结构 | 允许继续 Demo Replay、切换 Live Run 或直接进入 Workspace |

默认路径读取确定性 Fixture；选择 Live Run 前必须解释外部依赖、等待、失败与缓存语义。移动端可使用静态 Poster 或低复杂度场景，但核心四幕内容不减少。

## 3. 全局布局

桌面完整布局：

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Top Status Rail                                                     │
├───────────────┬──────────────────────────────────┬──────────────────┤
│ Research      │ Research Canvas                  │ Provenance       │
│ Atlas         │ 1–3 controlled panes            │ Observatory      │
│               │                                  │                  │
├───────────────┴──────────────────────────────────┴──────────────────┤
│ Research Console                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

推荐尺寸范围：

| 区域 | 默认 | 可调整范围 |
| --- | --- | --- |
| Top Status Rail | 44px | 固定 |
| Research Atlas | 276px | 224–360px |
| Provenance Observatory | 360px | 300–480px |
| Research Console | 76px 收起 | 76–280px |
| Research Canvas | 自适应 | 最小 560px |

空间不足时优先收起右栏，其次左栏；中央画布小于最低宽度时切换单焦点视图。

主要设计与视觉回归基准为 `1440×900`、`1920×1080`；`1280px` 宽仍必须可完成 Research Contract、运行、产物审查和 Evidence 定位主流程。

## 4. Top Status Rail

顶部不是传统营销导航，也不是 IDE 菜单栏。应包含：

- 中文字标缩略版
- 当前 ResearchProject / ResearchRun 路径
- 执行方式：Demo Replay / Live；产物来源：Fixture / Live / Cached / Revised
- 当前任务状态与关键步骤
- 全局搜索 / Command Palette
- 分享、导出、帮助和质量档

状态栏不得显示过多装饰。运行状态应使用文字、图标和轻量动效共同表达。

## 5. Research Atlas

Research Atlas 是左侧研究项目与阶段导航，不是聊天历史。

### 5.1 一级结构

```text
Recent Research
├─ ResearchProject A
│  ├─ Run 03 / Live / running
│  ├─ Run 02 / Revised
│  └─ Run 01 / Cached
├─ ResearchProject B
└─ Shared Result Links
```

### 5.2 项目内部结构

```text
Overview
Research Contract
Runs
Artifacts
├─ Data
├─ Papers
├─ Literature
├─ Reasoning
├─ Graph
└─ Exports
Feedback
History
```

### 5.3 并行状态

多个运行可并行，但界面通过“运行轨道”表达，不使用聊天未读数量：

- `queued`
- `running`
- `waiting_for_input`
- `completed`
- `failed`
- `cached_available`

运行轨道显示当前阶段、耗时和来源，不显示原始模型思维过程。

## 6. Research Contract

### 6.1 自然语言起步

用户在首页或 Research Console 输入研究目标，例如：

> 整合主案例中系外行星候选体与宿主恒星的关键参数，并追踪每个字段的来源和相关论文依据。

系统生成 Research Contract，而不是立即执行。

### 6.2 契约结构

字段名是目标领域契约，不使用仅供展示的同义词替代：

| 字段 | 示例内容 |
| --- | --- |
| `research_goal` | 整合候选体与宿主恒星关键参数 |
| `target_objects` | 系外行星候选体、宿主恒星 |
| `data_requirements` | 单位、时间范围、缺失值和交叉匹配要求 |
| `requested_fields` | 半径、质量、周期、恒星温度、金属丰度等 |
| `source_scope` | 允许的开放天文数据库与补充来源 |
| `paper_search_scope` | 关键词、年份、最大候选数、选择规则 |
| `output_requirements` | CSV、字段字典、溯源报告、图谱 |
| `evidence_requirements` | locator、quote/value、SourceSnapshot 和覆盖率 |
| `quality_constraints` | 来源完整性、单位一致性、证据覆盖率 |
| `execution_mode` | `demo_replay` 或 `live` |

用户可以逐项编辑、接受建议或恢复默认主案例。

### 6.3 执行门

- 必填字段不完整时不得执行。
- 系统应展示预计步骤和可能的外部依赖。
- Demo Replay 和 Live Run 的差异必须在确认前说明。
- 执行后契约进入只读版本；修改产生新运行或修订版本。

## 7. Research Canvas

中央画布支持 1–3 个受控面板。不是自由桌面，不允许无限悬浮窗口。

### 7.1 面板模型

每个面板包含：

- Artifact 类型和标题
- 运行来源与版本
- 主要内容
- Evidence / 来源入口
- 面板操作：固定、拆分、替换、关闭、全屏

### 7.2 拆分规则

支持：

- 单面板聚焦
- 左右双面板
- 主面板 + 右侧窄面板
- 左右 + 底部三面板

禁止：

- 超过三个中央面板
- 任意拖拽重叠窗口
- 未保存的布局在不同项目间污染

### 7.3 推荐对照组合

| 场景 | 面板组合 |
| --- | --- |
| 字段核验 | 数据表 + Evidence |
| 论文筛选 | 候选论文 + 检索运行详情 |
| 文献理解 | PaperSummary + 原文 Evidence |
| 推理审查 | Claim / Relation + ReasoningTrace + Evidence |
| 图谱审查 | Graph + Relation / Trace + Evidence |
| 反馈修正 | 当前版本 + 修订草案 + 影响范围 |

## 8. Provenance Observatory

右侧区域是产品的核心差异化组件。它不是普通详情栏，而是统一的来源、证据和版本观测台。

### 8.1 选中对象

可接受：

- 数据单元格或字段
- 数据来源
- 论文候选
- PaperSummary 结论
- Claim
- Relation
- ReasoningTrace
- GraphNode / GraphEdge
- ArtifactVersion

### 8.2 内容层级

```text
Object Identity
Source Mode / Version
Evidence
Source / Paper
Locator / Quote / Value
Extraction Method
Confidence / Quality
Snapshot / Query Hash
Related Objects
Feedback Actions
```

### 8.3 交互规则

- 从任意产物点击 Evidence，右栏更新但不丢失中央上下文。
- 可固定当前 Evidence，以便对照另一个对象。
- 支持在右栏打开更完整的 Evidence 文档视图。
- 不显示模型私有思维过程；ReasoningTrace 只展示可审查的显式依据。
- 来源不可访问时展示快照信息和失败原因。

## 9. Research Console

Research Console 位于底部，默认收起为紧凑状态。

### 9.1 作用

- 新建研究目标
- 追问当前产物
- 请求修改 Research Contract
- 重试某个 TaskStep
- 扩展字段或论文范围
- 生成导出物
- 提交反馈与局部修正

### 9.2 上下文

提交前明确显示：

- 当前项目
- 当前运行
- 选中产物
- 允许影响的范围
- execution mode 与 source mode

### 9.3 输出规则

AI 响应优先生成：

- 契约变更建议
- 新 Artifact
- 新运行计划
- 结构化解释
- 反馈修订草案

只有解释性追问才返回纯文本。长篇 AI 回复不得把核心产物推离主工作区。

## 10. 页面与产物视图

### 10.1 Project Overview

展示：

- Research Contract 摘要
- 最近运行
- 工作流阶段
- 产物覆盖情况
- Evidence 覆盖率
- 风险和失败
- 推荐下一步

视觉可使用低密度 ASCII 天体缩略图，但不使用全屏动态背景。

### 10.2 Data Workspace

展示：

- 可虚拟化数据表
- 字段字典
- 来源覆盖
- 单位和缺失值
- 质量评分
- 导出入口

关键交互：选择单元格后打开 Evidence；支持字段固定和对照；不在表格内塞入长来源文本。

### 10.3 Paper Acquisition Workspace

展示：

- 检索 Query 与参数
- 获取来源
- 候选数量、去重和排序
- PaperCandidate 列表
- 入选 / 排除原因
- Live / Cached / Seed Benchmark 标识

必须能证明候选不是手写塞入。

### 10.4 Literature Workspace

展示：

- 论文元信息
- 目标、方法、数据、发现、局限
- 每条核心结论的 Evidence
- 版本和 Prompt / 模型信息

支持论文间并排对照。

### 10.5 Reasoning Workspace

展示：

- Claim 列表
- 候选 Relation 与最终 Relation 分离
- Relation 类型、条件和置信度
- ReasoningTrace
- 双方 Evidence

不得把模型推理描述为无条件科学事实。

### 10.6 Graph Workspace

展示：

- 受控规模的证据图谱
- 节点类型和边类型
- 边的 Evidence / Relation / Trace
- 过滤、聚焦和邻接探索

图谱服务审查，不为视觉效果生成额外节点或无证据边。

### 10.7 Feedback Workspace

反馈必须定位到对象和版本：

- 字段 / 单位
- 来源
- 论文候选
- PaperSummary
- Claim / Relation / Trace
- GraphNode / GraphEdge

提交后先生成影响范围和修订计划，确认后产生新 ArtifactVersion。

## 11. Guided Tour

### 11.1 默认主案例

默认 Demo Replay 锁定“系外行星候选体与宿主恒星参数整合”，但界面和契约不写死为唯一对象类型。

### 11.2 引导步骤

```text
1. Signal：认识品牌和主案例
2. Question：查看或编辑 Research Contract
3. Acquire：数据与论文来源出现
4. Resolve：字段、论文和 Evidence 被整理
5. Reason：Claim、Relation 与 Trace 形成
6. Map：证据图谱聚合
7. Inspect：打开 Provenance Observatory
8. Continue：进入完整 Workspace
```

### 11.3 Demo Replay 与 Live Run

| 模式 | 行为 |
| --- | --- |
| Demo Replay | 确定性数据、稳定时序、可重复录制、明确标识 |
| Live Run | 调用真实 API，允许等待、失败、缓存和重试 |

两者共享相同领域模型与 UI 组件，不维护两套页面。

## 12. 会话与分享

### 12.1 免登录模式

- 评委可直接体验 Demo Replay。
- Live Run 创建隔离临时会话。
- 会话具有过期时间和容量限制。
- 不在浏览器保存敏感凭据。

### 12.2 只读分享

分享链接包含：

- ResearchProject / ResearchRun 标识
- 当前 ArtifactVersion
- 来源模式
- 可公开的 Evidence 和导出物

只读页面不得暴露内部密钥、受限全文、原始错误堆栈或未授权输入。

## 13. 空、加载、失败与缓存状态

每种产物视图必须覆盖：

- `empty`：说明需要什么输入或前置产物
- `loading`：布局稳定，显示具体 TaskStep
- `partial`：部分来源或字段可用
- `success`：产物、来源和版本完整
- `failed`：错误分类、影响和下一步
- `fixture`：场景版本、schema version 和明确 Demo 标识
- `cached`：真实历史 Run、缓存时间、适用性与本次 Live 失败原因
- `revised`：当前修订和原版本关系

ASCII 动效只辅助状态表达，不替代文字和进度。

## 14. 键盘与命令

推荐快捷键：

| 操作 | 快捷键 |
| --- | --- |
| Command Palette | `Ctrl/Cmd + K` |
| Research Console | `Ctrl/Cmd + J` |
| 新建项目 | `Ctrl/Cmd + Shift + N` |
| 打开 Evidence | `E`（焦点对象可用时） |
| 切换左栏 | `Ctrl/Cmd + B` |
| 切换右栏 | `Ctrl/Cmd + Shift + B` |
| 聚焦面板 1–3 | `Alt + 1/2/3` |
| 退出弹层 / Guided Step | `Esc` |

快捷键不得阻断浏览器和辅助技术的基础操作。

## 15. 移动端降级

移动端保留：

- 首页品牌体验的简化版本
- Research Contract 创建与确认
- 项目和运行查看
- 单焦点产物视图
- Evidence 抽屉
- 分享结果

移动端不提供三面板对照和完整高密度图谱编辑。WebGL 使用低质量或静态 Poster。

## 16. UX 验收

- 新用户在首页 10 秒内能识别产品主题和主动作。
- 无人讲解完成 Guided Tour 后，用户能说明数据、论文、推理和 Evidence 的关系。
- 用户可在 3 次交互内从任意结论定位到 Evidence。
- 工作台中央默认不是聊天流。
- 多项目并行状态可区分，但不会形成通用 Agent 线程列表的外观。
- 数据、论文、推理和图谱之间可以通过最多三面板完成对照。
- Demo Replay、Live、Cached 和 Revised 绝不混淆。
- 所有失败状态提供可执行下一步。
- `1440×900`、`1920×1080` 完整布局与 `1280px` 可完成主流程均通过验证。
- 中央最多三个拆分面板，底部 Research Console 不遮挡当前核心产物。
- 无鼠标可以确认 Research Contract、切换产物、定位 Evidence、重试或取消运行。
