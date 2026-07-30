# Documentation Index

| 元数据    | 值                               |
| --------- | -------------------------------- |
| Status    | Accepted                         |
| Authority | 文档地图、唯一事实来源与文档类型 |

本文件是仓库文档的完整索引。文档分类、状态、合并、拆分和归档规则见 [Documentation Governance](DOCUMENTATION_GOVERNANCE.md)。

## 1. 入口

| 文档                             | 职责                                 |
| -------------------------------- | ------------------------------------ |
| [README](../README.md)           | 项目定位、快速启动和最小文档入口     |
| [Documentation Index](README.md) | 完整文档地图和权威边界               |

入口文档只提供摘要和导航，不维护完整规范正文，不维护实现进度。

## 2. 规范

| 权威范围                                | 唯一事实来源                                        |
| --------------------------------------- | --------------------------------------------------- |
| 用户、问题、产品范围、主流程、成功指标  | [PRD](../PRD.md)                                    |
| 设计原则、体验域、交互模型              | [Product Design](../DESIGN.md)                      |
| HTTP 资源、传输结构、错误、授权         | [API Contract](architecture/API_CONTRACT.md)        |
| 领域实体、字段和不变量                  | [Data Model](architecture/DATA_MODEL.md)            |
| Run 状态、事件、取消、重试和派生        | [Workflow Design](architecture/WORKFLOW_DESIGN.md)  |
| ArtifactVersion、缓存、修订、分享和保留 | [Data Versioning](architecture/DATA_VERSIONING.md)  |
| 跨模块职责、输入输出和依赖              | [Module Boundaries](architecture/MODULES.md)        |
| 不可逆架构决策与替代关系                | [Architecture Decisions](architecture/DECISIONS.md) |

### 产品体验

| 文档                                                           | Authority                                              |
| -------------------------------------------------------------- | ------------------------------------------------------ |
| [Visual Language](design/VISUAL_LANGUAGE.md)                   | 品牌、Token、字体、ASCII/Dither、动效和视觉降级        |
| [Workspace UX](design/WORKSPACE_UX.md)                         | Brand Site、Guided Tour、Workspace、面板和具体交互     |
| [Frontend Architecture](architecture/FRONTEND_ARCHITECTURE.md) | Astro/React Monorepo、包边界、数据访问、构建和质量门禁 |

### AI 与推理

| 文档                                           | Authority                                  |
| ---------------------------------------------- | ------------------------------------------ |
| [Model Policy](ai/MODEL_POLICY.md)             | 模型调用准入、记录、降级与评测             |
| [Prompt Versioning](ai/PROMPT_VERSIONING.md)   | Prompt 不可变版本、registry 和发布流程     |
| [Reasoning Protocol](ai/REASONING_PROTOCOL.md) | Claim、Relation、ReasoningTrace 准入与修订 |

### 安全

| 文档                       | Authority                              |
| -------------------------- | -------------------------------------- |
| [Security](../SECURITY.md) | 密钥、输入、会话、分享、日志和安全要求 |

## 3. 工程与交付

| 文档                                                    | 职责                                            |
| ------------------------------------------------------- | ----------------------------------------------- |
| [AGENTS](../AGENTS.md)                                  | Agent 执行协议与项目约束                        |
| [Contributing](../CONTRIBUTING.md)                      | Git、Issue、PR、Review 和合并流程               |
| [Coding Standard](engineering/CODING_STANDARD.md)       | 代码组织、命名和基础实现规范                    |
| [Error Handling](engineering/ERROR_HANDLING.md)         | 内部错误分类、公开错误和日志关联                |
| [Test Strategy](engineering/TEST_STRATEGY.md)           | 测试分层、数据等级、环境和测试证据              |
| [Data Source Acquisition](engineering/DATA_SOURCE_ACQUISITION.md) | 主数据源查询、原始记录、失败语义与 SourceSnapshot |
| [Supplemental Source Acquisition](engineering/SUPPLEMENTAL_SOURCE_ACQUISITION.md) | 补充来源查询、录制响应、失败语义与独立 SourceSnapshot |
| [PaperCollection Pipeline](engineering/PAPER_COLLECTION_PIPELINE.md) | 论文检索、规范化、去重、排序与运行来源 |
| [Roadmap](product/ROADMAP.md)                           | 里程碑目标与顺序                                |
| [Backlog](product/BACKLOG.md)                           | Open Issue 角色与直接依赖索引；GitHub Issue 保存实时状态 |
| [Acceptance](product/ACCEPTANCE.md)                     | 阶段退出标准及所需证据                          |
| [Review Checklist](quality/REVIEW_CHECKLIST.md)         | 单个 PR 的审查清单                              |
| [Risk Register](quality/RISK_REGISTER.md)               | 有效风险、影响、触发条件和缓解措施              |
| [Deployment](../DEPLOYMENT.md)                          | 环境拓扑、配置、迁移、健康检查和发布验证        |
| [Local Setup](setup.md)                                 | 本地启动、测试命令和故障排查                    |
| [Handoff](handoff/README.md)                            | 唯一作品提交顺序和材料 provenance 要求          |
| [Documentation Governance](DOCUMENTATION_GOVERNANCE.md) | 文档分类、唯一事实来源规则与文档门禁            |

## 4. 包级文档与生成物

| 文档                                                    | 类型                | 说明                               |
| ------------------------------------------------------- | ------------------- | ---------------------------------- |
| [Prompt Registry README](../packages/prompts/README.md) | Package operational | Prompt 文件结构和 registry 用法    |
| [Schema README](../packages/schemas/README.md)          | Package operational | Schema 导出与消费边界              |
| `packages/prompts/*/vN.md`                              | Versioned artifact  | 不可变 Prompt 内容，不重复项目规范 |

## 5. 参考与归档

| 文档                                               | 类型            | 使用限制                         |
| -------------------------------------------------- | --------------- | -------------------------------- |
| [Competition Requirements](references/赛题要求.md) | Reference       | 外部要求，不直接定义内部实现     |
| [Reference Materials](references/README.md)        | Reference index | 第三方论文、代码和摘要，仅供研究 |
| [MAVIS Reference Summary](references/mavis/摘要.md) | Reference       | 已核验事实、许可裁决与项目边界   |

参考代码和论文必须先被规范文档明确采纳，才能成为实现约束。归档资料位于 `docs/archive/`，不作为实现依据。

## 6. 按任务定位

| 任务                         | 先查                                                   |
| ---------------------------- | ------------------------------------------------------ |
| 调整产品承诺或主流程         | PRD → Acceptance                                       |
| 修改首页、Tour 或 Workspace  | DESIGN → Workspace UX → Visual Language                |
| 修改前端目录、依赖或状态管理 | Frontend Architecture → Module Boundaries → ADR        |
| 修改 API、实体、状态或版本   | API Contract → Data Model → Workflow → Data Versioning |
| 修改模型、Prompt 或 Relation | Model Policy → Prompt Versioning → Reasoning Protocol  |
| 修改测试、错误或安全         | Test Strategy / Error Handling / Security              |
| 修改本地启动或部署           | Local Setup / Deployment                               |
| 拆任务、排期或判断完成       | Backlog / Roadmap / Acceptance                         |
| 准备提交材料                 | Handoff                                                |
| 新增、移动、合并或删除文档   | Documentation Governance                               |

## 7. 维护要求

- 新文档必须有明确 Authority、消费者和更新触发。
- 同一事实只在一个文档完整定义，其他文件只摘要并链接。
- 新增、移动、合并、归档或删除文档必须同步本索引。
- 参考和历史文档不得伪装为当前事实；实现进度由 GitHub Issues 与运行证据表达。
- 文档 PR 必须执行链接、标题、代码块、表格、Mermaid 和索引覆盖检查。
