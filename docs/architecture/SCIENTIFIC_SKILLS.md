# Bounded Scientific Skills

| 元数据 | 值 |
| --- | --- |
| Authority | 受控科学技能、科学分析产物、资源预算与工具调用边界 |

本文定义星文智析如何把天文数据分析、天体服务、科学图像处理、机器学习与交互式天图能力接入唯一 ResearchRun 主链。Workflow、Publisher、Evidence、Version 与 Workspace 的既有 Authority 保持不变。

## 1. 产品能力

系统支持以下受控能力族：

| 能力族 | Scientific Skill | 主要输出 |
| --- | --- | --- |
| 数据探索 | `data_profile`、`statistical_analysis`、`correlation_analysis`、`clustering_analysis`、`anomaly_detection`、`chart_visualization` | AnalysisReport / Visualization |
| 天体对齐 | `catalog_crossmatch`、`simbad_lookup` | Dataset / SourceCollection / AnalysisReport |
| 天文观测 | `skyview_fits`、`ephemeris`、`celestial_events`、`gaia_cone_search`、`vizier_tap` | SourceCollection / AnalysisReport / Visualization |
| 光谱与时域观测 | `spectrum_acquisition`、`light_curve_acquisition`、`spectrum_analysis`、`light_curve_analysis` | Spectrum / LightCurve / AnalysisReport |
| 科学图像 | `fits_image_analysis` | AnalysisReport / Visualization |
| 科学建模 | `tabular_machine_learning`、`time_series_classification`、`time_series_forecast`、`image_classification` | ModelEvaluation / ModelArtifact |
| 天图交互 | `wwt_scene` | Visualization |

技能目录是版本化 Authority。Research assistant 只能选择当前 Case、Contract、RunStep 与部署能力共同允许的技能。

## 2. 唯一执行链

```text
confirmed ResearchContract
  -> deterministic frozen task-owned RunPlan
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

`ScientificStepAdapter` 每次只执行当前 RunStep 绑定的一个 frozen task，并把解析后的 ArtifactVersion / ResearchInput 和 Registry result 组装为 canonical candidate；它记录 duration、upstream Evidence 与二进制内容引用。`ScientificStepPublisher` 同时校验 RunStep、Contract 与输出的 task/skill identity，再通过唯一 Publisher 事务发布该 task 的完整输出闭包。

Project-owned FITS ResearchInput 只接受 `application/fits` magic/MIME/扩展名一致的上传；输入解析器固定绑定 `fits_image_analysis`，以受限 base64 传入隔离进程，不允许把普通图片、任意二进制或本机路径伪装成 FITS。

表格型 Skill 可从 Project-owned CSV、XLSX、Parquet 或 JSON ResearchInput 读取至多 10,000 行、256 字段的 scalar rows。XLSX 必须是单工作表、无宏/外链且通过 ZIP bomb 门禁；Parquet 必须通过 footer、row group 解码体积与 Arrow primitive type 门禁。解析器复用 `openpyxl` 与 `pyarrow`，不自行实现 OOXML/Parquet reader。

`image_classification` 只接受 Project-owned `image_dataset` ResearchInput，不再接受用户手写 JSON 像素张量。ZIP 根级 `labels.json` 固定 `schema_version: 1.0.0` 与 `images[{path,label}]`；图片只允许 PNG、JPEG、WebP，manifest 与 archive 成员必须完全闭合，且拒绝加密、符号链接、路径穿越、大小写碰撞及超预算成员、解压体积、压缩比、单图尺寸、总像素、类别或样本数。服务端复用 Pillow 执行 EXIF transpose、RGB 转换、32×32 contain-pad 双线性缩放与 `[0,1]` 归一化。ModelEvaluation 与 ModelArtifact 固定记录 manifest 版本、预处理契约、image shape、类别索引和样本数；训练输入引用按需物化的 immutable SourceSnapshot，继续由既有评估与 ONNX 发布链承载，不伪造 Dataset 或 SourceCollection。普通 `image` 只保留为展示或未来推理输入。

`statistical_analysis` 除描述统计外，只接受固定目录中的 t 检验、Mann–Whitney U、单因素 ANOVA、卡方独立性和 Shapiro–Wilk 检验；每项记录样本量、显著性水平、统计量、p 值、判定、假设说明和 SciPy 版本。`clustering_analysis` 与 `anomaly_detection` 分别以 KMeans/DBSCAN + PCA/silhouette、IsolationForest/稳健 Z 分数承接聚类、降维和异常排序。模型训练不以单次 holdout 伪装完整评估：表格分类/回归与等长序列分类同时输出 baseline、交叉验证均值/标准差、分类校准损失和归一化特征重要性。`time_series_classification` 把每行视为一个独立等长序列，`series_fields` 冻结观测顺序；不接受参考实现的任意 PyTorch 模型类型、文件路径或训练循环参数。

第三方 SDK、网络协议、文件格式、数值库和模型实现只存在于 Registry 内部 Adapter，不泄漏到 Workflow、Router 或前端。

生产观测获取采用三个固定边界：

- `gaia_cone_search` 只访问 ESA Gaia Archive 的 Gaia DR3 TAP sync endpoint；调用方只能选择 allowlist 字段、ICRS 圆心、半径、格式和有界行数，不能提交 ADQL 或 URL。CSV 与 VOTable 均执行响应字节、列、行、标识符和有限数值校验。
- `vizier_tap` 只访问 CDS 的固定 HTTPS `TAPVizieR/tap/sync` endpoint；当前 Manifest 只开放 VizieR `I/355/gaiadr3`/`gaiadr3` 与 `II/246/out`/2MASS PSC 两个目录/表及其字段别名。每个 Manifest 明确绑定 ICRS RA/Dec 列、稳定排序列、字段类型和单位（Gaia 的 `RA_ICRS/DE_ICRS/Source` 与 2MASS 的 `RAJ2000/DEJ2000/2MASS` 不混用）。调用方只能选择 Manifest、ICRS 圆心、半径（`(0,5]` 度）、格式与有界行数，查询由一个固定 cone 模板生成，不接受任意 ADQL、表名、URL、JOIN 或谓词。CSV 与 VOTable 均执行响应字节、列、行、标识符和有限数值校验。
- `spectrum_acquisition` 只按 `plate + MJD + fiber` 读取 SDSS DR17 官方 SAS 的单目标光谱 FITS；Adapter 校验固定 HDU/列、掩码、逆方差和行数，然后把类型化波长/流量/不确定度行交给现有 `spectrum_analysis` 算法，不复制光谱分析实现。
- `light_curve_acquisition` 只读取 MAST mission-produced TESS LC FITS。调用方提供相互匹配的 TIC、sector 与受控产品文件名；下载固定从 MAST 起始，最多允许一跳到 `stpubdata.s3.us-east-1.amazonaws.com` 的 TESS 官方公开存储。有效 TIME、flux、uncertainty、QUALITY 行交给现有 `light_curve_analysis`。

三个 Adapter 均禁止任意 URL、跨 allowlist 重定向和无限响应，并把 provider、实际响应 URI、Adapter revision、可用的 ETag 与原始响应 SHA-256 交给 SourceSnapshot recorder。Recorded MockTransport 只证明适配器与契约，不能标为 Live。

VizieR 协议依据是 CDS 的 [VizieR catalogue service](https://vizier.cds.unistra.fr/vizier/index.htx) 与 [TAPVizieR 官方查询入口](https://tapvizier.cds.unistra.fr/TAPVizieR/tap)；目录字段与单位来自 [2MASS PSC II/246 官方 ReadMe](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/II/246?format=html&tex=true)。前者明确 VizieR 表通过 VO TAP/ADQL 查询，后者是当前固定 provider endpoint 的服务根。

`vizier_tap` 的单次结果先以 `AnalysisReport` 的 `catalog` result block 发布，并保留其 VizieR SourceSnapshot。它不会伪造 Dataset 或 SourceCollection：当前 `SourceCollectionArtifactCandidate` 的强契约要求两个独立 source/snapshot、crossmatch 结果、对齐/冲突注册表和 mapping/conversion manifest；单个 VizieR cone 结果不足以满足这些字段。只有在同一任务显式提供第二个独立来源并进入既有 crossmatch pipeline 后，才允许由该 pipeline 生成 SourceCollection。

采用使用 replace-not-layer 原则：当前 Contract、Schema、命名和测试在同一变更中整体迁移，不增加旧字段别名、双写、旧版本解析器、兼容 Renderer 或历史行为测试。可复用能力优先调用仓库现有深模块或官方稳定 package/SDK；仅在上游没有合格 Interface 且许可证允许时采用极小范围 vendored source，不手写复刻成熟外部算法。

天文观测事件由 `celestial_events` 统一承载。除月相、季节、月食、日食和合冲外，当前边界还支持 `venus_elongations`（金星东/西大距）、`transits`（水星或金星严格凌日）和 `occultations`（月掩行星）。凌日与掩星使用 Skyfield 有界的最小视分离搜索，再以受控天体半径和前景距离判定盘面重叠；不把仅有黄经合相误报为凌日或掩星。

需要观测地点的 `ephemeris` 与 `celestial_events` 请求必须二选一提供：`latitude_degrees` + `longitude_degrees`（可选 `elevation_meters`），或 `location_name`。城市名只通过 HTTPS `nominatim.openstreetmap.org` 的固定 allowlist 解析，禁止用户提供 URL、重定向和无限响应；结果只保留有界的 `resolved_location` 事实。使用城市名时，JPL DE421 与 Nominatim 各自形成独立 SourceSnapshot，并共同进入 Artifact 来源闭包。

## 4. Contract 与授权

ResearchContract 使用 `scientific_tasks` 保存可执行任务，每项由稳定 `task_id`、注册的
`skill_id`、受约束 `parameters` 与显式 `input_refs` 组成。规则如下：

1. 空列表表示不执行额外科学技能；不得根据自然语言隐式扩大权限。
2. 每个 skill 必须存在于服务端 Manifest-backed Research Catalog。
3. RunPlan 只根据已确认 Contract 和 requested ArtifactKind 编译。
4. `ResearchStepAgent` 的 Function Calling 只确认当前冻结 RunStep 的固定工具与公开分析；它不能选择另一 skill、修改参数或改变 Step 图。
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

`wwt_scene` 的当前声明式边界按职责分组，而不是保存浏览器命令序列：

- `view` 是坐标相机或受控太阳系目标的判别联合，包含视场、roll 和有限过渡时长；
- `time` 只能是系统时钟、固定暂停时间或带非零有限倍率的播放时间；
- `observer` 保存经纬度、高程与本地地平模式；使用地平网格时必须显式给出 observer；
- `coordinate_grids` 可以同时声明赤道、银道、黄道和地平网格及标签；
- `solar_system`、`constellations` 与 `precession_chart` 只保存 allowlist 开关；
- FITS 和 table layer 只保存 Project-owned `content_ref`、`content_hash` 与 `source_snapshot_id`，禁止路径或 URL；table layer 的球面/笛卡尔字段、单位、时间衰减与视觉编码均为强类型；
- `tour_steps` 是最多 512 个带稳定 ID 的坐标或跟踪目标步骤，不是定时器脚本；
- `readbacks` 只声明界面应读取的中心坐标、视场、roll 或当前时间；运行结果不得通过轮询截图推断这些状态；
- `text_alternative` 是必填的可访问文本事实，WebGL 不可用或能力未实现时仍须显示，不得把静默忽略字段当成降级。

能力矩阵以 `services/scientific_skills/wwt_capabilities.py` 为机器可读事实源。`engine` 表示仓库锁定的官方 WWT 包是否具有对应原语；`renderer` 表示当前标准 Renderer 是否真实消费该意图。任何 `renderer=unsupported` 的字段在 UI 接线前都不能作为 Live 闭环证据。

| 能力 | Contract | Engine | Renderer |
| --- | --- | --- | --- |
| 坐标定位、背景、系统时钟、固定时间、单一坐标网格 | supported | supported | unsupported |
| 圆、线、标签 annotation 与基础 FITS layer | supported | supported | unsupported |
| point annotation、annotation 样式、camera roll | supported | supported | unsupported |
| 前景、FITS stretch/colormap/range、table layer | supported | supported | unsupported |
| observer、本地地平、多网格、网格标签 | supported | supported | unsupported |
| 暂停/倍率播放、当前时间与视图 readback | supported | supported | unsupported |
| 太阳系目标跟踪、太阳系覆盖层、tour steps | supported | supported | unsupported |
| 星座边界/连线/图片/标签、岁差图 | supported | supported | unsupported |
| 必填文本替代 | supported | unsupported | unsupported |
| 自由 WebSocket 命令、自动截图上传 | unsupported | unsupported | unsupported |
| 截图轮询、未受控远端图层 URL | unsupported | supported | unsupported |

上述边界与替代方案见 [WWT declarative scene boundary](decisions/wwt-declarative-scene-boundary.md)。

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

以下值是 canonical phase，而不是把同类任务合并执行的共享 Step：

```text
acquiring_observations
analyzing_data
training_models
building_visualizations
```

phase 相对顺序固定为：

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

RunPlan 只冻结当前 Contract 请求产物所需的最小闭包。每个 `scientific_tasks` 项展开为独立 RunStep，并持久绑定 `task_id`、`skill_id`、所属 phase 与显式前置 Step key；同一 phase 可以有多个连续 task-owned RunStep，但每个 Step 具有独立 Attempt、retry、cancel、预算和原子输出闭包。没有 Skill、Artifact mapping 或部署 capability 时创建 Run 必须 fail closed。

该选择的背景与后果见 [Scientific task-owned RunStep decision](decisions/scientific-task-owned-run-steps.md)。

## 7. 安全与资源边界

- 禁止执行模型生成的 Python、Shell、SQL、JavaScript 或 notebook cell。
- 禁止 `eval`、`exec`、`runpy`、动态 import 和用户提供模块路径。
- 外部 host、catalog、survey、模型与算法全部 allowlist。
- 网络请求、下载大小、FITS/image 像素、表格行列、训练样本、模型复杂度与输出数量均有显式限制；Adapter 和上游 SDK 执行超时会使当前 Attempt 失败。
- 每次科学技能由 `ScientificSkillProcessExecutor` 在独立子进程与 Attempt-owned 临时目录执行；超时或取消先 terminate、再 kill，并回收进程与目录。线程级超时不作为硬终止保证。
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

当前远端观测来源采用 ESA Gaia Archive DR3、SDSS DR17 Science Archive Server、NASA/STScI MAST TESS 产品。版本策略是固定数据发布/产品族与 Adapter revision，定期以 opt-in Live smoke 核对 schema；上游未提供 ETag 时保持 `source_version_or_etag=null`，不得用本地时间或 Adapter version 伪造来源版本。一次科学结果涉及多个物理来源时，每个来源分别形成 SourceSnapshot；例如 `location_name` 星历分别记录 JPL DE421 与 Nominatim，不生成 composite SourceSnapshot。

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
- queued-to-worker 调度、模型固定工具调用、全种类 Renderer Registry 与产品 Benchmark 分别在其唯一能力边界接线；验收必须核对终态 Run/Attempt、版本化 Artifact/Evidence/SourceSnapshot 与浏览器实际渲染，不能由中间状态或 fixture 代替。

普通 CI 运行 Recorded/MockTransport 测试。公开只读 Live provider smoke 必须显式启用，且只证明 provider acquisition，不证明 terminal ResearchRun、Artifact 发布或 UI 闭环：

```powershell
$env:PYTHONPATH = "apps/api/src;."
$env:XINGWEN_RUN_LIVE_ASTRO_ACQUISITION_TESTS = "1"
uv run --project apps/api pytest -q -m live apps/api/tests/test_astro_acquisition.py
```
