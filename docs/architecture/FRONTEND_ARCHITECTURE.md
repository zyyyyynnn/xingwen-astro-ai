# Frontend Architecture

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 前端运行时、上游源码治理、模块分层、依赖方向与状态所有权 |

本文定义 Brand Site 与 Research Workspace 的工程分层、依赖方向、数据边界与上游 Agent 源码治理规范。

## 1. 运行时

| 应用 | 技术 | 职责 |
| --- | --- | --- |
| `apps/site` | Astro | Brand Site 静态站 |
| `apps/workspace` | React + Vite | Research Workspace 宿主、路由与 UI 运行时组合 |
| `apps/api` | FastAPI | 后端 API、Workflow 与持久化 |

精确依赖版本以根 `package.json` 与 `pnpm-lock.yaml` 为准。

**A-20 退役状态：** Research Workspace 产品层（Upstream Agent UI / Research Adapter 及其页面）已退役。`apps/workspace` 仅保留 `/workspace` 固定宿主与 `/share/$shareToken` 安全边界；旧引导路由与旧入口重定向至 `/workspace`。重建前，退役内容由 `scripts/check-frontend-legacy.mjs` 门禁强制不得回归；本文各节为产品层重建后的目标形态。

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
- **Source Scope & Mapping**：明确采用与排除的目录，建立完整 Upstream -> Local 源码映射表。
- **Governance Rules**：严禁跟随浮动 main 分支；严禁混用非兼容协议代码；仓库内有且仅有一套 Workspace Shell。

### 3.1 唯一上游 Agent 产品（A-21 冻结，Issue #173）

| 项 | 值 |
| --- | --- |
| Product | OpenHands |
| Repository | `https://github.com/OpenHands/OpenHands.git` |
| Tag | `v1.10.0` |
| Commit | `56638693908b8ac83a2fa3bde6eb6c33aae37f4b` (40 位 SHA) |
| License | MIT |
| 采用方式 | source-level vendor（源码级采用，非设计级模仿） |
| 产品机制策略 | preserve-upstream（保留 OpenHands 产品机制） |
| 领域适配策略 | adapter-and-renderer（经 Adapter / Renderer 替换科研领域） |
| 唯一性 | 仓库内唯一 Agent Product Source；禁止混壳 / 第二套 Shell |

冻结元数据位于 `apps/workspace/vendor/openhands/`（`upstream-lock.json`、`source-scope.json`、`vendor-blueprint.json`、`provenance-schema.json`、`LICENSE.upstream`、`NOTICE.md`），由 `scripts/check-agent-upstream-adoption.mjs` 机器门禁强制（G1–G8）。

上游源码升级需经过：锁定 SHA → 许可证审查 → 更新映射 → 上游 Diff 审查 → 运行契约与 UI 回归 → 独立合并。A-22 实际 Vendor 必须重新从官方仓库 checkout `v1.10.0` 并校验 `566386…37f4b`，否则 `BLOCKED`。

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

| 状态类型 | 权威来源 |
| --- | --- |
| Project / Run / Artifact 路由 | Router |
| Server state、缓存与 Mutation | Query Layer (经 Repository Port) |
| Run / Artifact / Evidence 事实 | Domain / Repository |
| 流式交互与输入草稿 | Upstream Agent Runtime |
| Workspace 布局与恢复 | Workspace Controller |
| 组件内部交互状态 (Hover / Active) | Local Component State |
| Share / Export 版本 | Server / ShareSnapshot |

同一事实在前端不得由多个全局 Store 重复持有。

## 6. 路由与数据流

```text
Transport DTO -> Contract Validation -> Domain Mapping -> Repository Port -> Research Adapter -> UI
```

- Fixture 与 HTTP Adapter 返回完全一致的 Domain Model。
- Agent Runtime 仅管理交互与流式展现，不直接创建科研事实或推进服务端状态机。
- 未知类型的 Artifact 明确渲染失败。

## 7. 构建与上游同步

- 上游源码升级需经过：锁定 SHA -> 许可证审查 -> 更新映射 -> 上游 Diff 审查 -> 运行契约与 UI 回归 -> 独立合并。
- 生产构建使用单根 `pnpm-lock.yaml`；大型组件使用代码分割（Code-Splitting）。
