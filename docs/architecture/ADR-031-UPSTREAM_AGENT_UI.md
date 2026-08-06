# ADR-031：采用成熟开源 Agent 前端源码作为工作台基线

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 科研 Agent 工作台前端骨架、上游采用与替代关系 |

## Context

现有自研 `ResearchShell`、A-17 三栏 Shell 和 `@xingwen/research-canvas` 静态原型均未达到可用产品标准。连续实现出现相同问题：参考成熟产品后重新手写 Sidebar、Main Stage、Context Rail 和 Composer，最终得到缺少成熟 Agent 运行反馈、面板行为、键盘合同和产品一致性的页面。

仓库已经具备 Domain、Repository、WorkspaceController、Artifact、Evidence 与 Version 边界，缺少的是成熟、经过真实使用验证的 Agent 前端产品骨架。

## Decision

采用以下上游作为工作台主基线：

```text
Repository: OpenHands/OpenHands
Release: 1.8.0
Source roots: frontend/、openhands-ui/
Excluded: enterprise/
License: MIT for adopted non-enterprise source
```

实施采用源码移植和定向改造：

1. 运行并审查原版上游；
2. 固定 Release 对应的 40 位 Commit SHA；
3. 建立 Upstream → Local 文件级移植矩阵；
4. 移植 App Shell、Sidebar、Thread、Composer、Panel Host、状态反馈、键盘和响应式机制；
5. 删除 Terminal、VS Code、Git Diff、Sandbox 和其他 Coding 专属模块；
6. 通过单一 Presentation Adapter 将 Xingwen Domain 投影为上游 UI ViewModel；
7. 新增科研 Event Renderer、Artifact Renderer、Evidence Lens、Source Review、Scientific Version Diff、Candidate Dossier 与 Reproducibility；
8. 使用 Cold Paper + Bluegray Token 完成品牌换肤；
9. 最终一次性切换正式 `/workspace` 并删除失败原型和旧 Shell。

## Rejected Alternatives

- 根据 OpenHands 截图手写相似界面；
- 只引入 `@assistant-ui/react` 后自行搭建整个 Shell；
- 继续修补 `@xingwen/research-canvas` 静态原型；
- 完整 Fork OpenHands 并采用其 Domain、API 或 Agent Runtime 作为星文智析事实源；
- 移植 `enterprise/` 源码；
- 同时维护旧 Shell 和新 Shell 的长期双路径。

## Domain Boundary

```text
Xingwen Domain / Repository
→ Research Presentation Adapter
→ OpenHands-derived UI
```

OpenHands 类型不得进入 Domain、Repository、Transport Contract 或持久化 Schema。TanStack Router、TanStack Query 和 WorkspaceController 的既有权威保持不变。

## License and Provenance

每个采用文件必须记录：

- 上游 Repository、Release、Commit 与路径；
- 本地路径；
- unchanged / adapted / rewritten / excluded；
- 原始版权与 MIT License；
- 修改摘要；
- 对应测试。

`enterprise/` 一律不进入移植清单。

## Consequences

- 工作台不再自研第二套通用 Agent Shell；
- 产品开发从“设计一个 Agent 界面”转为“替换成熟 Agent 产品中的 Coding Domain”；
- UI 代码必须可追溯到上游或明确标记为 Xingwen 科研扩展；
- 上游更新不自动跟随，必须通过独立审查和固定版本升级；
- 当前分支中 `26eca8671a8822e82bfd867a2e67a613aa116472` 引入的失败原型通过正常前向提交移除。

## Implementation Gate

在以下证据齐全前不得开始正式 UI 移植：

- 原版上游运行截图；
- 固定 Tag 与 Commit；
- 文件级移植矩阵；
- License / Notice 记录；
- 用户确认采用的 Sidebar、Thread、Panel 和 Composer 骨架；
- DESIGN、WORKSPACE_UX、VISUAL_LANGUAGE 和 FRONTEND_ARCHITECTURE 一致。
