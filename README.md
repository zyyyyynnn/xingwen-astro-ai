# 星文智析 AI 科研工具

面向天文科研场景的一体化 AI 科研应用，围绕“科研问题 -> 数据获取 -> 文献理解 -> 证据组织 -> 可视化表达”的链路，提供自动化数据分析、智能文献总结和天文学术图谱可视化能力。

## 项目定位

本项目服务于挑战杯“揭榜挂帅”赛题“基于国产开源大模型的 AI Scientist 研发与应用”，聚焦赛道二方向一 A：科学数据查找、解析与整合。

MVP 主案例为：**系外行星候选体与宿主恒星参数整合**。

系统目标不是泛聊天助手，也不是一次性生成报告工具，而是一个可复现、可溯源、可导出、可反馈修正的天文科研数据工作流。

## 核心功能

| 功能 | 说明 | MVP 定位 |
| --- | --- | --- |
| 自动化数据分析 | 获取多源天文数据，完成清洗、字段对齐、来源标注和 CSV 导出 | 主链路 |
| 智能文献总结 | 解析主案例相关文献，提取研究目标、方法、数据集、结论和局限 | 增强主功能 |
| 天文学术图谱可视化 | 构建论文、数据源、字段、证据之间的关系图谱 | 展示亮点 |

## MVP 主流程

```text
用户输入科研目标
-> Qwen 解析目标并生成任务计划
-> 获取系外行星和宿主恒星数据
-> 数据清洗、字段对齐、单位统一
-> 生成 CSV、数据字典、溯源报告
-> 解析主案例相关文献
-> 生成结构化文献总结
-> 构建论文-数据-字段-证据图谱
-> 前端展示完整流程和结果
-> 用户反馈字段/来源/单位问题
-> 系统局部修正并重新导出结果
```

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite |
| 后端 | FastAPI |
| 模型 | Qwen / 阿里云百炼 |
| 数据库 | PostgreSQL |
| 数据处理 | Python, pandas, astroquery / requests |
| 图谱展示 | 前端图谱组件，数据由后端输出统一 JSON |

## 仓库结构

```text
.
├── apps/
│   ├── web/                  # Vue 前端
│   └── api/                  # FastAPI 后端
├── services/
│   ├── data_pipeline/        # 数据获取、清洗、字段对齐、CSV 导出
│   ├── paper_pipeline/       # 文献解析、结构化总结
│   └── graph_pipeline/       # 图谱节点、边、证据链构建
├── packages/
│   └── schemas/              # 共享数据结构和 API 契约
├── docs/
│   ├── architecture/         # 架构、接口、数据模型
│   ├── product/              # PRD、路线图、验收标准
│   └── handoff/              # 给材料组的截图、说明、演示素材
├── samples/
│   ├── inputs/               # 样例输入
│   └── outputs/              # 样例输出
└── scripts/
    ├── dev/                  # 本地开发脚本
    └── verify/               # 验证脚本
```

## 关键文档

- [PRD.md](./PRD.md)
- [DESIGN.md](./DESIGN.md)
- [AGENTS.md](./AGENTS.md)
- [docs/architecture/API_CONTRACT.md](./docs/architecture/API_CONTRACT.md)
- [docs/architecture/DATA_MODEL.md](./docs/architecture/DATA_MODEL.md)
- [docs/product/ROADMAP.md](./docs/product/ROADMAP.md)
- [docs/product/ACCEPTANCE.md](./docs/product/ACCEPTANCE.md)

## 开发原则

1. 主案例优先围绕系外行星，不随意扩散到多个天文方向。
2. 三大功能必须串成科研工作流，不做三个孤立模块。
3. 所有模块输出统一 JSON，便于前端展示、图谱复用和材料组引用。
4. 所有关键结果必须有来源、参数、时间和处理记录。
5. 公网 Demo 必须有缓存兜底，避免外部服务不稳定影响展示。
