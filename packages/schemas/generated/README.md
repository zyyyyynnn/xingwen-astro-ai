# Generated Contracts

本目录预留给 `scripts/export_schemas.py` 生成的 JSON Schema。

CI 将契约导出到临时 Artifact 目录验证生成能力，不默认提交所有生成文件。需要提交生成产物时，必须同时提交 `manifest.json` 与 `json/*.schema.json`，并通过 `--check` 验证无漂移。

禁止手工修改生成文件。

本目录包含的基线：

- 既有 DTO JSON Schema 基线：由导出脚本生成并通过 manifest 固定，不按工作阶段命名其契约语义。
- `literature_claim/`：LiteratureClaim extraction、admission、publisher-ready candidate 与 Benchmark report 的领域 Pipeline JSON Schema；不是 HTTP DTO。
- `literature_relation/`：LiteratureRelation/ReasoningTrace extraction、admission、publisher-ready candidate 与 Benchmark report 的领域 Pipeline JSON Schema；不是 HTTP DTO。
- `graph/`：D-05 Versioned Evidence Graph build、admission、publisher-ready candidate、integrity 与 Benchmark 的领域 Pipeline JSON Schema；不是 HTTP DTO。
- `core/`：核心资源与 Artifact provenance read 投影的 JSON Schema、manifest 和契约 OpenAPI 3.1；路由挂载状态以 API Contract 为准。
- `security/`：Session、CSRF/Problem Details 相关传输 Schema。
