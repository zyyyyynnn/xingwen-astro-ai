# Case / Field Manifest

## 1. 范围

本目录保存主案例 `exoplanet_host_star` 的机器可读数据事实源。Manifest 冻结字段、单位、来源别名、冲突、缺失、误差、上下限、对象标识、crossmatch 与 Evidence locator 规则；它不执行数据获取、实体匹配、单位换算或质量评分。

主案例面向 TESS 系外行星候选体及其宿主恒星。字段语义以项目 Authority 与 NASA Exoplanet Archive 官方表定义为依据：

- [TESS Objects of Interest 表定义](https://exoplanetarchive.ipac.caltech.edu/docs/API_TOI_columns.html)
- [Planetary Systems / PSCompPars 表定义](https://exoplanetarchive.ipac.caltech.edu/docs/API_PS_columns.html)
- [TAP 使用说明](https://exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html)

## 2. 唯一事实源与目录边界

- `services/data_pipeline/manifests/exoplanet_host_star/` 保存 Case Manifest 与 Field Manifest。
- `source-evidence/` 保存官方定义、TAP_SCHEMA 观测与字段裁决证据；证据解释 Manifest 决策，但不替代生产合同。
- `mapping-rules/` 保存字段映射执行策略与单位换算 catalog；它固定 row-grain/entity projection、tolerance、容量、Decimal serialization limits 与常数 provenance，不复制 Field Manifest 字段事实。
- `quality-rules/` 保存唯一质量 RuleSet、公式注册表、ratio/status policy、Contract bindings、Publisher pass-only policy 与容量边界；它不复制 Field Manifest 的字段—指标关系。
- `apps/api/src/app/schemas/manifest.py` 是 Pydantic Schema authoring source，只定义结构、稳定 hash 与静态校验。
- `packages/schemas/generated/` 只保存 exporter 生成的 JSON Schema，不手写第二套生产 Schema。
- Domain、Contract、Repository 与 Pipeline 运行时代码按精确 Manifest identity/hash 消费，不复制字段清单。

`ResearchContract.requested_fields` 只接受 canonical Field Manifest IDs；来源列名不是 requested field identity。

## 3. Manifest 结构

### Case Manifest

Case Manifest 至少包含：

- `case_id`、名称与描述；
- `schema_version`、`manifest_version`、`content_hash` 与维护 identity；
- 支持的对象类型、默认请求字段与允许来源；
- 对 Field Manifest 的精确 identity/version/hash 引用；
- 对象 identity/crossmatch 规则与最低 Evidence locator 要求。

### Field Manifest

Field Manifest 至少包含：

- `manifest_id`、`case_id`、technical version、content hash 与维护 identity；
- 受控来源、来源列 allowlist、来源证据引用、单位与规则注册表；
- 完整字段定义；
- 每个字段的来源别名/优先级、冲突、缺失、误差、limit、identity/matching、Evidence、conversion 与 quality-input 声明。

Case Manifest 通过 version/hash 引用 Field Manifest；两份文件分别计算 hash，避免循环引用。

## 4. 字段事实读取

README 不维护 canonical 字段表或 NASA 原始列清单。生产事实只来自：

- Field Manifest `fields[]`：canonical field、unit、nullable、alias 与 companion columns；
- Field Manifest `sources[]`：provider/table mapping、approved columns、row key、reference/provenance roles 与裁决引用；
- Case Manifest：默认字段集合、provider allowlist 与 Field Manifest pin。

官方定义与 TAP_SCHEMA 观测的差异只保存在 `source-evidence/`。修改字段事实时先更新证据/裁决，再更新 Manifest、相关 machine assets、测试与 hashes。

## 5. 来源与优先级

Case Manifest 使用 provider source id `nasa_exoplanet_archive`；Field Manifest 复用同一 `SourceDefinition`，通过 `provider_source_id + source_table` 表达 table source identity。不得为 API、Pipeline 或页面另建第二套来源注册表。

source priority 与字段适用范围直接读取 Field Manifest。优先级只能决定 canonical selection，不能删除低优先级原值、冲突或 Transformation Evidence。完整执行规则见 [Data Artifacts](../../../docs/engineering/DATA_ARTIFACTS.md)。

## 6. 规则

- alias 唯一性范围是 `(source_id, source_table, raw_field)`；一个 raw field 不得映射到多个 canonical field。
- alias 的 value/uncertainty/limit/row-key/reference/provenance columns 必须属于对应 approved columns 与 role allowlist。
- 官方定义存在但单次 TAP_SCHEMA 观测暂缺的列只可依据当前裁决保留；live-only 列不能未经 Authority/裁决加入。
- 定量字段引用 canonical unit；允许源单位与 canonical unit 必须 quantity-kind 一致并声明 conversion rule identity。
- 标识/分类/文本字段显式使用 `none` unit identity，不用空字符串表示无单位。
- 正负 uncertainty 分开保留，缺失 uncertainty 不解释为零。
- upper/lower limit 由来源 flag rule 解释，不把 bound 当普通测量。
- display name 只用于 alias matching；唯一 identity 来自受控标识或已批准组合键。
- coordinate matching 只声明所需字段与算法 technical identity；实际阈值/算法由 Cross-source Alignment 实现。
- Evidence locator 至少固定 SourceSnapshot、query hash、row key、raw field 与来源 reference locator（若来源提供）。
- transformation rule 保存 immutable rule identity，不嵌入执行代码。
- quality metric input 只声明哪些字段参与 metrics；质量评估计算结果，不把 score 写回 Manifest。

## 7. 稳定 hash

Manifest `content_hash` 使用 `sha256:<64 lowercase hex>`：

1. Pydantic 校验通过；
2. hash 投影排除顶层 `content_hash` 本身；
3. object keys 稳定排序，arrays 保留声明顺序；
4. UTF-8、紧凑 JSON 与明确日期编码；
5. 对 canonical bytes 计算 SHA-256。

hash 标识内容，不替代 case/manifest identity 或 technical version。技术 identity 与 exact hash 用于可复现 pin；历史变化由 Git 保存。

## 8. 校验与消费

Schema/model validation 至少覆盖：

- schema/manifest technical identity 与 hash 格式；
- Case ↔ Field Manifest identity/version/hash 一致；
- canonical field、source alias、registry identity 不重复；
- provider source 可稳定解析到受控 table source；
- source allowlist、row key、reference/provenance companion columns 与当前裁决一致；
- canonical/source units 与 quantity kind 可转换；
- source priority、uncertainty、limit、Evidence、transformation、quality refs 均存在；
- `ResearchContract.requested_fields` 非空且只包含当前 Case Manifest canonical IDs；
- source alias 不能冒充 requested field identity。

## 9. 维护边界

消费方必须固定 manifest technical identity/hash，不读取动态 `latest` 作为科研可复现输入。Fixture/Recorded/Benchmark/Live/Cached 是数据来源/运行等级，不属于 Manifest 生命周期，也不能改变 Manifest Authority。定义变更同步更新受影响的 machine assets、hash、测试与生成 Contract；Git 保存历史，不在 Manifest 旁维护 machine changelog。
