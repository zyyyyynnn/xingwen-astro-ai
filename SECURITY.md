# Security

> 状态：本文约束当前 Astro Brand Site、React Research Workspace 与 `/api/v1`；A-02、A-03 和 `/api/v2` 能力保持 Pending，直到对应安全与契约验证通过。

## 1. 密钥管理

- Qwen / 百炼 API Key 只能放在后端环境变量或部署平台 Secrets。
- 论文源 API Key、Token 或访问凭据只能放在后端环境变量或部署平台 Secrets。
- 不允许提交 `.env`、数据库密码、Token、私钥。
- 不允许在前端代码、构建产物、截图、日志、文档中出现密钥。
- `.env.example` 只能使用占位值；其中的 `postgres` / `replace_me` 仅限本地模板。
- `VITE_` 和 `PUBLIC_` 变量会进入浏览器，只允许非敏感 URL、开关和展示配置。
- Site 与 Workspace 容器不得通过 `env_file` 或等价方式接收后端 Secrets；Compose 变量插值不等于向容器注入全部环境变量。

## 2. 生产启动防线

`APP_ENV=production` 时后端配置必须拒绝：

- `DEBUG=true`；
- 缺失 `DATABASE_URL`，或连接串使用本地默认凭据 `postgres:postgres`；
- 显式配置 `POSTGRES_PASSWORD=postgres`；
- `DASHSCOPE_API_KEY=replace_me` 或空值；
- `CORS_ORIGINS=*`。

使用托管 PostgreSQL 时可只配置平台提供的安全 `DATABASE_URL`，无需额外设置 `POSTGRES_PASSWORD`。使用 Compose 或自建 PostgreSQL 时必须覆盖本地默认密码。

部署平台仍需在启动前做 Secret 检查。运行时校验是最后防线，不替代 Secrets 管理。

## 3. 模型调用安全

- 所有模型调用统一经过后端 Qwen Client。
- Prompt 和模型输出记录具体版本、模型名和 hash。
- 模型输出必须经过 JSON、Schema 和 Evidence 校验。
- 无来源的模型结论不能作为最终事实展示。
- 跨文献关系必须绑定 Evidence 和 ReasoningTrace。
- 用户输入限制长度、来源范围和最大调用成本。
- 原始模型响应不得在失败时直接降级为最终业务响应。
- 不记录或展示模型隐藏推理过程；`ReasoningTrace` 只保存可审查的结论、条件、证据引用和转换说明。

## 4. 论文源访问安全

- 论文源访问统一经过后端 Paper Pipeline。
- 前端不得直接调用论文源接口。
- 只使用合规、可访问的元数据、摘要或开放文本片段。
- 不绕过付费全文、访问限制或来源许可。
- 记录检索参数、来源 URL、获取时间、缓存状态和去重规则。
- 对论文检索接口设置限流，避免公网 Demo 触发来源风控。

## 5. 公网 Demo 安全

- 限制主案例和调用频率。
- 对模型调用、论文检索、导出和反馈接口设置基础限流。
- 外部服务失败时只使用真实运行缓存。
- 当前缓存结果必须标注 `cached: true` 或页面提示；目标契约使用 `source_mode=cached`，且不得把 Fixture 标为缓存。
- CORS 只配置实际前端域名，不在生产使用通配符。
- 前端 API URL 必须是浏览器可访问的公网地址，不使用 Docker 内部服务名。

## 6. 匿名会话与分享（目标 `/api/v2`，待实现）

- 浏览器会话使用服务端签发的高熵随机标识；Cookie 必须设置 `Secure`、`HttpOnly`、`SameSite` 和明确有效期。
- 所有项目、运行、产物、版本、反馈和取消操作都必须在服务端校验会话所有权，资源 ID 不得替代授权。
- 修改类请求使用 CSRF 防护，并对创建运行、重试、导出、反馈和分享设置会话级与 IP 级限流。
- 分享快照只绑定明确的 ArtifactVersion 集合；默认只读、可撤销、可过期，不得隐式跟随后续版本。
- 分享令牌只保存不可逆 hash；令牌不得出现在日志、分析事件、Referer 或服务端错误详情中。
- 无效、过期或越权访问使用统一问题详情响应，不泄露资源是否存在；`401/403/404` 的唯一口径见 `docs/architecture/API_CONTRACT.md`。

## 7. 数据、日志与前端边界

- 日志不得记录完整 API Key、数据库连接串、论文源凭据或过长模型响应。
- Secret 使用 `SecretStr` 或等价脱敏类型管理。
- 外部数据源结果记录来源 URL、查询参数、获取时间。
- 论文获取结果记录检索参数、候选来源、去重规则和获取时间。
- 反馈内容按普通文本处理，不执行、不拼接为系统指令。
- 导出文件不包含内部调试信息、密钥或受限全文。
- Run 可记录 prompt/model hash、token 用量和 latency，不保存密钥或隐藏推理过程。
- Astro 静态站点不得携带会话凭据；工作台请求只访问受控 API Origin。
- 用户提供的名称、检索式、反馈、论文元数据和模型文本按不可信输入处理；前端默认文本渲染，禁止未净化 HTML。
- 内容安全策略至少限制脚本、连接、图片、字体和 frame 来源；Canvas/WebGL 降级不得放宽 CSP。
- Visual Engine 在路由离开和组件卸载时释放 WebGL、Canvas、观察器和动画句柄，避免跨项目残留或资源耗尽。

## 8. CI 与 GitHub 安全

- 所有改动通过分支和 PR。
- CI 检查 `.env`、错误 lockfile、关键环境变量、构建、测试和 Schema 导出。
- Secret scanning、依赖漏洞检查、CodeQL 保持启用。
- 部署密钥只配置在需要的 GitHub Environment。
- 成员按最小权限原则分配。

## 9. 发现泄露时

1. 立即撤销对应密钥。
2. 从部署平台和本地环境重新配置新密钥。
3. 检查 Git 历史、Actions 日志、截图和文档。
4. 从缓存和产物中清理泄露内容。
5. 在 `docs/quality/RISK_REGISTER.md` 记录原因和修复措施。
