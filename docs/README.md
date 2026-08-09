# Documentation Index

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 权威规范地图、文档治理规则与 Agent 默认读取规范 |

本文件是星文智析仓库权威规范的唯一地图与治理规则。Authority 定义稳定规则；
GitHub Issues/PRs 定义实时工作状态；代码、测试和真实运行定义实现事实。

## 1. 核心 Authority 索引

| 权威范围 | 唯一事实来源 | Status | Authority |
| --- | --- | --- | --- |
| 阶段目标与产品需求 | [PRD](../PRD.md) | Accepted | 用户、问题、产品范围、主流程、成功指标与非目标 |
| 竞赛方向、模型资格与提交证据 | [Competition Compliance](product/COMPETITION_COMPLIANCE.md) | Accepted | 固定赛道、Qwen 资格路径、调用证明与材料证据 |
| 体验域与设计原则 | [Product Design](../DESIGN.md) | Accepted | 产品设计原则、体验域关系与设计不变量 |
| 页面状态与交互规则 | [Workspace UX](design/WORKSPACE_UX.md) | Accepted | Workspace 信息架构、页面状态与核心交互 |
| 视觉风格与 Token | [Visual Language](design/VISUAL_LANGUAGE.md) | Accepted | 品牌、Token、字体、排版、密度与组件外观 |
| 前端架构与源码治理 | [Frontend Architecture](architecture/FRONTEND_ARCHITECTURE.md) | Accepted | 前端运行时、上游源码治理、模块分层与状态所有权 |
| 模块边界与依赖方向 | [Module Boundaries](architecture/MODULES.md) | Accepted | 模块职责、输入输出、依赖方向与跨模块交接 |
| HTTP 资源与传输契约 | [API Contract](architecture/API_CONTRACT.md) | Accepted | URL 资源、认证授权、Envelope、Problem Details 与演进 |
| 科学文档解析契约 | [Scientific Document Parsing Contract](architecture/SCIENTIFIC_DOCUMENT_PARSING_CONTRACT.md) | Accepted | Scientific Document Parsing 冻结契约、Parser Port、Golden Set、Benchmark 与上游采用边界 |
| 领域实体与不变量 | [Data Model](architecture/DATA_MODEL.md) | Accepted | 核心实体、实体关系、所有权与领域语义 |
| 运行状态与并发控制 | [Workflow Design](architecture/WORKFLOW_DESIGN.md) | Accepted | Run 状态机、Step、重试、取消与并发控制 |
| 版本、缓存与修订 | [Data Versioning](architecture/DATA_VERSIONING.md) | Accepted | ArtifactVersion、SourceSnapshot、CacheRecord 与 Revision |
| 模型准入与降级 | [Model Policy](ai/MODEL_POLICY.md) | Accepted | 模型调用准入、记录、降级与评测 |
| Prompt 管理 | [Prompt Versioning](ai/PROMPT_VERSIONING.md) | Accepted | Prompt 不可变版本、Registry 与运行引用 |
| Prompt Registry 包 | [Prompt Registry](../packages/prompts/README.md) | Accepted | packages/prompts 目录结构与本地使用方式 |
| Schema 包 | [Schema Package](../packages/schemas/README.md) | Accepted | Schema 导出与消费边界 |
| 证据准入与推导协议 | [Reasoning Protocol](ai/REASONING_PROTOCOL.md) | Accepted | Claim、Relation、ReasoningTrace 与 Graph 发布门 |
| 代码规范 | [Coding Standard](engineering/CODING_STANDARD.md) | Accepted | 代码组织、命名与实现基础 |
| 测试分层与证据 | [Test Strategy](engineering/TEST_STRATEGY.md) | Accepted | 测试分层、数据等级、环境与测试证据 |
| 跨源实体对齐 | [Cross-source Alignment](engineering/CROSS_SOURCE_ENTITY_ALIGNMENT.md) | Accepted | 跨源实体匹配、Evidences 与人工裁决 |
| 数据质量评估 | [Data Quality Evaluation](engineering/DATA_QUALITY_EVALUATION.md) | Accepted | 数据质量评估规则、指标与门禁 |
| 主数据源获取 | [Data Source Acquisition](engineering/DATA_SOURCE_ACQUISITION.md) | Accepted | 主数据源 TAP 获取与 Snapshot |
| 补充数据源获取 | [Supplemental Source Acquisition](engineering/SUPPLEMENTAL_SOURCE_ACQUISITION.md) | Accepted | 补充数据源获取与 Snapshot |
| 版本化数据产物 | [Versioned Data Artifacts](engineering/VERSIONED_DATA_ARTIFACTS.md) | Accepted | 数据产物构建、字段映射与转换证据 |
| 文献抽取 Pipeline | [LiteratureClaim Pipeline](engineering/LITERATURE_CLAIM_PIPELINE.md) | Accepted | LiteratureClaim 抽取、规范化与准入 |
| 文献推理 Pipeline | [LiteratureRelation Pipeline](engineering/LITERATURE_RELATION_PIPELINE.md) | Accepted | LiteratureRelation、ReasoningTrace 准入 |
| Versioned Evidence Graph Pipeline | [Graph Pipeline](engineering/GRAPH_PIPELINE.md) | Accepted | Graph 生成、Evidence-use、发布准入与渐进读取 |
| 文献检索 Pipeline | [PaperCollection Pipeline](engineering/PAPER_COLLECTION_PIPELINE.md) | Accepted | 论文检索、去重、排序与 Summary 准入 |
| 退出验收标准 | [Acceptance](product/ACCEPTANCE.md) | Accepted | 阶段与产品退出标准、一票否决项 |
| PR 审查清单 | [Review Checklist](quality/REVIEW_CHECKLIST.md) | Accepted | 单个 PR 的审查清单与合并条件 |
| 科学文档解析审查清单 | [Scientific Document Parsing Review](quality/SCIENTIFIC_DOCUMENT_PARSING_REVIEW.md) | Accepted | Scientific Document Parsing 人工审查：reference-after-rewrite、vendor 边界与采用完整性 |
| 安全要求 | [Security](../SECURITY.md) | Accepted | 密钥、信任边界、输入、会话、分享与日志要求 |
| 部署与运维 | [Deployment](../DEPLOYMENT.md) | Accepted | 环境拓扑、配置边界、迁移与健康检查 |
| 本地启动 | [Setup](setup.md) | Accepted | 本地与 Docker 启动方式、环境变量与调试命令 |
| Agent 执行协议 | [AGENTS](../AGENTS.md) | Accepted | Agent 执行协议与工作区安全约束 |
| 协作与 PR 流程 | [Contributing](../CONTRIBUTING.md) | Accepted | GitHub 分支、提交、PR、Review 与 Squash Merge |

第三方参考资料位于 [docs/references/](references/README.md)，仅作参考，不具有规范约束力。

## 2. Agent 默认读取规则

1. Agent 默认按 `AGENTS.md` 指定顺序读取，优先读取任务直接相关的 1–3 份 Authority 文档。
2. 严禁默认递归摄入全量 Markdown 文档、历史 Commit 或已关闭 PR。
3. 参考资料（`docs/references/`）不进入默认 Agent 读取路径。

## 3. 文档治理规则

1. **单一事实源**：一项事实只能有一个完整规范正文，其他文档仅提供相对链接或单行摘要。
2. **仅保留有效规范**：活跃文档只描述当前已批准且有效的规范，不记录历史方案、废弃过程或 ADR 比较。
3. ** Git 保存历史**：历史演进、废弃决策和迁移原因由 Git Commit 记录，不在活跃树保留 Superseded / Archive 文档。
4. **GitHub 保存状态**：任务实时状态、WIP 进度、Milestone 与依赖由 GitHub Issues / PRs 保存，不在 Markdown 维护 Backlog / Roadmap。
5. **不混淆实现与目标**：规范正文可以超前定义已批准但尚未代码实现的要求，
   但不得把 Draft/Open PR、Issue、Fixture、Benchmark、Recorded 或 Cached 写成 Current。
6. **禁止过程代号**：Accepted Authority 正文和元数据不保存 Issue/PR 编号、临时阶段
   代号、动态状态或个人本地路径；稳定版本、协议版本与外部标准编号可以保留。
7. **Authority 不保存进度**：不要写实现进度、已交付或待完成等状态断言；实时状态
   只在 GitHub，审计时使用不提交的 Truth Matrix。
8. **元数据一致性**：规范性 Authority 文档顶部必须包含 `Status: Accepted` 与 `Authority`；
   `docs/references/**` 必须保持 `Status: Reference` 且 `Authority` 不得成为生产事实源。
9. **边界与唯一性**：每个事实只有一个完整 Authority，其他文档只链接或作单行摘要；
   Domain、Repository、Workflow、Pipeline、Publisher 与 Versioning 边界不得在页面层重建。
10. **同步更新**：删除或移动 Markdown 文件时，必须同步更新本索引与相关相对链接。
