# Model Policy

本文规定 Qwen/百炼模型调用的准入、验证、记录和降级要求。

## 1. 调用路径

```text
Router
  -> application service
      -> workflow step
          -> Qwen Client
              -> schema validation
              -> evidence validation
              -> persistence
```

前端、Pipeline 临时脚本和图谱组件不得绕过后端 Qwen Client。

## 2. 输入要求

每次调用必须具备：

- `task_id`、`step_key`；
- Prompt 名称与版本；
- 模型名称与关键参数；
- 结构化输入；
- 输入证据 ID 与版本；
- 超时、重试与最大输出限制；
- 可计算的 input hash。

论文全文不可访问时，只能使用元数据、摘要和明确提供的开放文本片段。

## 3. 输出准入

模型响应进入业务存储前必须依次通过：

1. JSON 解析；
2. Pydantic/JSON Schema 校验；
3. 枚举和字段级业务校验；
4. Evidence 引用存在性校验；
5. 关系/图谱准入校验；
6. 内容 hash 与运行记录登记。

任何一步失败都不得把原始文本作为“临时最终结果”返回前端。

## 4. 证据强度

- 数据值：必须指向数据库查询或字段来源。
- 文献总结：核心 finding/limitation 必须指向论文证据。
- Claim：至少一个 Evidence。
- 最终 Relation：双方 Evidence + ReasoningTrace。
- GraphEdge：`evidence_ids`；跨文献边额外包含 `relation_id` 和 `reasoning_trace_id`。
- 无证据模型推断只能作为候选，且必须明确标注。

## 5. 模型参数

科研抽取与关系判断默认使用低随机性配置。参数由 Qwen Client/ExperimentRun 记录，不允许在多个业务文件中散落硬编码。

更换模型、温度、最大输出或结构化输出策略时，需要：

- 新的实验记录；
- 代表性样例回归；
- Schema 通过率对比；
- Evidence 覆盖率对比；
- 必要时新增 Prompt 版本。

## 6. 失败与降级

允许降级：

- 同一模型有限次数重试；
- 明确的备用模型；
- 来自真实运行且输入范围匹配的缓存；
- 转人工复核。

禁止降级：

- 删除 Evidence 要求换取成功；
- 把无法解析的自然语言直接展示为事实；
- 使用手写 seed 结果冒充实时模型输出；
- 静默扩大输入来源或抓取权限。

## 7. 日志与隐私

允许记录：

- model/prompt version；
- token/latency/status；
- hash、ID、错误分类；
- 截断后的诊断摘要。

禁止记录：

- API Key；
- 完整数据库连接串；
- 受限全文；
- 无限制完整 Prompt/Response；
- 用户未授权的敏感文本。

## 8. 评测门槛

进入 Demo 主链路前至少验证：

- JSON/Schema 通过率；
- Evidence 绑定率；
- 无证据关系拦截率；
- 代表性样例人工正确率；
- 超时、限流、缓存提示；
- Prompt/模型版本可定位。
