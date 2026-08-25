# AGENTS

本文件是仓库内 Agent、Codex 与自动化实现者的执行宪法。它定义工作前置、范围、Git 安全、架构纪律、产品完成定义、验证与正式 Review 规则。产品、架构、数据、UX 等领域事实仍由 [docs/README.md](docs/README.md) 指向的唯一 Authority 定义。

## 1. 指令与事实优先级

执行时按以下顺序处理约束：

1. 用户在当前任务中的明确授权与禁止事项；
2. 当前 Issue / PR 的稳定验收契约［
3. 本文件与 [CONTRIBUTING.md](CONTRIBUTING.md)［
4. [docs/README.md](docs/README.md) 指向的领域 Authority；
5. 当前代码、生成 Contract、数据库事实、测试与真实运行证据。

Authority 与实现冲突时不得选择更方便的一方继续。先判定实现漂移、文档漂移或本次任务是否正在改变 Authority，再把当前规则与实现重新收敛为单一事实源。

## 2. 每次任务的强制前置

开始修改前必须：

- 获取当前 `origin/main`，记录精确 Commit SHA；
- 检查当前分支、工作区状态和已有 diff，保留用户已有有效修改［
- 明确交付模式、范围、非目标和验收标准［
- d�� `docs/README.md` 只读取直接相关 Authority；
- 检查目标能力是否已经存在，先做 gap analysis，再决定新增、迁移、合并或删除；
- 从冻结的 `main` 建立任务分支，`main` 永远不是开发工作区。

冻结基线后若 `origin/main` 发生漂移，停止继续产生新修改并报告漂移。未经用户明确授权，不自动 merge、rebase、reset、cherry-pick 或用新的 `main` 覆盖已冻结基线。

## 3. 交付模式

### 默认：Atomic Delivery

Issue 保持原子任务契约。默认一个 Issue 对应一个主要交付 PR，同一 Issue 同时最多只有一个有效 Open 主要交付 PR。

### 例外：Grouped Delivery

只有用户或维护者明确授权，并且多个 Issue 属于同一垂直产品闭环、共享同一架构边界、需要共同集成或共同验证时，才允许一个 PR 同时交付多个 Issue。

Grouped Delivery 必须：

- 在 PR 正文声明授权背景与包含的 Issue；
- 为每个 Issue 单独列出 acceptance / implementation / evidence / remaining-risk；
- 不因打包而降低任何 Issue 的验收标准；
- 不把无关清理、顺手重构或独立产品能力塞入同一 PR；
- 仍遵守“一个 Issue 同时只有一个有效主要交付 PR”［
- 合并与 Issue closure 由用户或明确的 PR closure 语义决定，不自动扩大关闭范围。

不要为了流程新建没有产品价值的 umbrella Issue、stack 编号或阶段代号。

## 4. Current-only 与单一 Authority

仓库只维护当前最优架构，不保存为历史实现服务的兼容包袱。除非真实外部兼容性要求被明确授权，否则：

- 不建立旧 API / 新 API 双轨［
- 不保留 obsolete facade、旧 renderer、旧 store、旧 workflow、旧 schema 或旧命名别名［
- 不为“以后可能需要”建立通用 registry、strategy、planner、audit framework 或迁移框架；
- 新实现优先 reuse → absorb → consolidate → delete，再考虑新增抽象［
- 修改触达区域必须清除由本次变更直接产生或暴露的死代码、重复路径和失真测试。

下列事实只能有一个生产 Authority：Workspace Shell、Repository/Query server-state、ResearchRun/Step/Attempt/Event、Scientific runtime、Publisher、ArtifactVersion、Evidence、Revision、Renderer Registry、Public Share presentation、安全与模型执行记录。

任何新增或迁入能力都必须进入这些现有 Authority，不得旁路重建第二套 runtime、store、publisher、evidence、graph、revision、renderer 或 workspace。

## 5. 能力复用与融合

项目鼓励尽可能吸收成熟能力，但最终生产系统只能呈现为本项目自身的一套连续产品与工程体系。

实施时必须：

- 先核对当前 `main` 已具备的能力与质量，避免按外部目录或功能清单重复实现；
- 优先复用成熟算法、协议、交互机制、数据结构和现有内部能力；
- 对迁入能力统一领域命名、状态、错误、Evidence、Version、Artifact 与 UX；
- 删除只为过渡存在的 bridge、wrapper、双 DTO、双状态同步和孤立工具页；
- 用户不得需要理解能力来源、外部模块边界或实现拼装结构才能完成任务；
- 源码许可、归因和精确来源由法律文件及机器可读 provenance 负责，不写入治理 Markdown；
- 外部能力的具体名称、仓库地址、版本、提交号、迁移矩阵与差异审查只存在于实施 Prompt、PR/Review 或必要 provenance，不进入面向提交包的治理文档。

## 6. 产品与前端完成定义

**浏览器中不可发现、不可进入、不可理解或不可操作的用户功能，不算产品已实现。** API、单元测试、Fixture、静态截图或隐藏开发入口不能单独证明功能交付。

用户可见能力必须具备：真实入口、真实数据路径、明确 loading/empty/error/partial/unsupported、可恢复操作、必要 Evidence、权限边界和高价值 Browser 覆盖。

Research Workspace 继续使用当前已经采用并验证的成熟 Agent 交互骨架作为唯一 Shell；领域能力通过现有 Adapter、Domain、Renderer、Evidence 与 Fullscreen Result Workspace 深度集成。不得为新能力再造第二套 Dashboard、Docked Result Detail、工具控制台或独立门户。

新改业务前端的视觉数值必须消费语义 design token 或 `@xingwen/ui` component variant。Page / Feature 不直接散落任意视觉 magic number，不重复实现成熟组件已负责的 Dialog、Tabs、Popover、Focus、Resize、Graph layout 等基础机制。

默认产品 UI 使用用户语义，不以内部 ID、hash、schema、producer、adapter、raw enum、Issue/PR 编号或技术编号制造“专业感”。

## 7. 科研真实性与证据

- 关键数据、Summary、Claim、Accepted Relation、GraphEdge、科学结论与修订必须解析到真实 Evidence / SourceSnapshot / locator；
- ArtifactVersion 不可原地覆盖；Revision 通过确认后的 RevisionPlan、派生 Run 与新版本表达［
- frozen upstream reads 使用明确版本，不动态读取 `latest`；
- ReasoningTrace 只保存公开可审查的依据、条件、比较与引用，不保存模型私有 chain-of-thought［
- Live、Cached、Recorded、Fixture、Benchmark、Revision 必须准确区分，测试或录制数据不得冒充 Live［
- provider/model/prompt/input/output/provenance 只在真正可复现边界保存，不建立无业务价值的 hash-of-hash 或审计哈希体系。

## 8. 竞赛与模型

参赛主案例必须遵守 [Competition Compliance](docs/product/COMPETITION_COMPLIANCE.md)。合格模型的官方调用路径、model/revision、调用证明、ProducerExecution、ArtifactVersion 与 Evidence 必须形成真实闭环。非合格模型只能用于 benchmark、消融或对照，不得包装为合格主模型。

API Key、认证头、原始私有 provider response 与私有 reasoning 不得写入源码、日志、Artifact、截图或公开分享。

## 9. Markdown 展示边界

治理 Markdown 是最终提交包的一部分，必须从本项目自身产品与工程事实出发书写：

- 不出现外部参考项目或上游产品名称、仓库 URL、tag、commit、Issue/PR 编号、迁移来源标签或历史采用说明；
- 不保存工作阶段、批次、进度、Review ID、CI run ID、具体修复历史等过程性内容；
- 不为“证明借鉴”列举外部功能目录；
- 当前运行所必需的模型、协议、数据源和技术标准可在对应 Authority 中按事实出现［
- 法律归因与第三方许可证由 NOTICE、LICENSE、THIRD_PARTY_NOTICES 或机器 provenance 负责，不复制进治理 Authority。

## 10. 代码纪律

- 只改当前任务需要的文件Ｙ
- 不夹带无关格式化、依赖升级或目录重排［
- 精确 staging，禁止用 `git add .`、`git add -A` 或 `git add --all` 代替范围确认；
- 不通过 `any`、不安全断言、宽泛异常吞噬或伪 fallback 掩盖契约错误［
- 不为单个 Review finding 建永久框架、扫描器、快照体系或通用 abstraction；
- 一字母紧跟整数的内部版本/阶段简写禁止用于代码、测试、fixture、注释、文档、Prompt、commit、Issue、PR 与 ReviewＹ真实外部版本、科学版本和严重级别具有实际语义时除外［
- 工作过程文件、临时脚本、下载物、日志与本地绝对路径不得提交。

## 11. 验证

验证与风险匹配，优先少量高价值证据：

- Domain / Contract / Schema invariants；
- PostgreSQL + Worker / Publisher 的真实纵向链［
- Fixture / HTTP mapping parity；
- Browser 用户闭环、权限、安全、失败与恢复；
- Evidence closure、Revision、Share freeze；
- Accessibility、200% text、核心 viewport 和性能预算［
- 新增或迁入能力与当前单一 Authority 的集成回归。

测试通过是必要条件，不是完成定义。不要用脆弱 CSS class/snapshot、重复层级测试或大面积 hash mutation tests 代替产品与架构验证。

只报告实际执行并观察到的结果；未验证项明确写出，不能把“代码看起来可以”写成 PASS。

## 12. 正式 PR Review

用户要求“审核/审查/再次审核”时，执行完整 Review，而不是只看最后一个修复 Commit：

1. 获取 PR 元数据并冻结 exact HEAD、base、当前 `main` 与 merge-base；
2. 审查该 HEAD 的完整 PR diff；
3. 对照 Issue / Grouped Delivery acceptance、Authority、架构和真实 CI［
4. 先形成 findings，再执行一次独立 adversarial omission sweep；
5. 给出 exact-head verdict［
6. 提交恰好一个绑定该 HEAD 的 GitHub Review，默认使用 `COMMENT`，正文明确 verdict［
7. 未 Ready 时给出一个窄而可执行的修复 Prompt［
8. 新 Commit 使旧 Review 与旧 exact-head 证据失效，必须重新完整审查。

未经用户明确要求，不在 Review 中 merge、mark Ready、启用 auto-merge、关闭 Issue，或静默替实现者修复实质代码问题。

## 13. 完成报告

完成实现后至少报告：

- branch / exact HEAD / frozen base［
- 改动的真实范围［
- Authority 是否变化；
- 执行过的验证与实际结果；
- 未执行项、残余风险和外部依赖；
- PR 状态与是否仍为 Draft。

不得编造运行、CI、CodeQL、provider、部署、benchmark 或用户可见结果。