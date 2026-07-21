# Literature Reasoning Protocol

| 元数据    | 值                                                       |
| --------- | -------------------------------------------------------- |
| Status    | Accepted                                                 |
| Authority | Claim、Relation、ReasoningTrace 的生成、准入、评测与修订 |

本文定义跨文献推理的领域规则。模型调用要求见 [Model Policy](MODEL_POLICY.md)，Prompt 版本见 [Prompt Versioning](PROMPT_VERSIONING.md)，实体字段见 [Data Model](../architecture/DATA_MODEL.md)。

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

- paper id 和输入 Summary version；
- claim type；
- 原始可核验表述与规范化表述；
- 对象、指标、单位、范围和 conditions；
- evidence ids；
- confidence；
- `candidate | accepted | rejected` 状态及拒绝原因。

Claim normalization 不得改变结论方向、删除关键限制或合并不可比较对象。

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

只有在对象、定义、单位、条件、统计口径和比较目标足够一致时使用。无法建立可比性时，应使用 `limits` 或保留 candidate。

### uses_same_dataset / compares_method

属于结构关系，不自动推导 supports、limits 或 contradicts。

## 5. Relation 准入

Relation 至少包含：

- source / target claim ids；
- relation type；
- 显式 conditions 和 comparability note；
- 双方 evidence ids；
- reasoning trace id；
- confidence；
- `candidate | accepted | rejected` 状态；
- rejection / review reason。

Accepted Relation 必须同时满足：

- 两端 Claim 存在且属于明确版本；
- relation type 合法；
- source/target 方向与 Relation 类型语义一致；
- 双方 Evidence 存在并属于对应 Claim；
- conditions 不冲突且对象可比较；
- ReasoningTrace 存在并覆盖双方 Evidence；
- confidence 在合法范围；
- 未绕过来源许可、全文或安全边界。

不满足任一条件的记录不得进入最终 Graph。

Relation 的人工 review status 进入 `approved` 时，无论 admission status 是 candidate、accepted 还是 rejected，都必须绑定 review-approved ReasoningTrace；负例 Trace 记录不可比或拒绝依据，不将 rejected 关系发布到 Graph。

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
- Relation 科研审核正确率；
- Evidence 覆盖率；
- 无 Evidence / 不可比关系拦截率；
- candidate → accepted / rejected 分布；
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
