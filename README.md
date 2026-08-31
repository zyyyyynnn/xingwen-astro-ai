# 星文智析 AI 科研工具

面向天文科研场景的数据整合、文献理解、跨文献推理与证据图谱工作流。

## 项目定位

星文智析围绕固定主案例 **系外行星候选体与宿主恒星参数整合**，把研究意图转化为可执行研究协议，并通过真实数据源、文献解析、Qwen 推理、版本化科研产物与 Evidence 建立可复核闭环：

```text
研究意图
→ 研究协议
→ ResearchRun / Activity
→ 数据与文献获取
→ 科研产物 ArtifactVersion
→ Evidence / SourceSnapshot
→ 人工反馈与 Revision
→ Scientific Diff
→ Export / Share
```

项目聚焦“科学数据查找、解析与整合”。当前产品不承诺任意天文方向、任意 PDF 全文高精度解析、任意图表全自动处理或无边界科学发现。

## 复核路径

评审者从浏览器进入 Brand Site 和 Research Workspace 后，可以沿同一产品路径检查：

1. 输入研究目标并审查系统生成的 Research Contract；
2. 确认协议并观察 ResearchRun 与 Activity；
3. 打开 Dataset、Field Dictionary、Source Collection、Paper Collection、Paper Summary、Literature Claims、Literature Relations 与 Evidence Graph；
4. 从结果进入 Evidence Inspector，核对具体 SourceSnapshot 与页、块、表格、单元格等 locator；
5. 对固定 ArtifactVersion 提交反馈并生成 RevisionPlan；
6. 执行派生 Revision Run，比较旧版本与新版本的 Scientific Diff；
7. 对明确版本执行 CSV/Markdown Export 或创建只读 Share。

Fullscreen Result Workspace 是正式结果工作区；右侧结果栏只承担索引，不维护第二套结果事实。Public Share 冻结精确 ArtifactVersion，不跟随动态 `latest`。

科学结果通过同一 Renderer / Evidence 链展示 Analysis Report、Light Curve、Spectrum、Periodogram、Folded Light Curve、Model Evaluation 与 ONNX Model Artifact。Observation 结果支持 FITS 图像与 WWT 天球场景的坐标、图层、时间及显示控制。各结果的数据等级和真实调用范围由其来源与执行记录标明。

## 真实性分层

系统不会把测试、录制或缓存数据包装成实时事实。复核时应区分：

| 层级 | 含义 |
| --- | --- |
| Fixture | 仓库内固定测试输入，只用于可重复验证 |
| Recorded | 从真实外部响应录制并固定的可重放数据 |
| Benchmark | 独立冻结的评测输入、预期结果与机器指标 |
| Live | 当前运行中真实访问的外部/API 数据来源 |
| Cached | 从满足资格条件的历史 Live 产物复用 |
| Revision | 由用户反馈与 RevisionPlan 派生的新 Run / ArtifactVersion 关系 |
| Real Model Execution | 真实 Qwen provider 调用对应的 ProducerExecution 事实 |

`execution_mode`、Artifact `source_mode`、Revision lineage 与 ProducerExecution 是不同事实，不能互相替代。Revision 通过派生 Run、`parent_run_id` 与 ArtifactVersion `supersedes` 表达，不污染来源分类。

## 正式测试与科学证据资产

仓库保留可重复验证产品能力所需的固定资产，而不提交开发过程日志：

- `tests/fixtures/scientific-documents/papers/`：开放许可科研论文、页面图像、Recorded PaddleOCR-VL 响应与邻接来源/许可元数据；
- `services/scientific_document/evidence/`：真实 PaddleOCR-VL hybrid / paired 机器报告；
- `services/data_pipeline/benchmarks/`：Scientific Data Integration 与 Crossmatch 冻结评测语料；
- `services/data_pipeline/fixtures/`：明确标记的 Recorded acquisition fixtures；
- `tests/e2e-integration/`：真实 Compose、浏览器、版本、Evidence、Revision、Share 与 NFR 纵向验证。

这些资产只证明其明确声明的层级。Recorded 响应不等于 Live，真实模型历史报告也不能替代当前 Release 对 exact source commit 的 qualifying Qwen 验证。

## 交接与运行验证

机器可读能力清单见 [handoff-manifest.json](handoff-manifest.json)，定义运行入口、配置、数据等级、证据资产、验证范围与限制。

`pnpm release-candidate` 在干净工作区校验 `RELEASE_CANDIDATE_SOURCE_COMMIT == HEAD` 和该提交的 CI / CodeQL，再使用运行环境显式配置的 Qwen 模型执行真实科研链及活跃任务 graceful restart。证据保存在 `.artifacts/release-candidate/<source_commit>/<execution_time>/`，包含 NASA 来源与选择依据、文献与定位证据、模型执行、图谱、分析和重启结果；同目录生成的交付清单记录精确提交、时间及实际验证事实。

真实数据完整性要求覆盖多个对象与字段，至少 15 条数据、10 个字段、2 个来源、3 篇候选论文、4 个摘要科学章节、3 条定位证据、3 条有依据的主张及实际关系与图谱关系边。人工视觉验收覆盖 1280×800 与 1440×900；强杀恢复、网络分区及长期负载属于独立验证范围。

## 快速开始

### Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build --wait
```

| 服务 | 本地地址 |
| --- | --- |
| Brand Site | `http://127.0.0.1:4321` |
| Research Workspace | `http://127.0.0.1:5173` |
| 后端 API | `http://127.0.0.1:8000` |
| API 文档 | `http://127.0.0.1:8000/api/docs` |
| PostgreSQL | `127.0.0.1:5432` |

真实 Qwen 使用 DashScope 服务端配置：运行环境显式提供 `DASHSCOPE_API_KEY` 与 `DASHSCOPE_MODEL`，仓库没有默认测试型号；`DASHSCOPE_EXPLICIT_MODEL_REVISION` 可选，提供时须与模型身份一致，未提供时记录为 null。API Key 只写入本地 `.env` 或运行环境 Secret，不进入前端 bundle、Git、日志、Artifact 或公开 Share。

### 前端开发

```powershell
corepack enable
corepack prepare pnpm@11.13.1 --activate
pnpm install --frozen-lockfile
pnpm dev
```

Windows + Docker Desktop 也可从仓库根目录运行 `start-dev.bat`。脚本会校验 Docker/Compose、uv、pnpm 与锁定依赖，执行 PostgreSQL 与当前 Schema 前置检查，并启动 Backend、Site 与 Workspace。

详细环境变量、后端命令与故障排查见 [docs/setup.md](docs/setup.md)。

## 核心文档

| 唯一事实范围 | 文档 |
| --- | --- |
| 产品范围与退出标准 | [PRD](PRD.md) / [Acceptance](docs/product/ACCEPTANCE.md) |
| 产品设计与体验 | [Design](DESIGN.md) / [Workspace UX](docs/design/WORKSPACE_UX.md) / [Visual Language](docs/design/VISUAL_LANGUAGE.md) |
| 系统架构与契约 | [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md) / [API Contract](docs/architecture/API_CONTRACT.md) / [Data Model](docs/architecture/DATA_MODEL.md) |
| 安全 | [Security](SECURITY.md) |
| 部署 | [Deployment](DEPLOYMENT.md) |
| 测试与复核 | [Test Strategy](docs/engineering/TEST_STRATEGY.md) / [Review Checklist](docs/quality/REVIEW_CHECKLIST.md) |
| 开发环境 | [Setup](docs/setup.md) |

完整规范索引见 [docs/README.md](docs/README.md)。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
