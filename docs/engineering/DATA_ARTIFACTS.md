# Data Artifacts

| 元数据 | 值 |
| --- | --- |
| Authority | 字段映射、单位统一、Transformation Evidence 与 typed Data Artifact candidate |
| Scope | `exoplanet_host_star` Case 的 Dataset、FieldDictionary 与 SourceCollection |

本文定义 Data Artifact candidate 的唯一运行规范。`ArtifactVersion`、
SourceSnapshot、ProducerExecution、缓存与修订由
[Data Versioning](../architecture/DATA_VERSIONING.md) 定义；质量规则由
[Data Quality Evaluation](DATA_QUALITY_EVALUATION.md) 定义；跨源实体对齐由
[Cross-source Alignment](CROSS_SOURCE_ENTITY_ALIGNMENT.md) 定义。

## 1. Boundary

`build_data_artifact_candidates(DataArtifactBuildInput)` 消费已完成的 acquisition
结果、SourceSnapshot、Case/Field Manifest、`CrossmatchResult`、requested
canonical field IDs、`MappingRuleSet`、`UnitConversionCatalog` 与 producer
identity，生成三个 typed candidate：

- `DatasetArtifactCandidate`；
- `FieldDictionaryArtifactCandidate`；
- `SourceCollectionArtifactCandidate`。

实现位于 `services/data_pipeline/data_artifacts/`；Pydantic authoring source
位于 `apps/api/src/app/schemas/data_artifacts.py`。Pipeline 不访问 source
endpoint、数据库或 HTTP DTO，不运行 acquisition/crossmatch，不计算质量评分，
不分配 ArtifactVersion。Publisher 是发布版本、Evidence、latest pointer 与
quality projection 的唯一事务边界。

## 2. Frozen input and projection

输入必须精确闭合：

- Manifest identity/content hash、左右 acquisition records 与 SourceSnapshot；
- Crossmatch result 及其 source/evidence identity；
- requested fields、mapping rules、unit conversion catalog；
- producer technical identity、质量约束引用与 `input_hash`。

来源、query、record set、row key、raw record hash 与 Crossmatch 引用必须相互
一致。source column name 不是 canonical field identity，不能冒充
`requested_fields`。所有字段事实从 Manifest 与 machine assets 读取，代码不得
复制第二份 alias、priority、unit 或 conversion 常数。

领域 projection 是 deterministic、不可变的构建结果。candidate 的 input、
output、canonical content 与 lineage identity 必须覆盖实际科学内容、策略、
规则与 provenance；wall-clock 观察值不得造成同内容 hash 漂移。

## 3. Values and units

`SourceValueCandidate` 保留 raw/canonical value、source/canonical unit、source
priority、alias priority、conversion rule identity、uncertainty、limit、null
status、SourceSnapshot/query identity、origin 与 evidence locator。

数值使用 `Decimal` 与 frozen conversion catalog，输出 plain-decimal JSON string；
raw value 原样保留。NaN、Infinity、bool、非法数值、容量超限、缺单位、quantity
kind 不匹配或 conversion rule 不唯一都 fail closed。identity conversion 只允许
同单位。

`LimitValue` 具有结构化不变量：

- `not_applicable` 不得携带 raw flag 或 locator；
- structured database origin 的 applicable limit 必须同时携带 database flag
  与 `DatabaseCellLocator`，并且 locator 必须属于同一 raw record；
- document origin 的 semantic limit 可以不携带 database flag/locator，语义状态
  仍由 admitted document observation 绑定；
- limit、uncertainty 与主值不得引用另一 SourceSnapshot、row 或 raw record。

缺失值保持 typed null；未知 identity、review/conflict 或 incomplete 对侧不会被
source priority、默认值或字符串空值静默裁决。

## 4. Rows, selection and evidence

每个 Crossmatch record 形成稳定 row，并保留 entity level、projected fields、
member、completion、alignment 与 conflict 语义。Dataset row 的字段对象层级
必须符合 Field Manifest；不会从同行原始列隐式连接宿主上下文。

`FieldSelectionRecord` 记录候选集合、策略与原因；不同 canonical value 形成
`FieldConflictRecord`。source priority 只决定展示选择，不删除低优先级原值或
provenance。

`TransformationEvidence` 将 canonical field/source value 绑定回 raw value、
unit、uncertainty/limit/null、locator、conversion catalog、Crossmatch result、
logical key 与 selection/conflict 状态。所有 candidate registry 必须与实际
source snapshots、evidence、rows、selections 和 conflicts exact-match。

## 5. Document-derived supplemental values

Document observation 是既有 canonical row 的补充值，不是第三个 Crossmatch side。
它进入 Data Artifact 前必须已经通过 [Scientific Document Parsing Contract](../architecture/SCIENTIFIC_DOCUMENT_PARSING_CONTRACT.md) 的 typed admission。

### Supplemental invariants

- `DataArtifactBuildInput.document_observations` 只接受 typed observations，不接受 raw parse candidate 或任意 dict。
- `SourceValueCandidate.origin` 是 structured database 与 document research input 的 discriminated union；document locator 同时绑定 ResearchInput、DocumentParse、SourceSnapshot 与 cell/page geometry。
- approved structured value 有合法值时优先于 document；structured 缺值时 admitted document 可补充；相等 document 值形成 consensus，冲突且无 structured winner 时保持 unresolved。
- Dataset 的 SourceSnapshot registry 包含恰好两个 Crossmatch snapshots 与实际保留的 document snapshots；Publisher 通过唯一 binding 映射到既有 persisted rows，不复制 snapshot。
- Data Quality 的 structured source-scope denominator 只统计 Crossmatch 左右两侧；document parse quality 是独立的 `DocumentParseQualityObservation`，不污染结构化分母。
- Document admission 的 table/entity/value quality、unsupported-region reason code、raw candidate 与 locator provenance 必须原样进入 downstream evidence；Dataset projection 不重新解析 free text。

## 6. Quality and Publisher handoff

三个 candidate 必须依次通过 schema、domain admission 与 Data Quality Evaluation
attestation。Publisher 只接受 persistence-ready candidate：每个 declared
SourceSnapshot/Evidence 必须绑定同一 Project 的持久化记录，缺失、悬空、跨项目或
content/query identity 不一致时，在任何 ArtifactVersion 或 latest pointer 写入
前拒绝。

Dataset 的 Crossmatch Evidence 必须保留左右两侧 snapshot 与 locator；单值
`source_snapshot_id` 只是明确的左侧外键锚点，不能替代双侧 provenance。
replay 必须对 exact input、content、producer 与 provenance 等值校验；相同
publication identity 对应不同内容时稳定冲突。

## 7. Stable maintenance rules

1. 字段事实、alias、unit、priority 与转换常数只在 Manifest/machine assets 中维护。
2. `ResearchContract.requested_fields` 只接受 Case Manifest 的 canonical IDs。
3. Fixture、Recorded、Benchmark、Cached 与 Live 数据等级必须如实区分。
4. Public API 读取使用 typed candidate、persisted provenance 与 quality projection，不重新运行构建算法。
