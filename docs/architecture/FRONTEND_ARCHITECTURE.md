# Frontend Architecture

| 元数据    | 值                                                       |
| --------- | -------------------------------------------------------- |
| Status    | Accepted                                                 |
| Authority | 前端运行时、上游源码治理、模块分层、依赖方向与状态所有权 |

本文定义 Brand Site 与 Research Workspace 的工程分层、依赖方向、数据边界与上游 Agent 源码治理规范。

## 1. 运行时

| 应用             | 技术         | 职责                                          |
| ---------------- | ------------ | --------------------------------------------- |
| `apps/site`      | Astro        | Brand Site 静态站                             |
| `apps/workspace` | React + Vite | Research Workspace 宿主、路由与 UI 运行时组合 |
| `apps/api`       | FastAPI      | 后端 API、Workflow 与持久化                   |

精确依赖版本以根 `package.json` 与 `pnpm-lock.yaml` 为准。

**当前 Workspace 基线：** `apps/workspace` 已在 `/workspace` 薄宿主内挂载源码采用后的 OpenHands 桌面产品壳，保留导航、活动区、面板、标签、Composer、Overlay、焦点、滚动与尺寸调整机械结构。当前只定义编译安全的薄执行接口，不包含 Research Adapter、领域 ViewModel 或科研 Renderer；未连接 Agent 运行服务时，执行控件保持禁用。私有工作台仅使用 `/workspace`，`/share/$shareToken` 继续维持只读安全边界。

## 2. 模块分层

```text
Workspace Host
  -> Router / Provider / Runtime Composition
Upstream Agent UI
  -> Shell / Navigation / Activity / Workspace / Composer
Research UI
  -> Event Renderer / Artifact Renderer / Evidence Inspector / Version Diff
Research Adapter
  -> Domain -> UI ViewModel
  -> UI Intent -> Application Command
Existing Core
  -> Domain / Repository Port / Fixture / HTTP Adapter / Workspace Controller
```

## 3. 上游 Agent 源码治理

前端重建坚持“成熟骨架优先，不得参考后重新手写”。采用上游 Agent 源码前必须记录：

- **Repository & Commit**：固定官方仓库、固定 Tag 与 40 位 SHA 提交号。
- **License & Notice**：确认兼容开源许可证，完整保留版权与 NOTICE 声明。
- **Source Scope & Mapping**：先独立冻结需要的 OpenHands Product Mechanics（Shell、ConversationMain、Navigation、Tabs、Composer、Command Menu、Activity grouping、public event presentation、Resize、Focus 与状态展示），再建立 Upstream -> Local 源码映射表；本地 import closure 只负责验证实现完整、可解析且无孤立文件，不能反向定义采用范围。
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

`KEEP_AS_IS` 源码使用一个锁定在 `upstream-lock.json` 的聚合树摘要校验，不保存或逐文件复算 SHA；适配文件通过原始路径、采用类别、修改原因、代码审查与运行测试治理。批准的 Mechanics Scope、显式列出的 transitive mechanics 与实际 Import Closure 分开维护：前两者是人工架构边界，后者只验证所有落盘文件从 `src/root.tsx` 可达、本地导入可解析且没有孤立文件；禁止保留未参与构建的旧 facade 或残缺依赖树。Frontend API、Agent Runtime、认证、WebSocket、Git/Coding、移动端、Telemetry、兼容模块、Cloud、Enterprise 与 Sandbox 源码统一归入 `EXCLUDED`，不得出现在 vendored 目录。

`source-scope.json.files` 是精简的采用边界清单，只包含 approved/transitive mechanics 与代表性排除项；它不声称枚举冻结上游的全部源文件。完整的私有推理与禁用领域库存由 `source-policy.json` 维护，`scope_contract` 与 `total_scoped_files` 明确这一职责边界，避免恢复大体积的机器清单。

上游源码升级需经过：锁定 SHA → 许可证审查 → 更新映射与 Source Policy → 上游 Diff 审查 → 运行契约与 UI 回归 → 独立合并。实际 Vendor 必须重新从官方仓库 checkout `v1.10.0` 并校验 `566386…37f4b`，否则拒绝采用。

### 3.2 推理披露边界

上游 Agent UI 可保留 Activity 与 disclosure 等成熟交互机制，但模型私有 raw reasoning 不得进入产品 ViewModel、持久化边界或 UI。`source-policy.json` 将私有推理 extractor/renderer 全部排除；唯一保留的 disclosure 交互组件必须显式适配为只接收公开、可审计内容。这些约束优先于机械 Source Scope 分类。

用户可见推理必须显式、可核验且与 Evidence 关联。`ReasoningTrace` 是公开可审计的推导记录，不等于模型私有 chain-of-thought；具体领域语义见 `docs/ai/REASONING_PROTOCOL.md`。

Activity 采用 OpenHands 的事件列表、连续事件分组、可展开事件组、渐进状态展示与滚动锚定机制；OpenHands Activity 仅消费 domain-neutral presentation event，Research Adapter 负责将 Project、Run、Artifact、Evidence 等领域语义映射到该 presentation contract；运行时只注入公开 Activity Event，空状态不生成测试或演示事件。

### 3.3 共享 UI、shadcn 与图标治理

`@xingwen/ui` 是 Brand Site、Workspace Page / Feature 与 OpenHands 适配层唯一的通用共享 UI 入口。消费者只能使用包公开 `exports`；不得深层导入 `packages/ui/src/*`，不得在 Page / Feature 建立第二套 Button、Link、Input、Dialog 或 Icon Primitive。OpenHands 已采用的 Shell、Activity、Tabs、Composer、Overlay、Focus 与 Resize mechanics 继续作为产品机械结构复用，不因共享组件治理而重写。

shadcn 仅作为按需采用的源码来源，不作为第二套运行时组件库。采用顺序固定为：检查 OpenHands mechanics 与 `@xingwen/ui` 现有 export → 确认生产消费者缺口 → 通过 `packages/ui/components.json` 审查当前 registry 配置与源码 → 只将需要的组件放入 `@xingwen/ui`。每个 shadcn-derived component 必须在 `packages/ui/component-sources.json` 记录来源、许可证、适配说明与现有生产消费者；没有消费者不得加入。

Lucide 是唯一通用动作图标库，由 `@xingwen/ui/icons` 提供受控 public export；App、Page、Feature 与 OpenHands 适配源码不得直接依赖图标包。品牌资产与科研专用可视化不经 Lucide 替换。`@xingwen/ui` 只消费 `--color-*`、`--space-*`、`--control-*`、`--icon-*`、`--font-size-ui-*`、`--line-height-ui-*`、`--radius-*`、`--shadow-*`、`--motion-*` 与 `--focus-*` 等 Core semantic Token，不得依赖 `--workspace-*`、`--oh-*` 或 Raw palette。

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
  -> Repository Port

Artifact / Evidence Renderer
  -> @xingwen/domain
  -> @xingwen/ui
```

**依赖约束：**

- 共享包 (Shared Packages) 不得反向依赖 App。
- `@xingwen/domain` 不依赖 React、DOM、HTTP 或上游 UI 组件。
- 前端页面不得直接调用 `fetch` 或直接解析后端原始 Transport DTO。
- 依赖只能经由 Package 的公开 `exports` 导入，不得以深层私有路径或 `@ts-expect-error` 绕过。

## 5. 状态所有权

| 状态类型                          | 权威来源                         |
| --------------------------------- | -------------------------------- |
| Project / Run / Artifact 路由     | Router                           |
| Server state、缓存与 Mutation     | Query Layer (经 Repository Port) |
| Run / Artifact / Evidence 事实    | Domain / Repository              |
| 流式交互与输入草稿                | Upstream Agent Runtime           |
| Workspace 布局与恢复              | Workspace Controller             |
| 组件内部交互状态 (Hover / Active) | Local Component State            |
| Share / Export 版本               | Server / ShareSnapshot           |

同一事实在前端不得由多个全局 Store 重复持有。

## 6. 路由与数据流

```text
Transport DTO -> Contract Validation -> Domain Mapping -> Repository Port -> Research Adapter -> UI
```

- Fixture 与 HTTP Adapter 返回完全一致的 Domain Model。
- Agent Runtime 仅管理交互与流式展现，不直接创建科研事实或推进服务端状态机。
- 未知类型的 Artifact 明确渲染失败。

## 7. 构建与上游同步

- 上游源码升级需经过：锁定 SHA -> 许可证审查 -> 更新映射与 Source Policy -> 上游 Diff 审查 -> 运行契约与 UI 回归 -> 独立合并。
- 生产构建使用单根 `pnpm-lock.yaml`；大型组件使用代码分割（Code-Splitting）。
