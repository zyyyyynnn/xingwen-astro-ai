# Manifest Changelog

## exoplanet_host_star 1.0.1 — 2026-07-19

- 统一 Case/Field Manifest 审计元数据为 `created_at` 和 `maintained_by`，旧字段由 Schema 拒绝。
- 固化 NASA Exoplanet Archive 官方列定义、live TAP_SCHEMA 双重观测与逐列裁决证据。
- 为既有 `SourceDefinition` 增加 provider/table 映射、来源列 allowlist、角色列约束和裁决记录引用。
- 删除官方定义与重复 live metadata 均不支持的 `pscomppars.rowupdate`；保留官方定义支持但 live TAP_SCHEMA 暂缺的 PS/PSCompPars 坐标误差列。
- 将 Case/API provider source id `nasa_exoplanet_archive` 稳定解析到既有 `ps`、`toi`、`pscomppars` table source id，不新增来源注册表。
- 本版本仍只提供 C-01 静态契约，不包含 Adapter、抓取、crossmatch、单位转换、质量评分或 Artifact Pipeline。

## exoplanet_host_star 1.0.0 — 2026-07-18

- 冻结 `exoplanet_host_star` Case Manifest 1.0.0。
- 冻结包含 15 个 canonical field 的 Field Manifest 1.0.0。
- 声明 NASA Exoplanet Archive `ps`、`toi` 与 `pscomppars` 来源 alias。
- 声明单位、缺失、误差、上下限、冲突、identity/crossmatch、Evidence locator、转换规则版本和质量指标输入。
- 本版本只提供 C-01 静态契约，不包含数据获取、跨源匹配、单位换算或质量评分实现。
