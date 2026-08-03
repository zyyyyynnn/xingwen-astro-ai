# C-05 Data Quality Evaluation

| 元数据 | 值 |
| --- | --- |
| Status | Proposed |
| Authority | C-05 分层质量指标、Evidence 覆盖、Contract gate 与 Publisher handoff |
| Issue | [#35](https://github.com/zyyyyynnn/xingwen-astro-ai/issues/35) |

## 1. 边界

C-05 消费 C-04 的三个领域 candidate、`DataArtifactBuildInput`、C-08
`CrossmatchResult`、冻结 Case/Field Manifest 和 `ResearchContract`，生成
`DataQualityEvaluationResult` 或结构化 rejected outcome。它只衡量处理完整性、
可追溯性和交接条件，不代表科学结论正确率；不调用 HTTP、数据库、C-04
builder 或 C-08 engine，也不分配 `ArtifactVersion`、推进 Run 或发布 HTTP DTO。

Pydantic 编写源是 `apps/api/src/app/schemas/data_quality.py`；实现位于
`services/data_pipeline/data_quality/`。`data_quality` 是 C Pipeline typed
result discriminator，不是 Core `ArtifactKind`。

## 2. 冻结输入与 RuleSet

`DataQualityEvaluationInput` 的字段为：

- `data_artifact_input`；
- `dataset_candidate`、`field_dictionary_candidate`、`source_collection_candidate`；
- `research_contract`；
- `quality_rule_set`；
- C-05 `input_hash`。

公共入口第一步把 caller 输入重新序列化并通过 Pydantic 校验，因此
`model_construct()` 或 post-validation corruption 不会进入指标计算。随后它调用
C-04 独立 candidate/input validator，核对三类 candidate 的共同 pins、mapping
RuleSet、conversion Catalog、producer、C-04 input hash、requested fields、
SourceSnapshot、Evidence、Crossmatch identity、完整 acquisition records 和
`quality_evaluation_status=not_evaluated`。

`services/data_pipeline/manifests/exoplanet_host_star/quality-rules/quality-rules.v1.json`
是唯一生产 RuleSet。它绑定 C-02/C-04/C-08 schema 与内容 hash、producer、Decimal
precision、`ROUND_HALF_EVEN`、plain decimal serialization、公式注册表、适用范围、
不完整来源/空 denominator policy、Contract bindings、`pass_only` Publisher policy
和容量上限。caller 即使修改内容并重算 self-hash，也必须与仓库实例完整等值，
否则返回 `QUALITY_RULE_SET_MISMATCH`。

C-05 input hash 覆盖 C-04 input/candidate/C-08/Contract/RuleSet/Snapshot/Evidence
和 producer identity；排除 wall-clock、日志、分支、数据库 ID、ArtifactVersion
number、Publisher hash 与 private seal/context。

## 3. 指标语义

指标使用闭合公式 ID，不执行任意表达式。每项包含 metric id、scope、target、
formula id/version、整数 numerator/denominator、Decimal value、threshold、
threshold source 和 input locator。状态只有 `determinate`、`insufficient`、
`not_applicable`：

- `determinate` 要求 denominator > 0，value 使用冻结 Decimal policy 重算；
- `not_applicable` 使用空 denominator，不填 0 或 1；
- `insufficient` 保留已观察的计数但不伪造 value，主要用于来源范围不完整。

Completeness 的 denominator 只来自 `DatasetRow.projected_field_ids`；每个适用
cell 只能是 `mapped`、`declared_null` 或 `unresolved`，三者计数必须闭合。
`not_in_source` 等声明缺失保留其 null reason。inconclusive 不折算为 unmatched
或普通 missing。

结果固定提供 per-field、per-row、per-dataset 质量：completeness、missingness、
unresolved、provenance/Evidence coverage、unit consistency、same/cross-source
conflict，以及 dataset 的 object match coverage、low-confidence edge、
review-required、inconclusive、source-scope completeness 和 validation integrity。
Field Manifest 的 `quality_metric_inputs` 是字段维度唯一适用性事实源；C-05 不复制
字段—指标矩阵。

Evidence coverage 要求 mapped cell 的 selected SourceValue、全部 retained
candidate 和 Transformation Evidence 均有闭合 locator/Snapshot；C-08 的 paired/
conflict audited record 使用 Crossmatch Evidence。unmatched/inconclusive unpaired
record 没有 Crossmatch Evidence 时标记为不适用，不伪造 Evidence gap。locator 或
Snapshot 必需但缺失时拒绝或显式 gate failure，不用低分掩盖。

Crossmatch 指标只从 `data_artifact_input.crossmatch_result` 读取，并重新调用已有
`compute_crossmatch_metrics` 比对结果；不重新运行 engine。unit consistency 只对
Manifest 声明该维度的字段计算；错误单位、quantity kind 或换算属于 C-04 admission
错误，而不是 C-05 低分。

v1 aggregate score 固定关闭，`aggregate_score=null`、weights 为空，Publisher 不
消费汇总分。启用汇总分必须新增 RuleSet 版本与批准的权重来源。

## 4. ResearchContract gate

`ResearchContractQualityGate` 为每个 binding 保存 constraint id、source field、
metric、observed status/value、threshold、operator、RuleSet binding version 和
input locator。它检查 source completeness、unit consistency、Evidence minimum
coverage、locator/Snapshot requirement、canonical unit policy、requested fields
和 provider-level source scope（通过 Manifest 映射到实际 table source）。

整体规则是：任一明确 fail 则 `fail`；无 fail 但存在不足则 `insufficient`；全部
必需检查通过才 `pass`。`fail` 与 `insufficient` 都保留 typed result，但 Publisher
只接受 `pass`。

## 5. Publisher handoff

`admit_data_artifact_quality(...)` 是 process-local admission。它绑定原始 sealed
C-04 candidate 对象、immutable C-05 input JSON、quality result/hash、Contract、
RuleSet、candidate IDs/input/output hashes、Dataset canonical/lineage hash、
Snapshot/Evidence 引用和 bundle commitment。`build_data_quality_publication_validator`
供真实 `app.workflow.publisher.admit_artifact_candidate` 使用：检查 exact object
identity、C-04 seal、references，重新解析 immutable input，重新计算质量与 gate，
并要求结果完全相等且 gate pass。它不访问数据库、不调用 C-04 builder 或 C-08
engine；copy/reparse/foreign candidate 不会恢复发布权限。

## 6. 数据等级与验证

固定 crossmatch benchmark 是 synthetic fixture，不是科学 ground truth。Fixture、
Recorded、Live、Cached、Revision 不能混淆；本实现不运行公网 Live smoke。

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest -q tests/test_data_quality_contract.py tests/test_data_quality_pipeline.py tests/test_data_quality_publisher_port.py
Set-Location ../..
```
