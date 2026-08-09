# Data Quality Evaluation

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 分层质量指标、Evidence 覆盖、Contract gate 与 Publisher handoff |

## 1. 边界与唯一事实源

质量评估消费已经通过字段映射与实体对齐边界的三个 typed candidate、
`DataArtifactBuildInput`、冻结 Manifest、`CrossmatchResult` 和
`ResearchContract`，产生 `DataQualityEvaluationResult` 或结构化 rejected
outcome。它只负责确定性质量算法、typed result、Contract gate 和 Publisher
质量交接；不实现 mapping、crossmatch engine、HTTP、数据库、ArtifactVersion、
Workflow、CacheSelector、前端或科学真实性判定。

`apps/api/src/app/schemas/data_quality.py` 是公共 Pydantic Schema authoring
source。`quality-rules.json` 是唯一版本化 RuleSet。入口先校验 RuleSet 自身
hash，再由 `compile_quality_evaluation_plan()` 把冻结 RuleSet 编译为不可变
`QualityEvaluationPlan`。执行、gate、结果闭包和 admission 都消费同一个 plan；
不得在 Python 中另行维护公式选择或 Contract gate 清单。

计划固定绑定：RuleSet identity、Decimal precision/serialization、每个 metric
的 scope/result field/formula/version、封闭的 formula kind、numerator observation、
denominator observation、适用范围、空 denominator 策略、不完整来源策略，以及每个
gate 的 metric target、threshold Contract locator、operator、observation key、
binding version 和输入 locator。计划本身也有 canonical `content_hash`。三层
builder 只组装 observations 和 typed result；统一 plan interpreter 负责公式计数、
适用性、空 denominator 与 incomplete-source 状态，不允许 builder 提前改写状态。
observations 对 `rows -> outcomes` 只遍历一次，在同一遍内累积 field、row、dataset
counters；null reason 直接合并计数，不按 count 展开中间集合。复杂度由既有
row/cell/SourceValue/edge 容量约束，而不是隐含的重复 field scan 决定。

## 2. Contract 与输入绑定

`ResearchContract.content_hash` 使用 Core/Contract 边界的生产内容身份算法：完整
持久化 Contract 先精确投影为 `ResearchContractInput`，再对该输入内容做 canonical
hash。`id`、`project_id`、`version`、`created_from_draft_id`、`created_at` 等持久化
元数据不参与内容身份；质量评估不重新定义 Contract hash。Contract 确认流程、持久化
读取校验与质量评估都调用同一算法。质量评估在计算任何指标或 gate 前验证该 hash，随后
才绑定质量阈值、requested fields、source scope、Evidence requirements 和 unit
policy。修改 Contract 内容后保留旧 hash，或只重算外层 quality `input_hash`，都只能得到
`QUALITY_RESEARCH_CONTRACT_MISMATCH`。

Contract 内容身份保留生产输入的 canonical 序列语义；字段映射的 requested field
顺序仍由其 Manifest 投影决定，而质量绑定和 Contract gate 明确使用字段集合
等价语义。合法的多字段顺序差异不会 fail，但重复字段和字段集合差异仍会拒绝。

## 3. 指标闭包与状态

每个结果 metric 保存 `metric_id`、scope、target、formula id/version、formula
scope、precision、整数 numerator/denominator、Decimal value 和 input locator。
阈值不属于原始 metric：`QualityMetricResult` 不再有无语义的 `threshold` 或
`threshold_source`；阈值只在 `QualityConstraintResult` 中，由 plan 的
`contract_path` 从已验证 Contract 读取。

指标状态只有：

- `determinate`：适用且 denominator 大于零，value 必须由冻结 precision 重新计算；
- `insufficient`：来源范围不完整或其他充分性条件未满足，只保留观察计数，不伪造 value；
- `not_applicable`：该层/目标不适用或空 denominator，使用空计数，不把“不适用”写成零。

不同语义使用不同 metric/formula/scope：

- field 层分别计算 same-source 与 cross-source conflict；
- row 层的 low-confidence、review-required、inconclusive 是独立的 0/1 flag
  metric。low-confidence 只允许实体对齐结果提供可解释 confidence band 的 paired row
  进入分母；review-required 使用独立的 paired/conflict adjudicable 分母；
  inconclusive 只适用于 unpaired row。它们不复用 dataset rate 公式；
- dataset 层保留对应的 edge/record rate，另有 object match、source-scope 和
  validation integrity 指标。

row low-confidence 不比较 edge logical key、record logical key 或 Evidence ID。
实体对齐结果使用 candidate membership 和 connected component 语义提供权威
record-to-edge component 投影，质量评估只消费该投影；因此 row flag 与 dataset
low-confidence edge 计数来自同一组真实 edge。ConflictGroup 的 confidence
为 `not_applicable`，因此不输出确定的 `low_confidence=false`；unpaired row 同样
不适用。row review-required 只读取字段映射边界冻结的最终 `alignment_status`：
`review_required`/`conflict` 为 true，已经裁决的 `accepted`/`rejected` 为 false，
unpaired row 不适用；ConflictGroup 本身不构成无条件待审查判定。

unit consistency 的计数粒度固定为 retained non-null `SourceValue` assertion，而非
mapped cell：denominator 是具有 unit policy 的 retained non-null assertions，
numerator 是其中 canonical unit 与字段定义一致的 assertions。一个 mapped cell
保留多个来源 assertion 时会贡献多个计数，formula definition 与 observation ID
显式使用 assertion 语义。

RuleSet 的 `incomplete_source_policy=insufficient` 对所有三层适用 metric
一致传播：completeness、missingness、provenance、Evidence、unit、conflict、
object-match、low-confidence、review-required、inconclusive、source scope 和
validation integrity 都不能在来源不完整时输出 determinate。真正不适用的目标
仍保持 `not_applicable`。`aggregate_score` 固定关闭，质量结果不能被描述为
科学真实性、科学正确率或 ground truth score。

结果 Schema 还校验领域闭包：result ID 与 input/RuleSet 绑定，field/row 精确覆盖，
dataset result IDs 精确引用两层结果，metric 的 scope/formula/target 与 plan
一致，RuleSet binding 集合和顺序完整，Snapshot/Evidence 引用在顶层与嵌套结果
中闭合，Contract gate 完整覆盖全部 bindings，并复算各层 content/output hash。

`max_metric_records` 只限制实际公共输出记录数，即 field result 数乘 field-plan
metric 数、row result 数乘 row-plan metric 数、dataset-plan metric 数和 gate binding
数之和。等于上限允许，超过上限以 `QUALITY_CAPACITY_EXCEEDED` 稳定拒绝；
cell、SourceValue、Evidence、conflict reference 和 edge 工作量继续由各自独立容量
限制，不借用 metric output 容量做估算。

## 4. ResearchContract gate

gate 只遍历 plan 的 `gate_bindings`。metric gate 从 dataset result field 读取
观测值，从已验证 Contract 的 `contract_path` 读取 threshold；boolean gate 只
记录 `not_checked`，不伪造 metric observation。`operator`、not-applicable 结果、
Contract locator 和 binding version 都由 plan 驱动。整体状态固定按
`fail > insufficient > pass` 聚合，Publisher 只接受 `pass`。

来源不完整会同时使 raw metric 与依赖它的 threshold gate 进入
`insufficient`，而不是用部分数据生成看似确定的 pass/fail。Evidence locator、
SourceSnapshot、source scope 和 unit policy 仍分别执行其明确的 boolean gate。

Evidence 完整性属于字段映射 candidate admission：质量评估首先按冻结 input 重建并
精确校验 candidate，缺失 Transformation/Crossmatch Evidence 的 payload 在进入
observations 前即以 `QUALITY_DATA_ARTIFACT_CANDIDATE_MISMATCH` 拒绝。质量评估不维护不可达的
`QUALITY_EVIDENCE_GAP` 二次分支；Evidence coverage metric 与 gate 只审计已经通过
字段映射/实体对齐 admission 的覆盖计数，来源不完整时按 plan 传播 `insufficient`。

## 5. Process-local admission 与 Publisher

`admit_data_artifact_quality()` 绑定原始 sealed mapping candidate 对象、immutable
quality input JSON、canonical typed result、Contract/RuleSet identity、candidate
payload/reference、Snapshot/Evidence 引用，并在 admission 内调用可信 evaluator
一次。传入的 result 即使引用和 content/output hash 自洽，只要与这一次 canonical
evaluator 输出不同就拒绝；只有 canonical result 且 Contract gate 为 `pass` 才会
形成不可变 evaluation commitment。

commitment 绑定 result id、input/output/content hash、plan hash、Contract/RuleSet
identity，并嵌入 mapping/quality bundle commitment。Publisher quality validator 不再
重复运行质量评估；它只验证 exact candidate object、mapping seal、候选 payload/hash、
Snapshot/Evidence context 和 commitment/reference 闭包。质量评估不推进数据库版本、
Run 或事务。

## 6. 验证入口

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest -q tests/test_data_quality_contract.py tests/test_data_quality_pipeline.py tests/test_data_quality_publisher_port.py tests/test_data_quality_root_cause_regressions.py
Set-Location ../..
```

根因回归覆盖 formula scope mismatch、生产 Contract 确认/读取兼容与 hash drift、
三层不完整来源传播、多字段顺序等价、实体对齐 edge component 的 row 定位、Conflict
confidence/review 适用性矩阵、精确 metric capacity 边界、single-pass observations、
Evidence gap 的字段映射归属、unit assertion 粒度、plan 公式计数/空 denominator/
incomplete policy、伪造 result admission、结果领域闭包和 Publisher 单次评估
commitment。
