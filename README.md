<div align="center">

# 星文智析

_面向天文科研数据整合、文献理解与证据核验的 AI 科研工作台_

[![License: MIT](https://img.shields.io/badge/license-MIT-64748b)](LICENSE)

</div>

---

## 项目定位

星文智析围绕固定主案例 **系外行星候选体与宿主恒星参数整合**，将科研问题转化为可执行契约，并串联数据获取、字段对齐、论文检索、文献总结、跨文献推理、证据图谱、导出和追加式修订。

系统的核心交付不是聊天记录，而是可复现、可溯源、可对照的科研产物与 Evidence。

MVP 不承诺任意天文方向、任意 PDF 全文高精度解析、任意图表全自动处理或无证据科学发现。

## 当前状态

| 范围 | 状态 |
| --- | --- |
| 当前可运行基线 | `apps/web` Vue 骨架、FastAPI `/api/v1`、Docker Compose |
| 已接受目标 | Astro Brand Site、React Research Workspace、共享前端包与 `/api/v2` Project / Run / Artifact / Version 契约 |
| 实施状态 | Pending；目标文档不表示迁移已完成，当前启动命令保持不变 |

当前实现与目标架构必须始终分开描述。详细迁移方案见 [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md)。

## MVP 能力

| 能力 | 核心产物 |
| --- | --- |
| 数据整合 | Dataset、FieldDictionary、SourceSnapshot、Quality |
| 论文获取 | Query、PaperCollection、候选去重与选择依据 |
| 文献理解 | PaperSummary 与逐项 Evidence |
| 跨文献推理 | Claim、Relation、ReasoningTrace |
| 证据图谱 | 绑定 Evidence、Relation 与 Trace 的 Graph |
| 修订与交付 | ArtifactVersion、Feedback、RevisionPlan、Export、ShareSnapshot |

## 快速开始

当前本地基线使用 Docker Compose：

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

环境变量、裸机调试命令、测试和故障排查见 [Local Setup](docs/setup.md)。真实密钥只写入本地 `.env` 或部署平台 Secrets。

## 仓库结构

```text
apps/web                  当前前端回退基线
apps/api                  FastAPI 后端
services/data_pipeline    数据获取、对齐、质量与导出
services/paper_pipeline   论文检索、总结与证据
services/graph_pipeline   Claim、Relation、Trace 与 Graph
packages/schemas          当前生成 Schema 基线
packages/prompts          不可变生产 Prompt
samples                   可复现输入输出样例
scripts                   验证、导出与开发脚本
docs                      产品、设计、架构、工程与交接文档
```

目标迁移目录尚未全部建立；实际目录和运行方式以代码与 [Local Setup](docs/setup.md) 为准。

## 文档入口

| 需要了解 | 入口 |
| --- | --- |
| 产品范围与主流程 | [PRD](PRD.md) |
| 设计原则与体验边界 | [DESIGN](DESIGN.md) |
| 完整文档地图与唯一事实来源 | [Docs Index](docs/README.md) |
| 本地启动与验证 | [Local Setup](docs/setup.md) |
| Git、Issue 与 PR 流程 | [Contributing](CONTRIBUTING.md) |
| Agent 执行协议 | [AGENTS](AGENTS.md) |

文档层级、状态、合并、拆分和归档规则见 [Documentation Governance](docs/DOCUMENTATION_GOVERNANCE.md)。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.