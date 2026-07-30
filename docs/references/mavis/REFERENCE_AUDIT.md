# MAVIS Reference Audit

| 元数据          | 值                                                                     |
| --------------- | ---------------------------------------------------------------------- |
| Status          | Reference                                                              |
| Authority       | MAVIS 参考事实、来源与再分发裁决记录                                   |
| Audit date      | 2026-07-30                                                             |
| Governance      | [Issue #152](https://github.com/zyyyyynnn/xingwen-astro-ai/issues/152) |
| Source snapshot | `mavis.local-reference.01f166d78b4a`                                   |

## 1. 结论

本次审计未找到足以证明 11 个 API JSON 或 MAVIS 学位论文 PDF 可由本仓库再分发的许可证据。当前树删除这 12 个副本，只保留非侵权的派生事实、原始位置、文件大小和 SHA-256。删除不改写 Git 历史。

| 资产类别     | 数量 | License status        | 裁决         |
| ------------ | ---: | --------------------- | ------------ |
| API JSON     |   11 | `unverified`          | 从当前树移除 |
| 学位论文 PDF |    1 | `not_redistributable` | 从当前树移除 |
| 仓库派生摘要 |    1 | `verified`            | 保留         |

逐文件记录见 [ASSET_MANIFEST.json](ASSET_MANIFEST.json)。

## 2. 审计范围与方法

### 2.1 稳定源快照身份

未找到可作为原始来源身份的 MAVIS ZIP，因此本次使用确定性 inventory hash：

| 字段                 | 值                                                                 |
| -------------------- | ------------------------------------------------------------------ |
| `snapshot_id`        | `mavis.local-reference.01f166d78b4a`                               |
| `inventory_sha256`   | `01f166d78b4ada735de0c701ef3209586776737e9fd16a2162184b0d1ae4b05f` |
| `file_count`         | `2289`                                                             |
| `audit_rule_version` | `1.0.0`                                                            |

inventory 对本地只读参考快照递归枚举文件，将相对路径统一为 `/`，排除 `node_modules`、`.git`、`.idea`、`__pycache__`、`.ipynb_checkpoints` 路径段，按 .NET `StringComparer.Ordinal` 比较相对路径、以字节数作为数值型次级排序键，并以 UTF-8（无 BOM）编码的 `<relative_path>\t<byte_length>\t<file_sha256_lowercase>\n` 计算 SHA-256。该规则不依赖系统区域设置，且会检测同长度内容变化。该 fingerprint 标识本次审计输入，不授予资产再分发权，也不证明源码可运行。

benchmark 的 160/99/59/2、89 个 `code/visual.py` 和 Prompt 4/11 统计及判定规则，以 [摘要的“已核验结构事实”](摘要.md#已核验结构事实) 为唯一维护口径；本审计不复制第二套统计定义。

### 2.2 审计对象与方法

审计对象：

- 本地只读 MAVIS 参考快照；物理路径仅记录在本地审计证据中；
- 曾位于 `docs/references/mavis/api/` 的 11 个 JSON；
- 曾位于 `docs/references/papers/mavis-天文可视化工具.pdf` 的 PDF；
- 仓库引入提交 `ef3231c6ce3e0e0771c1e048f9b3ef16c829abb3` 和 [PR #61](https://github.com/zyyyyynnn/xingwen-astro-ai/pull/61)；
- 当前派生摘要。

方法：

1. 对仓库副本和本地快照 `data/api_for_prompt` 原文件计算 SHA-256，确认 11 个仓库 JSON 与本地来源逐字节对应。
2. 检查 JSON 内容、参考快照根目录和引入 PR 中的许可证、作者授权、NOTICE 或来源记录。
3. 读取并渲染 PDF 的封面与末页权利声明，核对作者、机构和授权范围。
4. 只读统计 benchmark 目录和 `code/visual.py`，检查 Prompt 直接文件引用以及 agent10/11/12 的接线路径。
5. 不运行模型、Benchmark、Redis、Jupyter、WWT、WebSocket 或 MAVIS 网络请求。

## 3. 参考事实来源

Benchmark 分类、Prompt 的 4/11 加载关系、agent10/11/12 可达性、静默 no-op 和当前项目安全边界只在 [MAVIS 非规范参考摘要](摘要.md) 中定义。本审计只消费该事实集进行来源和再分发裁决，不重复维护第二份正文。

隔离安全化补丁和报告位于本地 `.artifacts/`，该目录被 Git 忽略；它们只用于证明原始文件未被覆盖以及危险默认路径已在隔离副本中禁用。

## 4. 再分发依据与裁决

### 4.1 11 个 API JSON

未找到以下任一可接受依据：

- 文件内许可证或版权声明；
- 本地快照根目录的 LICENSE、COPYING 或 NOTICE；
- 原仓库及其明确许可证；
- 作者对本仓库的授权；
- PR #61 中的来源 URL 或再分发授权记录。

“来自外部目录”“学术/竞赛用途”以及“未看到禁止条款”均不构成授权。因此这 11 个文件标记为 `unverified` 并从当前树移除。

### 4.2 学位论文 PDF

PDF 封面记录：

- 题名：`基于大语言模型的天文数据分析任务智能执行技术研究`
- 作者：谢家福
- 机构：贵州大学
- 日期：2026 年 06 月

末页权利声明表明相关知识产权归贵州大学，并授权贵州大学保存、向有关机构提交、供查阅借阅、纳入数据库以及采用复制手段保存和汇编。该声明没有授予本仓库公开再分发 PDF 的权利，引入 PR 也没有补充授权记录。因此该副本标记为 `not_redistributable` 并从当前树移除。

本裁决只判断本仓库当前能否证明再分发权，不判断作者或机构能否在其他渠道合法发布。

### 4.3 派生摘要

`摘要.md` 是本仓库依据结构统计和有限事实重新撰写的派生文档，不保留论文正文、JSON 内容或凭据值。它由仓库维护并可保留；其 SHA-256 记录在 manifest。

## 5. 复核与恢复

- 被删除副本仍可从 Git 历史定位；本次不改写历史。
- 若未来取得明确授权，应在独立 Issue 中记录授权主体、适用资产、许可证文本或授权凭证，再决定是否恢复。
- 若本地 MAVIS 快照、来源 URL 或资产哈希变化，必须重新审计，不能沿用本记录。
