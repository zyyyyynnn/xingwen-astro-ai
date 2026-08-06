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

## 前端最低标准

| 维度 | 必须达到 |
| --- | --- |
| 上游来源 | 固定 Repository、Tag、Commit、License 与源码映射 |
| 产品骨架 | 使用真实上游 Shell、Navigation、Agent Activity、Workspace 与 Composer |
| 领域边界 | Domain、Repository、Workflow 与 Version 仍为事实源 |
| Agent 可用性 | Running、Needs Review、Completed 与 Failed 均有可执行路径 |
| Artifact | 核心类型使用专属 Renderer |
| Evidence | Statement / Cell / Claim 可定位 Evidence 与来源 |
| 修订 | 创建派生 Run 或新 ArtifactVersion，不覆盖历史 |
| 真实性 | Fixture、Live、Cached、Revision 分别表达 |
| 可访问性 | 键盘、焦点、读屏、Reduced Motion 与 200% 字体可用 |
| 响应式 | 1440×900、1280×800 与 390×844 完成核心路径 |
| 可恢复 | Workspace、运行与分享状态可恢复或明确失败 |
| 视觉 | 用户明确确认产品骨架、信息层级与可用性 |
| 工程 | Build、Architecture、Retirement、E2E 与 Compose 通过 |

## 上游采用标准

- 上游原版可运行；
- 源码来自固定版本；
- License 与 NOTICE 完整；
- 采用与排除范围明确；
- Upstream → Local 映射完整；
- 未手写替代上游已有成熟能力；
- 仓库内不存在第二套 Workspace Shell。

## 前端产品标准

- 用户可识别当前研究上下文、Agent 状态、主产物与下一步。
- Agent Activity 与 Artifact Workspace 同时可达。
- Completed 状态允许继续研究、修订、派生、导出与分享。
- Tool 与 Deliverable 分离。
- 默认视图不暴露内部 ID、Hash、Adapter、Fixture 或私有推理。
- 未实现能力不以假数据或禁用主控件呈现。

## 2. M1：开发基线

M1 完成需要同时满足：

- Docker Compose 可启动并健康检查 `site`、`workspace`、`api`、`postgres`，且 `migrate` one-shot 成功退出后 API 才启动；
- `/api` 健康检查和回归测试通过；
- 工具链基线（Node、pnpm、根 lockfile、uv、Schema 导出与 Foundation CI）通过；
- 前端运行时（Astro Site、React Workspace 最小宿主、共享包、根工具链与路由）通过 build、architecture 和 retirement checks；
- Fixture / HTTP Adapter 对同一场景返回同一 Domain Model；真实 Browser/Compose 覆盖 Session、经公开 Runtime 创建 Project 与 ContractDraft、Contract 确认、Run/Event、ArtifactVersion/Evidence、Workspace 冲突与刷新恢复、冻结 Share、匿名读取与撤销；操作口径以 [API Contract](../architecture/API_CONTRACT.md) 为准；
- PostgreSQL 是 Project、Contract、Run、Event、ArtifactVersion 和 Evidence 的权威事实源；集成 CI 不使用 SQLite、MSW 或 Repository mock；
- 运行时退役扫描通过，历史应用目录、专用依赖和环境变量不存在；
- Case / Field Manifest 和论文/推理 Benchmark 可机器校验并版本化；主案例事实包已冻结；
- `/api` 最小 Session、Project、Contract、Run、Event、Artifact、Version、Workspace 和 Share Contract 可测试；
- 静态首页为极简单英雄区（Hero + 单一“进入工作台”CTA + 一句标题 + 短注）；Token 为 bluegray 体系且业务组件不消费 Raw；
- 实现状态表述在页面、文档和材料中无混淆。

## 3. X-06：数据、论文与 Summary 主链路

X-06 完成需要证明：

- Project → Contract → Live Run 可复现；
- PostgreSQL 是 Run、Step、Event 和 ArtifactVersion 的事实来源；
- 至少一个主数据源和一个补充真实来源可运行；
- 跨源实体对齐、字段映射、单位统一和分层质量通过固定样例验证；
- Dataset、FieldDictionary、PaperCollection 和 PaperSummary 以 ArtifactVersion 发布；
- 数据和论文 Query、来源、时间、规则版本、hash 与 SourceSnapshot 可定位；
- PaperSummary 核心 finding / limitation 逐项绑定 Evidence；
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
- ShareSnapshot 和 Export 固定引用 Version，不跟随动态 latest；
- 公网 Site、Workspace、Share 和 API 可访问且生产安全配置通过；
- 外部来源失败时核心内容和操作仍可用；
- START HERE、短片、Web、PDF、源码/API/测试和 provenance manifest 使用同一事实版本。

## 6. 产品级最低标准

| 维度   | 必须达到                                                 |
| ------ | -------------------------------------------------------- |
| 可理解 | 无现场讲解可识别产品目标、主流程和可信边界               |
| 可运行 | Demo Replay 稳定；Live Run 有明确等待、失败和恢复        |
| 可复现 | 关键结果可定位 Contract、Run、Version、来源和生成条件    |
| 可溯源 | 关键数据、Summary、Relation 和 GraphEdge 可定位 Evidence |
| 可对照 | Workspace 基于成熟 Agent 骨架与 Panel Host 可完成审查    |
| 可降级 | 外部服务或选件失败不阻断核心流程                         |
| 可分享 | 只读分享最小范围、可撤销、可过期、不泄露编辑会话         |
| 可提交 | 网页、视频、PDF、导出和源码描述一致                      |

## 7. 一票否决

出现以下任一情况，不得宣布前端或对应阶段完成：

- 参考成熟产品后手写相似骨架；
- 无固定上游版本或许可证记录；
- 无源码映射；
- 静态假数据冒充产品能力；
- Preview Route 或工程文案进入正式产品；
- 旧 UI 或第二套 Shell 仍在生产路径；
- 技术测试通过但用户视觉验收未通过；
- 前端 Store 替代 Domain、Repository 或服务端 Workflow；
- 为满足旧测试恢复已退役 UI；
- Fixture、seed、录制响应或无来源数据冒充 Live / Cached；
- 数据、Summary、Accepted Relation 或 GraphEdge 无法追溯 Evidence；
- 保存或展示模型私有 chain-of-thought；
- ArtifactVersion 被原地覆盖，或 Share / Export 指向动态 latest；
- 前端暴露密钥、直连受控外部来源或渲染未净化外部 HTML；
- 跨会话资源可枚举或读取，分享泄露编辑凭据；
- API、Data Model、Workflow、Version、Issue 与实现明显冲突；
- 宣传未实现的任意方向、全文解析、图表解析或无证据科学发现；
- 必要 CI、测试或部署验证被绕过。

## 8. 关联文档

- 单个 PR 检查：[Review Checklist](../quality/REVIEW_CHECKLIST.md)
- 测试方法和数据等级：[Test Strategy](../engineering/TEST_STRATEGY.md)
- 材料提交和 provenance：[Handoff](../handoff/README.md)
- 风险与例外：[Risk Register](../quality/RISK_REGISTER.md)
