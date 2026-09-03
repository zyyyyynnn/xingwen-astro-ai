# syntax=docker/dockerfile:1.7
# Backend image: pinned CPython 3.13 patch line with uv-managed dependencies.

FROM python:3.13.13-slim AS api-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_LINK_MODE=copy

# Install the repository-governed uv version without a GitHub binary dependency.
RUN pip install --no-cache-dir uv==0.7.8 && uv --version

WORKDIR /app

# Compose uses the repository root as build context.
COPY apps/api/pyproject.toml apps/api/uv.lock ./

# Preserve a stable dependency cache before copying application sources.
RUN uv sync --frozen --no-install-project

# Schema one-shot and API runtime use the same current application image.
COPY apps/api/src ./src
COPY packages/prompts ./packages/prompts
COPY services/data_pipeline ./services/data_pipeline
COPY services/paper_pipeline ./services/paper_pipeline
COPY services/graph_pipeline ./services/graph_pipeline
COPY services/scientific_document ./services/scientific_document
COPY services/scientific_skills ./services/scientific_skills

RUN uv sync --frozen

# Validate every local production package required by the runtime image.
RUN PYTHONPATH=/app/src:/app uv run python -c "import app.test_support.bootstrap; import services.data_pipeline.crossmatch; import services.scientific_document.model_asset_contract; import services.scientific_skills"

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src:/app"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Optional heavyweight visual runtime. The default API image remains native/HTTP
# capable; operators selecting the verified local model bundle build this target.
FROM api-base AS api-visual
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        libgl1 \
        libglib2.0-0t64 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --group visual

FROM api-base AS api
