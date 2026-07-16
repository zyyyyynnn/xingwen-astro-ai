# Visual Language

| 项目状态           | 口径                                                    |
| ------------------ | ------------------------------------------------------- |
| Status             | Accepted for implementation                             |
| A-01 foundation    | Implemented：基础浅色 Token 与共享 UI 入口              |
| A-02 visual system | Pending                                                 |
| Runtime boundary   | `packages/design-tokens` + React UI + GPU Visual Engine |

本文定义星文智析的品牌视觉、配色 Token、字体、排版、ASCII / Dither、动效与组件外观。实现不得从参考产品复制界面皮肤，也不得在业务页面临时追加独立色值和视觉规则。

## 1. 核心概念

视觉母题为：

> **雾霾蓝天体在冷灰观测纸面上，被实时解析为 ASCII 字符、Dither 网点、轨道与证据结构。**

系统不是深色“太空大屏”。浅色背景承担理性、开放和材料感；低饱和雾霾蓝承担天体、品牌与交互焦点；深蓝灰承担文字、坐标与结构。

### 1.1 视觉关键词

- 编辑式天文排版
- 巨型裁切天体
- ASCII 字符颗粒
- 有序抖动与半色调
- 观测坐标与轨道
- 冷淡灰纸面
- 低饱和雾霾蓝
- 精密而非赛博朋克
- 艺术性入口，克制型工作区

### 1.2 明确禁止

- 黑底星空作为默认界面
- 高饱和蓝紫渐变
- 霓虹发光、强外辉光
- 玻璃拟态卡片堆叠
- 大面积圆角卡片墙
- 无业务意义的粒子雨或星点背景
- 聊天气泡作为工作台主要排版
- 每个模块使用不同主题色
- 用颜色替代来源、版本和状态文字

## 2. 品牌识别

### 2.1 名称层级

- 中文主标：**星文智析**
- 英文副标：`XINGWEN ASTRO AI`
- 产品描述：天文科研数据与证据工作台

中文主标始终优先。英文副标用于坐标、章节、页脚、加载画面和国际化辅助，不与中文机械等宽并排。

### 2.2 字标原则

字标采用定制排版而不是直接使用普通标题：

- 中文主标以衬线字形为基础，调整字面宽度、重心和笔画连接。
- “星”与“文”强调观测与知识，“智”与“析”强调计算与解析。
- 字标可以配合一组小型 ASCII / 轨道符号，但符号不得取代中文名称。
- 小尺寸场景使用简化字标，不保留细碎字符纹理。
- 只为四字主标做有限字距、重心和连接调整，不制作完整定制字体或字体族。

### 2.3 品牌符号

建议使用“观测孔径 + 轨道切面 + 字符栅格”的组合符号：

```text
圆形观测边界
+ 一条偏心轨道弧
+ 局部 4×4 字符 / 网点栅格
```

不得使用通用星星、火箭、机器人头像或聊天气泡作为主标志。

## 3. 色彩系统

### 3.1 色彩角色

| 色彩角色         | 作用                             |
| ---------------- | -------------------------------- |
| Cold Paper       | 页面基底、留白和内容承载         |
| Lunar Gray       | 分区、边界、禁用与次级信息       |
| Haze Blue        | 品牌、交互焦点、天体与空间关系   |
| Deep Observatory | 文字、坐标、关键结构与高对比状态 |
| Semantic Status  | 成功、风险、失败、缓存等独立语义 |

### 3.2 基础原色 Token

```css
:root {
  /* Cold paper */
  --raw-paper-0: oklch(0.995 0.002 230);
  --raw-paper-50: oklch(0.978 0.004 230);
  --raw-paper-100: oklch(0.955 0.006 230);
  --raw-paper-200: oklch(0.925 0.008 230);

  /* Lunar gray */
  --raw-gray-100: oklch(0.89 0.01 235);
  --raw-gray-200: oklch(0.84 0.012 235);
  --raw-gray-300: oklch(0.76 0.014 235);
  --raw-gray-400: oklch(0.67 0.016 235);
  --raw-gray-500: oklch(0.57 0.018 235);
  --raw-gray-600: oklch(0.47 0.02 235);
  --raw-gray-700: oklch(0.38 0.022 235);
  --raw-gray-800: oklch(0.29 0.024 235);
  --raw-gray-900: oklch(0.21 0.026 235);

  /* Haze blue */
  --raw-haze-50: oklch(0.97 0.012 235);
  --raw-haze-100: oklch(0.93 0.02 235);
  --raw-haze-200: oklch(0.87 0.032 235);
  --raw-haze-300: oklch(0.78 0.045 235);
  --raw-haze-400: oklch(0.68 0.055 235);
  --raw-haze-500: oklch(0.59 0.062 235);
  --raw-haze-600: oklch(0.5 0.058 235);
  --raw-haze-700: oklch(0.41 0.05 235);
  --raw-haze-800: oklch(0.33 0.042 235);
  --raw-haze-900: oklch(0.26 0.034 235);

  /* Semantic */
  --raw-success-500: oklch(0.56 0.07 165);
  --raw-warning-500: oklch(0.6 0.075 80);
  --raw-error-500: oklch(0.56 0.085 25);
  --raw-info-500: oklch(0.57 0.06 245);
}
```

这些值是首轮实现基线。允许在视觉回归和对比度测试后微调，但必须统一修改 Token，不得在组件内散落替代色。

### 3.3 语义 Token

```css
:root {
  --color-canvas: var(--raw-paper-50);
  --color-surface: color-mix(
    in oklch,
    var(--raw-paper-0) 86%,
    var(--raw-haze-50)
  );
  --color-surface-raised: var(--raw-paper-0);
  --color-surface-muted: var(--raw-paper-100);
  --color-surface-hover: color-mix(
    in srgb,
    var(--raw-haze-100) 68%,
    var(--raw-paper-0)
  );

  --color-ink-primary: var(--raw-gray-900);
  --color-ink-secondary: var(--raw-gray-600);
  --color-ink-tertiary: var(--raw-gray-500);

  --color-border: var(--raw-gray-200);
  --color-border-subtle: var(--raw-gray-100);

  --color-brand: var(--raw-haze-600);
  --color-brand-hover: var(--raw-haze-700);
  --color-brand-muted: var(--raw-haze-100);
  --color-focus: var(--raw-haze-500);

  --color-success: var(--raw-success-500);
  --color-warning: var(--raw-warning-500);
  --color-error: var(--raw-error-500);
  --color-live: var(--raw-success-500);
  --color-cached: var(--raw-warning-500);
  --color-revised: var(--raw-info-500);
  --color-demo: var(--raw-haze-600);

  --color-visual-paper: var(--raw-paper-50);
  --color-visual-celestial-ink: var(--raw-haze-700);
  --color-visual-celestial-deep: var(--raw-haze-900);
  --color-visual-celestial-soft: var(--raw-haze-200);
  --color-visual-orbit: color-mix(
    in oklch,
    var(--raw-haze-700) 25%,
    transparent
  );
  --color-visual-grid: color-mix(
    in oklch,
    var(--raw-gray-600) 10%,
    transparent
  );
  --color-visual-particle: var(--raw-haze-500);
}
```

实现可提供兼容别名，但业务组件只能使用语义 Token；Raw Token 仅允许出现在 `packages/design-tokens`。

### 3.4 色彩使用比例

推荐全局比例：

```text
冷淡灰 / 白灰基底     72–82%
深灰文字与结构        12–18%
雾霾蓝品牌与焦点       5–9%
状态色                 < 2%
```

雾霾蓝不应铺满所有卡片。视觉冲击来自天体形态、尺度、密度和排版，而不是提高饱和度或面积。

### 3.5 状态色规则

- 状态色只描述状态，不描述模块。
- `cached` 使用低饱和棕金，但必须同时显示“缓存”和运行时间。
- `demo_replay` 使用雾霾蓝 + 明确文字。
- `live` 使用雾霾蓝动态指示，但不使用高饱和绿色。
- `failed` 使用低饱和红灰，并提供下一步操作。
- `revised` 使用雾霾蓝与版本标识组合，不另设新主题色。

## 4. 字体系统

### 4.1 三层字体角色

| 角色            | 用途                               | 推荐                                         |
| --------------- | ---------------------------------- | -------------------------------------------- |
| Brand Serif     | 中文字标、叙事大标题、章节引语     | 思源宋体 / Noto Serif SC，并对字标定制       |
| Interface Sans  | 正文、控件、表格、Evidence         | 思源黑体 / Noto Sans SC + Inter 等拉丁无衬线 |
| Scientific Mono | ASCII、参数、坐标、ID、Query、Hash | IBM Plex Mono / JetBrains Mono               |

字体候选必须先通过许可证、中文覆盖、Web 传输和未来离线封装检查：

| 候选                           | 许可证      | 中文覆盖         | Web / Tauri 策略                                          |
| ------------------------------ | ----------- | ---------------- | --------------------------------------------------------- |
| Noto Serif SC / 思源宋体       | SIL OFL 1.1 | 完整简体中文     | Web 使用授权明确的 WOFF2 子集；Tauri 可连同许可证离线打包 |
| Noto Sans SC / 思源黑体        | SIL OFL 1.1 | 完整简体中文     | 正文按字重和字符集拆分；加载失败回退系统无衬线            |
| Inter                          | SIL OFL 1.1 | 拉丁、数字       | 仅作为拉丁补充，不承担中文正文                            |
| IBM Plex Mono / JetBrains Mono | SIL OFL 1.1 | 主要为拉丁、符号 | 用于参数与 ASCII；离线包必须保留许可证                    |

实施前记录实际字体版本、下载来源、许可证文件与 subset 命令。未完成授权记录前不得提交字体二进制；Web 使用 `font-display: swap`，静态首屏不得等待字体或 WebGL 才可见。

品牌衬线与正文无衬线必须并存，但不能平均混排：

- 衬线只用于品牌、叙事和少量关键标题。
- 无衬线负责所有操作与长时间阅读。
- 等宽只用于结构化元信息和 ASCII，不用于大段中文正文。

### 4.2 字号比例

```css
:root {
  --font-size-00: 0.6875rem;
  --font-size-0: 0.75rem;
  --font-size-1: 0.8125rem;
  --font-size-2: 0.9375rem;
  --font-size-3: 1rem;
  --font-size-4: 1.125rem;
  --font-size-5: 1.375rem;
  --font-size-6: 1.75rem;
  --font-size-7: clamp(2.25rem, 4vw, 4.5rem);
  --font-size-8: clamp(4rem, 10vw, 9rem);
}
```

工作台正文以 `--font-size-2` 或 `--font-size-3` 为主；首页字标和 ACT 标题可使用 7–8 级。

### 4.3 排版习惯

- 中文标题不使用过粗字重，依靠字号、字距和留白建立层级。
- 英文副标题使用大写、较宽字距和等宽编号，但避免全页大写。
- 参数标签采用 `LABEL / VALUE` 或 `01 — LABEL`，不模仿终端绿色字符。
- 长段 Evidence 使用舒适行长，建议 56–76 个中文字符宽度。
- 表格数字右对齐；单位与数值之间保持稳定间隔。

## 5. ASCII / Dither 系统

### 5.1 视觉角色

ASCII 粒子不是背景装饰，而是品牌与状态语言：

- 首页：构成完整天体、星云边缘和轨道扰动。
- Guided Tour：表现任务阶段的聚合、过滤、坍缩和重组。
- 工作台：仅用于空状态、运行状态、缩略图和空间关系。
- 数据和 Evidence 正文：不使用持续字符动画。

### 5.2 字符梯度

首选字符 Ramp：

```text
· : + * # % @
```

可扩展符号：

```text
/ \ | — ○ ◌ ◦ ×
```

约束：

- 同一画面核心 Ramp 不超过 7 个字符。
- 中文字符不作为高频粒子，避免纹理噪声和字体差异。
- 字符间距、行距和像素密度由 Shader 统一控制。
- 近看字符清晰，远看必须形成连续明暗，而不是终端字符墙。

### 5.3 Dither 规则

- 品牌主视觉以 ASCII 字符与 Dither 网点约各半为目标；可为可读性和设备能力小幅调整，但不得退化为纯字符墙或纯网点滤镜。
- 主算法采用 Bayer Matrix 或稳定蓝噪声，不使用每帧随机噪声造成闪烁。
- 字符阈值根据亮度、法线、深度和局部数据密度计算。
- 动画中的噪声应空间稳定；相机移动时不能出现严重摩尔纹。
- 核心天体可混合字符 Atlas 与网点，不要求全画面都是文字。
- 数据映射必须有图例或说明，不能暗示不存在的精度。

### 5.4 数据映射

允许映射：

| 数据       | 视觉变量                             |
| ---------- | ------------------------------------ |
| 工作流阶段 | 粒子聚合方向、轨道位置、形态转换     |
| 数据质量   | 字符密度、连续性、缺口比例           |
| 论文筛选   | 粒子保留 / 消散、轨道层级            |
| Claim 关系 | 连线类型、路径方向、局部聚合         |
| 失败与重试 | 结构断裂、停滞、重建，不使用剧烈抖动 |

不可映射：未经验证的科学事实、无证据关系、虚构观测值。

## 6. 构图系统

### 6.1 首页构图

- 天体主体覆盖视口宽度的 70–115%，允许裁切。
- 视觉重心不长期居中，使用偏轴构图和负空间容纳标题。
- 导航、标题和按钮始终为 DOM，不烘焙进 Canvas。
- 首屏至少保留一个清晰主动作和一个可信性入口。
- 不把完整行星缩小放在页面中央形成普通插画。

### 6.2 工作台构图

工作台采用“细框架 + 大画布 + 局部高密度”的结构：

- 外壳边界清楚，不堆叠浮动卡片。
- 左、右侧栏以连续面板存在，而不是多个圆角容器。
- 中央画布可拆分，但最多三块。
- 重要产物拥有明确标题、来源和版本带。
- ASCII 和轨道纹理只出现在边界、空状态或空间视图。

### 6.3 圆角与阴影

```css
:root {
  --radius-xs: 2px;
  --radius-sm: 4px;
  --radius-md: 7px;
  --radius-lg: 10px;
  --radius-pill: 999px;

  --shadow-float: 0 12px 28px
    color-mix(in srgb, var(--raw-gray-900) 10%, transparent);
  --shadow-modal: 0 24px 64px
    color-mix(in srgb, var(--raw-gray-900) 16%, transparent);
}
```

- 普通布局优先使用分隔线和背景层级，不使用阴影。
- 阴影只用于 Popover、Dialog、拖拽层和临时浮层。
- 页面级容器不得使用大圆角制造“玩具化”。

## 7. 图标与线条

- 图标采用 1.25–1.5px 线性风格。
- 项目独有图标应基于轨道、观测孔径、谱线、数据列、证据定位设计。
- 通用功能可使用成熟图标库，但不得用机器人、魔法棒和闪光星替代 AI 功能。
- 轨道线、关系线与表格边界必须有不同语义，不可只靠相同虚线区分。

## 8. 动效语言

### 8.1 三类动效

| 类型             | 作用         | 示例                               |
| ---------------- | ------------ | ---------------------------------- |
| Celestial Motion | 品牌与空间感 | 天体自转、凌星、轨道视差           |
| Assembly Motion  | 科研过程     | 字符聚合为数据、论文、Claim、Graph |
| Interface Motion | 操作反馈     | 面板切换、证据定位、状态变化       |

### 8.2 时长

```css
:root {
  --motion-instant: 90ms;
  --motion-fast: 150ms;
  --motion-base: 220ms;
  --motion-slow: 420ms;
  --motion-scene: 900ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --ease-enter: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-exit: cubic-bezier(0.7, 0, 0.84, 0);
}
```

首页天体可以使用 12–24 秒的连续慢周期；工作台不得使用持续吸引注意力的循环动画。

### 8.3 Reduced Motion

- 取消滚动绑定相机移动。
- 用淡入、静态分帧或 Poster 替代形态转化。
- 保留任务状态变化，但不使用粒子聚合。
- 不因关闭动画隐藏任何业务信息。

## 9. 组件外观原则

### 9.1 Button

- 主按钮使用雾霾蓝实底，尺寸克制。
- 次按钮优先边框或透明背景。
- 不使用大面积渐变和发光。
- 运行型按钮显示状态与快捷键，而不是只显示图标。

### 9.2 Input / Research Console

- 输入区更像研究指令台，不像聊天气泡。
- 顶部或底部包含当前项目、运行模式和上下文范围。
- 支持自然语言，但提交后优先生成 ResearchContractDraft，用户确认后才形成 ResearchContract。

### 9.3 Panel

- 面板标题带对象类型、名称、来源模式与版本。
- 面板焦点使用雾霾蓝细边或顶线，不使用强阴影。
- 面板关闭、拆分和固定操作在 hover / focus 时出现。

### 9.4 Table

- 高密度但可扫读；表头固定，数字对齐。
- 来源、质量和缺失值具备可访问的语义标记。
- 行 hover 只改变浅背景，不改变尺寸。
- 选中单元格可直接打开 Evidence Observatory。

### 9.5 Evidence

- Evidence 以阅读和核验为主，视觉最克制。
- 清楚展示 `locator`、`quote_or_value`、来源、时间、提取方式、置信度和版本。
- 不用 ASCII 纹理覆盖引用内容。

## 10. 性能质量档

| 档位   | 目标                   | 策略                                |
| ------ | ---------------------- | ----------------------------------- |
| High   | 可控终审展示或录制设备 | 高粒子密度、完整 Shader、适量后处理 |
| Medium | 普通现代笔记本         | 降低 DPR、粒子和采样，保留主要形态  |
| Low    | 集显、移动端、节能模式 | 低帧率或静态 Poster，核心 DOM 完整  |

自动检测只能作为初始建议，用户可手动切换。质量档不能改变科研数据和业务功能。

视觉回归使用固定 viewport、deterministic seed 与可冻结时间；页面隐藏时暂停渲染，卸载场景时必须释放 geometry、material、texture 和 render target。

## 11. 视觉验收

每个关键页面至少验证：

- 1440×900
- 1920×1080
- 1280×720
- 390×844 移动端降级
- 200% 字体缩放
- Reduced Motion
- High / Medium / Low 图形质量

首页、Guided Tour、工作台、数据表、论文、推理、图谱、Evidence 必须有视觉回归快照。
