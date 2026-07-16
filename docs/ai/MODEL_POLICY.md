# Model Policy

| 元数据    | 值                             |
| --------- | ------------------------------ |
| Status    | Accepted                       |
| Authority | 模型调用准入、记录、降级与评测 |

本文规定模型调用进入科研产物前的准入、验证和记录要求。Prompt 生命周期见 [Prompt Versioning](PROMPT_VERSIONING.md)，Relation 准入见 [Reasoning Protocol](REASONING_PROTOCOL.md)，敏感信息与日志要求见 [Security](../../SECURITY.md)。

## 1. 调用路径

```text
Workflow Step
  -> Model Application Service
      -> Model Client
          -> structure validation
          -> evidence / domain validation
          -> ProducerExecution
          -> ArtifactVersion publication
```

前端、Router、Notebook 和临时脚本不得绕过后端模型调用边界。Router 不维护生产 Prompt，不把模型自然语言直接作为科研事实。

## 2. 输入要求

每次调用必须绑定：

- `run_id`、`step_key`；
- ResearchContract 或输入 ArtifactVersion；
- Prompt 名称、版本和 hash；
- 模型名称与关键参数；
- 结构化输入及 Schema 版本；
- 输入 Evidence 与版本；
- 来源和访问边界；
- 超时、重试和最大输出限制；
- 可计算的 input hash。

论文全文不可合法访问时，只能使用元数据、摘要和明确允许的开放文本片段。

## 3. 输出准入

模型响应进入业务存储前必须依次通过：

1. JSON 或受控结构解析；
2. Pydantic / JSON Schema 校验；
3. 枚举和字段级业务校验；
4. Evidence 引用存在性与归属校验；
5. Summary、Relation、Trace 或 Graph 的领域准入；
6. ProducerExecution、hash 与版本登记；
7. ArtifactVersion 发布事务。

任何一步失败都不得把原始自然语言作为“临时最终结果”返回前端。

## 4. Evidence 强度

- 数据值或转换：必须指向 SourceSnapshot 和字段/转换 Evidence。
- PaperSummary：核心 finding / limitation 必须指向论文 Evidence。
- Claim：至少一个属于输入版本的 Evidence。
- Accepted Relation：双方 Evidence、conditions 和 ReasoningTrace。
- ReasoningTrace：premise、比较条件、引用和结构化结论。
- GraphEdge：Evidence；跨文献边额外包含 accepted Relation 和 ReasoningTrace。
- 无证据模型推断只能作为 candidate / unsupported。

## 5. 参数与版本

模型、参数、结构化输出策略或工具调用策略发生实质变化时，需要：

- 新的 ProducerExecution 基线；
- 代表性 Benchmark 回归；
- Schema 通过率和 Evidence 覆盖率对比；
- 人工正确率和拒绝率对比；
- 必要时新增 Prompt 版本；
- 评估历史 CacheRecord 兼容性；
- 记录差异和回滚方式。

参数由统一调用层管理，不允许在多个业务文件中散落硬编码。

## 6. 失败与降级

允许：

- 对明确瞬态错误进行有限重试，并记录 StepAttempt；
- 使用经过验证的备用模型或配置；
- Live 可恢复失败后，由 CacheSelector 选择匹配的真实历史版本；
- 将无法核验的输出标记为 candidate / unverifiable 并转人工复核。

禁止：

- 删除 Evidence、Schema 或质量要求换取成功；
- 把无法解析的自然语言直接展示为事实；
- 使用 Fixture、seed 或 recorded response 冒充实时模型输出；
- 静默扩大输入来源、全文访问或工具权限；
- 覆盖失败 Attempt 或伪造成功状态。

## 7. ProducerExecution

每次模型或算法执行至少记录：

```text
run_id
step_key
producer_name / producer_version
model_provider / model_name
prompt_name / prompt_version / prompt_hash
parameters_hash
input_hash / output_hash
status / error_code
started_at / finished_at / latency_ms
usage
```

ResearchRun 管理工作流；ProducerExecution 记录具体模型或算法执行，两者不得混为同一对象。

## 8. 可审查性

ReasoningTrace 不是模型内部推理日志，只保存用户可审查的依据、条件和引用。不得记录或展示模型私有 chain-of-thought。

## 9. 评测门槛

进入主流程前至少验证：

- JSON / Schema 通过率；
- Evidence 绑定率；
- unsupported / 无证据输出拦截率；
- 代表性样例人工正确率；
- 超时、限流、重试和缓存提示；
- Prompt、模型、ProducerExecution 和输入版本可定位性。

Benchmark 版本、样例和评审结果必须可复现，不能只报告单次最佳输出。
