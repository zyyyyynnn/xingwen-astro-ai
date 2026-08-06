# Review Checklist

| 元数据    | 值                                             |
| --------- | ---------------------------------------------- |
| Status    | Accepted                                       |
| Authority | 单个 Pull Request 的正式技术 Review 与合并清单 |

本清单由正式技术 Review 使用，回答“这个 PR 是否可以合并”。实施过程中的自审不能替代该 Review。合格审查者可以是人工、Codex、网页端 GPT、独立审查 Agent 或用户明确授权的其他技术审查主体；不以工具、模型、客户端或入口决定 Review 是否有效。里程碑和作品是否完成由 [Acceptance](../product/ACCEPTANCE.md) 判断，测试方法由 [Test Strategy](../engineering/TEST_STRATEGY.md) 定义。

阻塞项仅限真实影响当前 PR 正确性或可合并性的问题：标准 CI 失败；代码、数据或 Schema 无法正常工作；hash、版本或契约错误；安全或数据损坏风险；来源或科学内容明显失真；Diff 超出 Issue 范围；文档与实现存在实质冲突；Task、Bug 或 Gate 与主要交付 PR 不满足一对一关系；PR 无法合并。风格偏好、非当前范围增强、低概率防御性设计、后续工具改进、不影响当前正确性的理论边界，以及为单次任务增加额外自动化或治理层，默认记录为非阻塞建议。

## 1. 范围与事实来源

- [ ] PR 关联一个且仅一个主要 Task、Bug 或 Gate，或具有可追溯的用户直接授权；Epic 和其他 Issue 只作为补充引用。
- [ ] 主要 Issue 的 `PR 交付计划` 只定义一个交付 PR，不存在 `PR 1`、`PR 2` 或多个连续交付 PR。
- [ ] 主要 Issue 没有其他有效 Open PR；若当前 PR 替代已关闭且未合并的旧 PR，PR 描述已记录 supersede 关系。
- [ ] 当前 PR 不以多个相互独立的 Task、Bug 或 Gate 为主要 Issue。
- [ ] 改动只解决一个清晰目标，没有混入无关重构、依赖升级或格式化。
- [ ] Current、Target、Pending、Superseded 和 Archived 没有混写。
- [ ] 修改前已定位唯一事实来源，没有在低权威文档复制第二套规则。
- [ ] 新增、移动、合并、归档或删除文档已同步 `docs/README.md`。
- [ ] 影响产品承诺、架构取舍或不可逆迁移时，PRD / ADR / Issue 已先对齐。

## 2. Contract 与领域边界

适用于 API、Schema、Workflow、版本或前端数据访问变更：

- [ ] API Contract、Data Model、Workflow 和 Data Versioning 的职责没有互相侵入。
- [ ] Pydantic / OpenAPI / JSON Schema 是 Transport Contract 编写源，没有手写第二套同名 DTO。
- [ ] 组件不直接读取原始 DTO、拼接 URL 或调用外部来源。
- [ ] Project、Run、Artifact、ArtifactVersion、Evidence、SourceSnapshot 和 ShareSnapshot 未混淆。
- [ ] Run status、execution mode、source mode 和 revision 派生关系分别表达。
- [ ] 集合接口、错误、幂等、版本冲突、取消、重试和权限语义有对应测试。
- [ ] `/api` 回归接口没有被静默破坏。

## 3. 科研可信

- [ ] Fixture、recorded、Live、Cached、seed 和 Revision 的真实等级准确。
- [ ] Cached 结果可定位真实历史 Run、ArtifactVersion 和 SourceSnapshot。
- [ ] 数据关键值、PaperSummary 核心内容、Accepted Relation 和 GraphEdge 符合 Evidence 要求。
- [ ] ReasoningTrace 只保存可审查依据，不包含模型私有推理。
- [ ] 模型自由文本未绕过 JSON、Schema、Evidence 或领域准入。
- [ ] 修订创建新版本，不原地覆盖历史产物。
- [ ] 示例、Fixture 或视觉映射没有扩展产品承诺或暗示不存在的科学精度。

## 4. 前端范围与 Authority

适用于所有前端治理文档或实现变更：

- [ ] PR 只解决一个清晰前端目标。
- [ ] DESIGN、WORKSPACE_UX、VISUAL_LANGUAGE、FRONTEND_ARCHITECTURE 与 ADR 一致。
- [ ] Current、Target、Pending 与 Superseded 未混写。
- [ ] 变更未夹带无关后端、基础设施、依赖升级或文档重构。

## 5. 上游源码

适用于上游选型冻结、源码导入和上游同步 PR；非上游变更记录 N/A 及原因：

- [ ] Repository、Tag、Commit 与 License 已固定。
- [ ] 采用与排除目录明确。
- [ ] Upstream → Local 映射完整。
- [ ] 适用版权与 NOTICE 已保留。
- [ ] 未引入不兼容或企业专属目录。
- [ ] 未以截图参考、样式复制或手写相似实现冒充上游采用。
- [ ] 仓库内只有一个 Workspace Shell。

## 6. 架构与状态

适用于前端代码、组件或 Adapter 修改 PR；纯文档 PR 记录 N/A 及原因：

- [ ] 页面通过 Repository Port 消费 Domain。
- [ ] 页面不读取 Transport DTO 或直接调用 `fetch`。
- [ ] App 不跨包读取 Fixture 内部文件。
- [ ] 无路径别名或 `@ts-expect-error` 绕过边界。
- [ ] Router、Query、Workspace Controller 与上游 Runtime 未重复持有同一事实。
- [ ] Run status、execution mode、source mode 与 revision 分别表达。
- [ ] Runtime 不创建 ArtifactVersion、Evidence 或 SourceSnapshot。

## 7. 产品交互

适用于 Workspace UI / Runtime / Adapter / Renderer 功能变更 PR；纯文档或重置宿主 PR 记录 N/A 及原因：

- [ ] Navigation、Agent Activity、Artifact Workspace、Context Inspector 与 Composer 可用。
- [ ] Tool 与 Deliverable 分离。
- [ ] Completed 状态允许继续研究、修订和派生。
- [ ] Loading、Empty、Error、Cancel、Retry 与 Recovery 可用。
- [ ] 核心 Artifact 使用专属 Renderer。
- [ ] Statement / Cell / Claim 可定位 Evidence 与来源。
- [ ] 未知 Artifact / Event 明确失败。
- [ ] 不展示模型私有推理。

## 8. 视觉与可访问性

适用于可见 UI 变更 PR；无界面变更记录 N/A 及原因：

- [ ] 使用语义 Token，无业务组件 Raw Color。
- [ ] 未复制上游默认皮肤。
- [ ] 未以换肤重新设计成熟骨架。
- [ ] 默认界面无全屏深色、卡片墙、IDE 或工程 Preview 风格。
- [ ] 状态不只靠颜色。
- [ ] 中文产品语言优先。
- [ ] 无内部 ID、Hash、Adapter、Fixture 等默认文案。
- [ ] 键盘、焦点、读屏、Reduced Motion 与 200% 字体可用。
- [ ] 1440×900、1280×800 与 390×844 通过。
- [ ] 用户视觉验收已记录。

## 9. 前端测试与退役

按 PR 实际变更范围选择适用项，非适用项可记录 N/A 及原因：

- [ ] Upstream Contract、Unit、Component、Integration 与 E2E 通过。
- [ ] Fixture / HTTP 使用同一组件路径。
- [ ] Build、Architecture、Retirement 与 Compose 通过。
- [ ] 无 Preview Route、假数据、旧 UI 选择器或未消费依赖。
- [ ] 未通过删除测试或降低 Gate 隐藏问题。
- [ ] PR 描述与最终 Diff 一致。

## 10. 后端、数据与 Pipeline

- [ ] Router 只负责传输、授权和 Application Service 调用。
- [ ] Workflow 管理 Run/Step/Event；Pipeline 不推进主状态。
- [ ] PostgreSQL 或明确持久化层是状态事实来源，进程内结构不是唯一事实。
- [ ] 数据来源、查询、单位、转换、质量和 crossmatch 规则可复现。
- [ ] 论文候选记录 Query、来源、去重、排序和选择依据。
- [ ] Prompt、model、producer、参数和 input/output hash 可定位。
- [ ] Graph 无悬空引用，不为视觉效果创建无意义节点或边。
- [ ] 外部来源的超时、限流、无效结构和空结果具有稳定错误分类。

## 11. 安全与隐私

- [ ] 未提交 `.env`、API Key、token、私钥、连接串或真实密码。
- [ ] 浏览器构建变量只包含非敏感配置。
- [ ] Session、CSRF、ownership、Share token、限流和授权在服务端验证。
- [ ] 跨会话私有资源不泄露存在性。
- [ ] 分享锁定明确版本、最小范围、可撤销、可过期且不含编辑会话凭据。
- [ ] 日志和公开错误不含堆栈、密钥、受限全文、完整模型响应或私有推理。
- [ ] CSP、CORS、外部 URL allowlist 和输入长度限制在适用范围内验证。

## 12. 测试与验证证据

- [ ] PR 描述列出实际执行的命令和结果。
- [ ] 未执行项说明原因、风险和替代验证。
- [ ] 使用的测试数据等级明确标记为 Fixture、recorded、Live 或 Cached。
- [ ] 适用的 unit、integration、contract、pipeline、E2E、a11y、visual 或 deployment 测试通过。
- [ ] 生成 Contract、Schema、快照或文档索引没有 stale diff。
- [ ] 回归范围覆盖 Phase 0 和受影响的目标路径。
- [ ] 验证可在声明的环境中重复，不依赖个人电脑隐式状态。

## 13. 文档专项审查

- [ ] 关键规范包含 Status 与 Authority 元数据。
- [ ] 标题层级连续，代码块闭合，表格列数一致，Mermaid 可解析。
- [ ] 相对链接有效，没有指向已删除或移动文件。
- [ ] 同一枚举、状态机、技术栈或提交顺序没有在多份文档重复完整定义。
- [ ] 参考和归档资料明确标记为非规范性。
- [ ] 文档不包含个人本地路径、易失价格、未经核验的当前职位/状态或“最新版”等失效表述。
- [ ] 新规则具有可执行验收，不使用“合理”“完善”“尽量”等模糊结论。

## 14. 正式技术 Review 记录

- [ ] 记录载体是 GitHub Pull Request Review，不是普通 PR Comment、Issue Comment 或线程回复。
- [ ] `evidence_actor_identity` 等于 GitHub API 返回的 Review actor；它与 `reviewer_identity` 分别记录发布账号和实际审查主体。
- [ ] GitHub 可见记录包含 `review_type: technical`。
- [ ] `reviewer_kind` 为 `human | codex | web_gpt | agent` 之一，只记录来源，不决定有效性。
- [ ] `reviewer_identity` 真实可追溯，`review_authorization` 为 `repository_policy` 或 `user_explicit`；未伪造或冒充其他审查主体。
- [ ] `review_purpose` 明确为 `pr_technical_review` 或 `benchmark_scientific_review`，两者不互相替代。
- [ ] `pr_technical_review PASS` 的 scope 精确且仅绑定当前 `pull_request: zyyyyynnn/xingwen-astro-ai#number`；单个 SourcePolicy、Claim 或其他对象范围不能通过 PR Gate。
- [ ] `reviewed_head_sha` 是本次实际审查的 40 位 Commit SHA，且等于 PR 当前 HEAD。
- [ ] `verdict` 明确为 `PASS` 或 `BLOCKED`；普通无结论评论不满足门禁。
- [ ] GitHub state 与 verdict 一致：`APPROVED => PASS`、`CHANGES_REQUESTED => BLOCKED`；`COMMENTED` 正文含独立的匹配 verdict 行。
- [ ] `blocking_findings`、`non_blocking_findings` 和带时区 `reviewed_at` 已记录。
- [ ] GitHub API 已核对 Review 的 repository/PR、actor、state、commit id 和正文；记录的 `evidence_actor_identity` 与 actor 一致，`review_evidence_state` 与 state 一致。
- [ ] 多轮 Review 的最新记录显式 supersede 同 purpose/scope 的上一轮，不存在分叉、循环或未解决的 `BLOCKED` scope。
- [ ] Review 后若出现新 Commit，旧记录已视为 stale，并在新 HEAD 上重新 Review。

## 15. 合并条件

- [ ] 主要 Task、Bug 或 Gate 与当前 PR 满足一对一关系；Epic 仅作为补充引用。
- [ ] 主要 Issue 没有其他有效 Open PR，且其交付计划只定义当前单一 PR。
- [ ] 若当前 PR 是替代 PR，旧 PR 已关闭未合并，且 supersede 关系可追溯。
- [ ] 所有阻塞正式技术 Review 线程已解决。
- [ ] 必要 CI 通过，未通过项没有被绕过。
- [ ] 最新 `pr_technical_review` 的 `reviewed_head_sha` 等于 PR 当前 HEAD，且 verdict 为 `PASS`。
- [ ] 分支可合并，目标 HEAD 未发生未审查变化。
- [ ] PR 描述与最终 Diff 一致。
- [ ] 不扩大 MVP 承诺，不隐藏已知风险。
- [ ] 满足仓库默认 Squash merge 规则。

上述条件满足后，审查者或 Codex 均可将 Draft 转为 Ready、执行 Squash merge，并在 `main` 合并结果核对成功后关闭关联 Issue。条件未满足时不得执行；不存在额外人工 PR Review、负责人二次批准或单独授权评论门。

发布或作品提交前，另按 [Acceptance](../product/ACCEPTANCE.md) 和 [Handoff](../handoff/README.md) 完成阶段级验证。
