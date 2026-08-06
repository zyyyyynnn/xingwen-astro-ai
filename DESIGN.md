# Product Design

| 元数据    | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 产品设计原则、体验域关系、开源前端基线与设计不变量 |

本文是星文智析前端产品设计的最高层权威。页面结构与交互细节见 [Workspace UX](docs/design/WORKSPACE_UX.md)，视觉换肤见 [Visual Language](docs/design/VISUAL_LANGUAGE.md)，工程落点见 [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md)。

## 1. 产品命题

星文智析不是通用聊天 Agent、Coding Agent、后台管理系统或静态科研报告阅读器。产品围绕一条可审查科研链组织：

```text
Research Mission
→ Research Run
→ Agent Activity
→ Scientific Artifact
→ Evidence / SourceSnapshot
→ Review / Revision
→ Export / Share
```

产品价值：

> Agent 产生的每一个科研结论都可以被追溯、质疑、修订和复现。

## 2. 开源前端基线决策

科研工作台采用成熟开源 Agent 产品的真实前端源码作为基线，不再根据截图或概念手写相似 Shell。

主基线固定为：

```text
Repository: OpenHands/OpenHands
Release: 1.8.0
Source scope: frontend/ 与 openhands-ui/ 中非 enterprise/ 的适用前端源码
License: MIT；enterprise/ 不进入移植范围
```

采用原则：

1. 先运行原版上游产品，再建立逐文件移植矩阵；
2. 保留成熟的 App Shell、Sidebar、Thread、Composer、Panel Host、状态反馈、键盘和响应式机制；
3. 将 Coding / Conversation Domain 替换为星文智析 Mission、Run、Artifact、Evidence 与 Version Domain；
4. 删除 Terminal、VS Code、Git Diff、Sandbox 和其他 Coding 专属模块；
5. 科研 Artifact Renderer、Evidence Lens、Scientific Version Diff 和 Candidate Dossier 由星文智析实现；
6. 禁止以新建手写 Shell、静态三栏 Demo 或“外观类似 OpenHands”的页面替代真实源码移植。

OpenHands 是前端交互与运行框架基线，不决定星文智析的科研语义、品牌视觉或数据模型。

## 3. 产品层级

```text
Mission 组织研究目标
Run 组织 Agent 执行
Thread / Storyline 呈现过程与人机协作
Artifact 承载科研结果
Evidence 建立可信度
Version 记录科研变化
Context Panel 支撑核查
Composer 驱动下一轮研究
```

Agent Thread 是工作过程的一部分，不是整个产品的唯一主内容。Artifact、Evidence 和当前用户任务决定主工作区焦点。

## 4. 体验域

| 体验域 | 核心职责 |
| --- | --- |
| Brand Site | 建立品牌识别并进入工作台；首页采用单 CTA |
| Guided Tour | 以确定性主案例解释 Mission、Run、Artifact 与 Evidence |
| Research Workspace | 使用成熟 Agent Shell 承载任务执行、科研产物审查、证据核查、修订、导出和分享 |

三个体验域共享 Domain、Token 和 Evidence 规则，不共享无必要的页面状态。

## 5. 工作台设计不变量

- 默认界面在五秒内可识别当前研究问题、Run 状态、Agent 当前动作、最重要 Artifact 与下一步操作；
- Sidebar 管理 Mission / Run，不表现为普通聊天历史；
- Agent Thread / Storyline 使用结构化科研事件，不展示模型私有思维；
- 主工作区根据当前任务在 Thread、Artifact、Source、Compare 和 Completion 之间切换；
- 右侧 Context Panel 由当前选中的 Statement、Evidence、Artifact、Version 或 Checkpoint 驱动；
- Composer 提交结构化 Research Intent，而不是无作用范围的自由聊天文本；
- Completed Mission 仍可继续研究、请求修订或派生新 Mission，不展示不可用输入框；
- 默认产品界面不暴露 Fixture、Adapter、Execution Mode、Hash 或内部 ID；
- Fixture 与 HTTP 通过同一 Repository Port 和同一产品组件；
- WorkspaceSnapshot 保持工作区恢复状态的唯一持久权威。

## 6. 视觉原则

- 工作台沿用 Cold Paper + Bluegray 浅色体系；
- 不复制 OpenHands 默认主题或 Coding Agent 皮肤；
- 上游布局和交互结构可以保留，颜色、字体、状态与科研内容必须使用星文智析规范；
- 主工作区优先阅读和操作，Sidebar 与 Context Panel 服从主任务；
- 不以大面积卡片墙、静态 Dashboard、后台表单或禁用控件充当成熟 Agent 产品。

## 7. 权威顺序与实施门禁

发生冲突时按以下顺序裁决：

```text
DESIGN.md
→ docs/design/WORKSPACE_UX.md
→ docs/design/VISUAL_LANGUAGE.md
→ docs/architecture/FRONTEND_ARCHITECTURE.md
→ docs/product/ACCEPTANCE.md
→ docs/quality/REVIEW_CHECKLIST.md
→ Issue / PR 执行状态
```

开始工作台 UI 编码前必须完成：

1. 固定上游 Tag 与 Commit；
2. 运行原版上游前端；
3. 建立 Upstream → Local 文件级移植矩阵；
4. 完成许可证和版权记录；
5. 明确保留、删除、替换和新增模块；
6. 由用户确认采用的原版骨架与核心页面；
7. 确认权威文档与 Issue 一致。

## 8. 当前实施状态

`Accepted` 表示设计决策有效，不表示当前 PR 中的工作台原型通过产品验收。具体完成状态以 Issue #167、PR #168、运行截图和 CI 为准。
