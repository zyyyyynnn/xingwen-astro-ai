# Frontend Architecture

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 前端运行时、上游源码治理、模块边界、依赖方向与状态所有权 |

本文定义 Brand Site 与 Research Workspace 的工程边界。具体上游产品、版本与源码范围由单独 ADR 冻结。

## 1. 运行时

| 应用 | 技术 | 职责 |
| --- | --- | --- |
| `apps/site` | Astro | Brand Site 与静态入口 |
| `apps/workspace` | React + Vite | Workspace 宿主、路由与运行时组合 |
| `apps/api` | FastAPI | API、Workflow 与持久化 |

精确依赖版本以根 `package.json`、`pnpm-lock.yaml` 与包清单为准，不在本文重复维护。

## 2. Workspace 重建基线

### 保留

- Brand Site；
- Design Token；
- 通用 UI Primitive；
- Domain；
- Contract；
- Repository Port；
- Fixture / HTTP Adapter；
- WorkspaceSnapshot 与通用 Controller；
- 后端、Workflow、Pipeline 与持久化。

### 退役

- 旧 Workspace 产品 UI；
- 项目内自研 Agent Shell；
- Preview Route 与静态产品原型；
- 假 Project、Run、Artifact 与 Evidence；
- 只服务旧 UI 的样式、依赖和测试。

退役后 `apps/workspace` 只保留可构建宿主，直至上游产品冻结。

## 3. 分层

```text
Workspace Host
→ Router / Provider / Runtime Composition

Upstream Agent UI
→ Shell / Navigation / Activity / Workspace / Composer

Research UI
→ Event Renderer / Artifact Renderer / Evidence Inspector / Version Diff

Research Adapter
→ Domain → UI ViewModel
→ UI Intent → Application Command

Existing Core
→ Domain / Repository Port / Fixture / HTTP / Workspace Controller
```

## 4. 上游源码治理

正式采用上游前必须记录：

| 字段 | 要求 |
| --- | --- |
| Repository | 官方仓库 |
| Release | 固定 Tag |
| Commit | 固定完整 SHA |
| License | 兼容且保留适用版权 |
| Source Scope | 采用与排除目录 |
| Mapping | Upstream File → Local File |
| Modification | 本地语义与结构变化 |
| Verification | 上游合同与本地回归 |

该记录是版本化工程证据。

禁止：

- 跟随浮动 `main` 或 latest；
- 未核验许可证即复制源码；
- 复制企业或非兼容目录；
- 参考上游后手写相似实现；
- 失去源码来源映射；
- 同时维护两套 Shell。

## 5. 目录职责

上游冻结前只定义职责，不固定最终目录名。

```text
apps/workspace/src/
├── app/             # Router、Provider、Runtime composition
├── upstream/        # 选定上游源码或薄适配入口
├── adapters/        # Domain 与 UI Runtime 映射
├── events/          # Research Event Renderer
├── artifacts/       # Artifact Renderer
├── evidence/        # Evidence / Source / Version Inspector
└── routes/          # 正式路由
```

上游适合独立 Package 时，由对应 ADR 调整。仓库内始终只保留一个 Workspace Shell。

## 6. 依赖方向

```text
apps/workspace
  → Upstream Agent UI
  → Research Adapter
  → @xingwen/ui
  → @xingwen/design-tokens
  → @xingwen/workspace-core
  → @xingwen/data-access
  → @xingwen/domain

Research Adapter
  → @xingwen/domain
  → Repository Port
  → Upstream public contracts

Artifact / Evidence Renderer
  → @xingwen/domain
  → @xingwen/ui
```

约束：

- Shared Package 不依赖 App；
- Domain 不依赖 React、DOM、HTTP 或上游 UI；
- 页面不直接调用 `fetch`；
- 页面不读取 Transport DTO；
- App 不跨包读取 Fixture 内部文件；
- App 只通过公开 exports 导入；
- 不建立第二套生产 API 类型；
- 不以 `@ts-expect-error` 绕过架构边界。

## 7. 数据边界

```text
Transport DTO
→ Contract Validation
→ Domain Mapping
→ Repository Port
→ Query / Application State
→ Research Adapter
→ UI
```

Fixture 与 HTTP Adapter 返回同一 Domain Model。上游 Runtime 不拥有 ArtifactVersion、Evidence、SourceSnapshot 或 ShareSnapshot。

## 8. 状态所有权

| 状态 | 权威 |
| --- | --- |
| Project / Run / Artifact 路由选择 | Router |
| Server state、分页、缓存、Mutation | Query Layer，经 Repository Port |
| Run、Artifact、Evidence 事实 | Domain / Repository |
| 流式交互与待发送输入 | Upstream Runtime |
| Workspace 布局与恢复 | Workspace Controller 或经 ADR 冻结的唯一布局状态 |
| Hover、Popover、临时筛选 | Local Component State |
| Share / Export 版本 | Server / ShareSnapshot |

同一事实不得由多个 Store 重复持有。

## 9. Agent Runtime

```text
Run Event
→ Research Event Normalizer
→ Upstream Runtime Event
→ Research Event Renderer
```

```text
Upstream Composer
→ Research Intent
→ Application Service / Repository Mutation
```

Runtime 只管理交互生命周期，不创建科研事实或推进服务端状态机。

## 10. Artifact 与 Evidence

Artifact Renderer 只消费 Domain ViewModel。

```text
Artifact Kind
→ Renderer
→ Evidence Anchor
→ Source / Version Inspector
```

未知类型明确失败。

Evidence Inspector 只展示可审查内容：

- target；
- Evidence status；
- SourceSnapshot；
- locator；
- quote / value；
- extraction method；
- version；
- related objects。

## 11. 路由

| 路径 | 职责 |
| --- | --- |
| `/workspace` | 私有 Research Workspace |
| `/share/$shareToken` | 冻结匿名 Share |
| `/` | Workspace App 入口或重定向 |
| 其他 | Not Found |

开发 Preview Route 不进入生产 Route Tree。

## 12. 上游同步

上游升级必须：

1. 固定新 Tag 与 SHA；
2. 审查 Release Notes 与 License；
3. 更新源码映射；
4. 生成 Upstream Diff；
5. 运行上游合同测试；
6. 运行 Adapter、E2E、A11y 与视觉回归；
7. 通过独立变更合并。

## 13. 构建与质量

- 单一根 `pnpm-lock.yaml`；
- 依赖在引入时真实消费；
- 大型 Renderer 与非首屏能力代码分割；
- Docker / Compose 不引用已删除 Package；
- 架构检查验证依赖方向、公开入口、单一 Shell 与禁止深层导入；
- 具体测试方法见 [Test Strategy](../engineering/TEST_STRATEGY.md)；
- 完成标准见 [Acceptance](../product/ACCEPTANCE.md)。
