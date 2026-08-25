# Test Strategy

| 元数据 | 值 |
| --- | --- |
| Authority | 测试分层、真实性等级、质量门禁与证据格式 |

## 1. 原则

测试服务于高风险不变量与真实用户闭环，而不是追求测试数量。

优先保护：Contract、Evidence、immutability、Publisher atomicity、lease/recovery、permissions/security、Fixture/HTTP parity、能力融合正确性、Browser reachability、accessibility 和主案例竞赛证据。

Green tests 是必要条件，不是产品完成定义。

## 2. 分层

### Adopted Interaction Contract

当前 Workspace 已采用的成熟交互骨架必须独立验证：批准的交互范围、机器 provenance/source-policy、实际 import closure、无孤立旧 facade，以及 Navigation/Thread/Activity/Composer/Command/Resize/Scroll/Focus 的关键行为。隐私与领域排除规则优先于机械 import 可达性。

### Unit / Contract

覆盖：

- Domain invariants、Schema/admission、Mapper；
- mapping/unit/quality/cross-match；
- Claim/Relation/ReasoningTrace/Graph integrity；
- ArtifactVersion/SourceSnapshot/Evidence identity；
- Revision target 与 cache selection；
- exhaustive Renderer Registry；
- 新增或迁入算法的确定性科学正确性。

### Component

覆盖真正的交互状态：Navigation、Composer、Activity grouping/disclosure、Contract review、Fullscreen、Evidence Inspector、Graph、Scientific Diff、Revision、Share、keyboard/focus/reduced-motion。

不要长期维护只断言 CSS class、Badge 数量、单条文案、组件树 hash 或大面积 snapshot 的低价值测试。

### Integration

优先真实：

```text
FastAPI
→ Application Service
→ PostgreSQL Repository
→ ResearchRun Worker
→ Scientific Step / Pipeline
→ ProducerExecution
→ Publisher
→ ArtifactVersion / Evidence
→ RunEvent / Repository read
```

不 mock 掉 `_load_context`、RunStep 转换、ProducerExecution、Publisher 或数据库事务后再宣称纵向链通过。

### Browser / E2E

对于用户承诺能力，至少验证：

```text
formal product entry
→ Research Intent / Project
→ Contract / Run
→ Activity / Artifact
→ Evidence
→ applicable Diff / Revision / Export / Share
```

大型产品 PR 应以少量高价值 verticals 覆盖主要 Artifact family，而不是给每个组件堆 UI test。

Browser Gate 必须包含真实 failure/refusal/partial/unsupported、安全 share state、键盘路径、200% text 与三个正式桌面 viewport。Graph 需覆盖 canvas selection、edge Evidence 与 list fallback；Diff 需覆盖 Evidence 数量不变但来源替换；Revision 需覆盖 feedback → plan → derived result。

### Live / Benchmark

Live proof 用于验证真实 provider/source/model 行为；Benchmark 用固定输入与指标评估质量。二者不可互相替代。

外部对照 benchmark 只能说明对照；进入本项目后的能力需要自己的 current-main benchmark 或 vertical proof。

跨层回归至少保护以下当前高风险边界：Contract confirmation 的 persisted-resource 幂等、Run authoring fail-closed、derived/revision/cache target、Planner/ModelExecutionPort 未绑定时的拒绝语义、Executor lease/recovery、Open Access PaperCandidate → ResearchInput、snapshot-first RunEventFeed pagination/polling/backoff、exhaustive Renderer Registry、共享 Evidence Inspector、partial/unsupported document parsing、ArtifactVersion immutable revision。

## 3. 数据真实性等级

| 等级 | 用途 | 要求 |
| --- | --- | --- |
| Fixture | Unit / component | 明确 fixture/scenario，不作为能力宣传 |
| Recorded | 稳定外部响应回归 | 标注来源与录制语义 |
| Benchmark | 固定科学评估 | 固定输入、指标、版本与限制 |
| Live | 真实运行 | 保存真实 Run/SourceSnapshot/provider facts |
| Cached | 真实历史 Run 的复用 | 指向 origin Run，说明当前失败/选择原因 |
| Revision | 派生运行结果 | 绑定 parent/confirmed plan/supersedes |

合格模型测试必须区分 Alibaba Cloud Model Studio / Bailian 的 Qwen 真实调用证据与 DeepSeek、Gemini 等 non-qualifying benchmark/reference。没有 provider/model/version 或 revision/call proof 的测试只证明契约或 Adapter 行为，不证明竞赛资格。

## 4. 能力融合验证

新增或迁入能力至少验证：

1. 当前 `main` 已有行为未被重复实现；
2. 新能力进入现有 runtime/Artifact/Evidence，不旁路写第二事实源；
3. 临时 bridge 与重复 facade 已删除；
4. failure/unsupported 没被适配层吞掉；
5. 用户能从正式 Workspace 使用；
6. 对科学算法有确定性 unit/benchmark，对产品能力有 integration/browser proof；
7. 源码级采用的许可证和机器 provenance 完整。

不要求为每个外部文件做 SHA 列表或测试；只保护实际采用边界和必要 aggregate provenance。

## 5. NFR

前端产品变更按风险覆盖：

- Light 1440×900、1280×800、1024×768；
- 200% text 不遮挡关键内容或破坏 Graph 几何；
- keyboard、focus restore、screen reader、reduced motion；
- lazy chunk / initial JS、长 Activity、长表/大图与长会话内存；
- polling/backoff/cancel/timeout 不产生请求风暴或状态倒退。

## 6. 证据格式

PR/Review 报告只记录实际执行：exact HEAD、环境、命令、pass/fail/skip 数量、数据等级、外部 provider/source、未执行项和已知风险。旧 HEAD 的 CI 不作为新 Commit 的证据。
