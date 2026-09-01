# Scientific Document Parsing Contract

| 元数据 | 值 |
| --- | --- |
| Authority | Scientific Document Parsing Canonical Contract、Parser Port、Golden Set 与 Benchmark |
| Scope | 固定 `exoplanet_host_star` Case 的科学文档输入、解析、定位与数据准入 |

本文是科学文档解析边界的唯一规范。它不是通用 Document AI、网页解析、FITS
管线、图表数字化器或第二套 Evidence、Workflow、Version 系统。

## 1. Ownership and architecture

Xingwen owns the canonical parse schema, parse-quality semantics, locator and
Evidence meaning, immutable identity, and benchmark contracts. Upstream adapters
own PDF/image decoding, text extraction, geometry, OCR, layout, table, formula
and figure recognition.

解析结果必须沿用既有链路：

```text
Document → DocumentParse → ScientificDataExtractionCandidate
         → Field Manifest / existing mapping / UnitConversionCatalog
         → Data Artifact Quality → Publisher → ArtifactVersion
```

文档不是第三个 Crossmatch side，不创建新的 canonical object，不引入第二个
Publisher、Evidence 或版本系统。`docs/references/**` 只作参考，不能作为生产
Authority 或导入来源。

## 2. Canonical schema and Parser Port

唯一 authoring source 是
`apps/api/src/app/schemas/scientific_document.py`。其导出 JSON Schema 由
`compute_scientific_document_schema_hash()` 固定；
`SCIENTIFIC_DOCUMENT_SCHEMA_VERSION` 是 schema 的技术版本。

核心模型包括 `DocumentParseInput`、`DocumentParseCandidate`、
`DocumentPage`、`DocumentBlock`、`DocumentTable`、`DocumentTableCell`、
`DocumentFormula`、`DocumentFigure`、`DocumentLocator`、`DocumentBBox`、
`TextSpan`、`DocumentParseProfile` 与
`ScientificDataExtractionCandidate`。Canonical schema 不依赖 vendor 类型；
native/visual engine 只作为 provenance 字段记录。

Parser Port 只有一个 vendor-neutral 能力：

```text
DocumentParserPort.parse_document(
    input: DocumentParseInput
) -> DocumentParseCandidate
```

调用方提供并负责 `source_type`、`mime_type` 与输入内容身份；解析器不得猜测。
科学文档准入接受上传的 PDF / 支持的图像，以及经受控 URL 摄取、按实际字节确认同类 MIME 的文档。URL 输入保留 `type=url` 与 `source_type=url_fetch` 来源身份；研读和原文读取使用已存储的不可变内容、项目所有权及统一 MIME 准入。
生产 hybrid adapter 可先使用 native PDF text/geometry，再把需要视觉能力的页
路由到已配置的 visual service。缺少视觉配置或调用失败时必须显式返回
`partial`/`unsupported`，不能伪造结构或数值。

`DocumentParseProfile.routing_policy_id` 与 `resource_policy_id` 保存策略
身份；`parser_profile_version` 只表示 parser profile 的技术版本。

## 3. Quality semantics

- `accepted` 表示该 region 可进入准入链，不表示科学事实已被验证。
- `partial` 表示可用区域存在，但未解析不等于不存在，质量必须向下游传播。
- `unsupported` 表示不能可靠处理；不得生成、补全或自动选择该 region 的事实。

一个 table observation 的 parse quality 是推导科学语义所需的 authoritative
region 闭包：table、entity/value header 与对应 entity/value body cell。
任一为 `partial` 则 observation 为 `partial`；五者均为 `accepted` 才为
`accepted`；任一 semantic region 为 `unsupported` 则该 observation 不得准入。
Unsupported table/row/cell 不产生可用 scientific observation；应用层通过
稳定 `DOCUMENT_PARSE_UNSUPPORTED` reason code 暴露被拒绝的 region。

Whole-document `unsupported` 不得包含 accepted block。Unsupported table 不得
携带可用 structured rows；unsupported formula/figure 不得携带 recognized
textual payload。

## 4. Locator and aggregate integrity

`DocumentLocator` 是唯一定位结构，包含 `page_index`、可选 `block_id`、
`bbox`、`reading_order`、`text_span`、`table_id` 与 `cell_id`。坐标采用页面
左上角原点、x 向右、y 向下的绝对 PDF points；不使用 0..1 归一化。未知几何
使用 `None`，不能用零矩形代替。

`page_index` 按 PDF 物理页序从 0 开始。解析适配层转换底层库的页号，展示层在
用户可见页码中加 1；page、block、table、formula、figure 与 Evidence 共享该约定。

HTML table 只提供 enclosing table/block geometry 时，各 `DocumentTableCell.bbox`
必须为 `None`，不能把 enclosing bbox 复制成伪 cell geometry。由该 cell 派生的
`DocumentLocator` 仍绑定真实 `table_id`/`cell_id`，其 `bbox` 明确回退到 enclosing
table block bbox；这样既保留可核验的 region locator，也不虚构 cell-level 坐标。

表格 block 的 `text` 从 canonical cells 按真实行列生成纯文本，不保留供应商
HTML 标记。合并单元格只在 anchor 位置输出一次，覆盖位置保持空白；数值、单位
与不确定性不改写。摘要和展示消费同一 block text，Evidence text span 定位到该
不可变文本；单元格级科学数据准入继续使用 table/cell locator。

视觉 block 的展示包装转换为可读纯文本，保留科学内容；未知标记保留供下游安全
校验拒绝，不通过删去未知内容绕过准入。Figure 保留真实 region geometry；图片占位 HTML 的路径、属性与通用 alt 标签
不作为正文或图注。没有识别到可读文本时，figure text/caption 为 `None`、quality
为 partial。独立 figure/table caption 保持 caption block，参与正常文本 Evidence。

长文摘要按文档顺序合并相邻段落与短章节，在字符数和 Evidence 条目数预算内
分片；章节标题不单独强制触发模型调用。每条 Evidence 保留原章节、页码与文本
定位，分片携带所覆盖章节的有序提示，聚合结果继续校验分片内引用闭包。

`cell_id` 必须同时有 `table_id`；`text_span` 必须同时有 `block_id`。持久化
层必须在 immutable parse 上重新验证 locator，确认 page、block、table、cell
与 bbox 闭合。

`DocumentParseCandidate` 必须拒绝：

- 重复 page/block/table/cell identity 或重复 page reading order；
- page、block、table、formula、figure 的悬空、跨页或错误 block-kind 引用；
- bbox 越出页面或 table grid，重复/无序/重叠的 table anchors；
- parser profile、config、native/visual provenance 不一致。

每个 canonical block 必须在其所属 `DocumentPage.block_ids` 中出现且只出现一次。

## 5. Data admission and provenance

Raw extraction candidate 只保留 raw value/unit/text、field/entity hints、
ResearchInput/SourceSnapshot/DocumentParse identity、parse quality 与一个
`DocumentLocator`。它不负责 canonical mapping、单位归一化、科学选择或发布。

准入规则如下：

- field 只能通过 Field Manifest 的 canonical field id 或 exact normalized
  `DocumentFieldAlias` 解析；禁止 fuzzy、LLM 或动态 alias；
- entity 只能 exact-match 到 frozen Crossmatch identity row；不创建文档侧
  canonical object；
- uncertainty、upper/lower limit、explicit null 只在 document admission
  解析一次，Dataset projection 不重新读取 free text；
- outcome 只能是 `accepted`、`review_required` 或 `rejected`，并带稳定
  reason code；`review_required` 不得自动选择；
- 授权必须同时具备 Contract 的 `document_source_policy = research_input`、
  Case Manifest capability、bound ResearchInput、persisted DocumentParse、
  其 persisted SourceSnapshot 与有效 locator。

`DocumentDataAdmissionService.prepare(project_id, run_id, contract,
crossmatch)` 只解析 Contract draft 或该 Run 绑定的 ResearchInput。每个输入
没有 parse 时跳过，存在多个 distinct parse 时以
`DOCUMENT_PARSE_SELECTION_AMBIGUOUS` fail closed。

`execute(plan)` 只消费冻结的 Contract、Manifest pins、CrossmatchResult、RuleSet、
parse identity 与完整 SourceSnapshot projection，产生 raw candidates、typed
observations、outcomes 与 `unsupported_regions`。Producer input/output hash
覆盖这些完整事实，但不引入另一套 hash graph。

Document SourceSnapshot 必须复用既有 persisted row；Data Artifact binding 将
pipeline snapshot identity 映射到该 row，禁止重复创建。projection 必须保留
`source_version_or_etag`、`cache_version` 与 `request_metadata`。

## 6. Upstream boundary and machine assets

上游采用信息的唯一 machine authorities 是：

- `services/scientific_document/upstream_adoption.json`：包、导入根、adapter、
  runtime policy、组件角色与 license provenance；
- `services/scientific_document/visual_model_assets.json`：视觉组件的 immutable
  source、revision、license、文件清单与 asset identity；
- `services/scientific_document/golden_set.json`：固定 fixture、real local-only
  publication records、annotations 与 content identity。

规范文档只定义边界，不复制这些文件的 inventory、路径或 hash。模型目录必须
在 parser 初始化前完成 machine verification；local path/cache name 不是模型
identity。CPU 与 GPU profile 的证据必须独立，未验证能力必须明确为
`not_run`/`not_applicable`，不能由另一 profile 推断。

## 7. Benchmark and runtime boundary

`services/scientific_document/benchmark_runner.py` 使用真实 pinned adapter
运行已提交 fixture，验证 Golden/config/schema/upstream identity、quality counts、
geometry locator 与 deterministic input/output hash。未测能力必须保持显式状态，
不能表示成零覆盖率。

Runner 提供三种显式模式，消费同一冻结 Golden Set：`native-only`（无视觉后端）、
`hybrid`（必须配置真实 PaddleOCR-VL layout-parsing 服务，或已由 committed asset
manifest 完整校验的 local bundle；远程 URL+revision 与 local bundle 严格互斥，
缺配置时拒绝启动，绝不把降级运行标成 hybrid）与 `paired`（同一 manifest 的两种模式合并为一份可
对比报告，逐 mode 携带 accepted/partial/unsupported、anchor recovery、
routing coverage 与延迟/内存均值指标）。测量诚实性由契约强制：latency 取自
单调时钟实测；`peak_memory_bytes` 必须携带真实观测口径
（`python_heap_tracemalloc`），不得冒充进程 RSS 或 GPU 内存；GPU 未执行必须
记为 `not_run`/`deferred`；hybrid/paired 报告必须携带完整 visual provenance，
且 `scripts/check_scientific_document_benchmark_report.py` 对缺少实测 hybrid
case、latency、provenance，或没有任何成功 visual routing 的自述直接失败。报告 identity hash 排除 wall-clock
与计时噪声字段，同输入重复运行保持稳定。真实 Paddle invocation 属受控集成证据，
公共 CI 只验证 schema、deterministic parser tests 与已产出报告的
provenance/hash 契约。

受控 real Paddle CPU 执行的 hybrid/paired machine reports 固化在
`services/scientific_document/evidence/`。报告输入的 publication assets 是
`source_mode=fixture`，模型推理、routing、latency 与 output 则来自真实 production
hybrid adapter；因此这些 Artifact/evidence 不得标记为 `live`。CI 对两份报告执行
同一个 fail-closed checker，使任意 exact checkout 都能复核 model/revision、
config/input/output hash、case-level latency 与成功 visual routing。

API 只暴露一个 `HybridScientificDocumentParser` 与一个 DocumentParse persistence
边界。CAS reload、persisted SourceSnapshot、parser identity、locator 与 quoted
text 必须在 paper summary、export、Literature/Graph projection、Feedback 和
document-source read 前重新验证。HTML parsing、plot digitization、scanned OCR
和未授权的模型下载不在本 Contract 内。

## 8. Governance gate

`scripts/check_scientific_document_governance.py` 是实现门禁，负责检查：

- production 不导入 `docs.references`；
- parser import 只来自 approved adoption manifest；
- adoption 版本与关键 manifest 字段完整；
- CPU/GPU profile 证据不互相冒用；
- tracked contract/evidence 不含 machine-local absolute path、模型权重或
  未授权 vendor source；
- Canonical schema 不含 vendor import。

机器门禁不能判断外部实现是否被手写重造；任何 OCR、layout、reading-order、
table、formula、figure 或 parser engine 的复制/改名实现仍违反本 Contract。
