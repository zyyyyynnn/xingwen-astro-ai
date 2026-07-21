# Acceptance Criteria

| 元数据    | 值                               |
| --------- | -------------------------------- |
| Status    | Accepted                         |
| Authority | 里程碑、阶段和作品发布的退出标准 |

本文回答“一个阶段何时可以宣布完成”。单个 PR 的检查见 [Review Checklist](../quality/REVIEW_CHECKLIST.md)，测试设计见 [Test Strategy](../engineering/TEST_STRATEGY.md)，实时任务状态以 GitHub Issues 为准。

## 1. 证据要求

任何退出结论必须提供可复现证据，至少包含：

- 对应 Commit / PR / Issue；
- 验证命令和结果；
- 运行环境、应用版本和 Contract 版本；
- 使用 Fixture、recorded、Live 或 Cached 的真实数据等级；
- 关键 Run、ArtifactVersion、SourceSnapshot 或导出引用；
- 未执行项、已知限制和风险。

文档声明、截图或“页面看起来正确”不能单独证明实现完成。

## 2. M1：开发基线

M1 完成需要同时满足：

### Current runtime baseline

- 当前 Docker Compose 可启动并健康检查 `site`、`workspace`、`api`、`postgres`；
- `/api/v1` 健康检查和回归测试通过；
- Node.js 24.18.0、pnpm 11.13.1、根 lockfile、uv、Schema 导出和 Foundation CI 通过；
- A-01 Astro Site、React Workspace、共享包、根工具链与最小路由通过 build、E2E、architecture 和 retirement checks；
- 运行时退役扫描通过，历史应用目录、专用依赖和环境变量不存在。

### Pending M1 capabilities

- Case / Field Manifest 和论文/推理 Benchmark 可机器校验并版本化；
- X-00 已冻结主案例事实包；
- `/api/v2` 最小 Session、Project、Contract、Run、Event、Artifact、Version、Workspace 和 Share Contract 可测试；
- A-02 静态首页为极简单英雄区（Hero + 双 CTA + 一句标题 + 短注），Workspace Shell 支持键盘、移动端和实时视觉降级；Token 为 bluegray 体系且业务组件不消费 Raw；
- A-03 的 Fixture / HTTP Adapter 返回同一 Domain Model；
- X-01 的 Session、Contract、Run、Event、WorkspaceSnapshot 和 ShareSnapshot 主流程通过；
- Current、Implemented 和 Pending 在页面、文档和材料中无混淆。

## 3. X-06：数据、论文与 Summary 主链路

X-06 完成需要证明：

- Project → Contract → Live Run 可复现；
- PostgreSQL 是 Run、Step、Event 和 ArtifactVersion 的事实来源；
- 至少一个主数据源和一个补充真实来源可运行；
- 跨源实体对齐、字段映射、单位统一和分层质量通过固定样例验证；
- Dataset、FieldDictionary、PaperCollection 和 PaperSummary 以 ArtifactVersion 发布；
- 数据和论文 Query、来源、时间、规则版本、hash 与 SourceSnapshot 可定位；
- PaperSummary 核心 finding / limitation 逐项绑定 Evidence；
- A-04～A-06 可从关键值或结论定位 Evidence；
- 空结果、上游失败、Schema 无效、Evidence 不足和授权场景通过；
- Fixture、Live、Cached、Run status 和 view state 没有语义混用。

## 4. X-07：推理与证据图谱

X-07 完成需要证明：

- Claim、Relation、ReasoningTrace 和 Graph 均以明确 ArtifactVersion 发布；
- candidate、accepted、rejected Relation 可区分；
- Accepted Relation 绑定双方 Evidence、显式条件和 ReasoningTrace；
- ReasoningTrace 只保存可审查依据，不包含模型私有推理；
- Graph 不存在悬空引用；所有边有 Evidence，跨文献边有 Relation 和 Trace；
- 科学关系与 layout hint 分离；
- A-07/A-08 可在最多三个面板中完成推理、Graph 和 Evidence 对照；
- 固定 Benchmark 报告 Relation 科研审核正确率、Evidence 覆盖、无证据拦截、Graph 完整性和 Schema 通过率；
- 从 X-06 Summary 版本到 Graph 版本的 E2E 可复现。

## 5. X-08：版本、缓存、修订与交付

X-08 完成需要证明：

- 关键科研产物均使用不可变 ArtifactVersion；
- ResearchRun 与 ProducerExecution 的职责、父子关系和 hash 可定位；
- CacheRecord 只引用真实历史 Run、Version 和 SourceSnapshot；
- CacheSelector 仅在 Live 可恢复失败且质量/Evidence 仍满足时使用缓存；
- Feedback 绑定明确对象和基线版本，RevisionPlan 展示影响闭包；
- revision Run 只重算受影响步骤，生成新版本并保留历史；
- A-09/A-10 可正确表达来源、质量、版本、冲突和修订；
- ShareSnapshot 和 Export 固定引用 Version，不跟随动态 latest；
- 公网 Site、Tour、Workspace、Share 和 API 可访问且生产安全配置通过；
- WebGL 或外部来源失败时核心内容和操作仍可用；
- START HERE、短片、Web、PDF、源码/API/测试和 provenance manifest 使用同一事实版本。

## 6. 产品级最低标准

| 维度   | 必须达到                                                 |
| ------ | -------------------------------------------------------- |
| 可理解 | 无现场讲解可识别产品目标、主流程和可信边界               |
| 可运行 | Demo Replay 稳定；Live Run 有明确等待、失败和恢复        |
| 可复现 | 关键结果可定位 Contract、Run、Version、来源和生成条件    |
| 可溯源 | 关键数据、Summary、Relation 和 GraphEdge 可定位 Evidence |
| 可对照 | 工作台最多三面板可完成核心审查任务                       |
| 可降级 | 图形、字体或外部服务失败不阻断核心流程                   |
| 可分享 | 只读分享最小范围、可撤销、可过期、不泄露编辑会话         |
| 可提交 | 网页、视频、PDF、导出和源码描述一致                      |

## 7. 一票否决

出现以下任一情况，不得宣布对应阶段或作品完成：

- Fixture、seed、录制响应或无来源数据冒充 Live / Cached；
- 数据、Summary、Accepted Relation 或 GraphEdge 无法追溯 Evidence；
- 保存或展示模型私有 chain-of-thought；
- ArtifactVersion 被原地覆盖，或 Share / Export 指向动态 latest；
- 前端暴露密钥、直连受控外部来源或渲染未净化外部 HTML；
- 跨会话资源可枚举或读取，分享泄露编辑凭据；
- WebGL 失败导致首页或工作台不可用；
- API、Data Model、Workflow、Version、Issue 与实现明显冲突；
- 宣传未实现的任意方向、全文解析、图表解析或无证据科学发现；
- 必要 CI、测试或部署验证被绕过。

## 8. 关联文档

- 单个 PR 检查：[Review Checklist](../quality/REVIEW_CHECKLIST.md)
- 测试方法和数据等级：[Test Strategy](../engineering/TEST_STRATEGY.md)
- 材料提交和 provenance：[Handoff](../handoff/README.md)
- 风险与例外：[Risk Register](../quality/RISK_REGISTER.md)
