<div align="center">

# 星文智析 AI 科研工具

_面向天文科研场景的数据分析、文献获取、跨文献推理与证据图谱工作流_

![Astro](https://img.shields.io/badge/Astro-7-BC52EE) ![React](https://img.shields.io/badge/React-19.2-149ECA) ![Vite](https://img.shields.io/badge/Vite-8.1-646CFF) ![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.13-009688) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791) ![Docker](https://img.shields.io/badge/Docker-Compose-2496ED) [![License: MIT](https://img.shields.io/badge/license-MIT-64748b)](LICENSE)

</div>

---

## 项目定位

星文智析围绕固定主案例 **系外行星候选体与宿主恒星参数整合**，建设一条可复现、可溯源、可展示的科研数据工作流：

```text
科研目标 -> 数据获取 -> 字段清洗 -> 论文获取 -> 文献理解 -> 跨文献推理 -> 证据图谱 -> 结果导出 -> 反馈修正
```

项目聚焦挑战杯“基于国产开源大模型的 AI Scientist 研发与应用”赛题中“科学数据查找、解析与整合”方向。MVP 不承诺任意天文方向、任意 PDF 全文高精度解析、任意图表全自动处理或无边界科学发现。

## 当前状态

| 范围       | 状态                                                                                        |
| ---------- | ------------------------------------------------------------------------------------------- |
| 前端运行时 | A-01 Implemented：Astro Brand Site、React Research Workspace、共享包与根 pnpm 工具链        |
| 最小入口   | Site `/`、静态 404；Workspace `/`、`/tour`、`/workspace`、`/share/$shareToken` 与 Not Found |
| API        | FastAPI `/api/v1` Current；`/api/v2` Project / Run / Artifact / Version Pending             |
| 产品界面   | A-02 视觉系统与静态框架、A-03 Contract 双通道与业务行为均 Pending                           |
| 本地环境   | Compose：`site`、`workspace`、`api`、`postgres`                                             |

A-01 页面只证明运行时、路由、可访问性和包边界，不包含真实 Project、Run、Artifact 或数据请求行为。完整工程事实见 [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md)。

## 快速开始

```powershell
Copy-Item .env.example .env
docker compose up --build --wait
```

| 服务               | 地址                                |
| ------------------ | ----------------------------------- |
| Brand Site         | `http://127.0.0.1:4321`             |
| Research Workspace | `http://127.0.0.1:5173`             |
| 后端 API           | `http://127.0.0.1:8000`             |
| API 文档           | `http://127.0.0.1:8000/api/v1/docs` |
| PostgreSQL         | `127.0.0.1:5432`                    |

前端本机调试从仓库根目录执行：

```powershell
corepack enable
corepack prepare pnpm@11.13.1 --activate
pnpm install --frozen-lockfile
pnpm dev
```

环境变量、后端命令和故障排查见 [docs/setup.md](docs/setup.md)。真实密钥只写入本地 `.env` 或部署平台 Secrets。

## 仓库结构

```text
apps/site                 Astro 静态品牌站
apps/workspace            React 科研工作台入口
apps/api                  FastAPI 后端
packages/design-tokens    A-01 基础 Token 导出
packages/ui               共享 React UI 公开入口
packages/domain           纯 TypeScript 领域边界
packages/contracts        Pydantic Contract 前端边界
packages/data-access      Repository 边界（实现 Pending）
packages/workspace-core   工作台编排边界（实现 Pending）
packages/visual-engine    视觉运行时边界（实现 Pending）
packages/testing          共享测试入口
services                  数据、论文与图谱 Pipeline
scripts                   架构、基建与 Schema 脚本
docs                      架构、产品、质量、交接文档
```

## 核心文档

| 唯一事实范围                           | 文档                                                                |
| -------------------------------------- | ------------------------------------------------------------------- |
| 用户、场景、范围、成功标准与产品主流程 | [PRD](PRD.md)                                                       |
| 产品设计总纲、体验域与系统边界         | [DESIGN](DESIGN.md)                                                 |
| 前端技术栈、目录、依赖与构建           | [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md) |
| HTTP 资源与传输契约                    | [API Contract](docs/architecture/API_CONTRACT.md)                   |
| 领域实体与不变量                       | [Data Model](docs/architecture/DATA_MODEL.md)                       |
| 本地启动与环境变量                     | [Setup](docs/setup.md)                                              |
| 产品退出标准                           | [Acceptance](docs/product/ACCEPTANCE.md)                            |
| PR 与发布检查                          | [Review Checklist](docs/quality/REVIEW_CHECKLIST.md)                |
| 文档治理                               | [Documentation Governance](docs/DOCUMENTATION_GOVERNANCE.md)        |
| Agent 执行纪律                         | [AGENTS](AGENTS.md)                                                 |

其他资料按任务类型从 [docs/README.md](docs/README.md) 定位。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
