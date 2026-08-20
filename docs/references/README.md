# Reference Materials

本目录仅保存需要长期随仓库维护的外部规范与赛题资料。

## 内容

```text
docs/references/
├─ README.md
└─ 赛题要求.md
```

## 边界

- 第三方 Reference 项目源码不 vendoring 到本仓库。
- 参考迁移的阶段性材料不进入 Git。
- 正式技术审查直接读取外部只读 Reference checkout。
- 产品规则由当前 Authority 文档和 production code 定义。

## 赛题要求

[赛题要求.md](赛题要求.md) 是外部要求的仓库整理版。产品范围和提交口径仍由 PRD 与 Acceptance 负责；两者冲突时应先核对原始赛题材料，再通过 GitHub Issue 修改内部 Authority。
