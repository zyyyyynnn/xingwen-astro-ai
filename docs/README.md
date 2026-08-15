# Documentation Index

| 元数据 | 值 |
| --- | --- |
| Authority | 权威规范地图、文档治理规则与 Agent 默认读取规范 |

本文件是星文智析仓库规范 Authority 的唯一地图。列入下表的文档是 normative Authority；`docs/references/**` 仅是 non-normative Reference。Git 保存规范演进，GitHub Issues/PRs 保存工作状态，代码、测试与真实运行保存实现事实。

## 1. Authority Map

| 权威范围 | 唯一事实来源 | Authority |
| --- | --- | --- |
| 产品目标与需求 | [PRD](../PRD.md) | 用户、问题、产品范围、主流程、成功指标与非目标 |
| 竞赛方向、模型资格与提交证据 | [Competition Compliance](product/COMPETITION_COMPLIANCE.md) | 固定赛道、Qwen 资格路径、调用证明与材料证据 |
| 体验域与设计原则 | [Product Design](../DESIGN.md) | 产品设计原则、体验域关系与设计不变量 |
| 页面状态与交互规则 | [Workspace UX](design/WORKSPACE_UX.md) | Workspace 信息架构、页面状态与核心交互 |
| 视觉风格与 Token | [Visual Language](design/VISUAL_LANGUAGE.md) | 品牌、Token、字体、排版、密度与组件外观 |
| 前端架构与源码治理 | [Frontend Architecture](architecture/FRONTEND_ARCHITECTURE.md) | 前端运行时、上游源码治理、模块分层与状态所有权 |
| 模块边界与依赖方向 | [Module Boundaries](architecture/MODULES.md) | 模块职责、输入输出、依赖方向与跨模块交接 |
| HTTP 资源与传输契约 | [API Contract](architecture/API_CONTRACT.md) | URL 资源、认证授权、Envelope、Problem Details 与演进 |
| 科学文档解析契约 | [Scientific Document Parsing Contract](architecture/SCIENTIFIC_DOCUMENT_PARSING_CONTRACT.md) | Scientific Document Parsing、Parser Port、Golden Set、Benchmark 与上游采用边界 |
| 领域实体与不变量 | [Data Model](architecture/DATA_MODEL.md) | 核心实体、实体关系、所有权与领域语义 |
| 运行状态与并发控制 | [Workflow Design](architecture/WORKFLOW_DESIGN.md) | Run 状态机、Step、Attempt、lease、重试与并发控制 |
| 受控科学技能与分析产物 | [Bounded Scientific Skills](architecture/SCIENTIFIC_SKILLS.md) | 天文科学技能、分析/可视化/模型产物、资源预算与工具调用边界 |
| MAVIS 基准迁移台账 | [MAVIS Adoption Ledger](architecture/MAVIS_ADOPTION_LEDGER.md) | 160 例基准案例迁移范围、能力映射与 Live 验收门禁 |
| 产物与来源版本 | [Data Versioning](architecture/DATA_VERSIONING.md) | ArtifactVersion、SourceSnapshot、ProducerExecution、CacheRecord、修订、分享与哈希规则 |
| 模型准入与降级 | [Model Policy](ai/MODEL_POLICY.md) | 模型调用准入、记录、降级与评测 |
| Prompt 管理 | [Prompt Registry](ai/PROMPT_REGISTRY.md) | Prompt 当前定义、Registry、内容固定与运行引用 |
| Prompt Registry 包 | [Prompt Registry](../packages/prompts/README.md) | `packages/prompts` 目录结构与消费边界 |
| Schema 包 | [Schema Package](../packages/schemas/README.md) | Schema 导出与消费边界 |
| 证据准入与推导协议 | [Reasoning Protocol](ai/REASONING_PROTOCOL.md) | Claim、Relation、ReasoningTrace 与 Evidence Graph 发布门 |
| 代码规范 | [Coding Standard](engineering/CODING_STANDARD.md) | 代码组织、命名与实现基础 |
| 测试分层与证据 | [Test Strategy](engineering/TEST_STRATEGY.md) | 测试分层、数据等级、环境与测试证据 |
| 跨源实体对齐 | [Cross-source Alignment](engineering/CROSS_SOURCE_ENTITY_ALIGNMENT.md) | 跨源实体匹配、Evidence 与人工裁决 |
| 数据质量评估 | [Data Quality Evaluation](engineering/DATA_QUALITY_EVALUATION.md) | 数据质量评估规则、指标与门禁 |
| 主数据源获取 | [Data Source Acquisition](engineering/DATA_SOURCE_ACQUISITION.md) | 主数据源 TAP 获取与 SourceSnapshot |
| 补充数据源获取 | [Supplemental Source Acquisition](engineering/SUPPLEMENTAL_SOURCE_ACQUISITION.md) | 补充数据源获取与 SourceSnapshot |
| 数据产物 | [Data Artifacts](engineering/DATA_ARTIFACTS.md) | 字段映射、单位统一、Transformation Evidence 与 typed data Artifact candidate |
| 文献抽取 Pipeline | [LiteratureClaim Pipeline](engineering/LITERATURE_CLAIM_PIPELINE.md) | LiteratureClaim 抽取、规范化与准入 |
| 文献推理 Pipeline | [LiteratureRelation Pipeline](engineering/LITERATURE_RELATION_PIPELINE.md) | LiteratureRelation、ReasoningTrace 准入 |
| Evidence Graph Pipeline | [Evidence Graph Pipeline](engineering/GRAPH_PIPELINE.md) | Evidence Graph 生成、Evidence-use、发布准入与读取 |
| 文献检索 Pipeline | [PaperCollection Pipeline](engineering/PAPER_COLLECTION_PIPELINE.md) | PaperCollection benchmark runner、检索组件、去重、排序与 Summary 准入 |
| 退出验收标准 | [Acceptance](product/ACCEPTANCE.md) | 产品交付与发布退出标准、一票否决项 |
| PR 审查清单 | [Review Checklist](quality/REVIEW_CHECKLIST.md) | 单个 PR 的审查清单与合并条件 |
| 科学文档解析审查清单 | [Scientific Document Parsing Review](quality/SCIENTIFIC_DOCUMENT_PARSING_REVIEW.md) | Scientific Document Parsing 人工审查边界 |
| 安全要求 | [Security](../SECURITY.md) | 密钥、信任边界、输入、会话、分享与日志要求 |
| 部署与运维 | [Deployment](../DEPLOYMENT.md) | 环境拓扑、配置边界、migration 与健康检查 |
| 本地启动 | [Setup](setup.md) | 本地与 Docker 启动方式、环境变量与调试命令 |
| Agent 执行协议 | [AGENTS](../AGENTS.md) | Agent 执行协议与工作区安全约束 |
| 协作与 PR 流程 | [Contributing](../CONTRIBUTING.md) | GitHub 分支、提交、PR、Review 与 Squash Merge |

第三方参考资料位于 [docs/references/](references/README.md)，仅作参考，不具有规范约束力。

## 2. Agent 默认读取规则

1. Agent 按 `AGENTS.md` 指定顺序读取，优先读取任务直接相关的 1–3 份 Authority 文档。
2. 不默认递归摄入全量 Markdown、历史 Commit 或已关闭 PR。
3. `docs/references/**` 不进入默认 Authority 读取路径。

## 3. 文档治理规则

1. **结构决定角色**：列入本 Authority Map 的文档是 normative Authority；`docs/references/**` 是 non-normative Reference。Markdown 不维护生命周期 `Status`。
2. **单一事实源**：一项规范事实只有一个完整 Authority，其他文档仅提供相对链接或必要摘要。
3. **Git 保存演进**：活跃树只描述当前规则，不维护 Superseded/Archived 链、变更时间线或旧规则副本。
4. **GitHub 保存工作状态**：Issue、PR、依赖与实时进度不写入 Authority 元数据或正文。
5. **稳定元数据最小化**：仅在确有价值时使用 `Authority`、`Scope`、`Authoring source`、`Applies to`。
6. **禁止过程身份**：Authority 与活动源码不保存工作阶段代号、批次编号或伪版本名称；科研/技术版本、运行状态与外部精确版本保持其原有语义。
7. **边界唯一**：Domain、Repository、Workflow、Pipeline、Publisher 与 Versioning 规则不得在页面、Router 或文档副本中重建。
8. **同步更新**：移动或删除 Authority 时同步修改本 Map 与所有相对链接；Reference 不得成为生产事实源。
