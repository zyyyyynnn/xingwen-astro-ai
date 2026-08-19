# Reference Integration Traceability

| 元数据 | 值 |
| --- | --- |
| Scope | 旧 Reference Deep Integration 分支高价值源文件的分类登记与迁移归宿 |

本文件是 Reference Integration Preservation Gate 的登记 Authority：每项旧实现
固定为 `MAIN_EQUIVALENT / PORT_NEAR_AS_IS / PORT_REHOMED / TEST_ONLY /
DROP_INVALID` 之一，并记录保留的能力、目标 owner 与验证方式。分类只描述能力
归宿，不代表全部条目已完成移植；`verification` 列标注当前真实状态（`PASS` 表示
已有本地测试通过，`integration_pending` 表示本轮尚未移植）。

## 1. Scientific Skill Runtime

| Old source | Classification | Preserved capability | Target owner | Target file | Verification |
| --- | --- | --- | --- | --- | --- |
| services/scientific_skills/types.py | PORT_NEAR_AS_IS | bounded request/result 契约、budget、input/output hash | services/scientific_skills | services/scientific_skills/types.py | PASS |
| services/scientific_skills/registry.py | PORT_NEAR_AS_IS | 24 个 typed skill、参数契约、phase、workload class、fail-closed registry | services/scientific_skills | services/scientific_skills/registry.py | PASS（test_scientific_skill_registry.py） |
| services/scientific_skills/parameters.py | PORT_NEAR_AS_IS | typed parameter 校验 | services/scientific_skills | services/scientific_skills/parameters.py | PASS |
| services/scientific_skills/planning.py | PORT_NEAR_AS_IS | skill → workflow phase 映射 | services/scientific_skills | services/scientific_skills/planning.py | PASS |
| services/scientific_skills/process_execution.py | PORT_NEAR_AS_IS | 隔离子进程、hard timeout、terminate/kill fallback、declared-error mapping | services/scientific_skills | services/scientific_skills/process_execution.py | PASS（test_scientific_skill_process.py） |
| services/scientific_skills/data_analysis.py | PORT_NEAR_AS_IS | profile/统计/相关/聚类/异常/图表/crossmatch | services/scientific_skills | services/scientific_skills/data_analysis.py | PASS |
| services/scientific_skills/unsupervised.py | PORT_NEAR_AS_IS | KMeans/DBSCAN/silhouette/PCA/IsolationForest | services/scientific_skills | services/scientific_skills/unsupervised.py | PASS |
| services/scientific_skills/astronomy.py | PORT_NEAR_AS_IS | SIMBAD/SkyView/ephemeris/celestial events/FITS 分析/WWT scene | services/scientific_skills | services/scientific_skills/astronomy.py | PASS |
| services/scientific_skills/astro_acquisition.py | PORT_NEAR_AS_IS | Gaia/VizieR/MAST 光变/SDSS 光谱获取 | services/scientific_skills | services/scientific_skills/astro_acquisition.py | PASS |
| services/scientific_skills/astro_series.py | PORT_NEAR_AS_IS | 光谱/光变序列分析 | services/scientific_skills | services/scientific_skills/astro_series.py | PASS |
| services/scientific_skills/eclipse_geometry.py | PORT_NEAR_AS_IS | 凌日几何计算 | services/scientific_skills | services/scientific_skills/eclipse_geometry.py | PASS |
| services/scientific_skills/modeling.py | PORT_NEAR_AS_IS | leakage-safe 训练、诊断、ONNX 导出 | services/scientific_skills | services/scientific_skills/modeling.py | PASS |
| services/scientific_skills/inference.py | PORT_NEAR_AS_IS | ONNX 推理 | services/scientific_skills | services/scientific_skills/inference.py | PASS |
| services/scientific_skills/wwt_capabilities.py | PORT_NEAR_AS_IS | declarative WWT scene capability 描述 | services/scientific_skills | services/scientific_skills/wwt_capabilities.py | PASS |
| services/scientific_skills/execution.py | PORT_NEAR_AS_IS | input binding、candidate assembly、binary materialization | services/scientific_skills | services/scientific_skills/execution.py | PASS |
| services/scientific_skills/demo_fixture.py | TEST_ONLY | deterministic fixture 价值；不进入 production registry | （未移植） | — | integration_pending |

## 2. Scientific execution bridge（current Workflow 内）

| Old source | Classification | Preserved capability | Target owner | Target file | Verification |
| --- | --- | --- | --- | --- | --- |
| workflow/scientific_inputs.py | PORT_NEAR_AS_IS | input_refs → ArtifactVersion/SourceSnapshot/ResearchInput 单一 resolver；ownership/hash/evidence 闭合 | current Workflow | apps/api/src/app/workflow/scientific_inputs.py | PASS（test_scientific_input_parsing.py） |
| workflow/scientific_provenance.py | PORT_NEAR_AS_IS | 每个物理源独立 SourceSnapshot 记录 | current Workflow | apps/api/src/app/workflow/scientific_provenance.py | PASS |
| workflow/scientific_publication.py | PORT_REHOMED | task/skill binding、schema admission、Evidence/SourceSnapshot registry closure、coverage、stable artifact identity、idempotency、supersedes；事务所有权移交唯一 ArtifactPublisher | current Publisher seam | apps/api/src/app/workflow/scientific_admission.py | PASS |
| workflow/steps/scientific_steps.py（新增） | PORT_REHOMED | task-owned step 执行编排（resolver → skill → recorder → admission → publications） | current StepRuntime | apps/api/src/app/workflow/steps/scientific_steps.py | PASS |
| workflow/capacity.py | PORT_NEAR_AS_IS | worker register/heartbeat/drain/stop、capacity policy | current Workflow | apps/api/src/app/workflow/capacity.py | PASS |

## 3. Schema / DB / 契约扩展

| Old source | Classification | Preserved capability | Target owner | Target file | Verification |
| --- | --- | --- | --- | --- | --- |
| schemas/scientific_skills.py | PORT_NEAR_AS_IS | 六类科学成果 typed content schema | current schemas | apps/api/src/app/schemas/scientific_skills.py | PASS |
| schemas/scientific_artifact_api.py | PORT_NEAR_AS_IS | 科学成果读取 DTO | current schemas | apps/api/src/app/schemas/scientific_artifact_api.py | PASS |
| schemas/core.py（科学扩展） | PORT_REHOMED | 4 科学 phase、6 科学 ArtifactKind、ScientificSkillId、ScientificTaskInput、Contract 能力校验、RunStepRead phase/task/skill/depends | current schemas | apps/api/src/app/schemas/core.py | PASS |
| db/models.py（科学扩展） | PORT_REHOMED | RunStep task/skill binding 不变量、科学 phase 约束、ProducerExecution function-calling 审计列、WorkflowWorkerModel、queue deadline | current DB | apps/api/src/app/db/models.py | PASS（fresh schema bootstrap） |
| services/image_dataset.py | PORT_NEAR_AS_IS | ZIP 安全预算、labels allowlist、Pillow 校验、deterministic resize | current services | apps/api/src/app/services/image_dataset.py | PASS（test_image_dataset.py） |
| services/resource_authority.py（科学闭合） | PORT_NEAR_AS_IS | FITS/WWT/ONNX binary reference closure | current services | apps/api/src/app/services/resource_authority.py | PASS |
| ResearchInput xlsx/parquet/image_dataset | PORT_REHOMED | MIME magic-byte 嗅探、XLSX OOXML identity、Parquet PAR1、image_dataset 专用 policy | current ingestion | schemas/research_input.py + services/research_input_policy.py + services/research_input_ingestion.py | PASS |

## 3.1 前端契约对齐（最小一致）

| Old capability | Classification | Preserved capability | Target owner | Target file | Verification |
| --- | --- | --- | --- | --- | --- |
| domain ArtifactKind / RunStatus 扩展 | PORT_REHOMED | 6 科学 kind + 4 科学 phase 进入 domain 与 DTO 一致 | @xingwen/domain | packages/domain/src/enums.ts | PASS（typecheck） |
| Renderer Registry 穷举 | PORT_REHOMED | 6 科学 kind 以 user-safe fallback 登记，不静默、不 raw JSON | current 唯一 Registry | apps/workspace/src/presentation/artifact-renderer-registry.tsx | PASS（registry exhaustiveness） |
| 状态/步骤/成果中文文案 | PORT_REHOMED | 科学 phase 与 kind 的公开文案 | research-adapter + workspace | presentation-language.ts + artifact-presentation-labels.ts + research-presentation.ts + workspace-host.tsx | PASS（typecheck） |
| 契约产物再生 | PORT_REHOMED | core schema / openapi / dto.ts 从单一 authoring source 再生 | scripts + sync-contracts | packages/schemas + packages/contracts | PASS |

## 4. MAIN_EQUIVALENT（不再建第二实现）

| Old source | Classification | Reason |
| --- | --- | --- |
| workflow/data_pipeline_runtime.py | MAIN_EQUIVALENT | current steps/data_steps.py + StepPublicationFactory |
| workflow/data_pipeline_publication_runtime.py | MAIN_EQUIVALENT | current step_publication.py |
| workflow/document_pipeline_runtime.py | MAIN_EQUIVALENT | current steps/paper_steps.py |
| workflow/literature_pipeline_runtime.py | MAIN_EQUIVALENT | current steps/literature_steps.py |
| workflow/literature_workflow_runtime.py | MAIN_EQUIVALENT | current steps/literature_steps.py |
| workflow/paper_collection_search_runtime.py | MAIN_EQUIVALENT | current steps/paper_steps.py + LivePaperCollectionRunner |
| schemas/core.py RunCheckpoint/RunDecision 旧形态 | MAIN_EQUIVALENT | current RunCheckpoint + RunCheckpointDecision（通用 checkpoint 运行时唯一） |
| db/models.py WorkflowProjectDispatchModel | DROP_INVALID | 一个 Project 同时最多一个 non-terminal Run，无需 project dispatch fairness 表 |

## 5. DROP_INVALID（仅限明确禁止项）

| Old source / item | Reason |
| --- | --- |
| apps/api/migrations/**、alembic、schema_baseline、upgrade/downgrade | 无 migration 架构；fresh current schema bootstrap 唯一 |
| WorkflowProjectDispatchModel | 见上 |
| 旧 checkpoint/decision 第二 runtime（RunDecision*） | current 通用 checkpoint 唯一 |
| qwen3.7-plus | 批准池之外 |
| pickle / joblib / raw Python model object | ONNX 唯一安全模型格式 |
| 旧 coverage 数字（如 160 cases） | 分母必须重新扫描 Reference 决定 |

## 5.1 Reference Integration Authority（本轮移植）

| Old source | Classification | Preserved capability | Target owner | Target file | Verification |
| --- | --- | --- | --- | --- | --- |
| services/reference_integration/reference_capability_manifest.py | PORT_NEAR_AS_IS | manifest 语义校验、coverage 计数、disposition/eligibility 规则 | services/reference_integration | services/reference_integration/reference_capability_manifest.py | PASS（test_reference_integration_coverage.py） |
| services/reference_integration/build_reference_capability_manifest.py | PORT_NEAR_AS_IS | manifest --check（语义 + owner 存在性 + reference source digest） | services/reference_integration | services/reference_integration/build_reference_capability_manifest.py | PASS（--check 于 Reference root） |
| services/reference_integration/build_mavis_adoption_ledger.py | PORT_NEAR_AS_IS | MAVIS benchmark case index 构建器（分母重扫 Reference root，无硬编码数字、无机器路径） | services/reference_integration | services/reference_integration/build_mavis_adoption_ledger.py | PASS（--check：160 cases） |
| services/reference_integration/mavis_benchmark.py | PORT_NEAR_AS_IS | MAVIS benchmark 报告 | services/reference_integration | services/reference_integration/mavis_benchmark.py | PASS |
| services/paper_pipeline/summary_chunks.py | PORT_NEAR_AS_IS | section-aware chunking、reading order、chunk Evidence allowlist | services/paper_pipeline | services/paper_pipeline/summary_chunks.py | PASS（stdlib-only，manifest owner） |

## 5.2 科学成果读路径（本轮移植，§50）

| Old source | Classification | Preserved capability | Target owner | Target file | Verification |
| --- | --- | --- | --- | --- | --- |
| content_storage range read | PORT_REHOMED | ContentRead / open_read / HTTP Range（200/206/416）流式读取，保留当前 corruption-repair store | current services | apps/api/src/app/services/content_storage.py | PASS |
| services/scientific_artifacts.py | PORT_NEAR_AS_IS | 科学成果读取服务（kind 分发 + binary reference closure + range content） | current services | apps/api/src/app/services/scientific_artifacts.py | PASS |
| GET /api/artifact-versions/{id}/scientific + /scientific/content/{hash} | PORT_REHOMED | 精确 ArtifactVersion 读取 + 二进制 Range 读取（ownership/hash 闭合） | current artifacts router + contracts | apps/api/src/app/routers/artifacts.py + contracts/core.py | PASS（openapi/contract parity） |

## 5.3 科学成果展示与交互（本轮移植，§56-77）

| Old source | Classification | Preserved capability | Target owner | Target file | Verification |
| --- | --- | --- | --- | --- | --- |
| 科学成果内容组件（analysis-report/spectrum/light-curve/model-evaluation content） | PORT_REHOMED | 指标、发现、局限、人工确认、采样表、time-scale identity、Evidence wiring | 唯一 Renderer Registry + Fullscreen seam | apps/workspace/src/components/scientific-content/* | PASS（scientific-artifact-renderer.test.tsx） |
| scientific-artifact-renderer + registry 六 kind 接线 | PORT_REHOMED | 六个科学 kind 真实内容读取（ownership/version/kind 闭合） | 唯一 Registry | apps/workspace/src/presentation/artifact-renderer-registry.tsx | PASS（registry exhaustiveness + renderer tests） |
| wwt-session.ts | PORT_NEAR_AS_IS | 单一引擎 session、lease/supersession、串行渲染队列、场景重置、图层/注释/Blob URL 清理、FITS/table 图层、网格/观测者/时间/太阳系/星座/岁差、tour、readback | current components | apps/workspace/src/components/wwt-session.ts | PASS（wwt-viewport.test.tsx lease/close） |
| wwt-viewport.tsx | PORT_NEAR_AS_IS | StrictMode-safe mount、loading/error/retry、canvas focus、PNG 导出、文本与表格替代、实际状态 readback | current components | apps/workspace/src/components/wwt-viewport.tsx | PASS（wwt-viewport.test.tsx） |
| scientific-chart.tsx（旧手写 SVG renderer） | PORT_REHOMED | typed 轴/单位/序列语义 → Vega-Lite 安全构建器（无 raw spec/eval，卸载 finalize，表格替代） | current components | apps/workspace/src/components/scientific-chart.tsx | PASS（scientific-chart.test.tsx） |
| packages/ui/src/select.tsx | PORT_NEAR_AS_IS | shadcn registry（shadcn-cli@4.16.2）正式接入，图标重绑治理 barrel | packages/ui | packages/ui/src/select.tsx + component-sources.json | PASS（packages/ui/test/select.test.tsx） |
| apps/api/tests/test_wwt_scene_contract.py | TEST_ONLY | WWT 场景声明式契约、bounded skill 输出、危险远程控制拒绝、能力矩阵真实性 | apps/api/tests | apps/api/tests/test_wwt_scene_contract.py | PASS（9 tests） |

## 6. 尚未移植（integration_pending）

以下 REQUIRED 项已完成分类但尚未移植，保持 Draft 状态直至闭合：

| Item | Classification（既定归宿） |
| --- | --- |
| Inosum 七段式 PaperSummary 运行时（document_summary + paper_summary_exports + summary/prompt/fixture 七段式迁移） | PORT_NEAR_AS_IS（需迁移 PaperSummary schema 七段式结构，涉及已合并 paper summary 流，单独收口） |
| agent_runtime function-calling producer 审计写路径 | PORT_REHOMED（DB 审计列已就绪） |
