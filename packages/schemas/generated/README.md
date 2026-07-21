# Generated Contracts

本目录预留给 `scripts/export_schemas.py` 生成的 JSON Schema。

当前 CI 将契约导出到临时 Artifact 目录验证生成能力，不默认提交所有生成文件。需要提交生成产物时，必须同时提交 `manifest.json` 与 `json/*.schema.json`，并通过 `--check` 验证无漂移。

禁止手工修改生成文件。

当前已提交基线：

- `v1-phase0/`：冻结的 `/api/v1` Phase 0 DTO JSON Schema。
- `v2-core/`：#80 的七个核心资源 JSON Schema、manifest 与契约专用 OpenAPI 3.1；不表示运行路由已经挂载。
- `v2-security/`：#81 的 Session、CSRF/Problem Details 相关传输 Schema。
