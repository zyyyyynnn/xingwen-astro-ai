# Visual Language

| 元数据    | 值                                      |
| --------- | --------------------------------------- |
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

## 2. Brand Site

Homepage 使用以下结构：

```text
紧凑品牌栏
→ homepage-ascii.mp4
→ 单一“进入工作台”CTA
→ 两行衬线标题
→ 四列能力说明
```

固定资产：`apps/site/public/visual/homepage-ascii.mp4`。

固定标题：

```text
让每一颗系外行星候选体
都可溯源
```

唯一 CTA 为“进入工作台”，目标为 `/workspace`。

视频使用原生 `<video>`，无音频；Reduced Motion 和页面隐藏时暂停。视频失败不影响标题、说明与 CTA。

## 3. 色彩系统与 Token 权威

- 跨产品的 Raw palette、语义色彩、字号、间距、控件、图标、焦点、圆角、阴影与动效唯一定义于 [`packages/design-tokens/src/base.css`](../../packages/design-tokens/src/base.css)。
- Workspace 的栏宽、面板、Composer、命令菜单、层级与 Workspace 动效唯一定义于 [`packages/design-tokens/src/workspace.css`](../../packages/design-tokens/src/workspace.css)；已采用交互源码只通过 Workspace 的受控 Token bridge 消费这些值，桥接变量属于实现细节，不作为治理或产品标识。
- 主题色锚点为 `#6E7981`（`--raw-bluegray-500`）。
- Cold Paper 用于背景、画布与表面。
- Bluegray 用于品牌、文字、边框与交互强调。
- 语义状态色用于成功、警告、错误与信息。
- 业务组件不得硬编码 Raw 色值。

## 4. 色彩比例

```text
Cold Paper / Surface    72–82%
文字与结构              14–22%
Brand 强调               3–7%
状态色                   <2%
```
Workspace 正式主题为 Light。

## 5. 字体

| 角色            | 用途                                         | 推荐                            |
| --------------- | -------------------------------------------- | ------------------------------- |
| Brand Serif     | 中文字标、Homepage 主标题、Artifact 长文标题 | Noto Serif SC / 思源宋体        |
| Interface Sans  | Shell、Thread、控件、表格、Evidence、正文    | Noto Sans SC / 思源黑体 + Inter |
| Scientific Mono | ID、Hash、参数、Query、Raw 输出              | IBM Plex Mono / JetBrains Mono  |

字体资产进入仓库前记录版本、来源与许可证。

## 6. 排版

| 区域              | 层级                   |
| ----------------- | ---------------------- |
| Shell             | 12–14px，紧凑、稳定    |
| Agent Activity    | 13–15px，事件层级清晰  |
| Artifact Title    | 22–30px Serif          |
| Artifact Body     | 14–16px，行高 1.55–1.7 |
| Metadata / Status | 11–12px                |
| Raw Output        | 12px Mono              |

长文有效行宽为 680–780px。内部 ID 与 Hash 不使用标题层级。

Workspace 壳层统一消费 `--font-size-ui-*` 与 `--line-height-ui-*` 成对定义的 `label`、`body`、`heading` 角色。组件不得直接拼接基础字号刻度；在 Tailwind 任意值中引用字号变量时必须使用长度类型提示（`text-[length:var(...)]`），避免变量被误判为颜色而回退到浏览器默认字号。

## 7. 密度与结构

- 间距使用 4 / 8 / 12 / 16 / 20 / 24 / 32；
- Workspace 三栏顶部栏统一为 48px，并共享同一底部分隔线；品牌与主标题使用紧凑的 `body`，面板标签使用 `body`，状态文字使用 `label`；品牌可保留 Serif，但不得改变垂直基线；内容级空状态与页面标题才使用 `heading`；
- 导航项高度 36–44px；
- Composer 采用输入区与操作区分层的桌面结构，默认保留足够的组合空间；尺寸由 Workspace 语义 Token 定义，不得为追求紧凑而压缩到控件重叠、内容溢出或后续能力接入需要重做外壳；
- 圆角 4–8px；
- 分隔线、背景层级与留白优先于卡片；
- 阴影只用于 Overlay、Popover、Menu 与浮层。

## 8. Workspace 换肤

保留已采用交互骨架的：

- 布局；
- Panel 行为；
- 焦点管理；
- 键盘交互；
- 桌面工作区范围内的响应式布局；
- 运行反馈。

替换为本项目自身的：

- Brand；
- Token；
- 字体；
- 图标语义；
- 密度；
- 状态外观；
- 领域内容。

不得以换肤为由重新实现 Shell 或交互骨架。

## 9. 状态表达

状态使用：

```text
文字
+ 图标
+ 轻量颜色
```

颜色不定义业务状态机。Run 状态来自 Workflow，Evidence 状态来自领域模型。

## 10. 图标与动效

- 通用动作图标统一使用 Lucide，并经 `@xingwen/ui/icons` public export 消费；品牌资产与科研专用可视化不强制替换为 Lucide；
- 不混用多个视觉风格；
- 动效只服务状态变化、流式响应、Panel 过渡和焦点引导；
- 左右侧栏折叠统一使用 200ms ease-out 宽度过渡；内容保持稳定几何并由外层裁切，不得在过渡中重排，不得叠加位移、透明度或缩放，也不得替换切换控件节点而造成焦点与锚点漂移；
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
- 复制外部默认皮肤；
- 用颜色替代状态、来源或版本文字。

## 12. 视觉回归

固定 Web 验收视口：

```text
1440×900
1280×800
1024×768
```

至少覆盖 Empty、Running、Needs Review、Completed、Artifact Review、Evidence Inspector、Compare 与 Error。

视觉通过由用户确认。
