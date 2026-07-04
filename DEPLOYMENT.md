# Deployment

## 1. 部署目标

MVP 部署目标是提供稳定公网 Demo，而不是生产级大规模服务。

必须满足：

- 前端公网可访问。
- 后端 API 可被前端访问。
- PostgreSQL 可连接。
- Qwen / 百炼 API Key 只存在于后端或部署平台 Secrets。
- 主案例有真实运行缓存兜底。

## 2. 推荐方案

| 模块 | 推荐 | 说明 |
| --- | --- | --- |
| 前端 | Vercel / Netlify / 阿里云静态托管 | Vue 静态资源部署简单，适合公网 Demo |
| 后端 | Render / Railway / 阿里云 ECS | FastAPI 独立部署，隔离密钥 |
| 数据库 | Supabase Postgres / Neon / 阿里云 RDS | 先用托管 Postgres 降低运维成本 |
| 文件导出 | 后端临时文件或对象存储 | MVP 先保证 CSV/报告可下载 |

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
```

非敏感项：

```text
APP_ENV
CORS_ORIGINS
QWEN_BASE_URL
QWEN_MODEL
DEMO_CASE_KEY
```

## 5. 部署验收

| 检查项 | 标准 |
| --- | --- |
| 首页 | 可打开，无控制台严重报错 |
| API | `/api/v1/health` 可访问 |
| 任务 | 固定主案例可创建并查询状态 |
| 数据 | 可展示数据表和来源 |
| 导出 | CSV、数据字典、溯源报告可下载 |
| 缓存 | 外部服务失败时可展示真实缓存 |
| 安全 | 页面源码、日志、截图不暴露密钥 |

## 6. 部署前禁止事项

- 不把 `.env` 提交到仓库。
- 不把 API Key 写入前端构建变量。
- 不开放无限制任意模型调用入口。
- 不把手写假数据作为缓存结果。
