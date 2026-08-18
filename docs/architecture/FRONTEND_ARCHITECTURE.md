# Frontend Architecture

| 元数据    | 值                                                       |
| --------- | -------------------------------------------------------- |
| Authority | 前端运行时、上游源码治理、模块分层、依赖方向与状态所有权 |

本文定义 Brand Site 与 Research Workspace 的工程分层、依赖方向、数据边界与上游 Agent 源码治理规范。

## 1. 运行时

| 应用             | 技术         | 职责                                          |
| ---------------- | ------------ | --------------------------------------------- |
| `apps/site`      | Astro        | Brand Site 静态站                             |
| `apps/workspace` | React + Vite | Research Workspace 宿主、路由与 UI 运行时组合 |
| `apps/api`       | FastAPI      | 后端 API、Workflow 与持久化                   |

精确依赖版本以根 `package.json` 与 `pnpm-lock.yaml` 为准。

`/workspace` 是唯一私有工作台入口。实现可以采用锁定版本的 OpenHands-derived
interaction mechanics，但该源码选择不等于 Xingwen ResearchRun、模型运行时或科研
Renderer 已经实现。只有真实服务返回的状态、事件和版本化产物可以驱动执行态；没有
真实运行服务时，执行控件必须保持禁用并显示明确状态。`/share/$shareToken` 继续是
固定版本的只读安全边界。

## 2. 模块分层

```text
Experience
  -> Frontend Application Boundary
  -> Research Adapter / Query Layer
  -> Repository Port
  -> Fixture / HTTP Adapter
  -> API Application Service
  -> Research Assistant / ModelExecutionPort
  -> Workflow / Step Adapter
  -> Scientific Pipeline
  -> Publisher
  -> ArtifactVersion / Evidence / SourceSnapshot

Frontend Application Boundary
  -> Workspace Host / Router / Query Provider / Session Gate
  -> OpenHands-derived mechanics / Research Navigation / Thread / Composer
  -> Research Presentation / exhaustive Artifact Renderer Registry / existing Inspector

Research Adapter
  -> Domain -> UI ViewModel
  -> UI Intent -> Application Command
  -> RunEvent -> authorized-project ActivityPresentationEvent
  -> Repository/Data-access Error -> stable public application error
```

## 3. 上游 Agent 源码治理

前端重建坚持“成熟骨架优先，不得参考后重新手写”。采用上游 Agent 源码前必须记录：

- **Repository & Commit**：固定官方仓库、固定 Tag 与 40 位 SHA 提交号。
- **License & Notice**：确认兼容开源许可证，完整保留版权与 NOTICE 声明。
- **Source Scope & Mapping**：先独立冻结需要的 OpenHands Product Mechanics（Shell、Navigation、Composer、Activity grouping/disclosure、Resize、Scroll、Focus），再建立 Upstream -> Local 源码映射表；本地 import closure 只负责验证实现完整、可解析且无孤立文件，不能反向定义采用范围。XingWen 的 Contract / Artifact / Evidence 语义不得写进 vendor-derived primitive。
- **Source Policy**：在机械依赖可达性之外固定语义、安全与隐私边界；Policy 约束优先于 `KEEP_AS_IS`。
- **Governance Rules**：严禁跟随浮动 main 分支；严禁混用非兼容协议代码；仓库内有且仅有一套 Workspace Shell。

### 3.1 唯一上游 Agent 产品

| 项           | 值                                                         |
| ------------ | ---------------------------------------------------------- |
| Product      | OpenHands                                                  |
| Repository   | `https://github.com/OpenHands/OpenHands.git`               |
| Tag          | `v1.10.0`                                                  |
| Commit       | `56638693908b8ac83a2fa3bde6eb6c33aae37f4b` (40 位 SHA)     |
| License      | MIT                                                        |
| 采用方式     | source-level vendor（源码级采用，非设计级模仿）            |
| 产品机制策略 | preserve-upstream（保留 OpenHands 产品机制）               |
| 领域适配策略 | adapter-and-renderer（经 Adapter / Renderer 替换科研领域） |
| 唯一性       | 仓库内唯一 Agent Product Source；禁止混壳 / 第二套 Shell   |

冻结元数据位于 `apps/workspace/upstream/openhands/`（`upstream-lock.json`、`source-scope.json`、`source-policy.json`、`vendor-blueprint.json`、`provenance-schema.json`、`provenance.json`、`LICENSE.upstream`、`NOTICE.md`），由 upstream adoption 机器门禁强制。

`KEEP_AS_IS` 源码使用一个锁定在 `upstream-lock.json` 的聚合树摘要校验，不保存或逐文件复算 SHA；保留这一份用于锁定上游来源的 aggregate provenance，但禁止新增每个文件 SHA、CSS SHA、UI copy SHA、组件树 SHA 或 review SHA 清单。适配文件通过原始路径、采用类别、修改原因、代码审查与运行测试治理。批准的 Mechanics Scope、显式列出的 transitive mechanics 与实际 Import Closure 分开维护：前两者是人工架构边界，后者只验证所有落盘文件从 `src/root.tsx` 可达、本地导入可解析且没有孤立文件；禁止保留未参与构建的旧 facade 或残缺依赖树。Frontend API、Agent Runtime、认证、WebSocket、Git/Coding、Telemetry、兼容模块、Cloud、Enterprise 与 Sandbox 源码统一归入 `EXCLUDED`，不得出现在 vendored 目录。

`source-scope.json.files` 是精简的采用边界清单，只包含 approved/transitive mechanics 与代表性排除项；它不声称枚举冻结上游的全部源文件。公开步骤分析、Agent Activity 与禁用领域边界由 `source-policy.json` 维护，`scope_contract` 与 `total_scoped_files` 明确这一职责边界，避免恢复大体积的机器清单。

上游源码升级需经过：锁定 SHA → 许可证审查 → 更新映射与 Source Policy → 上游 Diff 审查 → 运行契约与 UI 回归 → 独立合并。实际 Vendor 必须重新从官方仓库 checkout `v1.10.0` 并校验 `566386…37f4b`，否则拒绝采用。

### 3.2 推理披露边界

上游 Agent UI 保留 Activity、Action → Observation 原位替换、连续操作分组与 CollapsibleThinking 机制。服务端验证后的中文 `public_analysis` 通过项目私有 RunEvent 进入 `ActivityPresentationEvent`；事件行默认显示一行真实摘要，完整内容默认收起并由用户控制展开。Provider 私有 `reasoning_content` 不进入前端、公开分享、导出或正式产物。前端不得解析 `<think>`、伪造分析文案或直接消费 provider 原始事件，所有内容必须先经过服务端持久化契约。`source-policy.json` 的这些约束优先于机械 Source Scope 分类。

用户可见推理必须显式、可核验且与 Evidence 关联。`ReasoningTrace` 是公开可审计的推导记录，不等于模型私有 chain-of-thought；具体领域语义见 `docs/ai/REASONING_PROTOCOL.md`。

Research Thread 采用 OpenHands 的事件列表、连续事件分组、可展开事件组、渐进状态展示与滚动锚定机制；这些是交互 mechanics，不是第二套产品事实模型。公开分析与其后工具动作直接进入扁平主消息流，系统级 Plan / Run 状态不作为 Thread 事件渲染。分析与工具共享同一事件行结构、单一状态化语义图标及文字状态。Research Adapter 只按稳定 `activity_id` 合并 reasoning 增量和工具 Action → Observation，不从 Step 名称反推或重写内容。空状态不生成测试或演示事件。

### 3.3 共享 UI、shadcn 与图标治理

`@xingwen/ui` 是 Brand Site、Workspace Page / Feature 与 OpenHands 适配层唯一的通用共享 UI 入口。消费者只能使用包公开 `exports`；不得深层导入 `packages/ui/src/*`，不得在 Page / Feature 建立第二套 Button、Link、Input、Dialog 或 Icon Primitive。OpenHands 已采用的 Shell、Activity、Tabs、Composer、Overlay、Focus 与 Resize mechanics 继续作为产品机械结构复用，不因共享组件治理而重写。

shadcn 仅作为按需采用的源码来源，不作为第二套运行时组件库。采用顺序固定为：检查 OpenHands mechanics 与 `@xingwen/ui` 现有 export → 确认生产消费者缺口 → 通过 `packages/ui/components.json` 审查当前 registry 配置与源码 → 只将需要的组件放入 `@xingwen/ui`。每个 shadcn-derived component 必须在 `packages/ui/component-sources.json` 记录来源、许可证、适配说明与现有生产消费者；没有消费者不得加入。

Lucide 是唯一通用动作图标库，由 `@xingwen/ui/icons` 提供受控 public export；App、Page、Feature 与 OpenHands 适配源码不得直接依赖图标包。品牌资产与科研专用可视化不经 Lucide 替换。`@xingwen/ui` 只消费 `--color-*`、`--space-*`、`--control-*`、`--icon-*`、`--font-size-ui-*`、`--line-height-ui-*`、`--radius-*`、`--shadow-*`、`--motion-*` 与 `--focus-*` 等 Core semantic Token，不得依赖 `--workspace-*`、`--oh-*` 或 Raw palette。

共享 Link 视觉呈现与 Router 导航所有权划分：`@xingwen/ui` 拥有 Link 视觉外观（文本/按钮样式、焦点圈、外部链接 semantics）；TanStack Router 拥有内部 SPA 路由、类型化导航与预加载生命周期。Workspace 在路由场景下使用 TanStack Router 进行 SPA 导航不属于建立第二套视觉 Link primitive，前提是其最终消费 `@xingwen/ui` 的共享视觉 contract。`@xingwen/ui` 本身不增加 Router 框架依赖。

## 4. 依赖方向

```text
apps/workspace
  -> Upstream Agent UI
  -> Research Adapter
  -> @xingwen/ui
  -> @xingwen/design-tokens
  -> @xingwen/workspace-core
  -> @xingwen/data-access
  -> @xingwen/domain

Research Adapter
  -> @xingwen/domain
  -> @xingwen/data-access narrow public ports/errors boundary

`@xingwen/research-adapter` is the framework-free, stateless application
boundary for Domain-to-ViewModel projections, public RunEvent activity
presentation, typed UI commands, and fail-closed public application errors. It
does not own transport parsing, session lifecycle, Query/cache state, polling,
renderers, or server state.

Artifact / Evidence Renderer
  -> @xingwen/domain
  -> @xingwen/ui
```

**依赖约束：**

- 共享包 (Shared Packages) 不得反向依赖 App。
- `@xingwen/domain` 不依赖 React、DOM、HTTP 或上游 UI 组件。
- 前端页面不得直接调用 `fetch` 或直接解析后端原始 Transport DTO。
- Contract authoring 的对象、字段、来源与成果选项必须读取服务端 Manifest-backed Research Catalog，经 Repository 映射为 Domain；App 不保存第二份目录常量。
- 依赖只能经由 Package 的公开 `exports` 导入，不得以深层私有路径或 `@ts-expect-error` 绕过。
- `@xingwen/ui` 只接纳组件级交互依赖；Radix、Command 所需的 `cmdk`、通知所需的
  `sonner` 与可调整分栏所需的 `react-resizable-panels` 属于当前批准的 UI runtime。
  App 不得重写这些依赖已经负责的焦点、键盘选择、通知生命周期或 resize 状态机。
  `tslib` 仅作为已采用组件的运行时辅助依赖；第三方来源、版本、许可证与生产 consumer
  必须由 UI provenance ledger 精确记录。
- 禁止 `any`、不安全类型断言和以类型逃逸掩盖 DTO 校验；Runtime DTO 必须先验证再映射。
- Artifact Renderer Registry 必须对领域 `ARTIFACT_KINDS` 的每一项穷举注册。每个
  kind 注册唯一 descriptor，至少包含 `kind`、`label`、`displayPriority`、
  `capabilities`、`ThreadRenderer` 与 `FullscreenRenderer`；按需要声明
  `compare`、`evidence`、`download` 与 `layoutMode`。`layoutMode` 只允许有限集合
  （`reading | wide | immersive`），Renderer 不得各自任意创建页面 Shell。缺项、
  重复项与未知 kind 必须失败，不得静默进入通用文本、JSON 或 Metadata renderer；
  没有专用 renderer 的 kind 使用统一 user-safe fallback（结果名称、简短说明、
  真实可用的下载、“当前暂无专用可视化”），不显示 raw JSON dump。

## 5. 状态所有权

| 状态类型                                           | 权威来源                                     |
| -------------------------------------------------- | -------------------------------------------- |
| Project / Thread / Run / ArtifactVersion 选择      | Router                                       |
| Server state、缓存与 Mutation                      | Query Layer (经 Repository Port)             |
| Thread / Contract / Run / Artifact / Evidence 事实 | Domain / Repository                          |
| Research assistant outcome                         | API ModelExecution + Thread entries          |
| 交互机械与输入草稿                                 | Workspace Controller / Presentation Boundary |
| Workspace 布局与恢复                               | Workspace Controller                         |
| 右侧研究栏可见性与宽度（UI preference）            | Local Component State (localStorage)          |
| Fullscreen 结果选择                                | Router (`artifactVersionId`)                  |
| Share / Export 版本                                | Server / ShareSnapshot                       |

同一事实在前端不得由多个全局 Store 重复持有。

## 6. 路由与数据流

```text
Transport DTO -> Contract Validation -> Domain Mapping -> Repository Port -> Research Adapter -> UI
```

版本化产物的唯一前端路径为：

```text
Router(projectId, artifactVersionId)
  -> Application Query
  -> Research Adapter
  -> Artifact presentation descriptor
  -> ThreadRenderer or FullscreenRenderer
```

右侧结果栏只消费 Artifact index projection，绝不渲染 Fullscreen renderer 到右栏。
Fullscreen 是真正的结果工作区（全窗口 Shell），不是固定尺寸的 Dialog；论文结果
宽屏默认 report + PDF 同屏（reading/wide split、独立滚动、可调整面板、Evidence
可定位 PDF），无法访问 PDF 时真实降级。

Router 只拥有选中的 `ArtifactVersion`；Query Layer 是唯一 server-state/cache owner；Registry
是唯一 kind dispatch owner；OpenHands ConversationMain 只拥有现有面板机械。不得为产物
另建 Store、Query cache、Renderer map、Inspector、路由或生产读取路径。

- Fixture 与 HTTP Adapter 返回完全一致的 Domain Model。
- OpenHands-derived mechanics 仅管理交互与公开事件展现，不是后端 Agent Runtime、
  执行器或事件存储；它不创建科研事实或推进服务端状态机。
- Session Gate 负责私有会话边界；Query Layer 负责 server state、快照优先读取、分页、
  polling/backoff 与 mutation invalidation；运行终态事件尾部同步完成后必须刷新该 Run 的
  Artifact 集合，页面不得自行复制这些职责。
- `/workspace` 的首次使用、项目创建和已有项目恢复必须留在同一 Workspace Shell 内；
  不得为项目选择或创建建立第二套独立门户页面。
- “返回首页”只进行导航，不撤销当前 Session；需要撤销 Session 的安全动作必须是显式、独立的会话操作，并清除私有 Query 缓存；
  只有真实的 Session 失效或私有边界拒绝才进入安全的会话重建状态页。
- Evidence Inspector 是跨 Artifact 的共享 presentation contract，页面 renderer 只
  提供类型化内容与 locator；未知类型明确渲染失败。

## 7. 构建与上游同步

- 上游源码升级需经过：锁定 SHA -> 许可证审查 -> 更新映射与 Source Policy -> 上游 Diff 审查 -> 运行契约与 UI 回归 -> 独立合并。
- 生产构建使用单根 `pnpm-lock.yaml`；大型组件使用代码分割（Code-Splitting）。
