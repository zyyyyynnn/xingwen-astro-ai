# Error Handling

> 当前 `/api/v1` 仍使用 Task 错误 Envelope；目标 `/api/v2` 使用 `application/problem+json`。目标实现、错误码与授权语义以 [API_CONTRACT.md](../architecture/API_CONTRACT.md) 为准。

## 1. 目标

错误处理必须同时满足：

- 用户能理解当前步骤是否失败、可重试或使用缓存；
- 开发者能通过 request/task/step 定位；
- 日志不泄露密钥和受限内容；
- 不把部分失败包装成科研成功。

## 2. 公开错误结构

当前 `/api/v1` 错误保持：

```json
{
  "error": {
    "code": "stable_machine_code",
    "message": "safe user-facing message",
    "request_id": "request identifier",
    "details": {}
  }
}
```

`details` 只放非敏感、可行动信息。堆栈和第三方原始响应只进入受控日志。

目标 `/api/v2` 使用 RFC 9457 Problem Details，并至少返回 `type`、`title`、`status`、`detail`、`code`、`request_id`；字段级错误进入受限 `errors` 列表。不得同时维护第二套 v2 错误 Envelope。

## 3. 错误分类

| 分类 | 示例 | 默认处理 |
| --- | --- | --- |
| validation | Schema、非法枚举、状态跳转 | 不重试，返回 4xx |
| not_found | task/evidence/paper 不存在 | 不重试，返回 404 |
| conflict | 乐观状态更新失败、版本冲突 | 刷新状态后决定 |
| external_transient | 超时、限流、5xx | 有限重试/缓存 |
| external_permanent | 鉴权失败、来源禁止 | 不重试，告警 |
| model_invalid | JSON/Schema/Evidence 校验失败 | 有限修复重试，不能直出 |
| internal | 未分类异常 | task 失败，返回安全 5xx |

## 4. Workflow 错误

- 当前 v1 先记录 TaskStep 失败，再转 ResearchTask `failed`。
- 目标 v2 先记录失败的 StepAttempt 与 RunEvent，再按 `WORKFLOW_DESIGN.md` 转 ResearchRun `failed` 或继续允许的恢复路径。
- 非法状态转换使用稳定错误码。
- 瞬时自动重试创建新的 StepAttempt；用户重试、修订或分叉创建带 parent / derivation 关系的新 Run。
- 缓存兜底保留实时错误分类和选择理由。
- 局部修正创建 revision Run 与新 ArtifactVersion，不改变或隐藏原 Run 的失败/完成事实。

## 5. 日志字段

建议统一字段：

```text
timestamp
level
request_id
task_id
step_key
source_id
paper_id
run_id
producer_execution_id
error_code
duration_ms
cached
```

禁止记录 SecretStr 原值、完整 DATABASE_URL、完整模型响应或受限全文。

## 6. 前端展示

- 错误提示区分校验失败、来源不可用、模型不可用和系统错误。
- 有缓存时同时显示“实时失败”和“当前展示缓存”。
- 不使用“分析完成”描述部分失败结果。
- request_id 可复制用于排查。
