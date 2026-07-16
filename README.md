<div align="center">

# 星文智析 AI 科研工具

_面向天文科研场景的数据分析、文献获取、跨文献推理与证据图谱工作流_

![Vue](https://img.shields.io/badge/Vue-3-brightgreen) ![Vite](https://img.shields.io/badge/Vite-TypeScript-646CFF) ![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.13-009688) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791) ![Docker](https://img.shields.io/badge/Docker-Compose-2496ED) [![License: MIT](https://img.shields.io/badge/license-MIT-64748b)](LICENSE)

</div>

---

## 项目定位

星文智析围绕固定主案例 **系外行星候选体与宿主恒星参数整合**，提供一条可复现、可溯源、可展示的科研数据工作流：

```text
科研目标 -> 数据获取 -> 字段清洗 -> 论文获取 -> 文献理解 -> 跨文献推理 -> 证据图谱 -> 结果导出 -> 反馈修正
```

项目聚焦挑战杯“基于国产开源大模型的 AI Scientist 研发与应用”赛题中“科学数据查找、解析与整合”方向。MVP 不承诺任意天文方向、任意 PDF 全文高精度解析、任意图表全自动处理或无边界科学发现。

## 当前状态

| 范围 | 状态 |
| --- | --- |
| 当前可运行基线 | `apps/web` 前端骨架、FastAPI `/api/v1`、Docker Compose |
| 已接受目标 | 独立品牌站、科研工作台、共享前端包与 `/api/v2` Project / Run / Artifact / Version 契约 |
| 实施状态 | Pending；目标文档不表示迁移已完成，当前启动命令保持不变 |

目标前端采用品牌站、科研工作台和共享包分层，业务数据统一经 Repository Port 接入 Fixture 或 HTTP Adapter。完整技术栈、目录、依赖、构建和迁移规则只在 [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md) 维护；迁移完成前不得在新旧前端双写同一业务。

## MVP 能力

| 能力 | 交付物 | 验收重点 |
| --- | --- | --- |
| 自动化数据分析 | 标准化系外行星与宿主恒星数据集 | 字段对齐、单位统一、来源标注、质量评分 |
| 自动论文获取 | 主案例相关论文候选集与获取记录 | 检索参数、来源、去重、相关性排序、缓存标注 |
| 智能文献总结 | 自动获取论文的结构化综述 | 目标、方法、数据、结论、局限、引用证据可追踪 |
| 跨文献逻辑推理 | Claim、Relation、ReasoningTrace | 支持、补充、派生、限制或矛盾关系绑定证据 |
| 学术图谱可视化 | 论文、数据源、字段、发现和证据关系图谱 | 节点可定位，边绑定 Evidence，推理链可审查 |
| 反馈修正 | 字段、单位、来源、文献关系问题局部修正 | 新版本保留修订记录，不做无意义全流程重跑 |

## 快速开始

本地开发以当前 Docker Compose 基线为准：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://127.0.0.1:5173` |
| 后端 API | `http://127.0.0.1:8000` |
| API 文档 | `http://127.0.0.1:8000/api/v1/docs` |
| PostgreSQL | `127.0.0.1:5432` |

前端只使用 pnpm，后端只使用 uv：

```powershell
cd apps/web
corepack enable
pnpm install --frozen-lockfile
pnpm dev

cd ../api
uv sync --frozen
uv run uvicorn app.main:app --reload
```

环境变量、测试和故障排查见 [docs/setup.md](docs/setup.md)。真实密钥只写入本地 `.env` 或部署平台 Secrets。

## 仓库结构

```text
apps/web                  当前前端骨架
apps/api                  FastAPI 后端
services/data_pipeline    数据获取、清洗、字段对齐、导出
services/paper_pipeline   论文检索、获取、结构化总结
services/graph_pipeline   Claim、Relation、图谱和证据链构建
packages/schemas          共享 Schema
packages/prompts          生产 Prompt 注册表
samples                   可复现输入输出样例
scripts                   开发、验证、导出脚本
docs                      架构、产品、质量、交接文档
```

目标迁移目录尚未建立；当前仓库结构和启动方式以实际文件与 [docs/setup.md](docs/setup.md) 为准。

## 核心文档

| 唯一事实范围 | 文档 |
| --- | --- |
| 用户、场景、范围、成功标准与产品主流程 | [PRD](PRD.md) |
| 产品设计总纲、体验域、系统边界与专项规范入口 | [DESIGN](DESIGN.md) |
| 品牌、颜色、字体、视觉引擎与动效 | [Visual Language](docs/design/VISUAL_LANGUAGE.md) |
| 首页、Guided Tour 与 Workspace 交互 | [Workspace UX](docs/design/WORKSPACE_UX.md) |
| 前端技术栈、目录、依赖、构建与迁移 | [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md) |
| HTTP 资源与传输契约 | [API Contract](docs/architecture/API_CONTRACT.md) |
| 领域实体与不变量 | [Data Model](docs/architecture/DATA_MODEL.md) |
| Run 状态、重试、取消与派生 | [Workflow Design](docs/architecture/WORKFLOW_DESIGN.md) |
| 版本、缓存、修订与分享 | [Data Versioning](docs/architecture/DATA_VERSIONING.md) |
| 产品退出标准 | [Acceptance](docs/product/ACCEPTANCE.md) |
| PR 与发布检查 | [Review Checklist](docs/quality/REVIEW_CHECKLIST.md) |
| 唯一材料提交顺序 | [Handoff](docs/handoff/README.md) |
| Agent 执行纪律与红线 | [AGENTS](AGENTS.md) |
| 本地启动与环境变量 | [Setup](docs/setup.md) |
| Git、Issue、PR 与合并流程 | [Contributing](CONTRIBUTING.md) |

其他资料按任务类型从 [docs/README.md](docs/README.md) 定位。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
