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
| Markdown/JSON 合并输出 | 由 canonical Artifact 取代 | `PaperSummaryArtifactContent` 与 version-pinned read model |
| 硬编码路径、自由文件写入、完整 prompt/response 日志 | 拒绝 | Project-owned input、受控日志与 immutable ArtifactVersion |
| 无标题时把全文复制到七类 | 拒绝 | 缺失/不确定内容保持为空或进入失败/人工处理，不补写证据 |

## AutoAstro

| 参考能力与证据 | 裁决 | 当前落点 |
| --- | --- | --- |
| `plan_generate.py`、`tools.parse_execution_order` 任务分解与依赖 | 用当前模型替换 | immutable `scientific_tasks` + `compile_run_plan`；模型不能改 Step |
| `cross_match.py` 目录对齐 | 复用更成熟的项目轮子 | `catalog_crossmatch` Adapter 直接调用 `services.data_pipeline.crossmatch` |
| `load_and_analyze_data.py` 数据探索/统计/绘图 | 采用能力，重构边界 | `data_profile`、`statistical_analysis`、`correlation_analysis`、`chart_visualization` |
| `model/self_model/*` 表格分类、回归与时间序列 | 采用能力，官方轮子替换 | `tabular_machine_learning`、`time_series_forecast` + scikit-learn |
| mmpretrain 配置与图像分类脚本 | 采用可验证的任务语义，不复制配置库 | bounded `image_classification` + scikit-learn baseline/evaluation |
| `framework_executor.py` 进度与多阶段执行 | 接入端口，不重复 worker | canonical RunStep 状态、`ScientificStepAdapter`、`ScientificStepPublisher` |
| `code_executor.py`、`error_correction.py` 生成代码/副进程/修复循环 | 拒绝 | fail-closed registry、固定 handler、参数白名单、Attempt 失败语义 |
| 本机路径、共享任务记忆、自由输出文件 | 拒绝 | immutable refs、content-addressed storage、Run-owned provenance |

## MAVIS

| 参考能力与证据 | 裁决 | 当前落点 |
| --- | --- | --- |
| `getData.json` / `local_tools.getRdBySimbad` 的对象与区域查询 | 采用官方实现 | `simbad_lookup` + Astroquery Simbad |
| `getData.json` / `local_tools.getFits` 的 SkyView FITS | 采用官方实现 | `skyview_fits` + Astroquery SkyView；二进制进入内容寻址存储 |
| `skyfield.json` 的目标位置、升落中天、晨昏、月相、季节、月食及合/冲语义 | 采用官方稳定实现 | `ephemeris`、`celestial_events` + Skyfield / bundled DE421；事件区间和输出数受限 |
| `photutils.json` 的 FITS 读取、背景、质心、源检测、分割与孔径测光 | 采用官方实现 | `fits_image_analysis` + Astropy/Photutils；操作、输入大小、二维形状和输出数受限 |
| `wwt_agent.json` 与 `WWTComponent.vue` 的定位、时间、背景、FITS、圆和线 | 完整定向改造 | `wwt_scene`、`WwtSceneVisualizationSpec`、`wwt-session.ts` |
| Vue Chat/Agent 状态和 Django SSE | 不复制应用壳 | 当前 Research Thread/RunEvent/Inspector Query 边界 |
| 动态工具路由概念 | 保留唯一接线点 | Contract allowlist + Registry；模型 Function Calling 不在此模块实现 |
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

该变更不实现或复制以下已有规划边界：queued-to-worker 的真实 Executor、全种类 Artifact Renderer Registry/Thread result block/PaperSummary Renderer、Gaia/IVOA 获取、Qwen Function Calling、产品 Benchmark 与自动 repair。科学模块只提供这些边界可调用或可注册的当前 Contract、Adapter、Publisher 和 domain view。

## 证据等级

- Current Contract、hash、Publisher admission、read integrity、Registry、RunPlan、Fixture/HTTP mapping 与 Workspace component 由自动化测试验证。
- Simbad 与 SkyView 依赖外部服务；没有实际 Live 调用记录时只能报告为 Adapter/contract verified，不能报告为 Live verified。
- WWT 使用官方 WebGL engine；自动化测试覆盖生命周期和场景指令，真实浏览器/WebGL 视觉验收需单独报告。
- Persistent Workflow Executor 完成接线前，科学任务不会被声称已由 Live Run 自动调度。
