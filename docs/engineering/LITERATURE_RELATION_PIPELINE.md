# LiteratureRelation Pipeline

| 元数据    | 值                                                                             |
| --------- | ------------------------------------------------------------------------------ |
| Authority | LiteratureRelation、ReasoningTrace 准入、confidence、固定 Benchmark 与交接边界 |
| Scope     | Detached Relation admission、可复现 Benchmark 与 typed candidate 契约          |

本文是 LiteratureRelation 运行规则和操作方式的唯一完整事实源。Relation taxonomy 与科研准入原则由
[Reasoning Protocol](../ai/REASONING_PROTOCOL.md) 负责，字段和领域不变量由
[Data Model](../architecture/DATA_MODEL.md) 负责，ArtifactVersion/hash 规则由
[Data Versioning](../architecture/DATA_VERSIONING.md) 负责。

## 1. 输入、输出与模块入口

运行入口是 `services.paper_pipeline.relation.LiteratureRelationPipeline`。它接收：

- 经过 LiteratureClaim Pipeline 封印的 `LiteratureClaimsCandidate@1.0.0`，以及每个 Claim 所属
  LiteratureClaims/PaperSummary ArtifactVersion、Project、Evidence 和 SourceSnapshot；
- `literature_relation` 当前定义对应的模型 JSON 响应；
- model、parameters version 与安全 parameters；
- 由调用方提供且已经版本化、校准的 `LiteratureRelationConfidenceAssessment`；模型只
  引用 assessment id，不生成 score；
- 可选的已知 ArtifactVersion、Claim、Evidence、SourceSnapshot、ownership 与既有
  Relation fingerprint 集合。

只有 LiteratureClaim status 为 `candidate | accepted` 的 Claim 可以进入稳定 pairing；rejected
Claim 保留在上游审计中，不进入 Relation endpoint。输出
`LiteratureRelationAdmissionResult`，始终包含 ProducerExecution、输入版本、
input/model-response/output hash 和稳定准入结论。JSON/Schema 失败不伪造 Relation 或
Trace。

pairing 的完整输入边界就是调用方固定的 LiteratureClaims ArtifactVersion 集合。
Prompt 不再接收未版本化的独立 `research_goal`；若工作流需要按 ResearchContract 缩小
范围，必须先固定传入的 ArtifactVersion 集合，而不能让未进入 input hash 的模板变量
暗中改变 Relation 输出。

只要至少一条 Relation 为 `candidate | accepted`，结果同时提供经过 Pipeline 封印的
`LiteratureRelationsCandidate@1.0.0`。它是一个 `kind=literature_relations` 的领域
typed candidate，并在同一内容闭包内保存 Relation、对应 ReasoningTrace、双方 Claim、
Evidence/SourceSnapshot 与 ProducerExecution；Pipeline 不另行发布 `reasoning_traces`
Artifact。Pipeline 自身不创建数据库 ArtifactVersion、不推进 ResearchRun、不发布 HTTP
DTO，也不生成 Graph 或 GraphEdge。

## 2. Schema

唯一 Pydantic 编写源是 `apps/api/src/app/schemas/literature_relation.py`，所有
公共 contract version 为 `1.0.0`：

| 模型                                        | 职责                                                                         |
| ------------------------------------------- | ---------------------------------------------------------------------------- |
| `LiteratureRelationExtractionOutput`        | 模型 JSON；包含 `schema_version` 和至少一条严格 Relation model candidate     |
| `LiteratureRelationCandidate`               | 单条 Relation 的方向、条件、可比性、provenance、三态与稳定拒绝结果           |
| `LiteratureReasoningTraceCandidate`         | Relation 绑定的公开可审查 Trace；包含 premises、连续 steps、限制和 Evidence  |
| `LiteratureRelationConfidenceAssessment`    | 绑定具体方向、Claim 版本、relation type 与 admission decision 的外部校准输入 |
| `LiteratureRelationAdmissionResult`         | 批次准入结果；JSON/Schema 顶层拒绝或 record-level 结果                       |
| `LiteratureRelationsCandidate`              | 唯一 publisher-ready 批次，内嵌 Relation 与 Trace 完整闭包                   |
| `LiteratureRelationBenchmarkEvaluationCase` | 冻结科研标签或稳定负例的完整重放输入                                         |
| `LiteratureRelationBenchmarkReport`         | 指标分子/分母、逐 case 结果、confidence 分布与稳定 hash                      |

模型 extraction 同时包含：

- 固定 `source_claim_id relation_type target_claim_id` 的 direction 及依据；
- conditions、condition conflicts/uncertainties；
- object、metric、unit 各自的 comparability status 与依据；
- 双方 Evidence ids；
- 可选的结构化 Trace model candidate；
- 可选的外部 confidence assessment id。

完整 Relation taxonomy 为 `supports | extends | derived_from | limits | contradicts |
uses_same_dataset | compares_method`。后两者是结构关系，不自动推出 supports、limits 或
contradicts。Trace step operation 是闭合枚举：`identify_premises`、
`compare_objects`、`compare_metric`、`compare_unit`、`check_conditions`、
`check_evidence`、`classify_relation`、`record_limitation`。

object 必须显式为 comparable；metric/unit 只有双方都缺失时可为 `not_applicable`，双方
相同且非空时可为 `comparable`。任一方缺失或双方值不同会推导为 `incomparable`，即使模型
如实声明 incomparable 也必须拒绝，不能把“声明一致”误当成“数据可比”。

独立 tracked JSON Schema 位于 `packages/schemas/generated/literature_relation`，不进入
HTTP OpenAPI。core `LiteratureRelationsArtifactContent`/`ReasoningTracesArtifactContent`
仅表达当前读取投影，不是编写源，也不能进入 Publisher。

## 3. 固定准入顺序与拒绝优先级

顺序不可调整：

```text
JSON
-> schema
-> input ArtifactVersion/content
-> Claim existence/status
-> Evidence/SourceSnapshot
-> ownership
-> pairing
-> direction
-> duplicate
-> conditions
-> comparability: object -> metric -> unit
-> ReasoningTrace
-> confidence
```

同一输入触发多个错误时，只返回最早阶段的主拒绝原因：

| 阶段          | 稳定拒绝原因                                                                                                                                                                                                                                                     |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| JSON          | `literature_relation.json_invalid`                                                                                                                                                                                                                               |
| schema        | `literature_relation.schema_invalid`                                                                                                                                                                                                                             |
| input         | `literature_relation.input_artifact_version_unknown`、`literature_relation.input_schema_version_unsupported`、`literature_relation.input_content_hash_mismatch`                                                                                                  |
| Claim         | `literature_relation.claim_not_found`、`literature_relation.paper_summary_artifact_version_unknown`、`literature_relation.claim_status_invalid`                                                                                                                  |
| Evidence      | `literature_relation.evidence_missing`、`literature_relation.evidence_not_found`、`literature_relation.source_snapshot_not_found`、`literature_relation.evidence_inconsistent`                                                                                   |
| ownership     | `literature_relation.ownership_mismatch`                                                                                                                                                                                                                         |
| pairing       | `literature_relation.self_pair`                                                                                                                                                                                                                                  |
| direction     | `literature_relation.direction_mismatch`                                                                                                                                                                                                                         |
| duplicate     | `literature_relation.duplicate`                                                                                                                                                                                                                                  |
| conditions    | `literature_relation.conditions_missing`、`literature_relation.conditions_conflict`                                                                                                                                                                              |
| comparability | `literature_relation.object_incomparable`、`literature_relation.metric_incomparable`、`literature_relation.unit_incomparable`                                                                                                                                    |
| Trace         | `literature_relation.trace_missing`、`literature_relation.trace_incomplete`、`literature_relation.trace_unsafe`、`literature_relation.trace_direction_mismatch`、`literature_relation.trace_evidence_incomplete`                                                 |
| confidence    | `literature_relation.confidence_undefined`、`literature_relation.confidence_definition_unsupported`、`literature_relation.confidence_calibration_missing`、`literature_relation.confidence_subject_mismatch`、`literature_relation.confidence_decision_mismatch` |

JSON/Schema 失败产生无 Relation record 的统一 rejected result；后续阶段只处理已经通过
唯一 model-output Schema 的结构化记录。pair identity 与 duplicate fingerprint 覆盖双方
Claim ArtifactVersion/id、relation type 和稳定方向。输入集合顺序变化不得改变 pair id、
方向、fingerprint、输出顺序或 hash。

## 4. 三态、Evidence 与 ReasoningTrace

- `accepted`：全部硬门通过；双方 Claim 为 accepted；conditions 已解决；Trace 与
  Evidence 闭包完整；confidence 为经过支持定义和校准的 `assessed`，score 达到阈值。
- `candidate`：全部硬门通过，但 Claim 尚为 candidate、conditions 仍有可审查不确定性、
  confidence 为已验证的 `not_evaluable`，或已校准 score 低于阈值。对应 review reason
  为 `claim_not_accepted | conditions_unresolved | confidence_not_evaluable |
confidence_below_threshold`。
- `rejected`：命中固定拒绝阶段和原因。高 confidence 不能覆盖任何硬门。

每条非 rejected Relation 必须具有 source 和 target 两侧 Evidence。每个引用同时绑定
Claim、Claim ArtifactVersion、PaperSummary ArtifactVersion、paper、SourceSnapshot
id/version/content hash、Evidence status 与 validation code。Relation 级 Evidence ids 和
SourceSnapshot ids 必须等于引用闭包，不能只给出无法回到输入版本的裸 id。

`LiteratureReasoningTraceCandidate` 固定 relation id、按 source/target 顺序保存的两个
premise Claim、从 1 连续编号的结构化 steps、conditions、limitations、conflicts、
conclusion、Evidence ids、Trace protocol version 与 ProducerExecution/hash。每步只保存
操作、公开 statement、Claim/Evidence 引用。不得保存或重建模型私有 chain-of-thought、
隐藏 Prompt、逐 token 推理、原始模型长输出或受限全文。

Trace `conditions` 必须等于 Relation conditions，Trace `conflicts` 必须等于 Relation
`condition_conflicts`。任一侧声明冲突都会在固定 conditions 阶段拒绝；两侧不一致时不
保留伪完整 Trace。只有双方 conflict 集合都为空的 Relation 才能进入非 rejected 状态。

安全扫描覆盖 Trace 以及 direction/comparability basis、conditions/conflicts/uncertainties
和 confidence basis 等全部自由文本。命中隐藏 Prompt、私有推理或凭据模式时按 Trace
阶段拒绝；可能进入 rejected audit record 的自由文本使用稳定占位符脱敏，原文只影响
不可逆 `model_response_hash`，不会出现在 AdmissionResult 或 sealed payload。

rejected Relation 可以保留满足上述安全边界且 Claim/Evidence/SourceSnapshot 引用与
Relation 精确闭合的负例 Trace，用于解释不可比或拒绝依据；Claim、Evidence 或 ownership
等较早阶段已破坏该闭包时不保留伪完整 Trace。Trace 的 `relation_status` 必须与 Relation
一致。rejected Relation 不进入最终 Graph，也不能被解释为 accepted。Graph Pipeline
拥有 Graph 发布和 GraphEdge 完整性规则。

## 5. Confidence 定义

confidence 不是“Relation 为真”或“可接受”的概率，而是对完整
`relation type + admission decision` 决策的校准置信。Evidence、ownership、方向、
conditions、comparability 和 Trace 硬门先执行，confidence 最后执行。

Pipeline 冻结：

| 字段                                | 值                                                            |
| ----------------------------------- | ------------------------------------------------------------- |
| definition id/version               | `relation_classification_decision_confidence@1.0.0`           |
| calibration id/version              | `exoplanet_host_star.paper_reasoning.relation_labels@1.3.0`   |
| calibration scientific/content hash | Benchmark `1.3.0` 当前 scientific payload/content hash        |
| calibration sample size             | `4` 条 review-approved Relation labels                        |
| calibration method                  | `frozen_approved_label_reference`                             |
| applicability scope                 | `benchmark.exoplanet_host_star.relation_admission_regression` |
| score interpretation                | `confidence_in_relation_type_and_admission_decision`          |
| accepted threshold                  | `0.9`                                                         |

模型只能引用调用方提供的 `LiteratureRelationConfidenceAssessment.assessment_id`。该对象
保存 source/target Claim ArtifactVersion+Claim id、relation type 与 subject fingerprint，
并显式绑定 `accepted | candidate | rejected` decision；同一 assessment 不能复用于其他
方向、版本、类型或决策。它还保存 `assessed | not_evaluable`、可选 score、definition/calibration id 与 version、
calibration scientific/content hash、sample size、method、scope、score interpretation、
threshold 和依据。引用缺失或未知、definition 未版本化/不受支持、calibration 缺失、
subject 或 decision 不匹配时硬拒绝；只有已经验证且绑定当前 candidate decision 的
assessment 显式为 `not_evaluable` 时保留 candidate。
`assessed` 且 score 低于 `0.9` 也只保留 candidate；达到 `0.9` 仅在其他门全部通过时
允许 accepted。

基准包中两条 rejected Relation 的原始 confidence 都是 `0.99`。这恰好说明 score 不是
accepted probability：它们表示对“当前 relation type + rejected admission decision”
的高置信，绝不能因超过阈值改成 accepted。

## 6. Prompt、ProducerExecution 与 Hash

生产 Prompt 是 `packages/prompts/literature_relation/prompt.md`，Registry 以 UTF-8/LF hash
固定当前定义。仓库只保留当前 Prompt 文件，业务代码不提供 Prompt 选择入口；已发布执行
通过 `ProducerExecution` 中的 Prompt 名称、语义版本与 hash 保留证据。

ProducerExecution 固定记录 producer/model、Prompt name/version/hash、schema/parameters/
pairing/comparison/Trace/confidence definition 与完整 calibration policy、全部输入 ArtifactVersion、
input/model-response/output hash、安全终态和时间。参数只允许受限安全标量；不保存模型
原始长响应、凭据、认证头、受限全文或私有推理。

- `input_hash` 覆盖 sealed LiteratureClaims 输入、Claim/PaperSummary ArtifactVersion、
  Evidence/SourceSnapshot、Prompt/model/parameters、pairing/comparison/Trace policy 和
  confidence definition/calibration，以及 caller 提供的 Evidence/SourceSnapshot/Summary
  可用性闭包和既有 Relation fingerprints；
- valid `model_response_hash` 对结构化模型输出规范化，并使用稳定 Relation 顺序；
- Relation fingerprint 只识别固定方向的 endpoint ArtifactVersion/Claim 和 relation type；
- `output_hash` 覆盖准入后的 Relation/Trace、Evidence 闭包、confidence、状态、拒绝原因、
  Producer 与输入版本，但排除 execution/run id、wall-clock、latency 和 producer output
  hash 自引用，也排除内嵌 Claim 的 producer execution id；
- ArtifactVersion admission 另对准备持久化的完整 JSON 计算 `content_hash`，两者职责
  不同，不要求相等。

因此相同冻结输入产生相同排序与 hash；Prompt、model parameters、ArtifactVersion、
Evidence、Trace、confidence 或 policy version 变化必须改变相应 hash。

## 7. Publisher Admission Seal

只有 Pipeline 直接返回的 `LiteratureRelationsCandidate@1.0.0` 可以进入通用 structured
ArtifactVersion admission port。authority 的弱引用与不可变快照 registry 以及 mint 只
存在于进程内闭包；一次性 binder 只接受 `sys.modules` 中的 exact Pipeline owner class，
把 minter 绑定进其 `admit` 闭包后从模块命名空间删除。公开验证 helper 只能检查
authority，不能创建 authority。
seal 同时绑定：

- 当前 Python 对象身份和 registry 中仅由 Pipeline mint 的 authority；
- `kind`、schema version、input/output hash；
- 准入 context hash 与 commitment hash；
- 完整公开 payload hash。

mint 还要求调用帧是绑定时记录的原始 `admit` code object，且待封印对象正是该帧局部
完成全部 gate 后构造的 candidate；即使通过 Python closure 反射取得 callable，脱离该
调用点直接执行也不能注册 authority。公开 verifier 逐层反射只能读取 tuple/NamedTuple
不可变快照，不能取得可写 registry；seal/context/candidate 使用弱引用精确绑定对象身份。

绑定完成后模块不保留可导入 mint、binder 或可写 registry。JSON/Pydantic round-trip、
copy/deepcopy、偷取或手工构造 seal、
手工重建、单条 Relation/Trace、raw extraction 与读取投影均不恢复 seal。
修改 Relation、Evidence、Trace、confidence、版本、
Producer 或 hash 会使 seal 失效。candidate/rejected 状态保留在批次内也不得冒充
accepted；Graph 消费端只能选择真正 accepted 的 Relation。

## 8. 固定 Benchmark

`services.paper_pipeline.relation_benchmark` 只读取 tracked 基准 Package，并校验：

```text
benchmark_id: exoplanet_host_star.paper_reasoning
schema_version: 1.3.0
benchmark_version: 1.3.0
scientific_payload_hash: sha256:35ccf88f92e2ed86603702dd1251ee43998ea2babb4184f2c9d46d00fc85afc4
content_hash: sha256:54046b775299d0b97fc61f12466255e7818eab50471d506ea07137cb61956337
tracked_file_sha256: 89fadef6a72ea484b4c22896889f9e874fe9ff9e586f1bebcb63ed1898c4cec5
```

默认 suite 确定性派生全部四条 review-approved Relation/Trace：`extends/accepted` 1、
`derived_from/candidate` 1、`limits/rejected` 1、`contradicts/rejected` 1。基准包没有
`supports`、`uses_same_dataset` 或 `compares_method` 科研标签，Benchmark 不伪造它们。
四条 Trace 全部为 review-approved；Trace 没有独立 admission status，按绑定 Relation
保存 1 accepted、1 candidate、2 rejected。

默认 suite 还从冻结输入派生 invalid JSON、Evidence missing、condition conflict、
object/metric/unit incomparable、dangling Claim/Summary version、wrong direction、
duplicate、incomplete Trace、undefined confidence、confidence subject/decision mismatch
等稳定负例。`--cases` 只用于重放
完整已序列化 suite，不允许提交有利子集；`--cases-output` 是可选审计输出，不是运行
前置输入。

```powershell
uv run --project apps/api python -m services.paper_pipeline.relation_benchmark `
  --cases-output .artifacts/literature-relation-benchmark-cases.json `
  --output .artifacts/literature-relation-benchmark-report.json
```

报告分别保存分子、分母和 rate：

- `scientific_pair_coverage_rate`：成功稳定配对并定位预期 Relation record 的
  scientific cases / 4；它与分类 exact match 分开；
- `scientific_relation_exact_match_rate`：与 Pipeline 可表达的冻结科研字段精确一致的
  Relation/Trace / 固定 4 条 approved labels；缺 record/Trace 计为失败，不能缩小分母。
  Trace 的独立 `uncertainty` 稳定映射到公开 limitations 后参与 exact；
- `relation_evidence_coverage_rate`：保留且 supported 的双方 Relation Evidence 引用 / 8；
- `trace_step_evidence_coverage_rate`：保留且 supported 的 Trace-step Evidence 引用 / 13；
- `evidence_less_block_rate`：确实因无 Evidence 被阻止的 evidence-less 负例 / 全部此类负例；
- `rejection_case_pass_rate`：status、最早 failure stage 和 reason 全部精确命中的负例 /
  全部 rejection cases；
- confidence 分开报告 assessed/not_evaluable/calibrated count 和原始
  `[0.0,0.5)`、`[0.5,0.9)`、`[0.9,1.0]` 分布，不与 admission rejection 合并成总分；
- `scientific_status_counts` 固定核对四条科研标签的 accepted/candidate/rejected 为
  `1/1/2`，`status_counts` 统计全部 scientific + rejection cases，
  `relation_type_counts` 只统计四条 scientific Relation；
- 逐 case input/output hash 和 report input/output hash。

任一分母为零时对应 rate 为 `null`，不能报告 100%。case id、Relation、Trace、
Evidence、拒绝原因和序列化 key 使用稳定顺序；report hash 不含时间戳、execution id 或
latency。相同冻结输入连续运行两次的 cases/report 必须字节一致。

该 Benchmark 的数据等级是 `Benchmark / seed`，不调用线上模型、不修改基准包，也不依赖
公网。exact match 只验证冻结人工标签和 admission 回归，不代表线上模型科学质量、
泛化能力、新科学结论或 acceptance probability。

## 9. 验证

普通测试只使用 fixture/stub：

```powershell
uv sync --project apps/api --frozen
uv run --project apps/api pytest apps/api/tests/test_literature_relation_pipeline.py
uv run --project apps/api pytest apps/api/tests/test_literature_claim_pipeline.py apps/api/tests/test_literature_relation_pipeline.py
uv run --project apps/api pytest
uv run --project apps/api python -m services.paper_pipeline.relation_benchmark --cases-output .artifacts/literature-relation-benchmark-cases-a.json --output .artifacts/literature-relation-benchmark-report-a.json
uv run --project apps/api python -m services.paper_pipeline.relation_benchmark --cases-output .artifacts/literature-relation-benchmark-cases-b.json --output .artifacts/literature-relation-benchmark-report-b.json
```

双跑后使用 `Get-FileHash -Algorithm SHA256` 比较两份 cases/report；对应文件 hash、stable
input hash 和 stable output hash 都必须相同。Prompt Registry 必须加载当前登记定义，
并确保其 front matter、output model 与 LF 文件 hash 一致。

tracked Schema 使用 [Schema Package](../../packages/schemas/README.md) 中正式
export/`--check` 命令验证；CI 同时运行 Benchmark、Schema、
OpenAPI、contracts sync/stale diff、Foundation、前端质量、Compose 与 Browser E2E。

## 10. 明确非目标

本 Pipeline 不实现 Graph/GraphEdge、HTTP endpoint/DTO、前端、数据库 ArtifactVersion 事务、
ResearchRun 推进、生产模型 client、Agent 平台或自由代码执行。它不修改已批准
科研事实，不复制 MAVIS Agent/Prompt，不保存原始模型长输出、受限全文、凭据或私有
chain-of-thought。
