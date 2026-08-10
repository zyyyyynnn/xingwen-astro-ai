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

每次模型调用必须在 `ProducerExecution` 中记录 `prompt_name`、`prompt_version` 与 `prompt_hash`。`ArtifactVersion` 与 `CacheRecord` 只通过这些固定值引用当次执行输入，不读取动态别名。

## 4. Research Intent 到 Contract Planner

Research Intent 进入运行前必须经过 Contract Planner Prompt。Planner 的输入只包含 Intent、项目范围、允许来源、字段/质量约束和必要的已发布 ArtifactVersion 摘要；它不直接访问数据库、外部来源或页面状态，也不生成 Artifact。

输出必须先通过生成的 Contract/Manifest Schema 与领域规则校验，再形成可编辑 Draft；用户确认后才产生不可变 Contract。无法支持的字段、来源或研究范围必须返回结构化 refusal/review-required，不得猜测或静默删减。
