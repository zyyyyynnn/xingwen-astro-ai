# syntax=docker/dockerfile:1.7
# 后端镜像：python:3.13-slim + uv
# AGENTS 红线：后端容器基线为 python:3.13-slim，依赖由 uv 管理

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_LINK_MODE=copy

# 安装 uv（通过 pip，避免 Docker 构建环境访问 github 受限）
RUN pip install --no-cache-dir uv==0.7.8 && uv --version

WORKDIR /app

# Compose 以仓库根目录为 build context，便于只读挂入权威 Case/Field Manifest。
# 先复制依赖清单，利用 Docker 层缓存。
COPY apps/api/pyproject.toml apps/api/uv.lock ./

# 先同步依赖以保留缓存层；源码复制后再安装当前项目本身。
RUN uv sync --frozen --no-install-project

# 复制源码与迁移资产（migrate one-shot service 与运行时共用同一镜像）
COPY apps/api/alembic.ini ./
COPY apps/api/migrations ./migrations
COPY apps/api/src ./src
COPY services/data_pipeline ./services/data_pipeline

# 安装当前 API distribution，使运行时 package metadata 与实际项目版本同源。
RUN uv sync --frozen

# Integration bootstrap 属于 API image 的显式运行边界；构建时即验证本地 Pipeline 包完整。
RUN PYTHONPATH=/app/src:/app uv run python -c "import app.test_support.bootstrap; import services.data_pipeline.crossmatch"

# 把 .venv/bin 加入 PATH，uvicorn 直接可用
# PYTHONPATH 同时包含 API 的 src layout 与冻结数据流水线包。
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src:/app"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
