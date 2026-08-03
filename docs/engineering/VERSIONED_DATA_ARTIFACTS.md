# Versioned Data Artifacts

| 元数据 | 值 |
| --- | --- |
| Status | Proposed |
| Authority | C-04 字段映射、单位统一、Transformation Evidence 与 typed Artifact candidate 运行规范 |
| Issue | [#34](https://github.com/zyyyyynnn/xingwen-astro-ai/issues/34) |

## 1. 范围与边界

C-04 消费已经完成的 TOI/PS acquisition 投影与 C-08 `CrossmatchResult`，按冻结 Manifest 生成 `DatasetArtifactCandidate`、`FieldDictionaryArtifactCandidate` 和 `SourceCollectionArtifactCandidate`。公共入口是：

```python
build_data_artifact_candidates(
    input: DataArtifactBuildInput,
) -> DataArtifactBuildResult
```

`DataArtifactBuildResult` 是进程内编排返回值；公共可序列化 Contract 是三个 typed candidate 与对应的输入/策略模型。

实现位于 `services/data_pipeline/data_artifacts/`，唯一 Pydantic Contract 编写源位于 `apps/api/src/app/schemas/data_artifacts.py`。科学 hash 投影位于 `app.schemas.data_artifact_identity`，process-local seal 位于 `app.schemas.data_artifact_seal`；二者都不定义或导出另一套 JSON Contract。C-04 不访问 NASA endpoint，不重新运行 Adapter/Crossmatch，不访问数据库，不分配 `ArtifactVersion`，不推进 Run，不发布 HTTP DTO，也不计算 C-05 质量分。

## 2. 输入与冻结策略

`DataArtifactBuildInput` 绑定 Case/Field Manifest pins、左右 acquisition 的 records/Snapshot/mode/data level/completion、C-08 结果、requested canonical fields、`MappingRuleSet`、`UnitConversionCatalog`、producer version、可选质量约束引用和稳定 `input_hash`。左右来源、Snapshot、record set、row key 与 raw-record hash 必须与 C-08 引用精确一致；来源列名不能冒充 canonical field ID。

公共入口同时执行两层真实性绑定：

- `policy.py` 从仓库 JSON 加载冻结 C-04 MappingRuleSet/UnitConversionCatalog，并对 caller 对象做完整 Pydantic 等值比较；仅重算 caller 的 policy hash 与 input hash 不能形成新的获准执行策略。
- C-08 handoff 的 embedded RuleSet、EntityAliasCatalog、SourcePolicy、top-level IDs/hashes 与 producer 必须完整等于 #158 的仓库冻结策略；内部自洽但由 caller 改写的 CrossmatchResult 会稳定拒绝。

当前 C-04 规则文件位于 `services/data_pipeline/manifests/exoplanet_host_star/mapping-rules/`：

- `mapping-rules.v1.json`：执行顺序、row-grain 投影矩阵、冲突/缺失策略、集合数值比较和容量边界；不复制字段 alias、priority、unit 或 companion columns。
- `unit-conversions.v1.json`：Manifest declaration-only conversion 的唯一执行因子与 Decimal 容量目录。

Field alias、source priority、alias priority、null、uncertainty、limit、unit 和质量输入只读取 Field Manifest。`pscomppars` 虽在 Manifest 中声明，但没有 acquisition/C-08 member 时不会产生伪造来源值。

## 3. 数值与单位

换算使用 `Decimal`、28 位精度、`ROUND_HALF_EVEN` 上下文和无指数 plain-decimal JSON 字符串；不进行隐式量化。所有 canonical 数值零（包括 `-0`、`-0.0` 与带 exponent 的负零）统一序列化为 `0`。Catalog 版本化限制输入文本长度、significant digits、adjusted exponent、fractional scale 和最终 plain string 长度，并在物化极端长字符串前 fail closed。初版只实现 Manifest 已授权的 identity、Jupiter radius → Earth radius、Jupiter mass → Earth mass。identity 要求来源/目标单位相同，所有规则同时核对 ID、版本、单位对和 quantity kind；NaN、Infinity、bool、非法数字与超容量数字均稳定拒绝。

raw value 仍按来源原样保留用于 lineage，因此 raw-record/input/Publisher content hash 可以区分 `0.0` 与 `-0.0` 等来源表示；该差异不改变 canonical value。不得把 canonical zero policy 解释为删除或重写原始 provenance。

半径与质量比例来自 [IAU 2015 Resolution B3](https://arxiv.org/abs/1510.07674) 的精确 nominal equatorial radii 与 nominal mass parameters：

- `71492000 / 6378100 = 11.20898073093868079835687744`
- `126686530000000000 / 398600400000000 = 317.8284065946747670097671753`

主值与 uncertainty 使用同一比例。catalog 保存 numerator、denominator、来源、版本和 content hash，Python 分支不复制常数。

## 4. 值、缺失、误差和 limit

每个 `SourceValueCandidate` 同时保留 raw/canonical value、单位、Snapshot/query/row/record/raw-field locator、source/alias priority、转换版本、reference/provenance 文本、uncertainty、limit、null status 和 content hash。reference/provenance 是不可信来源文本，不执行或解释为 HTML。

字段输出是 `mapped | declared_null | unresolved` 判别联合：

- nullable 且 raw field 为 null 时使用 Manifest 允许的 `not_measured`；来源没有适用 alias/value 时使用 `not_in_source`；
- 非 nullable字段没有安全值时稳定失败，不填 0 或空字符串；
- review/rejected/conflict identity 不按 source priority 重新裁决，而是保留 unresolved 行；
- truncated/unknown 对侧的 `inconclusive` 不改写为 `unmatched`。

非对称 uncertainty 分别保留原始符号和转换值，单侧缺失不补 0；locator 可区分 companion 不在 record 与存在但为 null。limit 只解析 Manifest 的 `measured/lower_limit/upper_limit` flag，未知类型/值和无主值的 bound 稳定失败，换算后 limit 类型不变。

## 5. Dataset row grain、选择与 Crossmatch 消费

每条 C-08 record 形成一个带 `entity_level`、projection policy version 和精确 `projected_field_ids` 的稳定 row。冻结矩阵如下；Pipeline 在读取 raw value 前执行兼容性判断，不兼容字段不会生成 outcome，也不会伪装成 `not_in_source`：

| Dataset row grain | 允许的 `FieldDefinition.object_type` | 语义 |
| --- | --- | --- |
| `host_star` | `star`、`system` | 宿主与系统位置上下文；禁止 `planet.*` |
| `planet_candidate` | `planet` | TOI candidate 自身；不从共行原始列隐式连接宿主上下文 |
| `planet_assertion` | `planet`、`star`、`system` | 单条 PS assertion 及该 assertion 明确携带的来源上下文 |

`system.*` 只进入 `host_star` 与来源 assertion，不任意传播到 `planet_candidate`。accepted paired/adjudication 只合并同一 C-08 row grain 的 members；review-required、rejected、conflict-group 保留 member 与 C-08 Evidence 但不伪装为确定实体；unpaired 保留 entity level、completion scope 和 `unmatched | inconclusive`。对象 identity 字段直接消费 C-08 已验证的 normalized identity value，不重新运行 identity 算法；相同 TIC 只确认 host identity，不能把 TOI candidate 与不同 `pl_refname` 的 PS assertions 合成一个 planet row。unresolved/review/conflict identity 也不能借字段投影形成隐式 merge。

字段候选按 Field Manifest 的 source priority、alias priority、stable source-value ID 排序。最高优先级只决定展示值，所有低优先级值和 provenance 均保留；不同 canonical value 形成 `FieldConflictRecord`，并由 `FieldSelectionRecord` 记录 row/field、候选集合、策略与原因。numeric conflict 与 selection priority 无关：absolute tolerance 使用集合 `max-min`，relative tolerance 使用 `span / max(abs(max), abs(min), relative_denominator_floor)`；absolute/relative 任一满足即一致，阈值包含性由冻结规则控制。identity conflict 不受字段 source priority 覆盖。

## 6. Evidence、候选、replay 与 hash

`TransformationEvidence` 将 dataset row/field/source value 绑定到 raw cell、raw/canonical value、uncertainty/limit、reference/provenance 值与 locator、conversion catalog、C-08 result/logical key/Evidence 和 selection 状态。`projection.py` 是唯一领域派生源：它只从 canonical `DataArtifactBuildInput`、冻结 Field Manifest、MappingRuleSet、UnitConversionCatalog 与 C-08 `CrossmatchResult` 生成不可变 `DataArtifactDomainProjection`。该投影封闭 rows/entity projection、完整 SourceValue/raw locator/canonical value/unit/uncertainty/limit/null、Evidence、source/alias priority、selection/conflict 与 SourceCollection acquisition exact set。

`pipeline.py` 只把领域投影序列化成三个候选，不拥有 selection、uncertainty、limit 或 conflict 算法。`admission.py` 不调用该装配器，也不读取候选已有集合来推测期望值；它从 immutable input 重新派生一份领域投影，然后对 rows、SourceValue、Evidence、selection、conflict、FieldDictionary 和 SourceCollection 做完整等值准入。因此 producer 漏值、选错 winner、改写 null/uncertainty/limit、改变 row member/alignment 或隐藏 conflict 都会在 seal 前拒绝。Pydantic 模型只负责可序列化类型、局部结构与 registry closure；领域真实性由 projection/admission 负责。

三类候选共享精确 Manifest/policy/catalog/producer/input/Snapshot/Evidence pins。公共入口先完成独立领域准入，再以不可变 process-local `DataArtifactAdmissionSnapshot`（canonical input JSON、冻结策略 commitment、bundle commitment）绑定完整公开 payload，最后写入带 object id、candidate/input/output/public-payload/context/bundle commitment 的 publication seal。Publisher gates 只从该 snapshot 重新解析输入并调用独立 validator，不执行候选装配器。同步修改 SourceValue、Evidence、outcome、hash、context 或跨 build 移植字段都会在 seal 或独立准入阶段拒绝；copy/reparse 只得到领域内容有效的 Contract，不恢复 seal/context，也不具 publication 资格。

- Dataset：columns、rows、判别字段 outcome、全部 source values、Evidence、selection/conflict 和 C-05 metric input 声明；不含 quality score。
- FieldDictionary：requested fields 对 Field Manifest `FieldDefinition` 的精确投影。
- SourceCollection：恰好一个 left 和一个 right `SourceCollectionMember`。每个成员将 source、完整 SourceSnapshot、mode/data level/completion、license 与全部 acquisition `RawSourceRecordReference` 绑定；record reference 只含 source/Snapshot/query/row key/raw-record hash，采用规范顺序，并由 record count 与 registry hash 封闭结构。完整性由 Publisher 的独立 validator 与原始 acquisition 双向比较，cell-level `raw_field` 只属于 Transformation Evidence。

BuildResult 是进程内编排结果，不是 generated JSON Contract；它进一步校验 Dataset columns 与 FieldDictionary definitions 完全相等、三类 candidate 的共同 pins 完全相等、Dataset 使用的 raw records 均属于 SourceCollection、alignment keys 覆盖 Dataset rows、C-08 identity 一致。公共序列化 Contract 是 DataArtifactBuildInput、Dataset、FieldDictionary、SourceCollection、MappingRuleSet 与 UnitConversionCatalog；候选 JSON/Pydantic round-trip 不会恢复 seal/context。

Dataset identity 只在 `data_artifact_identity.py` 定义：

- `canonical_content_hash` 覆盖 Manifest/policy/requested canonical schema、canonical row identity、row grain/entity projection/alignment、canonical 主值与单位、canonical uncertainty、limit status、null/unresolved、完整 canonical candidate 集合及其 source/alias priority、selection winner/order/reason 和 conflict scope/differences；排除 raw value/unit/table、locator、Snapshot/query/record/Evidence、source-value/conflict/selection 等派生 ID。所有 canonical Decimal 零在该投影中归一为 `0`。
- `canonical_row_identity` 仅在 `data_artifact_identity.py` 派生：它由 C-08 已准入的 record type/entity level/alignment、去重排序后的 normalized entity identity values 与 normalization rule version 构成；crossmatch conflict 还包含 conflict code。`planet_assertion` 的 logical assertion key 从已验证 row key 重新生成：要求 source namespace 非空，规范化字段和值的空白，保留全部 canonical row-key components，并要求至少一个不属于 identity locator 的 assertion discriminator。该计算完全忽略 `source_entity_key`，也不引入 Snapshot/query/raw-record/Evidence/source-value 等 lineage 与派生 ID。C-04 v1 的 assertion source 由冻结 Manifest 唯一确定，因此 source namespace 只参与输入合法性校验，不改变公开 key 形式。空字段、unmatched/inconclusive/review-required/rejected/conflict row 也因此具有稳定科学身份。Dataset 科学投影按该身份排序 rows，输入记录枚举顺序不参与 identity。
- `lineage_hash` 覆盖除 candidate/hash identity 字段以外的完整 Dataset public representation，因而包含 raw representation、Snapshot/query/record、locator、Evidence、input/C-08 lineage，并由 Schema 与 admission 严格复算。
- `output_hash` 覆盖除 candidate ID 与 output hash 自身外的完整公开候选内容，因此同时承诺 canonical 与 lineage hash。
- Dataset `candidate_id` 只能由 kind、schema version 与 `canonical_content_hash` 派生；不存在 legacy output-hash fallback。FieldDictionary/SourceCollection 继续以完整 output hash 作为自身 candidate identity 输入。

Dataset candidate ID 不是 ArtifactVersion identity 或 publication idempotency key。稳定 hash 排除 wall-clock、日志、分支、数据库 ID、ArtifactVersion number 与 Publisher content hash。raw provenance hash 可以区分 `0.0` 与 `-0.0`，但等价负零保持相同 canonical Dataset identity；Publisher content hash/output hash 仍可因 lineage 不同而不同。

## 7. Publisher 与 C-05 交接

C-04 生产模块不反向依赖 `app.workflow.publisher`。`services/data_pipeline/data_artifacts/admission.py` 提供 Evidence、domain、quality-prerequisite validators；它们从 immutable snapshot 重新解析输入，以同一领域投影规则重新派生完整期望值，并与候选逐集合比较，不导入或调用生产候选装配器。API/B 边界将三个 sealed candidate 分别交给 #78 `admit_artifact_candidate(...)`。复制、重新解析、bundle intermediate、dict 或 free text 不能绕过 instance seal。该端口只生成 `AdmittedArtifactCandidate`，数据库发布事务与 `ArtifactVersion` 仍属于 #78/B。

C-05 #35 消费 Dataset 的 field outcomes、conflicts、Evidence coverage、Crossmatch status 和 `quality_metric_input_declarations`，通过冻结 RuleSet 计算 per-field/row/dataset raw metrics 与 ResearchContract gate；C-04 始终输出 `quality_evaluation_status=not_evaluated`。C-05 的公共 Schema、hash、状态和 Publisher handoff 见 [Data Quality Evaluation](DATA_QUALITY_EVALUATION.md)。C-05 不改写 C-04 candidate，也不把质量结果当作 Core ArtifactKind 或 ArtifactVersion。

## 8. 数据等级、限制与验证

集成回归使用 C-08 synthetic fixture，它不是科学 ground truth；TOI/PS acquisition 各自的 recorded response 回归继续独立运行。Fixture、recorded response、Live 与 Cached 不互换。本实现不运行公网 Live smoke，不提供 HTTP/DB/Run 接线，不裁决 unresolved identity，也不计算动态质量指标。

```powershell
Set-Location apps/api
uv run pytest tests/test_data_artifact_contract.py tests/test_field_mapping.py tests/test_unit_conversion.py tests/test_data_artifact_pipeline.py tests/test_data_artifact_publisher_port.py tests/test_data_artifact_review_fixes.py tests/test_data_artifact_admission_replay.py tests/test_data_artifact_assertion_identity.py tests/test_data_quality_contract.py tests/test_data_quality_pipeline.py tests/test_data_quality_publisher_port.py
uv run pytest -q

Set-Location ../..
python -m unittest scripts.test_check_foundation
python scripts/check_foundation.py
node scripts/check-versionless-api.mjs
node scripts/check-docs.mjs
git diff --check
```
