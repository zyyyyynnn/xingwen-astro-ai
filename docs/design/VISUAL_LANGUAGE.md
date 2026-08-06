# Visual Language

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 品牌、Token、字体、排版和开源 Agent 骨架换肤规则 |

本文定义星文智析视觉系统。工作台使用成熟开源 Agent 前端的布局与交互机制，但不得复制其品牌皮肤、Coding Agent 视觉或默认主题。

## 1. 视觉命题

> 冷灰观测纸面、低饱和 Bluegray、编辑式科研排版、清晰的证据与状态层级。

星文智析不是深色太空大屏、代码 IDE、聊天气泡产品或后台管理系统。

## 2. 视觉基线

- 页面基底：Cold Paper；
- 主要文字与结构：Bluegray；
- 状态色：成功、风险、失败、信息使用既有 Semantic Token；
- Raw / Semantic Color Token 数值保持不变；
- 业务组件只消费 Semantic Token；
- 工作台默认使用浅色主题；
- 深色只用于小面积代码、原始输出或必要的高对比技术内容。

## 3. 上游骨架换肤

OpenHands 源码移植后执行以下换肤：

| 上游视觉对象 | 星文智析处理 |
| --- | --- |
| App background | 使用 `--color-canvas` |
| Panel / Sidebar | 使用 Paper / Surface 层级 |
| Primary text | 使用 `--color-ink-primary` |
| Secondary text | 使用 `--color-ink-secondary` |
| Border / Divider | 使用 `--color-border` 与 `--color-border-strong` |
| Primary action | 使用 Bluegray 品牌色，小面积出现 |
| Agent / Run status | 使用 Semantic Status + 明确文字 |
| Code / raw event | 局部技术表面，不扩展为整页深色主题 |

保留上游布局、滚动、焦点、面板和状态机制；替换颜色、字体、间距、圆角、阴影、图标、品牌和科研语义。

## 4. 页面层级

视觉优先级固定为：

```text
Current Research Goal
→ Current Agent / Run State
→ Primary Artifact or Thread
→ Evidence / Review Action
→ Secondary Metadata
```

Sidebar 和 Context Panel 的视觉权重低于 Primary Workspace。主区域不使用大量悬浮卡片；优先使用分隔线、段落、列表、结构化事件和 Artifact Canvas。

## 5. 字体

| 角色 | 用途 |
| --- | --- |
| Brand Serif | 中文品牌、Mission 标题、Artifact 长文标题、完成总结 |
| Interface Sans | Sidebar、Thread、正文、按钮、表格、Evidence |
| Scientific Mono | ID、Hash、Query、Prompt、Raw Event；仅在技术详情中 |

默认中文产品语言使用无衬线正文。内部 ID 不得以等宽字体出现在默认产品层。

## 6. 组件外观

- Panel 主要通过边界和背景层级区分；
- 圆角保持克制，通常 4–8px；
- 阴影主要用于 Overlay、Popover、Context Detail 和拖动层；
- Summary Card 每次最多三个，并且必须可操作；
- 不使用大号统计数字、彩色 Dashboard 图表或每模块独立主题色；
- Button 层级区分 Primary、Secondary、Ghost 和 Destructive；
- Disabled 控件只用于暂时不可操作的真实状态，不作为页面核心内容；
- Completed Mission 不显示禁用 Composer。

## 7. Artifact 与 Evidence

Artifact 长文使用稳定阅读宽度和编辑式排版。Statement、数据单元格、Claim、Relation 等可核查对象必须具有一致的 Evidence affordance：

- 可点击；
- 有明确支持、冲突或未解决状态；
- 不只依赖颜色；
- 打开 Context Panel 时保持主内容位置；
- 完整来源在 Primary Workspace 打开。

## 8. Brand Site

首页保持已经冻结的单 CTA：

```text
进入工作台
```

首页视觉只使用 `apps/site/public/visual/homepage-ascii.mp4`。不恢复双 CTA、Poster、WebGL、Three.js、R3F 或旧视觉引擎。

## 9. 禁止项

- 整页黑色或深蓝 Coding Agent 主题；
- OpenHands 默认品牌、Logo、文案或配色直接进入产品；
- 聊天气泡成为工作台主要排版；
- 大面积卡片墙；
- 原生后台表单质感；
- `A-17 CANVAS`、`Preview`、泛化 `Context` 等工程文案；
- 将 Fixture、Adapter、Execution Mode、Hash 或内部 ID 放在默认 Header；
- 在组件内散落未登记色值；
- 用状态色替代状态文字；
- 为展示“Agent 感”加入无业务价值的流光、粒子、头像或 Token 动画。

## 10. 视觉验收

每个正式视觉检查点必须提供：

- 1440×900；
- 1280×800；
- 390×844；
- 200% 字体；
- keyboard-only；
- Running、Needs review、Artifact Review、Evidence Detail 和 Completed；
- 与原版上游骨架的结构对照；
- 与本规范的换肤对照。

截图由用户确认后才可进入下一产品 Gate。
