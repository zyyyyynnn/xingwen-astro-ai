# Documentation Index

| 元数据 | 值 |
| --- | --- |
| Authority | 规范 Authority 地图、优先级与文档治理 |

本文件是星文智析规范体系的唯一地图。Authority 描述“当前应该是什么”；代码、生成 Contract、数据库、测试与真实运行描述“当前实际上是什么”；GitHub Issue/PR 描述“正在改变什么”。三者不得混为一份过程文档。

## 1. Authority Map

| 权威范围 | 唯一事实来源 |
| --- | --- |
| 产品目标、主案例、能力边界与差异化 | [PRD](../PRD.md) |
| 产品设计原则与体验不变量 | [Product Design](../DESIGN.md) |
| Workspace 信息架构与核心交互 | [Workspace UX](design/WORKSPACE_UX.md) |
| 品牌、Token、排版与视觉语言 | [Visual Language](design/VISUAL_LANGUAGE.md) |
| 前端运行时、OpenHands 源码治理与状态所有权 | [Frontend Architecture](architecture/FRONTEND_ARCHITECTURE.md) |
| 模块边界与依赖方向 | [Module Boundaries](architecture/MODULES.md) |
| HTTP 资源与传输契约 | [API Contract](architecture/API_CONTRACT.md) |
| 科学文档解析 | [Scientific Document Parsing Contract](architecture/SCIENTIFIC_DOCUMENT_PARSING_CONTRACT.md) |
| 领域实体与不变量 | [Data Model](architecture/DATA_MODEL.md) |
| Run/Step/Attempt/Event、lease、并发与恢复 | [Workflow Design](architecture/WORKFLOW_DESIGN.md) |
| ArtifactVersion、SourceSnapshot、ProducerExecution、Cache、Revision、Share | [Data Versioning](architecture/DATA_VERSIONING.md) |
| 模型准入、调用记录与降级 | [Model Policy](ai/MODEL_POLICY.md) |
| Prompt Registry | [Prompt Registry](ai/PROMPT_REGISTRY.md) |
| Prompt Registry package structure/consumption | [Prompt Package](../packages/prompts/README.md) |
| Generated Schema package/export boundary | [Schema Package](../packages/schemas/README.md) |
| Evidence / Claim / Relation / ReasoningTrace | [Reasoning Protocol](ai/REASONING_PROTOCOL.md) |
| 代码实现基础 | [Coding Standard](engineering/CODING_STANDARD.md) |
| 第三方能力迁移、吸收与深度集成 | [Reference Integration](engineering/REFERENCE_INTEGRATION.md) |
| 测试分层、真实性等级与证据 | [Test Strategy](engineering/TEST_STRATEGY.md) |
| 跨源实体对齐 | [Cross-source Alignment](engineering/CROSS_SOURCE_ENTITY_ALIGNMENT.md) |
| 数据质量评估 | [Data Quality Evaluation](engineering/DATA_QUALITY_EVALUATION.md) |
| 主数据源获取 | [Data Source Acquisition](engineering/DATA_SOURCE_ACQUISITION.md) |
| 补充数据源获取 | [Supplemental Source Acquisition](engineering/SUPPLEMENTAL_SOURCE_ACQUISITION.md) |
| 数据 Artifact | [Data Artifacts](engineering/DATA_ARTIFACTS.md) |
| LiteratureClaim Pipeline | [LiteratureClaim Pipeline](engineering/LITERATURE_CLAIM_PIPELINE.md) |
| LiteratureRelation / ReasoningTrace Pipeline | [LiteratureRelation Pipeline](engineering/LITERATURE_RELATION_PIPELINE.md) |
| Evidence Graph Pipeline | [Evidence Graph Pipeline](engineering/GRAPH_PIPELINE.md) |
| PaperCollection / Summary acquisition | [PaperCollection Pipeline](engineering/PAPER_COLLECTION_PIPELINE.md) |
| 竞赛赛道、Qwen 资格与提交证据 | [Competition Compliance](product/COMPETITION_COMPLIANCE.md) |
| 产品退出与一票否决 | [Acceptance](product/ACCEPTANCE.md) |
| Pull Request 正式审查 | [Review Checklist](quality/REVIEW_CHECKLIST.md) |
| 安全 | [Security](../SECURITY.md) |
| 部署 | [Deployment](../DEPLOYMENT.md) |
| 本地启动 | [Setup](setup.md) |
| Agent 执行协议 | [AGENTS](../AGENTS.md) |
| 分支、交付模式、Review 与合并 | [Contributing](../CONTRIBUTING.md) |

`docs/references/**` 只保存需要长期随仓库维护的外部材料说明，不是 normative Authority。第三方源码 archive/read-only checkout 是 Reference Integration 的审计输入，不因被本地提供或被某个 PR 使用而成为产品事实源。

## 2. 读取规则

Agent 默认顺序：

```text
AGENTS.md
→ 当前授权 / Issue / PR
→ docs/README.md
→ 直接相关的 1–4 份 Authority
→ current code / generated contract / tests / runtime evidence
```

不要默认递归读取所有 Markdown、历史 Commit、关闭 PR 或整个 Reference 源码。Reference Integration 任务例外：必须读取目标 Reference 的相关源码和当前 Xingwen 对应实现，形成 capability gap，而不是只读 README。

## 3. 冲突处理

- 用户明确改变交付策略时，先更新受影响 Authority，再继续大型实现。
- Authority 与生产代码冲突时，视为 drift；不能以“代码已经这样”自动覆盖规范，也不能以“文档写了”虚构实现已经存在。
- 当前产品/架构规则优先于历史测试、旧任务文本和关闭 PR 中的过时方案；需要的当前测试应随 Authority 一起更新。
- 一项稳定规则只在一个 Authority 中完整定义；其他文档用链接和必要摘要。

## 4. 文档治理

1. 活跃树只描述 current architecture，不维护 Superseded/Archived 说明链或历史规则副本。
2. GitHub 保存任务、进度、依赖、Review 与 delivery status；Authority 不写工作日志。
3. Issue 是原子任务契约；PR 默认原子交付，明确授权时可 Grouped Delivery，规则见 CONTRIBUTING。
4. 文档、代码、测试、fixture、Prompt 与 GitHub 文本不得使用内部一字母+整数版本/阶段简写；真实外部版本、科学版本和严重级别除外。
5. 改变公共 Contract、领域实体、Workflow、安全、UX、Reference Integration 或发布规则时，必须同步对应 Authority。
6. 新增 Authority 必须加入本 Map；没有独立稳定事实域时不要创建新 Authority。
7. 参考材料不能作为 production implementation 的动态依赖。
