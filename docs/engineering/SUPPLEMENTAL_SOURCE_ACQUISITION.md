# Supplemental Source Acquisition

| 元数据    | 值                                                                         |
| --------- | -------------------------------------------------------------------------- |
| Status    | Accepted                                                                   |
| Authority | C-07 补充来源查询、录制响应与独立 SourceSnapshot 运行规则                  |
| Issue     | #90                                                                        |
| Scope     | `exoplanet_host_star` 的 NASA Exoplanet Archive Planetary Systems metadata |

本文定义 C-07 的可执行边界。字段与来源表事实仍以
[C-01 Manifest](../../services/data_pipeline/manifests/README.md) 为唯一来源；
通用 SourceSnapshot 不变量仍由
[Data Versioning](../architecture/DATA_VERSIONING.md) 管理。本文不定义跨源匹配、
字段合并、单位转换、质量评分、ResearchRun 状态或 HTTP DTO。

本 Adapter 的输出由
[Cross-source Entity Alignment](CROSS_SOURCE_ENTITY_ALIGNMENT.md)
以纯确定性方式消费；本 Adapter 不导入或控制 crossmatch。

## 1. 来源选择与冻结边界

补充来源是 NASA Exoplanet Archive 的 `ps`（Planetary Systems）真实 TAP
表，table source id 为 `nasa_exoplanet_archive.ps`。C-02 主来源是独立的
`nasa_exoplanet_archive.toi` 表；两次查询分别产生 SourceSnapshot，不把缓存、
Fixture、seed 或 TOI 结果副本当作补充来源。

选择 `ps` 的依据是冻结契约：

- Case Manifest `1.0.1` 授权 provider source id
  `nasa_exoplanet_archive`；
- Field Manifest `1.0.1` 声明 `ps` 的 table source id、列、row key、引用列和
  provenance 列；
- `star.tic_id` 是 Case Manifest 的宿主恒星 identity field，并由 Field
  Manifest 映射到 `ps.tic_id`；
- Provider/table 映射复用既有 registry，不创建第二套 source registry，也不修改
  X-00 冻结包。

固定输入先归一化为排序且去重的 `TIC <positive integer>`。单次最多 100 个标识符，
数字部分最多 19 位；空白、大小写和调用方顺序不影响稳定 hash，非法或可注入值在发出
请求前拒绝。

`input_hash` 绑定 Manifest pins、identity field 和规范化输入；`query_hash` 进一步
绑定来源表、列裁决、运行时类型契约、约束和分页。两者均使用 canonical JSON
SHA-256。

| 冻结输入                         | 值                                                                                  |
| -------------------------------- | ----------------------------------------------------------------------------------- |
| Case Manifest version/hash       | `1.0.1` / `sha256:bb870d3c8b6b6c972cd8d7139b9cfcb672bb9ce75401109271aaf05a147819d3` |
| Field Manifest version/hash      | `1.0.1` / `sha256:c29b3ab32044f7e14b9d9fe618acf957373db33b4d1b4d8eb8ac4d83a8404d53` |
| Column adjudication version/hash | `1.0.0` / `sha256:b27b6fc8aab5d2ddeda2f21420650291567e09c26e969bb4eb89c54853d0766b` |
| Runtime schema contract          | `nasa_exoplanet_archive.ps.runtime_schema.2026-07-30` / `1.0.0`                     |
| X-00 baseline                    | `main@eb7e23f6d0c14555627c602c6e5a2b84210ba833`                                     |
| Query normalization / Adapter    | `1.1.0` / `1.1.0`                                                                   |

## 2. Provider 层、Adapter 层与职责

NASA TAP 的 provider 通用能力集中在
`services/data_pipeline/sources/nasa_tap.py`：

- HTTPS endpoint 与 redirect allowlist；
- 有界响应体、超时、状态分类、429 `Retry-After` 和指数退避；
- 安全响应头、request id、request hash 和 rate-limit metadata；
- 数据页 ETag 一致性检查；
- bounded completion 分类；
- SourceSnapshot 基础构建。

TOI 与 PS Adapter 复用同一 provider 层。来源 Adapter 仅保留本来源的 query renderer、
cursor、schema/row validator、分页编排和来源专用 provenance。安全、重试或版本语义发生
变化时不再维护两套实现。

## 3. 列契约与 Schema Drift

运行时首先验证 Field Manifest 引用的列裁决文件路径、文件 SHA-256、snapshot identity
和 table contract。C-01 裁决保留官方定义的 `raerr1`、`raerr2`、`decerr1`、
`decerr2`，同时记录这些列连续两次未出现在 live `TAP_SCHEMA`。C-07 不删除这些
Manifest 声明，而是将其记录为 `live_unavailable_columns`，只查询其余批准列。

实际查询列还绑定版本化运行时类型契约：

`services/data_pipeline/manifests/exoplanet_host_star/source-evidence/`
`nasa-exoplanet-archive/2026-07-30/ps-runtime-schema-contract.v1.json`

该契约为每个 queried column 固定 `string | integer | number` 类别。数据页请求前执行
`TAP_SCHEMA.columns` 预检，并逐列校验：

- 表名、列集合和唯一性；
- 所有 queried columns 的 datatype category；
- row key 和数据页字段集合；
- 页内及跨页 keyset 单调顺序。

任一列缺失、重复、类型漂移或数据页字段不一致均以
`NASA_PS_SCHEMA_DRIFT` 或对应的 stable invalid-response code 关闭；运行时不得根据单次
live 结果改写 Manifest 或类型契约。

## 4. 请求、分页与完成状态

查询按 Manifest row key `pl_name,pl_refname` 排序，使用有界 `TOP N` 和 keyset
cursor。`page_size <= 1000`、`max_pages <= 100`、`record_limit <= 100000`；默认最大
尝试 3 次，指数退避从 0.5 秒开始、上限 4 秒。第一页之后的请求失败分类为
`NASA_PS_PAGINATION_INTERRUPTED`，原始失败保留为 exception cause。

| 场景                            | failure class      | 是否重试 |
| ------------------------------- | ------------------ | -------- |
| timeout                         | `timeout`          | 有界重试 |
| 临时传输错误                    | `transport`        | 有界重试 |
| HTTP 429                        | `rate_limited`     | 有界重试 |
| HTTP 5xx                        | `upstream_server`  | 有界重试 |
| HTTP 4xx（429 除外）            | `upstream_client`  | 不重试   |
| 非法 JSON、字段、类型、排序漂移 | `invalid_response` | 不重试   |
| 数据页 ETag 不一致              | `invalid_response` | 不重试   |
| endpoint、origin 或来源等级违规 | `policy_violation` | 不重试   |

成功 Snapshot 明确记录：

- `completion_status=complete`：最后一页少于请求数，已观察到结果终点；
- `completion_status=truncated`：在满页状态下达到 `record_limit` 或 `max_pages`；
- `completion_status=unknown`：没有足够证据判断完整性；
- `continuation_cursor`：截断时保存最后一个 source-specific cursor。

成功的空数组是一页零记录的完整结果。满页达到边界时不得只写 `non_empty` 并暗示结果
完整；CLI 和导出同时暴露 completion status 与 continuation cursor。

## 5. SourceSnapshot、ETag 与 Schema 证据

每次成功查询生成 `source_id=nasa_exoplanet_archive.ps` 的独立
`SourceSnapshotRecord`。至少保存：

- canonical query、`input_hash`、`query_hash` 和规范化参数；
- endpoint、官方列文档和每次 request hash locator；
- `retrieved_at`、数据页 response hash、聚合 content hash；
- adapter、producer、retry、source policy 和 query normalization 版本；
- schema 状态、分页、cursor、完成状态、状态码、attempt、耗时和安全 request id；
- column adjudication 与 runtime schema contract pins；
- license note、`source_mode`、`data_level` 和录制 Fixture provenance。

`source_version_or_etag` 只接受数据页 representation 的真实且一致 ETag：

- 所有返回 ETag 的数据页必须一致，否则以
  `NASA_PS_SOURCE_VERSION_CHANGED` 失败；
- 上游未提供数据页 ETag 时，该字段为 `null`，状态为 `unavailable`；
- `TAP_SCHEMA` response hash 与 schema ETag 只保存在 `schema_preflight`，不得替代
  动态数据版本，也不得与数据页 ETag 拼接。

响应头采用 allowlist。`Authorization`、Cookie、Set-Cookie、API key、Session、
Token、credential 及其值不会进入 Snapshot、Fixture 或错误日志。

## 6. Live、Recorded、Fixture 与 Seed

| 实际来源             | `source_mode` | `data_level`        | 规则                      |
| -------------------- | ------------- | ------------------- | ------------------------- |
| 官方 endpoint 实时响应 | `live`        | `live_result`       | 唯一可标记 Live 的组合    |
| 版本化真实响应回放   | `fixture`     | `recorded_response` | 默认 CI smoke             |
| 合成测试样例         | `fixture`     | `fixture`           | 必须携带版本化 provenance |
| seed 输入或样例      | `fixture`     | `seed`              | 不得标记 Live             |

该 Adapter 不接受 `cached`。任何缓存集成都必须引用真实历史 Run、ArtifactVersion 和
SourceSnapshot，并由 CacheSelector 所属边界负责。

## 7. Recorded Fixture

受控响应位于
`services/data_pipeline/fixtures/exoplanet_host_star/nasa-ps-by-tic-first-page.recorded.v1.json`。
它在 `2026-07-30T05:56:13Z` 从官方 endpoint 录制，固定输入为
`TIC 219698776`，仅包含一页两条 metadata 记录。

Recorded schema 明确限制：

- `max_pages == 1`；
- `page_size == record_limit`；
- 记录数不得超过该单页上限；
- Fixture 保存 Manifest、列裁决和 runtime schema contract pins；
- `source_version_or_etag` 只能等于录制数据页 ETag；本次上游未返回数据页 ETag，因此为
  `null`；
- schema/page response hash 和整体 content hash 必须通过校验；
- Replay transport 只接受与 capture 完全相同的 schema query 和第一页 query。

Fixture 只证明录制时刻的一页响应，不表示完整 PS 结果集。录制的两条记录填满边界，
因此 replay 输出为 `completion_status=truncated`。

## 8. 运行与验证

默认 recorded 命令不访问公网：

```powershell
$env:PYTHONPATH = "apps/api/src;."
uv run --project apps/api python -m services.data_pipeline.supplemental_cli `
  --mode recorded `
  --output .artifacts/nasa-ps.recorded.json
```

有界 Live CLI 不需要密钥：

```powershell
$env:PYTHONPATH = "apps/api/src;."
uv run --project apps/api python -m services.data_pipeline.supplemental_cli `
  --mode live `
  --tic-id "TIC 219698776" `
  --page-size 2 `
  --max-pages 1 `
  --record-limit 2 `
  --timeout 30 `
  --output .artifacts/nasa-ps.live.json
```

普通 CI 使用 mock 和 recorded 响应。Live 测试只有显式设置环境变量时才访问 NASA：

```powershell
Set-Location apps/api
uv sync --frozen
uv run pytest tests/test_data_source_pipeline.py `
  tests/test_supplemental_source_pipeline.py

$env:XINGWEN_RUN_LIVE_SUPPLEMENTAL_SOURCE_TESTS = "1"
uv run pytest -m live tests/test_supplemental_source_pipeline.py
```

`XINGWEN_RUN_LIVE_SUPPLEMENTAL_SOURCE_TESTS` 只是显式联网开关，不是凭据。

## 9. 许可、限制与验收映射

NASA Exoplanet Archive metadata 可公开查询。产物必须保留 archive attribution，并遵循
官方 acknowledgement and citation guidance；Adapter 不重新许可上游内容。

PS 是动态表，同步 endpoint 不提供稳定 release id。Schema response hash 只是结构
证据，不代表全库版本；recorded 响应只证明录制时刻的内容。网络、限流和上游维护仍可能
使 opt-in Live smoke 失败。PS 与 TOI 虽是独立真实表和独立 SourceSnapshot，但属于
同一 NASA provider，符合冻结 Case SourcePolicy 对补充来源的约束。

输出只包含原始 PS 记录及其 provenance。如何把 TOI 与 PS 实体进行 exact、alias、
coordinate 或人工对齐属于 Issue #91，本文边界不提供任何匹配结论。

| 验收能力                                    | 代码或测试证据                                |
| ------------------------------------------- | --------------------------------------------- |
| 固定主案例补充来源真实或录制运行            | recorded CLI/test 与 opt-in Live smoke        |
| 稳定 query/input hash                       | 顺序、空白、重复值和有意义变更测试            |
| SourceSnapshot 可追溯来源、时间、参数和许可 | 分页 Snapshot、locator、版本证据和敏感头测试  |
| Fixture/seed 不标记 Live                    | origin/data-level 组合拒绝测试                |
| Schema drift 完整关闭                       | 非 row-key 数值列、integer 列和列集合漂移测试 |
| 有界结果不冒充完整集合                      | completion status 与 continuation cursor 测试 |
| 单元测试与 recorded/Live smoke              | `test_supplemental_source_pipeline.py`        |
