# Versioned Data Artifacts

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | C-04 字段映射、单位统一、Transformation Evidence 与 typed Artifact candidate 运行规范 |
| Issue | [#34](https://github.com/zyyyyynnn/xingwen-astro-ai/issues/34) |

## 1. 范围与边界

C-04 消费已经完成的 TOI/PS acquisition 投影与 C-08 `CrossmatchResult`，按冻结 Manifest 生成 `DatasetArtifactCandidate`、`FieldDictionaryArtifactCandidate` 和 `SourceCollectionArtifactCandidate`。公共入口是：

```python
build_data_artifact_candidates(
    input: DataArtifactBuildInput,
) -> DataArtifactBuildResult
```

实现位于 `services/data_pipeline/data_artifacts/`，唯一 Pydantic 编写源位于 `apps/api/src/app/schemas/data_artifacts.py`。C-04 不访问 NASA endpoint，不重新运行 Adapter/Crossmatch，不访问数据库，不分配 `ArtifactVersion`，不推进 Run，不发布 HTTP DTO，也不计算 C-05 质量分。

## 2. 输入与冻结策略

`DataArtifactBuildInput` 绑定 Case/Field Manifest pins、左右 acquisition 的 records/Snapshot/mode/data level/completion、C-08 结果、requested canonical fields、`MappingRuleSet`、`UnitConversionCatalog`、producer version、可选质量约束引用和稳定 `input_hash`。左右来源、Snapshot、record set、row key 与 raw-record hash 必须与 C-08 引用精确一致；来源列名不能冒充 canonical field ID。

当前规则文件位于 `services/data_pipeline/manifests/exoplanet_host_star/mapping-rules/`：

- `mapping-rules.v1.json`：执行顺序、冲突/缺失策略、数值比较和容量边界；不复制字段 alias、priority、unit 或 companion columns。
- `unit-conversions.v1.json`：Manifest declaration-only conversion 的唯一执行因子目录。

Field alias、source priority、alias priority、null、uncertainty、limit、unit 和质量输入只读取 Field Manifest。`pscomppars` 虽在 Manifest 中声明，但没有 acquisition/C-08 member 时不会产生伪造来源值。

## 3. 数值与单位

换算使用 `Decimal`、28 位精度、`ROUND_HALF_EVEN` 上下文和无指数 plain-decimal JSON 字符串；不进行隐式量化。初版只实现 Manifest 已授权的 identity、Jupiter radius → Earth radius、Jupiter mass → Earth mass。identity 要求来源/目标单位相同，所有规则同时核对 ID、版本、单位对和 quantity kind；NaN、Infinity、bool 与非法数字 fail closed。

半径与质量比例来自 [IAU 2015 Resolution B3](https://arxiv.org/abs/1510.07674) 的精确 nominal equatorial radii 与 nominal mass parameters：

- `71492000 / 6378100 = 11.20898073093868079835687744`
- `126686530000000000 / 398600400000000 = 317.8284065946747670097671753`

主值与 uncertainty 使用同一比例。catalog 保存 numerator、denominator、来源、版本和 content hash，Python 分支不复制常数。

## 4. 值、缺失、误差和 limit

每个 `SourceValueCandidate` 同时保留 raw/canonical value、单位、Snapshot/query/row/record/raw-field locator、source/alias priority、转换版本、reference/provenance 文本、uncertainty、limit、null status 和 content hash。reference/provenance 是不可信来源文本，不执行或解释为 HTML。

字段输出是 `mapped | declared_null | unresolved` 判别联合：

- nullable 且 raw field 为 null 时使用 Manifest 允许的 `not_measured`；来源没有适用 alias/value 时使用 `not_in_source`；
- 非 nullable 字段没有安全值时稳定失败，不填 0 或空字符串；
- review/rejected/conflict identity 不按 source priority 重新裁决，而是保留 unresolved 行；
- truncated/unknown 对侧的 `inconclusive` 不改写为 `unmatched`。

非对称 uncertainty 分别保留原始符号和转换值，单侧缺失不补 0；locator 可区分 companion 不在 record 与存在但为 null。limit 只解析 Manifest 的 `measured/lower_limit/upper_limit` flag，未知类型/值和无主值的 bound 稳定失败，换算后 limit 类型不变。

## 5. 选择、冲突与 Crossmatch 消费

每条 C-08 record 形成稳定 row。accepted paired/adjudication 可合并其全部 members；review-required、rejected、conflict-group 保留 member 与 C-08 Evidence 但不伪装为确定实体；unpaired 保留 entity level、completion scope 和 `unmatched | inconclusive`。对象 identity 字段直接消费 C-08 已验证的 normalized identity value，不重新运行 identity 算法；宿主恒星匹配不会推导 planet identity，多条 PS assertion 不折叠。

字段候选按 Field Manifest 的 source priority、alias priority、stable source-value ID 排序。最高优先级只决定展示值，所有低优先级值和 provenance 均保留；不同 canonical value 形成 `FieldConflictRecord`，并由 `FieldSelectionRecord` 记录策略与原因。identity conflict 不受字段 source priority 覆盖。

## 6. Evidence、候选与 hash

`TransformationEvidence` 将 dataset row/field/source value 绑定到 raw cell、uncertainty/limit/reference/provenance locator、conversion catalog、C-08 result/logical key/Evidence 和 selection 状态。三类 candidate 均携带两个 SourceSnapshot、Evidence 引用、Manifest/rule/catalog pins、producer、input/output hash，且仅原始 Pipeline 实例获得 instance-bound publication seal：

- Dataset：columns、rows、判别字段 outcome、全部 source values、Evidence、selection/conflict 和 C-05 metric input 声明；不含 quality score。
- FieldDictionary：requested fields 对 Field Manifest `FieldDefinition` 的精确投影。
- SourceCollection：mode/data level/completion、raw locators、alignment/conflict/review/inconclusive keys 与 license note。

稳定 hash 排除 wall-clock、日志、分支、数据库 ID、ArtifactVersion number 与 Publisher content hash。requested fields 和输出集合使用确定顺序；内容、规则、Manifest 或 conversion 版本变化会改变相应 hash。

## 7. Publisher 与 C-05 交接

C-04 生产模块不反向依赖 `app.workflow.publisher`。`services/data_pipeline/data_artifacts/admission.py` 提供 Evidence、domain、quality-prerequisite validators；API/B 边界将三个 sealed candidate 分别交给 #78 `admit_artifact_candidate(...)`。复制、重新解析、bundle intermediate、dict 或 free text 不能绕过 instance seal。该端口只生成 `AdmittedArtifactCandidate`，数据库发布事务与 `ArtifactVersion` 仍属于 #78/B。

C-05 #35 后续消费 Dataset 的 field outcomes、conflicts、Evidence coverage、Crossmatch status 和 `quality_metric_input_declarations` 计算质量；C-04 始终输出 `quality_evaluation_status=not_evaluated`。

## 8. 数据等级、限制与验证

集成回归使用 C-08 synthetic fixture，它不是科学 ground truth；TOI/PS acquisition 各自的 recorded response 回归继续独立运行。Fixture、recorded response、Live 与 Cached 不互换。本实现不运行公网 Live smoke，不提供 HTTP/DB/Run 接线，不裁决 unresolved identity，也不计算动态质量指标。

```powershell
Set-Location apps/api
uv run pytest tests/test_data_artifact_contract.py tests/test_field_mapping.py tests/test_unit_conversion.py tests/test_data_artifact_pipeline.py tests/test_data_artifact_publisher_port.py
uv run pytest -q

Set-Location ../..
python -m unittest scripts.test_check_foundation
python scripts/check_foundation.py
node scripts/check-versionless-api.mjs
node scripts/check-docs.mjs
git diff --check
```
