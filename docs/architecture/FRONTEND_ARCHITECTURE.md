# Frontend Architecture

| 项目状态 | 口径 |
| --- | --- |
| Status | Accepted for implementation |
| Implementation | Pending |
| Current runtime | `apps/web` 中的 Vue 3 + Vite 骨架 |
| Target runtime | Astro 品牌站 + React Research Workspace Monorepo |

本文定义星文智析前端重构后的工程架构。该方案取代现有单体 Vue 3 骨架，目标是同时支撑品牌首页、Guided Tour、科研工作台、实时 WebGL、契约驱动数据访问、视觉回归以及未来 Tauri 桌面封装。

## 1. 决策摘要

- 使用 pnpm workspace 管理前端应用和共享包。
- 使用 Node.js 24 LTS、TypeScript strict 与单一 `pnpm-lock.yaml`；Turborepo 仅用于明确的任务图和缓存职责。
- `apps/site` 使用 Astro 静态输出，负责品牌首页和基础 SEO。
- `apps/workspace` 使用 React + TypeScript + Vite，负责 Guided Tour 与科研工作台。
- Astro 通过 React Island 复用 WebGL、Research Contract 和部分交互组件。
- Three.js + React Three Fiber + 自定义 GLSL 负责 ASCII / Dither 实时渲染。
- OpenAPI / JSON Schema 与生成 Transport Type 进入 `packages/contracts`，组件只依赖 `packages/domain`。
- 所有业务页面通过 Repository Interface 获取统一领域模型。
- Fixture Adapter 与 HTTP Adapter 必须可互换。
- 当前交付为 Web，平台能力通过 Port / Adapter 为未来 Tauri 预留。
- 旧 `apps/web` 在迁移期只作为可回退基线，迁移完成后删除，不长期维护两套前端。

## 2. 目标目录

```text
apps/
├─ site/                         # Astro 品牌站与静态预渲染
│  ├─ src/pages/
│  ├─ src/layouts/
│  ├─ src/components/
│  └─ public/
├─ workspace/                    # React 科研工作台与 Guided Tour
│  ├─ src/app/
│  ├─ src/features/
│  ├─ src/routes/
│  ├─ src/shell/
│  └─ src/main.tsx
├─ api/                          # FastAPI，保持后端边界
└─ web/                          # 迁移期旧 Vue 骨架，完成后删除

packages/
├─ design-tokens/                # CSS Variables、字体、尺寸、动效、图形质量
├─ ui/                           # 项目自有 React 组件与 Radix primitives 封装
├─ visual-engine/                # R3F 场景、Shader、ASCII Atlas、质量管理
├─ domain/                       # 稳定领域对象、枚举与 artifact helpers
├─ contracts/                    # OpenAPI/JSON Schema、生成 DTO、transport validation
├─ data-access/                  # Repository、HTTP / Fixture adapters、query keys
├─ workspace-core/              # 面板布局、命令、selection、context model
├─ testing/                      # 测试工具、版本化 Fixture、a11y、visual baselines
└─ config/                       # tsconfig、lint、format、build 共享配置
```

`apps/desktop` 只在文档中保留目标边界，本轮不创建目录或实现。迁移实施前不得把上述目标命令写成当前可运行命令。

实际迁移可以分阶段落地，但最终不得继续把品牌站、工作台、领域模型、API 调用和 Shader 混在一个应用目录中。

## 3. 应用边界

### 3.1 `apps/site`

职责：

- `/` 首页四幕式叙事
- 主案例介绍和提交入口
- SEO、Open Graph、分享预览与稳定静态首屏
- WebGL React Island 的延迟加载
- 跳转 `/tour` 与 `/workspace`

不负责：

- 研究项目管理
- 完整运行状态
- 高密度科研产物视图
- 持久化工作台布局

构建模式：Astro static output。所有核心标题、说明和 CTA 必须存在于静态 HTML，不依赖 JavaScript 才能出现。

### 3.2 `apps/workspace`

职责：

- `/tour/*` Guided Tour
- `/workspace/*` Research Desktop
- ResearchProject / ResearchRun 管理
- Research Contract
- 多面板 Research Canvas
- Provenance Observatory
- Research Console
- 数据、论文、文献、推理、图谱、反馈和分享

不负责：

- 直接调用模型和外部科研数据源
- 保存密钥
- 用浏览器状态替代后端产物版本和运行状态

### 3.3 未来 `apps/desktop`

后续 Tauri 应用只负责：

- 窗口生命周期
- 文件系统对话框
- 系统通知
- 安全的本地持久化
- 深链接和协议关联

业务路由、领域模型、工作台组件和数据访问逻辑继续复用 `workspace` 与共享包。

## 4. 依赖方向

```text
apps/site ───────┐
                 ├─> packages/ui
apps/workspace ──┤   packages/visual-engine
                 │   packages/domain
                 │   packages/data-access
                 └─> packages/workspace-core

packages/ui ----------> design-tokens
packages/visual-engine -> design-tokens
packages/data-access -> domain
packages/data-access -> contracts
workspace-core -------> domain
```

禁止：

- `packages/domain` 依赖 React、Astro 或浏览器 API。
- `packages/ui` 直接调用 HTTP。
- `packages/visual-engine` 读取后端响应原始结构。
- feature 跨目录导入内部实现；必须经过 feature public API。
- Astro 页面直接持有工作台全局状态。

## 5. 技术选型

| 能力 | 选型 | 原因 |
| --- | --- | --- |
| 包管理 | pnpm workspace | 与现有基线一致，适合 Monorepo |
| 品牌站 | Astro | 静态首屏、SEO、Island、低 JS 成本 |
| 工作台 | React + Vite | 适合复杂交互、R3F 和未来 Tauri |
| 路由 | TanStack Router 或等价类型安全路由 | 路由参数、loader 和搜索参数可校验 |
| Server State | TanStack Query | 缓存、请求状态、失效和并发运行管理 |
| UI State | Zustand | 面板、选择、布局、命令等局部客户端状态 |
| Form | React Hook Form + Zod | Research Contract 和反馈表单校验 |
| UI Primitive | Radix UI | 可访问性和 headless 交互，不绑定默认皮肤 |
| 样式 | Tailwind CSS 4 + CSS Variables | Token 驱动和快速组合，避免散落样式 |
| 表格 | TanStack Table + virtual | 高密度科研数据与大列表 |
| 图谱 | `@xyflow/react` | 可控节点、边和交互，适合 Evidence Graph |
| 实时图形 | Three.js + React Three Fiber | React 场景组合和自定义 Shader |
| 测试 | Vitest + Testing Library + Playwright | 单元、交互、E2E、视觉回归 |
| 网络测试替身 | MSW（可选）+ Repository Fixture Adapter | 网络模拟与领域级 Fixture 分离，不作为生产数据源 |
| 任务图 | Turborepo（可选） | 仅在多应用构建缓存和依赖图产生明确收益时引入 |

选型版本在实施 Issue 中锁定；禁止在本阶段混入第二套路由、状态或 UI 框架。

## 6. 领域契约

### 6.1 Authoring Source

前后端契约将重新评估。目标状态为：

```text
OpenAPI / JSON Schema
-> generated TypeScript transport types
-> transport validation in packages/contracts
-> mapper / domain validation
-> frontend domain model
```

迁移期允许继续从 Pydantic 导出 JSON Schema，但前端不得手写同名传输类型。

### 6.2 Transport 与 Domain 分离

HTTP DTO 不直接进入组件：

```ts
interface ResearchRepository {
  getProject(projectId: ProjectId): Promise<ResearchProject>
  createRun(contract: ResearchContract): Promise<ResearchRun>
  getArtifact<T extends ArtifactKind>(ref: ArtifactRef<T>): Promise<ArtifactOf<T>>
  submitFeedback(input: FeedbackInput): Promise<RevisionPlan>
}
```

Adapter 负责：

- DTO 校验
- 日期、枚举和 ID 标准化
- transport error 转换
- API pagination / cursor
- execution mode、source mode 和版本元信息

组件只接收稳定的领域对象。

## 7. 双 Adapter 架构

```text
Feature / Application Service
           |
ResearchRepository
      /           \
FixtureAdapter   HttpAdapter
```

### 7.1 Fixture Adapter

用途：

- 首页 Demo Replay
- Guided Tour
- 视觉回归
- Story / component fixtures
- 后端未完成时的契约开发

要求：

- Fixture 版本化。
- 包含 `execution_mode=demo_replay` 与 `source_mode=fixture`。
- 字段严格通过同一 Schema。
- 不使用手写无来源数据冒充真实运行缓存。
- 每个 Fixture 包含 scenario、created_at、schema_version 和 provenance note。

### 7.2 HTTP Adapter

用途：

- 本地联调
- 公网 Live Run
- 真实项目与运行

要求：

- 支持 AbortSignal、request_id 和统一错误。
- TanStack Query key 与项目、运行、产物版本绑定。
- 不在组件中拼接 URL。
- 认证或临时会话令牌通过单独 session port 管理。

### 7.3 Adapter 选择

- build-time 环境只决定可用能力，不决定某个结果的来源。
- 用户在 Guided Tour 中切换 Demo Replay / Live Run。
- 每个 ArtifactVersion 或来源展示模型携带 `source_mode`，页面不可仅依赖全局模式判断。

## 8. 前端分层

```text
Route
-> Feature Page
-> Application Service / Hook
-> Repository / Workspace Core
-> Domain Model
-> UI / Visual Components
```

### 8.1 `app`

- Provider composition
- Router
- Error boundary
- Query client
- Session
- Theme / quality settings
- Global command registry

### 8.2 `features`

建议：

```text
features/
├─ projects/
├─ research-contract/
├─ runs/
├─ data-artifacts/
├─ paper-acquisition/
├─ literature/
├─ reasoning/
├─ graph/
├─ evidence/
├─ feedback/
├─ sharing/
└─ guided-tour/
```

每个 feature 公开：

- route components
- public hooks / application services
- domain-specific UI
- tests

禁止跨 feature 深层路径导入。

### 8.3 `shell`

- Top Status Rail
- Research Atlas
- Research Canvas
- Provenance Observatory
- Research Console
- responsive shell

Shell 不实现具体数据、论文或推理业务。

## 9. 工作台状态

### 9.1 Server State

TanStack Query 管理：

- Projects
- Runs
- TaskSteps
- Artifacts
- Evidence
- Versions
- Feedback status
- Share resources

### 9.2 Local State

Zustand 管理：

- 当前选择对象
- 左右栏开合
- 面板布局和尺寸
- Panel slots
- pinned Evidence
- Command Palette
- Research Console 展开状态
- 图形质量和 Reduced Motion 派生设置

不得把后端任务状态复制成长期本地真相。

### 9.3 URL State

以下状态应可分享或恢复：

- project_id
- run_id
- artifact ref
- selected object
- panel layout preset
- graph filters
- read-only share token

瞬时 hover、拖拽位置和未提交输入不进入 URL。

## 10. WebGL 与视觉运行时

### 10.1 包边界

`packages/visual-engine`：

```text
visuals/
├─ scenes/
│  ├─ signal-planet/
│  ├─ evidence-assembly/
│  └─ graph-transition/
├─ shaders/
├─ ascii/
├─ quality/
├─ runtime/
└─ react/
```

- 场景输入使用经过定义的 Visual Model，不读取原始 API DTO。
- Shader、纹理和字符 Atlas 统一管理。
- Astro 与 Workspace 通过 React 组件复用场景。

### 10.2 Visual Model

```ts
interface CelestialVisualModel {
  seed: string
  phase: 'signal' | 'question' | 'evidence' | 'workspace'
  density: number
  completeness: number
  relationStrength: number
  progress: number
  quality: 'high' | 'medium' | 'low'
  executionMode: 'demo_replay' | 'live'
}
```

业务数据到 Visual Model 的映射必须显式、可测试。视觉模型不得反向成为科研数据来源。

### 10.3 资源生命周期

- 路由级 lazy import。
- Canvas 进入视口后初始化。
- 页面隐藏时暂停 render loop。
- 卸载时 dispose geometry、material、texture、render target。
- DPR 设置上限。
- 错误边界回退到 Poster。
- WebGL 不阻塞静态首屏和主要 CTA。

### 10.4 质量检测

初始质量由设备能力、DPR、Reduced Motion、节能状态和运行采样决定。运行中可根据帧耗时降级，不自动升级造成抖动。

## 11. Design Token 架构

`packages/design-tokens` 输出：

- `tokens.css`
- Tailwind theme bridge
- TypeScript token names（仅用于需要 JS 的 Canvas / chart）
- typography presets
- motion presets
- graphics quality presets

原则：

- 颜色原始值只在 token package 定义。
- WebGL 从 token 的构建产物读取相同色值。
- status、brand、surface 和 visual token 分层。
- 不把 Canvas 颜色硬编码在 Shader 文件。

## 12. UI Component 架构

`packages/ui` 不是通用设计系统项目，而是星文智析的产品组件层。

### 12.1 基础组件

- Button
- IconButton
- Input / Textarea
- Select / Combobox
- Tooltip / Popover / Dialog
- Menu / Command Palette
- Tabs / Segmented Control
- Table primitives
- Skeleton / Empty / Error

### 12.2 产品组件

- BrandMark
- RunModeBadge
- ArtifactHeader
- SourceModeStrip
- ResearchContractEditor
- TaskStepRail
- EvidenceLocator
- VersionBadge
- QualityMetric
- SplitPaneHeader

产品组件允许依赖 domain 的轻量类型，但不调用 Repository。

## 13. 路由建议

### 13.1 Brand Site

```text
/
/case/exoplanet
/start
```

### 13.2 Guided Tour

```text
/tour
/tour/:scenarioId
/tour/:scenarioId/:step
```

### 13.3 Workspace

```text
/workspace
/workspace/projects/:projectId
/workspace/projects/:projectId/runs/:runId
/workspace/projects/:projectId/runs/:runId/data/:artifactId
/workspace/projects/:projectId/runs/:runId/papers/:artifactId
/workspace/projects/:projectId/runs/:runId/literature/:artifactId
/workspace/projects/:projectId/runs/:runId/reasoning/:artifactId
/workspace/projects/:projectId/runs/:runId/graph/:artifactId
/share/:shareToken
```

路由可通过 URL search params 恢复面板布局与选中对象，但必须限制长度和敏感数据。

## 14. 构建与部署

本节描述迁移后的目标状态，不改变当前 `apps/web`、Compose 或 `docs/setup.md` 命令。

### 14.1 构建产物

- `site`: 静态 HTML、CSS、预渲染资源和按需 JS Islands。
- `workspace`: SPA 静态资源。
- 同域部署时由平台将 `/workspace/*`、`/tour/*` 和 `/share/*` fallback 到 workspace entry。
- 目标工作台只以 `/api/v2` 为默认 Contract；`/api/v1` 仅能通过显式迁移 Adapter 服务当前回退基线，在 A-03 Contract / E2E 门禁通过前不得删除，但不得成为新页面的目标路径。

### 14.2 Docker

迁移后 Compose 至少包含：

- `site` 或统一前端静态服务
- `workspace` 构建/开发服务
- `api`
- `postgres`

开发期可通过一个 Node 容器运行 pnpm workspace 的两个 dev server，但生产部署应输出静态产物，不要求引入 Nginx 作为 MVP 前置。

### 14.3 环境变量

- Astro 公开变量使用明确的 `PUBLIC_` 前缀。
- Workspace 公开变量使用 `VITE_`。
- 只允许 API Base URL、公开部署标识和非敏感功能开关。
- 模型、数据库和论文源凭据只存在后端。

## 15. Tauri 预留

定义平台 Ports：

```ts
interface FileExportPort {
  saveFile(input: ExportFile): Promise<ExportResult>
}

interface NotificationPort {
  notify(input: NotificationInput): Promise<void>
}

interface LocalCachePort {
  get<T>(key: string): Promise<T | null>
  set<T>(key: string, value: T): Promise<void>
}
```

Web 提供 browser adapter；未来 Tauri 提供 native adapter。Feature 不直接 import Tauri API。

## 16. 非功能、安全与失败模式

| 风险或故障 | 目标行为 |
| --- | --- |
| WebGL 不可用或上下文丢失 | 静态 Poster 与完整 DOM 内容继续可用，CTA 和工作台不失效 |
| 外部 API / 模型超时 | Live Run 显示失败、重试或可用真实缓存；不得自动伪装成成功 |
| Fixture 与 HTTP 漂移 | Adapter 一致性测试失败并阻断合并 |
| 大数据表或图谱 | 虚拟化、规模上限、渐进加载；不把全部对象一次渲染到 DOM |
| 多 Run 并发 | Server state 以 project/run/version query key 隔离，取消请求不会污染其他 Run |
| 临时会话失效 | 明确提示过期并保留可导出的公开结果，不在浏览器持久化敏感令牌 |
| 分享链接泄露 | 只读、可撤销、可过期、最小范围；服务端存 token hash，不把会话凭据放入 URL |
| 用户与论文文本 | React 默认转义；禁止直接渲染未净化 HTML，外链和来源 URL 通过协议与 host allowlist 校验 |

静态站和工作台部署必须定义 CSP、HSTS、`X-Content-Type-Options`、`Referrer-Policy` 与最小 CORS allowlist。免登录会话使用 Secure、HttpOnly、SameSite Cookie；写操作采用 CSRF 防护和速率限制。具体接口约束见 `API_CONTRACT.md`。

## 17. 测试策略

### 17.1 单元与契约

- Domain parser / schema
- DTO to domain mapper
- Visual Model mapper
- Repository adapters
- state selectors
- quality tier logic

### 17.2 组件与交互

- Research Contract
- Split panes
- Evidence selection
- status and source modes
- keyboard navigation
- error / empty / cached states

### 17.3 E2E

- 首页四幕与跳过
- Demo Replay 完整路径
- Live Run 创建和失败
- 多项目切换
- 数据到 Evidence
- Relation 到 Trace / Evidence
- Graph edge 到 Evidence
- 反馈产生修订版本
- 只读分享

### 17.4 视觉与性能

- Playwright screenshot baselines
- WebGL Poster fallback
- Reduced Motion
- High / Medium / Low quality
- 关键 Lighthouse / Web Vitals 预算
- GPU 资源释放 smoke test

## 18. CI 门禁

前端 CI 至少执行：

```text
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e-smoke
pnpm test:visual-smoke
pnpm verify:architecture
pnpm verify:tokens
```

`verify:architecture` 应阻止：

- domain 依赖 UI / React
- UI 直接依赖 data-access
- feature 深层跨包导入
- 原始色值散落在 token 之外
- 裸 API URL 和组件内 fetch
- Shader 中硬编码品牌色

## 19. 迁移策略

### 19.1 Phase 1：平台基线

- 建立 pnpm workspace。
- 创建 `apps/site`、`apps/workspace` 与共享包。
- 保留旧 Vue 骨架作为短期参考，不添加新功能。
- CI 同时构建新应用。

### 19.2 Phase 2：设计与入口

- 迁移 Token 和字体。
- 实现 BrandMark、基础 UI 和 WebGL runtime。
- 完成首页静态/视觉框架与静态 Workspace Shell，不绑定领域状态或业务行为。

### 19.3 Phase 3：领域行为

- 在既有 Shell 上绑定 ResearchContractDraft / ResearchContract、Project / Run、Guided Tour FSM 与 WorkspaceSnapshot。
- 完成 Repository Port、Fixture / HTTP Adapter、Atlas / Canvas / Observatory / Console 交互，不重建 Shell。
- 核心科研产物视图由 A-04～A-10 分别实现，不纳入 A-03。

### 19.4 Phase 4：真实 Contract 集成与功能迁移

- X-01 使 HTTP Adapter 接入 B-04 生成的真实 `/api/v2` Contract。
- A-04～A-10 依次迁移科研产物视图、来源版本与反馈能力。
- 完成 Contract、E2E、视觉和性能门禁后，才删除 `apps/web` 及其旧前端依赖。
- 更新 Docker、README、setup 与部署文档。

迁移完成前不得在旧 Vue 和新 React 中重复实现同一业务功能。

## 20. 架构验收

- Brand Site 与 Workspace 可以独立构建和部署。
- 共享包不存在循环依赖。
- Fixture 与 HTTP Adapter 通过相同 Repository contract。
- 页面和组件不读取原始 API DTO。
- WebGL 可延迟加载、暂停、释放和降级。
- 工作台核心可被未来 Tauri 复用。
- 旧 Vue 前端最终完全删除，没有双栈长期维护。
- 所有关键决策与 `DESIGN.md`、ADR 和 Issue 保持一致。
