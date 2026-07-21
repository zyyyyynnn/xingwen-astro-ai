# D-01 Paper and Reasoning Benchmark

## 1. 目的与范围

本目录保存固定主案例 `exoplanet_host_star` 的版本化、机器可读论文与推理 Benchmark Package。它为 D-02～D-06、B-04、X-00 和端到端评测提供论文检索、人工结构化样例、Relation 准入、Graph 完整性与评测输入。

D-01 只提供静态基准、Pydantic 校验、稳定 hash 和纯指标计算，不实现论文检索 Adapter、外部请求、模型调用、自动摘要、自动 Claim/Relation、Graph 生成、API、数据库或 Run/ArtifactVersion 发布。

## 2. 目录与唯一事实源

```text
services/paper_pipeline/benchmarks/
├─ README.md
├─ CHANGELOG.md
└─ exoplanet_host_star/
   └─ paper-reasoning-benchmark.v1.json
```

- JSON 是 D-01 基准内容的唯一事实源，Graph taxonomy 与完整性规则也保存在同一 Package 中。
- `apps/api/src/app/schemas/paper_benchmark.py` 是 Benchmark Pydantic v2 Schema、引用完整性和指标定义的编写源。
- `apps/api/tests/test_paper_benchmark.py` 验证正常加载、恶意篡改、hash、Evidence、Relation、Trace、Graph 和指标。
- Benchmark 模型全部使用 `Benchmark` 前缀，不替代或修改 `/api/v1` DTO，也不声明 `/api/v2` 已实现。

## 3. 数据等级与使用边界

Seed papers 和结构化样例属于 `Benchmark / seed` 数据等级，只允许用于：

- 固定检索候选回归；
- 人工审查和 Relation 准入评测；
- 明确标记 scenario、schema version 和 provenance note 的 Fixture 派生。

它们不是自动获取结果、Live Run 或真实历史缓存。D-02 检索失败时不得直接返回 seed list 并将其描述为自动获取；Benchmark 和 Fixture 也不得进入 CacheSelector。

当前 Package 的 `review_status` 为 `pending_human_review`。其中的 Summary、Claim、Relation 和 Trace 是待负责人科研复核的结构化草案，不是已经通过人工正确性确认的 gold label。只有负责人完成逐项复核、添加批准记录并提升 Benchmark 版本后，才能将相应 Relation 纳入人工正确率分母。

## 4. 版本规则

- `schema_version` 表示 Pydantic/JSON 结构版本。
- `benchmark_version` 表示论文、Evidence、人工标签、Graph 或指标内容版本。
- 内容或语义变化必须提升 `benchmark_version`，更新 `change_records`、`review_records`、`CHANGELOG.md` 和 `content_hash`。
- 已被评测、Fixture 或下游 Contract 固定引用的版本不得原地改变语义。
- 消费方固定 `benchmark_id + benchmark_version + content_hash`，不得读取动态 latest。

## 5. 稳定 Hash

Benchmark 与 C-01 Manifest 共同调用 `app.schemas._hashing.compute_canonical_model_hash`，规则完全一致：

1. 先通过对应 Pydantic payload 模型校验并应用显式默认值；
2. 从顶层排除 `content_hash` 自身；
3. 使用 JSON mode 序列化并排除 `None`；
4. 对对象 key 按字典序排序；
5. 保留所有数组的声明顺序；
6. 使用 UTF-8、非 ASCII 转义关闭、紧凑分隔符且禁止 NaN；
7. 对规范化字节计算 SHA-256，格式为 `sha256:<64 lowercase hex>`。

`created_at`、`review_records` 和 `change_records` 均进入 hash，因为它们属于已发布基准的审计内容。测试固定了对象 key 重排不改变 hash、数组重排改变 hash，以及 JSON 重复加载后的 hash 稳定性。

## 6. 论文核验与访问边界

每篇 seed paper 至少记录 DOI、arXiv ID 或官方稳定 URL，并保存核验来源、核验日期和核验字段。优先使用 DOI/publisher、arXiv、NASA/NTRS/IPAC 等稳定记录。

`authors` 只保存逐名核验的作者，不使用 `et al.` 伪装成作者；`authors_complete` 明确说明作者数组是否为完整名单。当前长作者名单使用经过核验的前三位作者并标记为不完整，消费者不得把它展示成完整署名。

Package 还逐篇记录：

- metadata 和 abstract 是否公开；
- full text 是否有开放 preprint，或仍依赖 publisher；
- 是否需要鉴权；
- 许可/使用边界；
- 限流和公网运行风险。

本基准只保存元数据和短 abstract evidence。无法访问或未核验的全文不得生成全文 locator、页码或正文 Quote。来源 API 的实时配额和许可仍需 D-02 在实现时重新核验，D-01 声明不能替代运行时 SourceSnapshot。

## 7. Evidence 等级

当前证据等级包括：

- `public_abstract`：来自公开、已核验摘要；
- `open_full_text`：仅在明确核验开放全文后使用；
- `publisher_metadata`：只支持标题、作者、年份、DOI 等书目信息。

当前核心科研样例只使用 `public_abstract`，locator 明确记录 URL、section、paragraph 和 text range。摘要证据不能支持需要正文表格、页码、完整方法或对象级明细的结论。

`manual_transcription_from_verified_source` 表示保存短原文摘录；`manual_paraphrase_from_verified_source` 表示保存人工释义，并仍以 locator 指向可核对的摘要范围。释义不得扩大原文结论，也不得展示成逐字引文。

## 8. 人工评审方式

负责人评审至少逐项检查：

1. DOI/arXiv/URL、标题、作者引用和年份；
2. Quote 是否能在 locator 指定的公开来源找到；
3. Summary/Claim 是否未超出 Quote；
4. Relation 两端对象、指标、条件和版本是否可比；
5. Accepted Relation 是否绑定双方 Evidence 和 Trace；
6. candidate/rejected 的保留原因是否充分；
7. Graph 是否只发布 accepted Relation；
8. 评审人、日期、范围、结果和备注是否进入 `review_records`。

不得把模型输出或自动生成草案直接标记为人工正确答案。任何批准都会改变 hash，必须更新版本和变更记录。

## 9. 指标定义

`evaluate_benchmark` 只执行纯计数，不访问外部来源。Package 中冻结以下分子、分母：

| 指标 | 分子 | 分母 | 空集合 |
| --- | --- | --- | --- |
| Candidate recall | 返回的 distinct expected paper id | 所有场景 distinct expected paper id | `not_available` |
| Schema pass rate | 通过对应 Schema 的输出项 | 提交 Schema 校验的全部输出项 | `not_available` |
| Evidence coverage | 已满足的 finding/limitation/Claim/accepted Relation/Trace/GraphEdge Evidence 义务 | 本次输出全部 Evidence 义务 | `not_available` |
| Relation human accuracy | 类型和准入状态均匹配批准标签的 Relation | 具有批准人工标签的 Relation；pending 不计入 | `not_available` |
| Evidence-less relation block rate | 被拦截进入 accepted 的无证据 Relation | 故意缺少必要 Evidence 的全部 Relation | `not_available` |

分子不得大于分母。人工批准 Relation 为空时必须报告 `not_available`，不能用 0% 或 100% 掩盖没有人工 gold label 的事实。

## 10. 下游消费

- D-02：固定 search scenarios、source policy、expected candidates 与 seed identifiers，真实查询结果另建 SourceSnapshot。
- D-03：使用 Summary/Evidence 草案做 Prompt、Schema 和 Evidence 回归，不能直接发布为模型产物。
- D-04：使用 Claim、Relation、Trace 和负例验证准入与人工评测。
- D-05：使用同包 Graph taxonomy、accepted Relation 和完整性规则验证 Graph 发布门。
- D-06：只将已发布版本作为修订基线，不原地改写本 Package。
- B-04/X-00：通过版本/hash 固定引用；不得复制枚举或维护第二套基准正文。

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
