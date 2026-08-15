# Data and Artifact Versioning

| 元数据 | 值 |
| --- | --- |
| Authority | ArtifactVersion、SourceSnapshot、ProducerExecution、修订、分享与哈希规则 |

本文定义已落地科研产物与来源的真实身份，并单独约束尚未接入运行时的修订与缓存契约。运行编排见 [Workflow Design](WORKFLOW_DESIGN.md)。

## 1. 已落地对象与目标契约

| 对象 | 运行边界 | 可变性 | 作用 |
| --- | --- | --- | --- |
| ResearchContract | 当前运行时 | 确认后不可变 | 固定研究目标、字段、来源与质量约束 |
| ResearchArtifact | 当前运行时 | 身份可更新 | 表示逻辑产物并维护 `latest_version_id` |
| ArtifactVersion | 当前运行时 | 内容不可变 | 保存具体产物、内容哈希、输入哈希与 provenance |
| SourceSnapshot | 当前运行时 | 不可变 | 保存一次来源读取的查询、内容与安全元数据 |
| ProducerExecution | 当前运行时 | 完成后不可变 | 保存算法、Pipeline 或模型执行的输入输出身份 |
| DocumentParse | 当前运行时 | 创建后不可变 | ResearchInput-backed 内部 Canonical 解析 derivative；不是公开 ArtifactVersion |
| WorkspaceSnapshot | 当前运行时 | 乐观锁覆盖 | 保存私有 UI 恢复状态，不是科研产物 |
| ShareSnapshot | 当前运行时 | 创建后不可变 | 冻结公开 ArtifactVersion 与 Evidence 范围 |
| CacheRecord | 目标契约 | 不可变 | 绑定真实历史 Run、ArtifactVersion、SourceSnapshot 与复用匹配 identity |
| UserFeedback | 目标契约 | 创建后不可变 | 固定具体 ArtifactVersion 与对象定位 |
| RevisionPlan | 目标契约 | 确认后不可变 | 固定 UserFeedback 与受影响 Artifact 闭包 |

目标契约描述稳定边界，不表示对应表、Repository 或 Workflow 已在当前运行时提供。

## 2. ArtifactVersion 不变量

- `(artifact_id, version_number)` 与 `(artifact_id, publication_key)` 唯一。
- 内容、`content_hash`、`input_hash`、ProducerExecution 与 Evidence 绑定发布后不可修改。
- `latest_version_id` 只是可变读取指针；Evidence、分享与导出必须引用具体 version ID。
- PaperSummary JSON/Markdown 导出必须在读取边界重新闭合对应版本的
  ownership、kind、content hash 与 provenance；导出内容和文件名仅由该已验证的
  immutable ArtifactVersion 决定，不跟随 latest 指针。
- `source_mode` 的 `fixture | live | cached` 是 provenance 事实。只有目标 CacheSelector 选择到绑定真实 origin Run/ArtifactVersion 的 CacheRecord 时才能标记 `cached`；当前运行时不会伪造 cached 结果。
- `supersedes_version_id` 仅在真实发布关系存在时记录，并必须保持同一 Artifact 内的无环 lineage。

## 3. ProducerExecution 与 SourceSnapshot

ProducerExecution 记录 `producer_type`、name/version、可用的 model/prompt identity、parameters/input/output hash、token usage、latency 与执行状态。bounded Function Calling 在同一记录中另固定 provider/tool call identity、授权 tool/skill、registry revision、成功时已校验的 arguments hash、拒绝时仅保存的 rejected arguments hash、error hash 与唯一允许重放的公开 analysis 投影。拒绝记录仅在 provider 返回唯一、非空且有界的 call identity 时保存 tool call ID 与 rejected arguments hash，绝不保存原始 arguments。记录必须绑定 StepAttempt、lease generation 与 idempotency key；完成、失败或拒绝后不可改写为另一结果。不得保存密钥、认证头、完整 Contract、受限全文、原始 provider body 或私有 chain-of-thought。

SourceSnapshot 记录来源身份、查询与内容哈希、抓取时间、许可说明和脱敏 request metadata。同一查询的不同抓取分别形成独立 Snapshot；不得用本地时间或随机值伪造上游版本。

- Upload ResearchInput 可在首次正式解析时按需物化一个固定该 ResearchInput/content hash 的 SourceSnapshot；Snapshot 不复制二进制或全文。
- `image_dataset` 训练固定其 ResearchInput-backed SourceSnapshot；每个 ModelEvaluation 与 ModelArtifact 还必须保存 labels manifest schema、服务器预处理契约、image shape 与 canonical label schema。读取与重放不得重新解释动态目录或未固定预处理参数。
- Upload ResearchInput 派生的 PaperSummary 必须复用 PaperCollection canonicalization
  的唯一 Paper identity authority。在没有可信 DOI、arXiv ID 或完整书目特征时，
  identity basis 为 `source_record`，固定 `research_input:{input_id}` 与完整 ResearchInput
  UUID；禁止从 content hash 截断值、文件名或临时路径生成第二 Paper identity。
  该身份只表示一篇 canonical Paper，不自动宣称已观测到 PaperCollection 成员关系。

## 4. DocumentParse 版本化

- DocumentParse logical identity 固定输入内容、parser/profile/model/config revision 与 Canonical output hash；相同 Project 下严格复用同一身份。
- 不同 parser、model、configuration 或 output revision 新建记录，不原地覆盖；数据库同时禁止更新 Parse 与其 locator。
- Canonical payload 以其内容 hash 进入现有 content-addressed storage，PostgreSQL 仅保存安全引用。读取通过 hash 校验恢复 Canonical Contract，不返回存储路径。

## 5. Canonical hash

- 哈希输入使用 UTF-8、LF 与规范化对象键顺序，格式为 `sha256:<64 lowercase hex>`。
- `input_hash` 覆盖 Contract、输入版本与 Producer 参数；`content_hash` 覆盖发布给消费者的稳定内容。
- 自引用哈希、数据库主键、日志与无业务意义的墙上时钟不进入科学内容哈希；审计字段是否进入哈希由对应 Schema 的 canonical authoring function 决定。

## 6. 分享冻结

ShareSnapshot 固定 `artifact_version_ids` 与允许公开的 `evidence_ids`。Artifact 的 latest 指针变化不会改变已创建分享；Share token 只保存 hash，公开读取不授予写权限。

## 7. 修订与缓存目标契约

- RevisionPlan 将 UserFeedback 映射为受影响产物闭包；确认计划后创建 `derivation_kind=revision` 的新 Run，历史 ArtifactVersion 保持不可变。
- CacheSelector 只能选择 Contract、input hash、producer identity 与 Evidence 仍匹配的 CacheRecord。选择失败时保持 Live 失败事实，不生成 cached ArtifactVersion。
- 当前 HTTP Run authoring 不接受 RevisionPlan、feedback、retry 或 cache 参数；缺少对应执行路径时必须 fail closed。
