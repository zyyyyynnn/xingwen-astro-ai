# Crossmatch Rule Assets

| 元数据    | 值                                                      |
| --------- | ------------------------------------------------------- |
| Status    | Accepted                                                |
| Authority | C-08 crossmatch rule asset versioning and hash coupling |

本目录保存 C-08 跨源对齐的版本化规则资产：

- `crossmatch-rules.v1.json`：RuleSet（identity/coordinate/capacity policy 版本、method priority、confidence、conflict policy 与各 manifest/policy 的 version/hash pin）。
- `entity-alias-catalog.v1.json`：版本化 `EntityAliasCatalog`（`catalog_id`、`version`、`content_hash`、`entries`、`source`、`maintainer`、`created_at`）。
- `source-policy.v1.json`：冻结 SourcePolicy（允许的 origin、source_mode 与 completion 语义）。

## Hash 与版本耦合

- 每个文件都带 canonical `content_hash`（`sort_keys=True`、`ensure_ascii=False`、紧凑分隔符的 SHA-256）。RuleSet 通过 version/hash pin 引用其他资产，冻结 Benchmark manifest 又 pin RuleSet 的 `rule_set_content_hash`。
- 任何语义内容变更必须同步：升版本、重算 canonical content hash、更新 RuleSet pin、更新 `crossmatch-benchmark.v1.json` 与相关测试。
- 纯 JSON 空白或键顺序变化不改变 canonical hash，因此不会导致加载失败；只有语义内容变化才会。

## 边界

- `entity-alias-catalog.v1.json` 当前仅为合成 benchmark fixture，用于确定性评审。
- 合成 alias 不是科研 gold truth；本 PR 不引入真实 curated catalog。
- 未经明确授权不创建新的跟踪 Issue。
