# Data and Artifact Versioning

本文定义科研产物的版本治理规则。它是 Phase 1–3 的实现契约，不表示相关数据库表已在 Phase 0 落地。

## 1. 为什么需要版本

同一个 ResearchTask 可能因以下变化产生不同结果：

- 外部数据源快照变化；
- 论文候选集变化；
- 清洗或单位映射规则变化；
- Prompt、模型或参数变化；
- 人工反馈与局部修正；
- 图谱构建规则变化。

只保存“当前值”无法复现答辩截图、解释结论来源或比较模型升级效果。

## 2. 版本对象

### ArtifactVersion

统一描述 Dataset、PaperSummary、Claim 集合、ReasoningTrace、Graph、Export 等产物版本。

最低字段：

```text
id
task_id
artifact_type
artifact_id
version
content_hash
producer_type
producer_version
input_hash
created_at
supersedes_version_id
```

规则：

- `(artifact_type, artifact_id, version)` 唯一；
- 内容不可原地改写；
- 局部修正创建新版本并关联前一版本；
- 展示层可指向 latest，但证据、缓存和导出必须绑定明确版本。

### ExperimentRun

描述一次模型或算法执行。

最低字段：

```text
id
task_id
step_key
model_name
model_parameters
prompt_name
prompt_version
input_hash
output_hash
status
started_at
finished_at
token_usage
latency_ms
error_code
```

规则：

- 不保存密钥；
- 参数中敏感或超长内容必须脱敏；
- 同一输出可关联多个 ArtifactVersion；
- 失败运行也保留记录。

### SourceSnapshot

描述外部数据或论文来源在获取时的可复现信息。

最低内容：

```text
source_id
retrieved_at
query
query_hash
source_version_or_etag
cache_version
license_note
```

## 3. Hash 规则

- JSON 在 hash 前必须使用稳定键排序与统一编码；
- 文本统一 UTF-8 与换行；
- 二进制文件使用 SHA-256；
- hash 用于识别内容，不代替业务主键；
- 模型输入 hash 必须覆盖 Prompt 版本、模型参数和证据 ID/版本。

## 4. 修正与删除

- 用户反馈生成 `UserFeedback`；
- 修正生成新 ArtifactVersion；
- 旧版本默认保留，除非涉及密钥、侵权或依法删除；
- 图谱边修正必须同步 Relation、ReasoningTrace 和 Evidence 版本；
- 删除操作保留审计元信息，但不保留必须清除的敏感内容。

## 5. 缓存绑定

缓存记录至少指向：

- 原始 task/run；
- ArtifactVersion；
- SourceSnapshot；
- Prompt/模型版本；
- 创建时间和适用输入 hash。

缓存不得只保存一个无来源 JSON 文件。

## 6. MVP 实施顺序

1. Phase 1：SourceSnapshot 与关键产物 content hash。
2. Phase 2：ReasoningTrace/Graph 明确绑定产物版本。
3. Phase 3：ArtifactVersion、ExperimentRun、ModelCall 落库与比较视图。

任何阶段都不得为了版本治理提前引入 Redis、对象存储或图数据库。
