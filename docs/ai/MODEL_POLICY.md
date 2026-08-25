# Model Policy

| 元数据    | 值                                          |
| --------- | ------------------------------------------- |
| Authority | 模型输出准入、执行记录、Evidence 与失败语义 |

模型与比赛资格由 [Competition Compliance](../product/COMPETITION_COMPLIANCE.md) 约束；Prompt identity 由 [Prompt Registry](PROMPT_REGISTRY.md) 管理。本文定义模型执行边界、候选输出准入与 provenance 规则。

## 1. 模型输出不是发布事实

模型输出必须先解析为对应的 Pydantic output model，再通过领域、Evidence、质量与 hash 准入。原始自由文本、解析失败内容或缺少 Evidence 的结论不得成为 ArtifactVersion。

当前使用模型候选的文献 Pipeline 包括 PaperSummary、LiteratureClaim 与 LiteratureRelation。每条 Pipeline 独立验证输入 ArtifactVersion、Prompt identity、输出 Schema、Evidence locator、状态计数与 canonical output hash。

## 2. Pre-run ModelExecutionRecord 与 ProducerExecution

Research assistant 的分析发生在 Run 之前，必须使用独立的 `ModelExecutionRecord`。它记录 provider、requested model、provider 返回 model（可得时）与真实存在的显式 revision（可为空）、Prompt name/version/hash、安全规范化后的 Prompt/input/output/parameters snapshot 及其 hash、状态、token usage、latency、provider request id、error code 与时间边界。它不等同于 Run 内 Pipeline 的 ProducerExecution，也不能替代后者。浮动模型别名不得伪造不可变 revision；未显式固定 revision 时该字段必须为空。

Run 内模型 Pipeline 使用 ProducerExecution 保存与 ModelExecutionRecord 相同的模型 provenance 语义：

- `producer_type=model`、producer identity 与 requested model；
- provider 返回 model（可得时）与真实显式 revision（可为空）；
- `prompt_name`、`prompt_version`、`prompt_hash`；
- `parameters_hash`、`input_hash`、`output_hash`；
- 状态、错误码、token usage 与 latency。

两类记录均不得包含 API key、认证头、受限全文、原始 provider body 或私有 chain-of-thought。ModelExecutionRecord 的 output snapshot 只能保存通过 Pydantic 与领域校验的公开 outcome；ReasoningTrace 只保存可审查的依据、假设、限制、Evidence 与 Claim/Relation 引用。失败记录必须保存失败发生前已经获得的安全 hash、token、latency 与 provider request id，不得因失败丢失调用证据。

## 3. 失败关闭

- JSON 解析、Schema、Evidence、方向、单位、可比性或 provenance 校验失败时，Candidate 必须拒绝或标记为对应科学状态。
- 可恢复的外部失败只在调用方已有的有界 attempt 规则内重试；失败不得用 Fixture 冒充 Live 结果。
- Pipeline 不得自行推进 ResearchRun、写 Artifact latest pointer 或绕过 Publisher。

## 4. 可复现身份

发布身份必须固定实际使用的 Prompt 内容 hash、模型/producer identity、参数 hash、输入 ArtifactVersion 与输出 hash。动态别名、页面状态或未持久化临时对象不得作为可复现事实源。

## 5. ModelExecutionPort

ModelExecutionPort 是 provider-neutral 的模型执行边界，拥有 typed request、Prompt identity、参数、超时、token usage、provider request identity 与原始失败分类。Provider Adapter 只负责调用与传输映射，不能决定 Artifact 准入或推进 Run。

调用方必须先存在可验证的 Adapter 与对应 execution writer 才能执行该 Port。Research assistant 在没有 provider credentials 时必须以 `MODEL_RUNTIME_UNAVAILABLE` 失败；不得生成模板响应、模拟模型响应、成功状态、ArtifactVersion 或比赛调用证明。CI 可以注入明确的 fake port，但 fake provenance 必须标记为测试。

### 5.1 实例级 Provider 配置

- Provider 配置是实例级运行事实，不属于 Project、Thread、Session 或 Run。部署环境变量提供只读 baseline；本地工作台可安装一个已验证 override，供所有后续模型调用复用。
- 默认 preset 绑定赛题指定合格模型的官方服务与受治理参数；自定义 preset 只允许通过当前批准的标准兼容聊天接口。Adapter 负责传输映射，不把 provider 私有参数扩散到领域层。
- 保存配置前必须执行真实、最小连接探测。探测成功后才加密持久化并原子替换运行快照；已开始的调用继续使用其快照，新调用读取最新配置。
- 分块模型任务以一个父 ProducerExecution 为调用边界：父级开始时固定一个运行快照，所有有序子请求继承该快照并分别记录执行事实；下一独立调用或下一父级任务再读取最新配置。父级与子级的 provider、model 与 revision 必须一致，不得用启动前或结束后的配置代替实际 provenance。
- 父级聚合记录不得冒用任一子请求的 provider request id；子级分别保存其请求 id 与 provider 返回 model，父级仅在所有子级返回 model 完整且一致时保存该共识值。
- 配置状态只公开 preset、base URL、model、来源、验证时间与 API Key 尾号，不公开原始凭据、认证头或 provider 响应体。

## 6. CacheSelector 协作

模型调用发生可恢复失败时，只有 Workflow 的 CacheSelector 可以选择真实 CacheRecord。选择结果必须匹配 Contract、input hash、model/prompt identity 与 Evidence；模型 Pipeline 自身不得把 Fixture 或本地 seed 标记为 cached。
