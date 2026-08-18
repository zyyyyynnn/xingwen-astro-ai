# Literature Reasoning Protocol

| 元数据 | 值 |
| --- | --- |
| Authority | Claim、Relation 与 ReasoningTrace 的推导、准入与图谱发布规范 |

本文定义跨文献推理的领域规则与准入门禁。模型调用要求见 [Model Policy](MODEL_POLICY.md)，实体模型见 [Data Model](../architecture/DATA_MODEL.md)。

## 1. 概念定义

- **LiteratureClaim**：从文献总结或摘要中抽取的独立科学断言，包含原始与规范化表述、对象、指标/单位、条件与关联 Evidence。
- **LiteratureRelation**：两条 Claim 之间的有向科学关系，表达格式为 `source_claim_id relation_type target_claim_id`。
- **ReasoningTrace**：支持特定 Relation 的分步可审查推导轨迹。

### 1.1 公开消息边界

四类边界严格区分，不得互相替代或混写：

| 边界                        | 语义                                             |
| --------------------------- | ------------------------------------------------ |
| `assistant_message`         | 用户可见的自然研究交流，写入 Research Thread     |
| Run public reasoning activity | 步骤级公开摘要（`public_analysis`），次级信息  |
| `ReasoningTrace`            | Evidence-bound 正式领域产物                      |
| Provider private reasoning  | 不保存、不显示、不导出                           |

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
4. **条件与可比性 (Comparability)**：两端 Claim 的对象 (Object) 必须可比；`supports | extends | limits | contradicts` 还必须按双方实际指标 (Metric) 与单位 (Unit) 通过可比性校验。`derived_from | uses_same_dataset | compares_method` 属于依赖或结构关系，不以科学指标和单位作比较，其 Metric/Unit 状态必须为 `not_applicable`。不满足对应关系语义的候选必须硬拒绝 (`rejected`)。
5. **ReasoningTrace 支撑**：存在完整的 `ReasoningTrace` 且推导步骤覆盖双方 Evidence。
6. **校准置信度 (Confidence Assessment)**：外部校准的置信评估达到对应阈值。

硬门校验未通过的关系仅能保留为 `candidate` 或 `rejected`，绝对禁止发布进入图谱。`LiteratureRelations` ArtifactVersion 是一次准入结果的可审计聚合：只要模型输出通过 JSON/Schema 解析并形成记录，即使全部记录均为 `rejected`，聚合产物与空的 `ReasoningTrace` 投影仍应如实发布；发布聚合不改变记录状态，也不授予图谱准入资格。

## 4. ReasoningTrace 规范

- `ReasoningTrace` 仅记录公开可核验的逻辑步骤、参数对比、条件与 Evidence 引用。
- 严禁记录或泄露模型私有的 chain-of-thought 或内部思维过程。

## 5. 学术图谱 (Graph) 发布门

跨文献 `GraphEdge` 发布时必须满足：
1. 必须关联经过准入校验的 `Accepted Relation`；
2. Edge 的源与目标方向必须与 Relation 的 `source` -> `target` 方向完全一致；
3. Edge 必须完整绑定 Evidence、Relation 与 ReasoningTrace；
4. 严禁为了视觉美化生成无科学依据或无法追溯 Evidence 的节点与边。

## 6. 反馈与修订准入

UserFeedback 必须固定目标 ArtifactVersion、对象 locator、建议内容与提交者可见 Evidence。RevisionPlan 将一组 Feedback 映射为受影响 Artifact 闭包；只有确认后的 Plan 才能创建 `derivation_kind=revision` 的派生 Run。没有 Revision executor 时，系统不得接受 feedback 参数后返回成功，也不得覆盖原 ArtifactVersion。
