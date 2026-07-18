# C-01 Case / Field Manifest

## 1. 范围

本目录保存主案例 `exoplanet_host_star` 的版本化、机器可读数据事实源。C-01 只冻结字段、单位、来源别名、冲突、缺失、误差、上下限、对象标识、crossmatch 与 Evidence locator 规则，不执行数据获取、实体匹配、单位换算或质量评分。

主案例面向 TESS 系外行星候选体及其宿主恒星。当前字段语义以项目架构文档和 NASA Exoplanet Archive 的官方表定义为依据：

- [TESS Objects of Interest 表定义](https://exoplanetarchive.ipac.caltech.edu/docs/API_TOI_columns.html)
- [Planetary Systems / PSCompPars 表定义](https://exoplanetarchive.ipac.caltech.edu/docs/API_PS_columns.html)
- [TAP 使用说明](https://exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html)

## 2. 唯一事实源与目录边界

- `services/data_pipeline/manifests/exoplanet_host_star/` 保存 Case Manifest 和 Field Manifest 数据。
- `apps/api/src/app/schemas/manifest.py` 是 Pydantic v2 Schema authoring source，只定义结构、稳定 hash 和静态校验，不新增 API 端点。
- `packages/schemas/generated/` 只保存现有导出脚本生成的 JSON Schema，不手写第二套生产 Schema。
- `packages/domain`、`packages/contracts`、前端和 Pipeline 运行时代码只能按版本引用 Manifest，不复制字段清单。
- `/api/v1` 现有 Mock 字段保持兼容；目标 `/api/v2` 的 `ResearchContract.requested_fields` 使用 canonical field id，不使用来源列名。

## 3. Manifest 拆分

### Case Manifest

Case Manifest 至少包含：

- `case_id`、中英文名称和描述；
- `schema_version`、`manifest_version`、`content_hash`、`maintained_at` 和维护责任；
- 支持的对象类型、默认请求字段和允许来源；
- 对 Field Manifest 的不可漂移引用（manifest id、版本和 hash）；
- 对象 identity/crossmatch 规则与最低 Evidence locator 要求。

### Field Manifest

Field Manifest 至少包含：

- `manifest_id`、`case_id`、版本、hash 和维护信息；
- 受控来源、单位和规则标识注册表；
- 完整字段定义列表；
- 每个字段的来源别名、来源优先级、冲突策略、缺失/误差/上下限、身份与匹配、Evidence、转换版本及质量指标输入。

Case Manifest 通过版本和 hash 引用 Field Manifest；两份文件分别计算 hash，避免循环引用。

## 4. 冻结字段范围

`required` 表示字段必须存在于默认 Dataset/FieldDictionary 的列定义中；`nullable` 表示单条科学记录可以为空。`required=true` 与 `nullable=true` 可以同时成立，但空值必须携带受控 `null_reason`，不得以默认数值代替观测缺失。

| canonical field id | 中文含义 | canonical unit | required | nullable | 角色 |
| --- | --- | --- | --- | --- | --- |
| `planet.toi_id` | TESS 候选体标识 | `none` | 是 | 否 | 候选体主标识、exact crossmatch |
| `planet.name` | 行星常用名称 | `none` | 否 | 是 | 显示/别名，不作为唯一标识 |
| `planet.disposition` | 候选体处置状态 | `none` | 是 | 是 | 候选/确认/误报语义 |
| `star.tic_id` | TIC 宿主恒星标识 | `none` | 是 | 否 | 宿主恒星主标识、exact crossmatch |
| `star.gaia_dr3_id` | Gaia DR3 宿主恒星标识 | `none` | 否 | 是 | 外部目录标识、exact crossmatch |
| `star.name` | 宿主恒星常用名称 | `none` | 否 | 是 | 显示/alias crossmatch，不作为唯一标识 |
| `system.right_ascension` | 系统赤经 | `degree` | 是 | 否 | coordinate crossmatch |
| `system.declination` | 系统赤纬 | `degree` | 是 | 否 | coordinate crossmatch |
| `planet.orbital_period` | 行星轨道周期 | `day` | 是 | 是 | 核心科研参数 |
| `planet.radius` | 行星半径 | `earth_radius` | 是 | 是 | 核心科研参数 |
| `planet.mass` | 行星质量或最佳质量估计 | `earth_mass` | 是 | 是 | 核心科研参数，必须保留质量 provenance |
| `star.effective_temperature` | 恒星有效温度 | `kelvin` | 是 | 是 | 核心宿主恒星参数 |
| `star.metallicity` | 恒星金属丰度 | `dex` | 是 | 是 | 核心宿主恒星参数 |
| `star.radius` | 恒星半径 | `solar_radius` | 是 | 是 | 核心宿主恒星参数 |
| `star.mass` | 恒星质量 | `solar_mass` | 是 | 是 | 核心宿主恒星参数 |

字段不覆盖其他天文方向，也不加入仅为页面展示服务的派生字段。

## 5. 来源和优先级声明

C-01 只声明来源元数据和选择规则，不访问来源：

1. `nasa_exoplanet_archive.ps`：有文献引用、同一参数集的 published planet/host solution；存在匹配记录时优先用于对应字段。
2. `nasa_exoplanet_archive.toi`：TESS 候选体、TIC 身份、处置状态和候选体参数的主来源。
3. `nasa_exoplanet_archive.pscomppars`：提高字段完整性的后备来源；其跨文献组合特性必须在 provenance 和冲突结果中保留。

优先级不能静默删除低优先级原值。C-04 后续只能按本 Manifest 的策略选择 canonical value，同时保留全部来源值和 Evidence。

## 6. 规则声明

- 来源 alias 的唯一性范围为 `(source_id, source_table, raw_field)`；同一原始列不得指向两个 canonical field。
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
- canonical/allowed source unit 存在且 quantity kind 可转换；
- source priority、uncertainty、limit、Evidence、transformation 和 quality 引用均已定义；
- `ResearchContract.requested_fields` 非空、只接受当前 Case Manifest 中的 canonical field id；
- 来源 alias（例如 `pl_rade`）不能冒充 `requested_fields` canonical id。

## 9. 维护规则

- C-01 初始版本由 C 负责人维护，X-00 只做跨模块集成冻结。
- 修改字段事实必须关联 Issue，并同步 `CHANGELOG.md`、版本和 hash。
- C-02～C-05、B-04、A-03 和 D/X 消费方必须固定 manifest version/hash；不得读取动态“latest”作为可复现输入。
- Fixture 可以引用 Manifest，但必须另带 fixture/scenario/schema/provenance 标记；Manifest 本身不是 Fixture、Live 或 Cached 数据结果。
