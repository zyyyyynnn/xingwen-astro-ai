# Error Handling

| 元数据    | 值                                           |
| --------- | -------------------------------------------- |
| Status    | Accepted                                     |
| Authority | 内部错误分类、传播、日志关联和用户可执行反馈 |

HTTP 状态、Problem Details 字段和授权错误的唯一事实来源是 [API Contract](../architecture/API_CONTRACT.md)。本文说明错误如何在 Router、Application、Workflow、Pipeline 和前端之间传播。

## 1. 原则

错误处理必须同时满足：

- 不把部分失败、缓存结果或无效模型输出包装成科研成功；
- 用户能判断影响范围和下一步操作；
- 开发者能通过 request、Run、Step 和 ProducerExecution 定位；
- 自动重试、用户重试、缓存和修订使用不同语义；
- 公开响应与日志不泄露敏感信息或受限内容。

## 2. Current 与 Target

- 当前 Pipeline `/api` 保持既有 Task error envelope 和回归行为。
- 目标核心 `/api` 只使用 RFC 9457 Problem Details，不维护第二套 v2 错误 Envelope。
- v1 和 v2 可以使用不同传输结构，但必须映射到稳定内部错误分类。

## 3. 内部错误分类

| 分类               | 示例                              | 默认策略                           |
| ------------------ | --------------------------------- | ---------------------------------- |
| validation         | Schema、非法枚举、Contract 不满足 | 不重试，返回可定位字段错误         |
| authentication     | 会话缺失或过期                    | 结束当前写操作，要求重新建立会话   |
| authorization      | CSRF、动作禁止                    | 不重试，不泄露额外资源信息         |
| not_found          | 资源不存在或跨会话私有资源        | 不重试，使用不泄露存在性的响应     |
| conflict           | 状态、乐观锁、幂等或版本冲突      | 拉取最新快照后由用户或应用决定     |
| external_transient | 超时、限流、临时 5xx              | 有限自动重试；满足规则时可建议缓存 |
| external_permanent | 凭据、许可、来源禁用              | 不自动重试，停止受影响步骤         |
| upstream_invalid   | 外部或模型返回不可校验结构        | 不直出，记录 producer 失败         |
| quality_gate       | Evidence 或质量约束不满足         | 不发布 ArtifactVersion             |
| internal           | 未分类异常                        | 安全 5xx，保留内部 cause           |

错误码必须稳定、可测试，不直接使用异常类名或第三方文本作为公开 code。

## 4. 传播边界

### Router

- 解析请求、调用 Application Service、映射公开响应；
- 不捕获后继续执行科研步骤；
- 不返回堆栈或上游原始响应。

### Application Service

- 验证 Session、ownership、状态和幂等；
- 将领域错误映射为稳定公开错误；
- 决定操作是否允许重试、取消或派生。

### Workflow

- Step 失败先记录 StepAttempt 和 RunEvent；
- 非法状态转换立即拒绝；
- 自动瞬态重试保留每次 Attempt；
- 终态 Run 不静默恢复为 running；
- 用户 retry、revision 或 fork 创建派生 Run；
- 缓存选择保留本次 Live 失败和选择原因。

### Pipeline / Producer

- 保留内部 cause 和上游 request id；
- 返回结构化错误，不推进 Run 主状态；
- Schema、Evidence 或质量门失败时不得发布产物。

## 5. 前端展示

前端错误展示至少回答：

1. 什么操作或步骤失败；
2. 哪些产物仍然有效；
3. 是否可以自动重试、用户重试、修改 Contract 或使用缓存；
4. 当前展示是否来自 Fixture / Live / Cached；
5. 可复制的 request id 或 Run id。

有缓存时同时显示“本次 Live 失败”和“当前展示历史缓存”。不得使用“完成”描述部分失败或未通过 Evidence 门的结果。

## 6. 日志关联

建议统一字段：

```text
timestamp
level
request_id
session_id_hash
project_id
run_id
step_key
attempt_number
producer_execution_id
artifact_version_id
source_snapshot_id
error_code
upstream_request_id
duration_ms
```

仅记录定位所需字段。原始 Session、Share token、密钥、完整连接串、受限全文、未截断模型响应和私有推理不得进入日志。

## 7. 重试与缓存

- 自动重试只处理明确瞬态错误，并遵守 retry policy；
- Schema、Evidence、权限、非法状态和 Contract 错误不可自动重试；
- CacheSelector 只在 Live 可恢复失败后运行；
- 缓存不匹配当前 Contract、质量或 Evidence 要求时，保持失败；
- 前端不得仅凭 HTTP code 自行推断缓存适用性。

## 8. 验证

错误相关改动至少覆盖：

- 内部错误到 v1/v2 公开响应映射；
- 401/403/404 不泄露资源存在性；
- 409 状态、版本和幂等冲突；
- 自动 retry 与用户派生 Run 的差异；
- 上游超时、限流、无效结构和永久失败；
- Evidence / quality gate 阻断发布；
- 日志脱敏和 request/run/step 关联；
- 前端失败、缓存建议和可执行下一步。
