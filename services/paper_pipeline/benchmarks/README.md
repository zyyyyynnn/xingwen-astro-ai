# Paper and Reasoning Benchmark

## 1. 目的与范围

本目录保存固定主案例 `exoplanet_host_star` 的版本化、机器可读论文与推理 Benchmark Package。它为论文检索、结构化摘要、Claim/Relation 准入、Graph 完整性和端到端评测提供固定输入。

本 Package 只提供静态基准、Pydantic 校验、稳定 hash 和纯指标计算，不实现论文检索 Adapter、外部请求、模型调用、自动摘要、自动 Claim/Relation、Graph 生成、API、数据库或 Run/ArtifactVersion 发布。

## 2. 目录与唯一事实源

```text
services/paper_pipeline/benchmarks/
├─ README.md
└─ exoplanet_host_star/
   └─ paper-reasoning-benchmark.json
```

- JSON 是基准内容的唯一事实源，Graph taxonomy 与完整性规则也保存在同一 Package 中。
- `apps/api/src/app/schemas/paper_benchmark.py` 是 Benchmark Pydantic v2 Schema、引用完整性和指标定义的编写源。
- `apps/api/tests/test_paper_benchmark.py` 验证正常加载、恶意篡改、hash、Evidence、Relation、Trace、Graph 和指标。
- Benchmark 模型全部使用 `Benchmark` 前缀，只描述静态科研基准，不替代生产 Research API 或 Pipeline domain contracts。

## 3. 数据等级与使用边界

Seed papers 和结构化样例属于 `Benchmark / seed` 数据等级，只允许用于：

- 固定检索候选回归；
- 网页端 GPT 科研审查和 Relation 准入评测；
- 明确标记 scenario、schema version 和 provenance note 的 Fixture 派生。

它们不是自动获取结果、Live Run 或真实历史缓存。论文检索失败时不得直接返回 seed list 并将其描述为自动获取；Benchmark 和 Fixture 也不得作为缓存回退。

当前 Package 的科研评审记录绑定 `benchmark_version`、`scientific_payload_hash` 与完整对象 scope；所有可评审的 Summary、Evidence、Claim、Relation 和 Trace 均满足相同科研评审边界。仓库工作流、Issue、PR、Commit 与 CI 状态不进入 Benchmark Contract。

## 4. 版本规则

- `schema_version` 表示 Pydantic/JSON 结构版本。
- `benchmark_version` 表示论文、Evidence、科研审核标签、Graph 或指标内容版本。
- 内容或语义变化必须提升 `benchmark_version`，同步当前 `scientific_review` 与 `content_hash`。
- `scientific_review` 表达单一当前科研评审：记录 reviewer identity、`reviewed_at`、purpose、verdict、当前 benchmark version、scientific payload hash、findings 和结构化对象范围；automation 不能产生正式通过结论。
- 当前科研评审存在阻断项时不得批准 Package。
- 已发布的技术身份不得原地改变语义；仓库只维护当前消费的 Benchmark 定义。
- 消费方固定 `benchmark_id + benchmark_version + content_hash`，不得读取动态 latest。

## 5. 稳定 Hash

Benchmark 与 Case/Field Manifest 共同调用 `app.schemas._hashing.compute_canonical_model_hash`，规则完全一致：

1. 先通过对应 Pydantic payload 模型校验并应用显式默认值；
2. 从顶层排除 `content_hash` 自身；
3. 使用 JSON mode 序列化并排除 `None`；
4. 对对象 key 按字典序排序；
5. 保留所有数组的声明顺序；
6. 使用 UTF-8、非 ASCII 转义关闭、紧凑分隔符且禁止 NaN；
7. 对规范化字节计算 SHA-256，格式为 `sha256:<64 lowercase hex>`。

`created_at` 与当前 `scientific_review` 进入完整 `content_hash`，因为它们属于当前基准的审计内容。测试固定了对象 key 重排不改变 hash、数组重排改变 hash，以及 JSON 重复加载后的 hash 稳定性。

`scientific_payload_hash` 使用相同 canonical JSON 规则，但排除 `content_hash`、自身和 `scientific_review`，并递归规范化 Package 与所有对象级 `review_status`。它仍覆盖版本、来源、论文、Summary、Evidence、Claim、Relation、Trace、Graph 和指标，使科研 Review 能绑定稳定科研内容，再追加 Review 元数据而不形成 hash 自引用；仅改变批准状态不会改变 scientific hash，但会改变完整 `content_hash`。`scientific_payload_hash` 与完整 Package `content_hash` 均由当前 Pydantic/共享 hashing 边界计算并由测试固定，不在文档维护第二份算法或动态 latest。

## 6. 论文核验与访问边界

每篇 seed paper 至少记录 DOI、arXiv ID 或官方稳定 URL，并保存核验来源、核验日期和核验字段。优先使用 DOI/publisher、arXiv、NASA/NTRS/IPAC 等稳定记录。无法解析的 Clark NTRS URL 使用对应 Crossref 单记录 API，Crossref 核验统一使用不依赖 publisher 跳转的单记录 API URL。

`authors` 只保存逐名核验的作者，不使用 `et al.` 伪装成作者；`authors_complete` 明确说明作者数组是否为完整名单。当前长作者名单使用经过核验的前三位作者并标记为不完整，消费者不得把它展示成完整署名。

Package 还逐篇记录：

- metadata 和 abstract 是否公开；
- full text 是否有开放 preprint，或仍依赖 publisher；
- 是否需要鉴权；
- 许可/使用边界；
- 限流和公网运行风险。

本基准只保存元数据和短 abstract evidence。无法访问或未核验的全文不得生成全文 locator、页码或正文 Quote。来源 API 的实时配额和许可仍需论文检索 Adapter 在运行时重新核验，静态声明不能替代运行时 SourceSnapshot。

Crossref 的 `documented_policy` 保存当前基准所固定的官方声明与冲突说明；`observed_runtime_limits` 保存基准核验时 public 单记录/列表请求实际观测值。未配置真实联系身份时不得伪造 polite 响应头。静态值只是版本化快照，运行时 Adapter 必须优先服从当前响应头、处理 `429`/backoff，并在缺失头时使用保守策略；本 Package 不实现 Adapter。

## 7. Evidence 等级

当前证据等级包括：

- `public_abstract`：来自公开、已核验摘要；
- `open_full_text`：仅在明确核验开放全文后使用；
- `publisher_metadata`：只支持标题、作者、年份、DOI 等书目信息。

当前核心科研样例只使用 `public_abstract`，locator 明确记录 URL、section、paragraph 和 text range。摘要证据不能支持需要正文表格、页码、完整方法或对象级明细的结论。

`manual_transcription_from_verified_source` 表示保存短原文摘录；`manual_paraphrase_from_verified_source` 表示保存人工释义，并仍以 locator 指向可核对的摘要范围。释义不得扩大原文结论，也不得展示成逐字引文。

### 7.1 Relation 方向

Relation 方向语义以 [Reasoning Protocol](../../../docs/ai/REASONING_PROTOCOL.md#4-relation-类型) 为权威来源；本 Package 只保存遵循该语义的实例，并由回归测试约束 Trace 与 GraphEdge 顺序。

## 8. 网页端 GPT 科研评审方式

网页端 GPT 科研审查至少逐项检查：

1. DOI/arXiv/URL、标题、作者引用和年份；
2. Quote 是否能在 locator 指定的公开来源找到；
3. Summary/Claim 是否未超出 Quote；
4. Relation 两端对象、指标、条件和版本是否可比；
5. review-approved Relation 是否绑定双方 Evidence 和已批准 Trace；
6. candidate/rejected 的保留原因是否充分；
7. Graph 是否只发布 accepted Relation；
8. `reviewer_type=web_gpt`、稳定 identity、purpose、当前 version、scientific payload hash、结构化对象范围、日期、verdict 与 findings 是否进入唯一当前 `scientific_review`。

不得把本地自动生成草案或测试 identity 标记为科研通过。Package 只有在当前 version/hash 的有效 `benchmark_scientific_review` 通过记录覆盖所有 source policy、seed paper、Summary、Evidence、Claim、Relation、Trace 和 GraphEdge，且所有带科研评审状态的对象均已批准时才能标为 `approved`。PR 技术审查由 GitHub 工作流独立管理，不得写入 Benchmark。

## 9. 指标定义

`evaluate_benchmark` 只执行纯计数，不访问外部来源。Package 中冻结以下分子、分母：

| 指标                              | 分子                                                                              | 分母                                        | 空集合          |
| --------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------- | --------------- |
| Candidate recall                  | 返回的 distinct expected paper id                                                 | 所有场景 distinct expected paper id         | `not_available` |
| Schema pass rate                  | 通过对应 Schema 的输出项                                                          | 提交 Schema 校验的全部输出项                | `not_available` |
| Evidence coverage                 | 已满足的 finding/limitation/Claim/accepted Relation/Trace/GraphEdge Evidence 义务 | 本次输出全部 Evidence 义务                  | `not_available` |
| Relation scientific accuracy      | 类型和准入状态均匹配批准标签的 Relation                                           | 具有批准科研标签的 Relation；pending 不计入 | `not_available` |
| Evidence-less relation block rate | 被拦截进入 accepted 的无证据 Relation                                             | 故意缺少必要 Evidence 的全部 Relation       | `not_available` |

分子不得大于分母。科研批准 Relation 为空时必须报告 `not_available`，不能用 0% 或 100% 掩盖没有 approved scientific benchmark label 的事实。

## 10. 下游消费

- Benchmark runner 消费 search scenarios、source policy、expected candidates 与 seed identifiers；生产 Paper Search 则从 `ResearchContract.paper_search_scope` 产生 typed `PaperSearchInput`，两者复用 Crossref、normalization、canonicalization、dedupe、ranking、SourceSnapshot、ProducerExecution 与 hashing primitives。
- 摘要生成使用 Summary/Evidence 草案做 Prompt、Schema 和 Evidence 回归，不能直接发布为模型产物。
- 文献推理使用 Claim、Relation、Trace 和负例验证准入与科研评测。
- Graph 发布门使用同包 Graph taxonomy、accepted Relation 和完整性规则。
- 修订流程引用明确的已发布 ArtifactVersion，不原地改写已发布科研事实。
- API 与端到端评测通过版本/hash 固定引用；不得复制枚举或维护第二套基准正文。

## 11. 验证入口

在 `apps/api` 中执行：

```powershell
uv sync --frozen
uv run pytest tests/test_paper_benchmark.py
uv run pytest
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas
uv run python ../../scripts/export_schemas.py --output ../../.artifacts/schemas --check
```

仓库级另执行 `git diff --check`、`python scripts/check_foundation.py` 和 `pnpm check:docs`。
