# Prompt Registry Package

| 元数据    | 值                                        |
| --------- | ----------------------------------------- |
| Status    | Accepted                                  |
| Authority | `packages/prompts` 目录结构与本地使用方式 |

全局 Prompt 生命周期、版本和发布规则见 [Prompt Versioning](../../docs/ai/PROMPT_VERSIONING.md)。本文件不重复模型准入、Evidence 或评测政策。

## 目录

```text
packages/prompts/
├─ README.md
├─ registry.json
├─ literature_claim/
│  └─ v1.md
├─ paper_summary/
│  ├─ v1.md
│  └─ v2.md
└─ literature_reasoning/
   └─ v1.md
```

## 使用规则

- 业务代码通过 registry 选择 Prompt；公共加载器由对应实现 Issue 交付后才能在生产中使用。
- 文件名使用稳定版本 `vN.md`，不创建 `latest.md`。
- 已被 Run、ArtifactVersion、Benchmark 或 CacheRecord 引用的版本不原地改写。
- `registry.json` 的默认版本变化必须通过 PR 和回归验证。
- 新 Prompt 或新版本包含完整 front matter，并与目标输出 Schema 对齐。
- 包内文件不保存运行凭据、用户数据、受限全文或实际模型响应。

## 变更验证

- registry 与文件路径、名称和版本一致；
- front matter 可解析；
- Prompt hash 稳定且唯一；
- 目标 JSON/Schema、Evidence 和领域准入测试通过；
- 旧版本仍可加载；
- 相关 Benchmark 和生成物无未解释漂移。
