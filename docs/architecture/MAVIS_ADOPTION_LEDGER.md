# MAVIS Benchmark Adoption Ledger

| 元数据 | 值 |
| --- | --- |
| Authority | MAVIS 160 例迁移与受控科学技能集成台账规范 |
| Source Authority | [mavis_adoption_ledger.json](../../services/reference_integration/mavis_adoption_ledger.json) |
| Scope | 参考项目集成、受控能力映射、旧运行机制拒绝与 Live 验收门禁 |

本文档是星文智析为参考项目 MAVIS（Multi-Agent Visual Interaction System for Astronomy）160 个基准测试案例建立的架构迁移与治理台账说明。机器可读唯一事实源为 [mavis_adoption_ledger.json](../../services/reference_integration/mavis_adoption_ledger.json)。

---

## 1. 核心结论与覆盖总览

1. **160 例完整建账，无一遗漏**：参考项目 `mavis/data/task_benchmark` 下全部 160 个 `divide_task_converted.json` 及其保留的案例代码已逐例解析；源 JSON 均核验 SHA-256 摘要，代码调用面用于校正工具声明遗漏，并收录入机器可读台账。
2. **迁移契约并非 Live 成功证据**：本台账是**迁移范围与验收契约（Migration & Acceptance Contract）**。当前仓库中没有逐例执行的真实证据，因此 **0 个案例标为 `implemented_verified`**。
3. **状态分布**：
   - `implemented_unverified`（160 例）：受控 Contract、Skill、Publisher 与标准 Renderer 已有对应实现，但尚无逐例终态 Live 与人工视觉证据。
   - `planned`（0 例）：台账内已识别的功能缺口均已有受控实现入口；这不代表已经完成 Live 验证。
   - `excluded`（0 例）：业务功能均得到受控承接，无整体废弃案例。
   - `implemented_verified`（0 例）：严禁在缺乏端到端 Live 证据时声称已验证。

机器台账中的 `wwt_capability_matrix` 分别记录 Contract、锁定官方 Engine 与当前标准 Renderer 状态。某项只有 Contract/Engine 为 `supported` 而 Renderer 为 `unsupported` 时，不得据此提升案例状态。

---

## 2. 能力矩阵与模块映射

| 能力族 (Capability Family) | 案例数 | 当前状态 | 目标模块与代码表面 (Target Xingwen Surfaces) | 主要产物与 Schema |
| --- | --- | --- | --- | --- |
| `ephemeris` | 67 | 67 `implemented_unverified` | `services/scientific_skills/astronomy.py:calculate_ephemeris` | `AnalysisReport`, `ephemeris_coordinates` |
| `wwt_navigation` | 100 | 100 `implemented_unverified` | `services/scientific_skills/astronomy.py:build_wwt_scene`<br>`apps/workspace/src/components/wwt-session.ts` | `WwtSceneVisualizationSpec` |
| `wwt_time` | 65 | 65 `implemented_unverified` | `services/scientific_skills/astronomy.py:build_wwt_scene` | `WwtTimeControl`, `WwtSceneStep` |
| `simbad` | 60 | 60 `implemented_unverified` | `services/scientific_skills/astronomy.py:query_simbad` | `SourceCollection`, `simbad_source_collection` |
| `skyview_fits` | 42 | 42 `implemented_unverified` | `services/scientific_skills/astronomy.py:retrieve_skyview_fits` | `SourceSnapshot`, `fits_image_artifact` |
| `wwt_annotation` | 39 | 39 `implemented_unverified` | `services/scientific_skills/astronomy.py:build_wwt_scene` | `WwtAnnotation`, `WwtSceneVisualizationSpec` |
| `fits_image_analysis` | 38 | 38 `implemented_unverified` | `services/scientific_skills/astronomy.py:analyze_fits_image` | `AnalysisReport`, `fits_photometry_report` |
| `conjunction` | 37 | 37 `implemented_unverified` | `services/scientific_skills/astronomy.py:find_celestial_events` | `AnalysisReport`, `celestial_events_list` |
| `wwt_solar_system` | 36 | 36 `implemented_unverified` | `services/scientific_skills/astronomy.py:build_wwt_scene`；`apps/workspace/src/components/wwt-session.ts` | `WwtTrackedObjectView`, `WwtSolarSystemOptions` |
| `coordinate_resolution` | 32 | 32 `implemented_unverified` | `services/scientific_skills/astronomy.py:query_simbad` | `SourceCollection`, `simbad_source_collection` |
| `wwt_fits` | 24 | 24 `implemented_unverified` | `services/scientific_skills/astronomy.py:build_wwt_scene` | `WwtFitsLayer`, `WwtSceneVisualizationSpec` |
| `opposition` | 13 | 13 `implemented_unverified` | `services/scientific_skills/astronomy.py:find_celestial_events` | `AnalysisReport`, `celestial_events_list` |
| `inferior_conjunction` | 13 | 13 `implemented_unverified` | `services/scientific_skills/astronomy.py:find_celestial_events` | `AnalysisReport`, `celestial_events_list` |
| `planetary_transit` | 11 | 11 `implemented_unverified` | `services/scientific_skills/astronomy.py:_strict_transit_events` | `AnalysisReport`, `celestial_events_list` |
| `celestial_body_radius` | 10 | 10 `implemented_unverified` | `services/scientific_skills/astronomy.py:get_celestial_body_radius` | 受控物理常数 |
| `geocoding` | 9 | 9 `implemented_unverified` | `services/scientific_skills/astronomy.py:_geocode_location` | `SourceSnapshot`, `resolved_location` |
| `eclipse` | 6 | 6 `implemented_unverified` | `services/scientific_skills/astronomy.py:find_celestial_events`、`services/scientific_skills/eclipse_geometry.py` | `AnalysisReport`, `celestial_events_list` |
| `superior_conjunction` | 3 | 3 `implemented_unverified` | `services/scientific_skills/astronomy.py:find_celestial_events` | `AnalysisReport`, `celestial_events_list` |
| `seasonal_event` | 2 | 2 `implemented_unverified` | `services/scientific_skills/astronomy.py:find_celestial_events` | `AnalysisReport`, `celestial_events_list` |
| `moon_phase` | 1 | 1 `implemented_unverified` | `services/scientific_skills/astronomy.py:find_celestial_events` | `AnalysisReport`, `celestial_events_list` |
| `venus_elongation` | 1 | 1 `implemented_unverified` | `services/scientific_skills/astronomy.py:_venus_elongation_events` | `AnalysisReport`, `celestial_events_list` |
| `occultation` | 26 | 26 `implemented_unverified` | `services/scientific_skills/astronomy.py:_strict_occultation_events` | `AnalysisReport`, `celestial_events_list` |
| `spectrum` | 0 | 不适用 | MAVIS 两个“光谱双星”案例属于 SIMBAD 对象类型筛选，不是光谱数据获取或分析 | 不适用 |
| `weather` | 0 | 不采用参考实现 | 参考实现固定返回“晴天”，不构成真实能力；如未来引入必须使用可审计气象数据源 | 不适用 |
| `light_curve` | 0 | MAVIS 基准不适用 | 项目平台能力由 `services/scientific_skills/astro_series.py` 独立承接 | `LightCurve` |
| `gaia_ivoa` | 0 | MAVIS 基准不适用 | 平台级 Gaia/IVOA TAP 能力不计入本 160 例台账 | `SourceCollection` |

---

## 3. 保留的用户功能与领域语义

星文智析在受控 Contract 中保留了 MAVIS 的核心科研与可视化意图；是否已经可渲染以能力矩阵为准：

1. **天体坐标与星历解算**：
   - 基于 JPL DE421 星历内核计算太阳系各大行星、月球、太阳的实时与历史赤道坐标（RA/Dec）、地心/站心视位置；
   - 自动推算月相变化周期、二分二至（春分、秋分、夏至、冬至）时刻与地平天顶位置。
2. **天象事件判定**：
   - 行星冲日（Mars, Jupiter, Saturn opposition）；
   - 行星合日、上合日、下合日（Superior/Inferior Conjunction）；
   - 月掩行星、日食与月食（Lunar/Solar Eclipses, Occultations）；
   - 行星凌日（Mercury/Venus Transits）。
3. **天体数据库检索**：
   - SIMBAD 目标天体坐标解析与多源标识名解析（Object ID Resolution）；
   - 锥形视场区域检索（Cone Search）、天体类型过滤（脉冲星、白矮星、红矮星、双星、星系、星团）。
4. **科学 FITS 图像处理与测光**：
   - NASA SkyView 巡天图像获取与 FITS 头信息解析；
   - Photutils 孔径测光（Circular Aperture Photometry）、局部背景噪声估计；
   - 星点检测（DAOStarFinder / IRAFStarFinder）、源分割（Source Segmentation）与 PSF 测光。
5. **WWT 科学天图场景呈现**：
   - Contract 已表达坐标定位、背景、系统/固定时间、基础 FITS、圆/线/标签，以及 roll、observer/本地地平、多网格、暂停/倍率播放、readback、太阳系目标与覆盖层、星座、岁差、table layer、扩展 FITS 显示参数和有界 tour；
   - 标准 Renderer 已消费重构后的 Scene Contract，包括内容寻址 FITS/table layer、annotation、tour、readback 和 singleton 生命周期；对应 capability 为 `renderer=supported`；
   - ready 状态提供用户主动的本地 PNG 导出；该动作直接读取当前 canvas，不轮询、不上传，也不进入科学 Contract 或 Live 事实链；
   - 自动化接线不等于真实 WebGL 视觉验收；在人工验收前仍必须保留必填文本替代，不得将案例标为 `implemented_verified`。

---

## 4. 拒绝的旧机制与替代边界

我们明确拒绝 MAVIS 参考代码中的不安全运行机制，并在星文智析架构中确立了对应的替代边界：

```text
[拒绝: 旧 MAVIS 运行机制]                      [采用: 星文智析规范架构]
LLM 生成自由 Python / exec()      ───►  受控参数白名单 + Pydantic Schema + ScientificSkillRegistry
多轮 Prompt 递归自动纠错          ───►  WorkflowExecutor 状态机 + StepAttempt 显式预算与重试
私有 WebSocket 远程遥控 Vue      ───►  声明式 WwtSceneVisualizationSpec 产物 + 前端标准渲染
截图轮询与图片文件回传           ───►  标准 Renderer 读取状态 + 必填文本替代
Django 全局共享输出目录          ───►  Run/Attempt 隔离临时执行环境 + Content-Addressed Storage
代码中硬编码第三方 API Key       ───►  服务级安全凭据配置与受控网关白名单
本机硬编码绝对路径               ───►  版本化 SourceSnapshot 与 Project-owned ArtifactVersion
```

### 4.1 详细机制拒绝与架构替代

1. **拒绝 `arbitrary_python_execution`**：
   - *旧机制*：后端 Prompt 让模型实时拼装 Python 代码（`create_code`, `code1.py`），并通过 `exec` 运行未经验证的动态脚本。
   - *新边界*：全部转化为封装在 `services/scientific_skills/` 中的受控 Handler。输入参数由 Pydantic Schema 强校验，严禁执行模型自由生成的代码。
2. **拒绝 `recursive_self_correction`**：
   - *旧机制*：模型执行报错后，将错误信息无限制塞回 Prompt 进行自循环纠错重试。
   - *新边界*：由统一的 `Persistent Workflow Executor` 承接 Attempt 计数、指数退避与明确失败分类（区分 retryable 网络故障与不可重试的 Schema 错误）。
3. **拒绝 `browser_remote_control_websocket` 与 `screenshot_polling`**：
   - *旧机制*：Django 后端通过 WebSocket 发送指令驱动 Vue 前端 WWT 窗口，并调用截图脚本轮询图片。
   - *新边界*：技能只输出结构化声明式规范 `WwtSceneVisualizationSpec`；标准 Renderer 只能消费 capability matrix 声明为 supported 的意图，其他意图 fail closed 或显示文本替代。
4. **拒绝 `hardcoded_personal_paths` 与 `hardcoded_credentials`**：
   - *旧机制*：源码与基准配置中充满 `C:\Users\86136\Desktop\...` 路径及硬编码高德 API Key。
   - *新边界*：全面净化，所有路径使用相对路径或内容哈希；城市解析改用固定 HTTPS allowlist 的 Nominatim，并限制超时、重定向与响应体大小，不复制参考项目密钥。
5. **拒绝伪造的 `weather` 能力**：
   - *旧机制*：函数无外部调用且固定返回“晴天”。
   - *新边界*：不把常量字符串登记为已实现天气能力；未来只有可审计外部数据、SourceSnapshot 与 Live 证据齐全时才能引入。

---

## 5. Live 闭环验收标准与证据链

任何案例从 `implemented_unverified` 或 `planned` 状态跃迁至 `implemented_verified`，必须提供完整的**端到端 Live 证据链**：

```text
confirmed ResearchContract
  └──> queued -> planning -> executing RunStep (task-owned)
        ├──> StepAttempt: 记录真实持续时间与资源消耗
        ├──> External Port Call: 真实 SIMBAD / SkyView / JPL 响应
        ├──> SourceSnapshot: 外部获取数据的不可变哈希快照
        ├──> ProducerExecution: 记录 Skill ID、版本、参数与计算闭包
        ├──> ArtifactVersion Admission: 通过 Pydantic Schema 与领域门禁校验
        ├──> Evidence Graph: 产物节点与事实推导边持久化
        └──> UI Inspection: 前端 Inspector / WWT 真实渲染并通过人工视觉验收
```

### 5.1 验收门禁要求

1. **Contract 校验**：参数符合 `ScientificSkillRequest` 严格类型白名单。
2. **数值精度门禁 (`ephemeris_precision_check`)**：冲合时刻与历表天体位置与权威 JPL 天历误差在公差内。
3. **FITS 格式门禁 (`fits_header_validation`)**：FITS 头部 WCS 坐标系与数据维度合法。
4. **测光容差门禁 (`photometry_flux_tolerance_check`)**：孔径与背景通量积分结果在物理合理范围内。
5. **WWT 场景门禁 (`wwt_scene_spec_validation` + `wwt_*_renderer`)**：JSON 通过 `WwtSceneVisualizationSpec` 只证明 Contract；案例所需的每个 Renderer capability 还必须为 supported，并经真实 WebGL 初始化、无控制台错误、状态 readback 与人工视觉验收。

---

## 6. 台账工具与维护工作流

本台账提供配套的自动化构建与校验工具链，严守不可变与确定性原则：

### 6.1 校验现有台账一致性
```bash
uv run --project apps/api python services/reference_integration/build_mavis_adoption_ledger.py --reference-root E:\xingwen-astro-ai-reference --check
```

### 6.2 运行自动化测试套件
```bash
uv run --project apps/api pytest -q apps/api/tests/test_mavis_adoption_ledger.py
```

### 6.3 静态代码质量检查
```bash
uv run --project apps/api ruff check services/reference_integration/build_mavis_adoption_ledger.py apps/api/tests/test_mavis_adoption_ledger.py
```

> [!IMPORTANT]
> 台账 JSON 中的 `source_set_hash` 会对所有 160 个源文件的相对路径和 SHA-256 内容摘要进行确定性哈希。上游参考源文件一旦发生任何改动，构建脚本将自动 fail closed。
