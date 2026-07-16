# PRD

| 项目状态     | 口径                                                             |
| ------------ | ---------------------------------------------------------------- |
| Status       | Active                                                           |
| A-01 runtime | Implemented：Astro Brand Site、React Research Workspace 与共享包 |
| Product UI   | A-02、A-03 Pending                                               |
| API          | `/api/v1` Current；`/api/v2` Pending                             |

本文件定义产品范围，不把规划能力写成当前能力。A-01 最小入口不包含 Project、Run、Artifact、Repository 或真实数据行为；当前命令以 `README.md` 与 `docs/setup.md` 为准。

## 1. 产品目标

星文智析面向天文科研数据整理与证据核验场景，帮助用户从一个研究目标出发，完成研究任务契约确认、数据获取与清洗、自动论文获取、文献总结、跨文献逻辑推理、证据图谱、结果导出和反馈修订。

MVP 默认主案例为：**系外行星候选体与宿主恒星参数整合**。

产品架构允许扩展到其他天文数据整合任务，但提交版本只承诺已通过真实运行、证据和测试验证的范围。

## 2. 产品形态

产品包含三个连续但职责不同的体验域：

| 体验域             | 作用                                             |
| ------------------ | ------------------------------------------------ |
| Brand Site         | 建立品牌、主案例和可信性认知，提供产品入口       |
| Guided Tour        | 以确定性回放解释完整研究链路，并可启动 Live Run  |
| Research Workspace | 以多项目、科研产物、证据和版本为核心完成研究审查 |

工作台不是通用聊天 Agent。AI 作为上下文协作者存在，中央主区域优先展示数据集、论文、Claim、Relation、ReasoningTrace、Graph 和 Evidence。

## 3. 成功标准

| 维度   | MVP 必达标准                                                            |
| ------ | ----------------------------------------------------------------------- |
| 可理解 | 无现场讲解时，用户可从首页和 Guided Tour 理解产品价值、工作流和证据机制 |
| 可运行 | 公网 Demo 可访问，主案例可使用 Demo Replay 稳定展示并支持 Live Run      |
| 可复现 | 同一主案例可定位到运行参数、来源快照、产物版本和缓存来源                |
| 可溯源 | 数据字段、文献结论、跨文献关系和图谱边均能追踪到 Evidence               |
| 可对照 | 工作台支持最多三面板对照科研产物、推理依据和证据                        |
| 可导出 | 支持 CSV、数据字典、溯源报告、文献与推理关系 JSON 等导出                |
| 可分享 | 可生成隔离、只读的结果分享链接                                          |
| 可提交 | 页面、视频、PDF、源码、API 和测试材料形成一致的作品入口                 |
| 可降级 | WebGL、外部来源或模型失败时，核心信息和任务操作仍可用                   |

## 4. 目标用户

| 用户           | 主要需求                                   | 产品响应                                               |
| -------------- | ------------------------------------------ | ------------------------------------------------------ |
| 天文科研初学者 | 将研究意图转换为明确的数据、论文和证据需求 | 生成可编辑 ResearchContractDraft，确认后展示完整产物链 |
| 科研使用者     | 对照数据、论文、结论和来源，审查结果可靠性 | Research Canvas + Provenance Observatory               |
| 竞赛评审       | 快速判断作品是否真实、完整、可复现         | 品牌入口、Guided Tour、运行来源、Evidence 和版本入口   |
| 开发与复现人员 | 检查架构、接口、数据和测试                 | 技术文档、API、源码、Fixture / HTTP 双通道和复现步骤   |
| 材料制作人员   | 生成一致的截图、视频和技术说明             | 确定性 Demo Replay、稳定视口和可定位版本               |

## 5. 主流程

1. 用户输入自然语言研究意图。
2. 系统解析为可编辑的 `ResearchContractDraft`。
3. 用户创建或选择 `ResearchProject`，确认目标对象、字段、来源范围、论文范围、输出和质量要求，形成不可变 `ResearchContract`。
4. 用户在启动时选择 Demo Replay 或 Live，系统创建 `ResearchRun`；执行方式只记录在 Run/启动状态中。
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

执行方式、产物来源与修订派生关系是三个独立维度，不得写入同一枚举或混为一个状态：

| `execution_mode` | 用途                                  | 约束                           |
| ---------------- | ------------------------------------- | ------------------------------ |
| `demo_replay`    | 首页和 Guided Tour 的确定性主案例回放 | 明确标识，不冒充实时运行       |
| `live`           | 调用真实 API、数据源和模型            | 允许等待、失败、重试和缓存建议 |

| `source_mode` | 含义                     | 约束                                                                  |
| ------------- | ------------------------ | --------------------------------------------------------------------- |
| `fixture`     | 版本化演示数据           | 仅用于 Demo Replay、测试和稳定录制，必须带 scenario 与 schema version |
| `live`        | 本次真实运行产物         | 绑定 Run、SourceSnapshot、时间和参数                                  |
| `cached`      | 可定位的真实历史运行产物 | 展示来源 Run、时间、参数、适用性和实时失败原因                        |

`execution_mode` 只属于 ResearchRun、创建 Run 请求或 Guided Tour 启动状态，不属于 ResearchContract。`demo_replay` 通常读取 `fixture`；`live` 执行可以产出 `live`，或在明确失败后选择 `cached`。手写 Fixture 永远不能标记为 `cached`。

修订由 `derivation_kind=revision` 或 `supersedes_version_id` 非空推导；修订后的产物仍保留实际 `source_mode`。界面可显示 `LIVE · REVISED`，但不得把 `revised` 写回来源枚举。

## 7. 用户与会话

MVP 采用免登录体验：

- Demo Replay 直接可用。
- Live Run 创建隔离临时研究会话。
- 会话具有过期和资源限制。
- 支持生成只读结果链接。
- 暂不实现完整账号、团队空间和企业权限。

## 8. MVP 功能范围

| 模块              | 必须实现                                                   | 暂不承诺                     |
| ----------------- | ---------------------------------------------------------- | ---------------------------- |
| 品牌入口          | 主题、主案例、基础 SEO、静态首屏与视觉降级                 | 内容型大型官网               |
| Guided Tour       | Demo Replay、Live 切换、步骤控制、可跳过                   | 为每个天文方向制作独立故事   |
| Research Contract | 自然语言解析 Draft、结构化编辑、确认不可变 Contract 后执行 | 无约束直接执行任意科研目标   |
| 项目与运行        | 多 ResearchProject、多个 ResearchRun、并行状态             | 完整团队协作和权限体系       |
| 任务编排          | 状态流转、错误、缓存和结果聚合                             | 浏览器直接编排外部 Pipeline  |
| 数据分析          | 真实来源、字段对齐、单位统一、质量和 CSV                   | 任意天文数据格式完全自动处理 |
| 论文获取          | 自动检索、去重、排序、来源和选择依据                       | 全网无限制爬取或绕过付费全文 |
| 文献总结          | 结构化摘要、Evidence 和版本                                | 完全自动论文写作             |
| 跨文献推理        | Claim、Relation、ReasoningTrace、Evidence                  | 无证据多跳科学发现           |
| 学术图谱          | 节点、边、Evidence、Trace 与前端交互                       | 大规模通用知识图谱平台       |
| 科研桌面          | Research Atlas、最多三面板、Observatory、Console           | 无限自由窗口和完整 IDE       |
| 反馈修正          | 对象级反馈、影响范围、追加式版本                           | 原地覆盖历史产物             |
| 分享与导出        | 只读链接、CSV、JSON、报告                                  | 复杂公开协作社区             |

## 9. 页面与工作区范围

本 PRD 只冻结 Brand Site、Guided Tour 与 Research Workspace 三类产品形态及其功能范围。首页叙事、Tour 状态机、页面区域、面板与具体交互只在 [WORKSPACE_UX.md](docs/design/WORKSPACE_UX.md) 定义。

## 10. 视觉与交互要求

产品采用克制的浅色科研视觉，品牌表达不能牺牲正文阅读、无障碍或设备降级。完整品牌、颜色、字体、视觉引擎与动效规则见 [VISUAL_LANGUAGE.md](docs/design/VISUAL_LANGUAGE.md)，完整交互见 [WORKSPACE_UX.md](docs/design/WORKSPACE_UX.md)。

## 11. 质量指标

| 指标               | 定义                                               | MVP 目标 |
| ------------------ | -------------------------------------------------- | -------- |
| 字段覆盖率         | 目标字段中成功获取并对齐的比例                     | >= 80%   |
| 来源完整性         | 结果字段带来源记录的比例                           | 100%     |
| 单位一致性         | 关键数值字段单位统一情况                           | 100%     |
| 论文获取可复现性   | 候选带 Query、来源、时间和选择依据                 | 100%     |
| 文献结构完整度     | 目标、方法、数据、结论、局限覆盖                   | >= 80%   |
| 跨文献关系证据率   | 最终 Relation 绑定 Evidence 和 Trace               | 100%     |
| 图谱证据完整度     | GraphEdge 绑定 Evidence                            | 100%     |
| 证据可达性         | 从关键结果定位 Evidence 所需交互                   | <= 3 次  |
| Guided Tour 完整性 | 默认回放无需外部服务即可完整展示                   | 100%     |
| 运行语义准确性     | execution、source 与 revision 派生关系分别正确标识 | 100%     |
| WebGL 降级         | 不支持 WebGL 时核心内容和操作可用                  | 100%     |
| 可访问性           | 核心流程键盘可用且无严重自动化违规                 | 100%     |

## 12. 作品提交路径

材料提交顺序只在 [docs/handoff/README.md](docs/handoff/README.md) 维护。视频和网页必须使用相同 Demo Replay、版本与事实口径，避免截图、描述和实际系统不一致。

## 13. 验收口径

产品退出标准只在 [docs/product/ACCEPTANCE.md](docs/product/ACCEPTANCE.md) 维护；PR 与发布检查只在 [docs/quality/REVIEW_CHECKLIST.md](docs/quality/REVIEW_CHECKLIST.md) 维护。文档通过不能替代实现、运行和测试证据。
