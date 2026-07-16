# Documentation Governance

本文定义仓库文档的层级、事实归属、状态口径与维护责任。文档通过不能替代实现、测试或运行证据。

## 1. 文档层级

| 层级 | 作用 | 典型文件 |
| --- | --- | --- |
| L1 产品与操作协议 | 定义产品范围、设计总纲、Agent 与贡献规则 | `PRD.md`, `DESIGN.md`, `AGENTS.md`, `CONTRIBUTING.md` |
| L2 专项架构与设计 | 维护一个明确事实域的唯一正文 | `docs/architecture/*`, `docs/design/*` |
| L3 计划与验收 | 维护任务顺序、退出条件、风险与审查门禁 | `docs/product/*`, `docs/quality/*` |
| L4 运行与交付 | 维护启动、部署、安全与材料提交 | `docs/setup.md`, `DEPLOYMENT.md`, `SECURITY.md`, `docs/handoff/*` |
| L5 非规范性资料 | 提供赛题或第三方研究背景，不定义项目实现 | `docs/references/*` |

## 2. 一项事实一个正文来源

| 事实 | 唯一正文来源 |
| --- | --- |
| 用户、范围、成功标准、产品主流程 | `PRD.md` |
| 产品设计原则、体验域、系统边界 | `DESIGN.md` |
| 前端运行时、目录、依赖、构建 | `docs/architecture/FRONTEND_ARCHITECTURE.md` |
| 模块职责与依赖方向 | `docs/architecture/MODULES.md` |
| HTTP 资源与传输契约 | `docs/architecture/API_CONTRACT.md` |
| 实体与不变量 | `docs/architecture/DATA_MODEL.md` |
| Run 状态与编排 | `docs/architecture/WORKFLOW_DESIGN.md` |
| 版本、缓存、修订与分享 | `docs/architecture/DATA_VERSIONING.md` |
| 本地命令与环境变量 | `docs/setup.md` |
| 产品退出标准 | `docs/product/ACCEPTANCE.md` |

其他文档只链接或摘要，不复制完整规则。正文冲突时，先修正唯一来源，再同步消费者。

## 3. 状态口径

- **Current**：仓库当前存在且可定位的事实。
- **Implemented**：对应代码、测试与运行证据已经完成。
- **Pending**：已接受但尚未满足完成证据的能力。
- **Proposed**：仍需 Issue 或 ADR 确认的提案。

禁止仅因设计文档已写完就把能力标为 Implemented。混合状态的文档必须精确到模块或 Issue，例如“A-01 Implemented；A-02/A-03 Pending”。

## 4. 更新责任

| 变化 | 必须同步 |
| --- | --- |
| API、错误或授权 | `API_CONTRACT.md` |
| 实体、字段或枚举 | `DATA_MODEL.md` |
| Run 状态、重试、取消或派生 | `WORKFLOW_DESIGN.md` |
| Artifact、版本、缓存或分享 | `DATA_VERSIONING.md` |
| 前端目录、依赖或命令 | `FRONTEND_ARCHITECTURE.md`, `MODULES.md`, `docs/setup.md` |
| 产品范围或退出条件 | `PRD.md`, `ACCEPTANCE.md` |
| 风险或安全边界 | `RISK_REGISTER.md`, `SECURITY.md` |

PR 模板必须记录适用文档影响；不适用时明确勾选“无影响”。

## 5. 生命周期与删除

- 活跃文档只描述当前事实和有效规划，不重复 Git 已保存的实现历史。
- 内容被唯一正文完全吸收后，删除冗余文档并修正所有链接。
- 只有仍有审计或交付价值、且不会误导当前实现的材料才允许归档。
- 第三方资料必须标明非规范性，并保留来源、许可或用途说明。
- 失效的成员分工、工具版本、启动命令和技术选择不得以“仅供参考”继续留在活跃规范中。

## 6. 质量门禁

文档变更至少检查：

1. 相对链接可解析。
2. 命令与实际脚本一致。
3. Current / Implemented / Pending 与代码证据一致。
4. 没有第二份同名事实源。
5. 非规范性资料没有被引用为实现要求。
6. 目录删除后索引、README、Issue 与 PR 模板同步更新。
