# Review Checklist

| 元数据    | 值                                 |
| --------- | ---------------------------------- |
| Status    | Accepted                           |
| Authority | 单个 Pull Request 的审查与合并清单 |

本清单回答“这个 PR 是否可以合并”。里程碑和作品是否完成由 [Acceptance](../product/ACCEPTANCE.md) 判断，测试方法由 [Test Strategy](../engineering/TEST_STRATEGY.md) 定义。

## 1. 范围与事实来源

- [ ] PR 关联明确 Issue 或用户授权。
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
- [ ] `/api/v1` 回归接口没有被静默破坏。

## 3. 科研可信

- [ ] Fixture、recorded、Live、Cached、seed 和 Revision 的真实等级准确。
- [ ] Cached 结果可定位真实历史 Run、ArtifactVersion 和 SourceSnapshot。
- [ ] 数据关键值、PaperSummary 核心内容、Accepted Relation 和 GraphEdge 符合 Evidence 要求。
- [ ] ReasoningTrace 只保存可审查依据，不包含模型私有推理。
- [ ] 模型自由文本未绕过 JSON、Schema、Evidence 或领域准入。
- [ ] 修订创建新版本，不原地覆盖历史产物。
- [ ] 示例、Fixture 或视觉映射没有扩展产品承诺或暗示不存在的科学精度。

## 4. 前端与交互

适用于 Brand Site、Guided Tour、Workspace、设计系统或 Visual Engine：

- [ ] Site、Workspace、shared packages 的依赖方向符合 Frontend Architecture。
- [ ] 工作台以科研产物为主，不退化为聊天流、工具日志、IDE 或无限窗口。
- [ ] 中央 Canvas 不超过三个受控面板。
- [ ] Raw Color、字体、动效和 ASCII/Dither 规则符合 Visual Language。
- [ ] 关键状态不只靠颜色表达，键盘、焦点、读屏和 200% 字体缩放可用。
- [ ] WebGL、字体或 JavaScript 失败时仍有 DOM 内容、Poster 和主操作。
- [ ] 页面隐藏时暂停实时渲染，卸载时释放 GPU 和观察器资源。
- [ ] 外部 HTML、URL 和用户文本按安全规则校验或净化。

## 5. 后端、数据与 Pipeline

- [ ] Router 只负责传输、授权和 Application Service 调用。
- [ ] Workflow 管理 Run/Step/Event；Pipeline 不推进主状态。
- [ ] PostgreSQL 或明确持久化层是状态事实来源，进程内结构不是唯一事实。
- [ ] 数据来源、查询、单位、转换、质量和 crossmatch 规则可复现。
- [ ] 论文候选记录 Query、来源、去重、排序和选择依据。
- [ ] Prompt、model、producer、参数和 input/output hash 可定位。
- [ ] Graph 无悬空引用，不为视觉效果创建无意义节点或边。
- [ ] 外部来源的超时、限流、无效结构和空结果具有稳定错误分类。

## 6. 安全与隐私

- [ ] 未提交 `.env`、API Key、token、私钥、连接串或真实密码。
- [ ] 浏览器构建变量只包含非敏感配置。
- [ ] Session、CSRF、ownership、Share token、限流和授权在服务端验证。
- [ ] 跨会话私有资源不泄露存在性。
- [ ] 分享锁定明确版本、最小范围、可撤销、可过期且不含编辑会话凭据。
- [ ] 日志和公开错误不含堆栈、密钥、受限全文、完整模型响应或私有推理。
- [ ] CSP、CORS、外部 URL allowlist 和输入长度限制在适用范围内验证。

## 7. 测试与验证证据

- [ ] PR 描述列出实际执行的命令和结果。
- [ ] 未执行项说明原因、风险和替代验证。
- [ ] 使用的测试数据等级明确标记为 Fixture、recorded、Live 或 Cached。
- [ ] 适用的 unit、integration、contract、pipeline、E2E、a11y、visual 或 deployment 测试通过。
- [ ] 生成 Contract、Schema、快照或文档索引没有 stale diff。
- [ ] 回归范围覆盖当前 v1 和受影响的目标路径。
- [ ] 验证可在声明的环境中重复，不依赖个人电脑隐式状态。

## 8. 文档专项审查

- [ ] 关键规范包含 Status、Authority 和必要的 Implementation 状态。
- [ ] 标题层级连续，代码块闭合，表格列数一致，Mermaid 可解析。
- [ ] 相对链接有效，没有指向已删除或移动文件。
- [ ] 同一枚举、状态机、技术栈或提交顺序没有在多份文档重复完整定义。
- [ ] 参考和归档资料明确标记为非规范性。
- [ ] 文档不包含个人本地路径、易失价格、未经核验的当前职位/状态或“最新版”等失效表述。
- [ ] 新规则具有可执行验收，不使用“合理”“完善”“尽量”等模糊结论。

## 9. 合并条件

- [ ] 所有阻塞 Review 线程已解决。
- [ ] 必要 CI 通过，未通过项没有被绕过。
- [ ] 分支可合并，目标 HEAD 未发生未审查变化。
- [ ] PR 描述与最终 Diff 一致。
- [ ] 不扩大 MVP 承诺，不隐藏已知风险。
- [ ] 满足仓库默认 Squash merge 规则。

发布或作品提交前，另按 [Acceptance](../product/ACCEPTANCE.md) 和 [Handoff](../handoff/README.md) 完成阶段级验证。
