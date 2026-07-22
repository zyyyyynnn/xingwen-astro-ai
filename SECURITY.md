# Security

| 元数据         | 值                                                                    |
| -------------- | --------------------------------------------------------------------- |
| Status         | Accepted                                                              |
| Authority      | 密钥、信任边界、输入、会话、分享、日志和安全响应要求                  |
| Implementation | `/api/v2` Session / CSRF / ownership、Artifact provenance 私有读取及 Workspace/Share Runtime Current；Session、限流与 Snapshot/Share 记录仍为进程生命周期存储 |

本文定义必须满足的安全控制。部署拓扑和发布步骤见 [Deployment](DEPLOYMENT.md)，HTTP 授权与公开错误见 [API Contract](docs/architecture/API_CONTRACT.md)，模型调用准入见 [Model Policy](docs/ai/MODEL_POLICY.md)。

## 1. 信任边界

不可信输入包括：

- 用户研究意图、项目名称、反馈和导出参数；
- 浏览器 URL、search params 和分享 token；
- 外部天文数据、论文元数据、摘要和开放文本；
- 模型响应；
- Fixture、recorded response、缓存文件和导入文件；
- 第三方参考代码和配置示例。

所有不可信输入必须在进入 Domain、持久化、HTML、外部请求或文件系统前完成适用的 Schema、长度、类型、协议、来源和权限校验。

## 2. 密钥与配置

- 模型、论文源、数据源、数据库和内部服务凭据只存在于后端环境或部署平台 Secrets。
- 不提交 `.env`、token、私钥、真实密码或完整连接串。
- `.env.example` 只使用占位值和说明。
- `VITE_`、`PUBLIC_` 和所有浏览器构建变量都视为公开信息。
- 前端或静态站不得通过 `env_file`、构建参数或生成 HTML 接收后端 Secrets。
- 日志、截图、导出、错误详情和测试 Fixture 不包含原始凭据。

生产配置必须拒绝 DEBUG、默认数据库凭据、空/占位关键凭据和通配 CORS。

## 3. 匿名 Session 与授权

当前运行基线使用进程内端口适配器保存匿名 Session、限流及 Workspace/Share 记录，重启后失效。配置 `DATABASE_URL` 后，Artifact/Version/Evidence/SourceSnapshot 私有读取及 Workspace/Share 资源校验使用 PostgreSQL authority，并对每次查询执行 Session-to-Project ownership 检查；跨会话与不存在资源均返回不泄露存在性的 `404`。不得把当前进程生命周期记录描述为跨实例 Session 或 Snapshot。

Artifact provenance 响应使用 `no-store`，并在数据库读取后再次过滤凭据名称、认证头、Cookie、受限全文、原始模型长输出、URL 敏感 query 参数和内部堆栈。SourceSnapshot request metadata 使用明确 allowlist；引用缺失或越出所属 Project 时拒绝返回整个 provenance 图。

Session 创建按客户端地址限流，ShareSnapshot 创建按 Session 独立限流。当前进程内限流状态在重启后清空；多实例生产部署需在边界层配置共享限流。

目标 `/api/v2` 的免登录体验仍需要完整授权边界：

- Session 使用服务端签发的高熵标识和明确过期时间；
- Cookie 使用 `Secure`、`HttpOnly`、合适的 `SameSite` 与最小 Path/Domain；
- 所有 Project、Run、Artifact、Version、Feedback、Export 和 Share 管理操作在服务端校验 ownership；
- 资源 ID、URL 参数或前端隐藏状态不能替代授权；
- 修改类请求使用 CSRF 防护；
- 会话固定、过期、撤销、并发和配额场景具有测试；
- 跨会话私有资源返回不泄露存在性的响应。

精确的 401/403/404 语义由 API Contract 维护。

## 4. 分享安全

- ShareSnapshot 锁定明确 ArtifactVersion 和可公开 Evidence 范围，不指向动态 latest。
- 分享默认只读、最小范围、可撤销、可过期。
- Share token 具有足够随机熵；服务端只保存不可逆 hash。
- 原 token 只在创建结果中返回一次，不写入日志、分析事件、Referer、错误或 Project 聚合。
- 分享响应过滤会话信息、未授权用户输入、内部错误、受限全文和敏感来源字段。
- 分享页面使用严格 CSP、`Referrer-Policy: no-referrer` 和默认 `Cache-Control: no-store`。
- 无效、撤销和过期 token 不泄露底层 Project 或 Version 是否存在。

当前公开 Share 错误使用固定 instance，不回显 token 路径；Uvicorn access log 通过 Filter 将 token path segment 替换为 `[REDACTED]`。成功和失败响应都使用 `no-store`、`no-referrer`、严格 CSP、`nosniff` 与最小 Permissions Policy。M1 只允许 `public_metadata_only`，原始 Artifact content 和 Evidence locator 不进入公开 DTO；公网反向代理日志仍必须由部署配置执行相同脱敏。

## 5. 外部来源访问

- 前端不直连模型、论文源或天文数据源。
- 外部请求只允许配置的协议和 host；禁止任意 URL fetch、内部网络探测和非预期重定向。
- 论文访问遵守来源许可，不绕过付费全文、认证或访问限制。
- 请求记录可复现的 query、来源、时间、版本和错误，但不记录认证头或 Cookie。
- 对模型、论文检索、数据查询、导出和反馈实施会话级与来源级限流。
- 上游返回内容按不可信文本处理；未经净化的 HTML 不进入浏览器 DOM。

## 6. 模型与科研内容安全

- 模型输出必须通过结构、Schema、Evidence 和领域准入。
- 无来源结论不能作为最终事实；无 Evidence / Trace 的关系只能作为 candidate。
- 原始模型文本不能在校验失败时降级为业务结果。
- ReasoningTrace 只保存可审查依据、条件和引用，不保存模型私有 chain-of-thought。
- Prompt、模型、参数、输入和输出通过版本与 hash 定位，不记录无必要的完整内容。
- 用户输入、论文文本和反馈不得被拼接为更高权限系统指令。

## 7. 浏览器与内容安全

- React/Astro 默认文本转义不得被绕过；需要 HTML 时先使用受控净化策略。
- CSP 至少限制 script、connect、img、font、frame、object 和 base URI。
- 生产环境启用 HSTS、`X-Content-Type-Options`、Referrer Policy、Permissions Policy 和最小 CORS allowlist。
- 外链使用允许协议，并对新窗口关系设置安全属性。
- 文件名、MIME、大小和导出格式必须校验；下载 URL 短期有效，不暴露底层路径。
- Workspace 不在 localStorage 持久化 Session、Share 原 token 或其他敏感凭据。
- WebGL 降级不得放宽 CSP；路由离开时释放 Canvas、GPU、Observer 和动画资源。

## 8. 日志、错误与数据最小化

允许记录：

- request id、Run id、step key、Version id；
- 公开 error code、状态、时间和延迟；
- producer、Prompt/model 版本和 hash；
- 截断、脱敏的诊断摘要。

禁止记录：

- 原始 Session / Share token、API Key、认证头、数据库密码；
- 完整连接串、受限全文和无必要的用户输入；
- 原始长模型响应或模型私有推理；
- 可直接复原凭据的配置快照。

公开错误不得包含堆栈、SQL、内部路径、第三方原始响应或资源存在性信息。

## 9. 缓存、版本与删除

- Cached 产物必须引用真实历史 Run、ArtifactVersion 和 SourceSnapshot。
- Fixture、seed、recorded response 或手写 JSON 不进入真实 CacheRecord。
- Revision 创建新 ArtifactVersion，不原地覆盖或删除正常历史。
- 涉及密钥泄露、侵权或法定删除时执行强制清理；审计信息不得继续保存必须删除的内容。
- Session、临时导出、过期 Share 和诊断数据具有明确保留与清理策略。

## 10. CI、供应链与仓库

- 所有变更通过分支和 PR；保护规则与必要 CI 不得绕过。
- CI 检查意外 `.env`、错误 lockfile、Secret 模式、依赖安装、构建、测试和 Schema 生成。
- 依赖版本锁定；升级需要变更说明和适用回归。
- Secret scanning、依赖漏洞检查和 CodeQL 在仓库支持范围内保持启用。
- 部署凭据只授予必要 Environment 和最小权限。
- 第三方代码、字体、论文和数据在纳入前检查许可与来源。

## 11. 事件响应

发现泄露或越权风险时：

1. 立即停止受影响流量或功能；
2. 撤销并轮换相关凭据/token；
3. 检查 Git 历史、Actions、部署日志、截图、导出和缓存；
4. 清理暴露内容并验证无法继续访问；
5. 修复根因，增加回归测试和检测门禁；
6. 在 Risk Register 记录影响、原因、处理和后续责任；
7. 必要时按来源许可、平台规则或法律要求通知相关方。

安全修复不得通过删除测试、放宽授权或隐藏错误来“恢复可用”。
