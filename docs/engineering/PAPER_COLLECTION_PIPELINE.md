# PaperCollection and PaperSummary Pipeline

| 元数据    | 值                                                                        |
| --------- | ------------------------------------------------------------------------- |
| Status    | Accepted                                                                  |
| Authority | PaperCollection 获取、PaperSearchInput 与 PaperSummary Prompt/Schema/Evidence 准入 |

本文是论文 Pipeline 运行规则和操作方式的唯一完整事实源。领域实体不变量仍由
[Data Model](../architecture/DATA_MODEL.md) 负责，ArtifactVersion 与缓存规则由
[Data Versioning](../architecture/DATA_VERSIONING.md) 负责，Run 状态只由
[Workflow Design](../architecture/WORKFLOW_DESIGN.md) 负责。

## 1. Contract 输入与边界

生产检索只消费已确认 `ResearchContract.paper_search_scope` 映射出的 typed
`PaperSearchInput`。该输入至少固定 target query、keywords、year range、允许来源、
candidate/selection limits、排序策略与 Evidence/full-text scope。Query normalization
只有一个权威实现，Benchmark/Fixture 也必须先适配到同一 `PaperSearchInput`，不得在
Pipeline 之外维护第二套 normalizer。

Benchmark 文件 `services/paper_pipeline/benchmarks/exoplanet_host_star/paper-reasoning-benchmark.json`
是 fixture/benchmark adapter 的输入，不是生产检索的事实源；加载时同时校验：

| 输入                    | 固定值                                                                    |
| ----------------------- | ------------------------------------------------------------------------- |
| Benchmark schema        | `1.3.0`                                                                   |
| Benchmark version       | `1.3.0`                                                                   |
| Scientific payload hash | `sha256:35ccf88f92e2ed86603702dd1251ee43998ea2babb4184f2c9d46d00fc85afc4` |
| Content hash            | `sha256:54046b775299d0b97fc61f12466255e7818eab50471d506ea07137cb61956337` |

不读取动态 `latest`。任何版本或 hash 不一致都会在外部请求前失败。

Paper collection stage 只生成经过 `PaperCollection` Pydantic Schema 校验的内容。它不
创建或更新 ArtifactVersion、latest 指针、CacheRecord、ResearchRun、RunStep 或 RunEvent，
也不实现 PaperSummary、Claim、Relation、ReasoningTrace、Graph 或前端工作区。

## 2. 数据流与支持来源

```text
ResearchContract.paper_search_scope
-> typed PaperSearchInput
-> normalized source-independent query + Crossref parameters
-> Crossref metadata pages
-> SourceSnapshot + raw candidates
-> canonical candidates
-> duplicate groups + conflicts / uncertain matches
-> deterministic ranking + selection / exclusion reasons
-> ProducerExecution + metrics + stable hashes
-> validated PaperCollection content
-> ArtifactVersion publisher
-> typed detail and candidate pagination reads
```

本 Pipeline 的 Live Adapter 为 Crossref REST `/works` metadata API：

- 只请求 DOI、title、author、publication date、URL、resource 和 alternative id 等书目信息；
- 不请求或保存受限全文，不把 Crossref metadata link 解释为全文授权；
- 只访问 allowlist 中的 `https://api.crossref.org`，跨 host redirect 会被拒绝；
- 使用 offset/rows 分页，按 `PaperSearchInput.candidate_limit` 有界停止；
- 单请求 timeout 可配置，默认 15 秒；
- timeout、transport、HTTP 429 和 5xx 最多尝试 3 次，退避为 0.25、0.5 秒并受 2 秒上限约束，`Retry-After` 优先；
- 4xx（429 除外）、非法状态、策略违规和畸形 JSON/字段不可重试；
- 分页串行执行；有运行时 rate-limit header 时按 interval/limit 延迟，缺失 header 时使用保守 1 秒页间隔；
- HTML tag、控制字符和非 HTTP(S) URL 被净化；响应体、认证头、Cookie 和凭据不进入日志或公开内容。

错误分类固定为 `timeout | rate_limited | transport | upstream_server | upstream_client | invalid_response | policy_violation`。空 `items` 是成功的零候选结果，不是来源失败。来源失败生成 `failed` acquisition content、真实分类与重试计数，不回退到 Benchmark seed。

## 3. Query 规范化

`PaperSearchInput` 是检索边界的唯一输入类型。确认 Contract、Benchmark scenario
adapter 与任何 HTTP/Fixture Repository 都必须产生该类型；Pipeline 只在进入来源
Adapter 前规范化一次，并将 normalized query、query hash 与 source parameters 传给
所有来源 adapter。

规则版本为 `1.0.0`：

1. 文本先做 Unicode NFKC，再折叠空白、去除首尾空白并 `casefold`；
2. keywords 去重并排序，source ids 去重并排序；
3. 来源无关部分保存 normalized query、keywords、年份范围、分页、候选上限和排序策略；
4. Crossref 参数保存 `query.bibliographic`、日期 filter、`sort=relevance`、`order=desc` 和 allowlisted select 字段；
5. `query_hash` 覆盖规范化结果、规则版本、来源参数、年份、分页与排序，不覆盖原始大小写/空白或运行时间；
6. `query_id` 由 `query_hash` 确定性派生。

因此语义相同但大小写、Unicode 宽度或空白不同的输入得到相同 normalized result、query id 和 hash。原始 query 仍保留用于审计。

## 4. Candidate canonicalization

规则版本为 `1.0.0`：

- DOI 去除 `doi:`、`doi.org` / `dx.doi.org` 前缀，URL decode 后统一小写并清理尾部常见标点；
- arXiv 去除 `arXiv:`、abs/pdf URL、`.pdf` 和 `vN` 版本后缀并统一小写；
- DOI 存在时 URL 统一为 `https://doi.org/{doi}`；否则 arXiv 存在时统一为 `https://arxiv.org/abs/{id}`；普通 URL 只允许 HTTP(S)，去 fragment、凭据和 tracking 参数，并排序 query 参数；
- title 做 NFKC、casefold、常见 Unicode 标点/符号折叠和空白规范化；展示 title、作者顺序、年份和全部净化前书目字段仍保留；
- author 做 NFKC、casefold、标点和空白规范化，供冲突与 title/year 匹配使用；
- canonical paper id 按 DOI、arXiv id、title+year+first-author、source record 的优先级，对稳定 canonical JSON 做 SHA-256，格式为 `paper.<hex>`；
- raw candidate id 同样使用稳定 SHA-256 和确定性 occurrence index，不使用 Python `hash()` 或随机 ID。

## 5. 去重、冲突与不确定匹配

规则版本为 `1.0.0`，匹配顺序为：

1. normalized DOI 精确相等；
2. normalized arXiv id 精确相等；
3. normalized title + year 相等，并且首作者 surname 相等或 normalized author 集合有交集。

精确标识匹配会合并，即使年份、作者、title 或另一个标识冲突；所有原候选继续保留，冲突按字段、关联 candidate 和依据显式记录。title/year 相同但作者缺失或冲突时只生成 `potential_duplicates`，不得宣称确定重复。duplicate group id 覆盖排序后的全部 candidate ids 和规则版本，因此与来源返回顺序无关。

## 6. 排序与选择

规则版本为 `1.0.0`。relevance score 为以下确定性加权和并限制在 0–1：

- normalized keyword phrase 命中率：55%；
- normalized query token 与 title token 交集：25%；
- DOI 或 arXiv 可核验标识：10%；
- publication year 位于 query 年份范围：10%。

最终排序键依次为 inverse score、normalized title、year、canonical paper id、candidate id。每个 duplicate group 只有最高排名代表可入选；代表组超过 selection limit 时记录 `selection limit reached`，组内其他记录说明它重复于哪个更高排名 candidate。所有入选项有 `selection_reason`，所有排除项有 `exclusion_reason`。

## 7. 来源等级、Snapshot 与 hash

`source_mode` 只允许 Data Model 定义的 `fixture | live | cached`，与数据等级分别记录：

| source_mode | 允许的数据等级                                               | 约束                                                                    |
| ----------- | ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| `live`      | `live_result`                                                | 真实请求和抓取时间；Recorded response 不得标 Live                       |
| `cached`    | `real_run_cache`                                             | SourceSnapshot 必须记录 `origin_run_id` 与 `origin_artifact_version_id` |
| `fixture`   | `fixture`、`recorded_response`、`benchmark`、`manual_review` | 不能表述为真实 Live/Cached 结果                                         |

Seed 不是来源模式，也不作为检索候选输入；其用途仅限 benchmark、manual review 或 fixture，且不得作为 Live 失败回退。冻结 benchmark package 中的 `scientific_review` 是科研审核用途，不会自动映射成 Live/Cache 来源。

每个成功 source execution 产生完整 SourceSnapshot，包含 source/query/query hash、抓取时间、content hash、license note、非敏感 request metadata、分页 request/response hash 和运行时限流摘要。每个 candidate 同时保存 snapshot id、source id、source record id 以及 DOI/arXiv/URL 中可用的核验标识。失败 execution 没有伪造 Snapshot，但仍保存 query hash、分页策略、请求参数 hash、时间、重试和错误分类。

`input_hash` 覆盖固定 Benchmark reference、query hash 和所有规则版本。`output_hash` 覆盖规范化查询、来源 response/content hash、全部候选、分组、冲突、排序、选择、指标与 producer；抓取时间、执行时间和 latency 不进入 content hash，避免同一内容因 wall clock 漂移。完整时间仍保存在 content 中。ProducerExecution 的 input/output hash 与顶层一致。

## 8. PaperCollection 与读取投影边界

Pydantic 编写源是 `apps/api/src/app/schemas/paper_collection.py`。内容至少包含：

- 固定 benchmark fixture reference/version/hash（仅用于 fixture/benchmark provenance）；
- normalized Query、source parameters、pagination 和 query hash；
- acquisition status、SourceExecution、SourceSnapshot；
- raw/canonical candidates、duplicate groups、potential duplicates 和 conflicts；
- relevance、stable ranking key、selected、selection/exclusion reason；
- selected paper ids、全部规则版本；
- source failure、empty result、candidate recall 和 duplicate rate 指标；
- ProducerExecution、input hash 和 output hash。

Publisher 可以把已校验且符合质量策略的 content 原样放入 `kind=paper_collection` ArtifactVersion，并登记 content/input hash、producer 与 snapshot ids。读取投影不复制 Publisher，也不重新运行检索、canonicalization、去重或排序；它通过 ownership 边界重新校验冻结 content 和 provenance，提供 detail 与候选 cursor 分页。`acquisition_run.status=failed` 的诊断 content 不得发布为成功 ArtifactVersion；读取遗留或损坏记录时使用稳定 Problem Details 失败关闭。

## 9. PaperSummary Prompt Registry

生产 Prompt 只能通过 `packages/prompts/registry.json` 和 `packages/prompts/registry.py` 加载。Registry 只登记当前 `paper_summary` 定义及其 path、语义版本、content hash 与 output models。加载器按 UTF-8/LF 计算 SHA-256 并核对 front matter；调用方不能选择历史 Prompt，执行证据由 `ProducerExecution` 中固定的名称、版本和 hash 保存。

一次调用固定 Prompt name/version/hash、model name、parameters version/hash、PaperCollection ArtifactVersion id/schema/output hash、SourceSnapshot 版本和 Evidence 输入 hash。Prompt 不在 Router、组件或临时脚本维护。

## 10. PaperSummary Schema 与准入

`services/paper_pipeline/summary.py` 只接收 PaperCollection `selected_paper_ids` 中的论文。模型响应依次经过：

1. JSON 解析：失败返回 `failure_stage=json` 与 `paper_summary.json_invalid`；
2. `PaperSummaryModelOutput` 判别 Schema：所有核心字段必须显式存在，失败返回 `failure_stage=schema`；
3. Evidence 校验：逐项核对 paper/candidate/source/source record/SourceSnapshot；locator `source_url` 必须匹配原始候选 URL，`paper_metadata` 的 quote/value 必须等于对应 metadata 字段，`paper_text` quote 必须出现在有界可访问片段；
4. 生成 `PaperSummaryArtifactContent` 并复算 input/output hash。

finding/limitation 无 Evidence 时为 `unsupported`；Evidence id 未知、provenance 不匹配或源文本不可访问时为 `unverifiable`；quote/value 未出现在提供的可访问片段时为 `unsupported`。只有所有引用 Evidence 均 supported 的项才为 `supported`。`accessible_excerpt` 仅用于本次校验，不进入 Summary；原始模型响应只计算 hash，不保存长输出。Schema 拒绝、Evidence 状态和来源冲突均不会触发自动科研裁决。

SourceSnapshot 版本是冲突时的权威运行版本。若 caller 声明其他版本，Summary 记录 conflict id、claimed version、snapshot version 与 `source_snapshot_version_retained`，Evidence 仍固定到 Snapshot id/version/content hash。

## 11. Benchmark 评测

`services/paper_pipeline/summary_benchmark.py` 复用已批准 `1.3.0` benchmark package、`BenchmarkEvaluationInput` 与 `evaluate_benchmark` 指标 runner，不修改 Benchmark 科研内容，也不创建平行指标算法。调用 runner 时只消费 Schema/Evidence 指标，并把本次未评测的 Relation 指标保持为 `not_available`。报告固定 Prompt/model/parameter 版本、各 case input/model-response/output hash，并记录每项指标的分子、分母与结果：

- Schema 通过率：accepted Summary case / 全部 case；
- Evidence 覆盖率：supported findings + limitations / 全部 findings + limitations；
- unsupported 拦截率：显式期望拦截且未成为 supported 的核心项 / 全部期望拦截项；
- 人工审查样例：必须引用 benchmark package 中 `review_status=approved` 的 PaperSummary id。

Evidence 或 unsupported 指标分母为零时报告 `null`，与 `report_not_available` 空集规则一致，不用 `0.0` 冒充已计算结果。

评测函数不调用模型；同一版本化 case 输入产生相同 report input/output hash。模型执行、成本/延迟采集和生产 Benchmark 调度不属于该评测函数边界。

## 12. PaperSummary 与 Publisher/读取投影边界

`PaperSummaryArtifactContent` 直接作为 `ArtifactContent` 的 `kind=paper_summary` 判别分支，并通过 structured admission port；不生成第二套 Transport Schema。`PaperSummaryModelOutput` 明确标记为中间模型，通用 Publisher 会拒绝其绕过 Evidence admission，只有完整 `PaperSummaryArtifactContent` 可进入发布准入。该阶段不执行 ArtifactVersion 数据库事务、不推进 ResearchRun、不实现 HTTP/domain read、不实现 CacheSelector。下游 Publisher 必须登记 content/input hash、ProducerExecution、SourceSnapshot ids 与 Evidence ids，且不得把 rejected execution 发布成成功 ArtifactVersion。

## 13. 验证命令

普通 CI 使用 fixture/mock，不访问公网：

```powershell
Set-Location apps/api
uv sync --frozen
uv run pytest tests/test_paper_collection_pipeline.py tests/test_paper_summary_pipeline.py
uv run pytest
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas --check
```

显式真实 Benchmark Query smoke 从仓库根目录执行；只打印脱敏 summary，完整 metadata content 仅在指定 `--output` 时写入 `.artifacts`：

```powershell
uv run --project apps/api python -m services.paper_pipeline `
  --scenario search.tess_mission_and_catalogs `
  --page-size 25 `
  --selection-limit 10 `
  --output .artifacts/paper-collection.live.json
```

对应 pytest Live 标记默认跳过，显式启用方式为：

```powershell
$env:XINGWEN_RUN_LIVE_PAPER_TEST = "1"
Set-Location apps/api
uv run pytest -m live tests/test_paper_collection_pipeline.py
```

## 14. 验证映射

| #     | 验收项                     | 自动化证据                                                              |
| ----- | -------------------------- | ----------------------------------------------------------------------- |
| 1     | 固定 Query 真实来源        | `test_frozen_benchmark_query_runs_against_real_crossref`（opt-in Live） |
| 2     | Query 稳定                 | `test_query_normalization_and_hash_ignore_case_and_whitespace`          |
| 3–4   | 来源/分页可复现、分页合并  | `test_crossref_pagination_merges_pages_and_records_metadata`            |
| 5–7   | timeout、限流、有界重试    | timeout 与 rate-limit tests                                             |
| 8     | 不可重试错误               | `test_crossref_non_retryable_client_error_stops_immediately`            |
| 9     | 空结果                     | Crossref empty 与 Pipeline empty tests                                  |
| 10    | 畸形/缺失字段              | `test_crossref_malformed_response_is_classified`                        |
| 11–12 | DOI/arXiv 归一             | parameterized DOI/arXiv tests                                           |
| 13    | title/year 稳定分组        | `test_title_year_duplicate_group_is_stable_across_input_order`          |
| 14–15 | 作者/年份冲突保留          | exact identifier conflict test                                          |
| 16    | group id 稳定              | title/year input-order test                                             |
| 17    | 稳定排序/tie-breaker       | ranking test                                                            |
| 18–19 | selection/exclusion reason | ranking test 与 Schema validator                                        |
| 20    | Live 失败无 seed 回退      | `test_live_failure_records_truth_and_never_falls_back_to_seed`          |
| 21    | candidate 定位 Snapshot    | Pipeline provenance test                                                |
| 22    | Producer/rule versions     | Pipeline provenance test                                                |
| 23    | input/output hash 稳定     | Pipeline hash test 与 tamper test                                       |
| 24    | PaperCollection Schema     | JSON round-trip 与 tamper test                                          |
| 25–27 | 来源失败、召回、重复率     | failure/empty/provenance metrics tests                                  |
| 28    | 日志不泄露                 | logging、sanitization 与 sensitive metadata tests                       |
| 29    | 不推进 ResearchRun         | `test_pipeline_has_no_research_run_state_dependency`                    |
| 30    | 现有回归                   | `uv run pytest` 与仓库标准 CI                                           |

## 15. 已知限制

- PaperSummary admission 不负责抓取 abstract/PDF/全文，也不做表格/图像 OCR；Evidence 可访问片段必须由上游依法提供。
- PaperSummary admission 不实现跨文献 Relation/Graph、论文写作、ResearchRun 推进、读取投影或 ArtifactVersion 事务。
- 本 Pipeline 只集成 Crossref metadata Adapter；arXiv 与需要 token 的 NASA ADS 不在其范围。
- Crossref relevance 是上游排序输入，最终本地评分是可解释的词法基线，不是科研相关性人工结论。
- 只支持最多 100 个候选和 offset pagination；不抓取 abstract、PDF 或任意全文。
- Crossref 数据会更新；SourceSnapshot 固定本次结果，但不能保证未来同 query 返回相同 metadata。
- Cached 只定义可校验的消费边界；真实 CacheSelector、origin persistence 和发布由 B/Workflow 边界负责。
- Live smoke 依赖公网和 Crossref 运行状态，因此普通 CI 默认跳过，并且不得用 Fixture 结果替代 Live 结论。
