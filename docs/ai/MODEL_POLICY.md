# Model Policy

| 元数据 | 值 |
| --- | --- |
| Authority | 模型输出准入、执行记录、Evidence 与失败语义 |

模型与比赛资格由 [Competition Compliance](../product/COMPETITION_COMPLIANCE.md) 约束；Prompt identity 由 [Prompt Registry](PROMPT_REGISTRY.md) 管理。本文定义模型执行边界、候选输出准入与 provenance 规则。

## 1. 模型输出不是发布事实

模型输出必须先解析为对应的 Pydantic output model，再通过领域、Evidence、质量与 hash 准入。原始自由文本、解析失败内容或缺少 Evidence 的结论不得成为 ArtifactVersion。

当前使用模型候选的文献 Pipeline 包括 PaperSummary、LiteratureClaim 与 LiteratureRelation。每条 Pipeline 独立验证输入 ArtifactVersion、Prompt identity、输出 Schema、Evidence locator、状态计数与 canonical output hash。

## 2. Pre-run ModelExecutionRecord 与 ProducerExecution

Research assistant 的分析发生在 Run 之前，必须使用独立的 `ModelExecutionRecord`。它记录 provider、固定 model 与 revision、Prompt name/version/hash、安全规范化后的 Prompt/input/output/parameters snapshot 及其 hash、状态、token usage、latency、provider request id、error code 与时间边界。它不等同于 Run 内 Pipeline 的 ProducerExecution，也不能替代后者。

Run 内模型 Pipeline 使用 ProducerExecution 保存：

- `producer_type=model`、producer/model identity；
- `prompt_name`、`prompt_version`、`prompt_hash`；
- `parameters_hash`、`input_hash`、`output_hash`；
- 状态、错误码、token usage 与 latency。

Run 内 bounded Function Calling 也必须使用同一 ProducerExecution 事实源，
不建立第二 tool-call ledger。Worker 在 provider 调用前以当前
StepAttempt、lease generation 与稳定 idempotency key 创建 `running` 记录，并固定：

- 当次唯一授权 tool name、可用的 ScientificSkill ID 与由精确 tool schema/
  skill revision 计算的 registry revision hash；
- model/prompt identity、安全 parameters hash 与只保存 hash 的 Contract-scoped input；
- 成功时的 provider request ID、tool call ID、已校验 arguments hash、
  model result hash、token、latency 与已校验的公开分析投影；
- provider 失败或 tool/arguments 校验拒绝时，失败前已获得的安全 result
  hash、error hash、request ID、token 与 latency；校验拒绝若且仅若返回一个
  非空、有界 call identity，还必须保存 tool call ID 与 rejected arguments hash。
  原始 arguments 不进入 ProducerExecution 或 error hash。

幂等 replay 必须返回同一 ProducerExecution；只有具备完整成功闭包的终态
记录才能恢复公开 decision，`running`、`failed` 或 `rejected` 记录不得
触发重复 provider 调用或伪造成功。持久化内容不包含完整 Contract、原始
provider body、凭据或私有 chain-of-thought；唯一允许的文本结果是通过长度、
字段与语言校验的用户可见 `public_analysis`。

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

## 6. CacheSelector 协作

模型调用发生可恢复失败时，只有 Workflow 的 CacheSelector 可以选择真实 CacheRecord。选择结果必须匹配 Contract、input hash、model/prompt identity 与 Evidence；模型 Pipeline 自身不得把 Fixture 或本地 seed 标记为 cached。
