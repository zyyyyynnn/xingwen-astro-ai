# Docs Index

本目录仅提供文档索引。开发、审查或修改时，按任务类型定位对应事实来源。

## 按任务查文档

| 任务 | 文档 |
| --- | --- |
| 本地启动与 CI | [setup.md](setup.md), [engineering/TEST_STRATEGY.md](engineering/TEST_STRATEGY.md) |
| 拆任务和排期 | [product/BACKLOG.md](product/BACKLOG.md), [product/ROADMAP.md](product/ROADMAP.md) |
| 判断是否完成 | [product/ACCEPTANCE.md](product/ACCEPTANCE.md), [quality/REVIEW_CHECKLIST.md](quality/REVIEW_CHECKLIST.md) |
| 查项目边界 | [product/PROJECT_CHARTER.md](product/PROJECT_CHARTER.md), [../PRD.md](../PRD.md) |
| 查产品设计总纲、体验域、系统边界与专项规范入口 | [../DESIGN.md](../DESIGN.md) |
| 查模块职责 | [architecture/MODULES.md](architecture/MODULES.md) |
| 查目标前端架构 | [architecture/FRONTEND_ARCHITECTURE.md](architecture/FRONTEND_ARCHITECTURE.md) |
| 改品牌、Token、字体或 WebGL | [design/VISUAL_LANGUAGE.md](design/VISUAL_LANGUAGE.md) |
| 改首页、Guided Tour 或工作台 | [design/WORKSPACE_UX.md](design/WORKSPACE_UX.md) |
| 查任务编排 | [architecture/WORKFLOW_DESIGN.md](architecture/WORKFLOW_DESIGN.md) |
| 改接口 | [architecture/API_CONTRACT.md](architecture/API_CONTRACT.md) |
| 改数据结构 | [architecture/DATA_MODEL.md](architecture/DATA_MODEL.md) |
| 改版本/缓存治理 | [architecture/DATA_VERSIONING.md](architecture/DATA_VERSIONING.md) |
| 查架构决策 | [architecture/DECISIONS.md](architecture/DECISIONS.md) |
| 改模型调用 | [ai/MODEL_POLICY.md](ai/MODEL_POLICY.md) |
| 改 Prompt | [ai/PROMPT_VERSIONING.md](ai/PROMPT_VERSIONING.md), [../packages/prompts/README.md](../packages/prompts/README.md) |
| 改跨文献关系 | [ai/REASONING_PROTOCOL.md](ai/REASONING_PROTOCOL.md) |
| 查编码与错误规则 | [engineering/CODING_STANDARD.md](engineering/CODING_STANDARD.md), [engineering/ERROR_HANDLING.md](engineering/ERROR_HANDLING.md) |
| 查风险 | [quality/RISK_REGISTER.md](quality/RISK_REGISTER.md) |
| 部署和安全 | [../DEPLOYMENT.md](../DEPLOYMENT.md), [../SECURITY.md](../SECURITY.md) |
| 查参考资料 | [references/README.md](references/README.md), [references/赛题要求.md](references/赛题要求.md) |
| 材料交接 | [handoff/README.md](handoff/README.md) |

## 维护原则

- 不新增无明确消费者的文档。
- 改接口必须同步 `API_CONTRACT.md`。
- 改数据结构必须同步 `DATA_MODEL.md`。
- 改状态、步骤或编排必须同步 `WORKFLOW_DESIGN.md` 和测试。
- 改模型/Prompt/推理准入必须同步 `docs/ai/*`。
- 改体验域或系统边界同步 `DESIGN.md`；改 UI 细节同步对应专项设计文档和 `REVIEW_CHECKLIST.md`。
- 所有目标架构文档必须标明 Status、Implementation、Current runtime 和 Target runtime。
- 未实现能力只能写为规划、预留或后续扩展。
