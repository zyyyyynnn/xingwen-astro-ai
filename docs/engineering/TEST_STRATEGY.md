# Test Strategy

| 元数据    | 值                                           |
| --------- | -------------------------------------------- |
| Status    | Accepted                                     |
| Authority | 测试分层、测试数据等级、环境、门禁和证据格式 |

测试优先保护科研可信链路、领域不变量和自主评审主路径。本文不定义产品何时完成；阶段退出见 [Acceptance](../product/ACCEPTANCE.md)，单个 PR 检查见 [Review Checklist](../quality/REVIEW_CHECKLIST.md)。

## 1. 测试原则

- 先测试不可逆数据损坏、来源失真、权限越权和版本覆盖风险。
- 领域规则优先于页面快照数量。
- 外部服务不作为每个 PR 的稳定前置，但必须有可选 Live smoke。
- Fixture、recorded、Live 和 Cached 必须使用相同 Contract，并明确真实等级。
- 无法自动判断的论文相关性、Summary 事实性和 Relation 正确性使用版本化 Benchmark，并由网页端 GPT 科研审查。
- 测试失败不得通过降低 Evidence、Schema、安全或质量要求规避。

## 2. 测试分层

### Unit

覆盖纯规则和边界：

- Case / Field Manifest 与单位转换；
- crossmatch、去重、排序和质量公式；
- Run 状态转换、retry policy 和 CacheSelector；
- Schema、mapper、hash、版本与 supersedes；
- Evidence、Relation 和 Graph 完整性准入；
- 前端 selector、quality tier 和 Visual Model mapper。

### Component

覆盖可访问的 UI 行为：

- Research Contract 编辑与确认；
- Atlas、受控 Split Panels、Observatory 和 Console；
- Dataset、Paper、Summary、Reasoning、Graph 和 Feedback 状态；
- Fixture/Live/Cached/Revision、错误、空和部分结果；
- 键盘、焦点、读屏、Reduced Motion 和 Poster fallback。

### Integration

覆盖模块协作：

- FastAPI Router → Application Service → Repository；
- Workflow → Pipeline Adapter → ArtifactVersion 发布；
- PostgreSQL transaction、lease、Event 和版本登记；
- Qwen/Data/Paper Client 的 stub 或 recorded response；
- Session、CSRF、ownership、Share 和 Problem Details；
- Fixture / HTTP Repository Adapter 的 Domain 一致性。
- 真实 PostgreSQL + FastAPI Runtime 的 Session → Project → Contract → Run/Event → ArtifactVersion/Evidence → Workspace/Share 链路；
- fresh Compose 上不使用 MSW 的真实 HTTP Browser、冲突、刷新恢复与匿名 Share。

### Contract

覆盖跨边界稳定性：

- Pydantic 生成 OpenAPI 3.1 / JSON Schema；
- operationId、错误、cursor、幂等和授权说明完整；
- generated Transport Type 无 stale diff；
- Fixture 与 recorded payload 通过同一 Schema；
- DTO → Domain mapper 覆盖日期、ID、枚举、版本和错误；
- v1 回归 Contract 未被静默破坏。

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

覆盖核心用户路径：

- Brand Site 静态首屏与 Guided Tour；
- Demo Replay 完整流程；
- Project → Draft → Contract → Live Run；
- Dataset / Summary / Relation / Graph 到 Evidence；
- Run Event 断线恢复；
- Feedback → RevisionPlan → revision Run → 新 Version；
- ShareSnapshot、Export、会话过期和授权失败；
- 外部服务失败、缓存建议和无缓存失败。

### Visual and performance

- 固定 viewport、seed、时间和数据版本的视觉回归；
- High / Medium / Low 图形质量；
- WebGL/context loss、Poster 和 Reduced Motion；
- 页面隐藏暂停与资源释放 smoke；
- 大表虚拟化、Graph 规模和关键 Web Vitals 预算。

## 3. 测试数据等级

| 等级              | 用途                              | 能否表述为真实结果                      |
| ----------------- | --------------------------------- | --------------------------------------- |
| Fixture           | Unit、组件、Demo Replay、视觉回归 | 否；必须标记 scenario 与 schema version |
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

### M1

- Foundation、frozen install/sync、lint、typecheck、unit、build；
- Schema/OpenAPI 生成和 stale check；
- 当前 v1 回归、A-01 Site/Workspace 入口与共享包 smoke；
- Fixture/HTTP Domain 一致性；
- PostgreSQL 17、Alembic upgrade、真实 FastAPI Runtime 与 `/api` 回归；
- fresh Compose 的 `postgres → migrate → api → workspace` 与真实 HTTP Browser/刷新恢复/Share 撤销；
- 静态首屏、键盘和 WebGL fallback。

### X-06

增加数据库 Integration、数据/论文 Pipeline、Artifact/Evidence、A-04～A-06 E2E 和固定 Benchmark。

### X-07

增加 Relation 准入、Trace 安全、Graph 完整性、A-07/A-08 E2E 和评测指标。

### X-08

增加版本事务、并发冲突、CacheSelector、RevisionPlan、Session/Share 安全、部署 smoke、材料 provenance 和降级验证。

## 6. 覆盖策略

不以单一全局覆盖率代替关键风险测试。以下能力缺少对应测试时不得合并：

- 状态机、幂等、取消和派生 Run；
- Contract 与 Domain mapper；
- Evidence / Relation / Graph 准入；
- 字段、单位、crossmatch 和质量规则；
- ArtifactVersion、CacheSelector 和 RevisionPlan；
- Session、Share、CSRF 和跨会话授权；
- Visual Engine fallback 与资源释放。

包级覆盖率阈值可在实现 Issue 中冻结，但不得通过排除关键文件虚增指标。

## 7. 测试证据格式

PR 或阶段报告至少记录：

- 命令和环境；
- Commit、Contract、Fixture/Benchmark 版本；
- 通过、失败和跳过数量；
- 未执行项及原因；
- 使用的数据等级；
- Live 依赖和降级行为；
- 失败日志或报告位置；
- 性能/评测指标及与基线的差异。

“本地通过”但没有命令、版本和结果摘要，不构成可复现证据。
