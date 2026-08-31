# Product Design

| 元数据 | 值 |
| --- | --- |
| Authority | 产品设计原则、体验域关系与设计不变量 |

## 1. 产品命题

星文智析以科研任务为上下文，由 Agent 组织研究并产生版本化科研产物，再通过 Evidence、SourceSnapshot、Version 与人类复核建立可信闭环。

```text
Research Intent
→ Research Contract
→ Research Run / Agent Activity
→ Scientific Artifact
→ Evidence Review
→ Revision / Export / Share
```

产品不以聊天历史、工具日志、功能来源、文件浏览器或静态 Dashboard 组织科研工作。

## 2. 体验域

| 体验域 | 核心职责 | 边界 |
| --- | --- | --- |
| Brand Site | 品牌与主案例认知 | 不承担研究执行或项目管理 |
| Research Workspace | 研究、产物审查、证据核验、修订 | 唯一私有科研工作台 |
| Public Share | 冻结 ArtifactVersion 与必要 Evidence | 不提供编辑、运行或动态 latest |

## 3. 设计原则

- **成熟交互优先**：Shell、Navigation、Thread、Activity、Composer、Command、Focus、Resize、Scroll 优先使用已经采用和验证的成熟实现，不为“定制感”重新手写。
- **科研产物优先**：对话解释研究过程，Artifact / Evidence 承载正式科研结果。
- **能力深度融合**：新增或迁入能力必须转化为当前 Domain、Run、Artifact、Evidence 与 UX，不保留功能岛。
- **无拼接感**：同类动作、状态、错误、结果与证据使用同一产品语言和交互模型。
- **Evidence-first**：关键数据、结论、关系与版本可回到来源与 locator。
- **人类控制**：Contract、Checkpoint、Evidence review、RevisionPlan 与公开分享具有清晰决策点。
- **渐进复杂度**：先呈现任务、Agent 状态、主结果与下一步，再按需披露执行细节。
- **真实性分层**：Live、Cached、Recorded、Fixture、Benchmark、Revision、partial/unsupported 分别表达。
- **Current-only**：不为旧命名、旧 renderer、旧 API 或历史测试保留生产兼容层。
- **单一 Authority**：UI 不复制 Domain、Workflow、Version、Evidence、Transport 或 Renderer 规则。
- **视觉服从阅读**：低噪声、高密度、长期科研阅读优先，不用卡片墙和装饰性“AI 感”。
- **可恢复与可访问**：运行、页面、布局、键盘与失败恢复是正式体验。

## 4. 产品对象

| 产品语言 | 领域对象 |
| --- | --- |
| 研究项目 | ResearchProject |
| 研究运行 | ResearchRun |
| 研究协议 | ResearchContract |
| 科研结果 | Artifact / ArtifactVersion |
| 证据 | Evidence |
| 来源 | SourceSnapshot |
| 修订 | RevisionPlan / derived Run / superseding ArtifactVersion |
| 分享 | ShareSnapshot |

adapter、provider、schema、hash、内部 ID、工具编号和能力来源不是默认产品对象。

## 5. 结构不变量

- Workspace 只有一套 Shell、一个 Research Thread、一个 Composer、一个 Result Index、一个 Fullscreen Result Workspace、一个共享 Evidence presentation。
- Artifact Renderer Registry 是结果 kind dispatch 的唯一入口；不能为私有/公开/特殊能力各建一套 renderer family。
- 右侧 Research Rail 只做概览与索引，不成为第二个结果详情区。
- Graph、Reasoning、Diff、Revision、论文 PDF 与 Scientific Artifact 都进入 Fullscreen Result Workspace 的统一架构。
- Public Share 独立于私有 Agent Shell，但复用同一 typed presentation primitives，并由后端正向公开投影控制数据最小化。
- ReasoningTrace 展示公开可审查依据，不展示私有 chain-of-thought。
- 未实现能力不得以禁用大按钮、假数据或“Coming soon”占据主流程。

## 6. 能力的产品化转化

任何新能力进入产品前必须回答：用户为什么需要、从哪里触发、结果属于哪个 Artifact、Evidence 在哪里、失败如何呈现、如何回到主研究叙事。

禁止：

- 为单一能力增加无必要顶层导航；
- 让用户选择内部执行来源或实现路径；
- 为每个 Scientific Skill 建独立工具页面；
- 把原始脚本输出、本地文件路径或 raw JSON 当成主要结果；
- 用新的 Panel/Shell 避开现有 Result Workspace。

正确体验是让 Agent 根据 Contract 和上下文调用能力，并把中间活动与正式结果分别映射到 Activity、Artifact、Evidence 与 Revision。

## 7. 视觉与交互

Brand Site 承担品牌表达；Workspace 保持 Light、Cold Paper、低饱和 Bluegray 与编辑式科研阅读。业务前端尺寸、间距、字体、圆角、阴影、z-index、breakpoint、panel geometry 和 motion 消费语义 Token / `@xingwen/ui` variants。

优先现有共享 UI、成熟交互 primitive 与专业图表/图布局能力。不要为追求“定制感”手写成熟组件已经解决的基础交互。

## 8. 人工产品门禁

自动化只能证明契约、回归和部分 NFR，不能独立证明产品已经成熟。正式验收必须在真实浏览器中检查：能力发现、连续研究叙事、结果可读性、Evidence 路径、失败/恢复、键盘与 1280×800、1440×900 桌面视口。
