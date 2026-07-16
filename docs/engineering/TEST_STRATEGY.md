# Test Strategy

测试优先保护科研可信链路和可演示主路径，而不是追求无差别覆盖率。

## 1. 分层

### Unit

覆盖：

- 状态转换；
- 字段/单位规则；
- 论文去重和相关性规则；
- Schema 校验；
- Evidence/Relation 准入；
- hash 与版本规则。

### Integration

覆盖：

- FastAPI + application service；
- repository + PostgreSQL；
- Qwen/Paper/Data Client 的 stub；
- WorkflowHooks 状态持久化；
- 错误结构和 request_id。

### Contract

覆盖：

- Pydantic JSON Schema 可导出；
- OpenAPI 与前端生成类型无漂移；
- fixtures 符合 Schema；
- API_CONTRACT/DATA_MODEL 变更对应测试更新。

### Pipeline

使用固定主案例样例，验证：

```text
goal
-> Dataset
-> PaperCandidate
-> PaperSummary
-> Claim/Relation/Trace
-> Graph/Evidence
```

外部服务默认使用录制或 stub；另设可选 live smoke，不作为每个 PR 的稳定门槛。

### Evaluation

人工标注小样例集，评估：

- 论文相关率；
- Summary 事实一致性；
- Evidence 覆盖率；
- Relation 正确率；
- 无证据候选拦截率；
- 缓存标识准确率。

## 2. CI 门槛

每个 PR 至少执行：

1. repository foundation check；
2. 前端 frozen install + build；
3. 后端 frozen sync + pytest；
4. Pydantic Schema 导出；
5. `docker compose config`。

进入 Phase 1 后增加数据库集成测试；Phase 2 增加 Pipeline/Evaluation；Phase 3 增加缓存、修正和部署 smoke。

## 3. 测试数据分级

| 类型 | 用途 | 可否作为真实结果 |
| --- | --- | --- |
| fixture | 单元、前端联调、Demo Replay | 否，必须明确标注 |
| recorded response | 稳定集成测试 | 仅标注为录制来源 |
| seed list | 评测基准、fallback | 不可冒充自动获取 |
| real run cache | Demo 兜底 | 可以，但必须 cached |
| live result | 实时链路 | 可以，保留来源 |

## 4. 最低覆盖门槛

Phase 0 不设置虚假的全局百分比门槛，但以下代码必须有测试：

- 状态机；
- Evidence 准入；
- Relation 准入；
- 数据单位转换；
- 缓存选择；
- 安全配置校验。

新增关键规则没有对应测试时不得合并。

## 5. 可复现报告

PR 验证说明必须写：

- 命令；
- 环境；
- 通过/失败结果；
- 未执行项及原因；
- 是否使用 stub、recorded、cache 或 live；
- 外部服务失败时的降级行为。
