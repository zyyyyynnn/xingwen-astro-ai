# Reference Materials

本目录只保存需要长期随仓库维护的外部规范说明；它不是 production Authority，也不承担第三方源码 vendoring。

## 长期材料

- [赛题要求.md](赛题要求.md)：外部赛题要求的仓库整理版。产品化解释由 PRD、Competition Compliance 与 Acceptance 负责。

## 第三方源码

第三方 Reference 源码可由用户通过本地 archive、只读 checkout 或其他审计输入提供。默认规则：

- 不因“源码可读”而成为生产事实源；
- 不默认把大体积 Reference archive 提交到 Git；
- 实现 Agent 必须读取相关源码而非只看 README，并与 current `main` 做 capability gap；
- 迁移后的稳定规则写入对应 Xingwen Authority，工作矩阵留在 PR；
- 源码级采用需要固定来源/revision、确认 license、保留必要 attribution/NOTICE；
- 未观察到明确 license 的 archive 不视为源码复制授权；
- 生产代码不得动态依赖本地 Reference checkout/archive。

Reference 的迁移、吸收、转化、anti-stitching 与验收规则统一见 [Reference Integration](../engineering/REFERENCE_INTEGRATION.md)。
