# Contributing

## 1. 开发流程

1. 从 `main` 拉取最新代码。
2. 从 Issue 新建 feature 分支。
3. 完成开发、自测和必要文档更新。
4. 提交 Pull Request。
5. 至少 1 人 Review。
6. Squash merge 后删除分支。

## 2. 分支命名

```text
feat/a-task-timeline
feat/b-qwen-client
feat/c-data-cleaning
feat/d-graph-json
docs/project-foundation-audit
fix/api-task-status
```

## 3. Commit 格式

```text
feat: add task timeline component
fix: handle qwen timeout
docs: update api contract
chore: initialize backend structure
```

## 4. PR 前检查

- 是否关联 Issue。
- 是否说明改动范围和验证方式。
- 是否更新相关文档。
- 是否改动 API 或数据结构。
- 是否需要前后端联调。
- 是否涉及密钥、模型调用、外部数据源或公网 Demo。

## 5. 文档同步

| 改动 | 同步文档 |
| --- | --- |
| 接口 | `docs/architecture/API_CONTRACT.md` |
| 数据结构 | `docs/architecture/DATA_MODEL.md` |
| 模块边界 | `DESIGN.md`, `docs/architecture/MODULES.md` |
| MVP 范围 | `PRD.md`, `docs/product/ACCEPTANCE.md` |
| 部署 | `DEPLOYMENT.md`, `.env.example` |
| 风险 | `docs/quality/RISK_REGISTER.md` |

## 6. 合并标准

PR 同时满足以下条件才可合并：

- 主链路或任务目标明确。
- 验证方式可复现。
- 文档没有明显过期。
- 未引入密钥泄露风险。
- 不宣传未实现能力。
