# Reference Materials

本目录保存赛题要求、第三方参考代码、研究摘要和来源审计记录，仅用于比较、调研和形成设计输入，不定义当前产品或实现规则。任何规则必须先进入对应的当前 Authority，才能成为实现依据。

## 内容

```text
docs/references/
├─ README.md
├─ 赛题要求.md
├─ INTEGRATION_TRACEABILITY.md
├─ autoastro/           derived summary + selected code
├─ mavis/               derived summary（含安全审计与项目边界）
└─ inosum/              derived summary + selected code
```

## 使用原则

- 优先直接复用质量合格的源码或官方稳定 package；接口、目录与状态所有权仍按当前领域模型定向改造。
- 参考代码的模型、依赖、许可、安全和数据来源必须独立审查。
- 第三方示例中的 Prompt、工具调用、错误处理和缓存策略不能直接视为适合本项目。
- 任何涉及模型迁移的改动必须经过 Model Policy、Prompt Registry、Schema 和 Evidence 验证。
- 外部 API、论文来源和数据源的访问方式、许可、配额和可用性需要在实施时重新核验。
- 参考资料中的结果不得被包装为星文智析的真实运行结果。

## 与当前模块的可能关联

| 参考      | 可研究方向                         | 当前 Authority                                   |
| --------- | ---------------------------------- | ------------------------------------------------ |
| AutoAstro | 数据获取、对象匹配、分析任务组织   | Data Model、Module Boundaries                    |
| mavis     | 天文工具封装、可视化与交互模式     | Frontend Architecture、Workspace UX、Graph Pipeline |
| InnoSum   | 论文章节识别、结构化摘要和质量评估 | Model Policy、Prompt Registry、Reasoning Protocol |

当前采用状态与逐项代码落点见 [Reference Integration Traceability](INTEGRATION_TRACEABILITY.md)；表中未列出的参考结果不得被推断为当前能力。

## 赛题要求

[赛题要求.md](赛题要求.md) 是外部要求的仓库整理版。产品范围和提交口径仍由 PRD 与 Acceptance 负责；两者冲突时应先核对原始赛题材料，再通过 GitHub Issue 修改内部 Authority。

## 外部资料边界

当前目录只保留派生摘要、审计记录和选定代码。外部资料必须独立核验来源、许可和内容；摘要不能替代原始证据。
