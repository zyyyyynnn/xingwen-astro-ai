# Deployment

## MVP 部署目标

- 前端公网可访问。
- 后端公网可访问或通过受控网关访问。
- PostgreSQL 可连接。
- Qwen API Key 通过环境变量配置。
- 主案例有缓存兜底数据。

## 推荐部署方式

| 模块 | 推荐 |
| --- | --- |
| 前端 | Vercel / Netlify / 阿里云静态托管 |
| 后端 | Render / Railway / 阿里云 ECS |
| 数据库 | Neon / Supabase Postgres / 阿里云 RDS |
| 文件导出 | 后端本地临时文件或对象存储 |

## 环境变量

```text
DATABASE_URL=
QWEN_API_KEY=
QWEN_BASE_URL=
QWEN_MODEL=
APP_ENV=
CORS_ORIGINS=
```

## 部署验收

- 能访问首页。
- 能创建任务。
- 能查询任务状态。
- 能展示主案例缓存结果。
- 能下载 CSV。
- 不暴露任何 API Key。

