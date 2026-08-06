# Model Policy

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 模型调用准入、验证、记录、降级与评测规范 |

本文规定模型调用进入科研产物前的准入、验证与记录要求。Prompt 版本管理见 [Prompt Versioning](PROMPT_VERSIONING.md)，推理推导协议见 [Reasoning Protocol](REASONING_PROTOCOL.md)，安全与日志规范见 [Security](../../SECURITY.md)。

## 1. 模型调用路径

```text
Workflow Step -> Model Application Service -> Model Client -> Structure & Evidence Admission -> ProducerExecution -> ArtifactVersion Publisher
```

前端、Router 或脚本严禁绕过后端模型服务直接调用模型 API；模型输出的自然语言严禁不经校验直接充当科研事实。

## 2. 输入与输出准入

每次模型调用必须绑定 `run_id`、`step_key`、Prompt 名称/版本/哈希、模型名称与参数、输入 `input_hash`。

模型响应进入持久化前必须依次通过：
1. 受控 JSON 语法解析；
2. Pydantic / JSON Schema 结构校验；
3. 字段级与枚举业务校验；
4. Evidence 引用存在性与归属校验；
5. 对应领域（Summary / Claim / Relation / Trace）的准入门校验；
6. `ProducerExecution` 与哈希计算；
7. `ArtifactVersion` 原子发布事务。

任何环节失败均严禁将原始自然语言作为临时事实返回给客户端。

## 3. Evidence 强度规则

- **数据与属性**：必须绑定 `SourceSnapshot` 与对应字段/转换 Evidence。
- **PaperSummary**：核心 finding / limitation 必须逐项绑定文献 Evidence。
- **Claim**：必须包含至少一条绑定当前输入版本的 Evidence。
- **Accepted Relation**：必须包含双方 Evidence、明确条件与 `ReasoningTrace`。
- **GraphEdge**：必须包含 Evidence；跨文献边额外包含 Accepted Relation 与 `ReasoningTrace`。
- 无 Evidence 支撑的模型推测仅能标记为 `candidate` / `unsupported`。

## 4. 失败与降级

- **允许**：对明确的网络超时/限流执行有界自动重试，记录 `StepAttempt`；在 Live 失败后由 CacheSelector 挑选匹配的真实历史版本；将无法确证的输出转为 `unsupported` / `unverifiable`。
- **禁止**：删除 Evidence、 Schema 或质量要求换取成功；把无法解析的文本直接展示为事实；使用 Fixture 或手写响应伪造真实模型输出；覆盖失败 Attempt。

## 5. ProducerExecution

每次模型或算法执行必须记录包含 `run_id`、`step_key`、`producer_name/version`、`model_provider/name`、`prompt_name/version/hash`、`parameters_hash`、`input_hash`、`output_hash`、`status`、`latency_ms` 与 `token_usage` 的完整元数据。

`ReasoningTrace` 仅包含用户可审查的依据、条件与引用，绝对不记录或展示模型私有 chain-of-thought。
