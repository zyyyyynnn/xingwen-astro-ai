# Research Workspace UX

| 元数据    | 值                                     |
| --------- | -------------------------------------- |
| Authority | Workspace 信息架构、页面状态与核心交互 |

本文定义 Research Workspace 的唯一产品行为。XingWen Research Workspace 是
Web 应用，正式主题为 Light。`/workspace` 是唯一私有工作台入口；
`/share/$shareToken` 是固定版本的只读安全边界。Workspace 只有在真实 ResearchRun
服务可验证时才允许显示运行结果；无运行服务时必须显示明确的未连接/不可执行状态，
禁止注入假事件。自动化覆盖与门禁见
[Test Strategy](../engineering/TEST_STRATEGY.md)。

当前 full-stack packaging 可以跨 Frontend、API、Workflow 与测试收敛一个完整实现，
但不会转移模块所有权。Research Workspace UX 仍由本文件定义；科学执行、Reference
Integration、Scientific Skill、Executor、Worker、Attempt、Artifact scientific
presentation 与 Live closure 由对应科学执行 Authority 定义。当前已验收行为优先于
历史测试、旧任务文案与旧实现；冲突内容应删除，不建立 compatibility layer。

## 1. 目标

Workspace 支持用户在同一研究上下文中完成：

```text
提出研究意图
→ 助手正常解释并澄清
→ 审查并确认研究协议
→ 观察研究执行
→ 审查科研结果
→ 核验证据与来源
→ 作出人类决策
→ 修订、导出或分享
```

## 2. Workspace 布局

宽屏三列结构：

```text
左侧项目导航 | Research Thread | 右侧研究栏
```

Research Thread 是最重要的研究叙事入口。

右侧研究栏只承担：

- 研究概览；
- 研究结果索引。

右侧栏不承担 Artifact detail。结果点击直接进入 Fullscreen；Fullscreen 是正式结果阅读
入口，其打开/关闭不能改变用户的右侧研究栏可见性偏好。

新 Project 没有任何研究内容时：

- 右栏隐藏；
- 主区保留极简提示“开始你的研究”；
- Composer 常驻。

主区不出现“新建研究”按钮。“新建研究”的唯一入口在左侧导航。

## 3. Research Navigation

导航项只显示：

```text
[status icon] 项目标题
```

不显示 Run 状态文字、阶段、最近结果、更新时间或结果数量。

必须支持：

- 当前项；
- Pinned 分组在前，Recent 分组在后；
- Pin / Unpin 通过 context menu 控制；
- 展开态提供项目搜索（本地 UI filter）；
- Collapse；
- 键盘导航；
- 有限 resize。

status icon 必须来自真实 server/project projection，aria-label 表达
running / waiting / error / idle，但不在 UI 旁显示文字标签。

导航不显示原始内部 ID，不使用大面积卡片替代列表结构。Command Menu 保持全局
command/search，但不得创建第二个“新建研究”入口。

## 4. Research Thread

Thread 不是运行日志。它是：

```text
用户消息
+ AI 正常回复
+ 协议
+ 澄清
+ 必要公开分析
+ 工具活动
+ 阶段解释
+ 研究结果
+ 修订/人工决定
```

用户可见 AI 信息严格区分：

1. **Assistant Message**：自然语言科研叙事，是视觉主线；
2. **Public Analysis**：可公开、简短、可展开的步骤分析，不是 private chain-of-thought；
3. **Tool Activity**：从真实 RunEvent 投影的次级执行记录；
4. **ReasoningTrace**：Evidence-bound 的正式 Scientific Artifact，不是普通聊天思考；
5. **Provider private reasoning**：永不保存、展示或导出。

AI 正常消息必须贯穿研究全程。至少在以下语义节点有正常 Assistant Message：

- 理解用户目标；
- 协议形成；
- 协议确认/启动；
- 进入主要研究阶段；
- 得到重要中间发现；
- 遇到需要用户理解的问题；
- 进入结果整理；
- 正式结果发布；
- 研究完成。

不得按固定时间或每个 Tool call 机械发消息。Reasoning / Tool Activity 是次级
信息，不得代替 Assistant Message。

### 4.1 Unified Stream

所有持久事实按服务端权威顺序显示。不得：

- 先 messages 后 tools 再 artifacts 地按类型批量拼接；
- 用浏览器 `new Date()` / `Date.now()` 为历史事实制造顺序；
- 按类型批量 append 后假装 chronological。

唯一允许的瞬时尾项是当前尚未被服务端确认的用户发送消息；它不得改变历史 chronology。

用户向上阅读时：

- 新事件不得抢滚动；
- 底部显示“新进展”提示；
- 用户本来就在底部时才自动跟随。

用户自己发送消息后滚到底部。

### 4.2 视觉层级

Assistant Message 是主叙事；Reasoning / Tool Activity 是次级信息：

```text
AI message
  分析
  工具
  工具
AI message
  工具
```

不得把所有内容放同级 Card。

## 5. Contract

首次研究：

```text
用户消息 → AI 正常解释 → Protocol Draft → AI 下一步提示
```

协议草案不能孤立出现。用户只点一次“确认协议并开始研究”。内部流程：

```text
Draft → Confirm Contract → 使用 Confirm 返回的正式 Contract ID → Create Run
```

如果 Confirm 成功但 Create Run 失败：

- Contract 保持 confirmed；
- 不回滚 Draft；
- 显示“重新开始研究”；
- 不重复确认或创建 Contract。

Confirmed Contract 不允许原地修改。修改请求走新 Draft / Revision，用户确认后
产生新执行。Chat 是主要修改入口；Review Dialog 是查看/有限高层结构化编辑入口。

## 6. Clarification

只在无法正确继续时阻塞询问。非关键默认：

- AI 可采用合理默认；
- 如果会影响解释，公开说明。

Clarification 必须由正式共享组件显示：

```text
AI Message + 问题 + 可选项 + “其他/自行说明”
```

回答后：

- 历史问题保留；
- 显示已回答内容；
- 不再可修改过去答案。

## 7. Research Composer

空 Workspace 与已存在 Project 使用同一个 Composer application seam；两者只在首次提交是否
需要先建立 Project context 上有差异，不存在第二套发送/controller 产品逻辑。

Run 执行期间 Composer 始终可用。只在当前发送请求 pending 时防止重复提交。不建立前端
消息队列。

支持：

- Enter 提交；
- Shift+Enter 换行；
- IME-safe 提交；
- 自适应高度，约 6–8 行后内部滚动；
- 文本 paste；
- 文件拖放/选择；
- PDF/CSV/FITS/JSON/图片等通过正式 ResearchInput 摄取，不作为临时聊天 blob。

附件在 active Run 期间上传只进入 Project-owned ResearchInput；不得自动绑定或改变已冻结 Run。
把新资料纳入正式研究必须走 Revision request → Revision Plan → 用户确认 → derived Run。

## 8. Cancel / Retry / Checkpoint

Cancel：

- 轻量 AlertDialog；
- 已发布结果保留；
- 未完成执行停止；
- late publish 被拒绝；
- Run 进入 cancelled。

自动 retry 只处理受治理的瞬时失败，次数耗尽后用户可见。人工 Retry 从最小
合法失败边界重新执行，保留历史 Attempt，不原地覆盖失败尝试。

Human Checkpoint：Run = `waiting_for_input`，同一个 Run 等待，用户回答后
resume，不建立第二套 review runtime。

## 9. Revision

用户运行中提出改变 Contract 的要求：

- 不静默修改当前 Run；
- AI 说明会影响当前研究；
- 创建 Revision Plan；
- 用户确认后才产生 revision Run。

## 10. Result

Thread 中结果作为研究叙事的一部分出现。

右栏只做索引：

- 最近正式结果优先；
- 一个逻辑结果一个列表项；
- 点击直接 Fullscreen。

结果详情只有 Fullscreen 一个产品入口；右栏不得承载结果详情预览。

## 11. 全屏科研结果

Fullscreen 是真正的结果工作区，不是放大的 Dialog。

论文结果宽屏默认：

```text
研究报告 | 论文全文 PDF
```

论文 Report 与 original PDF 属于同一个 Fullscreen research workspace。两侧同屏、独立滚动、
正式可调整面板；点击报告 Evidence 时 PDF 定位到真实 locator。1024×768 Web 视口使用
「研究报告 / 论文原文」单内容区切换，但两个 pane 保持 mounted（或等价完整保存 reading state），
保留报告滚动、PDF 页码、缩放、搜索与滚动位置。

## 12. 右侧研究栏（Inspector）

宽屏：

- 可展开/关闭；
- 宽度可拖拽；
- 记住用户上一次 open/closed 和宽度；
- 历史 Project 第一次进入默认 docked；新空 Project 默认 hidden；
- 新结果产生不自动抢焦点；
- 不自动切换到“研究结果”。

1024×768 Web 视口：右栏改为右侧 Sheet，不压缩主 Thread 到不可读。Docked 与 Sheet 必须
复用同一个 Inspector content，不维护第二套内容状态。

所有宽度适配基于 CSS viewport / container layout，不做设备检测或 UA 判断。

## 13. UI 文案

默认前端禁止展示：

```text
artifactVersionId / runId / attemptId / producerExecutionId
sourceSnapshotId / sourceId / sourceRecordId
hash / parameters hash / provider request id
内部枚举 / 内部模型配置 / 内部 Adapter 名称
```

除非用户主动进入真正需要的高级信息，而且该信息确实帮助判断结果可信度。
不要通过内部参数制造“专业感”。

## 14. 版本语言

用户界面严禁出现“v+数字”式版本号（如 v 后接 1、2、3）或“Version 数字”式
文案。结果历史使用：

```text
当前结果
历史结果
发布时间
修订来源
基于此结果修改
```

例外只允许外部不可改正式名称，例如 OpenHands 外部 release tag、第三方
pipeline 正式版本、模型正式名称、Schema/协议真正机器版本。

## 15. 响应式与可访问性

- 完整键盘路径；
- 可见 Focus Ring；
- Skip Link；
- 正确 Heading 层级；
- 状态不只靠颜色；
- Reduced Motion；
- Overlay 关闭后恢复焦点；
- Resize 提供键盘替代。

正式视觉验收只覆盖 Light Web：1440×900、1280×800、1024×768。Phone、Dark 与额外字体缩放场景不是本轮产品验收路径；Reduced Motion、键盘、Focus 与 Screen Reader 仍是正式要求。

## 16. 产品语言

界面结构与操作以中文为主。标准、论文标题与 DOI 可保留英文。

默认视图禁止出现：

- Preview、阶段编号或内部项目代号；
- Adapter、Fixture、Hash、Execution Mode；
- 失效功能提示占据主操作区；
- 假 Project、假 Run、假 Evidence；
- 原始模型思维过程。

## 17. 验收边界

产品视觉由用户确认。自动化测试、构建和截图差异不能单独判定 Workspace 可用。
目标是成熟、克制、连续、科研阅读优先的界面，而不是卡片堆叠的 Agent Demo。
