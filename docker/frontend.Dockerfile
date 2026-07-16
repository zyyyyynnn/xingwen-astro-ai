# syntax=docker/dockerfile:1.7

FROM node:24.18.0-bookworm-slim

ENV COREPACK_HOME=/opt/corepack \
    PATH=/opt/corepack:${PATH} \
    TURBO_TELEMETRY_DISABLED=1 \
    ASTRO_TELEMETRY_DISABLED=1

WORKDIR /workspace

RUN corepack enable && corepack prepare pnpm@11.13.1 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY apps/site/package.json ./apps/site/package.json
COPY apps/workspace/package.json ./apps/workspace/package.json
COPY packages/contracts/package.json ./packages/contracts/package.json
COPY packages/data-access/package.json ./packages/data-access/package.json
COPY packages/design-tokens/package.json ./packages/design-tokens/package.json
COPY packages/domain/package.json ./packages/domain/package.json
COPY packages/testing/package.json ./packages/testing/package.json
COPY packages/ui/package.json ./packages/ui/package.json
COPY packages/visual-engine/package.json ./packages/visual-engine/package.json
COPY packages/workspace-core/package.json ./packages/workspace-core/package.json

RUN pnpm install --frozen-lockfile

COPY eslint.config.mjs prettier.config.mjs tsconfig.base.json turbo.json ./
COPY apps/site ./apps/site
COPY apps/workspace ./apps/workspace
COPY packages/contracts ./packages/contracts
COPY packages/data-access ./packages/data-access
COPY packages/design-tokens ./packages/design-tokens
COPY packages/domain ./packages/domain
COPY packages/testing ./packages/testing
COPY packages/ui ./packages/ui
COPY packages/visual-engine ./packages/visual-engine
COPY packages/workspace-core ./packages/workspace-core

CMD ["pnpm", "--filter", "@xingwen/site", "dev"]
