# Review Checklist

| 元数据 | 值 |
| --- | --- |
| Authority | Pull Request exact-head 正式技术 Review 与合并清单 |

本清单回答“当前这个 exact HEAD 是否具备合并资格”。产品退出另见 [Acceptance](../product/ACCEPTANCE.md)。

## 1. Freeze

- [ ] 已记录 PR exact HEAD、base、当前 `main` 与 merge-base。
- [ ] 已确认冻结后 `main` 是否漂移；若漂移，没有静默吸收。
- [ ] 审查的是完整 PR diff，不只是最后一个 repair Commit。
- [ ] 当前 PR body、CI 与 Review evidence 都对应这个 HEAD。

## 2. Delivery Scope

- [ ] Delivery Mode 是默认 Atomic 或明确授权的 Grouped。
- [ ] Atomic PR 对应一个主要 Issue/任务；Grouped PR 的多个 Issue 属于同一 vertical closure，并有逐 Issue acceptance/evidence matrix。
- [ ] 同一 Issue 没有两个竞争的有效主要 Open PR。
- [ ] 无无关重构、顺手清理、过程文件、阶段编号或历史兼容包袱。
- [ ] PR/Commit title 符合 CONTRIBUTING。

## 3. Correctness / Architecture

- [ ] 正常路径、边界、失败、重试、并发与资源释放正确。
- [ ] Current-only：没有旧/new 双 API、双 schema、旧 facade、compatibility layer 或动态 latest 读取。
- [ ] Domain、Repository、Workflow、Publisher、Evidence、Revision、Renderer、Workspace 的单一 owner 未被绕过。
- [ ] 没有 generic framework/registry/hash/audit abstraction 只为本 PR 存在。
- [ ] Generated Contract 与生产模型同步，无 stale diff。

## 4. Integration Cohesion

若 PR 新增或迁入成熟能力：

- [ ] 先做 current-main capability gap，没有重复已有或更优实现。
- [ ] 能力被吸收到现有 runtime/Artifact/Evidence/UX，而不是 sidecar 或功能岛。
- [ ] 没有第二 Planner/Agent runtime/Worker/Publisher/Evidence store/Graph backend/Revision engine/Renderer family/Shell。
- [ ] 临时 bridge、raw JSON semantic bus、wrapper-on-wrapper 和旧 facade 已删除。
- [ ] 用户不需要理解内部实现来源或模块结构即可使用。
- [ ] 源码级采用的许可证、NOTICE/attribution 与机器 provenance 完整，但不把来源标识写入治理 Markdown。

## 5. Scientific Trust

- [ ] Live/Cached/Recorded/Fixture/Benchmark/Revision 语义准确。
- [ ] 关键 data/Summary/Accepted Relation/GraphEdge/科学结论可解析到真实 Evidence/SourceSnapshot/locator。
- [ ] ReasoningTrace 是公开可审查依据，不含 provider private chain-of-thought。
- [ ] ArtifactVersion immutable；Revision 产生新版本并保持 supersedes/parent lineage。
- [ ] 哈希只存在于真正 identity/provenance/integrity 边界。

## 6. Product / Frontend

- [ ] 所有用户承诺能力从正式浏览器入口可达；backend-only/test-only 不被标记完成。
- [ ] Loading/empty/error/refusal/partial/unsupported/recovery 都可理解。
- [ ] 单一 Fullscreen Result Workspace、Evidence presentation、Renderer Registry 与 Public Share presentation 未被复制。
- [ ] touched business UI 使用 semantic tokens / `@xingwen/ui` / mature primitives，无无意义 arbitrary visual numbers。
- [ ] UI 不暴露内部 ID/hash/raw enum/producer/adapter/Issue/PR 编号或能力来源边界。
- [ ] Graph/Diff/Revision/Share 等高风险体验有真实语义，不用 count-only、raw JSON 或静态 mock 替代。

## 7. Security / Competition

- [ ] Secrets、token、认证头、私有 provider response 与 private reasoning 未泄露。
- [ ] Session ownership、CSRF/CORS、public share freeze/redaction/expiry/revoke 按 Authority 工作。
- [ ] 竞赛主案例的合格模型调用没有被非合格 provider、Fixture、Recorded 或外部 benchmark 冒充。

## 8. Documentation

- [ ] 修改公共 Contract、领域实体、Workflow、安全、UX 或发布规则时已同步对应唯一 Authority。
- [ ] 治理 Markdown 只描述本项目当前事实，不含外部参考项目/上游产品名称、仓库 URL、tag、commit、迁移来源标签或具体过程标识。
- [ ] 法律归因与精确来源只存在于 NOTICE/LICENSE/THIRD_PARTY_NOTICES 或机器 provenance。
- [ ] 没有把实施 Prompt、迁移矩阵、审查历史或过程状态写入 Authority。

## 9. Verification

- [ ] 针对性 Unit/Contract/Integration 已通过。
- [ ] 风险涉及数据库/Worker/Publisher 时有真实 PostgreSQL/vertical proof。
- [ ] 用户功能有 Browser proof；正式产品 closure 覆盖 keyboard、200% text 与核心 viewport。
- [ ] 没有通过删除断言、降低 Evidence gate、伪造 Fixture 或过度 snapshot 获得绿色测试。
- [ ] CI claim 已独立核对；无法绑定 exact HEAD 的检查明确写“未独立验证”。

## 10. Adversarial Omission Sweep

完成第一次 findings 后，必须再单独检查：

- 新能力是否只在某层“看起来存在”而没有产品闭环；
- 是否出现第二事实源或 duplicated presentation；
- same-count / same-status 但真实 Evidence 内容变化是否被漏掉；
- partial/unsupported/failure 是否被吞掉；
- 新增能力是否只是表面接入而未真正融入统一产品链；
- 200% text、长内容、权限边界、revoked/expired share 是否遗漏；
- 是否有更简单、复用更多、删除更多的实现。

## 11. Formal Review Output

- 一个 exact HEAD 提交一个正式 GitHub Review；默认 action 为 `COMMENT`。
- 正文明确 `verdict: PASS`、`verdict: NOT READY` 或 `verdict: BLOCKED`，并列出 blocker / non-blocker / verification limits。
- NOT READY/BLOCKED 时给出一个窄、可执行、不扩 scope 的 repair Prompt。
- 新 Commit 使旧 Review stale；必须重新 full-diff review。
- Reviewer 不自动 merge、mark Ready、auto-merge、close Issue，也不静默替实现者修复实质代码问题。
