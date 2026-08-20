# Evidence Graph Pipeline

| 元数据 | 值 |
| --- | --- |
| Authority | Evidence Graph 的生成、准入、Evidence 使用、发布与读取边界 |
| Scope | Graph candidate、Publisher handoff、固定 Benchmark 与渐进读取规范 |

本文是 Evidence Graph Pipeline 的唯一运行 Authority。领域实体与所有权由 [Data Model](../architecture/DATA_MODEL.md) 定义，ArtifactVersion 与 hash 通则由 [Data Versioning](../architecture/DATA_VERSIONING.md) 定义，Relation/ReasoningTrace 语义由 [Reasoning Protocol](../ai/REASONING_PROTOCOL.md) 定义，结构化数据输入由 [Data Artifacts](DATA_ARTIFACTS.md) 定义。

## 1. 输入、输出与所有权

Evidence Graph 只消费同一 Project 内已经固定的不可变输入：

- 完整发布的 LiteratureRelations ArtifactVersion 及其 PaperSummary、Claim、Relation、ReasoningTrace 与 provenance 闭包；
- 可选但不可拆分的 Dataset/FieldDictionary ArtifactVersion 对，两者必须来自同一构建闭包并共享通过门禁的 DataQuality projection；
- 上述版本声明的 Evidence、SourceSnapshot、Producer、schema version、content/input/output hash；
- Graph taxonomy、构建策略、容量策略与显式 build scope 的 technical identity。

输入不得引用动态 `latest`。Fixture、Recorded、Benchmark、Cached 与 Live 必须保持其真实来源语义。若调用方缩小构建范围，scope 必须在构建前显式声明并进入 `input_hash`，且所包含节点/边仍保持完整 Evidence 闭包。

输出是一个不可变、typed、publisher-ready `GraphArtifactCandidate`，至少封闭：

- 节点、边及稳定身份与确定性顺序；
- 每条边绑定的上游 ArtifactVersion、Evidence 与 SourceSnapshot；
- Graph 自有 Evidence-use identity；
- taxonomy/schema/producer/build/capacity policy identity；
- 输入版本集合、`input_hash`、`output_hash` 与完整性计数。

Pipeline 不创建数据库 ArtifactVersion/Evidence，不推进 ResearchRun，不更新 latest pointer，不承担 HTTP DTO 或页面状态。数据库物化只发生在 Publisher 事务内。

## 2. 节点身份

节点身份来自上游领域 identity，而不是 label、数组位置或当前 ArtifactVersion：

- `dataset` 使用 `ResearchArtifact.artifact_id`；构建所用 ArtifactVersion 仅作为 provenance；
- `field` 由 `field_manifest_id + canonical_field_id` 构成；source column、alias、展示 label 与 Dataset row 不进入 identity；
- Paper、Claim、Relation、ReasoningTrace 使用其上游 typed identity；ReasoningTrace 固定其所属的 `LiteratureRelations` ArtifactVersion，不拥有独立 ArtifactVersion；
- `source` 是 taxonomy 保留类型；来源真实性通过 SourceSnapshot/Evidence provenance 表达，Pipeline 不凭展示数据生成 source node；
- `research_goal` 只有在 Graph input contract 明确提供版本固定的 ResearchGoal Authority 时才允许生成，不能从 Project 名称、Dataset metadata 或页面文本推测。

Graph 不生成 row node。Dataset row、SourceValue、selection、null、unresolved 与 conflict 属于数据产物内部结构，只能经明确领域投影进入 Graph。

## 3. Edge 与 Evidence closure

任何 edge 必须具备可验证的 Evidence closure。跨文献 Relation edge 必须固定 Relation、ReasoningTrace、对应 Evidence 与其 SourceSnapshot；数据 edge 必须固定产生相关实体/字段投影的 Dataset/FieldDictionary ArtifactVersion 及其 Transformation/Crossmatch Evidence。

Graph-owned Evidence 不能复用 upstream Evidence id。Publisher 为每个 Evidence-use 创建新的 persisted Evidence identity，并在 locator 中保存 upstream ArtifactVersion/Evidence/target/hash，使 Graph 自有声明与上游科研证据可双向追溯。

restricted upstream Evidence 的限制必须原样传播，不能因进入 Graph 而降级权限或把不可公开内容写入公共 locator。

## 4. 构建与确定性

构建顺序必须由稳定 identity 排序，不能依赖 Python set/dict 插入顺序、数据库自增值或 wall clock。相同固定输入、策略与 producer identity 必须得到相同 `input_hash`、Graph content 与 `output_hash`。

Graph build 至少验证：

1. 所有输入 ArtifactVersion 属于同一 Project；
2. Artifact kind 与 typed content 匹配；
3. Literature/Data 输入闭包完整，半闭合 Dataset/FieldDictionary 组合拒绝；
4. 节点 identity 唯一；
5. edge 端点存在；
6. edge Evidence-use 完整且没有悬空 SourceSnapshot/Evidence；
7. source snapshot registry 与 upstream exact identity 一致；
8. 容量策略在物化前 fail closed；
9. content/input/output hash 复算一致。

## 5. Admission 与 Publisher

`GraphArtifactCandidate` 是唯一可发布 Graph candidate。Publisher 的 admission boundary 按 candidate kind 做 exact class 检查，任意 read projection、dict、自定义 wrapper 或只携带相同字段的 Pydantic model 都不能取得 Graph 发布资格。

Graph publication 还必须提供 persisted SourceSnapshot/Evidence bindings。Publisher 在同一 fenced transaction 内验证：

- Run/RunStep/StepAttempt 与 ProducerExecution 一致；
- lease generation 未失效；
- persisted SourceSnapshot 属于同 Project 且 source/version/content hash 与 candidate 一致；
- upstream Evidence 的 ArtifactVersion、target、type、SourceSnapshot、restriction 与 evidence hash 一致；
- Graph-owned Evidence id 新建且唯一；
- publication key replay 与原 content/producer/provenance 完全一致。

任何不一致都 fail closed，不通过 alias、兼容 DTO 或 fallback candidate 绕过。

## 6. Benchmark

Graph Benchmark 只验证当前 Graph contract、scientific fixtures 与 deterministic admission，不是生产输入源。Benchmark/Fixture 可复用 production builder/admission 组件，但必须保持 `benchmark`/`fixture` 数据等级，不得表示为 Live。

Benchmark machine asset 只保存当前技术 identity、当前 scientific payload、当前 review record、当前 scope/verdict 与用于复现的 hashes。历史审查和变更由 Git 保存，不在 JSON 中维护 review chain 或 change log。

## 7. 读取边界

Graph 读取只从已发布 ArtifactVersion 与持久化 provenance 构建 typed read model；读取层不重新运行 graph build、admission 或科研推导。分页/渐进读取只能改变传输切片，不能改变 Graph identity、Evidence closure 或已固定版本。

公共读取与 Share 必须固定明确 ArtifactVersion。权限、restricted Evidence 与 source visibility 在读取边界执行；Graph 的节点/边标签不能泄漏不可见 Evidence 内容。

## 8. 维护规则

1. Graph taxonomy/build/admission 策略变更必须同步 technical identity、hash、schema 与 benchmark。
2. `ArtifactVersion` 是跨领域统一版本机制；Graph 名称本身不编码发布批次或工作阶段。
3. Pipeline、Publisher、Repository、Router、Workspace 各守其职责，不复制 Graph 算法或 Evidence 规则。
4. Git 保存定义演进；GitHub 保存任务状态；活动源码与 Authority 只维护当前事实。
