# Frontend Architecture

| 元数据         | 值                                                      |
| -------------- | ------------------------------------------------------- |
| Status         | Accepted                                                |
| Authority      | 前端运行时、目录、依赖方向、构建与质量门禁              |
| Implementation | A-01 runtime、A-14 Domain/Tour FSM、A-15/A-16 Adapter/Core Current；A-02 视觉与 A-03 UI 接线 Pending |

本文是前端运行时、目录、依赖方向、构建和质量门禁的唯一正文来源。A-01 只证明最小入口与工程边界，不代表完整科研产品界面已交付。

## 1. 运行时决策

- `apps/site` 使用 Astro 静态输出，负责 Brand Site 与静态 404。
- `apps/workspace` 使用 React、Vite 与 TanStack Router，负责 Guided Tour、Research Workspace 与 Share 路由入口。
- 根 pnpm workspace 管理两个 App 和八个共享 Package。
- Pydantic 仍是生产 Transport Schema 的唯一编写源；前端不得手写第二套同名生产 Schema。
- Site 与 Workspace 不保存密钥，不直连模型、论文源或天文数据源。
- A-02 与 A-03 前端产品行为保持 Pending；`/api/v2` M1 后端核心 Runtime 已实现，但在 A-03 完成前不宣称 Workspace 已接入真实 HTTP 主链路。

## 2. 当前目录

```text
apps/
├─ site/                         # Astro 静态 Brand Site
├─ workspace/                    # React Research Workspace SPA
└─ api/                          # FastAPI（前端边界之外）

packages/
├─ design-tokens/                # A-01 基础 Token 与 CSS 公开入口
├─ ui/                           # 共享 React UI 公开入口
├─ domain/                       # 纯 TypeScript 领域边界
├─ contracts/                    # Pydantic Contract 消费边界
├─ data-access/                  # Repository Port、Fixture/HTTP Adapter 与 Contract 校验
├─ workspace-core/               # Guided Tour FSM 与 WorkspaceSnapshot Controller
├─ visual-engine/                # 视觉运行时边界，行为 Pending
└─ testing/                      # 共享测试入口

package.json
pnpm-workspace.yaml
pnpm-lock.yaml
turbo.json
tsconfig.base.json
eslint.config.mjs
prettier.config.mjs
playwright.config.ts
```

每个共享 Package 都有独立 `package.json`、`tsconfig.json`、公开 `exports`、build/typecheck/lint/test 脚本。未实现能力只用类型和明确 Issue 边界表达。

## 3. 依赖方向

```text
apps/site
  -> @xingwen/design-tokens
  -> @xingwen/ui
  -> @xingwen/visual-engine  (允许公开接口，当前未使用)

apps/workspace
  -> @xingwen/design-tokens
  -> @xingwen/ui
  -> @xingwen/workspace-core
  -> @xingwen/data-access

@xingwen/workspace-core
  -> @xingwen/domain

@xingwen/data-access
  -> @xingwen/domain
  -> @xingwen/contracts
```

约束：

- Shared Package 不依赖 App。
- `domain` 不依赖 React、Astro、Vite、HTTP、DOM 或 Browser API。
- `ui` 与 `visual-engine` 不调用 `fetch` 或 Repository。
- App 只能从 Package 的公开 `exports` 导入，不跨包读取内部文件。
- 不使用 TypeScript 路径别名绕过 Package public entry。
- 不建立第二套路由、全局状态或生产 API 类型系统。

这些约束由 `pnpm check:architecture` 自动验证。

## 4. 精确版本基线

| 类别                             | 当前版本        |
| -------------------------------- | --------------- |
| Node.js                          | 24.18.0 LTS     |
| pnpm                             | 11.13.1         |
| Astro / React integration        | 7.0.9 / 6.0.1   |
| React / React DOM                | 19.2.7 / 19.2.7 |
| Vite / React plugin              | 8.1.5 / 6.0.3   |
| Tailwind CSS / Vite plugin       | 4.3.2 / 4.3.2   |
| TypeScript                       | 6.0.3           |
| Turborepo                        | 2.10.5          |
| TanStack Router                  | 1.170.18        |
| Vitest                           | 4.1.10          |
| Testing Library React / jest-dom | 16.3.2 / 6.9.1  |
| Playwright                       | 1.61.1          |
| ESLint / typescript-eslint       | 10.7.0 / 8.64.0 |
| Prettier / Astro plugin          | 3.9.5 / 0.14.1  |

### TypeScript 版本说明

TypeScript 7.0.2 已发布，但当前不能进入基线：

- `typescript-eslint@8.64.0` 的 peer 范围为 `>=4.8.4 <6.1.0`。
- `@astrojs/check@0.9.9` 依赖 TypeScript `^5 || ^6`。

因此选择所有实际依赖共同支持的最高稳定版 6.0.3。升级条件是上述两项同时正式声明支持 TypeScript 7；不得使用 beta、rc、nightly 或 canary 绕过。

## 5. Brand Site 最小入口

`apps/site` 当前静态输出：

- `/`：中文标题“星文智析”、产品说明、Workspace CTA 和基础 metadata。
- `/404.html`：清晰的 Not Found 内容与返回首页链接。
- `PUBLIC_WORKSPACE_URL`：控制 CTA 地址，默认 `http://localhost:5173/workspace`。
- React integration：用于服务端渲染共享 `BrandMark`，不增加客户端 hydration。
- 无 JavaScript 时：首页标题、说明与 CTA 仍存在于静态 HTML。

A-01 不实现完整首页叙事、WebGL、字体资产、社交预览或 A-02 视觉系统。

## 6. Research Workspace 最小入口

`apps/workspace` 当前使用一棵 TanStack Router route tree：

| 路径                 | 页面身份                                 |
| -------------------- | ---------------------------------------- |
| `/`                  | 科研工作台入口                           |
| `/tour`              | 引导入口                                 |
| `/workspace`         | 科研工作区                               |
| `/share/$shareToken` | 共享入口；不读取共享数据，也不回显 token |
| 其他                 | Not Found boundary                       |

根布局提供可访问的主要导航和 skip link。Router 提供 Error Boundary、Loading fallback 与 Not Found boundary。每个页面只说明 A-01 基线，不实现真实 Project、Run、Artifact、Repository 或 API 行为。

## 7. Shared Package 当前边界

| Package          | 当前内容                                        | 后续 Issue                               |
| ---------------- | ----------------------------------------------- | ---------------------------------------- |
| `design-tokens`  | 基础浅色语义变量、字体 fallback、CSS 与 TS 入口 | A-02 冻结完整颜色、字体、间距和动效系统  |
| `ui`             | 静态 `BrandMark` 与 UI 基元                      | A-02 建立 primitive 与复合组件           |
| `domain`         | A-14 前端 Domain Model（Project、Contract、Run、ArtifactVersion、Evidence、ProvenanceState） | A-04～A-08 各科研工作区消费 |
| `contracts`      | 生成的 v2 DTO、JSON Schema 与 ajv 运行时校验     | 随后端 Pydantic Contract 同步维护        |
| `data-access`    | 收窄 Repository Port、版本化 Fixture 与 `/api/v2` HTTP Adapter | A-03 接入 Workspace UI |
| `workspace-core` | Guided Tour FSM 与 WorkspaceSnapshot Controller | A-03 Contract、Tour UI 与页面状态编排    |
| `visual-engine`  | A-02 公开边界类型                               | A-02 实现生命周期与降级                  |
| `testing`        | 共享入口地址                                    | 各前端 Issue 按实际测试需要扩展          |

基础 Token 只为 A-01 页面提供可读浅色 fallback，不构成完整 A-02 设计系统。

## 8. 根工具链

根脚本：

```text
pnpm dev
pnpm build
pnpm lint
pnpm typecheck
pnpm test
pnpm test:e2e
pnpm format:check
pnpm check:docs
pnpm check:architecture
pnpm check:legacy
pnpm check
```

Turborepo 调度 `build`、`dev`、`lint`、`typecheck` 与 `test`。`pnpm check` 顺序聚合 format、documentation、lint、typecheck、unit、build、architecture 和 runtime-retirement gate；E2E 独立运行以便先安装浏览器。

pnpm 11 配置位于 `pnpm-workspace.yaml`：

- 只链接显式 `workspace:*` 依赖。
- `engineStrict` 与 `nodeVersion: 24.18.0` 固定运行时。
- `strictPeerDependencies` 拒绝不兼容 peer。
- `allowBuilds` 只允许已审查的 esbuild 安装脚本。
- Vite transitive 版本统一覆盖为 8.1.5。
- 仓库只允许一个根 `pnpm-lock.yaml`。

## 9. 测试边界

- Unit：Vitest + Testing Library 验证共享深链接、生成 Contract 校验、Fixture/HTTP 一致性、错误映射与 Workspace Controller。
- E2E：Playwright 验证 Site、无 JavaScript Site、Site 404、Workspace 四个入口、共享深链接、Not Found 与页面控制台错误。
- Typecheck：两个 App 与全部共享 Package 分别执行。
- Build：Site 与 Workspace 分别产出 `dist`；共享 Package 产出 JS 与声明文件。
- Architecture：验证依赖方向、公开入口、Domain 纯度、单 lockfile 与禁止路径别名。
- Foundation/runtime-retirement：验证必需目录、环境变量、依赖状态和已退役实现不会重新进入仓库。

## 10. Docker 与本地运行

`docker/frontend.Dockerfile` 是 Site 与 Workspace 共用的前端镜像定义：

- 基于 `node:24.18.0-bookworm-slim`。
- Corepack 激活 pnpm 11.13.1。
- 从根 workspace 执行 `pnpm install --frozen-lockfile`。
- Compose 通过 filter 命令分别启动 Site 与 Workspace，并绑定 `0.0.0.0`。

Compose 服务与默认端口：

| Service     | Port |
| ----------- | ---- |
| `site`      | 4321 |
| `workspace` | 5173 |
| `api`       | 8000 |
| `postgres`  | 5432 |

前端容器只接收 `PUBLIC_WORKSPACE_URL` 或 `VITE_API_BASE_URL`，不通过 `env_file` 接收后端密钥。HTTP Adapter 已实现，但当前 Workspace 页面尚未接线；`VITE_API_BASE_URL` 是 A-03/X-01 使用的非敏感地址。

## 11. CI

Frontend job 从仓库根目录执行 frozen install、format、lint、typecheck、unit、build、architecture、runtime-retirement 和 Playwright E2E。Foundation job 执行 Python 基建检查与 Compose config；Backend job 继续执行 uv frozen sync、pytest 与 Pydantic Schema export。

CI 不允许 App 私有 lockfile、第二套包管理器状态或跨包深层导入。

## 12. Pending 边界

- A-02：完整 bluegray Design Token、primitive、Brand Site 极简单英雄首页、静态 Workspace Shell、Visual Engine（ASCII/Dither Hero）、Poster 与 Reduced Motion。
- A-03：Research Contract 双通道 UI、Guided Tour 页面接线、Workspace/Share 交互与真实 HTTP 模式切换；Repository、Fixture/HTTP Adapter、WorkspaceSnapshot Controller 已实现。
- X-01：完整 Workspace 主链路、Compose 与真实 HTTP 集成证据收口。
- A-04～A-10：各科研产物工作区、反馈、响应式与发布收口。
- Desktop/Tauri：需独立 Issue 与 Platform Adapter，不在当前目录创建。

任何 Pending 能力都不能因存在空接口、路由占位或设计文档而标记为 Implemented。
