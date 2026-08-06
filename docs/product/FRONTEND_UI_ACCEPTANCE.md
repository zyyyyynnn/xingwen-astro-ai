# Frontend UI Acceptance

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | A-17 前端 UI 重构的阶段退出标准与视觉产品门禁 |

本文回答“科研 Agent 工作台前端何时可以进入下一 Gate、何时可以宣布完成”。通用里程碑仍由 [Acceptance](ACCEPTANCE.md) 管理。

## 1. Gate 0：上游采用准备

必须同时提供：

- OpenHands/OpenHands `1.8.0` 原版前端可运行证据；
- Release 对应的 40 位 Commit SHA；
- Sidebar、Thread、Composer、Panel Host、Command Palette、Loading / Error / Retry 的原版截图；
- Upstream → Local 文件级移植矩阵；
- MIT License 与版权处理记录；
- `enterprise/` 未进入采用范围的证明；
- 用户确认采用的原版页面和交互骨架。

任一项缺失不得开始正式 UI 移植。

## 2. Gate 1：成熟 Agent Shell

必须证明实际移植并消费上游源码，而不是手写相似页面：

- Sidebar 保留成熟分组、Pin、Recent、搜索、折叠、选中和状态行为；
- Thread 支持 Agent 运行事件、长任务状态、错误、恢复和滚动；
- Composer 支持输入、提交、取消、重试、附件和键盘；
- Panel Host 支持 Context / Artifact / Source 面板、关闭、返回和响应式；
- Command Palette 与焦点导航可用；
- 上游源码、修改点和本地测试可追溯。

Gate 1 不要求全部科研 Feature，但必须看起来和操作起来是成熟 Agent 产品，而不是静态三栏页面。

## 3. Gate 2：科研 Domain 替换

必须完成：

- Conversation → Research Mission；
- Session / Run → Research Run；
- Message / Action → Research Thread Event；
- File / Workspace Item → Scientific Artifact；
- Details Panel → Evidence / Source / Version Context；
- Composer → Structured Research Intent；
- Coding 专属 Terminal、VS Code、Git Diff、Sandbox 和设置已移除。

默认产品层不得出现 Coding Agent 文案、OpenHands Brand、Fixture、Adapter、Hash 或内部 ID。

## 4. Gate 3：竞赛垂直闭环

必须打通：

```text
选择 Mission
→ 查看 Running Thread 或 Completion Summary
→ 打开 Artifact
→ 点击 Statement / Cell / Claim
→ 打开 Evidence Context
→ 查看来源定位
→ 请求修订或继续研究
→ 生成新 ArtifactVersion
→ 查看 Scientific Version Diff
```

Human Checkpoint、Conflict、Unresolved 和 Source Version Conflict 必须具有明确状态和操作。

## 5. Gate 4：Artifact 与领域高光

必须具备真实 Renderer：

- Dataset；
- Field Dictionary；
- Source Collection；
- Paper Collection；
- Literature Summary；
- Literature Comparison；
- Literature Claims；
- Literature Relations；
- Reasoning Trace；
- Candidate Dossier；
- Evidence Graph（真实 Contract 可用后）。

Candidate Dossier、Evidence Conflict、Scientific Version Diff 和 Reproducibility 构成国赛展示高光。

## 6. Gate 5：完整迁移与退役

必须证明：

- `/workspace` 只进入新工作台；
- Fixture 与 HTTP 使用同一 UI 与 Presentation Adapter；
- WorkspaceSnapshot 可保存、恢复并处理 revision conflict；
- 旧 ResearchShell、A-17 手写三栏 Shell、`@xingwen/research-canvas` 失败原型、Preview Route 和旧 CSS 已退役；
- 没有长期双路径、`v2`、`legacy` 或隐藏旧入口；
- Dockerfile、Foundation、E2E 和文档不存在退役模块残余。

## 7. 视觉产品标准

必须提交并由用户确认：

- 1440×900 Running Mission；
- 1440×900 Artifact Review；
- 1440×900 Evidence Detail；
- 1440×900 Completed Mission；
- 1280×800；
- 390×844；
- 200% 字体；
- keyboard-only。

五秒识别检查：

1. 当前研究问题是什么；
2. Run 处于什么状态；
3. Agent 正在做什么；
4. 当前最重要 Artifact 是什么；
5. 用户现在可以做什么。

## 8. Agent 产品最低标准

- 至少存在一个真实可用的 Running Thread，而不是静态报告页；
- Agent 状态、取消、重试、错误与恢复可见；
- Composer 在适用状态可真实提交 Research Intent；
- Completed Mission 显示可继续研究的动作，不显示禁用聊天框；
- Context Panel 由当前选中对象驱动；
- Artifact 是主工作内容，不是按钮列表或 Hash Viewer；
- Sidebar、Thread、Panel、Composer 的交互来自上游成熟骨架；
- 视觉使用 Xingwen Token，不复制 OpenHands 默认主题。

## 9. 一票否决

出现以下任一情况，前端 Gate 直接失败：

- 根据截图或产品概念手写新的通用 Agent Shell；
- 无 Upstream → Local 文件映射；
- 只安装依赖但没有消费成熟源码；
- 使用静态 Fixture 假数据冒充 Agent 运行；
- `@ts-expect-error`、跨包深层导入或页面直读 Fixture 绕过架构；
- 正式截图出现 `A-17 CANVAS`、Preview Route、泛化 Context、内部 ID 或调试文案；
- 整页退化为 Dashboard、后台表单、静态文章页或禁用 Composer；
- 实现者自行宣布视觉 PASS 而没有用户确认；
- 必要 CI、E2E、Compose 或可访问性验证未通过。
