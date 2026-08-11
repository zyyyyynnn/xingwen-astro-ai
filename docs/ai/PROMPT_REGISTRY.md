# Prompt Registry

| 元数据    | 值                                                        |
| --------- | --------------------------------------------------------- |
| Authority | 生产 Prompt 的当前定义、Registry、内容固定与运行引用规范 |

本文定义生产 Prompt 的单一当前事实源。模型调用准入见 [Model Policy](MODEL_POLICY.md)，推导协议见 [Reasoning Protocol](REASONING_PROTOCOL.md)。

## 1. 当前定义

每个生产 Prompt 只保存在 `packages/prompts/<prompt_name>/prompt.md`，并只在 `packages/prompts/registry.json` 登记一次。仓库不保留旧 Prompt 文件、生命周期状态、默认版本选择器或兼容入口。

Prompt front matter 必须声明：

- `name`：领域能力标识；
- `version`：模型执行证据使用的语义版本；
- `output_model` / `output_models`：目标输出 Contract；
- `evidence_required`：是否强制绑定 Evidence；
- `input_schema_version` / `output_schema_version`：适用的技术 Schema 版本。

## 2. Registry

Registry 将领域能力名称直接映射到一个 Prompt 文件、语义版本、content hash 与输出模型。加载器必须：

- 拒绝未登记名称、重复 path/hash、越界路径、重复 JSON key 与未知字段；
- 以 UTF-8/LF 规范化正文后计算 SHA-256，并与登记值核对；
- 核对 front matter 的名称、版本与输出模型；
- 不接受调用方选择其他 Prompt 版本。

Prompt Contract 变化时直接更新当前定义、提升语义版本并同步回归测试。历史执行由已发布 `ProducerExecution` 中的 `prompt_name`、`prompt_version` 与 `prompt_hash` 保留，不通过仓库中的旧 Prompt 副本提供重放兼容。

## 3. 运行引用

每次模型调用必须在 `ProducerExecution` 中记录 `prompt_name`、`prompt_version` 与 `prompt_hash`。ArtifactVersion 通过 ProducerExecution 与输入版本固定当次执行身份，不读取动态别名。

## 4. Contract Planner

Contract Planner 拥有 Research Intent 到 ResearchContractDraft candidate 的规划职责。输入只包含 Intent、Project 范围、允许来源、字段与质量约束以及必要的已发布 ArtifactVersion 摘要；输出必须通过 ResearchContractInput Schema 与领域校验，且不能直接创建 Contract、Run 或 Artifact。

HTTP Draft authoring 只有在绑定真实 Planner 与 ModelExecutionPort 时才能声称模型规划已执行。没有该绑定时必须使用明确的结构化输入路径或拒绝模型规划请求，不得用模板结果伪造 Planner 执行。
