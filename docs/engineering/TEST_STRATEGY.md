# Test Strategy

| 元数据    | 值                                           |
| --------- | -------------------------------------------- |
| Status    | Accepted                                     |
| Authority | 测试分层、测试数据等级、环境、门禁和证据格式 |

测试优先保护科研可信链路、领域不变量和自主评审主路径。本文不定义产品何时完成；阶段退出见 [Acceptance](../product/ACCEPTANCE.md)，单个 PR 检查见 [Review Checklist](../quality/REVIEW_CHECKLIST.md)。

## 1. 测试原则

- 先测试不可逆数据损坏、来源失真、权限越权和版本覆盖风险。
- 领域规则与上游骨架合同优先于页面快照数量。
- Research Adapter 独立测试，不通过页面假数据验证。
- Fixture 与 HTTP 使用同一 UI 路径和 Domain ViewModel。
- 外部服务不作为每个 PR 的稳定前置，但必须有可选 Live smoke。
- Fixture、recorded、Live 和 Cached 必须使用相同 Contract，并明确真实等级。
- 无法自动判断的论文相关性、Summary 事实性和 Relation 正确性使用版本化 Benchmark，并由网页端 GPT 科研审查。
- 不为使测试通过恢复已退役 UI。
- 自动化测试不能替代用户视觉验收。
- 测试失败不得通过降低 Evidence、Schema、安全或质量要求规避。

## 2. 测试分层

### Upstream Contract

覆盖选定上游的 Shell、Navigation、Agent Activity、Workspace、Composer、Command、Loading / Empty / Error、Cancel / Retry / Recovery、Keyboard 与 Responsive 行为。

### Unit

**领域与 Pipeline 规则：**
- Case / Field Manifest 与单位转换；
- crossmatch、去重、排序和质量公式；
- Run 状态转换、retry policy 和 CacheSelector；
- Schema、mapper、hash、版本与 supersedes；
- Evidence、Relation 和 Graph 完整性准入；
- C-05 quality RuleSet、Decimal ratio、projected-field applicability、Evidence coverage、Contract gate 和 admission hash。

**前端 Adapter 与 Renderer 映射：**
- Domain → UI ViewModel、Run Event → Research Event、Composer Input → Research Intent、Artifact Kind → Renderer；
- Evidence / Source / Version selection；
- source mode、execution mode、status 与 revision 分离；
- 未知 Artifact / Event 的稳定失败。

### Component

覆盖：

- Navigation 的选择、Pin、Recent、Collapse；
- Agent Activity 的流式事件、Tool、Deliverable、Error 与 Checkpoint；
- Artifact Workspace 的 Docked、Focus、Compare；
- Context Inspector 的历史与焦点恢复；
- Composer 的提交、取消、附件与结构化动作；
- Empty、Draft、Running、Needs Review、Completed、Failed 状态；
- Keyboard、Screen Reader、Reduced Motion 与 200% 字体。

### Integration

覆盖模块协作与契约边界：

- FastAPI Router → Application Service → Repository；
- Workflow → Pipeline Adapter → ArtifactVersion 发布；
- PostgreSQL transaction、lease、Event 和版本登记；
- Qwen/Data/Paper Client 的 stub 或 recorded response；
- Session、CSRF、ownership、Share 和 Problem Details；
- Repository Port → Domain → Research Adapter → Upstream UI；
- 验证 Fixture / HTTP 一致、Run Event 恢复、WorkspaceSnapshot、ArtifactVersion、Evidence、SourceSnapshot、ShareSnapshot 与 Session ownership。

### Contract

覆盖跨边界稳定性：

- Pydantic 生成 OpenAPI 3.1 / JSON Schema；
- operationId、错误、cursor、幂等和授权说明完整；
- generated Transport Type 无 stale diff；
- Fixture 与 recorded payload 通过同一 Schema；
- DTO → Domain mapper 覆盖日期、ID、枚举、版本和错误；
- Phase 0 回归 Contract 未被静默破坏。

### Pipeline and evaluation

使用冻结 Case Manifest 与 Benchmark 验证：

```text
Contract
-> Dataset / FieldDictionary / Quality
-> PaperCollection
-> PaperSummary
-> Claim / Relation / ReasoningTrace
-> Graph / Evidence
```

报告至少包括：

- 数据匹配覆盖率、冲突率、单位和 Evidence 覆盖；
- 论文候选召回、去重和选择依据完整性；
- Summary Schema 通过率、Evidence 覆盖和 unsupported 拦截；
- Relation 科研审核正确率、无证据拦截率和置信度分布；
- Graph 悬空引用、Evidence 完整性和稳定 hash。

### End-to-end

核心路径：

```text
进入 Workspace
→ 新建或选择 Project
→ 确认 Contract
→ 启动 Run
→ 查看 Agent Activity
→ 打开 Artifact
→ 定位 Evidence
→ 打开 Source
→ 完成 Checkpoint
→ 请求修订
→ 查看新 ArtifactVersion
→ Compare
→ Export / Share
→ 刷新恢复
```

同时覆盖 Brand Site 静态首屏、ShareSnapshot、Export、会话过期、授权失败与外部服务降级。（注：Demo Replay 与 Guided Tour 已从当前前端重建基线移除，不作为必选 E2E）。

### Visual and Accessibility

固定视口：

```text
1440×900
1280×800
390×844
200% font scale
```

覆盖 Empty、Running、Needs Review、Completed、Artifact Review、Evidence Inspector、Compare、Error 与移动端。
视觉证据由用户确认。页面隐藏暂停与资源释放、关键 Web Vitals 预算保持验证。

## 3. 测试数据等级

| 等级              | 用途                              | 能否表述为真实结果                      |
| ----------------- | --------------------------------- | --------------------------------------- |
| Fixture           | Unit、组件、视觉回归             | 否；必须标记 scenario 与 schema version |
| Recorded response | 稳定集成测试                      | 否；只能说明为录制的外部响应            |
| Benchmark / seed  | 网页端 GPT 科研审查、回归、校验   | 否；不能冒充自动获取                    |
| Live result       | 可选 Live smoke 或真实运行        | 是；必须保留来源、时间和参数            |
| Real run cache    | Live 失败后的可审查兜底           | 是，但必须标记 Cached 并定位 origin Run |

测试数据不得从低等级静默升级为高等级。Recorded response 和 Benchmark 不进入 CacheSelector。

D-02 的 Crossref 单元/集成测试使用 fixture 或 recorded response 并标记 `source_mode=fixture`；真实来源测试使用 `live` marker 与 `XINGWEN_RUN_LIVE_PAPER_TEST=1` 显式启用。命令、数据等级和来源记录见 [PaperCollection Pipeline](PAPER_COLLECTION_PIPELINE.md)。

## 4. 环境矩阵

| 环境             | 主要用途                                                       | 外部服务                                          |
| ---------------- | -------------------------------------------------------------- | ------------------------------------------------- |
| local            | 快速开发、Unit、Component                                      | 默认 stub/Fixture                                 |
| CI               | 稳定 Contract、PostgreSQL Integration、Fixture + real HTTP E2E | stub/recorded + fresh Compose，禁止依赖不稳定公网 |
| preview          | 浏览器、路由、安全和部署 smoke                                 | 受控 Live 或专用测试凭据                          |
| production smoke | 发布后关键路径                                                 | 限制主案例和调用额度                              |

敏感凭据只存在于受控环境，不写入 Fixture、录制数据或测试日志。

## 5. 阶段门禁

### 当前重置与宿主基线 (Reset & Host Baseline)

- Workspace 仅要求 `apps/workspace` 宿主 Router、Runtime Composition、Repository Port 与 Minimal Host Route 可运行并通过 build/architecture/retirement 校验；
- 不要求当前重置宿主完成完整 Agent 产品主链路 E2E。

### 目标 Agent 产品验收 (Target Workspace Acceptance)

- 适用时期：ADR-032 冻结上游选型与 F-03~F-08 骨架及 Adapter 落地后；
- 覆盖 Session → Project → Contract → Run → Artifact → Evidence → Revision → Share 产品链。

## 6. 覆盖策略

不以单一全局覆盖率代替关键风险测试。以下能力缺少对应测试时不得合并：

- 状态机、幂等、取消和派生 Run；
- Contract 与 Domain mapper；
- Evidence / Relation / Graph 准入；
- 字段、单位、crossmatch 和质量规则；
- ArtifactVersion、CacheSelector 和 RevisionPlan；
- Session、Share、CSRF 和跨会话授权；
- 视觉与渲染 fallback 与资源释放。

包级覆盖率阈值可在实现 Issue 中冻结，但不得通过排除关键文件虚增指标。

## 7. 测试证据格式

PR 或阶段报告至少记录：

- 上游 Repository、Tag、Commit 与 License（若涉及前端）；
- 命令和环境；
- Commit、Contract、Fixture/Benchmark 版本；
- 通过、失败和跳过数量；
- 使用的数据等级（Fixture / Live / Cached / Revision）；
- 截图路径与用户视觉结论；
- 未执行项及原因、剩余风险。

“本地通过”但没有命令、版本、截图和结果摘要，不构成可复现证据。
