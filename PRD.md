# PRD

| 项目状态 | 口径 |
| --- | --- |
| Status | Accepted for implementation |
| Implementation | Pending |
| Current runtime | `apps/web` 中的 Vue 3 骨架 |
| Target runtime | Astro 品牌站 + React Research Workspace Monorepo |

本文件冻结目标产品范围，不表示 Astro / React 迁移或目标 API 已经实现。当前可运行命令仍以 `README.md` 与 `docs/setup.md` 的“当前实现基线”为准。

## 1. 产品目标

星文智析面向天文科研数据整理与证据核验场景，帮助用户从一个研究目标出发，完成研究任务契约确认、数据获取与清洗、自动论文获取、文献总结、跨文献逻辑推理、证据图谱、结果导出和反馈修订。

MVP 默认主案例为：**系外行星候选体与宿主恒星参数整合**。

产品架构允许扩展到其他天文数据整合任务，但提交版本只承诺已通过真实运行、证据和测试验证的范围。

## 2. 产品形态

产品包含三个连续但职责不同的体验域：

| 体验域 | 作用 |
| --- | --- |
| Brand Site | 用四幕式 ASCII / Dither 天文叙事建立品牌和价值认知 |
| Guided Tour | 以稳定 Demo Replay 或可切换 Live Run 展示完整研究链路 |
| Research Workspace | 以多项目、科研产物、证据和版本为核心的研究桌面 |

工作台不是通用聊天 Agent。AI 作为上下文协作者存在，中央主区域优先展示数据集、论文、Claim、Relation、ReasoningTrace、Graph 和 Evidence。

## 3. 成功标准

| 维度 | MVP 必达标准 |
| --- | --- |
| 可理解 | 无现场讲解时，用户可从首页和 Guided Tour 理解产品价值、工作流和证据机制 |
| 可运行 | 公网 Demo 可访问，主案例可使用 Demo Replay 稳定展示并支持 Live Run |
| 可复现 | 同一主案例可定位到运行参数、来源快照、产物版本和缓存来源 |
| 可溯源 | 数据字段、文献结论、跨文献关系和图谱边均能追踪到 Evidence |
| 可对照 | 工作台支持最多三面板对照科研产物、推理依据和证据 |
| 可导出 | 支持 CSV、数据字典、溯源报告、文献与推理关系 JSON 等导出 |
| 可分享 | 可生成隔离、只读的结果分享链接 |
| 可提交 | 页面、视频、PDF、源码、API 和测试材料形成一致的作品入口 |
| 可降级 | WebGL、外部来源或模型失败时，核心信息和任务操作仍可用 |

## 4. 目标用户

| 用户 | 主要需求 | 产品响应 |
| --- | --- | --- |
| 天文科研初学者 | 将研究意图转换为明确的数据、论文和证据需求 | 生成可编辑 Research Contract，并展示完整产物链 |
| 科研使用者 | 对照数据、论文、结论和来源，审查结果可靠性 | Research Canvas + Provenance Observatory |
| 竞赛评审 | 快速判断作品是否真实、完整、可复现 | 首页四幕、Guided Tour、运行来源、Evidence 和版本入口 |
| 开发与复现人员 | 检查架构、接口、数据和测试 | 技术文档、API、源码、Fixture / HTTP 双通道和复现步骤 |
| 材料制作人员 | 生成一致的截图、视频和技术说明 | 确定性 Demo Replay、稳定视口和可定位版本 |

## 5. 主流程

1. 用户输入自然语言研究意图。
2. 系统解析为可编辑的 `ResearchContract`。
3. 用户确认目标对象、字段、来源范围、论文范围、输出和质量要求。
4. 系统创建 `ResearchProject` 与 `ResearchRun`。
5. 系统获取并清洗天文数据，输出 Dataset、字段字典、来源和质量评分。
6. 系统自动检索论文候选，记录 Query、来源、去重和排序。
7. 系统生成结构化 PaperSummary，并绑定 Evidence。
8. 系统抽取 Claim，构建候选与最终 Relation、ReasoningTrace。
9. 系统构建绑定 Evidence 的学术图谱。
10. 用户在最多三面板的 Research Canvas 中对照审查产物。
11. 用户通过 Provenance Observatory 定位来源、证据、版本和运行快照。
12. 用户导出、分享只读结果或提交局部反馈。
13. 系统生成修订计划和新 ArtifactVersion，保留旧版本。

## 6. 运行模式

执行方式与产物来源是两个独立维度，不得用一个 Badge 混合表达：

| `execution_mode` | 用途 | 约束 |
| --- | --- | --- |
| `demo_replay` | 首页和 Guided Tour 的确定性主案例回放 | 明确标识，不冒充实时运行 |
| `live` | 调用真实 API、数据源和模型 | 允许等待、失败、重试和缓存建议 |

| `source_mode` | 含义 | 约束 |
| --- | --- | --- |
| `fixture` | 版本化演示数据 | 仅用于 Demo Replay、测试和稳定录制，必须带 scenario 与 schema version |
| `live` | 本次真实运行产物 | 绑定 Run、SourceSnapshot、时间和参数 |
| `cached` | 可定位的真实历史运行产物 | 展示来源 Run、时间、参数、适用性和实时失败原因 |
| `revised` | 反馈后生成的新 ArtifactVersion | 关联原版本、Feedback 和修订依据 |

`demo_replay` 通常读取 `fixture`；`live` 执行可以产出 `live`，或在明确失败后选择 `cached`。手写 Fixture 永远不能标记为 `cached`。

## 7. 用户与会话

MVP 采用免登录体验：

- Demo Replay 直接可用。
- Live Run 创建隔离临时研究会话。
- 会话具有过期和资源限制。
- 支持生成只读结果链接。
- 暂不实现完整账号、团队空间和企业权限。

## 8. MVP 功能范围

| 模块 | 必须实现 | 暂不承诺 |
| --- | --- | --- |
| 品牌入口 | 四幕式首页、基础 SEO、静态首屏、WebGL 降级 | 内容型大型官网 |
| Guided Tour | Demo Replay、Live 切换、步骤控制、可跳过 | 为每个天文方向制作独立故事 |
| Research Contract | 自然语言解析、结构化编辑、确认后执行 | 无约束直接执行任意科研目标 |
| 项目与运行 | 多 ResearchProject、多个 ResearchRun、并行状态 | 完整团队协作和权限体系 |
| 任务编排 | 状态流转、错误、缓存和结果聚合 | 浏览器直接编排外部 Pipeline |
| 数据分析 | 真实来源、字段对齐、单位统一、质量和 CSV | 任意天文数据格式完全自动处理 |
| 论文获取 | 自动检索、去重、排序、来源和选择依据 | 全网无限制爬取或绕过付费全文 |
| 文献总结 | 结构化摘要、Evidence 和版本 | 完全自动论文写作 |
| 跨文献推理 | Claim、Relation、ReasoningTrace、Evidence | 无证据多跳科学发现 |
| 学术图谱 | 节点、边、Evidence、Trace 与前端交互 | 大规模通用知识图谱平台 |
| 科研桌面 | Research Atlas、最多三面板、Observatory、Console | 无限自由窗口和完整 IDE |
| 反馈修正 | 对象级反馈、影响范围、追加式版本 | 原地覆盖历史产物 |
| 分享与导出 | 只读链接、CSV、JSON、报告 | 复杂公开协作社区 |

## 9. 页面与工作区范围

| 区域 | 核心内容 | 验收重点 |
| --- | --- | --- |
| 首页 | ASCII / Dither 天体、四幕叙事、双入口 | 10 秒识别主题；无 JS 仍有核心内容 |
| Guided Tour | Research Contract、阶段产物、Evidence 揭示 | 60–90 秒可理解完整价值，可随时跳过 |
| Project Overview | 契约、运行、阶段、产物和风险 | 多运行来源与版本清楚 |
| Data Workspace | 数据表、字段字典、来源、质量 | 单元格可定位 Evidence |
| Paper Acquisition | Query、候选、去重、排序、入选原因 | 能证明自动获取过程 |
| Literature | 目标、方法、数据、发现、局限 | 每条核心结论可打开 Evidence |
| Reasoning | Claim、候选/最终 Relation、Trace | 不把无证据推理当事实 |
| Graph | 节点、边、Evidence、Relation、Trace | 图谱服务审查而非装饰 |
| Provenance Observatory | 来源、locator、quote/value、snapshot、版本 | 从任意关键结果三次交互内到 Evidence |
| Feedback | 对象定位、影响范围、修订计划 | 修订产生新版本并保留历史 |
| Share | 只读结果和公开 Evidence | 不暴露敏感数据和内部状态 |

## 10. 视觉与交互要求

- 主色为低饱和雾霾蓝，基底为冷淡灰，只实现浅色系统。
- ASCII 字符与 Dither 网点共同构成品牌视觉。
- 首页和 Guided Tour 允许高强度实时 WebGL；数据、文献和 Evidence 区域保持克制。
- 中文“星文智析”为主字标，英文为副标。
- 品牌与叙事标题使用衬线；正文使用无衬线；坐标、参数和 ASCII 使用等宽。
- 工作台中央默认不是聊天流。
- 桌面端提供完整多面板体验；移动端降级为单焦点产物视图。
- 支持 Reduced Motion、高/中/低图形质量和静态 Poster 回退。

## 11. 质量指标

| 指标 | 定义 | MVP 目标 |
| --- | --- | --- |
| 字段覆盖率 | 目标字段中成功获取并对齐的比例 | >= 80% |
| 来源完整性 | 结果字段带来源记录的比例 | 100% |
| 单位一致性 | 关键数值字段单位统一情况 | 100% |
| 论文获取可复现性 | 候选带 Query、来源、时间和选择依据 | 100% |
| 文献结构完整度 | 目标、方法、数据、结论、局限覆盖 | >= 80% |
| 跨文献关系证据率 | 最终 Relation 绑定 Evidence 和 Trace | 100% |
| 图谱证据完整度 | GraphEdge 绑定 Evidence | 100% |
| 证据可达性 | 从关键结果定位 Evidence 所需交互 | <= 3 次 |
| Guided Tour 完整性 | 默认回放无需外部服务即可完整展示 | 100% |
| 来源模式准确性 | Demo、Live、Cached、Revised 正确标识 | 100% |
| WebGL 降级 | 不支持 WebGL 时核心内容和操作可用 | 100% |
| 可访问性 | 核心流程键盘可用且无严重自动化违规 | 100% |

## 12. 作品提交路径

作品材料默认按以下顺序组织：

```text
START HERE
-> 60–90 秒品牌短片
-> 公网首页
-> Guided Tour
-> Research Workspace
-> 技术方案 PDF
-> API / 源码 / 测试 / 复现材料
```

视频和网页使用相同 Demo Replay、版本与视觉基线，避免截图、描述和实际系统不一致。

## 13. 验收口径

MVP 完成必须同时满足：

- 公网首页、Guided Tour、Workspace 和分享页可访问。
- 默认主案例可通过 Demo Replay 完整展示，Live Run 入口真实可用。
- Research Contract 可查看、编辑和确认。
- 数据、论文、文献、推理、图谱和 Evidence 形成连续链路。
- Fixture 与 HTTP Adapter 返回同一领域模型，示例与真实来源明确标识。
- 数据结果来自真实来源或明确标注的真实运行缓存。
- 自动论文候选包含检索参数、来源、时间和选择依据。
- PaperSummary、Relation、Trace 和 GraphEdge 绑定 Evidence。
- 工作台支持最多三面板对照，中央默认不使用聊天流。
- CSV、数据字典、溯源报告和推理关系 JSON 可导出。
- 反馈产生新版本，不覆盖历史产物。
- WebGL 可降级，Reduced Motion 和移动端可用。
- README、PRD、DESIGN、专项设计文档、API、数据模型、Issue 和实现一致。
