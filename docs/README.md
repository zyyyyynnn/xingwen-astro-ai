# Documentation Index

| 元数据    | 值                               |
| --------- | -------------------------------- |
| Status    | Accepted                         |
| Authority | 文档地图、唯一事实来源与文档类型 |

本文件是仓库文档的完整索引。文档层级、状态、合并、拆分和归档规则见 [Documentation Governance](DOCUMENTATION_GOVERNANCE.md)。

## 1. L0：入口

| 文档                             | 职责                                       |
| -------------------------------- | ------------------------------------------ |
| [README](../README.md)           | 项目定位、当前状态、快速启动和最小文档入口 |
| [Documentation Index](README.md) | 完整文档地图和权威边界                     |

入口文档只提供摘要和导航，不维护完整规范正文。

## 2. L1：核心规范

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

## 3. L2：专项规范

### Product experience

| 文档                                                           | Authority                                              |
| -------------------------------------------------------------- | ------------------------------------------------------ |
| [Visual Language](design/VISUAL_LANGUAGE.md)                   | 品牌、Token、字体、ASCII/Dither、动效和视觉降级        |
| [Workspace UX](design/WORKSPACE_UX.md)                         | Brand Site、Guided Tour、Workspace、面板和具体交互     |
| [Frontend Architecture](architecture/FRONTEND_ARCHITECTURE.md) | Astro/React Monorepo、包边界、数据访问、构建和质量门禁 |

### AI and reasoning

| 文档                                           | Authority                                  |
| ---------------------------------------------- | ------------------------------------------ |
| [Model Policy](ai/MODEL_POLICY.md)             | 模型调用准入、记录、降级与评测             |
| [Prompt Versioning](ai/PROMPT_VERSIONING.md)   | Prompt 不可变版本、registry 和发布流程     |
| [Reasoning Protocol](ai/REASONING_PROTOCOL.md) | Claim、Relation、ReasoningTrace 准入与修订 |

### Engineering, security and deployment

| 文档                                              | Authority                                |
| ------------------------------------------------- | ---------------------------------------- |
| [Coding Standard](engineering/CODING_STANDARD.md) | 代码组织、命名和基础实现规范             |
| [Error Handling](engineering/ERROR_HANDLING.md)   | 内部错误分类、公开错误和日志关联         |
| [Test Strategy](engineering/TEST_STRATEGY.md)     | 测试分层、数据等级、环境和测试证据       |
| [Security](../SECURITY.md)                        | 密钥、输入、会话、分享、日志和安全要求   |
| [Deployment](../DEPLOYMENT.md)                    | 环境拓扑、配置、迁移、健康检查和发布验证 |
| [Local Setup](setup.md)                           | 当前本地启动、测试命令和故障排查         |

## 4. L3：执行治理

| 文档                                                    | 职责                                            |
| ------------------------------------------------------- | ----------------------------------------------- |
| [AGENTS](../AGENTS.md)                                  | Agent 执行顺序、修改纪律、Git 安全和最低验证    |
| [Contributing](../CONTRIBUTING.md)                      | Git、Issue、PR、Review 和合并流程               |
| [Roadmap](product/ROADMAP.md)                           | 里程碑结果、顺序和阶段退出门                    |
| [Backlog](product/BACKLOG.md)                           | Issue 范围与依赖地图；GitHub Issue 保存实时状态 |
| [Acceptance](product/ACCEPTANCE.md)                     | 里程碑与发布退出标准及所需证据                  |
| [Review Checklist](quality/REVIEW_CHECKLIST.md)         | 单个 PR 的审查清单                              |
| [Risk Register](quality/RISK_REGISTER.md)               | 有效风险、影响、触发条件和缓解措施              |
| [Handoff](handoff/README.md)                            | 唯一作品提交顺序和材料 provenance 要求          |
| [Documentation Governance](DOCUMENTATION_GOVERNANCE.md) | 文档层级、状态、生命周期和质量门禁              |

## 5. 包级文档与生成物

| 文档                                                    | 类型                | 说明                               |
| ------------------------------------------------------- | ------------------- | ---------------------------------- |
| [Prompt Registry README](../packages/prompts/README.md) | Package operational | Prompt 文件结构和 registry 用法    |
| [Schema README](../packages/schemas/README.md)          | Package operational | 当前 Schema 导出与消费边界         |
| `packages/prompts/*/vN.md`                              | Versioned artifact  | 不可变 Prompt 内容，不重复项目规范 |

## 6. L4：参考资料

| 文档                                                          | 类型            | 使用限制                         |
| ------------------------------------------------------------- | --------------- | -------------------------------- |
| [Competition Requirements](references/赛题要求.md)            | Reference       | 外部要求，不直接定义内部实现     |
| [Reference Materials](references/README.md)                   | Reference index | 第三方论文、代码和摘要，仅供研究 |

参考代码和论文必须先被 L1/L2 规范明确采纳，才能成为实现约束。

## 7. 按任务定位

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

## 8. 维护要求

- 新文档必须有明确 Authority、消费者和更新触发。
- 同一事实只在一个文档完整定义，其他文件只摘要并链接。
- 新增、移动、合并、归档或删除文档必须同步本索引。
- 目标规范必须明确 Implementation 状态；参考和历史文档不得伪装为当前事实。
- 文档 PR 必须执行链接、标题、代码块、表格、Mermaid 和索引覆盖检查。
