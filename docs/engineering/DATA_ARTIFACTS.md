# Data Artifacts

| 元数据 | 值 |
| --- | --- |
| Authority | 字段映射、单位统一、Transformation Evidence 与 typed data Artifact candidate 运行规范 |

本文定义数据产物构建的唯一运行规范。`ArtifactVersion`、SourceSnapshot、缓存与修订机制由 [Data Versioning](../architecture/DATA_VERSIONING.md) 定义；本 Pipeline 只生成经过验证、可交给 Publisher 的 typed data Artifact candidate，不分配版本、不推进 ResearchRun、不写 HTTP DTO。

## 1. 职责与边界

数据产物构建消费已经完成的数据获取结果、Case/Field Manifest、[Cross-source Alignment](CROSS_SOURCE_ENTITY_ALIGNMENT.md) 的冻结 `CrossmatchResult`，以及通过文档准入边界的 typed document observations，生成：

- `DatasetArtifactCandidate`；
- `FieldDictionaryArtifactCandidate`；
- `SourceCollectionArtifactCandidate`。

进程内编排入口是 `build_data_artifact_candidates(DataArtifactBuildInput)`。公共可序列化合同只有输入模型、三个 typed candidate 以及其明确引用的策略/证据模型。

实现位于 `services/data_pipeline/data_artifacts/`，Pydantic authoring source 位于 `apps/api/src/app/schemas/data_artifacts.py`。科学 hash 投影与 process-local admission seal 分属 identity/seal 模块；二者不定义第二套 JSON Contract。

Pipeline 不访问 NASA endpoint、不重新运行 source adapter/crossmatch、不访问数据库、不计算质量评分、不发布 ArtifactVersion。数据质量由 [Data Quality Evaluation](DATA_QUALITY_EVALUATION.md) 独立评估并形成 Publisher 所需 attestation。

## 2. 输入与策略 Authority

`DataArtifactBuildInput` 必须固定：

- Case/Field Manifest identity 与 content hash；
- 左右 acquisition 的 records、SourceSnapshot、source mode/data level/completion；
- `CrossmatchResult`；
- requested canonical field IDs；
- `MappingRuleSet` 与 `UnitConversionCatalog`；
- producer technical identity；
- 可选质量约束引用；
- ResearchContract 的必填 document-source policy；
- 已准入 document observation 及其 ResearchInput、persisted DocumentParse、persisted/pipeline SourceSnapshot 与 locator 闭包；
- 稳定 `input_hash`。

来源、Snapshot、record set、row key 与实体对齐引用必须精确闭合。来源列名不是 canonical field identity，不能冒充 `requested_fields`。

执行策略只能从 `services/data_pipeline/manifests/exoplanet_host_star/mapping-rules/` 的当前 machine assets 加载。调用方即使能构造内部自洽的新对象，也不能通过重算 hash 改写当前 Authority。

Field alias、source/alias priority、document alias、null、uncertainty、limit、unit 与 quality-input 声明只读取 Field Manifest；运行时代码不得复制第二份字段事实。数据库列 alias 与 document alias 使用不同 declaration；document alias 只允许 canonical field exact match 或 Manifest 注册 alias，未知值必须 review/reject，不允许 fuzzy mapping、LLM auto-map 或猜值。

## 3. Typed document observation 与授权

`ScientificDataExtractionCandidate` 是 document-pipeline-owned raw candidate，不是 canonical 数据模型。data-pipeline-owned `ScientificDocumentObservation` 是最小、versioned、hashed 的一次性解释边界。它在进入 data-artifact mapping 前固定：

- canonical field 与 frozen Crossmatch canonical row；
- scalar 或显式 null；
- raw/canonical unit 输入；
- symmetric/asymmetric uncertainty；
- upper/lower limit；
- parse quality；
- ResearchInput、persisted DocumentParse、persisted SourceSnapshot、pipeline SourceSnapshot projection 与 `DocumentLocator` provenance。

`document_parse_id` 必须引用持久化 `DocumentParseRecord.id`，不能引用 parser logical parse identity。typed observation 构造时只解析一次 `±`、非对称误差、`<`、`>` 与 null；data-artifact mapping 之后只能消费 typed fields，不能重新解释自由文本。

Document value 的统一授权规则要求同时满足：

1. Case Manifest 明确支持 document supplemental source；
2. `DataRequirements.document_source_policy == research_input`；
3. ResearchInput、persisted DocumentParse、persisted/pipeline SourceSnapshot 与 locator 闭包一致；
4. observation 通过 document admission；
5. parse quality 为 `accepted`，或为 `partial` 且该 observation 明确可读。

`disabled`、Case 不支持、provenance mismatch、未知 field alias、未知 unit/conversion、悬空 row 或 `unsupported` 都 deterministic fail closed。该规则只有一个 authority，data-artifact mapping 与 quality evaluation 复用其 admission result，不复制授权判断。

Cross-source alignment 仍严格只处理 left/right structured sources。Document 是 supplemental source，只能绑定已有 frozen canonical row，不能成为 `CrossmatchSide`，不能触发 N-source crossmatch，也不能伪装成 database table、row key、raw DB field 或 `nasa_exoplanet_archive`。

## 4. 数值与单位

数值换算使用 `Decimal`、28 位精度与 `ROUND_HALF_EVEN`，输出为无指数 plain-decimal JSON string。canonical 数值零统一序列化为 `0`，但 raw value 必须原样保留，因此来源表示差异仍能进入 lineage/content hash。

`UnitConversionCatalog` 固定可执行 conversion identity、单位对、quantity kind、容量边界与常数 provenance。输入文本长度、significant digits、adjusted exponent、fractional scale 和最终字符串长度均有上限；NaN、Infinity、bool、非法数值与超容量数值 fail closed。

主值与 uncertainty 使用同一已授权换算；identity conversion 只允许同单位。转换常数只存在于 machine catalog，Python 分支不复制常数。

## 5. 值、缺失、误差与 limit

每个 structured/document `SourceValueCandidate` 通过判别 provenance 保留其真实来源。shared provenance 只有：

- `structured`：Crossmatch side、数据库 SourceSnapshot/query/row/record/raw-field locator；
- `document`：ResearchInput、persisted DocumentParse、persisted SourceSnapshot、pipeline SourceSnapshot projection 与 `DocumentLocator`。

名称必须使用 `pipeline_source_snapshot_id` 与 `persisted_source_snapshot_id` 明确区分两个 identity。每个 `SourceValueCandidate` 还保留：

- raw/canonical value 与 unit；
- SourceSnapshot/query/row/record/raw-field locator；
- source/alias priority；
- conversion identity；
- reference/provenance 文本；
- uncertainty 与 limit；
- null status 与 content hash。

字段结果是 `mapped | declared_null | unresolved` 判别联合。缺失值不能被补成 `0`/空字符串；未知 identity、review/conflict 状态不能通过 source priority 自动裁决；truncated/unknown 对侧的 `inconclusive` 不能改写为 `unmatched`。

非对称 uncertainty 分别保存，单侧缺失不补零。limit 只接受 Manifest 已声明的 measured/lower/upper 语义，未知类型、未知 flag 或没有主值的 bound 都稳定拒绝。

## 6. Dataset row grain 与实体对齐

每个 Crossmatch record 形成一个稳定 row，并显式记录 `entity_level`、projection policy identity 与 `projected_field_ids`。允许的字段对象层级为：

| Dataset row grain | 允许的 Field object type | 约束 |
| --- | --- | --- |
| `host_star` | `star`、`system` | 禁止 `planet.*` |
| `planet_candidate` | `planet` | 不从同行原始列隐式连接宿主上下文 |
| `planet_assertion` | `planet`、`star`、`system` | 只保留该 assertion 明确携带的来源上下文 |

accepted pair/adjudication 只合并同一 row grain 的 members。review-required、rejected、conflict-group 与 unpaired 都保留其原始 member、Evidence 和 completion 语义，不伪装为确定实体。

对象 identity 直接消费 Crossmatch 的已验证 normalized identity，不在字段投影时重新运行 identity 算法。字段 source priority 只能决定展示值，不能删除低优先级原值与 provenance。

## 7. Conflict、selection 与 Evidence

不同 canonical value 形成 `FieldConflictRecord`；`FieldSelectionRecord` 记录 row/field、候选集合、策略与原因。numeric conflict 的 tolerance 计算与 source priority 分离，阈值包含性由当前 mapping rules 固定。

值选择固定为 `valid structured value > document value`：

- structured 有效时 document 不覆盖；
- structured 缺失时 admitted document 可以补缺；
- 多个语义相同的 document values 共享 canonical outcome，并保留全部 provenance；
- document-only values 冲突时保留全部并形成 unresolved conflict，不选择 scientific winner；
- candidate id、时间戳与输入顺序只用于稳定序列化，不能影响科学结论。

`TransformationEvidence` 将输出 row/field/source value 绑定回：

- raw cell 与 locator；
- raw/canonical value、unit、uncertainty/limit/null；
- conversion catalog；
- Crossmatch result/logical key/Evidence；
- selection/conflict 状态。

领域投影是 deterministic、不可变的构建结果。candidate 的 `input_hash`、`output_hash`、content hash 必须覆盖实际影响科学内容的输入、策略、规则与 provenance；wall-clock 等运行观察值只在其明确合同中出现，不能造成同内容 hash 漂移。

## 8. SourceCollection、quality 与 Publisher handoff

`SourceCollectionArtifactCandidate` 显式区分 `crossmatch_sources` 与 `supplemental_document_sources`。crossmatch SourceSnapshot 必须严格为两个；Artifact 顶层 SourceSnapshot 总数可以因 supplemental document sources 增加，不能再用总数等于二验证 cross-source alignment 不变量。

Document parse quality 是 quality evaluation 的独立 observation，不进入 cross-source alignment left/right completeness。`partial` 的明确可读 observation 可以继续；`unsupported` 不能进入 Dataset。`unparsed != absent`，parse quality 也不等于 scientific truth。既有 `determinate | insufficient | not_applicable` 与 state-priority 语义保持不变。

## 9. Candidate、replay 与 Publisher handoff

三个 candidate 都必须经过其 schema、domain seal 与 data-quality gate。Publisher 是创建 `ArtifactVersion`、更新 latest pointer、持久化 quality projection 与绑定 Evidence 的唯一事务边界。

Publisher admission 只接受 persistence-ready candidate：candidate 声明的每个 SourceSnapshot 与 Evidence 都必须映射到同 Project 的持久化记录，缺失、悬空或不一致的 binding 必须在任何版本、事件或 latest pointer 写入前拒绝。Dataset 的 crossmatch Evidence 必须在单条 persisted Evidence 中保留左右两侧 Snapshot 与 locator；单值 `source_snapshot_id` 仅作为明确的左侧外键锚点，不能替代双侧 provenance。Document provenance 复用同一 pipeline snapshot → persisted SourceSnapshot binding，不创建第二份 persisted SourceSnapshot；Publisher 只 materialize 判别 provenance 并保持 ResearchInput/DocumentParse/locator 引用闭合，不分配第二套版本或事务。

replay 必须对 exact input/content/producer/provenance 进行等值校验；相同 idempotency/publication identity 被用于不同内容时稳定冲突。不能使用 DTO wrapper、任意 dict、read projection 或自定义 Pydantic model 绕过 typed candidate admission。

## 10. Replay、fixture 与验证

相同 frozen input 的 observation identity、排序、input/output/content hash 必须稳定。Document admission 的确定性 fixture 必须引用 persisted ResearchInput、DocumentParse 与 SourceSnapshot 语义，不能用 Mock 或 fixture 结果声称真实 Hybrid Parser Live acceptance。

高价值回归至少覆盖：一次性 scalar/unit/uncertainty/limit/null 解析；provenance mismatch fail-closed；exact/Manifest alias；frozen row 绑定；授权矩阵；structured priority/document 补缺/同值 provenance/document conflict；parse quality 与 cross-source completeness 独立；replay 稳定性；Publisher 到持久化 provenance 与 data-artifact read/export 的闭环。

## 11. 维护规则

1. 字段事实改动先更新 source evidence/canonical Manifest，再更新 mapping/unit/quality machine assets 与 hash。
2. `ResearchContract.requested_fields` 只接受 Case Manifest 的 canonical Field IDs。
3. source alias、recorded response、Fixture/Benchmark/Cached/Live 必须保持其真实数据等级，不互相伪装。
4. 技术版本、content/input/output hash 与 upstream exact identity 是科研可复现信息，继续保留；Git 保存这些定义的历史变化，不在活动目录维护 machine changelog 副本。
