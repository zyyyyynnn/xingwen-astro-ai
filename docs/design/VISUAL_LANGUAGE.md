# Visual Language

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 品牌、Token、字体、排版、密度与组件外观 |

本文定义 Brand Site 与 Research Workspace 的统一视觉语言。业务组件只消费语义 Token。

## 1. 视觉命题

> 冷灰观测纸面上，低饱和 Bluegray 承载天文对象、文字、结构与精密交互。

关键词：

- 编辑式天文排版；
- Cold Paper；
- 低饱和 Bluegray；
- 清晰结构线；
- 高信息密度；
- 长时间阅读；
- 小面积状态色；
- 精密而非赛博朋克。

## 2. Brand Site 基线

Homepage 保留：

```text
紧凑品牌栏
→ homepage-ascii.mp4
→ 单一“进入工作台”CTA
→ 两行衬线标题
→ 四列能力说明
```

固定资产：

```text
apps/site/public/visual/homepage-ascii.mp4
```

固定标题：

```text
让每一颗系外行星候选体
都可溯源
```

唯一 CTA：`进入工作台`，目标 `/workspace`。

视频使用原生 `<video>`，无音频；Reduced Motion 和页面隐藏时暂停。视频失败不影响标题、说明与 CTA。

## 3. 色彩系统

```css
:root {
  --raw-paper-0: #fcfefe;
  --raw-paper-50: #f5f8fa;
  --raw-paper-100: #ecf1f3;
  --raw-paper-200: #e1e7eb;

  --raw-bluegray-50: #f3f7fa;
  --raw-bluegray-100: #e8eef1;
  --raw-bluegray-200: #d2dadf;
  --raw-bluegray-300: #b7c1c7;
  --raw-bluegray-400: #919ca2;
  --raw-bluegray-500: #6e7981;
  --raw-bluegray-600: #505d65;
  --raw-bluegray-700: #37444d;
  --raw-bluegray-800: #202d36;
  --raw-bluegray-900: #0c1a23;

  --raw-success-500: #2e8b6f;
  --raw-warning-500: #b8862b;
  --raw-error-500: #a8483e;
  --raw-info-500: #5078a8;
}
```

```css
:root {
  --color-canvas: var(--raw-paper-50);
  --color-surface: var(--raw-paper-0);
  --color-surface-muted: var(--raw-paper-100);
  --color-surface-hover: var(--raw-paper-200);

  --color-ink-primary: var(--raw-bluegray-900);
  --color-ink-secondary: var(--raw-bluegray-600);
  --color-ink-tertiary: var(--raw-bluegray-500);

  --color-border: var(--raw-bluegray-200);
  --color-border-strong: var(--raw-bluegray-400);

  --color-brand: var(--raw-bluegray-500);
  --color-brand-hover: var(--raw-bluegray-600);
  --color-brand-pressed: var(--raw-bluegray-700);
  --color-brand-on: var(--raw-paper-0);
  --color-focus: var(--raw-bluegray-400);

  --color-success: var(--raw-success-500);
  --color-warning: var(--raw-warning-500);
  --color-error: var(--raw-error-500);
  --color-info: var(--raw-info-500);
}
```

Raw Token 只定义于 `packages/design-tokens`。

## 4. 色彩比例

```text
Cold Paper / Surface    72–82%
文字与结构              14–22%
Brand 强调               3–7%
状态色                   <2%
```

默认 Workspace 不使用全屏深色。深色只用于 Raw 输出、代码或必须保留的局部执行视图。

## 5. 字体

| 角色 | 用途 | 推荐 |
| --- | --- | --- |
| Brand Serif | 中文字标、Homepage 主标题、Artifact 长文标题 | Noto Serif SC / 思源宋体 |
| Interface Sans | Shell、Thread、控件、表格、Evidence、正文 | Noto Sans SC / 思源黑体 + Inter |
| Scientific Mono | ID、Hash、参数、Query、Raw 输出 | IBM Plex Mono / JetBrains Mono |

字体资产进入仓库前记录版本、来源与许可证。

## 6. 排版

| 区域 | 层级 |
| --- | --- |
| Shell | 12–14px，紧凑、稳定 |
| Agent Activity | 13–15px，事件层级清晰 |
| Artifact Title | 22–30px Serif |
| Artifact Body | 14–16px，行高 1.55–1.7 |
| Metadata / Status | 11–12px |
| Raw Output | 12px Mono |

长文有效行宽为 680–780px。内部 ID 与 Hash 不使用标题层级。

## 7. 密度与结构

- 间距使用 4 / 8 / 12 / 16 / 24 / 32；
- Header 高度 44–56px；
- 导航项高度 36–44px；
- Composer 收起高度 52–64px；
- 圆角 4–8px；
- 分隔线、背景层级与留白优先于卡片；
- 阴影只用于 Overlay、Popover、Menu 与浮层。

## 8. 上游换肤

选定上游后，保留其：

- 布局；
- Panel 行为；
- 焦点管理；
- 键盘交互；
- 响应式；
- 运行反馈。

替换其：

- Brand；
- Token；
- 字体；
- 图标语义；
- 密度；
- 状态外观；
- 领域内容。

不得用换肤为理由重新实现 Shell 或交互骨架。

## 9. 状态表达

状态使用：

```text
文字
+ 图标
+ 轻量颜色
```

颜色不定义业务状态机。Run 状态来自 Workflow，Evidence 状态来自领域模型。

## 10. 图标与动效

- 使用上游单一图标体系或经批准的单一图标库；
- 不混用多个视觉风格；
- 动效只服务状态变化、流式响应、Panel 过渡和焦点引导；
- 遵守 Reduced Motion；
- 页面隐藏时暂停非必要动画。

## 11. 禁止模式

- 黑底星空作为默认界面；
- 高饱和蓝紫渐变；
- 霓虹、外辉光和玻璃拟态；
- 大面积圆角卡片墙；
- 无业务意义的粒子或轨道动画；
- 聊天气泡主导 Artifact 阅读；
- 每个模块使用独立主题色；
- 复制上游默认皮肤；
- 用颜色替代状态、来源或版本文字。

## 12. 视觉回归

固定视口：

```text
1440×900
1280×800
390×844
200% font scale
```

至少覆盖 Empty、Running、Needs Review、Completed、Artifact Review、Evidence Inspector、Compare、Error 与移动端状态。

视觉通过由用户确认。
