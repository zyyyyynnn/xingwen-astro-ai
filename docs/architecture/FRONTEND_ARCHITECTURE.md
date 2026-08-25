# Frontend Architecture

| 元数据 | 值 |
| --- | --- |
| Authority | 前端运行时、成熟交互源码治理、模块分层、依赖方向与状态所有权 |

本文定义 Brand Site 与 Research Workspace 的工程分层、依赖方向、数据边界和已采用交互源码的治理规则。精确第三方来源、版本、许可证和锁定信息由法律文件、依赖锁文件及机器 provenance 维护，不在治理 Markdown 中复制。

## 1. 运行时边界

| 应用 | 职责 |
| --- | --- |
| `apps/site` | Brand Site 静态站 |
| `apps/workspace` | Research Workspace 宿主、路由与 UI 运行时组合 |
| `apps/api` | API、Workflow 与持久化服务 |

精确依赖版本以 package manifest、lockfile 与服务环境定义为准。

`/workspace` 是唯一私有工作台入口。采用成熟交互源码只证明壳层 mechanics 已落地，不等于 ResearchRun、模型运行时或科研 Renderer 已经实现。执行态只能由真实服务返回的状态、事件和版本化产物驱动；没有真实运行服务时必须明确不可执行。`/share/$shareToken` 是冻结版本的独立只读安全边界。

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
  -> adopted agent mechanics / Research Navigation / Thread / Composer
  -> Research Presentation / exhaustive Artifact Renderer Registry / shared Inspector

Research Adapter
  -> Domain -> UI ViewModel
  -> UI Intent -> Application Command
  -> RunEvent -> authorized-project ActivityPresentationEvent
  -> Repository/Data-access Error -> stable public application error
```

## 3. 成熟交互源码治理

当前 Workspace 采用一套已经冻结并验证的成熟 Agent 产品 mechanics。治理原则是“保留成熟交互机制，替换为本项目领域语义”，而不是根据外观重新手写一套近似实现。

必须保持：

- 单一 Workspace Shell；
- Navigation、Thread、Activity grouping/disclosure、Composer、Command、Resize、Scroll、Focus 等已采用 mechanics 的行为契约；
- approved mechanics scope 与实际 import closure 一致，无孤立旧 facade；
- 语义、安全、隐私与领域 policy 高于机械源码可达性；
- 精确来源、revision、许可证、NOTICE 与 aggregate provenance 由机器元数据和法律文件维护；
- 外部源码升级必须独立进行：锁定来源 → license/provenance 审查 → scope/policy diff → 产品行为回归 → 独立 PR。

治理 Markdown 不记录外部产品名称、仓库 URL、tag、commit 或迁移历史。

### 3.1 推理披露边界

已采用的 Activity 机制保留 Action → Observation 原位更新、连续操作分组、折叠披露与滚动锚定。服务端验证后的 `public_analysis` 通过项目私有 RunEvent 进入 `ActivityPresentationEvent`；默认显示短摘要，完整内容由用户控制展开。

Provider 私有 `reasoning_content` 不进入前端、公开分享、导出或正式产物。前端不得解析 `<think>`、伪造分析文案或直接消费 provider 原始事件，所有内容先经过服务端持久化契约。

`ReasoningTrace` 是 Evidence-bound 的公开可审查领域记录，不等于模型私有 chain-of-thought。

### 3.2 共享 UI 与基础组件治理

`@xingwen/ui` 是 Brand Site、Workspace Page / Feature 与 adopted mechanics 适配层唯一的通用共享 UI 入口。

- 消费者只使用 package public exports，不深层导入 `packages/ui/src/*`；
- Page / Feature 不建立第二套 Button、Link、Input、Dialog、Tabs、Popover、Sheet、Icon 或 Focus primitive；
- 需要的新 primitive 先确认现有 consumer 缺口，再加入共享 UI；
- 第三方组件来源、许可证与当前生产 consumer 记录在机器 provenance / legal notices，不写进治理 Markdown；
- 通用动作图标由 `@xingwen/ui/icons` 统一 public export；
- 品牌资产与科研专用可视化不强制套用通用动作图标；
- 共享 UI 只消费 Core semantic Token，不依赖 Feature 私有视觉变量。

Router 拥有 SPA 导航与 URL 状态；共享 UI 拥有 Link 的视觉和可访问性 contract。二者不得互相复制职责。

## 4. 依赖方向

```text
apps/workspace
  -> adopted interaction mechanics
  -> Research Adapter
  -> @xingwen/ui
  -> @xingwen/design-tokens
  -> @xingwen/workspace-core
  -> @xingwen/data-access
  -> @xingwen/domain

Research Adapter
  -> @xingwen/domain
  -> @xingwen/data-access narrow public ports/errors boundary

Artifact / Evidence Renderer
  -> @xingwen/domain
  -> @xingwen/ui
```

依赖约束：

- 共享包不得反向依赖 App；
- `@xingwen/domain` 不依赖 React、DOM、HTTP 或 UI runtime；
- 前端页面不得直接调用 `fetch` 或直接解析 raw Transport DTO；
- Contract authoring 的对象、字段、来源和成果选项读取服务端 catalog，经 Repository 映射为 Domain；App 不保存第二份目录常量；
- 依赖只通过 package public exports 导入；
- 不使用 `any`、不安全断言或 `@ts-expect-error` 绕过契约；
- DTO 必须 runtime validate 后才能映射为 Domain。

### Artifact Renderer Registry

Renderer Registry 是 Artifact kind dispatch 的唯一 owner：

- 对领域 `ARTIFACT_KINDS` 穷举；
- 每个 kind 只有一个 descriptor；
- descriptor 统一声明 label、priority、Thread/Fullscreen renderer 及 compare/evidence/download/layout capability；
- layout mode 只使用有限语义集合；
- Renderer 不创建自己的页面 Shell；
- 未知 kind fail closed；
- 无专用 renderer 的 kind 使用统一 user-safe fallback，不显示 raw JSON dump。

## 5. 状态所有权

| 状态类型 | 权威来源 |
| --- | --- |
| Project / Thread / Run / ArtifactVersion 选择 | Router |
| Server state、缓存与 Mutation | Query Layer，经 Repository Port |
| Thread / Contract / Run / Artifact / Evidence 事实 | Domain / Repository |
| Research assistant outcome | API ModelExecution + Thread entries |
| 交互机械与输入草稿 | Workspace Controller / Presentation Boundary |
| Workspace 布局与恢复 | Workspace Controller |
| 右侧研究栏可见性与宽度 | Local UI preference |
| Fullscreen 结果选择 | Router |
| Share / Export 版本 | Server / ShareSnapshot |

同一事实不得由多个全局 Store 重复持有。

## 6. 路由与数据流

```text
Transport DTO
→ Contract Validation
→ Domain Mapping
→ Repository Port
→ Research Adapter
→ UI
```

版本化产物的唯一前端路径：

```text
Router(projectId, artifactVersionId)
→ Application Query
→ Research Adapter
→ Artifact presentation descriptor
→ ThreadRenderer or FullscreenRenderer
```

右侧结果栏只消费 Artifact index projection，绝不渲染 Fullscreen detail。Fullscreen 是真正的结果工作区，不是固定尺寸 Dialog。

- Fixture 与 HTTP Adapter 返回一致 Domain Model；
- adopted mechanics 只管理交互与公开事件展现，不是后端 Agent Runtime 或事件存储；
- Session Gate 负责私有会话边界；
- Query Layer 负责 server state、分页、polling/backoff、mutation invalidation 和终态后的 Artifact 刷新；
- `/workspace` 的首次使用、项目创建和项目恢复都留在同一个 Workspace Shell；
- Evidence Inspector 是跨 Artifact 共享 presentation contract；
- `/share/$shareToken` 只读取冻结公开投影，不复用私有读取路径。

## 7. Design Token 与 Feature 视觉约束

Feature/Page 的 spacing、dimension、typography、line-height、radius、border、shadow、z-index、breakpoint、density、panel geometry、motion 必须消费 semantic design token 或共享组件 variant。

禁止：

- Feature-level arbitrary px/rem 或临时视觉常量；
- 为单页复制基础 primitive；
- 为 Graph 同时维护 CSS geometry 与布局 geometry 两套权威；
- 用 Badge/Pill/Card 堆叠替代信息层级；
- 用内部 ID、hash、producer、adapter、raw enum 或实现来源作为默认产品 metadata。

## 8. 构建与升级

- 生产构建使用单一锁文件；
- 大型 Renderer / visualization 使用按需加载；
- adopted mechanics 或共享 UI 的来源升级必须独立 review，不与业务功能顺手混合；
- 精确来源信息只更新机器 provenance 与法律文件；
- 产品 Authority 只记录升级后仍成立的当前行为，不记录迁移过程。
