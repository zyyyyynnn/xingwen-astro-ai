# LiteratureClaim Pipeline

| 元数据    | 值                                                                 |
| --------- | ------------------------------------------------------------------ |
| Status    | Accepted                                                           |
| Authority | LiteratureClaim 抽取、规范化、准入、固定 Benchmark 与交接边界      |
| Scope     | Detached Claim admission、可复现 Benchmark 与 typed candidate 契约 |

本文是 LiteratureClaim 运行规则和操作方式的唯一完整事实源。Claim 字段与不变量仍由
[Data Model](../architecture/DATA_MODEL.md) 负责，ArtifactVersion/hash 规则由
[Data Versioning](../architecture/DATA_VERSIONING.md) 负责，跨文献 Relation 规则由
[Reasoning Protocol](../ai/REASONING_PROTOCOL.md) 负责。

## 1. 输入、输出与模块入口

运行入口是 `services.paper_pipeline.claim.LiteratureClaimPipeline`。它接收：

- `PaperSummaryArtifactVersionInput` repository-port 值；其中 content 必须已经通过
  已验证的 `PaperSummaryArtifactContent` Pydantic 校验；
- 请求的 PaperSummary ArtifactVersion id 和 paper id；
- `literature_claim` 当前 Prompt 定义对应的模型 JSON 响应；
- model、parameters version、安全 parameters；
- 可选的 Evidence/SourceSnapshot 存在性集合和既有 Claim fingerprint。

输出 `LiteratureClaimAdmissionResult`。结果始终包含 ProducerExecution、
PaperSummary input reference、input/model-response/output hash；JSON/Schema 失败不
伪造 Claim。Schema-valid 记录包含 raw/normalized text、claim type、polarity、
objects、metric/unit、conditions、scope、limitations、qualifiers、uncertainty、
Evidence/SourceSnapshot、状态和稳定拒绝原因。

只要批次中至少有一条 `candidate` 或 `accepted` Claim，结果同时提供经过 Pipeline
封印的 `LiteratureClaimsCandidate`。该类型可以直接交给 ArtifactVersion structured
admission port；Pipeline 自身不创建数据库 ArtifactVersion。

## 2. 固定准入顺序

顺序不可调整：

1. JSON 解析；
2. `LiteratureClaimExtractionOutput` Pydantic Schema；
3. PaperSummary ArtifactVersion 存在性与支持的 schema version；
4. Evidence 与 SourceSnapshot 存在性；
5. paper、Summary、statement、Evidence、SourceSnapshot ownership；
6. normalization 可行性；
7. exact structured fingerprint duplicate；
8. 最终 `candidate | accepted | rejected`。

同一输入同时触发多个错误时，只返回最早阶段的主拒绝原因：

| 阶段          | 稳定拒绝原因                                                                                                             |
| ------------- | ------------------------------------------------------------------------------------------------------------------------ |
| JSON          | `literature_claim.json_invalid`                                                                                          |
| Schema        | `literature_claim.schema_invalid`                                                                                        |
| input         | `literature_claim.input_artifact_version_unknown`、`literature_claim.input_schema_version_unsupported`                   |
| Evidence      | `literature_claim.evidence_missing`、`literature_claim.evidence_not_found`、`literature_claim.source_snapshot_not_found` |
| ownership     | `literature_claim.ownership_mismatch`                                                                                    |
| normalization | `literature_claim.normalization_unsafe`                                                                                  |
| duplicate     | `literature_claim.duplicate`                                                                                             |

JSON/Schema 失败产生无 Claim record 的统一 rejected result；后续阶段只处理已经通过
唯一 model-output Schema 的结构化记录。

## 3. 状态语义

- `accepted`：输入版本、ownership 和 normalization 全部通过，且每条绑定 Evidence
  均由 Summary Evidence admission 标记为 `supported`；
- `candidate`：结构与 provenance 完整，但至少一条绑定 Evidence 为
  `unsupported` 或 `unverifiable`；
- `rejected`：命中上表任一稳定拒绝原因。

状态不使用 confidence、文本相似度或 hash 相同来宣称科学正确性。全 rejected
批次没有 publisher candidate；混合批次保留 rejected record 作为审计，但下游
Relation 输入只能选择 candidate/accepted Claim。

## 4. Schema、Prompt 与版本

唯一 Pydantic 编写源是
`apps/api/src/app/schemas/literature_claim.py`。中间模型
`LiteratureClaimModelCandidate`、`LiteratureClaimExtractionOutput`、单条
`LiteratureClaimCandidate` 和 `LiteratureClaimAdmissionResult` 不能绕过 Pipeline 直接进入
Publisher；只有 Pipeline 封印的完整
`LiteratureClaimsCandidate@1.0.0` 才是领域 typed candidate。task-read
`app.schemas.reasoning.LiteratureClaim`、`LiteratureReasoningResponse` 和 core
`LiteratureClaimsArtifactContent` 是当前读取投影，带不可发布 marker，不是第二套编写源。
独立 tracked JSON Schema 位于
`packages/schemas/generated/literature_claim`，不进入 HTTP OpenAPI。

生产 Prompt 位于 `packages/prompts/literature_claim/prompt.md`，通过
`packages/prompts/registry.json` 的单一 hash-pinned 当前记录加载。Prompt 要求：

- 每条 Claim 指向一个明确 Summary statement 及其 Evidence；
- finding、method、dataset、limitation 使用契约枚举；
- 不合并不可比较对象、指标、数据集、样本或实验条件；
- 保留方向、否定、conditions、scope、limitations、qualifiers 和 uncertainty；
- 只输出 JSON，不输出 confidence、Relation、ReasoningTrace、Graph 或私有推理。

Extraction、Claim candidate、admission、publisher candidate 与 Benchmark report
schema/report version 均固定为 `1.0.0`；producer、parameters 和 normalization
version 也均为 `1.0.0`。ProducerExecution 固定记录
Prompt/schema/model/parameters/producer/normalization 版本。parameters 复用 Summary
安全标量和敏感键拒绝策略。

## 5. Normalization 与 duplicate

normalization version 为 `1.0.0`，只执行保守、确定性规则：

- Unicode NFKC、首尾清理和空白折叠；
- 仅规范已明确支持的单位别名：Kelvin、percent、solar mass、solar radius；
- 未知单位保持原样；带 `or`、`unknown`、近似/问号或转换箭头的歧义单位拒绝；
- 多对象 Claim 必须提供显式 `comparison_basis`；
- raw text 含否定标记时 normalized text 必须保留否定；
- conditions、scope、limitations、qualifiers 和 uncertainty 原样保留，不合并。

duplicate 使用上述规范结构的 canonical SHA-256 fingerprint，覆盖 text、
normalized text、type、polarity、objects、metric/unit、conditions、scope、
limitations、qualifiers、uncertainty 和 comparison basis。不同对象或条件产生不同
fingerprint；不使用模糊文本相似度。

## 6. Hash 与追踪

复用 `app.schemas._hashing.compute_canonical_payload_hash`：

- `input_hash` 覆盖 PaperSummary Version/schema/output hash、Summary/Paper、
  SourceSnapshot versions、Prompt/model/parameters、producer 和 normalization 版本；
- valid `model_response_hash` 将 JSON keys 规范化，并把 Claim 批次按结构化内容排序；
- `output_hash` 覆盖准入后的 Claim、Evidence references、状态、拒绝原因和版本；
- execution/run id、wall-clock、latency 和 producer output hash 自引用不进入稳定
  content hash。

因此相同版本化输入产生相同 hash；Prompt、parameters 或输入 ArtifactVersion 变化会
改变 input/output hash。随机 id、时间戳和 Claim 集合遍历顺序不会破坏稳定性。
ArtifactVersion admission 另对准备持久化的完整 JSON 计算 `content_hash`；该 hash
覆盖嵌入的审计字段，和稳定 `output_hash` 职责不同，不要求相等。持久化边界使用
admitted `content_hash` 对照数据库 ProducerExecution。

## 7. 固定 Benchmark

`services.paper_pipeline.claim_benchmark` 只读取 tracked 冻结 `1.3.0`
Package，校验其 schema/version/scientific payload/content 四项 pin，并动态遍历其中
全部 `review_status=approved` 的 Claim 标签。默认 CLI 通过
`claim_benchmark_cases.build_frozen_claim_benchmark_cases` 确定性派生准入输入，不调用
线上模型、不修改基准包，也不依赖 ignored `.artifacts` 输入：

```powershell
uv run --project apps/api python -m services.paper_pipeline.claim_benchmark `
  --cases-output .artifacts/literature-claim-benchmark-cases.json `
  --output .artifacts/literature-claim-benchmark-report.json
```

冻结的 `1.3.0` 实际有 8 条适用于 Claim Pipeline 的 approved Claim（method 3、dataset 2、
limitation 2、finding 1）；生成器逐条产生科研标签 case，并从同一 tracked 包派生
invalid JSON、ownership、Evidence missing、duplicate 四类负例。正式 CLI 要求科研
case id 与全部 approved Claim 一一对应；`--cases` 只用于重放已序列化的完整 suite，
不能提交子集。`--cases-output` 是可选审计输出，不是运行前置输入。

四个指标都同时保存分子、分母和 rate：

- `schema_pass_rate`：通过 JSON 与 `LiteratureClaimExtractionOutput` Pydantic 的 case /
  全部 case；正式 suite 非空；
- `rejection_case_pass_rate`：实际 `rejected` 且 failure stage/reason 都精确命中预期的
  负例 / 全部 `rejection_case`；无负例时为 `null`；
- `evidence_coverage_rate`：进入科研标签比较的 Schema-valid Claim 中，Publisher
  candidate 保留且状态为 `supported` 的 Evidence reference / 这些 Claim 声明的全部
  Evidence obligation；分母为零时为 `null`；
- `scientific_label_exact_match_rate`：paper/type/raw text/normalized
  text/conditions/Evidence/status 与 approved 标签全字段 exact match / 仅
  `scientific_label`、Schema-valid 且存在可比较 record 的 case；无适用科研 case 时为
  `null`。invalid JSON、ownership、Evidence missing、duplicate 等负例不进入该分母；
- `sample_count`、`claim_type_counts` 记录总样本和已比较科研标签类型；
- `status_counts`：accepted/candidate/rejected case 数；
- `rejection_counts`：按稳定拒绝枚举聚合的数量和排序后 case id；
- 每个 case 的 input/output hash 以及 report input/output hash。

case、类型、拒绝原因与序列化 key 均稳定排序；report content hash 不包含 execution
id、时间戳或 latency。exact match 只是对既有人工审核标签和 admission 行为的
回归，不是线上模型科学质量、泛化能力或新科学结论指标。

## 8. Relation、持久化与读取边界交接

- [LiteratureRelation Pipeline](LITERATURE_RELATION_PIPELINE.md) 直接接收经过封印的 `LiteratureClaimsCandidate`；只把 status 为 candidate 或 accepted 的 Claim
  送入稳定 pairing。它使用 objects、metric、unit、conditions、scope、limitations、
  Evidence/SourceSnapshot 和 Summary version 做可比性与 provenance 校验，不复制或
  重做 Claim admission。
- 依赖输出的唯一发布交接是同时内嵌 Relation 与 `LiteratureReasoningTraceCandidate` 的
  `LiteratureRelationsCandidate@1.0.0`。单条 Relation、Trace、模型 extraction、读取包络和重解析批次不能替代该封印对象。
- 持久化边界接收完整 `LiteratureClaimsCandidate`，重新验证 Pydantic、Pipeline seal、
  schema/input/output hash 和 Evidence references 后调用 ArtifactVersion Publisher。
  读取边界提供 version-pinned HTTP projection；两者都不复制 Claim Schema 或重做
  Claim admission。

## 9. 验证

普通测试只使用 fixture/stub：

```powershell
uv sync --project apps/api --frozen
uv run --project apps/api pytest apps/api/tests/test_literature_claim_pipeline.py
uv run --project apps/api pytest
```

针对性测试覆盖四类 Claim、三态、全部稳定拒绝原因、优先级、normalization、
duplicate、hash 漂移/稳定、Publisher seal、全部 approved 标签、四项 Benchmark
分母/空子集、CLI 生成与排序。tracked Schema 使用文档中的正式 export/`--check`
命令验证；core contracts 仍执行 `sync-contracts`，且不在本 Pipeline 中新增 HTTP DTO。

## 10. 明确非目标

本 Pipeline 不实现 Relation、ReasoningTrace、Graph、HTTP endpoint/DTO、前端、数据库
ArtifactVersion 事务、ResearchRun 推进、生产模型 client、Agent 平台或自由代码执行。
不保存原始模型长输出、受限全文、凭据或 chain-of-thought，也不复制或注册 MAVIS
Prompt。
