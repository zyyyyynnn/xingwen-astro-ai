# Product Design

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 产品设计原则、体验域关系与设计不变量 |

本文定义星文智析的设计判断标准。产品范围与成功指标见 [PRD.md](PRD.md)。页面规格见 [Workspace UX](docs/design/WORKSPACE_UX.md)，视觉规则见 [Visual Language](docs/design/VISUAL_LANGUAGE.md)，工程边界见 [Frontend Architecture](docs/architecture/FRONTEND_ARCHITECTURE.md)。

## 1. 产品命题

星文智析以科研任务为上下文，由 Agent 执行研究、生成版本化科研产物，并通过 Evidence、SourceSnapshot、Version 与人类复核建立可信闭环。

```text
Research Intent
→ Research Contract
→ Research Run
→ Agent Activity
→ Scientific Artifact
→ Evidence Review
→ Revision / Export / Share
```

产品不以聊天历史、工具日志、文件浏览器或静态 Dashboard 组织科研工作。

## 2. 体验域

| 体验域 | 核心职责 | 边界 |
| --- | --- | --- |
| Brand Site | 建立品牌识别并进入 Workspace | 不承担研究配置、Agent 执行或项目管理 |
| Research Workspace | 执行研究、审查产物、核验证据、推进修订 | 不承担营销叙事或通用 IDE 能力 |
| Public Share | 展示冻结 ArtifactVersion 与必要证据 | 不提供编辑、运行或动态 latest |

## 3. 设计原则

| 原则 | 判断标准 |
| --- | --- |
| 成熟骨架优先 | Shell、导航、Agent Thread、Workspace、Composer 与状态反馈采用成熟开源 Agent 产品源码，不参考后重写 |
| 科研产物优先 | Artifact 与 Evidence 是主要工作对象；对话与执行事件承担协作和解释 |
| Evidence-first | 关键数据、结论、关系与版本可定位 Evidence、来源和快照 |
| 人类控制 | 研究协议、证据集和结论修订具有明确决策点 |
| 渐进复杂度 | 先呈现任务、Agent 状态、主产物和下一步，再披露执行细节 |
| 真实性分层 | Fixture、Live、Cached、Revision 与失败分别表达 |
| 单一事实源 | UI 不复制 Domain、Workflow、Version 或 Transport 规则 |
| 视觉服从阅读 | Brand Site 承担品牌识别；Workspace 保持克制、高密度和长时间可读 |
| 可恢复 | 运行、页面和布局状态具有明确恢复路径 |
| 人工视觉门禁 | 自动化测试不能替代用户对产品骨架和可用性的确认 |

## 4. 产品对象

| 产品语言 | 领域对象 |
| --- | --- |
| 研究项目 | ResearchProject |
| 研究运行 | ResearchRun |
| 研究协议 | ResearchContract |
| 科研产物 | Artifact / ArtifactVersion |
| 证据 | Evidence |
| 来源快照 | SourceSnapshot |
| 修订 | 派生 Run / 新 ArtifactVersion |
| 分享 | ShareSnapshot |

产品语言不得创建第二套持久化模型。

## 5. 设计不变量

- Project 表示持续研究上下文，Run 表示一次执行。
- Contract 固定研究输入和质量约束，不保存执行方式。
- Artifact 表示稳定身份，ArtifactVersion 表示不可变内容。
- Run status、execution mode、source mode 与 revision 关系分别表达。
- 改变研究条件时创建新 Contract 或派生 Run。
- 缓存只引用真实历史 Run、ArtifactVersion 与 SourceSnapshot。
- 关键科研内容按契约绑定 Evidence。
- ReasoningTrace 只展示可审查依据，不包含模型私有推理。
- WorkspaceSnapshot 保存私有恢复状态；ShareSnapshot 保存冻结公开投影。
- 技术 ID、Hash、Adapter 与内部模式不进入默认产品视图。
- 未实现能力不得以假数据、禁用主控件或虚构状态呈现。

## 6. 前端体验边界

### Brand Site

Brand Site 使用 `homepage-ascii.mp4` 作为唯一主视觉，保留固定标题和单一“进入工作台”CTA；CTA 指向 `/workspace`。

### Research Workspace

Research Workspace 采用成熟开源 Agent 产品源码骨架，通过适配层接入既有 Domain、Repository 与 Workflow。仓库内不得保留第二套 Workspace Shell 或静态 Preview 产品路径。

### 既有核心

Domain、Contract、Repository Port、Fixture / HTTP Adapter、Workflow、Version 与后端服务保持权威，不因前端产品骨架改变。