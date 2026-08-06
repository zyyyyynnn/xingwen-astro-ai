# Frontend UI Review Checklist

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | A-17 开源 Agent 前端移植、视觉产品与退役专项 Review |

本文补充 [Review Checklist](REVIEW_CHECKLIST.md)，用于审查科研 Agent 工作台重构。

## 1. 权威与范围

- [ ] DESIGN、WORKSPACE_UX、VISUAL_LANGUAGE、FRONTEND_ARCHITECTURE 与 ADR-031 一致；
- [ ] Issue 只引用权威规范，没有维护第二套冲突 UI；
- [ ] PR 保持一个主要 Issue 和一个 Draft PR；
- [ ] 当前实现状态没有被写成已完成目标；
- [ ] 当前 Head 与截图、测试和 PR 正文一致。

## 2. 上游源码采用

- [ ] 固定 `OpenHands/OpenHands` Release `1.8.0` 与 40 位 Commit SHA；
- [ ] 原版上游已运行并留有本地审查证据；
- [ ] Upstream → Local 文件级移植矩阵完整；
- [ ] 每个采用文件记录原路径、本地路径、修改程度、License 和测试；
- [ ] `enterprise/` 未被复制、依赖或打包；
- [ ] MIT Copyright 与 License 已按适用范围保留；
- [ ] 上游布局、状态、键盘和响应式机制被真实消费；
- [ ] 没有以截图仿制、静态三栏页或新手写 Shell 冒充移植。

## 3. 产品骨架

- [ ] Sidebar 具备 Group、Pin、Recent、Search、Collapse、Selection 和状态；
- [ ] Thread 支持 Running、Streaming、Error、Retry、Cancel 和 Recovery；
- [ ] Composer 支持作用范围、提交、取消、重试、附件和键盘；
- [ ] Panel Host 支持 Context、Artifact、Source、返回、固定和关闭；
- [ ] Command Palette 与焦点导航可用；
- [ ] Loading、Empty、Disconnected、Failed、Archived 等状态不是临时占位；
- [ ] Completed Mission 不展示禁用聊天框；
- [ ] 页面不是 Dashboard、后台表单、静态报告或聊天气泡流。

## 4. 科研 Domain 映射

- [ ] Conversation 正确映射为 Research Mission；
- [ ] Session / Run 正确映射为 Research Run；
- [ ] Agent Action 映射为结构化 Research Event；
- [ ] Workspace Item 映射为 Scientific Artifact；
- [ ] Details Panel 映射为 Evidence、Source、Version 或 Execution Context；
- [ ] Composer 提交结构化 Research Intent；
- [ ] OpenHands 类型没有进入 Domain、Repository、Transport 或持久化 Schema；
- [ ] Coding 专属模块已经删除或不进入产品构建。

## 5. 数据与架构

- [ ] UI 通过 Presentation Adapter 消费 Domain / Repository；
- [ ] Query 调用 Repository，不在页面直连 API；
- [ ] Fixture 与 HTTP 使用同一 ViewModel 和组件；
- [ ] 没有跨包深层导入 Fixture；
- [ ] 没有 `@ts-expect-error` 用于绕过正式包边界；
- [ ] 没有第二套 Router、持久化 Store、DTO 或 API Client；
- [ ] WorkspaceSnapshot 仍是工作区恢复权威；
- [ ] ArtifactVersion、Evidence、SourceSnapshot 和 Revision 语义保持。

## 6. 视觉与产品语言

- [ ] 使用 Cold Paper + Bluegray Semantic Token；
- [ ] 未复制 OpenHands 默认主题、Brand 或 Coding 文案；
- [ ] 默认正式界面为中文；
- [ ] 正式页面不出现 `A-17 CANVAS`、Preview、泛化 Context、Fixture、Adapter、Hash 或内部 ID；
- [ ] Sidebar 与 Context Panel 的视觉权重低于 Primary Workspace；
- [ ] 状态不只靠颜色表达；
- [ ] 没有大面积圆角卡片墙和无意义深色区域；
- [ ] Completed、Running、Review、Artifact 和 Evidence 状态具有明确操作。

## 7. Artifact 与 Evidence

- [ ] 每个核心 Artifact Kind 有类型专属 Renderer；
- [ ] 未支持类型显示明确产品状态，不回落为 Hash Viewer；
- [ ] Statement、Cell、Claim、Relation 可打开 Evidence Context；
- [ ] Evidence 展示支持、冲突、未解决、来源和版本；
- [ ] 完整来源在 Primary Workspace 打开；
- [ ] Version Diff 比较 Protocol、Source、Evidence、Claim、Conflict 和 Limitation；
- [ ] Candidate Dossier 与 Reproducibility 使用真实 Domain 数据。

## 8. 响应式与可访问性

- [ ] 1440×900、1280×800、390×844 无横向滚动；
- [ ] 200% 字体仍可完成核心路径；
- [ ] keyboard-only 可访问 Sidebar、Thread、Composer、Context 和主操作；
- [ ] Focus、ARIA、Dialog、Drawer 和 Sheet 行为正确；
- [ ] Context Detail 在中等宽度下不持续压缩主内容；
- [ ] 移动端不是机械堆叠三栏；
- [ ] 零非预期 `pageerror` 与 `console.error`。

## 9. 退役

- [ ] `@xingwen/research-canvas` 失败原型已删除；
- [ ] `__a17-research-canvas-preview` 已删除；
- [ ] 旧 ResearchShell、A-17 手写 Shell 和旧 CSS 已删除；
- [ ] 无 `v2`、`legacy`、隐藏旧路由或长期双实现；
- [ ] Dockerfile、Foundation、Architecture、Legacy 和 E2E 不再引用退役模块；
- [ ] 未混入与 A-17 无关的启动脚本或环境治理改动。

## 10. 验证与判定

- [ ] Upstream adoption tests 通过；
- [ ] License / Notice 检查通过；
- [ ] `pnpm install --frozen-lockfile` 通过；
- [ ] format、docs、lint、typecheck、unit、build、architecture、legacy 通过；
- [ ] Fixture E2E、真实 HTTP / Compose E2E 通过；
- [ ] 用户已确认视觉截图；
- [ ] PR 正文记录真实完成项、未完成项与 CI；
- [ ] PR 仍为 Draft，直到全部 Gate 通过。

以下任一项存在时 verdict 必须为 `BLOCKED`：无上游矩阵、手写替代 Shell、跨包 Fixture 导入、视觉未确认、核心 E2E 失败、旧路径未退役或文档与实现冲突。
