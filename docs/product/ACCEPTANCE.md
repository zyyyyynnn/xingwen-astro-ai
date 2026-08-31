# Acceptance Criteria

| 元数据 | 值 |
| --- | --- |
| Authority | 产品交付与发布退出标准、一票否决项 |

## 1. 证据要求

任何“完成”“Ready”或发布结论必须绑定 exact Commit/PR，并说明：

- 实际执行的验证命令与观察结果；
- 环境、数据等级和必要 Contract/模型 revision；
- 真实 Run / ArtifactVersion / Evidence / SourceSnapshot 证据；
- Browser / Compose / PostgreSQL / Worker 等实际使用的验证层；
- 未执行项、skip、已知限制与外部依赖。

不得把旧 HEAD、目标架构、Fixture、静态截图、外部 benchmark 或未执行 provider 当成当前能力证明。

## 2. 产品退出标准

| 维度 | 必须达到 |
| --- | --- |
| 可理解 | 无现场讲解即可识别产品目标、当前研究状态、主要结果、可信边界与下一步 |
| 可运行 | Research Workspace 与真实 ResearchRun 可运行，等待、失败、partial、unsupported、retry/recovery 真实 |
| 可达 | 每个向用户承诺的能力有正式入口或明确 Agent 自动触发路径 |
| 可复现 | 关键结果可定位 Contract、Run、ArtifactVersion、来源、模型/Prompt 与生成条件 |
| 可溯源 | 数据、Summary、Accepted Relation、GraphEdge 与关键科学结论逐项可定位 Evidence |
| 可修订 | Feedback → confirmed RevisionPlan → derived Run → superseding ArtifactVersion 可验证 |
| 可降级 | 外部服务、数据源或可选能力失败时真实呈现 failure/partial/unsupported，并保持仍可成立的核心研究链可用，不以假结果填补缺口 |
| 可分享 | 冻结版本公开投影可撤销、可过期、最小披露且不加载私有编辑会话 |
| 可部署 | 当前 schema、配置、健康检查、PostgreSQL、Worker 与前端部署边界完整 |
| 可访问 | Keyboard、Focus、Screen Reader、Reduced Motion 与正式桌面视口可用 |
| 竞赛合规 | 主案例具有 Qwen 官方合格调用路径、可复核 model/revision 与 call proof、ProducerExecution、ArtifactVersion 与 Evidence 闭环 |

## 3. Capability Reachability Gate

每个产品能力必须同时满足：

```text
real user entry / Agent trigger
→ current Domain / Repository
→ current Workflow / Scientific runtime
→ typed Artifact / Evidence / Activity
→ understandable loading/error/result
→ applicable compare/revision/export/share
→ Browser or live vertical evidence
```

以下只能证明“内部实现存在”，不能证明“产品交付”：API endpoint、library function、Unit Test、Fixture、benchmark、静态 screenshot、隐藏开发路由、手工数据库注入。

## 4. Integration Cohesion Gate

新增或迁入能力退出前必须证明：

- 已对当前 `main` 做 capability gap，未重复已有或更优实现；
- 新能力进入现有单一 runtime/store/Publisher/Evidence/Renderer/Workspace；
- 没有 sidecar、raw JSON bridge、第二 store、第二 renderer family 或永久兼容层；
- 临时 seam 与失真旧实现已经删除；
- 用户不需要理解内部来源或模块结构；
- 正式 Browser / integration / benchmark 证明能力已成为当前产品链的一部分。

## 5. Workspace 行为验收

- AI 正常消息贯穿目标理解、Contract、主要阶段、中间发现、结果发布与完成；
- Activity / Public Analysis 是次级信息，不替代 Assistant Message；
- 右侧研究栏只做概览与结果索引；点击结果进入唯一 Fullscreen；
- Evidence Inspector 是共享 presentation，关键结果到 Evidence 不超过三次交互；
- 论文结果在可用时支持报告/PDF 同屏与 locator 定位；
- Scientific Diff 比较实际用户相关 Evidence、结论、关系、限制与冲突，不以 count-only 或 raw JSON 代替；
- Graph 具备可选择节点/边、Evidence context、键盘路径和 list fallback；
- Public Share 使用冻结 typed projection 和共享只读 presentation；
- 默认 UI 不显示内部 ID、hash、raw enum、producer、adapter、Issue/PR 编号、内部阶段版本或能力来源标识。

正式视觉验收覆盖 Light：1440×900、1280×800。

## 6. Grouped Delivery 验收

Grouped Delivery PR 只有在每个包含 Issue 都有独立 acceptance/evidence matrix 且全部达到对应 closure 标准时，才允许使用 `Closes` 语义。一个 Issue 未完成时，不得用同 PR 其他能力的通过结果替代。

## 7. 一票否决

出现任一情况，不得宣布完成：

- 在 `main` 直接开发或绕过正式 PR/Review；
- 为已有成熟职责重新手写相似骨架，或形成第二套 Workspace/Runtime/Publisher/Evidence/Renderer/Revision；
- 用户承诺能力仅存在于后端、测试、Fixture 或隐藏入口；
- Fixture/Recorded/seed 冒充 Live/Cached；
- 关键科学事实、Summary、Accepted Relation 或 GraphEdge 无 Evidence；
- 保存/展示 provider 私有 chain-of-thought；
- ArtifactVersion 原地覆盖，Share/Export 指向动态 latest；
- 公开分享泄露私有 session、token、secret、内部 metadata 或未净化内容；
- 外部源码在 license/provenance 不明确时直接复制进 production；
- 当前 API/Data Model/Workflow/Versioning/UX Authority 与实现互相矛盾；
- 缺少符合 Competition Compliance 的真实合格 Qwen 执行及可复核调用证明；
- 必要 CI、real integration、Browser、安全或可访问性验证被绕过。
