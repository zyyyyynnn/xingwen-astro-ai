# PaperCollection and PaperSummary Pipeline

| 元数据 | 值 |
| --- | --- |
| Authority | PaperCollection benchmark runner、可复用检索组件与 PaperSummary Prompt/Schema/Evidence 准入 |

本文定义当前论文 Pipeline 的实际运行边界。领域实体由 [Data Model](../architecture/DATA_MODEL.md) 定义，ArtifactVersion 与缓存规则由 [Data Versioning](../architecture/DATA_VERSIONING.md) 定义，ResearchRun 状态只由 [Workflow Design](../architecture/WORKFLOW_DESIGN.md) 负责。

## 1. PaperCollection 架构与入口

文献检索流水线提供两个明确隔离的入口，共享底层规范化、跨源适配、去重排序与 Schema 校验核心：

1. **生产 Contract-driven 入口**（`LivePaperCollectionRunner`）：
   - 唯一输入：由 confirmed `ResearchContract` 经单一 mapper（`build_paper_search_input`）生成的不可变 typed `PaperSearchInput`；
   - 生产执行绑定 `PaperSearchInput.input_hash`，不携带 `benchmark` 引用；
   - 检索真实公开书目元数据，实时失败（`SourceFailure`）直接记录失败，绝不回退至 Fixture 或种子数据。

2. **基准 Benchmark 入口**（`PaperCollectionBenchmarkRunner`）：
   - 专用于基准场景评估（benchmark-only），输入为固定 benchmark machine asset：
     `services/paper_pipeline/benchmarks/exoplanet_host_star/paper-reasoning-benchmark.json`
   - 加载时固定并验证其 technical identity、scientific payload hash 与 content hash；
   - 基准执行绑定 `benchmark` 引用，不携带 `search_input`；
   - `scenario_id` 不用于生产 ResearchContract。

两者互斥，生产与基准输入通过同一底层 canonical query normalizer 保证语义一致性。

## 2. 数据流

### 生产 Contract-driven 数据流
```text
confirmed ResearchContract
-> build_paper_search_input (unique mapper)
-> typed PaperSearchInput
-> normalized query (normalize_paper_search_input)
-> Live Crossref adapter
-> SourceSnapshot + raw candidates
-> canonical candidates
-> duplicate groups + conflicts / uncertain matches
-> deterministic ranking + selection / exclusion reasons
-> ProducerExecution + metrics + stable hashes
-> validated PaperCollection (search_input bound, benchmark=None)
-> Publisher admission
```

### 基准 Benchmark 数据流
```text
fixed benchmark scenario
-> normalized benchmark query (normalize_benchmark_query)
-> Crossref/recorded source adapter
-> SourceSnapshot + raw candidates
-> canonical candidates
-> duplicate groups + conflicts / uncertain matches
-> deterministic ranking + selection / exclusion reasons
-> ProducerExecution + metrics + stable hashes
-> validated PaperCollection benchmark content (benchmark bound, search_input=None)
```

runner 只生成经过 `PaperCollection` Pydantic Schema 校验的内容；它不直接修改数据库版本或推进 Run state，所有持久化均由统一 Publisher 负责。

## 3. Crossref adapter 边界

Crossref REST `/works` adapter 仅处理公开书目 metadata：DOI、title、author、publication date、URL、resource、alternative id 等。它不请求或保存受限全文，不把 metadata link 推断为全文授权。

adapter 必须：

- 仅访问受控 HTTPS host，并拒绝跨 host redirect；
- offset/rows 分页且有明确页数/候选上限；
- timeout、transport、429/5xx 按固定 retry/backoff policy 处理；
- 非 429 的 4xx、策略拒绝、畸形 JSON/schema 不盲目重试；
- 串行分页并尊重运行时 rate-limit headers；
- 净化 HTML/control characters/credential-bearing URLs；
- 不把 response body、Authorization、Cookie、token 或其他 secret 写入日志/公开内容。

错误分类保持 `timeout | rate_limited | transport | upstream_server | upstream_client | invalid_response | policy_violation`。空 `items` 是成功的零候选；来源失败是失败，不回退 seed。

## 4. Query normalization

benchmark query normalization 是确定性组件：

1. 文本做 Unicode NFKC、空白折叠、trim 与 casefold；
2. keywords/source ids 去重并稳定排序；
3. source-independent query 保存 normalized text、keywords、year bounds、pagination 与 ranking inputs；
4. Crossref parameters 只从受控字段构造；
5. `query_hash` 覆盖会影响来源请求/排序的规范化输入与 technical rule identities；
6. `query_id` 从稳定 hash 确定性派生。

相同语义输入不能因原始大小写、Unicode 宽度、空白或容器迭代顺序产生不同 hash。

## 5. Candidate canonicalization

canonicalization 固定以下优先级：

- DOI 去除表现层前缀、URL decode 后归一；
- arXiv identity 去除表现层 URL/版本后缀后归一；
- URL 只允许 HTTP(S)，去 fragment/credentials/tracking 参数并稳定 query ordering；
- title/author 使用 Unicode normalization、casefold 与稳定标点/空白策略；
- canonical paper id 优先基于 DOI、arXiv、title+year+first-author，再到 source record identity；
- candidate occurrence identity 由 canonical input/hash 派生，不使用随机数或 Python `hash()`。

原始书目信息与 SourceSnapshot provenance 仍保留，不因 canonicalization 丢失来源事实。

## 6. Dedupe、conflict 与 ranking

确定 duplicate 的匹配顺序是 exact DOI、exact arXiv、再到受约束 title/year/author。精确 identity 匹配可以合并但必须保存字段冲突；title/year 相同但作者证据不足只产生 potential duplicate，不宣称确定重复。

ranking 只使用已声明、可解释的 deterministic features。最终排序必须有稳定 tie-breaker；每个 duplicate group 只有一个代表可入选。所有 selected/excluded candidate 都必须有可观察 reason。

## 7. Source level、Snapshot 与 hash

`source_mode` 与数据等级分开记录：

| source mode | 合法数据等级 | 约束 |
| --- | --- | --- |
| `live` | `live_result` | 真实请求与抓取时间 |
| `cached` | `real_run_cache` | 必须引用真实历史 Run/ArtifactVersion |
| `fixture` | `fixture`、`recorded_response`、`benchmark`、`manual_review` | 不表述为 Live/Cached |

每次成功 source execution 产生完整 SourceSnapshot。Crossref Snapshot 的 `query` 保存完整、稳定序列化的 `NormalizedPaperQuery`，使读取边界可通过同一 typed contract 重新计算 `query_hash`；只保存展示查询文本不足以证明 query identity。失败 execution 不伪造 Snapshot，但仍记录 query/request hash、分页策略、时间、retry 与 error classification。

`input_hash`、`output_hash` 与 ProducerExecution hash 必须覆盖影响 scientific/selection 内容的固定输入与规则；wall-clock latency 不进入 content identity。

## 8. PaperSummary Prompt 与模型边界

PaperSummary Prompt 只能通过 `packages/prompts/registry.json` / `registry.py` 的当前定义加载。运行记录固定 Prompt name/version/hash、model technical identity、parameters hash、PaperCollection ArtifactVersion/input hash、SourceSnapshot 与 Evidence inputs；不保存模型私有 chain-of-thought 或长原始响应。

Summary 只接收已选定的 PaperCollection paper identity。JSON/schema/Evidence 三层验证分别失败关闭；finding/limitation 的 `supported | unsupported | unverifiable` 科研语义保留，不能因模型输出而自动提升为支持事实。

## 9. Publisher handoff

PaperCollection/PaperSummary Pipeline 只产生 typed content/candidate。ArtifactVersion、Evidence 与 persisted SourceSnapshot 的发布必须走统一 Publisher；Pipeline 不写数据库版本、不推进 Run state，也不在 Router 中复制科研算法。

生产检索生成的 PaperCollection 绑定唯一的 `PaperSearchInput` 输入；基准场景评估生成的 PaperCollection 绑定固定的 `benchmark` 引用，两者互斥且数据等级严格隔离。

## 10. Selected candidate handoff

选中的 `PaperCandidate` 通过 API bridge 进入既有 ResearchInput ingestion：先闭合
ArtifactVersion、candidate、SourceSnapshot 与 Evidence provenance，再要求显式 lawful
access evidence。公开访问 URL 只作为摄取请求输入，实际字节、MIME、大小、SSRF、重定向、
内容哈希、CAS、ownership 与 idempotency 均由 ResearchInput 边界负责。metadata-only
只记录不可变 provenance 和拒绝/未证明原因，不创建输入；此阶段不启动 parser、summary
或 executor。Fixture、recorded、cached 和 synthetic candidate 不得被呈现为 Live 或
创建新的 ResearchInput。
