# Supplemental Source Acquisition

| 元数据 | 值 |
| --- | --- |
| Status | Implemented |
| Authority | C-07 补充来源查询、录制响应与独立 SourceSnapshot 运行规则 |
| Issue | #90 |
| Scope | `exoplanet_host_star` 的 NASA Exoplanet Archive Planetary Systems metadata |

本文定义 C-07 的可执行边界。字段与来源表事实仍以
[C-01 Manifest](../../services/data_pipeline/manifests/README.md) 为唯一来源；
通用 SourceSnapshot 不变量仍由
[Data Versioning](../architecture/DATA_VERSIONING.md) 管理。本文不定义跨源匹配、
字段合并、单位转换、质量评分、ResearchRun 状态或 HTTP DTO。

## 1. 来源选择与冻结边界

补充来源是 NASA Exoplanet Archive 的 `ps`（Planetary Systems）真实 TAP
表，table source id 为 `nasa_exoplanet_archive.ps`。C-02 主来源是独立的
`nasa_exoplanet_archive.toi` 表；两次查询分别产生 SourceSnapshot，不把缓存、
Fixture、seed 或 TOI 结果副本当作补充来源。

选择 `ps` 的依据是冻结契约：

- Case Manifest `1.0.1` 只授权 provider source id
  `nasa_exoplanet_archive`；
- Field Manifest `1.0.1` 已声明 `ps` 的 table source id、列、row key、引用列和
  provenance 列；
- `star.tic_id` 是 Case Manifest 的宿主恒星 identity field，并已由 Field
  Manifest 映射到 `ps.tic_id`；
- 因此实现复用既有 provider/table 映射，不创建第二套 source registry，也不修改
  X-00 冻结包。

固定输入为规范化后的 TIC 标识符集合。空白、大小写、重复值和调用方顺序先归一化为
排序且去重的 `TIC <positive integer>`；单次最多 100 个标识符，数字部分最多
19 位，非法或可注入的值在发出请求前拒绝。
`input_hash` 绑定 Manifest pins、identity field 和规范化输入；`query_hash` 进一步
绑定来源表、列契约、约束和分页。两者都复用 canonical JSON SHA-256。

| 冻结输入 | 值 |
| --- | --- |
| Case Manifest version/hash | `1.0.1` / `sha256:bb870d3c8b6b6c972cd8d7139b9cfcb672bb9ce75401109271aaf05a147819d3` |
| Field Manifest version/hash | `1.0.1` / `sha256:c29b3ab32044f7e14b9d9fe618acf957373db33b4d1b4d8eb8ac4d83a8404d53` |
| Column adjudication version/hash | `1.0.0` / `sha256:b27b6fc8aab5d2ddeda2f21420650291567e09c26e969bb4eb89c54853d0766b` |
| X-00 baseline | `main@eb7e23f6d0c14555627c602c6e5a2b84210ba833` |
| Query normalization / Adapter | `1.0.0` / `1.0.0` |

## 2. 列契约与 live metadata gap

运行时先校验 Field Manifest 引用的列裁决文件路径、文件 SHA-256、snapshot
identity 和 table contract。查询列由该版本化证据派生，不另写一份字段清单。

C-01 裁决保留官方定义的 `raerr1`、`raerr2`、`decerr1`、`decerr2`，同时记录
这些列连续两次未出现在 live `TAP_SCHEMA`。NASA 当前也会拒绝直接选择这些列。
C-07 不删除这些 Manifest 声明，而是将它们记录为 `live_unavailable_columns`，
只对其余已批准列执行 live 查询。规范化 query 和 SourceSnapshot 同时保存：

- 完整 `declared_columns`；
- 裁决 snapshot id、version 和 content hash；
- `live_unavailable_columns`；
- 实际 `queried_columns`。

数据页请求前执行 `TAP_SCHEMA.columns` 预检。实际可查询列缺失、重复、类型漂移，
或返回记录字段不一致时，以 `NASA_PS_SCHEMA_DRIFT` 或相应 invalid-response
错误关闭，不根据单次 live 结果改写 Manifest。

## 3. 请求、分页与错误语义

Adapter 使用官方同步 TAP endpoint：
`https://exoplanetarchive.ipac.caltech.edu/TAP/sync`。传输层只允许 HTTPS 和
`exoplanetarchive.ipac.caltech.edu`，跨 host redirect 作为 policy violation
拒绝。请求不发送认证信息。

查询按 Manifest row key `pl_name,pl_refname` 排序，并使用有界 `TOP N` 和 keyset
cursor。`page_size <= 1000`、`max_pages <= 100`、`record_limit <= 100000`；
默认最大尝试 3 次，指数退避从 0.5 秒开始、上限 4 秒，429 优先采用有界
`Retry-After`。第一页之后的失败显式分类为
`NASA_PS_PAGINATION_INTERRUPTED`，原始失败保留为 exception cause。

| 场景 | failure class | 是否重试 |
| --- | --- | --- |
| timeout | `timeout` | 有界重试 |
| 临时传输错误 | `transport` | 有界重试 |
| HTTP 429 | `rate_limited` | 有界重试 |
| HTTP 5xx | `upstream_server` | 有界重试 |
| HTTP 4xx（429 除外） | `upstream_client` | 不重试 |
| 非法 JSON、字段或排序漂移 | `invalid_response` | 不重试 |
| endpoint、origin 或来源等级违规 | `policy_violation` | 不重试 |

成功的空数组是明确的零结果：保留一页零记录证据，Snapshot
`result_status=empty`。失败请求不伪造成功 Snapshot。

## 4. SourceSnapshot 与敏感信息

每次成功查询生成 `source_id=nasa_exoplanet_archive.ps` 的独立
`SourceSnapshotRecord`，至少保存：

- canonical query、`input_hash`、`query_hash` 和规范化参数；
- endpoint、官方列文档和每次 request hash locator；
- `retrieved_at`、数据页 response hash、聚合 content hash；
- ETag；上游未提供 ETag 时使用 `tap-schema:<response hash>` 作为等效版本证据；
- adapter、producer、retry、source policy 和 query normalization 版本；
- schema 状态、分页、cursor、状态码、attempt、耗时和安全 request id；
- license note、`source_mode`、`data_level` 和录制 Fixture provenance。

响应头采用 allowlist。`Authorization`、Cookie、Set-Cookie、API key、Session、
Token、credential 及其值不会进入 Snapshot、Fixture 或错误日志。

## 5. Live、Recorded、Fixture 与 Seed

| 实际来源 | `source_mode` | `data_level` | 规则 |
| --- | --- | --- | --- |
| 官方 endpoint 当前响应 | `live` | `live_result` | 唯一可标记 Live 的组合 |
| 版本化真实响应回放 | `fixture` | `recorded_response` | 默认 CI smoke |
| 合成测试样例 | `fixture` | `fixture` | 必须携带版本化 provenance |
| seed 输入或样例 | `fixture` | `seed` | 不得标记 Live |

该 Adapter 不接受 `cached`。未来缓存只有在引用真实历史 Run、
ArtifactVersion 和 SourceSnapshot 时才能接入；C-07 不实现该能力。

## 6. Recorded Fixture

受控响应位于
`services/data_pipeline/fixtures/exoplanet_host_star/nasa-ps-by-tic-first-page.recorded.v1.json`。
它在 `2026-07-30T05:56:13Z` 从官方 endpoint 录制，仅包含一页两条 metadata
记录；固定输入 `TIC 219698776` 同时存在于 TOI 与 PS 表，可作为 #91 的原始输入，
但 C-07 不据此生成匹配结论。Fixture 保存来源、文档、时间、Manifest/裁决 pins、输入、分页、schema/page
response hash、等效来源版本、license、provenance 和整体 content hash。

更新流程：

1. 先运行下一节的有界 Live CLI 和 Live smoke，保存输出并确认官方列文档与
   `TAP_SCHEMA`；
2. 只把相同固定输入的一页最小响应更新到 Fixture，同时更新 `recorded_at`、
   response hashes、来源版本证据和 provenance note；
3. 若结构变化，提升 Fixture schema/version；不得原地伪装为旧响应；
4. 使用 `compute_recorded_ps_fixture_hash` 重算 content hash；
5. 运行 recorded smoke、篡改检测、schema drift 和完整后端测试。

录制文件不得包含认证头或私有数据。响应变大时继续保持固定的一页小样本，不提交全库
导出。

## 7. 运行与验证

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
uv run pytest tests/test_supplemental_source_pipeline.py

$env:XINGWEN_RUN_LIVE_SUPPLEMENTAL_SOURCE_TESTS = "1"
uv run pytest -m live tests/test_supplemental_source_pipeline.py
```

`XINGWEN_RUN_LIVE_SUPPLEMENTAL_SOURCE_TESTS` 只是显式联网开关，不是凭据。

## 8. 许可与已知限制

NASA Exoplanet Archive metadata 可公开查询。产物必须保留 archive attribution，
并遵循官方 [acknowledgement and citation guidance](https://exoplanetarchive.ipac.caltech.edu/docs/acknowledge.html)；
Adapter 不重新许可上游内容。

PS 是动态表，当前同步 endpoint 未提供独立 release id 或稳定 ETag，因此
`TAP_SCHEMA` 响应 hash 只是本次结构证据，不代表全库版本。Live 结果可能随上游更新；
recorded 响应只证明录制时刻的内容。网络、限流和上游维护仍可能使 opt-in Live smoke
失败。PS 与 TOI 虽是独立真实表和独立 SourceSnapshot，但属于同一 NASA provider，
这是被冻结 Case SourcePolicy 允许的最小 C-07 实现。

输出只包含原始 PS 记录及其 provenance。如何把 TOI 与 PS 实体进行 exact、alias、
coordinate 或人工对齐属于 Issue #91，本实现不提供任何匹配结论。

## 9. Issue #90 验收映射

| 验收能力 | 代码或测试证据 |
| --- | --- |
| 固定主案例补充来源真实或录制运行 | recorded CLI/test 与 opt-in Live smoke |
| 稳定 query/input hash | 顺序、空白、重复值和有意义变更测试 |
| SourceSnapshot 可追溯来源、时间、参数和许可 | 分页 Snapshot、locator、版本证据和敏感头测试 |
| Fixture/seed 不标记 Live | origin/data-level 组合拒绝测试 |
| 单元测试与 recorded/Live smoke | `test_supplemental_source_pipeline.py` |
