# 星文智析 AI 科研工具

面向天文科研场景的数据分析、文献获取、跨文献推理与证据图谱工作流。

## 项目定位

星文智析围绕固定主案例 **系外行星候选体与宿主恒星参数整合**，建设一条可复现、可溯源、可展示的科研数据工作流：

```text
科研目标 -> 数据获取 -> 字段清洗 -> 论文获取 -> 文献理解 -> 跨文献推理 -> 证据图谱 -> 结果导出 -> 反馈修正
```

项目聚焦“科学数据查找、解析与整合”方向。MVP 不承诺任意天文方向、任意 PDF 全文高精度解析、任意图表全自动处理或无边界科学发现。

## 快速开始

```powershell
Copy-Item .env.example .env
docker compose up --build --wait
```

| 服务 | 地址 |
| --- | --- |
| Brand Site | `http://127.0.0.1:4321` |
| Research Workspace | `http://127.0.0.1:5173` |
| 后端 API | `http://127.0.0.1:8000` |
| API 文档 | `http://127.0.0.1:8000/api/docs` |
| PostgreSQL | `127.0.0.1:5432` |

前端本机调试从仓库根目录执行：

```powershell
corepack enable
corepack prepare pnpm@11.13.1 --activate
pnpm install --frozen-lockfile
pnpm dev
```

Windows + Docker Desktop 可直接运行仓库根目录的 `start-dev.bat`。脚本会校验
Docker/Compose、uv、pnpm 与锁定依赖，在当前窗口完成 PostgreSQL 和当前 schema 前置检查，
再分别打开 Backend 与 Frontend 窗口，最后优先打开品牌首页
`http://127.0.0.1:4321`。

环境变量、后端命令与故障排查见 [docs/setup.md](docs/setup.md)。真实密钥只写入本地 `.env` 或部署平台 Secrets。

## 核心文档

| 唯一事实范围 | 文档 |
| --- | --- |
| 阶段与退出标准 | [PRD](PRD.md) / [Acceptance](docs/product/ACCEPTANCE.md) |
| 产品设计与体验 | [Design](DESIGN.md) / [Workspace UX](docs/design/WORKSPACE_UX.md) / [Visual Language](docs/design/VISUAL_LANGUAGE.md) |
| 系统架构与契约 | [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md) / [API Contract](docs/architecture/API_CONTRACT.md) / [Data Model](docs/architecture/DATA_MODEL.md) |
| 执行与审查规范 | [AGENTS](AGENTS.md) / [Contributing](CONTRIBUTING.md) / [Review Checklist](docs/quality/REVIEW_CHECKLIST.md) |

完整规范索引见 [docs/README.md](docs/README.md)。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
