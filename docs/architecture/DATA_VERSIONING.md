# Data and Artifact Versioning

| 元数据 | 值 |
| --- | --- |
| Authority | ArtifactVersion、来源、缓存、修订、分享与保留规则 |

本文定义科研产物、来源快照、运行缓存、修订版本与分享快照的版本控制规则。

## 1. 版本对象分类

| 对象 | 是否不可变 | 说明与用途 |
| --- | --- | --- |
| ResearchContract | 确认后不可变 | 固定 Run 的研究输入协议与质量要求 |
| ResearchRun | 创建后不可变 | 记录一次由 Contract 驱动的独立执行 |
| ResearchArtifact | 身份可更新 | 表示同一逻辑产物，维护 `latest_version_id` 指针 |
| ArtifactVersion | 内容不可变 | 唯一的版本快照，是 Evidence、Cache、Share 的绑定单位 |
| SourceSnapshot | 不可变 | 抓取或检索到的原始数据/文献快照 |
| CacheRecord | 不可变 | 绑定真实历史 Run/Version 的复用记录 |
| WorkspaceSnapshot | 乐观锁可覆盖 | 私有 UI 恢复状态，非科研产物 |
| ShareSnapshot | 创建后不可变 | 冻结公开的版本快照与脱敏范围 |

## 2. ArtifactVersion 不变量

- **版本唯一性**：`(artifact_id, version_number)` 组合在系统中绝对唯一。
- **不可变性**：`ArtifactVersion` 创建并计算 `content_hash` 后严禁原地修改内容。`latest_version_id` 仅为可变指针。
- **引用锁定**：Evidence、ShareSnapshot 与 Export 必须固定引用具体的 `version_id`，绝对不引用动态 `latest`。
- **来源追踪**：`source_mode` 仅允许 `fixture | live | cached`。Cached 必须关联真实的 `origin_run_id` 与 `origin_artifact_version_id`。
- **修订链表**：修订生成新 `ArtifactVersion`，并通过非空的 `supersedes_version_id` 形成无环单向链。

## 3. ProducerExecution

`ProducerExecution` 记录模型或算法执行的可复现元信息：
- 包含 `producer_type`、`producer_name`、`producer_version`、`model_name`、`prompt_name`、`prompt_version`、`prompt_hash`、`parameters_hash`、`input_hash`、`output_hash`、`token_usage` 与 `latency_ms`。
- 严禁保存 Secrets 密钥、认证头、完整受限全文或模型私有 chain-of-thought。

## 4. SourceSnapshot 版本化

- 包含 `source_id`、`retrieved_at`、`query_hash`、`content_hash`、`license_note` 与脱敏后的 `request_metadata`。
- 相同查询在不同时间抓取产生独立的 `SourceSnapshot` 实例。

## 5. 哈希 (Hash) 计算规则

- **统一格式**：哈希前数据使用 UTF-8 编码、规范化键顺序与 LF 换行符。`content_hash` / `input_hash` 采用 `sha256:<hex>` 格式。
- **排除干扰**：哈希计算排除日志、数据库主键 ID、墙上时钟 (wall-clock) 与自引用哈希。
- **版本哈希分离**：`input_hash` 覆盖研究契约、输入版本与模型/Prompt 参数；`content_hash` 覆盖发布给客户端的稳定 JSON 内容。

## 6. 修订与缓存

- **修订 (Revision)**：确认 `RevisionPlan` 后创建新 Run，重新计算受影响步骤并生成新的 `ArtifactVersion`；历史版本完全保留并支持 Compare 对照。
- **缓存 (Cached)**：只有来自真实历史 Run 且通过契约/Evidence 校验的产物才能标记为 Cached。Fixture 数据绝对不可作为真实 Cached 使用。

## 7. 分享与导出版本控制

- `ShareSnapshot` 仅冻结已发布的 `artifact_version_ids` 与允许公开的 `evidence_ids`。
- 即使后续产生了新的 `ArtifactVersion` 或更新了 `latest_version_id`，既有分享链接的内容绝对保持冻结、不随之改变。
