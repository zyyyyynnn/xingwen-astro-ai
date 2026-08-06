# Frontend Architecture

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 前端运行时、上游源码移植、目录、依赖方向、构建与质量门禁 |

本文定义前端工程方案。产品设计见 [DESIGN.md](../../DESIGN.md)，交互见 [Workspace UX](../design/WORKSPACE_UX.md)，视觉见 [Visual Language](../design/VISUAL_LANGUAGE.md)。

## 1. 运行时

- `apps/site`：Astro 静态 Brand Site；
- `apps/workspace`：React、Vite、TanStack Router 的科研 Agent 工作台；
- `packages/domain`：纯 TypeScript Domain；
- `packages/data-access`：Repository Port、Fixture / HTTP Adapter；
- `packages/workspace-core`：WorkspaceSnapshot 与 Controller；
- `packages/ui`：星文智析 UI Primitive 与视觉 Token 适配；
- 根 pnpm workspace、单一 `pnpm-lock.yaml` 和现有质量门禁继续有效。

## 2. 上游源码基线

工作台前端骨架固定采用：

```text
Repository: OpenHands/OpenHands
Release: 1.8.0
Allowed source roots: frontend/、openhands-ui/
Excluded source root: enterprise/
License: MIT for adopted non-enterprise source
```

实施开始时必须记录 Release 对应的 40 位 Commit SHA。Tag、Commit、上游路径、版权、许可证、本地路径和修改摘要进入一个版本化移植清单。

不得使用移动的 `main` 作为未固定基线。

## 3. 移植方式

本项目采用源码移植，不采用以下方式：

- 根据截图手写相似 Shell；
- 只安装 OpenHands 或 assistant-ui 依赖但不消费成熟源码；
- 新建静态三栏 Demo 冒充 Agent 骨架；
- 复制 `enterprise/` 源码；
- Fork 整个 OpenHands 后让其 Domain、API 和运行时成为星文智析事实源。

执行顺序：

```text
运行原版上游
→ 冻结 Tag / SHA
→ 建立文件级移植矩阵
→ 移入最小成熟骨架
→ 删除 Coding 专属模块
→ 增加 Xingwen Presentation Adapter
→ 接入 Artifact / Evidence Renderer
→ 切换正式路由
→ 删除失败原型与旧 Shell
```

## 4. 目标目录

最终目录可按上游实际结构调整，但职责必须保持：

```text
apps/workspace/src/
├── app/                         # Router、Provider、Runtime wiring
├── upstream/                    # 经许可移植的 OpenHands UI 骨架
│   ├── shell/
│   ├── sidebar/
│   ├── thread/
│   ├── composer/
│   ├── panels/
│   └── primitives/
├── research/
│   ├── presentation/            # Domain → UI ViewModel
│   ├── events/                  # Research Event Renderer
│   ├── artifacts/               # Artifact Renderer Registry
│   ├── evidence/                # Evidence / Source Context
│   └── intents/                 # Structured Research Intent
├── queries/                     # TanStack Query → Repository Port
└── pages/                       # Route composition only
```

已提交的手写 `@xingwen/research-canvas` 静态原型不是目标架构，后续正常提交中移除，不保留 `v2`、`legacy` 或双 Shell。

## 5. Upstream → Local 移植矩阵

编码前必须形成文件级矩阵，至少包含：

| 字段 | 含义 |
| --- | --- |
| upstream_repository | `OpenHands/OpenHands` |
| upstream_release | `1.8.0` |
| upstream_commit | 40 位 SHA |
| upstream_path | 原始文件路径 |
| local_path | 本地文件路径 |
| adoption | unchanged / adapted / rewritten / excluded |
| domain_replacement | Coding 对象如何替换为 Research 对象 |
| license | MIT 与版权处理 |
| tests | 对应本地测试 |

矩阵是实施证据，不是新的业务规范。没有矩阵不得开始正式 UI 移植。

## 6. 依赖方向

```text
apps/workspace
  → upstream UI shell
  → research presentation adapter
  → @xingwen/ui
  → @xingwen/workspace-core
  → @xingwen/data-access

research presentation adapter
  → @xingwen/domain
  → Repository ViewModel

@xingwen/workspace-core
  → @xingwen/domain

@xingwen/data-access
  → @xingwen/domain
  → @xingwen/contracts
```

约束：

- 上游 UI 骨架不直接调用 Xingwen API；
- 页面和上游组件通过 Query / Adapter 消费 Domain ViewModel；
- Shared Package 不依赖 App；
- Domain 不依赖 React、HTTP、DOM 或 OpenHands 类型；
- 不建立第二套 Router、持久化 Store、Transport DTO 或 Repository；
- Fixture 与 HTTP 使用同一 Presentation Adapter 与同一 UI；
- 禁止跨包深层导入 Fixture；
- 禁止用 `@ts-expect-error` 绕过正式包边界。

## 7. Presentation Adapter

唯一转换边界：

```text
Xingwen Domain / Repository
→ Research Presentation Adapter
→ OpenHands-derived UI Components
```

Adapter 负责：

- Project / Run → Mission / Session Sidebar ViewModel；
- Run Event → Research Thread Event；
- ArtifactVersion → Workspace Item / Artifact View；
- Evidence / SourceSnapshot → Context Panel ViewModel；
- Revision / Supersedes → Scientific Version Diff；
- Research Intent → Application Command。

上游 UI 类型不得反向污染 Domain、Repository 或 API Contract。

## 8. 组件采用边界

保留并改造：

- App Shell；
- Sidebar；
- Thread；
- Composer；
- Workspace / Details Panel Host；
- Command Palette；
- Loading / Error / Retry / Disconnected；
- Keyboard、Focus、Resize 和 Responsive。

删除：

- Terminal、VS Code、Git Diff；
- Repository 文件系统；
- Sandbox、Coding Agent Settings；
- Coding 专属 Tool Renderer；
- OpenHands Brand、Telemetry 和 enterprise 集成。

新增：

- Research Event Renderer；
- Artifact Renderer Registry；
- Evidence Lens；
- Source Review；
- Scientific Version Diff；
- Candidate Dossier；
- Reproducibility Context。

## 9. 其他可复用轮子

- TanStack Query：Server State；
- TanStack Router：URL 与选中对象；
- Radix：Dialog、Popover、Menu、Tabs、Tooltip、ScrollArea、ARIA；
- cmdk：Command Palette；
- react-resizable-panels：在上游骨架缺少对应能力时补充 Panel Resize；
- TanStack Table / Virtual：Dataset Artifact；
- XYFlow：Evidence Graph，只有真实 Contract 可用后接入。

assistant-ui 不在第一阶段接管 Shell 或 Runtime。只有上游 Composer / Thread 无法满足已冻结 Research Intent 合同时，经过 ADR 补充后才可引入。

## 10. 状态权威

```text
TanStack Router → Project / Mission / Artifact / Version URL
TanStack Query → Server State
WorkspaceController → WorkspaceSnapshot、Panel 与 Selection
Upstream UI local state → hover、popover、临时展开和输入草稿
Domain / Repository → Mission、Run、Artifact、Evidence、Version 事实
```

上游组件不得创建第二套科研事实源。

## 11. 测试门禁

必须新增：

- 上游移植矩阵完整性检查；
- 被采用源码的 License / Notice 检查；
- 禁止手写替代 Shell 的 retirement 检查；
- Presentation Adapter 单元测试；
- Fixture / HTTP UI parity；
- Sidebar、Thread、Composer、Context Panel 的键盘和响应式测试；
- Artifact / Evidence / Version 核心 E2E；
- 1440×900、1280×800、390×844 和 200% 字体视觉 Gate。

## 12. 当前迁移处理

当前分支中 `26eca8671a8822e82bfd867a2e67a613aa116472` 引入的静态预览、手写 `@xingwen/research-canvas`、跨包 Fixture 深层导入与 Preview Route 均视为失败原型。后续通过正常前向提交移除，不改写 Git 历史。
