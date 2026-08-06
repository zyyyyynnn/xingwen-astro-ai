# Security

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 密钥、信任边界、输入、会话、分享、日志与安全要求 |

本文定义系统必须满足的稳定安全控制。部署拓扑见 [Deployment](DEPLOYMENT.md)，HTTP 授权与错误响应见 [API Contract](docs/architecture/API_CONTRACT.md)，模型调用准入见 [Model Policy](docs/ai/MODEL_POLICY.md)。

## 1. 信任边界

不可信输入包括：
- 用户研究意图、项目名称、反馈和导出参数；
- 浏览器 URL、search params 和分享 token；
- 外部天文数据、论文元数据、摘要和开放文本；
- 模型响应、Fixture、缓存文件和导入文件。

所有不可信输入在进入 Domain、持久化、HTML、外部请求或文件系统前，必须完成 Schema、长度、类型、协议、来源和权限校验。

## 2. 密钥与配置

- 模型、论文源、数据源、数据库和内部服务凭据只存在于后端环境或部署平台 Secrets。
- 不提交 `.env`、token、私钥、真实密码或连接串；`.env.example` 只使用占位值。
- 前端与构建变量（`VITE_` / `PUBLIC_`）均视为公开信息，不得包含 Secrets。
- 日志、截图、导出、错误详情和测试 Fixture 严格禁止包含原始凭据。
- 生产配置必须拒绝 DEBUG 模式、默认数据库凭据和通配 CORS。

## 3. 匿名 Session 与授权

- Session 使用服务端签发的高熵标识与明确过期时间。
- Cookie 配置 `Secure`、`HttpOnly` 与合适的 `SameSite`。
- 所有 Project、Run、Artifact、Version、Feedback、Export 和 Share 操作由服务端校验 ownership。
- 跨会话或不存在的私有资源均返回不泄露存在性的 `404` 响应。

## 4. 分享安全

- ShareSnapshot 锁定明确不可变 ArtifactVersion 与可公开 Evidence 范围。
- 分享默认只读、最小范围、可撤销、可过期；Share token 服务端仅保存不可逆 hash。
- 原 token 只在创建时返回一次，不写入日志、Referer 或 Project 聚合。
- 分享响应严格过滤会话信息、内部错误、受限全文与敏感来源字段。
- 无效、撤销和过期 token 不泄露底层资源存在性。

## 5. 外部来源与网络安全

- 前端不直连模型、论文源或天文数据源。
- 外部请求仅允许配置的协议与 host allowlist；禁止任意 URL fetch、内网探测与非预期重定向。
- 上游返回内容按不可信文本处理；未经净化的 HTML 严禁直接注入 DOM。

## 6. 模型与科研内容安全

- 模型输出必须通过结构、Schema、Evidence 和领域准入。
- 无来源结论不能作为最终事实；无 Evidence / Trace 的关系只能作为 candidate。
- ReasoningTrace 只保存可审查依据与引用，严禁保存模型私有 chain-of-thought。
- Prompt、模型、参数、输入和输出通过不可变版本与 hash 定位。

## 7. 浏览器与内容安全

- React/Astro 默认文本转义不得绕过；需渲染 HTML 时使用受控净化策略。
- 生产环境启用严格 CSP、HSTS、`X-Content-Type-Options`、Referrer Policy 与 Permissions Policy。
- 外链使用安全协议与 `rel="noopener noreferrer"` 属性。
- 文件名、MIME、大小与导出格式必须校验。

## 8. 日志、错误与数据最小化

- 允许记录：request id、Run id、Version id、公开 error code、状态、时间与脱敏摘要。
- 禁止记录：原始 Session/Share token、API Key、认证头、密码、连接串、完整模型响应与私有推理。
- 公开错误严禁回显堆栈、SQL 命令、内部路径或资源存在性。

## 9. 缓存、版本与删除

- Cached 产物必须引用真实历史 Run、ArtifactVersion 和 SourceSnapshot。
- Fixture 或录制响应不得伪造进入真实 CacheRecord。
- Revision 产生新 ArtifactVersion，不原地覆盖或删除正常历史。
- 涉及密钥泄露或法定要求时执行彻底清理。

## 10. 供应链与 CI 安全

- 保护规则与必要 CI 不得绕过。
- CI 自动检查意外 `.env`、Secret 模式、依赖安装与 Schema 生成。
- 依赖版本严格锁定；第三方代码、字体、论文与数据接入前须校验许可与来源。
