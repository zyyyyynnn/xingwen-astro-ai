# Data Source Acquisition

| 元数据 | 值 |
| --- | --- |
| Authority | 主数据源查询、原始记录、失败语义与 SourceSnapshot 运行规则 |
| Scope | `exoplanet_host_star` 的 NASA Exoplanet Archive TOI metadata |

本文定义主数据源 Adapter 的可执行边界。Case / Field Manifest 的字段事实仍由
[Manifest](../../services/data_pipeline/manifests/README.md) 管理，SourceSnapshot 的
通用不变量仍由 [Data Versioning](../architecture/DATA_VERSIONING.md) 管理，ResearchRun
状态只由 [Workflow Design](../architecture/WORKFLOW_DESIGN.md) 管理。

## 1. 冻结输入与任务边界

主数据源 Adapter 只读取冻结的 `exoplanet_host_star` Case / Field Manifest，不读取动态 `latest`，也不接受调用方传入另一套字段清单。运行前同时校验版本与内容 hash。

| 输入 | 固定值 |
| --- | --- |
| Case Manifest version | `2.0.0` |
| Case Manifest hash | `sha256:efbee5ec7d9e9e450a1b08685eb27e0a600f58faec5524d37dc05a9b1f28276c` |
| Field Manifest version | `2.0.0` |
| Field Manifest hash | `sha256:b0ce150bebbfa9549273ecbb5e26ed302f64b9925d768bb42f944554d011a86f` |
| Query normalization | `1.0.0` |
| NASA TAP Adapter | `1.0.0` |

本实现不会执行 crossmatch、字段合并、单位统一、质量评分、第二来源回退、缓存选择、ArtifactVersion 发布或 ResearchRun 推进。Fixture 和 seed 不能在 Live 失败时替代真实来源结果。

## 2. 主来源与查询规范

唯一主来源是 NASA Exoplanet Archive 的同步 TAP endpoint：`https://exoplanetarchive.ipac.caltech.edu/TAP/sync`。Adapter 只允许 HTTPS 和 `exoplanetarchive.ipac.caltech.edu`，跨 host redirect 会作为策略错误关闭。TOI 列定义引用官方 [TOI table documentation](https://exoplanetarchive.ipac.caltech.edu/docs/API_TOI_columns.html)，TAP 行为引用官方 [TAP guide](https://exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html)。

规范化查询的 selected columns 完全来自 Field Manifest 的 `nasa_exoplanet_archive.toi.approved_columns`。基础约束固定为 `tid is not null` 与 `toi is not null`，排序固定为 `tid,toi`。每页使用 `TOP N`，后续页使用 `(tid > cursor_tid or (tid = cursor_tid and toi > cursor_toi))`，因此请求数、单页大小、最大页数和总记录数都有上限。业务 row key 仍遵循 Manifest 的 `toi`；若跨页出现重复 TOI，Adapter 以 `NASA_TAP_DUPLICATE_ROW_KEY` 失败，不把同一候选体保存为两个不可变原始记录。

数据查询前执行一次 TAP_SCHEMA 预检。预检要求全部 approved columns 存在，`tid` 保持整数类型，`toi` 保持字符类型；缺列、重复列、游标类型变化、返回记录字段漂移或非稳定排序都按 schema/response drift 关闭，不根据单次 Live 结果修改 Manifest。

## 3. 原始记录与 SourceSnapshot

每条 `RawDataSourceRecord` 保存 table source id、Manifest row key、按 approved column 顺序构造的原始 payload 和稳定 SHA-256 content hash。主数据源 Adapter 不解释数值科学含义，不把 null 改成零，不执行单位转换，也不选择 canonical value。

成功 acquisition 生成一个 `SourceSnapshotRecord`。Snapshot 绑定规范化 query 与 query hash、抓取时间、原始记录和分页内容 hash、许可说明、Adapter 版本、endpoint、TAP_SCHEMA 请求/响应 hash、分页 request/response hash、状态码、attempt count、latency、游标、限流摘要及安全 request-id。响应只经过 header allowlist；Authorization、Cookie、API key、credential 与未批准的响应头不会进入 Snapshot。

NASA TOI TAP 实测响应未提供 ETag、独立 source version 或 request-id。对应字段保持 `null`，`source_version_or_etag_status` 和 `request_id_status` 显式记录 `unavailable`；部分页面提供时使用 `partially_available`。实现不会使用查询时间、随机 UUID 或本地版本伪造上游标识。NASA Exoplanet Archive 的 DOI 指南没有为 TOI 表列出独立 DOI，因此不得套用 Planetary Systems 或 PSCompPars DOI。

## 4. 来源等级与 Recorded Fixture

Live 请求必须使用 `source_mode=live` 与 `data_level=live_result`。版本化 replay 必须使用 `source_mode=fixture` 与 `data_level=recorded_response`，并在 Snapshot 中绑定 fixture id、schema version、scenario、recorded time、Case / Field Manifest 版本与 hash、fixture content hash 和 provenance note。`source_mode=cached` 不被此 Adapter 接受，因为该 Adapter 没有真实 origin Run、ArtifactVersion 和 CacheRecord。

Recorded Fixture 位于 `services/data_pipeline/fixtures/exoplanet_host_star/nasa-toi-first-page.recorded.json`。它来自 2026-07-22 对官方 TAP endpoint 的成功 metadata-only 小流量请求，只用于离线复现 Contract、分页和 provenance；回放结果不是当前 Live 数据，也不是历史 Run cache。Fixture payload 或 provenance 的任何变化都必须更新 schema/version 规则与 content hash。

## 5. 失败、重试与空结果

| 场景 | 分类 | 重试 |
| --- | --- | --- |
| timeout | `timeout` | 最多 3 次 |
| transport failure | `transport` | 最多 3 次 |
| HTTP 429 | `rate_limited` | 最多 3 次，优先遵循有界 `Retry-After` |
| HTTP 5xx | `upstream_server` | 最多 3 次 |
| HTTP 4xx（429 除外） | `upstream_client` | 不重试 |
| 非法 JSON、schema drift、非稳定排序 | `invalid_response` | 不重试 |
| endpoint/redirect/origin 等级违规 | `policy_violation` | 不重试 |

指数退避由固定 policy version 管理，并受最大等待上限约束。成功返回空数组表示零条真实结果，仍生成含零记录分页证据的 SourceSnapshot；失败请求不伪造成功 Snapshot。命令入口在失败时输出 failure class、code、attempt count、HTTP status 和 `research_run_advanced=false`。

## 6. 运行与验证

默认命令使用 Recorded Fixture，不访问公网。它只打印脱敏 summary；指定 `--output` 时才写出完整记录、分页和 Snapshot。

```powershell
$env:PYTHONPATH = "apps/api/src;."
uv run --project apps/api python -m services.data_pipeline `
  --mode recorded `
  --output .artifacts/nasa-toi.recorded.json
```

Live smoke 默认限制为一页两条记录，且不会创建或推进 ResearchRun。

```powershell
$env:PYTHONPATH = "apps/api/src;."
uv run --project apps/api python -m services.data_pipeline `
  --mode live `
  --page-size 2 `
  --max-pages 1 `
  --record-limit 2 `
  --timeout 30 `
  --output .artifacts/nasa-toi.live.json
```

普通 CI 运行 Fixture/mock 测试，不依赖 NASA 服务。显式 Live 测试需要调用者主动设置环境变量。

```powershell
Set-Location apps/api
uv sync --frozen
uv run pytest tests/test_data_source_pipeline.py

$env:XINGWEN_RUN_LIVE_DATA_SOURCE_TESTS = "1"
uv run pytest -m live tests/test_data_source_pipeline.py
```

## 7. 验收映射

| 验收能力 | 自动化或运行证据 |
| --- | --- |
| 冻结 Manifest 与稳定 query hash | Manifest/query tests |
| 有界 `TOP` 与 keyset pagination | query rendering 与 multi-page Adapter tests |
| 真实主来源与 TAP_SCHEMA 预检 | opt-in Live smoke 与 schema drift test |
| 原始记录、row key 和 content hash | paginated snapshot 与 duplicate row-key tests |
| timeout、429、5xx、4xx、非法 JSON | classified retry/error tests |
| 空结果成功 | empty-result test |
| ETag、request-id、限流与耗时口径 | safe reproducibility metadata test |
| Header/credential 脱敏 | allowlist 与 SourceSnapshot sensitive-key validation |
| Fixture 不冒充 Live/Cached | recorded replay 与 origin-masquerading tests |
| 不推进 ResearchRun | CLI output `research_run_advanced=false`，Pipeline 无 Workflow 依赖 |

该 Adapter 的结果是主来源 acquisition 边界和证据记录，不是已经完成的数据集。下游
数据能力必须在明确 Contract 下执行 crossmatch、字段归一、质量计算和发布集成。
