# Local Setup

当前仓库处于基础搭建阶段。M1 完成后按本文档启动本地环境。

## 1. 环境要求

| 工具 | 建议版本 |
| --- | --- |
| Node.js | 20+ |
| Python | 3.11+ |
| PostgreSQL | 16+ |
| Git | 2.40+ |

## 2. 环境变量

复制模板：

```bash
cp .env.example .env
```

必须本地填写：

```text
DATABASE_URL=
DASHSCOPE_API_KEY=
```

禁止提交 `.env`。

## 3. 前端启动

```bash
cd apps/web
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5173`

## 4. 后端启动

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认地址：`http://127.0.0.1:8000`

API 文档：`http://127.0.0.1:8000/docs`

## 5. 本地验收顺序

1. 后端 `/api/v1/health` 正常。
2. 前端首页可打开。
3. 创建任务接口返回 `task_id`。
4. 任务流程页可展示状态。
5. 数据、文献、图谱页面能展示 Mock 或真实结果。
6. `.env` 未被 Git 跟踪。

## 6. 常见问题

| 问题 | 处理 |
| --- | --- |
| API Key 报错 | 检查 `.env` 中 `DASHSCOPE_API_KEY`，不要写到前端 |
| CORS 报错 | 检查 `CORS_ORIGINS` 是否包含前端地址 |
| 数据库连不上 | 检查 `DATABASE_URL`、数据库是否启动、库名是否存在 |
| Demo 需要稳定展示 | 开启 `ENABLE_DEMO_CACHE=true` 并准备真实运行缓存 |
