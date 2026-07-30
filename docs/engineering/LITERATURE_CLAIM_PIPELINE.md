# LiteratureClaim Pipeline

| 元数据       | 值                                                                 |
| ------------ | ------------------------------------------------------------------ |
| Status       | Implemented                                                        |
| Authority    | D-07 LiteratureClaim 抽取、规范化、准入、固定 Benchmark 与交接边界 |
| Implementation | detached Claim admission 与 publisher-ready typed candidate Current；生产模型、Workflow/数据库发布、HTTP 读取 Pending |

本文是 D-07 运行规则和操作方式的唯一完整事实源。Claim 字段与不变量仍由
[Data Model](../architecture/DATA_MODEL.md) 负责，ArtifactVersion/hash 规则由
[Data Versioning](../architecture/DATA_VERSIONING.md) 负责，跨文献 Relation 规则由
[Reasoning Protocol](../ai/REASONING_PROTOCOL.md) 负责。

## 1. 输入、输出与模块入口

运行入口是 `services.paper_pipeline.claim.LiteratureClaimPipeline`。它接收：

- `PaperSummaryArtifactVersionInput` repository-port 值；其中 content 必须已经通过
  D-03 `PaperSummaryArtifactContent` Pydantic 校验；
- 请求的 PaperSummary ArtifactVersion id 和 paper id；
- `literature_claim@v1` Prompt 对应的模型 JSON 响应；
- model、parameters version、安全 parameters；
- 可选的 Evidence/SourceSnapshot 存在性集合和既有 Claim fingerprint。

输出 `LiteratureClaimAdmissionResult`。结果始终包含 ProducerExecution、
PaperSummary input reference、input/model-response/output hash；JSON/Schema 失败不
伪造 Claim。Schema-valid 记录包含 raw/normalized text、claim type、polarity、
objects、metric/unit、conditions、scope、limitations、qualifiers、uncertainty、
Evidence/SourceSnapshot、状态和稳定拒绝原因。

只要批次中至少有一条 `candidate` 或 `accepted` Claim，结果同时提供经过 Pipeline
封印的 `LiteratureClaimsCandidate`。该类型可以直接交给 #78 structured publisher
admission port；D-07 自身不创建数据库 ArtifactVersion。

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

| 阶段 | 稳定拒绝原因 |
| ---- | ------------ |
| JSON | `literature_claim.json_invalid` |
| Schema | `literature_claim.schema_invalid` |
| input | `literature_claim.input_artifact_version_unknown`、`literature_claim.input_schema_version_unsupported` |
| Evidence | `literature_claim.evidence_missing`、`literature_claim.evidence_not_found`、`literature_claim.source_snapshot_not_found` |
| ownership | `literature_claim.ownership_mismatch` |
| normalization | `literature_claim.normalization_unsafe` |
| duplicate | `literature_claim.duplicate` |

JSON/Schema 失败产生无 Claim record 的统一 rejected result；后续阶段只处理已经通过
唯一 model-output Schema 的结构化记录。

## 3. 状态语义

- `accepted`：输入版本、ownership 和 normalization 全部通过，且每条绑定 Evidence
  均由 D-03 标记为 `supported`；
- `candidate`：结构与 provenance 完整，但至少一条绑定 Evidence 为
  `unsupported` 或 `unverifiable`；
- `rejected`：命中上表任一稳定拒绝原因。

状态不使用 confidence、文本相似度或 hash 相同来宣称科学正确性。全 rejected
批次没有 publisher candidate；混合批次保留 rejected record 作为审计，但下游
Relation 输入只能选择 candidate/accepted Claim。

## 4. Schema、Prompt 与版本

唯一 Pydantic 编写源是
`apps/api/src/app/schemas/literature_claim.py`。中间模型
`LiteratureClaimExtractionOutput` 不能绕过 D-07 直接进入 Publisher；完整
`LiteratureClaimsCandidate@1.0.0` 才是领域 typed candidate。

生产 Prompt 位于 `packages/prompts/literature_claim/v1.md`，通过
`packages/prompts/registry.json` 的 immutable hash-pinned record 加载。Prompt 要求：

- 每条 Claim 指向一个明确 Summary statement 及其 Evidence；
- finding、method、dataset、limitation 使用契约枚举；
- 不合并不可比较对象、指标、数据集、样本或实验条件；
- 保留方向、否定、conditions、scope、limitations、qualifiers 和 uncertainty；
- 只输出 JSON，不输出 confidence、Relation、ReasoningTrace、Graph 或私有推理。

ProducerExecution 固定记录 Prompt/schema/model/parameters/producer/normalization
版本。parameters 复用 D-03 安全标量和敏感键拒绝策略。

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

## 7. 固定 Benchmark

`services.paper_pipeline.claim_benchmark.evaluate_literature_claims` 只读取冻结 D-01
`1.3.0` Package 及其中 `review_status=approved` 的 Claim 标签，不调用线上模型，
不修改 Benchmark，不编造科研正确性标签。CLI 接收已经序列化的
`LiteratureClaimBenchmarkEvaluationCase[]`：

```powershell
uv run --project apps/api python -m services.paper_pipeline.claim_benchmark `
  --cases .artifacts/d07-claim-cases.json `
  --output .artifacts/d07-claim-benchmark-report.json
```

报告字段：

- `sample_count`、`claim_type_counts`：样本总数和冻结标签分类；
- `schema_pass_rate`：通过 JSON/Pydantic 的 case / 全部 case；
- `evidence_coverage`：D-03 supported Evidence references / 全部 Claim Evidence
  references；分母为零时是 `null`；
- `scientific_review_accuracy`：与 D-01 approved Claim 的 paper/type/raw
  text/normalized text/conditions/Evidence/status 全字段 exact match / 全部 case；
- `status_counts`：accepted/candidate/rejected case 数；
- `rejection_counts`：按稳定拒绝枚举聚合的数量和排序后 case id；
- 每个 case 的 input/output hash 以及 report input/output hash。

exact match 是对既有人工审核标签的回归指标，不表示 hash 或字符串匹配本身证明科学
正确。

## 8. D-08 / B-08 交接

- D-08 直接导入 `LiteratureClaimsCandidate.claims`，只把 status 为 candidate 或
  accepted 的记录送入 Relation pairing；使用 objects、metric、unit、conditions、
  scope、limitations、Evidence/SourceSnapshot 和 Summary version 做可比性与
  provenance 校验。
- B-08 接收完整 `LiteratureClaimsCandidate`，重新验证 Pydantic、Pipeline seal、
  schema/input/output hash 和 Evidence references 后调用 #78 Publisher。B-08 负责
  ArtifactVersion persistence 与 version-pinned HTTP projection，不复制 D-07 Schema
  或重做 Claim admission。

## 9. 验证

普通测试只使用 fixture/stub：

```powershell
uv sync --project apps/api --frozen
uv run --project apps/api pytest apps/api/tests/test_literature_claim_pipeline.py
uv run --project apps/api pytest
```

针对性测试覆盖四类 Claim、三态、全部稳定拒绝原因、优先级、normalization、
duplicate、hash 漂移/稳定、Publisher seal、D01 Benchmark 字段与排序。

## 10. 明确非目标

D-07 不实现 Relation、ReasoningTrace、Graph、HTTP endpoint/DTO、前端、数据库
ArtifactVersion 事务、ResearchRun 推进、生产模型 client、Agent 平台或自由代码执行。
不保存原始模型长输出、受限全文、凭据或 chain-of-thought，也不复制或注册 MAVIS
Prompt。
