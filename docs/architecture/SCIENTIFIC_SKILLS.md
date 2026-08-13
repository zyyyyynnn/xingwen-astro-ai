# Bounded Scientific Skills

| 元数据 | 值 |
| --- | --- |
| Authority | 受控科学技能、科学分析产物、资源预算与工具调用边界 |

本文定义星文智析如何把天文数据分析、天体服务、科学图像处理、机器学习与交互式天图能力接入唯一 ResearchRun 主链。Workflow、Publisher、Evidence、Version 与 Workspace 的既有 Authority 保持不变。

## 1. 产品能力

系统支持以下受控能力族：

| 能力族 | Scientific Skill | 主要输出 |
| --- | --- | --- |
| 数据探索 | `data_profile`、`statistical_analysis`、`correlation_analysis`、`chart_visualization` | AnalysisReport / Visualization |
| 天体对齐 | `catalog_crossmatch`、`simbad_lookup` | Dataset / SourceCollection / AnalysisReport |
| 天文观测 | `skyview_fits`、`ephemeris`、`celestial_events` | SourceCollection / AnalysisReport / Visualization |
| 科学图像 | `fits_image_analysis` | AnalysisReport / Visualization |
| 科学建模 | `tabular_machine_learning`、`time_series_forecast`、`image_classification` | ModelEvaluation / Visualization |
| 天图交互 | `wwt_scene` | Visualization |

技能目录是版本化 Authority。Research assistant 只能选择当前 Case、Contract、RunStep 与部署能力共同允许的技能。

## 2. 唯一执行链

```text
confirmed ResearchContract
  -> deterministic frozen RunPlan
  -> Workflow Step Adapter invocation port
  -> ScientificStepAdapter
  -> ScientificSkillRegistry
  -> typed ScientificSkillResult
  -> scientific Artifact admission
  -> Publisher
  -> ArtifactVersion / Evidence / SourceSnapshot
```

Scientific Skill 不是 Agent、Workflow、Publisher 或插件运行时。模型不得增加、删除、重排 Step，也不得直接发布 ArtifactVersion。
Persistent Workflow Executor 负责 lease、Attempt、retry、cancel 与 Step 调度；本模块只提供它可调用的 Step Adapter、输入解析和发布端口，不创建第二套 worker 或状态机。

## 3. 深模块与 Interface

外部 seam 只有一个：

```text
ScientificSkillRegistry.execute(ScientificSkillRequest)
  -> ScientificSkillResult
```

`ScientificSkillRequest` 固定：

- Project、Run 与 request identity；
- skill id 与 skill revision；
- 已完成白名单与形状校验的参数；
- SourceSnapshot identity 与 content hash；
- resource budget。

`ScientificSkillResult` 固定：

- stable status：`completed | partial | unsupported`；执行异常由 Workflow Attempt 失败语义承接；
- bounded result；
- input/output hash；
- skill revision 与 SourceSnapshot closure；
- warnings。

`ScientificStepAdapter` 负责把 frozen task、解析后的 ArtifactVersion / ResearchInput 和 Registry result 组装为 canonical candidate，并记录 duration、upstream Evidence 与二进制内容引用；`ScientificStepPublisher` 仍通过唯一 Publisher 事务发布。

第三方 SDK、网络协议、文件格式、数值库和模型实现只存在于 Registry 内部 Adapter，不泄漏到 Workflow、Router 或前端。

采用使用 replace-not-layer 原则：当前 Contract、Schema、命名和测试在同一变更中整体迁移，不增加旧字段别名、双写、旧版本解析器、兼容 Renderer 或历史行为测试。可复用能力优先调用仓库现有深模块或官方稳定 package/SDK；仅在上游没有合格 Interface 且许可证允许时采用极小范围 vendored source，不手写复刻成熟外部算法。

## 4. Contract 与授权

ResearchContract 使用 `scientific_tasks` 保存可执行任务，每项由稳定 `task_id`、注册的
`skill_id`、受约束 `parameters` 与显式 `input_refs` 组成。规则如下：

1. 空列表表示不执行额外科学技能；不得根据自然语言隐式扩大权限。
2. 每个 skill 必须存在于服务端 Manifest-backed Research Catalog。
3. RunPlan 只根据已确认 Contract 和 requested ArtifactKind 编译。
4. 后续 Function Calling 接线只能在当前 RunStep 的 capability allowlist 内选择已授权 skill；本模块不实现模型 Function Calling。
5. Tool args 必须通过 frozen Contract、运行时参数读取器和对应 Pydantic Artifact Schema 后才能执行。
6. 任何 tool result 都只是 observation/candidate，不自动成为 accepted scientific fact。

## 5. Artifact

### 5.1 AnalysisReport

`analysis_report` 保存：

- 研究目标与分析范围；
- 数据画像、统计指标、关系和异常；
- Evidence-backed findings；
- 使用的技能、输入版本和参数；
- 局限、警告与 human-required 项；
- 可关联 Visualization 与 ModelEvaluation 版本。

### 5.2 Visualization

`visualization` 保存可复现的声明式 VisualizationSpec，而不是可执行脚本：

- `chart`：系列、坐标轴、编码、单位和数据引用；
- `image`：FITS/image layer、stretch、colormap、标注和区域；
- `wwt_scene`：背景、视场、时间、坐标、图层与 annotation；
- `model_diagnostic`：指标、混淆矩阵、残差或预测对照。

Renderer 不执行 Python，不从任意 URL 加载数据。外部资源必须先成为当前 Project-owned ResearchInput、SourceSnapshot 或 ArtifactVersion。

### 5.3 ModelEvaluation

`model_evaluation` 保存：

- task kind、算法与版本；
- train/validation/test split identity；
- feature/target manifest；
- metrics、baseline 与 diagnostics；
- model artifact reference；
- resource usage、limitations 与 reproducibility metadata。

模型权重或大型二进制由 content-addressed storage 保存，Artifact 内容只保存安全引用和 hash。

## 6. RunStep

新增 canonical steps：

```text
acquiring_observations
analyzing_data
training_models
building_visualizations
```

顺序固定为：

```text
planning
-> fetching_data
-> cleaning_data
-> acquiring_observations
-> analyzing_data
-> training_models
-> building_visualizations
-> searching_papers
-> summarizing_papers
-> reasoning_literature
-> building_graph
```

RunPlan 只冻结当前 Contract 请求产物所需的最小闭包。没有 Skill、Artifact mapping 或部署 capability 时创建 Run 必须 fail closed。

## 7. 安全与资源边界

- 禁止执行模型生成的 Python、Shell、SQL、JavaScript 或 notebook cell。
- 禁止 `eval`、`exec`、`runpy`、动态 import 和用户提供模块路径。
- 外部 host、catalog、survey、模型与算法全部 allowlist。
- 网络请求、下载大小、FITS/image 像素、表格行列、训练样本、模型复杂度与输出数量均有显式限制；Adapter 和上游 SDK 执行超时会使当前 Attempt 失败。
- Python 线程无法被安全强杀；进程级 CPU/GPU、内存、磁盘和硬终止必须由 Persistent Workflow Executor 的隔离执行单元落实，本模块不伪造该保证。
- 每次执行使用 Run/Attempt-owned 隔离目录；不得复用或删除共享输出目录。
- 日志不保存凭据、受限全文、原始模型响应、完整上传内容或本机路径。
- 不可安全恢复的歧义进入 `partial | unsupported | human_required`，不得猜值或伪造成功。

## 8. 第三方采用

每个生产 Adapter 必须记录：

- upstream repository/package；
- release/revision；
- software/model/data license；
- adopted interface；
- dependency and runtime constraints；
- upgrade strategy；
- Fixture、Recorded 与 Live 验证证据。

当前实现优先调用仓库既有交叉匹配深模块，以及 Astropy、Astroquery、Photutils、scikit-learn、Skyfield、Skyfield Data 和 WorldWide Telescope 官方包；第三方采用与参考能力映射见 [Reference Integration Traceability](../references/INTEGRATION_TRACEABILITY.md)。

## 9. 前端

- 当前科学 Artifact domain view 只消费 version-pinned Domain/ViewModel，不解析 raw provider payload。
- WWT 作为 `visualization` 的按需重型 Renderer 动态加载，不成为第二套 Workspace 或 WebSocket 运行时。
- 样式只消费 `@xingwen/design-tokens` 与 `@xingwen/ui` 公开 Token/primitive。
- Tool Execution 与 Deliverable 分离；运行事件显示技能、状态和公开摘要，完整结果打开对应 Artifact。

全种类 Artifact Renderer Registry、Research Thread result block、PaperSummary Renderer 与 Inspector 全屏机制由前端统一呈现基础负责；本模块只提供可注册的科学 domain view，不复制该基础设施。

## 10. 失败语义

| 失败 | 结果 |
| --- | --- |
| 参数不合法或未授权 | 执行前拒绝 |
| 上游超时/限流 | retryable failure，受 Attempt 预算约束 |
| 外部 schema drift | partial 或 failed，保留 SourceSnapshot |
| 科学歧义 | human-required，不选择 winner |
| 资源超限 | failed，不发布部分伪成功 Artifact |
| Renderer capability 缺失 | explicit unsupported，不回退 JSON dump |
| 权重/图像/文件不可用 | partial 或 source unavailable |

## 11. 验收

- 每个生产 Skill 至少有 deterministic contract test 和关键 failure test；外部网络 Skill 另需 Recorded 或 Live integration evidence 才能标记为 Live verified。
- 相同 frozen input、configuration 和 dependency revision 产生稳定 semantic identity/hash。
- AnalysisReport、Visualization、ModelEvaluation 均通过 Publisher admission，并可由科学 Artifact read boundary 校验 Evidence、Producer 与内容哈希。
- WWT 单例生命周期、场景切换、时间、FITS 内容授权与组件卸载必须有自动化回归测试。
- 实际 queued-to-worker 调度、模型 Function Calling、全种类 Renderer 注册、Gaia/IVOA 获取和产品 Benchmark 分别在其唯一既有能力边界中接线；本模块不得抢占或伪造这些闭环。
