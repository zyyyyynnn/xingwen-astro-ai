# Generated Contracts

本目录预留给 `scripts/export_schemas.py` 生成的 JSON Schema。

当前 CI 将契约导出到临时 Artifact 目录验证生成能力，不默认提交所有生成文件。需要提交生成产物时，必须同时提交 `manifest.json` 与 `json/*.schema.json`，并通过 `--check` 验证无漂移。

禁止手工修改生成文件。
