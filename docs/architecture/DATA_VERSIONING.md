# Data and Artifact Versioning

| 元数据 | 值 |
| --- | --- |
| Authority | ArtifactVersion、SourceSnapshot、ProducerExecution、修订、分享与哈希规则 |

本文定义已落地科研产物、来源、缓存选择与修订的真实身份。运行编排见 [Workflow Design](WORKFLOW_DESIGN.md)。

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
| CacheRecord | 当前运行时 | 创建后不可变 | 绑定真实历史 Run、ArtifactVersion、SourceSnapshot 与复用匹配 identity |
| CacheSelectionAudit | 当前运行时 | 创建后不可变 | 固定当前 recoverable failure、选择条件、命中或拒绝原因与可选 origin |
| UserFeedback | 当前运行时 | 创建后不可变 | 固定具体 ArtifactVersion、基线 hash 与对象定位 |
| RevisionPlan | 当前运行时 | 创建后不可变 | 固定 UserFeedback、parent Run revision、ArtifactVersion 决策与受影响 Step 闭包 |
| RevisionPlanConfirmation | 当前运行时 | 创建后不可变 | 一对一固定 Plan、确认请求与 revision Run |

## 2. ArtifactVersion 不变量

- `(artifact_id, version_number)` 与 `(artifact_id, publication_key)` 唯一。
- 内容、`content_hash`、`input_hash`、ProducerExecution 与 Evidence 绑定发布后不可修改。
- `latest_version_id` 只是可变读取指针；Evidence、分享与导出必须引用具体 version ID。
- `execution_mode` 是运行时执行意图，`source_mode` 的 `fixture | recorded | live | cached` 是实际 provenance 事实；`recorded` 不等同于 fixture、cached 或 live。CacheSelector 命中只返回并审计绑定真实 origin Run/ArtifactVersion 的 CacheRecord，不复制 ArtifactVersion；后续 cached ArtifactVersion 仍只能由 Publisher 在显式消费该选择结果的执行闭环中发布，当前 HTTP/runtime 不伪造该发布。
- `supersedes_version_id` 仅在真实发布关系存在时记录，并必须保持同一 Artifact 内的无环 lineage。

## 3. ProducerExecution 与 SourceSnapshot

ProducerExecution 记录 `producer_type`、name/version、可用的 model/prompt identity、parameters/input/output hash、token usage、latency 与执行状态。不得保存密钥、认证头、受限全文或私有 chain-of-thought。

SourceSnapshot 记录来源身份、查询与内容哈希、抓取时间、许可说明和脱敏 request metadata。同一查询的不同抓取分别形成独立 Snapshot；不得用本地时间或随机值伪造上游版本。

- Upload ResearchInput 可在首次正式解析时按需物化一个固定该 ResearchInput/content hash 的 SourceSnapshot；Snapshot 不复制二进制或全文。

## 4. DocumentParse 版本化

- DocumentParse logical identity 固定输入内容、parser/profile/model/config revision 与 Canonical output hash；相同 Project 下严格复用同一身份。
- 不同 parser、model、configuration 或 output revision 新建记录，不原地覆盖；数据库同时禁止更新 Parse 与其 locator。
- Canonical payload 以其内容 hash 进入现有 content-addressed storage，PostgreSQL 仅保存安全引用。读取通过 hash 校验恢复 Canonical Contract，不返回存储路径。

## 5. Canonical hash

- 哈希输入使用 UTF-8、LF 与规范化对象键顺序，格式为 `sha256:<64 lowercase hex>`。
- `input_hash` 覆盖 Contract、输入版本与 Producer 参数；`content_hash` 覆盖发布给消费者的稳定内容。
- 自引用哈希、数据库主键、日志与无业务意义的墙上时钟不进入科学内容哈希；审计字段是否进入哈希由对应 Schema 的 canonical authoring function 决定。

## 6. 分享冻结

ShareSnapshot 固定 `artifact_version_ids`、允许公开的 `evidence_ids` 以及创建时已脱敏的 ArtifactVersion/Evidence/SourceSnapshot identity 投影。Artifact 的 latest 指针变化或 API 进程重启不会改变已创建分享；Share token 只保存 hash，公开读取不授予写权限。撤销或过期达到保留期后可清理分享记录，但不得修改被引用的 ArtifactVersion、Evidence 或 SourceSnapshot。

## 7. 修订与缓存运行时

- RevisionPlan 将同一 completed parent Run 的 UserFeedback 映射为受影响产物闭包，并冻结 parent revision 与 Project 全部 current ArtifactVersion。确认计划时再次验证这些指针，在同一事务创建 Confirmation 与 `derivation_kind=revision` Run；历史 Run 和 ArtifactVersion 保持不可变。
- 数据产物影响数据三类与 Graph；PaperCollection 影响 Summary、Claim、Relation、Trace 与 Graph；Summary、Claim、Relation、Trace、Graph 依次只影响自身及其下游。抽象 kind 闭包只在父 Contract 的 canonical RunStep 闭包内生效；只有仍为 latest、确由 parent Run 发布且实际存在的 ArtifactVersion 才能标记 recompute，其他 frozen ArtifactVersion 均作为 reuse identity 暴露给既有 Workflow/Publisher，不复制内容或直接发布新版本。
- CacheRecord 注册与选择时重新验证 completed Live origin Run、`source_mode=live` ArtifactVersion、ArtifactVersion content canonical hash、completed ProducerExecution、Contract hash、非空 SourceSnapshot/Evidence closure、每个 SourceSnapshot 的 source-owned typed query identity、SourceSnapshot identity hash 与数据产物质量投影；Fixture、recorded/cached version、失败 Run、identity 不闭合或无法按来源契约重建的查询必须拒绝。
- CacheSelector 只能在 `fallback_on_recoverable_failure` 的 failed Live Run 上，针对 failed/retryable Attempt 与调用方明确指定的 failed ProducerExecution，选择 Contract、input hash、producer/Prompt、来源范围、质量约束、Evidence 要求与有效期全部匹配且 provenance 仍闭合的 CacheRecord。
- 命中与拒绝均保留原 `run.failed` 事实并追加单调 Event/不可变审计；选择不改变 failed Run 或 origin Run 的终态，不移动 Artifact latest，不生成或复制 cached ArtifactVersion。相同 RunStep/selector request 并发选择只产生一份审计与 Event。
- original Run authoring 不接受 RevisionPlan、feedback、retry 或 cache 参数；revision Run 只能由确认端点创建。CacheSelector 仍是内部能力；缺少公开执行路径的 retry、fork 或 cached publication 必须 fail closed。
