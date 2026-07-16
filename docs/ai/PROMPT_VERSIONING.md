# Prompt Versioning

Prompt 文件统一放在 `packages/prompts`，由 `registry.json` 指定默认版本。

## 1. 版本规则

使用不可变语义版本目录：

```text
<prompt_name>/v1.md
<prompt_name>/v2.md
```

以下变化必须新建版本：

- 输出 Schema 或字段变化；
- 证据要求变化；
- 关系类型解释变化；
- 输入模板变化；
- 安全边界和拒绝规则变化；
- 会显著改变结果的示例或指令变化。

仅修正不影响语义的错字可原位修改，但 PR 必须说明。

## 2. 文件头

每个 Prompt 使用 YAML front matter 记录：

- `name`
- `version`
- `output_model` / `output_models`
- `evidence_required`

业务代码以 registry + front matter 为依据加载，不使用复制粘贴字符串。

## 3. 运行记录

每次调用记录：

```text
prompt_name
prompt_version
prompt_hash
model_name
model_parameters
input_hash
output_hash
```

真实运行缓存必须保留这些字段，确保旧 Prompt 结果不会冒充当前版本实时结果。

## 4. 发布流程

1. 新建版本文件。
2. 使用固定样例集执行回归。
3. 对比 Schema 通过率、Evidence 覆盖率、人工正确率。
4. 更新 `registry.json` 的 current。
5. 同步相关 Issue、文档和缓存口径。
6. 保留旧版本文件。

## 5. 禁止事项

- 在 Router、前端组件或 Notebook 中维护生产 Prompt。
- 原地重写已用于正式缓存的 Prompt。
- Prompt 要求模型伪造 DOI、引用、页码或实验结果。
- 仅凭自然语言输出绕过 Schema。
- 使用“最新 Prompt”但不记录具体版本。
