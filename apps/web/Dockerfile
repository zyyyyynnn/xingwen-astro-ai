# syntax=docker/dockerfile:1.7
# 前端镜像：node:24-alpine + pnpm
# AGENTS 红线：前端容器基线为 node:24-alpine

FROM node:24-alpine

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:$PATH" \
    CI=1

# 安装 pnpm（通过 corepack，固定版本）
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate

WORKDIR /app

# 先复制依赖清单，利用 Docker 层缓存
COPY package.json pnpm-lock.yaml ./

# 安装依赖（frozen-lockfile 确保一致性）
RUN pnpm install --frozen-lockfile

# 复制源码
COPY . .

EXPOSE 5173

# 开发模式：Vite dev server，支持热更新
CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "5173"]
