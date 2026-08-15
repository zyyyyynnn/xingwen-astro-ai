# Reference Integration Traceability

本文是非规范追踪记录：把本地 Inosum、AutoAstro 与 MAVIS 快照中的可观察能力逐项映射到当前实现、官方替代或明确拒绝项。生产规则以 [Documentation Index](../README.md) 列出的 Authority 为准。

## 采用原则

1. 已有项目深模块能承接时直接调用，不复制第二份算法或状态。
2. 上游已有成熟、可维护的官方 package 时采用 package，不手写复刻或搬运 vendor bundle。
3. 参考源码可安全复用时允许定向改造；路径、状态所有权、Contract、Evidence 和 UI 样式必须进入当前体系。
4. 不保留旧字段、旧命名、旧测试、双写或兼容解析层。
5. “参考中出现”不等于“当前 Live verified”；Fixture、单元测试、Recorded 与 Live 证据分别报告。

## Inosum

| 参考能力与证据 | 裁决 | 当前落点 |
| --- | --- | --- |
| `get_splite_answer` 的七类章节模型 | 采用并类型化 | `app.schemas.paper_summary` 七段 current Schema；生成 JSON Schema/DTO |
| `extract_background`、`extract_methodology`、`extract_dataset`、`extract_experiments_conclusion`、`extract_discussion`、`extract_limitations`、`extract_questions` | 定向改造 | `services.paper_pipeline.summary`、`packages/prompts/paper_summary/prompt.md` |
| `step1_generate_single -> step2_generate_single` 两阶段顺序 | 融入既有论文主链 | 当前 Paper pipeline、Prompt Registry、Publisher 与 Evidence admission |
| Markdown/JSON 合并输出 | 定向改造 | `PaperSummaryArtifactContent` 与固定 immutable ArtifactVersion 的 JSON/Markdown export API；复用 validated read boundary，不写临时路径 |
| 上传论文的 Paper 身份 | 融入现有 Authority | 复用 `services.paper_pipeline.canonicalize.canonical_paper_id`；无书目 ID 时用 ResearchInput source-record identity，不截断 content hash，不猜测 PaperCollection 成员关系 |
| 硬编码路径、自由文件写入、完整 prompt/response 日志 | 拒绝 | Project-owned input、受控日志与 immutable ArtifactVersion |
| 无标题时把全文复制到七类 | 拒绝 | 缺失/不确定内容保持为空或进入失败/人工处理，不补写证据 |

## AutoAstro

| 参考能力与证据 | 裁决 | 当前落点 |
| --- | --- | --- |
| `plan_generate.py`、`tools.parse_execution_order` 任务分解与依赖 | 用当前模型替换 | immutable `scientific_tasks` + `compile_run_plan`；模型不能改 Step |
| `cross_match.py` 目录对齐 | 复用更成熟的项目轮子 | `catalog_crossmatch` Adapter 直接调用 `services.data_pipeline.crossmatch` |
| `load_and_analyze_data.py` 数据探索/统计/绘图 | 采用能力，重构边界 | `data_profile`、`statistical_analysis`、`correlation_analysis`、`chart_visualization`；统计技能包含受控假设检验目录 |
| 聚类、PCA 与异常检测任务语义 | 采用能力，拒绝生成代码 | `clustering_analysis`、`anomaly_detection` + scikit-learn；输出确定性标签、PCA 投影、silhouette 与异常排序 |
| `model/self_model/*` 表格分类、回归与时间序列 | 采用能力，官方轮子替换 | `tabular_machine_learning`、`time_series_classification`、`time_series_forecast` + scikit-learn；包含 holdout、baseline、交叉验证、分类校准和特征重要性；拒绝导入即训练、硬编码 checkpoint 与测试集早停 |
| mmpretrain 配置与图像分类脚本 | 采用可验证的任务语义，不复制配置库 | Project-owned `image_dataset` ZIP + `labels.json`，Pillow 固定预处理，bounded `image_classification` + scikit-learn baseline/evaluation + ONNX；拒绝任意 config、路径与 JSON 像素张量 |
| `framework_executor.py` 进度与多阶段执行 | 接入端口，不重复 worker | canonical RunStep 状态、`ScientificStepAdapter`、`ScientificStepPublisher` |
| `code_executor.py`、`error_correction.py` 生成代码/副进程/修复循环 | 拒绝 | fail-closed registry、固定 handler、参数白名单、Attempt 失败语义 |
| 本机路径、共享任务记忆、自由输出文件 | 拒绝 | immutable refs、content-addressed storage、Run-owned provenance |

## MAVIS

| 参考能力与证据 | 裁决 | 当前落点 |
| --- | --- | --- |
| `getData.json` / `local_tools.getRdBySimbad` 的对象与区域查询 | 采用官方实现 | `simbad_lookup` + Astroquery Simbad |
| `getData.json` / `local_tools.getFits` 的 SkyView FITS | 采用官方实现 | `skyview_fits` + Astroquery SkyView；二进制进入内容寻址存储 |
| `skyfield.json` 的目标位置、升落中天、晨昏、月相、季节、月食及合/冲语义 | 采用官方稳定实现 | `ephemeris`、`celestial_events` + Skyfield / bundled DE421；事件区间和输出数受限 |
| `local_tools.py` 的天体半径、金星大距、凌日与掩星 | 定向迁移并修正算法 | 受控半径表；Skyfield 视分离极值、视半径与前后景距离共同判定，不沿用“黄经合相即重叠”或“以大距冒充凌日” |
| `getLatLongByCityName` 城市坐标 | 保留用户能力、替换不安全渠道 | 固定 HTTPS allowlist 的 Nominatim；限制超时、响应体、重定向和坐标；Nominatim 与 JPL 各自形成独立 SourceSnapshot，不复制高德密钥 |
| 参考案例中需要的受控目录锥形查询 | 采用 CDS 官方 TAPVizieR，增加第二个公开目录 | `vizier_tap`；固定 `https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync`，Manifest 目前只开放 Gaia DR3 `I/355/gaiadr3` 与 2MASS PSC `II/246/out` 的 allowlist 字段、ICRS cone、CSV/VOTable 与预算门禁；provider URI/revision/ETag/raw SHA-256 进入 SourceSnapshot |
| `photutils.json` 的 FITS 读取、背景、质心、源检测、分割与孔径测光 | 采用官方实现 | `fits_image_analysis` + Astropy/Photutils；操作、输入大小、二维形状和输出数受限 |
| `wwt_agent.json` 与 `WWTComponent.vue` 的坐标定位、固定时间、背景、基础 FITS、圆、线和标签 | 定向改造；Scene Contract 与标准 Renderer 已接线 | `wwt_scene`、`WwtSceneVisualizationSpec`、`wwt-session.ts` |
| `wwt_agent1/2/4.json` 的 roll、暂停/倍率播放、当前时间/视图读取、observer/本地地平、多网格、太阳系目标与覆盖层、星座、岁差、point、foreground | Contract、官方 Engine 与标准 Renderer 已核验；尚缺真实浏览器 WebGL 人工验收，不计 Live verified | `WwtSceneVisualizationSpec`、`WWT_CAPABILITY_MATRIX`；受控意图的 Renderer 状态为 `supported` |
| `wwt_agent2.json` 的 table layer 与扩展 FITS 显示参数 | 采用内容寻址强类型替代；禁止路径/URL；Renderer 只通过 content hash 加载 | `WwtTableLayer`、`WwtFitsLayer`、SourceSnapshot/ContentStorage |
| MAVIS 自动逐步跳转 | 采用有界声明式 tour；不复制浏览器定时器脚本 | `WwtSceneStep`、最多 512 个稳定步骤；标准 Renderer 执行受控 tour |
| 用户保存当前 WWT 画面 | 保留用户能力，替换自动轮询/上传 | ready 画布上的显式 PNG 下载；生成中、空画布、tainted WebGL 均有明确状态，不写服务端或 Artifact |
| `WWTComponent.vue` 的私有 WebSocket、100 ms 状态轮询、截图轮询/自动上传 | 拒绝 | 无自由命令面；Spec 只声明 readback 意图并强制 `text_alternative` |
| Vue Chat/Agent 状态和 Django SSE | 不复制应用壳 | 当前 Research Thread/RunEvent/Inspector Query 边界 |
| 动态工具路由概念 | 保留唯一接线点 | Contract allowlist + Registry；`ResearchStepAgent` 只确认当前冻结 RunStep 的固定工具，不能增删任务或替换技能；成功、provider 失败与校验拒绝都进入唯一 ProducerExecution ledger |
| `mutil_agent*.py` 生成代码、Jupyter 远程执行与递归修复 | 拒绝 | 无任意代码、Shell、notebook 或自由 WebSocket 命令执行面 |
| `utils.py`、Django 配置中的凭据/内网地址与绝对路径 | 拒绝且不得复制 | 环境配置、Project ownership、内容 hash 与安全日志规则 |
| `wwt-tutorial` 内 vendor bundle | 用官方 package 替换 | `@wwtelescope/engine*` 按需动态 import |

## 当前系统交接

```text
ResearchContract.scientific_tasks
  -> deterministic RunPlan
  -> Persistent Workflow Executor owned invocation seam
  -> ScientificStepAdapter
  -> ScientificSkillRegistry
  -> canonical Artifact candidate
  -> ScientificStepPublisher
  -> ArtifactVersion + ProducerExecution + Evidence + SourceSnapshot
  -> ScientificArtifactReadService
  -> Repository/Query
  -> token-based scientific domain view / WWT singleton session
```

当前生产链已接入 queued-to-worker 的 `ResearchRunWorker`、Qwen 受控工具选择、Artifact Renderer Registry、Thread/Inspector/fullscreen 展示，以及文献、数据和科学产物的 Publisher/read 闭环。缺失输入通过持久化 Human Checkpoint 与幂等 resume/retry/cancel 派生 Run 处理。仍在交付中的平台能力与治理项必须按代码和验收证据单独报告，不能由本追踪表提前宣称完成。

## 证据等级

- Current Contract、hash、Publisher admission、read integrity、Registry、RunPlan、Fixture/HTTP mapping 与 Workspace component 由自动化测试验证。
- Crossref、Nominatim/JPL、Gaia DR3 TAP、CDS TAPVizieR、SDSS DR17、MAST TESS 已有本轮直接 Live 调用记录，但尚未因此把任一 MAVIS 案例提升为逐例 `implemented_verified`；Simbad 与 SkyView 没有实际 Live 记录时仍只能报告为 Adapter/contract verified。
- WWT 使用官方 WebGL engine；自动化测试覆盖后端完整场景 Contract、Skill、hash、来源引用、生成契约、标准 Renderer 消费、singleton 生命周期与 capability matrix。受控展示能力当前为 `renderer=supported`，但仍必须完成真实浏览器/WebGL 视觉验收，不能把 Contract/Engine/组件测试冒充逐例 Live 运行证据。
- Worker/Publisher 的 PostgreSQL 测试不是外部服务 Live 证据；只有终态 Run、Attempt、ArtifactVersion、Evidence、SourceSnapshot 与浏览器渲染同时成立时才算完整 Live 闭环。
