# Prompt Versioning

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 生产 Prompt 的文件结构、不可变版本、Registry 与引用规范 |

本文定义生产 Prompt 的版本管理、文件结构与 Registry 注册规则。模型调用准入见 [Model Policy](MODEL_POLICY.md)，推导协议见 [Reasoning Protocol](REASONING_PROTOCOL.md)。

## 1. 不可变版本规则

生产 Prompt 统一保存在 `packages/prompts/<prompt_name>/vN.md`。

- **创建新版本**：当输出 Schema、Evidence 要求、推理条件、输入模板或安全拒绝规则发生变化时，必须创建新的 `v(N+1).md` 版本文件。
- **不可变性**：已被历史 Run、`ArtifactVersion` 或 `CacheRecord` 引用的 Prompt 文件绝对禁止原地改写正文或覆盖原有文件。

## 2. Front Matter 规范

每个 Prompt Markdown 文件必须在顶部通过 YAML front matter 声明：
- `name`：Prompt 机器标识。
- `version`：版本号（如 `v1`）。
- `output_model` / `output_models`：适用模型。
- `evidence_required`：是否强制绑定 Evidence。
- `input_schema_version` / `output_schema_version`：调用的 Schema 版本。

## 3. Registry (registry.json)

`packages/prompts/registry.json` 是场景到 Prompt 版本的唯一映射注册中心：
- 映射场景名称到具体的 Prompt 版本文件。
- 标注当前默认版本、`deprecated` 或 `disabled` 状态。
- 严禁删除仍被历史版本引用的 Prompt 文件。

## 4. 运行引用

每次模型调用必须在 `ProducerExecution` 中记录 `prompt_name`、`prompt_version` 与 `prompt_hash` (对 Prompt 文件内容按 UTF-8/LF 归一化计算出的 SHA-256 哈希值)。`ArtifactVersion` 与 `CacheRecord` 仅通过这些字段显式引用 Prompt，不依赖全局默认版本的动态漂移。
