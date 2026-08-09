# Graph Pipeline

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | Versioned Evidence Graph 的生成、准入、Evidence 使用、发布与读取边界 |
| Scope | 生产 Graph candidate、Publisher handoff、固定 Benchmark 与渐进读取规范 |

本文是 Graph Pipeline 运行规则的唯一完整事实源。核心实体与所有权由
[Data Model](../architecture/DATA_MODEL.md) 定义，ArtifactVersion 与 hash 通则由
[Data Versioning](../architecture/DATA_VERSIONING.md) 定义，跨文献 Relation 语义由
[Reasoning Protocol](../ai/REASONING_PROTOCOL.md) 定义，数据字段和值的上游真实性由
[Versioned Data Artifacts](VERSIONED_DATA_ARTIFACTS.md) 定义。

## 1. 输入、输出与所有权边界

Graph Pipeline 只消费同一 Project 内已经固定的不可变输入：

- Graph 的 version selection 不包含 ResearchContract 或 ResearchGoal，因此不得生成
  research_goal node 或 `uses_dataset` edge；
- 完整发布的 LiteratureRelations ArtifactVersion，以及其内嵌的 PaperSummary、Claim、
  Relation、ReasoningTrace 与 provenance 闭包；
- 可选但不可拆分的 Dataset/FieldDictionary ArtifactVersion 对；两者必须来自同一构建闭包、
  具有相同 Manifest/策略/SourceSnapshot/Evidence pins，并共享通过门禁的 DataQuality
  projection；
- 上述版本声明的 Evidence、SourceSnapshot、Producer、schema version、content hash 与
  output hash；
- 版本化的 Graph taxonomy、构建策略、容量策略与可选的显式构建 scope。

输入不得引用动态 `latest`，不得把 Fixture 冒充 Cached，也不得由展示层临时选择暗中改变
Graph 内容。若调用方需要缩小构建范围，scope 必须在构建前显式声明、进入 `input_hash`，并对
所包含的每个节点和边保持完整 Evidence 闭包。

版本读取边界必须一次返回上述完整 typed envelope，不能返回 loose JSON、裸 candidate、动态
latest 或集合 API 的单页结果。Dataset 与 FieldDictionary 只能同时存在或同时缺席；半闭合的
数据输入不能表示为合法 Graph build。

Graph 的 `GraphBuildScope` 对未固定的 `research_goal_id` 直接拒绝；不得从 Project 名称、
Dataset metadata、页面输入或默认文本推测研究目标。该省略不影响 literature-only 或
Dataset/FieldDictionary Graph 的合法性。`research_goal` node 与 `uses_dataset` 端点规则
只接受版本固定的正式 ResearchGoal 输入 Authority；缺少该 Authority 时保持禁用并拒绝构建。

输出是一个不可变、typed、publisher-ready Graph candidate。它至少封闭：

- 节点、边及其稳定身份和确定性顺序；
- 每条边使用的上游 ArtifactVersion、Evidence 与 SourceSnapshot；
- Graph 自有的 Evidence-use 身份；
- taxonomy、schema、producer、构建策略与容量策略版本；
- 输入版本集合、`input_hash`、`output_hash` 和完整性计数。

Pipeline 不创建数据库 ArtifactVersion 或 Evidence 记录，不推进 ResearchRun，不更新
`latest_version_id`，也不承担 HTTP DTO、页面布局或交互状态。数据库物化只发生在 Publisher
事务内。

## 2. 节点 taxonomy 与稳定身份

节点身份来自上游领域身份，不来自标签、数组位置、数据库自增值或当前 ArtifactVersion：

- `research_goal` 节点身份规则为已确认 ResearchContract 中的目标及 Contract 身份；当前 Graph Contract
  尚无该版本输入，因此当前不会生成这种节点；
- `dataset` 节点的领域身份严格等于 `ResearchArtifact.artifact_id`。用于构建的
  `ArtifactVersion.id` 另行保存在版本 provenance 中，不能替代节点身份；
- `field` 节点的领域身份严格由 `field_manifest_id + canonical_field_id` 二元组组成。
  source column、alias、展示标签或 Dataset row 不能进入该身份；
- Paper 与 Claim 节点使用其上游 typed identity，并明确固定产生该投影的 ArtifactVersion；
- `source` 节点类型为保留 taxonomy。当前 Pipeline 不生成 `source` 节点，Source 与
  SourceSnapshot 只通过 Evidence provenance 表达；包含新生成 `source` 节点的 candidate
  不具备发布资格。

Graph 不生成 row node。Dataset row、SourceValue、selection、null、unresolved 与 conflict
信息通过 `dataset -> field` 边的完整 Evidence-use 闭包表达。不得为缩短边的 Evidence
集合而把 row 重新包装成未受治理的节点。

节点 ID 的序列化形式由唯一 Pydantic Schema 定义；无论具体编码形式如何，dataset 和 field
的上述领域身份都不得改变。相同领域身份在同一 Graph 中只能出现一次。

Field node 集合由固定 FieldDictionary 的 canonical field 全集定义，不由任一 Dataset row
是否存在非 null 值决定。每个 Dataset logical identity 与每个 canonical field identity 在同一
Graph 中至多形成一条 `provides_field` edge；合法发布候选必须为每个应映射 field 精确形成一条。
即使所有纳入行均为 null 或 unresolved，也不能省略 Field node 或该 edge。若完整上游闭包不能
为该 edge 提供至少一个有效 Evidence-use，整个 Graph 必须失败关闭。

## 3. 边 taxonomy、方向与端点

边是有向且不可隐式反转的。当前生产约束如下：

| edge type | 唯一合法方向 | 约束 |
| --- | --- | --- |
| `uses_dataset` | `research_goal -> dataset` | 仅表示已固定研究目标使用该 Dataset Artifact；其他端点组合一律非法 |
| `provides_field` | `dataset -> field` | 仅表示该 Dataset 对 canonical field 的完整版本化投影；不得改为 field -> dataset |
| `supports_finding` | `paper -> claim` | 结构性来源边，必须绑定该 Paper/Claim 的一致 provenance 与 Evidence |
| Literature Relation type | `source claim -> target claim` | edge type、方向与 endpoint 必须逐项等于其 Accepted Relation |

`uses_dataset` 不得用于 Dataset 间 lineage、Paper 引用或任意 UI 分组；`provides_field` 不得
用于 Source、row、raw column 或 FieldDictionary 自身。任何新的 edge type 或端点矩阵都必须
先更新 Graph taxonomy 的唯一 Schema 与本 Authority，不能依赖宽松字符串或前端约定。
缺少精确 ResearchContract/研究目标输入时，即使 Dataset 存在也不得生成 `uses_dataset`。

每条边必须满足：

1. source、target 都解析到当前 Graph 中的唯一节点，且 source != target；
2. edge type 位于当前 versioned taxonomy，并符合唯一合法端点矩阵；
3. edge identity、方向和 Evidence-use 集合稳定且无重复；
4. 所有上游 ArtifactVersion、Evidence、SourceSnapshot 均存在、hash 匹配且同属一个
   Project；
5. 非跨文献结构边不得携带伪造的 Relation 或 ReasoningTrace 绑定；
6. 任何无法证明的边都必须拒绝，不能为了布局、连通性或视觉完整性补边。

## 4. 数据字段的完整 Evidence 并集

一个 `dataset -> field` 边必须承诺该 Dataset ArtifactVersion 对该 canonical field 的完整
上游 Evidence 并集。集合不得只保留当前展示值，必须覆盖：

- `selected`：被 FieldSelectionRecord 选择的 winner 及其 Transformation Evidence；
- `unselected`：所有未被选择的合法候选、低优先级来源值及其 Evidence；
- `null`：`declared_null`、`not_measured`、`not_in_source` 等已声明空值状态及其 provenance；
- `unresolved`：无法安全产生主值、review/rejected identity、unmatched/inconclusive 等上游
  unresolved 状态及其 Evidence；
- `conflict`：FieldConflictRecord 的全部成员、差异、selection 决策及其 Evidence。

FieldDictionary 定义 Field node；`MappedCanonicalValue` 必须保留 selected 与 unselected
source candidates 及其全部 TransformationEvidence，`DeclaredNullValue` 必须保留 null reason、
candidate references 与已有 TransformationEvidence，`UnresolvedCanonicalValue` 和 conflict
必须保留全部候选、conflict ids、原因与 Evidence，不能选择或虚构 scientific winner。

形式上，对给定 edge 与上游版本，必需集合是该 Dataset/Field 在所有
`projected_field_ids` 声明该 field 适用的行中的上述五类 Evidence-use 集合并集。其他 entity
类型且未投影该 field 的行不属于该 field 的 applicable rows，不能虚构 null 或 Evidence；但任一
已投影行缺少 outcome，或任何临时 filter 隐藏 applicable row，均须以 aggregation incomplete
失败关闭。相同上游
Evidence 在同一 edge、同一上游 ArtifactVersion 下只出现一次；同一 Evidence 被不同 edge
使用时必须形成不同的 Graph-owned Evidence-use。Pipeline 必须从不可变输入独立重建此并集，
并与 candidate 做完整集合等值比较。漏掉 unselected、null、unresolved 或 conflict 成员与
漏掉 selected winner 同样是硬拒绝。

因为没有 row node，边可以附带确定性的分类计数和分组索引以支持读取，但计数不能代替完整
Evidence-use registry。过滤、聚合与渐进传输也不得改变该 registry 或 Publisher 的准入
分母。

## 5. Graph-owned Evidence-use 与 Publisher 物化

Graph-owned Evidence-use 的科学身份严格由以下三元组组成：

```text
(graph_edge_identity, upstream_artifact_version_id, upstream_evidence_id)
```

该身份不使用新数据库 UUID、数组位置、展示标签或动态 latest。上游版本变化时，即使
Evidence 文本相同，也产生不同的 Evidence-use 身份；同一上游 Evidence 在两条边上使用时，
也产生两个不同身份。candidate 必须同时固定上游 Evidence 的 content、locator、status、
SourceSnapshot id/version/content hash 与 Project ownership，不能只保存裸 ID。

Publisher 在发布事务内为每个 Graph-owned Evidence-use **新物化一条属于 Graph
ArtifactVersion 的 Evidence**：

- 新 Evidence 的 target type 为 `graph_edge`，target/locator 明确绑定对应 edge 与上游
  Evidence-use 身份；
- `artifact_version_id` 指向新建的 Graph ArtifactVersion，而不是上游 ArtifactVersion；
- `source_snapshot_id` 复用上游 Evidence 已固定的同一 SourceSnapshot，不复制、不更新也不
  重新抓取 Snapshot；
- locator 只保存 Graph Evidence-use、upstream ArtifactVersion/Evidence/target 的稳定 ID 与
  upstream Evidence hash；`quote_or_value` 固定为 `null`，不复制上游短摘录或受限全文；
- `extraction_method` 固定为 `graph_admission`，`confidence` 固定为 `1.0`，Evidence type 沿用
  已验证的 upstream 类型，`is_restricted` 原样传播 upstream Evidence 的限制标志；
- 上游 Evidence 保持不可变，不能直接改绑到 Graph ArtifactVersion。

Graph ArtifactVersion 与全部新 graph-edge Evidence 必须在同一 Publisher 事务中原子创建。
任一 Evidence-use 无法物化、Snapshot 不存在、ownership 不一致或集合计数不闭合时，整个
发布失败，不得留下部分 Graph 或部分 Evidence。

本契约复用现有 ResearchArtifact、ArtifactVersion、Evidence 与 SourceSnapshot 持久化模型，
不引入数据库迁移，也不原地改写既有 Graph 或上游 ArtifactVersion。

## 6. Literature Relation 与 ReasoningTrace 闭包

跨文献 Claim 边只允许来自真正 `accepted` 的 LiteratureRelation。`review_status=approved`
只表示科研标签已经审核，不能替代 Relation admission status。candidate 或 rejected Relation
即使具有高 confidence、approved Review 或完整 Trace，也绝对不能进入 Graph。

每条跨文献边必须同时满足：

1. source/target Claim 均为 `accepted`，且分别固定明确的 LiteratureClaims 与
   PaperSummary ArtifactVersion；
2. edge source、target 严格等于 Relation 的 `source_claim_id -> target_claim_id`，不得反转；
3. edge type 严格等于 Relation type，不从文本或相邻边推导另一类型；
4. Relation 固定的 ReasoningTrace 存在、status 与 Relation 一致，premises 按相同方向排列；
5. Trace steps、双方 Claim Evidence、Relation Evidence、SourceSnapshot 与 ownership 完整
   闭合；
6. Graph-owned Evidence-use 覆盖该 edge 实际使用的全部上游 Evidence，并由 Publisher 新物化
   graph-edge Evidence。

`graph_eligible` 只是上述闭包的读取结果，不是新的科学判断。Graph Pipeline 必须重新验证
闭包，不能盲信上游 DTO 上的布尔投影。缺少任一 endpoint version、Trace、Evidence 或
SourceSnapshot 都是硬拒绝；不得把不完整 Relation 降级成无 Relation 的普通跨文献边。

同一文献内的 `paper -> claim` 结构边不要求 Relation/Trace，但仍必须绑定该 Paper、Claim、
Evidence 与 SourceSnapshot 的精确版本闭包。它不能被标记为跨文献 Relation 边。

## 7. 确定性准入与 Publisher 防绕过

完整性阶段、优先级和 reason taxonomy 固定如下。数值越小越优先；同一请求存在多个失败时，
报告按 `priority -> stage -> path -> reason` 稳定排序，并只以第一项作为 admission 主结果。

| stage | priority | 固定 reasons |
| --- | ---: | --- |
| `input_schema` | 100 | `invalid_json`, `schema_invalid` |
| `artifact_version` | 200 | `input_version_unknown`, `input_version_unpublished`, `wrong_artifact_kind`, `unsupported_schema_version`, `content_hash_mismatch`, `input_hash_mismatch`, `producer_execution_mismatch`, `cross_version_reference` |
| `ownership` | 300 | `cross_project_ownership` |
| `taxonomy` | 400 | `taxonomy_violation` |
| `identity` | 500 | `duplicate_node_identity`, `duplicate_edge_identity`, `identity_collision` |
| `endpoint` | 600 | `dangling_endpoint` |
| `evidence_snapshot` | 700 | `evidence_missing`, `evidence_unknown`, `evidence_inconsistent`, `source_snapshot_missing`, `source_snapshot_unknown`, `source_snapshot_inconsistent`, `provenance_version_mismatch` |
| `relation_trace` | 800 | `relation_not_accepted`, `reasoning_trace_missing`, `reasoning_trace_mismatch`, `reasoning_trace_incomplete` |
| `direction_type` | 900 | `wrong_direction`, `relation_type_mismatch` |
| `capacity_progressive` | 1000 | `evidence_hidden_by_filter`, `aggregation_incomplete`, `size_limit_exceeded`, `silent_truncation`, `progressive_input_incomplete` |
| `hash_commitment` | 1100 | `candidate_hash_mismatch`, `report_hash_mismatch`, `admission_commitment_mismatch` |

准入按固定阶段执行：Schema、输入版本/hash、Project ownership、节点身份/taxonomy、边端点与
方向、数据 Evidence 完整并集、Literature Relation/Trace 闭包、duplicate/capacity、稳定
hash、publication authority。多重失败输入必须收集所有仍可安全独立判定的 finding，并按
priority、stage、path、reason 稳定排序；`first_failure_stage` 与 `first_rejection_reason` 固定取
排序首项。依赖无效前置对象且无法安全判断的后续 gate 不制造级联错误，但输入重排不能改变
完整 finding 集合或首因，后续内容看似完整也不能覆盖前置失败。

领域准入必须从 immutable input、冻结 taxonomy 与策略独立重建期望 Graph，逐集合比较节点、
边和 Evidence-use；不得调用生产 candidate 装配器，也不得从 candidate 自己声明的集合推测
期望值。只有完成全部门禁后由 Pipeline 直接返回的 exact candidate instance 才能获得一次性
process-local publication authority。

publication seal 至少绑定对象身份、schema/kind、input/output/public-payload hash、immutable
input snapshot、taxonomy/policy commitment、节点/边/Evidence-use registry 与完整性计数。
Publisher 必须在写入前再次执行独立领域校验和 seal 校验。

以下对象均不具发布资格：raw dict、自由文本、旧 GraphResponse、单独 Node/Edge、部分/过滤
Graph、渐进传输 chunk、Pydantic/JSON round-trip、copy/deepcopy、手工构造 seal、从其他输入
移植的 candidate。封印后修改节点、边、Evidence-use、版本、Producer、计数或 hash 会使
authority 失效。通用 Publisher port 不能提供绕过 Graph 专属 validator 的可选开关。

Graph seal 转换为通用 `AdmittedArtifactCandidate` 后，通用 wrapper 还必须以独立的闭包私有
authority 绑定 exact wrapper object、content JSON/hash、schema、Evidence/Snapshot registry 与
materialization plan。直接导入模块 token、copy/deepcopy 或低级修改 wrapper 均不得进入首次发布
或幂等 replay。

## 8. Hash 与版本分层

Graph 使用相互独立的 hash 层，禁止用一个 hash 代替全部职责：

1. **输入 hash**：`input_hash` 覆盖 Project、显式 scope、taxonomy、完整 policy set、所有上游
   ArtifactVersion id/kind/schema/content/input/output hash 与 producer pins，以及
   Evidence-use/SourceSnapshot closure；Graph Contract 不包含未固定的 ResearchContract、运行时
   execution id 或 Publisher 新分配的 Graph ArtifactVersion；
2. **领域身份与 fingerprint**：node identity 遵循第 2 节；edge fingerprint 覆盖 edge type、
   有向端点及必要的 Relation binding；Evidence-use identity 覆盖第 5 节三元组；
3. **科学 hash**：`scientific_hash` 覆盖 kind、schema version、Project、input versions、
   taxonomy、完整 policy/scope、nodes、edges、Evidence-use 与 SourceSnapshot；排除
   progressive/layout metadata、Producer、GraphIntegrityReport 和全部派生 hash；
4. **布局 hash**：`layout_hash` 只覆盖 declarative `layout_hint`。布局变化不能伪装成科学
   内容变化；progressive 分块属于完整输出 envelope，但既不进入 scientific hash，也不进入
   layout hash；
5. **完整性报告 hash**：`report_hash` 是 GraphIntegrityReport 完整 payload 排除其
   `content_hash` 自身后的 canonical hash。报告计数、完整性结论或容量结果变化必须改变该 hash；
6. **candidate output hash**：`output_hash` 覆盖完整公开 candidate、稳定排序的节点/边/
   Evidence-use、输入版本、策略、Producer 与上述三个 hash，排除自身和 execution/run id、
   wall-clock、latency 与日志；上游 ArtifactVersion、Evidence、SourceSnapshot 的持久身份属于
   固定 provenance，必须保留；
7. **Publisher content hash**：ArtifactVersion `content_hash` 对实际发布的稳定 JSON 内容计算，
   包含最终版本化 provenance；它与 Pipeline `output_hash` 职责不同，不要求相等；
8. **读取投影 hash**：过滤、分页、聚合或渐进响应只能由固定 Graph ArtifactVersion 与显式读取
   参数派生响应级 hash/ETag，绝不能替代 ArtifactVersion `content_hash`。

节点按稳定 node identity、边按稳定 edge identity、Evidence-use 按三元组规范排序。输入数组、
数据库查询或并发完成顺序不得改变 candidate、hash 或 Benchmark 输出。任何上游版本、Evidence、
taxonomy、policy 或 scope 变化都必须改变相应输入/输出 hash，并通过新 Graph ArtifactVersion
发布，不能原地修改。

算法 ProducerExecution 使用 `graph_algorithm_parameters()` 返回的 scalar-only 参数 manifest；
其 canonical `parameters_hash` 必须等于 candidate producer pin。Publisher 还要逐项验证 execution
的 input hash、type/name/version、parameters hash 与 Graph candidate 一致，并要求 execution
output hash 等于实际 Publisher content hash，防止数据库列与 candidate 内嵌 provenance 分叉。

## 9. Size、filter、aggregation 与 progressive delivery

Graph 构建容量由 versioned capacity policy 控制。策略至少分别限制节点、边、单边与总
Evidence-use 数量以及可序列化 payload 大小，并进入 `input_hash`。超过上限必须在 seal 前
fail closed；不得静默截断、抽样后冒充完整 Graph，或只发布 selected Evidence。

完整 Graph ArtifactVersion 与读取视图严格分离：

- **filter**：节点类型、edge type、对象 ID 或 Evidence 状态过滤只影响读取投影。响应必须固定
  Graph version、回显规范化 filter，并声明完整总数与当前返回数；
- **aggregation**：Dataset-field 边允许提供从完整 Evidence-use registry 计算的确定性计数；
  展示层聚合不能合并领域 identity、丢弃 provenance、生成新科学关系或写回 ArtifactVersion；
- **progressive delivery**：大 Graph 可按稳定 node/edge/Evidence-use 顺序分 chunk 读取。每个
  chunk 必须绑定同一 Graph ArtifactVersion、filter 与 cursor，并声明是否完成；
- **partial state**：任一 filter 结果、aggregation view 或未完成 chunk 都不是新的 Graph
  candidate，不得获得 publication seal、标记为完整、作为 Cached Artifact 或参与科学 hash。

若构建 scope 本身需要缩小，必须在 Pipeline 输入中版本化并重新发布一个明确 scope 的 Graph
ArtifactVersion；读取时临时 filter 不能反向改变该 scope。

## 10. 固定 Benchmark 与数据等级

正式 Graph Benchmark 包含两个彼此分离的证据层级：

- 论文与推理固定包属于 `Benchmark / seed`。正式 suite 必须消费整个冻结 Graph label，不允许
  favorable subset；当前回归固定 6 个节点、2 条边，其中唯一跨文献边是 Accepted `extends`
  Relation。candidate/rejected Relation、悬空端点、反向边、taxonomy 越界、Relation/Trace
  不匹配与 Evidence 缺失构成固定负例；
- 数据侧结构回归属于明确标记的 synthetic Fixture，用于验证 research_goal/dataset/field
  方向、稳定 identity、无 row/source node、五类 Evidence 完整并集与 Publisher 防绕过。它不是
  科学 ground truth，不能与论文 Benchmark 指标合并。

Benchmark 不访问公网、不调用生产模型、不创建数据库版本，也不把 seed 或 Fixture 描述为
Live/Cached。Recorded response、Live 与 Cached 输入必须保持其真实数据等级；Cached 只能引用
真实历史 ArtifactVersion，不能来自 Benchmark 或 Fixture。

正式 Benchmark runner 只执行固定输入的离线 replay。它不得构造或伪造 publication seal，
不得把 replay observation 当作 publisher-ready Graph candidate，也不得调用 Publisher。生产
Graph Pipeline 与 Publisher 的同路径集成由独立的 typed PublishedGraphInputs 回归验证；其结果
不能替代冻结论文 Benchmark 的完整 6-node/2-edge scientific label，也不能混入 scientific
指标分母。

报告至少分别保存完整 Graph exact match、node/edge exact coverage 与 unexpected count、跨文献
Relation/Trace closure、Evidence-use coverage、non-accepted Relation block、完整性通过/失败
计数、固定负例 pass rate、逐 case input/output hash 和 report input/output hash。只报告 recall
会放过伪造的额外节点或边，因此 exact/precision 与 unexpected count 是发布门的一部分。

十二项 rate 的口径固定如下。所有 rate 均由逐 case 事实重算；分母为零时 rate 必须为 `null`，
不得以 `0` 或 `1` 代替空集合。`scientific` 指标只消费完整冻结论文 Graph，Fixture 不得进入其
分母。

| metric | numerator | denominator | exclusion scope |
| --- | --- | --- | --- |
| `full_graph_exact_match_rate` | nodes、edges、Evidence-use、Relation/Trace 与 unexpected count 全部精确匹配的 scientific cases | 完整 scientific Graph cases | 排除全部 Fixture 与 schema/rejection/size cases |
| `node_exact_match_rate` | identity、type、logical reference 均匹配的 expected scientific nodes | 全部 expected scientific nodes | 排除 Fixture；unexpected nodes 单独计数且使 full-graph exact 失败 |
| `edge_exact_match_rate` | identity、方向、type、endpoint、Relation binding 与 Evidence-use 集合均匹配的 expected scientific edges | 全部 expected scientific edges | 排除 Fixture；unexpected edges 单独计数且使 full-graph exact 失败 |
| `evidence_coverage_rate` | 精确匹配的 `(edge identity, upstream Evidence-use identity)` | scientific edges 要求的全部 Evidence-use bindings | 排除负例、size 与 data Fixture；同一 Evidence 在不同 edge 分别计数 |
| `accepted_relation_coverage_rate` | 已形成匹配 Graph edge 的 accepted Relations | frozen scientific label 中全部 accepted Relations | candidate/rejected Relation 不进入分母 |
| `reasoning_trace_coverage_rate` | 与 accepted Relation、方向、两端 Claim 闭合的 ReasoningTraces | accepted scientific Relations 要求的全部 ReasoningTraces | candidate/rejected Relation 的 Trace 不进入分母 |
| `nonaccepted_relation_exclusion_rate` | 未进入 scientific Graph 的 candidate/rejected Relations | frozen label 中全部 non-accepted Relations | 不把 synthetic rejection pass 混入该 scientific exclusion 指标 |
| `stable_identity_order_rate` | identity 与 registry 顺序稳定的 schema-valid expected-pass cases | 全部适用的 schema-valid expected-pass Benchmark/Fixture cases | 排除 expected-failure、invalid JSON 与 schema-invalid cases；该项不是 scientific quality 指标 |
| `data_mapping_fixture_pass_rate` | 节点、方向、FieldDictionary field、五类 Evidence 完整并集均符合预期的数据映射 Fixtures | 全部 formal data-mapping Fixtures | 排除 frozen scientific、rejection 与 size cases；该项不是科学 ground truth |
| `rejection_case_pass_rate` | 在固定 first stage/reason 失败的 rejection Fixtures | 全部 formal rejection Fixtures | 排除 scientific 与 size cases |
| `size_boundary_pass_rate` | 产生预期 pass/fail 的 size-boundary Fixtures | 全部 formal size-boundary Fixtures | 排除 scientific 与其他 rejection cases |
| `schema_pass_rate` | 通过输入 Schema 的 cases | formal suite 全部 cases | invalid JSON 与 schema-invalid 负例保留在分母且计为未通过 |

case id、节点、边、Evidence-use 与序列化 key 使用稳定顺序。相同冻结输入的自动生成、反向输入
顺序与完整 suite replay 必须产生字节一致的 cases/report。Benchmark report hash 不包含时间戳、
execution id 或 latency；报告 Schema 必须从逐 case 结果重算全部聚合后再验证 output hash。

Benchmark 报告必须原样声明：该 Benchmark 只证明当前冻结人工标签、Graph integrity admission
和确定性回归，不代表线上模型科学质量、泛化能力、实时数据能力或新科学发现。

从仓库根目录执行正式离线回归：

```powershell
uv run --project apps/api python -m services.graph_pipeline.benchmark `
  --cases-output .artifacts/graph-benchmark-cases.json `
  --output .artifacts/graph-benchmark-report.json
```

使用 `--cases` 指向第一次生成的 cases 文件可验证 serialized replay；相同完整 suite 的 cases 与
report 必须字节一致。`.artifacts` 仅是运行输出，不是 Benchmark 输入事实源。

## 11. 明确非目标

本 Pipeline 不实现或授权：

- 数据库迁移、Graph database、既有 ArtifactVersion 原地更新或跨 Project 合并；
- 数据/论文抓取、Crossmatch、字段 selection、质量评分、Claim/Relation/Trace 生成或新的科学
  推断；
- row node、当前 `source` node、无 Evidence 的视觉补点补边或自动反向边；
- HTTP 路由、前端布局、力导向算法、交互筛选状态或 Workspace persistence；
- 把 filter/aggregation/progressive partial view 发布成新科学 Artifact；
- 生产模型调用、Agent 自由代码执行、私有 chain-of-thought、受限全文或凭据保存；
- CacheSelector、ResearchRun 状态推进、RevisionPlan 执行或 ShareSnapshot 发布。

Graph 修订仍遵循 Data Versioning：通过新的 Run 和 Graph ArtifactVersion 表达，既有 ArtifactVersion 保持不可变并与
Evidence；任何展示便利都不能降低 immutable version、Evidence-first 与 Project ownership 门。
