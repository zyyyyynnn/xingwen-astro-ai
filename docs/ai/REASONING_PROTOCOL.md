# Literature Reasoning Protocol

| 元数据    | 值                                                       |
| --------- | -------------------------------------------------------- |
| Status    | Accepted                                                 |
| Authority | Claim、Relation、ReasoningTrace 的生成、准入、评测与修订 |

本文定义跨文献推理的领域规则。模型调用要求见 [Model Policy](MODEL_POLICY.md)，Prompt
版本见 [Prompt Versioning](PROMPT_VERSIONING.md)，实体字段见
[Data Model](../architecture/DATA_MODEL.md)，D-08 固定准入顺序、拒绝枚举、hash、
Publisher seal 和 Benchmark 运行方式见
[LiteratureRelation Pipeline](../engineering/LITERATURE_RELATION_PIPELINE.md)。

## 1. 输入前提

只接收已经通过以下检查的输入：

- PaperSummary 来自明确 ArtifactVersion；
- Paper、Summary 和 Claim candidate 可定位 SourceSnapshot 与 Evidence；
- Evidence 含 locator、quote_or_value 和 extraction method；
- 比较对象、字段、单位、研究范围和必要条件可识别；
- 输入 Schema、Prompt/model 和 producer 版本可定位。

标题相似、关键词重合、引用关系或模型自信度不能单独作为科学关系依据。

## 2. 处理流程

```text
PaperSummary ArtifactVersion
-> Claim extraction and normalization
-> candidate pairing
-> relation classification
-> condition and comparability check
-> Evidence consistency check
-> ReasoningTrace construction
-> candidate / accepted / rejected admission
```

每个阶段保存结构化输出和拒绝原因，不以不可审查的长文本替代领域对象。

## 3. Claim

LiteratureClaim 至少包含：

- paper id、输入 PaperSummary ArtifactVersion、Summary/statement id；
- claim type、polarity；
- 原始可核验表述与规范化表述；
- objects、metric/unit、conditions、scope、limitations、qualifiers、uncertainty
  和 comparison basis；
- Evidence/SourceSnapshot ids、normalization version 与稳定 fingerprint；
- Prompt/model/parameters/ProducerExecution、input/model-response/output hash；
- `candidate | accepted | rejected` 状态、failure stage 及拒绝原因。

Claim normalization 不得改变结论方向、删除关键限制或合并不可比较对象。
confidence 不属于 D-07 Claim Schema，也不能作为科学正确性或准入依据。D-07 唯一
编写源是 `apps/api/src/app/schemas/literature_claim.py`；Phase 0
`app.schemas.reasoning.LiteratureClaim` 及其 `LiteratureReasoningResponse` 包络只保留
冻结传输兼容，不能进入 Publisher。

## 4. Relation 类型

所有 Relation 使用 `source_claim_id relation_type target_claim_id`：source 是关系主语，target 是关系宾语。ReasoningTrace premises 与 GraphEdge endpoints 必须保持相同方向，不得把两端当作无序集合。

### supports

两条 Claim 在对象、指标、条件和结论方向上相容。只能表述为“提供支持证据”，不得写成绝对证明。

### extends / derived_from

- `A extends B`：source A 明确扩展 target B 的对象、数据、方法或适用范围。
- `A derived_from B`：source A 对 target B 存在可核验的前置数据、方法或产物依赖。

仅时间更晚或主题相似不构成扩展关系。

### limits

`A limits B` 表示 source A 对 target B 的适用范围、样本偏差、数据质量、方法或解释强度施加限制。

### contradicts

只有在对象、定义、单位、条件、统计口径和比较目标足够一致时使用。`limits` 也必须有
可比较命题和限制证据；无法建立对象、指标或单位可比性时应 rejected，不能靠改成
`limits`、降低 confidence 或保留 candidate 绕过硬门。

### uses_same_dataset / compares_method

属于结构关系，不自动推导 supports、limits 或 contradicts。

## 5. Relation 准入

Relation 至少包含：

- source / target claim ids；
- relation type；
- 显式 conditions 和 comparability note；
- 双方 evidence ids；
- reasoning trace id；
- 外部版本化且经过校准的 confidence assessment；
- `candidate | accepted | rejected` 状态；
- rejection / review reason。

Accepted Relation 必须同时满足：

- 两端 Claim 存在且属于明确版本；
- relation type 合法；
- source/target 方向与 Relation 类型语义一致；
- 双方 Evidence 存在并属于对应 Claim；
- conditions 不冲突，且对象、指标、单位分别为 comparable 或协议明确允许的 not applicable；
- ReasoningTrace 存在并覆盖双方 Evidence；
- confidence assessment 的 definition、calibration、scope 和 threshold 版本受支持，且
  score 达到 accepted threshold；
- 未绕过来源许可、全文或安全边界。

不满足任一条件的记录不得进入最终 Graph。

D-08 唯一 Pydantic 编写源是 `apps/api/src/app/schemas/literature_relation.py`。模型只
输出 `LiteratureRelationExtractionOutput`，不得直接决定 admission；只有 Pipeline
返回并封印的 `LiteratureRelationsCandidate@1.0.0` 可以交给 Publisher。该单一
`kind=literature_relations` candidate 在同一内容闭包中保存 Relation、
ReasoningTrace、双方 Claim、Evidence/SourceSnapshot、confidence 与 ProducerExecution；
D-08 不另行发布 `reasoning_traces` Artifact。

confidence 表示对完整 `relation type + admission decision` 的校准置信，不是 Relation
为真或可接受的概率。Evidence、ownership、方向、conditions、comparability 与 Trace
硬门优先；阈值 `0.9` 只在全部硬门通过后区分 accepted 与 candidate。已经验证的
`not_evaluable` assessment 形成 candidate；assessment 引用缺失/未知、definition 未
版本化、calibration 缺失，或 assessment 的 source/target Claim ArtifactVersion+Claim、
relation type fingerprint、最终 admission decision 与当前 Relation 不一致，都是硬拒绝。
同一 assessment 不得跨方向、版本、relation type 或 decision 复用。D-01 两条 rejected Relation 的原始 confidence
均为 `0.99`，不得因高于阈值改成 accepted。

Relation 的网页端 GPT 科研 review status 进入 `approved` 时，无论 admission status 是 candidate、accepted 还是 rejected，都必须绑定 review-approved ReasoningTrace；负例 Trace 记录不可比或拒绝依据，不将 rejected 关系发布到 Graph。

## 6. ReasoningTrace

ReasoningTrace 至少包含：

- relation id；
- premise claim ids；
- 可审查的比较步骤；
- 每步引用的 evidence ids；
- relation type 的选择依据；
- conditions、限制和不确定性；
- Prompt/model 或规则版本；
- review status。

Trace 只保存公开可核验的依据和结构化转换，不记录模型私有 chain-of-thought、逐 token 推理或隐藏 Prompt 内容。
D-08 对 Trace 之外的 direction/comparability basis、conditions/conflicts/uncertainties
和 confidence basis 使用同一安全门；rejected audit record 只保留稳定脱敏占位符，不
回显命中的模型自由文本。

D-08 `LiteratureReasoningTraceCandidate` 还固定 Relation admission status、
ProducerExecution、input/model-response hash，并要求 step 从 1 连续编号、premise Claim
严格按 source/target 顺序、Trace Evidence 覆盖双方 Relation Evidence。rejected
Relation 可保留符合安全边界的负例 Trace，但不得进入 Graph。

## 7. Graph 发布门

跨文献 GraphEdge 只有在以下条件满足时才能发布：

- 引用 Accepted Relation；
- relation、source claim、target claim 均存在；
- edge source/target 与 Relation source/target 方向一致；
- Evidence 和 ReasoningTrace 引用完整；
- 版本属于允许的 Project / Run 上下文；
- edge type 与 Graph taxonomy 一致；
- 没有悬空或跨版本错误引用。

Layout、坐标和视觉聚合不能改变 Relation 的科学语义。

## 8. 评测

固定 Benchmark 至少报告：

- Claim Schema 通过率与科研审核正确率；
- candidate pairing 覆盖；
- Relation 科研标签 exact match 与 admission rejection exact pass，不能合并成总分；
- Relation Evidence 与 Trace-step Evidence 各自的覆盖率；
- 无 Evidence / 不可比关系拦截率和最早拒绝阶段；
- candidate → accepted / rejected 分布；
- confidence assessed/not_evaluable/calibrated 数量和原始分布；
- Graph 完整性；
- Prompt/model 版本变化带来的差异。

评测样例、版本和网页端 GPT 科研审查依据必须可复现；PR 技术 Review 与 Benchmark 科研 Review 不互相替代。

## 9. 人工反馈与修订

人工修订必须：

1. 创建绑定基线 ArtifactVersion 的 Feedback；
2. 生成包含影响闭包的 RevisionPlan；
3. 通过新的 revision Run 重算受影响 Summary、Claim、Relation、Trace 或 Graph；
4. 创建新的 ArtifactVersion 和 supersedes 关系；
5. 保留原版本、Feedback、Evidence 和 producer 记录；
6. 重新执行 Relation 准入和 Graph 完整性检查。

不得直接修改已发布 Relation、Trace、Evidence 或 GraphEdge。
