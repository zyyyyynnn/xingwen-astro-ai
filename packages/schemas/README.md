# Shared Schemas

本目录承载前后端共享契约的生成产物与使用说明，不在前端、后端之间手工维护两套同名类型。

## Phase 0 单一事实来源

当前 authoring source 为：

```text
apps/api/src/app/schemas
```

这些 Pydantic v2 Model 必须与：

- `docs/architecture/API_CONTRACT.md`
- `docs/architecture/DATA_MODEL.md`

保持一致。

通过以下命令导出 JSON Schema：

```powershell
cd apps/api
uv run python ../../scripts/export_schemas.py --output ../../packages/schemas/generated
```

CI 使用临时输出目录验证所有 Schema 均可导出。后续需要提交生成产物时，使用：

```powershell
cd apps/api
uv run python ../../scripts/export_schemas.py
uv run python ../../scripts/export_schemas.py --check
```

## 消费规则

- 后端：直接引用 `app.schemas`，不得复制字段定义。
- 前端：Phase 1 起从 JSON Schema/OpenAPI 生成 TypeScript 类型，不手写重复接口。
- Pipeline：按 Pydantic Model 或其 JSON Schema 输出结构化结果。
- 任何接口字段变化都必须同步契约文档，并重新导出 Schema。
- 生成目录不得手工编辑；差异必须从 authoring source 修复。

## 迁移方向

当 TypeScript codegen 稳定后，可通过 ADR 决定是否把独立 IDL 提升为 authoring source。在此之前不搬迁现有 Pydantic 模型，避免为“共享目录”制造第二套事实来源。
