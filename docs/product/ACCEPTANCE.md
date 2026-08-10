# Acceptance Criteria

| 元数据    | 值                                   |
| --------- | ------------------------------------ |
| Authority | 产品交付与发布的退出标准及一票否决项 |

本文定义产品交付与发布的退出标准。单个 PR 审查见 [Review Checklist](../quality/REVIEW_CHECKLIST.md)，测试设计见 [Test Strategy](../engineering/TEST_STRATEGY.md)。

## 1. 证据要求

退出结论必须提供可复现的运行证据，至少包含：

- 对应的 Commit / PR；
- 实际验证命令与观察到的结果；
- 运行环境与契约版本；
- 数据真实性等级（Live / Fixture / Cached）；
- 关键 Run、ArtifactVersion 或 Evidence 标识；
- 未执行项与已知限制。

## 2. 产品交付标准

| 维度     | 必须达到                                                                                            |
| -------- | --------------------------------------------------------------------------------------------------- |
| 可理解   | 无需现场讲解即可识别产品目标、主流程与可信边界                                                      |
| 可运行   | Research Workspace 宿主与 Agent 运行流程可运行，Live Run 有明确等待、失败与恢复                     |
| 可复现   | 关键结果可定位 Contract、Run、ArtifactVersion、来源与生成条件                                       |
| 可溯源   | 关键数据、Summary、Relation 和 GraphEdge 可逐项定位 Evidence                                        |
| 竞赛合规 | 主案例具有合格 Qwen 官方调用路径、固定模型版本、脱敏 call proof、ProducerExecution 与输入/输出 hash |
| 可对照   | Workspace 基于成熟 Agent 骨架，可高效对照产物与证据                                                 |
| 可降级   | 外部服务或选件失败时不阻断核心流程                                                                  |
| 可分享   | 只读分享受最小范围保护，可撤销、可过期、不泄露编辑会话                                              |
| 可部署   | 环境拓扑、配置、Migration 与健康检查完整通过                                                        |
| 可访问   | 键盘导航、焦点控制、屏幕阅读与字体缩放可用                                                          |

Workspace 验收必须以已合并、可复现、可运行的实现证据为准。OpenHands 采用记录、
目标架构或 Draft/Open PR 只能证明源码治理范围，不能证明 Live Run、模型资格或完整
研究闭环。验收材料必须分别给出壳层、真实运行服务、科研产物、Evidence 与 `/share`
只读边界的证据。

正式提交还必须通过 [Competition Compliance](COMPETITION_COMPLIANCE.md)：合格 Qwen
执行、批准的 provider 路径、model/version/revision、脱敏 call proof、
ProducerExecution、input/output hash 以及真实 ArtifactVersion/Evidence 必须形成可复核
闭环。模型内部调用、准入与记录规则由 [Model Policy](../ai/MODEL_POLICY.md) 负责。

## 3. 前端与上游采用标准

- 前端选型基于成熟开源 Agent 产品源码骨架进行领域改造，仓库内仅维护单一 Workspace Shell。
- 业务页面通过 Repository Port 消费 Domain Model，不直接读取 Transport DTO 或原始 fetch。
- Completed 状态下允许继续研究、修订、派生、导出与分享。
- 默认视图严禁暴露内部 ID、Hash、Adapter、Fixture 或模型私有推理。

## 4. 一票否决项

出现以下任一情况，不得宣布作品完成或达到正式提交标准：

- 参考成熟产品后手写相似骨架，或在仓库内引入第二套 Workspace Shell；
- Fixture、seed、录制响应或无来源数据冒充 Live / Cached 真实结果；
- 数据、Summary、Accepted Relation 或 GraphEdge 无法追溯 Evidence；
- 保存或展示模型私有 chain-of-thought；
- ArtifactVersion 被原地覆盖，或 Share / Export 指向动态 latest；
- 前端暴露 Secrets 密钥、直连受控外部来源或渲染未净化 HTML；
- 跨会话私有资源可被枚举或读取，分享泄露编辑凭据；
- API、Data Model、Workflow、Data Versioning 规范与代码实现发生矛盾；
- 缺少符合 Competition Compliance 的真实合格模型执行及可复核调用证明；
- 必要自动化 CI、测试或部署验证被绕过。
