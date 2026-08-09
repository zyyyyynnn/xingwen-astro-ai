# AGENTS

本文件是仓库的 Agent 执行协议。协作与合并流程见
[CONTRIBUTING.md](CONTRIBUTING.md)，规范地图与文档治理见
[docs/README.md](docs/README.md)。

## 1. 默认读取顺序

1. 读取本文件，确定执行协议与核心边界。
2. 读取当前 Issue 或用户直接授权，确定目标、范围与验收标准。
3. 读取 [docs/README.md](docs/README.md)，定位唯一 Authority。
4. 只读取 1–3 份与任务直接相关的 Authority 正文。
5. 核对当前代码、生成 Contract、测试与真实运行证据；参考资料仅按需读取。

不要默认递归读取 `docs/references/`、全量 Markdown、历史 Commit、已关闭 PR
或过程性 Handoff。需要扩大范围时说明原因，并保持事实来源可追溯。

## 2. 真实性、状态与产品主链

只有以下证据可以支持“Current Implementation”：`origin/main` 中的代码、已合并
PR、生成 Contract、当前测试、可执行运行时、PostgreSQL 数据或真实 Browser/集成
运行证据。Draft/Open PR、Issue、目标架构、Fixture、Recorded response、Benchmark、
Seed、Cached 结果、未来 handoff 与参考项目都不是 Current。

活跃规范只描述已批准的稳定规则，不描述实现进度、PR 状态、Issue 状态或动态
“当前实现”。审计时可在临时 Truth Matrix 中区分 `CURRENT / TARGET / PLANNED /
REFERENCE`，但不把该矩阵提交为第二套状态源。

冲突按事实职责裁决：当前任务范围由用户直接授权或 Issue 定义；稳定预期行为由
Accepted Authority 定义；实现状态由当前代码、Contract、测试与真实运行证据定义；
研究灵感只来自 Reference，不能覆盖前三者。

产品主链固定为：

```text
Research Intent → Draft → Contract → Run → Artifact → Evidence
→ review → revision / export / share
```

Fixture、Recorded、Benchmark、Cached 与 Live 必须显式区分；Revision 创建新的
Run/ArtifactVersion；ArtifactVersion 不可变；Evidence、Export、Share 固定到明确
版本；Event 不是唯一状态事实；candidate/rejected 不是科研事实；parser confidence
不是 scientific confidence；partial/unsupported 不得自动补成 complete。

## 3. 架构边界

```text
Experience
→ Frontend Application Boundary
→ Research Adapter / Query
→ Repository Port
→ Fixture / HTTP Adapter
→ API Application Service
→ Workflow
→ Step Adapter
→ Scientific Pipeline
→ Publisher
→ ArtifactVersion / Evidence / SourceSnapshot
```

- Domain 不依赖 React、DOM、HTTP 或 SQL；Page/Feature 不直接 `fetch`。
- UI 不读取 API path、raw DTO 或未校验响应；Runtime DTO 必须先验证，再映射为 Domain/ViewModel。
- Fixture 与 HTTP Adapter 共享同一 Repository/Domain 映射；Adapter 不写科研事实。
- Router 不承载算法或直接串联 Pipeline；Pipeline 不推进 Run 状态、不写 HTTP DTO、不分配版本。
- Publisher 是 ArtifactVersion/Evidence 的唯一发布事务边界。
- Prompt 只从 Prompt Registry 加载；禁止 `any`、不安全断言、深层 import 与第二套状态机、事件存储、执行器、Shell 或渲染器。

## 4. OpenHands 与成熟能力复用

OpenHands 只提供产品交互机械结构：Shell、Navigation、Activity、Composer、
Command、公开事件呈现、Resize 与 Focus。它不带入后端 Agent Runtime、Sandbox、
Terminal、Git/Editor/Repo Browser、任意代码执行、认证、Cloud/Enterprise 或编码
工作面；不得据此声称 Xingwen ResearchRun 已经执行。

优先复用成熟 upstream：OpenHands、TanStack Query/Table/Virtual、XYFlow/React Flow、
shadcn/ui（仅补缺失组件）、Docling/docling-parse native、PaddleOCR-VL visual，以及
通过 Alibaba Cloud Model Studio/Bailian 的 Qwen。不得新增泛化 RAG、向量数据库、
LangGraph 或第二套通用平台类别。所有上游采用必须记录版本、Commit/Revision、许可、
边界和升级策略。

## 5. 实现与 Issue 治理

- 先检查工作区、分支、根目录、基线与相关 diff；保留用户已有修改。
- 一个 Issue 只承担一个模块、一个可观察交付物、一个主要负责人和一个主要 PR。
- Epic 只维护父级范围与退出证据；父子关系不自动等于 blocked-by，真实阻塞使用 GitHub 原生依赖。
- Issue 必须区分 `Completed baseline` 与 `Planned handoff`；未来计划不能写成已实现。
- 新能力必须先明确 Contract、失败/拒绝语义、版本/Evidence 边界与回归验收。
- 默认不引入新依赖、不修改生成物/供应商代码/锁文件、不夹带无关重构。
- 未经明确要求，不提交、推送、变基、合并、切换分支、强制覆盖或删除数据。

## 6. 验证与报告

优先运行实际路径、针对性测试、相关测试、构建/静态检查；不跳过直接相关测试。
只报告真实执行并观察到的结果。无法验证时明确写“未验证”、原因与建议的
PowerShell 命令，并区分本地检查、CI、PR 状态、合并状态和能力阻塞。
