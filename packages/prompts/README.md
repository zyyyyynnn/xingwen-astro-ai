# Prompt Registry Package

| 元数据    | 值                                        |
| --------- | ----------------------------------------- |
| Status    | Accepted                                  |
| Authority | `packages/prompts` 目录结构与本地使用方式 |

全局规则见 [Prompt Registry](../../docs/ai/PROMPT_REGISTRY.md)。本文件不重复模型准入、Evidence 或评测政策。

## 目录

```text
packages/prompts/
├─ README.md
├─ registry.json
├─ literature_claim/
│  └─ prompt.md
├─ paper_summary/
│  └─ prompt.md
└─ literature_reasoning/
   └─ prompt.md
```

## 使用规则

- 每个领域能力只登记一个当前 Prompt 定义；业务代码只按名称解析该定义。
- Registry 固定 path、语义版本、content hash 与输出模型；文件和 front matter 必须一致。
- Prompt Contract 变化时提升语义版本并更新当前文件，不保留旧文件、状态字段或兼容入口。
- `ProducerExecution` 记录当次执行的 Prompt 名称、版本和 hash，提供不可变执行证据。
- 包内文件不保存运行凭据、用户数据、受限全文或实际模型响应。
- Literature Relation Prompt 只输出 `LiteratureRelationExtractionOutput`；最终 Relation/ReasoningTrace 状态、hash 与发布资格仍由 Pipeline 决定。

## 变更验证

- Registry 与文件路径、名称、语义版本和 hash 一致；
- front matter 可解析，目标输出 Contract 一致；
- Prompt、Evidence、领域准入和相关 Benchmark 回归通过；
- 仓库不存在旧 Prompt 副本、生命周期状态或版本选择测试。
