# Prompt Registry

Prompt 是受版本控制的科研产物，不允许散落在 Router、Pipeline 或临时脚本中。

## 目录约定

```text
packages/prompts/
├── registry.json
├── paper_summary/
│   └── v1.md
└── literature_reasoning/
    └── v1.md
```

## 规则

1. 已被真实运行或缓存引用的 Prompt 文件只读，不原地改写。
2. 修改语义、输出字段、证据要求或安全边界时新建版本。
3. `registry.json` 的 `current` 只表示默认版本，不删除旧版本。
4. 每次模型调用记录 `prompt_name`、`prompt_version`、`model_name`、输入/输出 hash。
5. Prompt 输出必须通过 Pydantic/JSON Schema 校验后才能持久化。
6. Prompt 不允许要求模型伪造引用、补写不可访问全文或隐藏不确定性。

详细规则见 `docs/ai/PROMPT_VERSIONING.md`。
