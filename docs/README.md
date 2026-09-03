# Documentation Index

| 元数据 | 值 |
| --- | --- |
| Authority | 文档地图与索引 |

星文智析文档按职责分区。每份文档只完整定义一个事实域；代码、生成 Contract 与测试描述实际实现，文档描述当前设计与约定。

## Product

| 事实域 | 文档 |
| --- | --- |
| 产品目标、主案例、能力范围与成功指标 | [PRD](../PRD.md) |
| 产品设计原则与体验不变量 | [Product Design](../DESIGN.md) |
| Workspace 信息架构与核心交互 | [Workspace UX](design/WORKSPACE_UX.md) |
| 品牌、Token、排版与视觉语言 | [Visual Language](design/VISUAL_LANGUAGE.md) |
| 竞赛赛道、合格模型资格与提交证据 | [Competition Compliance](product/COMPETITION_COMPLIANCE.md) |

## Architecture

| 事实域 | 文档 |
| --- | --- |
| 前端运行时与状态所有权 | [Frontend Architecture](architecture/FRONTEND_ARCHITECTURE.md) |
| 模块边界与依赖方向 | [Module Boundaries](architecture/MODULES.md) |
| HTTP 资源与传输契约 | [API Contract](architecture/API_CONTRACT.md) |
| 科学文档解析 | [Scientific Document Parsing Contract](architecture/SCIENTIFIC_DOCUMENT_PARSING_CONTRACT.md) |
| 领域实体与不变量 | [Data Model](architecture/DATA_MODEL.md) |
| Run/Step/Attempt/Event、lease、并发与恢复 | [Workflow Design](architecture/WORKFLOW_DESIGN.md) |
| ArtifactVersion、SourceSnapshot、ProducerExecution、Cache、Revision、Share | [Data Versioning](architecture/DATA_VERSIONING.md) |

## AI / Reasoning

| 事实域 | 文档 |
| --- | --- |
| 模型准入、调用记录与降级 | [Model Policy](ai/MODEL_POLICY.md) |
| Prompt Registry | [Prompt Registry](ai/PROMPT_REGISTRY.md) |
| Prompt 包结构与消费 | [Prompt Package](../packages/prompts/README.md) |
| Generated Schema 包与导出边界 | [Schema Package](../packages/schemas/README.md) |
| Evidence / Claim / Relation / ReasoningTrace | [Reasoning Protocol](ai/REASONING_PROTOCOL.md) |

## Engineering

| 事实域 | 文档 |
| --- | --- |
| 代码实现基础 | [Coding Standard](engineering/CODING_STANDARD.md) |
| 测试分层与真实性等级 | [Test Strategy](engineering/TEST_STRATEGY.md) |
| 跨源实体对齐 | [Cross-source Alignment](engineering/CROSS_SOURCE_ENTITY_ALIGNMENT.md) |
| 数据质量评估 | [Data Quality Evaluation](engineering/DATA_QUALITY_EVALUATION.md) |
| 主数据源获取 | [Data Source Acquisition](engineering/DATA_SOURCE_ACQUISITION.md) |
| 补充数据源获取 | [Supplemental Source Acquisition](engineering/SUPPLEMENTAL_SOURCE_ACQUISITION.md) |
| 数据 Artifact | [Data Artifacts](engineering/DATA_ARTIFACTS.md) |
| LiteratureClaim Pipeline | [LiteratureClaim Pipeline](engineering/LITERATURE_CLAIM_PIPELINE.md) |
| LiteratureRelation / ReasoningTrace Pipeline | [LiteratureRelation Pipeline](engineering/LITERATURE_RELATION_PIPELINE.md) |
| Evidence Graph Pipeline | [Evidence Graph Pipeline](engineering/GRAPH_PIPELINE.md) |
| PaperCollection / Summary acquisition | [PaperCollection Pipeline](engineering/PAPER_COLLECTION_PIPELINE.md) |

## Operations

| 事实域 | 文档 |
| --- | --- |
| 安全 | [Security](../SECURITY.md) |
| 部署 | [Deployment](../DEPLOYMENT.md) |
| 本地启动 | [Setup](setup.md) |
| 分支、交付与合并 | [Contributing](../CONTRIBUTING.md) |

`docs/references/**` 保存随仓库维护的外部规范材料说明。`tests/evidence/` 保存真实运行与竞赛提交的机器可读证据。
