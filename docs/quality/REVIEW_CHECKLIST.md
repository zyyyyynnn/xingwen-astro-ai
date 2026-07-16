# Review Checklist

本清单用于 PR、自测和作品交付前检查。Current runtime 为 Vue / v1；Astro / React / v2 是 Accepted for implementation / Pending，只有对应代码、测试与运行证据存在后才能勾选目标项。

## 1. PR 合并前

| 检查项 | 必须满足 |
| --- | --- |
| 范围 | PR 对应明确 Issue，不混入无关重构 |
| 当前/目标 | 文档和 PR 明确 Current、Target、Pending，不宣传未实现架构 |
| 验证 | PR 列出命令、结果和未执行原因 |
| 契约 | API、Data、Workflow、Version、UI 或安全变化同步对应文档 |
| 安全 | 无 `.env`、Key、Token、连接串、论文凭据、session/share token 或敏感日志 |
| 包管理 | 只有 pnpm / uv；无额外 lockfile，frozen/locked 检查通过 |
| 科研可信 | Fixture、Live、Cached、Revised 准确；Summary/Relation/GraphEdge 证据完整 |
| 口径 | 主案例范围清楚，不宣传任意方向、任意 PDF 或无证据发现 |
| CI | 适用 build、test、contract、architecture、a11y、visual、Compose 卡口通过 |

## 2. 目标前端架构

- `apps/site` 只承载静态品牌站和按需 Island，不持有完整 Workspace 状态。
- `apps/workspace` 承载 Guided Tour 与 Workspace，不直连外部来源或模型。
- `packages/domain` 不依赖 React、Astro、HTTP 或平台 API。
- `packages/ui` 和 `packages/visual-engine` 不调用 Repository / fetch。
- `packages/data-access` 经 contracts 校验 DTO，再映射 Domain。
- Feature 不跨包深层导入，不维护第二套路由、server state 或 UI framework。
- 旧 `apps/web` 迁移期只做阻塞性修复，不与 React 双写业务。
- `apps/desktop` 未经独立 Issue 不创建；Tauri API 只通过 Platform Adapter。

## 3. Brand Site 与 Guided Tour

- 静态 HTML 含中文主标题、产品说明、主 CTA 和可信性入口。
- SIGNAL / QUESTION / EVIDENCE / WORKSPACE 四幕完整，约 60–90 秒。
- 可暂停、返回和跳过，不强制滚动劫持。
- WebGL、字体或 JavaScript 未加载时仍有完整首屏和导航。
- Demo Replay 明确标记 Fixture；切换 Live 前说明等待、失败、重试和缓存。
- title、description、canonical、Open Graph、社交预览和基础结构化数据正确。
- 无明显 CLS；首屏和主要动作键盘可用。
- 移动端使用简化场景或 Poster 仍保留核心内容。

## 4. Research Workspace

- Top Rail、Research Atlas、Research Canvas、Provenance Observatory、Research Console 职责清楚。
- 中央默认显示科研产物，不是聊天气泡、工具日志、IDE 或 terminal。
- Canvas 最多三个受控面板；不同 Project 的布局不会互相污染。
- `1440×900`、`1920×1080` 完整，`1280px` 可完成主流程。
- Research Console 不遮挡核心产物，提交前显示上下文与影响范围。
- 从关键字段、结论、Relation 或 GraphEdge 三次交互内定位 Evidence。
- Project、Run、Artifact、Version、WorkspaceSnapshot、ShareSnapshot 不混淆。
- 无鼠标可确认 Contract、切换产物、打开 Evidence、取消/重试和分享。
- empty/loading/partial/success/failed/fixture/cached/revised 状态完整。

## 5. Design Token、UI 与字体

- Raw Color 只在 design-tokens；组件使用 canvas/surface/ink/border/brand/status/visual 语义 Token。
- 状态颜色可区分，并同时提供文字或图标。
- 不使用黑底星空、霓虹蓝紫、强发光、大面积渐变、玻璃拟态或大圆角 Card 墙。
- 不把所有内容塞入 Card；高密度区域用层级、分隔和虚拟化。
- 字体版本、来源、SIL OFL 许可证、中文覆盖、Web subset 与 Tauri 离线策略有记录。
- 200% 字体缩放、焦点、对比度、触控目标和读屏标签通过。
- 未净化外部 HTML 不进入 DOM；React 默认转义不被绕过。

## 6. Visual Engine

- ASCII / Dither 使用 GPU atlas / instancing，不创建大量 DOM glyph。
- Visual Model 映射显式可测试，不反向成为科研事实来源。
- High / Medium / Low 考虑 WebGL、GPU、DPR、viewport、frame time、Reduced Motion 和 visibility。
- deterministic seed、冻结时间和固定 viewport 可用于视觉回归。
- 页面隐藏暂停；卸载 dispose geometry、material、texture、render target。
- WebGL/context loss 自动 Poster；Canvas 不承载唯一信息。
- Reduced Motion 取消滚动相机和粒子形变，但不隐藏状态。

## 7. Contract 与 Adapter

- `/api/v2` 资源和字段符合 API_CONTRACT / DATA_MODEL；v1 未被静默破坏。
- Pydantic 生成 OpenAPI / JSON Schema；generated Transport Type 无 stale diff。
- 组件不读取原始 DTO、不拼 URL、不直接 fetch。
- Fixture / HTTP Adapter 通过同一 Contract 和 Domain 一致性测试。
- `execution_mode` 与 `source_mode` 分离；Fixture 不能标记 Cached。
- 集合 cursor、错误 Problem Details、Idempotency-Key、版本冲突和 request_id 一致。
- Run Snapshot / Event 恢复、cancel、retry、revision、fork 语义有测试。

## 8. Session、Share 与输入安全

- 匿名 Session 使用 Secure、HttpOnly、SameSite Cookie；写操作验证 CSRF。
- 服务端按 session ownership 检查 Project / Run / Artifact，跨会话不能枚举或读取。
- Session、Run、Share、Feedback 和导出限流并有配额错误。
- Share token 高熵、只存 hash、可撤销/过期，ShareSnapshot 锁定版本而非 latest。
- 分享内容执行最小范围和脱敏，不含密钥、内部错误、受限全文或私有输入。
- Research Contract、Feedback、URL 和导出参数有 Schema、长度和 allowlist 校验。
- CSP、HSTS、MIME sniffing、Referrer Policy、Permissions Policy 与 CORS allowlist 正确。

## 9. 数据、论文、推理与图谱

- 数据字段有名称、单位、转换、SourceSnapshot、质量和 Evidence。
- 论文检索参数、来源、时间、去重、排序、入选/排除依据可复现。
- Seed 只作 benchmark、Fixture 或人工校验，不冒充自动获取。
- PaperSummary 的核心 finding / limitation 绑定 Evidence。
- Claim、候选 Relation、Accepted Relation 分离；Accepted Relation 有条件、Evidence 和 Trace。
- ReasoningTrace 只保存显式可审查依据，不保存 chain-of-thought。
- 每条 GraphEdge 有 Evidence；跨文献边有 Relation / ReasoningTrace。
- 图谱规模受控，不为装饰创建节点或边。

## 10. 版本、缓存和反馈

- ArtifactVersion 内容不可变，latest、supersedes、content hash 可回溯。
- CacheRecord 指向真实 origin Run、Version、SourceSnapshot 和 input hash。
- Live 失败与缓存选择原因同时保留；缓存不满足 Contract 时明确失败。
- Feedback 定位 object id + ArtifactVersion；RevisionPlan 展示影响范围。
- Revision 创建派生 Run 和新版本，旧版本保留；冲突不静默覆盖。
- Share、Export 和 Evidence 固定引用 Version id，不引用动态 latest。

## 11. 当前 Docker、后端与 CI

- 未进入迁移 Issue 时，`docker compose config` 和当前 `web/api/postgres` 命令保持有效。
- 当前 web 使用 Node 24 / pnpm，api 使用 Python 3.13 / uv，postgres 使用 17。
- `/api/v1/health`、当前后端测试和 foundation check 通过。
- 目标前端建立后，CI 增加 lint、typecheck、test、build、E2E smoke、visual smoke、architecture/token checks。
- 不引入无 ADR 的 Redis、Celery、MinIO、Nginx、RabbitMQ、Neo4j 或向量数据库。

## 12. 作品提交前

按 `START HERE -> 60–90 秒短片 -> 公网首页 Guided Tour -> Workspace -> PDF -> 源码/API/测试` 自主走读。

- 视频、网页、截图、Fixture version、真实 Run 和文档口径一致。
- 公网首页、Tour、Workspace、Share 可访问，错误和缓存兜底可演示。
- CSV、字段字典、溯源报告、论文候选、关系 JSON 和 Graph 可下载或核验。
- 页面无错位、空白占位、未标来源数据、密钥或调试堆栈。
- 未实现能力标记 Proposed / Pending，不依赖现场讲解才能理解。

## 13. 文档审查

- README 是否区分当前实现与目标架构。
- PRD / DESIGN / VISUAL / WORKSPACE / FRONTEND_ARCHITECTURE 是否分工清楚且不大段复制。
- API / DATA_MODEL / WORKFLOW / VERSION / MODULES 是否字段和语义一致。
- ROADMAP / BACKLOG / A-01～A-10 Issue 是否使用目标技术和依赖。
- `docs/setup.md` 是否仍准确描述当前命令，没有把目标命令写成已可运行。
- Markdown 链接、标题层级、表格、Mermaid 与 `git diff --check` 是否通过。
