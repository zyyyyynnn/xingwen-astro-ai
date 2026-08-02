# C-01 Case / Field Manifest

## 1. 范围

本目录保存主案例 `exoplanet_host_star` 的版本化、机器可读数据事实源。C-01 只冻结字段、单位、来源别名、冲突、缺失、误差、上下限、对象标识、crossmatch 与 Evidence locator 规则，不执行数据获取、实体匹配、单位换算或质量评分。

主案例面向 TESS 系外行星候选体及其宿主恒星。当前字段语义以项目架构文档和 NASA Exoplanet Archive 的官方表定义为依据：

- [TESS Objects of Interest 表定义](https://exoplanetarchive.ipac.caltech.edu/docs/API_TOI_columns.html)
- [Planetary Systems / PSCompPars 表定义](https://exoplanetarchive.ipac.caltech.edu/docs/API_PS_columns.html)
- [TAP 使用说明](https://exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html)

## 2. 唯一事实源与目录边界

- `services/data_pipeline/manifests/exoplanet_host_star/` 保存 Case Manifest 和 Field Manifest 数据。
- `services/data_pipeline/manifests/exoplanet_host_star/source-evidence/` 保存官方定义、TAP_SCHEMA 观测和裁决记录；证据解释来源列裁决，但不替代 Manifest 的生产契约。
- `services/data_pipeline/manifests/exoplanet_host_star/mapping-rules/` 保存 C-04 执行策略与单位换算实现 catalog；它固定执行语义和常数 provenance，但不复制 Field Manifest 字段事实。
- `apps/api/src/app/schemas/manifest.py` 是 Pydantic v2 Schema authoring source，只定义结构、稳定 hash 和静态校验，不新增 API 端点。
- `packages/schemas/generated/` 只保存现有导出脚本生成的 JSON Schema，不手写第二套生产 Schema。
- `packages/domain`、`packages/contracts`、前端和 Pipeline 运行时代码只能按版本引用 Manifest，不复制字段清单。
- Pipeline（`/api/tasks`）现有 Mock 字段保持兼容；目标 `/api` 的 `ResearchContract.requested_fields` 使用 canonical field id，不使用来源列名。

## 3. Manifest 拆分

### Case Manifest

Case Manifest 至少包含：

- `case_id`、中英文名称和描述；
- `schema_version`、`manifest_version`、`content_hash`、`created_at` 和 `maintained_by`；
- 支持的对象类型、默认请求字段和允许来源；
- 对 Field Manifest 的不可漂移引用（manifest id、版本和 hash）；
- 对象 identity/crossmatch 规则与最低 Evidence locator 要求。

### Field Manifest

Field Manifest 至少包含：

- `manifest_id`、`case_id`、版本、hash、`created_at` 和 `maintained_by`；
- 受控来源、来源列 allowlist、来源证据引用、单位和规则标识注册表；
- 完整字段定义列表；
- 每个字段的来源别名、来源优先级、冲突策略、缺失/误差/上下限、身份与匹配、Evidence、转换版本及质量指标输入。

Case Manifest 通过版本和 hash 引用 Field Manifest；两份文件分别计算 hash，避免循环引用。

## 4. 字段事实读取方式

README 不维护 canonical 字段表或 NASA 原始列清单，避免与 JSON 漂移。唯一生产事实源是：

- Field Manifest 的 `fields[]`：canonical field、单位、可空性、alias 和 companion column；
- Field Manifest 的 `sources[]`：provider/table 映射、`approved_columns`、row key、reference/provenance 角色和版本化裁决引用；
- Case Manifest：默认字段集合、provider-level 允许来源以及对 Field Manifest 版本/hash 的固定引用。

官方定义和 live TAP_SCHEMA 的差异只记录在 `source-evidence/`。修改字段事实时先更新证据与裁决，再更新 Manifest、测试、版本和 hash；不得手工同步 README 字段表。

## 5. 来源和优先级声明

C-01 只声明来源元数据和选择规则，不访问来源：

API/Case Manifest 使用 provider source id `nasa_exoplanet_archive`；Field Manifest 复用同一组 `SourceDefinition`，以 `provider_source_id + source_table` 派生 table source id：`nasa_exoplanet_archive.ps`、`nasa_exoplanet_archive.toi` 和 `nasa_exoplanet_archive.pscomppars`。不得为 API 粒度另建第二套来源注册表。

table source 的选择顺序和字段适用范围直接读取 Field Manifest 的 `source_priority` 与 `source_aliases`，README 不复制这些字段事实。优先级不能静默删除低优先级原值；C-04 按 Manifest 策略选择展示 canonical value，同时保留全部来源值、冲突和 Transformation Evidence。完整运行规则见 [Versioned Data Artifacts](../../../docs/engineering/VERSIONED_DATA_ARTIFACTS.md)。

## 6. 规则声明

- 来源 alias 的唯一性范围为 `(source_id, source_table, raw_field)`；同一原始列不得指向两个 canonical field。
- 每个 alias 的 raw、误差、limit、row key、reference 和 provenance 列必须属于对应 `SourceDefinition.approved_columns`；角色列还必须匹配该来源的角色 allowlist。
- 官方定义存在但 live TAP_SCHEMA 暂缺的列只能依据版本化裁决保留，不能因单次 live 查询删除；live-only 列也不能未经官方定义或裁决直接加入。
- 定量字段必须引用已注册 canonical unit；每个允许源单位必须与 canonical unit 具有相同 `quantity_kind`，并声明 conversion rule id。
- 字符串、标识和分类字段使用显式 `none` 单位定义，不用空字符串表示“无单位”。
- 正负误差分别声明，不把缺失误差解释为零误差。
- upper/lower limit 使用来源 limit flag 规则声明，不把极限值解释为常规测量。
- display name 只能参与 alias matching；唯一身份必须由 TOI/TIC/Gaia 标识或经审查的组合键确定。
- coordinate matching 只声明所需字段和规则版本，阈值与算法由 C-03 实现。
- Evidence locator 至少要求 `source_snapshot_id`、`query_hash`、`row_key`、`raw_field` 和来源 reference locator（若来源提供）。
- transformation rule 只保存不可变规则 id/version；C-01 不包含执行代码。
- quality metric inputs 只声明字段参与 `completeness`、`missingness`、`conflict`、`unit_consistency`、`evidence_coverage` 或 `crossmatch_coverage`，不计算分数。

## 7. 稳定 hash

Manifest hash 使用 `sha256:<64 lowercase hex>`：

1. Pydantic 校验通过后，以 JSON mode 序列化；
2. 从顶层排除 `content_hash`；
3. 对对象 key 稳定排序，数组顺序保持 Manifest 声明顺序；
4. 使用 UTF-8、无 BOM、紧凑分隔符和明确 ISO 8601 日期编码；
5. 对所得字节计算 SHA-256。

hash 标识内容，不替代 `case_id`、`manifest_id` 或 `manifest_version`。任何字段语义、来源别名、单位或规则变化都必须提升 Manifest 版本并更新变更记录。

## 8. 校验和消费方式

Schema/模型校验必须覆盖：

- schema/manifest version 和 hash 格式；
- Case 与 Field Manifest 的 case、版本和 hash 引用一致；
- canonical field id、来源 alias 和注册表 id 不重复；
- Case 的 provider source id 可由现有 `SourceDefinition` 稳定解析到 table source id，不存在第二套映射注册表；
- 来源 allowlist、row key、reference/provenance companion column 与固定裁决记录一致；
- canonical/allowed source unit 存在且 quantity kind 可转换；
- source priority、uncertainty、limit、Evidence、transformation 和 quality 引用均已定义；
- `ResearchContract.requested_fields` 非空、只接受当前 Case Manifest 中的 canonical field id；
- 来源 alias（例如 `pl_rade`）不能冒充 `requested_fields` canonical id。

## 9. 维护规则

- C-01 初始版本由 C 负责人维护，X-00 只做跨模块集成冻结。
- 修改字段事实必须关联 Issue，并同步 `CHANGELOG.md`、版本和 hash。
- C-02～C-05、B-04、A-03 和 D/X 消费方必须固定 manifest version/hash；不得读取动态“latest”作为可复现输入。
- Fixture 可以引用 Manifest，但必须另带 fixture/scenario/schema/provenance 标记；Manifest 本身不是 Fixture、Live 或 Cached 数据结果。
