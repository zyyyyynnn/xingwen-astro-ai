# Competition Compliance

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 竞赛方向、模型资格、平台合规与提交证据规范 |

本文把 [赛题要求](../references/赛题要求.md) 中与产品、模型和提交材料有关的约束
转化为 Xingwen 的稳定产品规范。参考资料仍是需求输入，不是生产实现或事实源。

## 1. 固定参赛方向

产品固定参加 Track 2 / Direction 1 / A：科学数据查询、解析与整合。作品叙事和
验收必须围绕一个可复核的科学数据主案例，不能用通用聊天、通用 OCR 或泛化
Agent 能力替代科学纵向链。

在唯一产品主链中，Run 承载的科研处理子链固定为：

```text
confirmed Contract / data requirements
→ multi-source acquisition
→ parsing
→ cleaning
→ alignment
→ annotation
→ structured output
→ Evidence / provenance
→ feedback / revision
```

主链必须保留来源、版本、哈希、Evidence locator 和失败语义；解析得到的候选值
不能绕过字段准入、单位、质量、Evidence 或 Publisher 边界直接成为科研事实。

## 2. 合格模型与调用路径

参赛主案例的合格模型必须是 Qwen，并通过 Alibaba Cloud Model Studio / Bailian
或比赛官网明确推荐的工具调用。模型调用必须沿用：

```text
ResearchRun Step
→ ModelExecutionPort
→ qualifying Qwen adapter
→ typed Schema / Evidence admission
→ ProducerExecution
→ Publisher
```

Qwen 适配器是薄边界：只负责 provider protocol、鉴权配置、超时/限流、结构化
响应与安全元数据映射，不在 Adapter 中实现科研规则、字段事实或第二套 Prompt
Registry。禁止使用浮动的 `latest` 作为提交证据。

每次合格调用必须能够复核：

- provider 与官方接入路径；
- model name、版本或 revision；
- Prompt name/version/hash 与输入 Contract/hash；
- 参数、时间、运行环境、request/call proof、响应/output hash；
- Schema/Evidence admission、ProducerExecution 与最终 ArtifactVersion；
- 失败、拒绝、partial 或 unsupported 的真实结果。

密钥、原始认证头、原始响应全文和模型私有 chain-of-thought 不得进入材料、日志或
公开 Artifact。截图、录屏和 manifest 只能展示脱敏后的调用证明与科研 Evidence。

## 3. 基准与非合格模型

DeepSeek、Gemini 或其他模型可以作为 benchmark、消融、风险对照或参考材料，但
不能作为本方向合格主模型，也不能把其结果包装为 Qwen 合规调用。每个对照结果
必须标注 provider、model、版本、输入/输出 hash、数据等级和“non-qualifying
benchmark/reference”。没有相同 Contract、Evidence 与评测条件的数字不得横向
宣传为能力结论。

## 4. 证据与发布门

作品材料至少展示一条纵向闭环：

```text
Research Intent
→ Draft
→ confirmed Contract
→ ResearchRun with qualifying Qwen execution
→ scientific ArtifactVersion
→ Evidence / SourceSnapshot
→ review
→ feedback / revision or export
```

Fixture、Recorded response、Benchmark、Cached 与 Live 必须分栏标识。只有真实
Run、真实模型调用和可定位的版本/Evidence 才能作为能力证明；Fixture 或 benchmark
只能证明契约、确定性规则和回归覆盖。

## 5. 提交检查

提交前的 manifest 必须包含主案例、赛道声明、模型资格证明、调用与版本证据、
许可说明、运行环境、数据来源、脱敏说明、失败/降级示例和复现入口。任何无法
复核 provider/model/version/call proof 或无法回到 Evidence/provenance 的结论，
必须降级为未证实，不得写入完成性宣传。
