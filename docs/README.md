# Docs Index

本目录只做索引，不复述各文档正文。新成员优先读“必读入口”，开发时按改动类型查对应文档。

## 必读入口

| 文档 | 用途 |
| --- | --- |
| [../README.md](../README.md) | 项目入口、MVP 能力、快速开始 |
| [../PRD.md](../PRD.md) | MVP 范围、用户、成功标准 |
| [../DESIGN.md](../DESIGN.md) | 系统架构、状态机、证据、缓存、UI 设计基线 |
| [../AGENTS.md](../AGENTS.md) | Agent 操作协议、协作红线、验证要求 |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Git、Issue、PR、合并流程 |

## 按任务查文档

| 任务 | 文档 |
| --- | --- |
| 本地启动 | [setup.md](setup.md) |
| 拆任务和排期 | [product/BACKLOG.md](product/BACKLOG.md), [product/ROADMAP.md](product/ROADMAP.md) |
| 判断是否完成 | [product/ACCEPTANCE.md](product/ACCEPTANCE.md), [quality/REVIEW_CHECKLIST.md](quality/REVIEW_CHECKLIST.md) |
| 查项目边界 | [product/PROJECT_CHARTER.md](product/PROJECT_CHARTER.md), [../PRD.md](../PRD.md) |
| 查模块职责 | [architecture/MODULES.md](architecture/MODULES.md), [../DESIGN.md](../DESIGN.md) |
| 改接口 | [architecture/API_CONTRACT.md](architecture/API_CONTRACT.md) |
| 改数据结构 | [architecture/DATA_MODEL.md](architecture/DATA_MODEL.md) |
| 查架构决策 | [architecture/DECISIONS.md](architecture/DECISIONS.md) |
| 查风险 | [quality/RISK_REGISTER.md](quality/RISK_REGISTER.md) |
| 部署和安全 | [../DEPLOYMENT.md](../DEPLOYMENT.md), [../SECURITY.md](../SECURITY.md) |
| 查参考资料 | [references/README.md](references/README.md), [references/赛题要求.md](references/赛题要求.md) |
| 材料交接 | [handoff/README.md](handoff/README.md) |

## 推荐阅读顺序

1. `README.md`
2. `PRD.md`
3. `DESIGN.md`
4. `AGENTS.md`
5. `CONTRIBUTING.md`
6. `docs/setup.md`
7. 当前 Issue 对应的契约文档

## 维护原则

- 不新增无明确消费者的文档。
- 改接口必须同步 `API_CONTRACT.md`。
- 改数据结构必须同步 `DATA_MODEL.md`。
- 改 UI 基线必须同步 `DESIGN.md` 和 `REVIEW_CHECKLIST.md`。
- 未实现能力只能写为规划、预留或后续扩展。
