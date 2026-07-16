# Prompt Versioning

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 生产 Prompt 的文件结构、不可变版本、Registry 与发布流程 |

Prompt 文件统一放在 `packages/prompts`，由 `registry.json` 指定默认版本。模型调用准入见 [Model Policy](MODEL_POLICY.md)，跨文献关系准入见 [Reasoning Protocol](REASONING_PROTOCOL.md)。

## 1. 版本规则

使用不可变版本目录：

```text
<prompt_name>/v1.md
<prompt_name>/v2.md
```

以下变化必须新建版本：

- 输出 Schema 或字段变化；
- Evidence 要求变化；
- 关系类型或准入条件变化；
- 输入模板或来源范围变化；
- 安全边界和拒绝规则变化；
- 会显著改变结果的示例或指令变化。

已被 Live Run、ArtifactVersion、Benchmark 或 CacheRecord 引用的 Prompt 不得原地改写。仅修正不影响语义的排版或错字时，PR 必须说明并运行回归。

## 2. 文件头

每个 Prompt 使用 YAML front matter 记录：

- `name`；
- `version`；
- `output_model` / `output_models`；
- `evidence_required`；
- 适用的 input / output Schema version（需要时）。

业务代码以 registry + front matter 为依据加载，不使用复制粘贴字符串或“最新 Prompt”这类不可复现标识。

## 3. Registry

`registry.json` 负责：

- 列出已发布 Prompt 与文件路径；
- 指定各使用场景的默认版本；
- 标明 deprecated / disabled 状态；
- 保持稳定名称到版本文件的映射。

切换默认版本必须通过 PR 和 Benchmark；不得删除仍被历史运行引用的版本。

## 4. 运行记录

每次调用通过 ProducerExecution 记录：

```text
run_id
step_key
prompt_name
prompt_version
prompt_hash
model_name
parameters_hash
input_hash
output_hash
```

ArtifactVersion、CacheRecord 和材料 provenance 必须能回到具体 Prompt 版本和 hash。默认版本变化不能改变历史运行语义。

## 5. 发布流程

1. 新建版本文件并更新 front matter。
2. 更新 registry，但验证完成前不切换默认版本。
3. 使用固定 Benchmark 执行 JSON、Schema、Evidence 和领域准入回归。
4. 对比人工正确率、Evidence 覆盖率、拒绝率、延迟和成本变化。
5. Review 通过后切换默认版本。
6. 记录生效 Commit、适用范围和回滚版本。
7. 保留旧版本文件。

## 6. 禁止事项

- 在 Router、前端组件、Notebook 或临时脚本中维护生产 Prompt；
- 原地重写已用于正式运行或缓存的 Prompt；
- 要求模型伪造 DOI、引用、页码、观测值或实验结果；
- 仅凭自然语言输出绕过 Schema 或 Evidence；
- 把测试 Prompt、用户输入模板或第三方参考 Prompt 自动升级为生产版本；
- 未记录具体版本和 hash 就发布或缓存结果。

## 7. 验证

Prompt 变更至少验证：

- front matter 与 registry 一致；
- 文件路径、版本号和 hash 唯一；
- 目标输出 Schema 可校验；
- Evidence 与拒绝规则有效；
- 固定 Benchmark 无未解释退化；
- 旧版本文件和历史引用仍可解析；
- 生成物与文档无 stale diff。