# Deployment

## 1. 部署目标

MVP 部署目标是提供稳定公网 Demo，而不是生产级大规模服务。

必须满足：

- 前端公网可访问。
- 后端 API 可被前端访问。
- PostgreSQL 可连接。
- Qwen / 百炼 API Key 只存在于后端或部署平台 Secrets。
- 论文源凭据只存在于后端或部署平台 Secrets。
- 主案例有真实运行缓存兜底，覆盖数据、论文获取、文献总结、跨文献推理和图谱。

## 2. 推荐方案

| 模块 | 推荐 | 说明 |
| --- | --- | --- |
| 前端 | Vercel / Netlify / 阿里云静态托管 | Vue 静态资源部署简单，适合公网 Demo |
| 后端 | Render / Railway / 阿里云 ECS | FastAPI 独立部署，隔离密钥和论文源访问 |
| 数据库 | Supabase Postgres / Neon / 阿里云 RDS | 先用托管 Postgres 降低运维成本 |
| 文件导出 | 后端临时文件或对象存储 | MVP 先保证 CSV/JSON/报告可下载 |

## 3. 环境划分

| 环境 | 用途 | GitHub Environment |
| --- | --- | --- |
| local | 本地开发 | 不使用 GitHub Secrets |
| preview | PR 或测试部署 | `preview` |
| production | 正式公网 Demo | `production` |

## 4. 环境变量

见 [.env.example](.env.example)。

敏感项：

```text
DATABASE_URL
DASHSCOPE_API_KEY
PAPER_SOURCE_API_KEY
```

非敏感项：

```text
APP_ENV
CORS_ORIGINS
QWEN_BASE_URL
QWEN_MODEL
QWEN_TIMEOUT_SECONDS
DEMO_CASE_KEY
PAPER_SOURCE_BASE_URL
PAPER_SEARCH_TIMEOUT_SECONDS
PAPER_SEARCH_MAX_RESULTS
ENABLE_DEMO_CACHE
CACHE_TTL_SECONDS
```

`PAPER_SOURCE_API_KEY` 如当前论文来源不需要鉴权，可留空或不配置；不得写入前端构建变量。

## 5. 部署验收

| 检查项 | 标准 |
| --- | --- |
| 首页 | 可打开，无控制台严重报错 |
| API | `/api/v1/health` 可访问 |
| 任务 | 固定主案例可创建并查询状态 |
| 数据 | 可展示数据表和来源 |
| 论文获取 | 可展示检索参数、候选论文、去重和相关性排序 |
| 文献总结 | 可展示 PaperSummary |
| 跨文献推理 | 可展示 Claim、Relation、ReasoningTrace |
| 图谱 | 可展示证据图谱和推理链详情 |
| 导出 | CSV、数据字典、溯源报告、论文与推理关系 JSON 可下载 |
| 缓存 | 外部服务失败时可展示真实缓存 |
| 安全 | 页面源码、日志、截图不暴露密钥或论文源凭据 |

## 6. 部署前禁止事项

- 不把 `.env` 提交到仓库。
- 不把 API Key 写入前端构建变量。
- 不把论文源凭据写入前端构建变量。
- 不开放无限制任意模型调用入口。
- 不开放无限制论文检索入口。
- 不把手写假数据或 seed list 作为缓存结果。
