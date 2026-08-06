# Literature Reasoning Protocol

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | Claim、Relation 与 ReasoningTrace 的推导、准入与图谱发布规范 |

本文定义跨文献推理的领域规则与准入门禁。模型调用要求见 [Model Policy](MODEL_POLICY.md)，实体模型见 [Data Model](../architecture/DATA_MODEL.md)。

## 1. 概念定义

- **LiteratureClaim**：从文献总结或摘要中抽取的独立科学断言，包含原始与规范化表述、对象、指标/单位、条件与关联 Evidence。
- **LiteratureRelation**：两条 Claim 之间的有向科学关系，表达格式为 `source_claim_id relation_type target_claim_id`。
- **ReasoningTrace**：支持特定 Relation 的分步可审查推导轨迹。

## 2. Relation 类型与方向

所有 Relation 的方向固定为 `source`（关系主语）到 `target`（关系宾语），方向严格不可逆：
- `supports`：两端 Claim 在对象、指标与结论方向上一致相容。
- `extends` / `derived_from`：`A extends B` 表示 A 扩展了 B 的范围/数据；`A derived_from B` 表示 A 存在对 B 的数据/方法依赖。
- `limits`：A 对 B 的适用范围、数据质量或结论强度施加明确限制。
- `contradicts`：在对象、单位与条件完全相容的前地下，两端结论存在冲突。
- `uses_same_dataset` / `compares_method`：结构性关联类型。

## 3. Relation 准入门门禁

一条 Relation 只有在完全满足以下**硬门校验**后，才能被标记为 `accepted` 并允许发布至图谱：
1. **实体与版本存在**：两端 Claim 存在且均属于有效的不可变版本。
2. **方向与类型合法**：`source` 与 `target` 的方向与 Relation 语义完全一致。
3. **Evidence 完整**：两端 Claim 的 Evidence 真实存在且归属正确。
4. **条件与可比性 (Comparability)**：两端 Claim 的对象 (Object)、指标 (Metric) 与单位 (Unit) 必须满足可比性校验。不满足可比性的关系必须硬拒绝 (`rejected`)。
5. **ReasoningTrace 支撑**：存在完整的 `ReasoningTrace` 且推导步骤覆盖双方 Evidence。
6. **校准置信度 (Confidence Assessment)**：外部校准的置信评估达到对应阈值。

硬门校验未通过的关系仅能保留为 `candidate` 或 `rejected`，绝对禁止发布进入图谱。

## 4. ReasoningTrace 规范

- `ReasoningTrace` 仅记录公开可核验的逻辑步骤、参数对比、条件与 Evidence 引用。
- 严禁记录或泄露模型私有的 chain-of-thought 或内部思维过程。

## 5. 学术图谱 (Graph) 发布门

跨文献 `GraphEdge` 发布时必须满足：
1. 必须关联经过准入校验的 `Accepted Relation`；
2. Edge 的源与目标方向必须与 Relation 的 `source` -> `target` 方向完全一致；
3. Edge 必须完整绑定 Evidence、Relation 与 ReasoningTrace；
4. 严禁为了视觉美化生成无科学依据或无法追溯 Evidence 的节点与边。

## 6. 反馈与修订

- 针对 Claim、Relation 或 GraphEdge 的修订必须通过提交 `UserFeedback` 触发。
- 修订由 `derivation_kind=revision` 的新 Run 重新计算受影响闭包，生成新的 `ArtifactVersion` 与 `supersedes` 关系。
- 历史 Relation、Trace、Evidence 与 Graph 保持不可变读。
