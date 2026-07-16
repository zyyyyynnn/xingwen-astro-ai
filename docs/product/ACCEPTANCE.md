# Acceptance Criteria

> Current runtime：Vue `apps/web` + FastAPI `/api/v1`。Target runtime：Astro + React Monorepo + `/api/v2`。目标前端验收为 Accepted for implementation / Pending，不能用文档通过代替代码和运行证据。

## 1. MVP 总验收

| 编号 | 标准 | 必须证明 |
| --- | --- | --- |
| G-01 | 公网 Web 可访问且无人讲解可理解 | URL、静态首屏、Guided Tour 与主入口 |
| G-02 | 主案例形成连续产物链 | Contract、Run、Dataset、Paper、Summary、Relation、Graph、Evidence、Export |
| G-03 | Demo Replay 与 Live Run 可区分 | execution/source mode 截图、状态测试、Fixture provenance |
| G-04 | 真实数据和论文获取可复现 | Query、来源、时间、去重、排序、SourceSnapshot |
| G-05 | 推理与图谱可审查 | Claim、Relation、ReasoningTrace、GraphEdge 与 Evidence |
| G-06 | Project / Run / Artifact / Version 可定位 | 聚合接口、版本链、派生 Run 和历史对照 |
| G-07 | 失败、缓存和修订不失真 | Live 失败、真实缓存来源、Feedback、RevisionPlan、新版本 |
| G-08 | 分享与导出安全 | 冻结 ShareSnapshot、撤销/过期、脱敏、CSV/JSON/报告 |
| G-09 | WebGL 和设备降级 | Poster、Reduced Motion、High/Medium/Low、移动端 |
| G-10 | 本地和 CI 可复现 | frozen install、build、test、Compose、Contract 与架构门禁 |

## 2. 首页与 Guided Tour

| 项目 | 标准 |
| --- | --- |
| 静态首屏 | HTML 中存在中文主标题、说明、主 CTA 和可信性入口；WebGL 不是 LCP 前置条件 |
| 四幕 | SIGNAL、QUESTION、EVIDENCE、WORKSPACE 顺序完整，总时长约 60–90 秒 |
| 控制 | 可暂停、返回、跳过，不做强制滚动劫持 |
| Research Contract | ACT 02 可编辑目标、对象、字段、来源、论文、输出、证据和质量约束 |
| 来源语义 | Demo Replay 显示 Fixture；Live Run 说明等待、失败、重试和真实缓存 |
| SEO | 静态 title、description、canonical、Open Graph 与社交预览可检查 |
| 稳定性 | 无 WebGL 时完整静态首屏，无明显 CLS，首个主动作可键盘操作 |
| 移动端 | 可使用 Poster 或简化场景，但四幕核心信息和入口完整 |

## 3. Research Workspace

| 项目 | 标准 |
| --- | --- |
| 布局 | Top Rail、Research Atlas、Research Canvas、Provenance Observatory、Research Console |
| 科研产物优先 | 中央默认不是聊天流，不用工具日志或 IDE 模型组织产品 |
| 视口 | `1440×900`、`1920×1080` 完整；`1280px` 宽仍可完成主流程 |
| Canvas | 最多三个受控拆分面板，不提供无限悬浮窗口 |
| 对照 | 数据+来源、Summary+Evidence、Relation+Trace+Evidence、Graph+Evidence 可组合 |
| Observatory | 当前对象、source mode、locator、quote/value、confidence、query hash、版本可见 |
| Console | 不遮挡核心产物；提交前显示 Project、Run、选中对象和影响范围 |
| 多项目/Run | Project、并行 Run、Artifact、Version 明确，不用聊天线程替代 |
| 恢复与分享 | WorkspaceSnapshot 可恢复；ShareSnapshot 冻结版本且只读 |
| 键盘 | 无鼠标可确认 Contract、切换产物、定位 Evidence、取消/重试和打开帮助 |
| 状态 | empty、loading、partial、success、failed、fixture、cached、revised 完整 |

## 4. Visual Engine 与设计系统

| 项目 | 标准 |
| --- | --- |
| Token | OKLCH Raw Scale 与语义 Token；业务组件无散落 Raw Color |
| 字体 | 衬线/无衬线/等宽层级；许可证、来源、中文覆盖、Web/Tauri 策略有记录 |
| 品牌 | ASCII 字符与 Dither 近看可辨、远看连续；不是满屏滤镜 |
| 渲染 | GPU glyph atlas / instancing，不用大量 DOM glyph |
| 档位 | High、Medium、Low 根据 WebGL、GPU、DPR、viewport、frame time、Reduced Motion 决定 |
| 生命周期 | 页面隐藏暂停；卸载 dispose geometry/material/texture/render target |
| 可复现 | deterministic seed，可冻结时间和 viewport 做视觉回归 |
| 降级 | Context loss / 无 GPU 自动 Poster；DOM 内容和操作保持完整 |
| 可访问 | 状态不只靠颜色，200% 字体缩放、焦点、读屏和 Reduced Motion 通过 |

## 5. Contract、Adapter 与来源状态

- `/api/v2` 明确 Project、Contract、Run、Event、ArtifactVersion、Evidence、WorkspaceSnapshot、ShareSnapshot。
- Fixture / HTTP Adapter 校验同一 Transport Schema 并返回同一 Domain Model。
- `execution_mode=demo_replay|live` 与 `source_mode=fixture|live|cached|revised` 分离。
- Fixture 版本化并带 scenario、schema version、provenance note；不能标记 Cached。
- Cached 绑定真实历史 Run、ArtifactVersion、SourceSnapshot、时间、input hash 和本次失败。
- 页面和组件不读取原始 DTO、不在组件内 fetch、不拼接裸 API URL。
- Collection cursor、错误 Problem Details、幂等、取消、重试、派生和版本冲突有 Contract 测试。

## 6. A 系列工作区验收

| Issue | 最低产物 |
| --- | --- |
| A-01 | pnpm Monorepo、Astro/React 空基线、strict TS、共享 packages、build/test/CI 目标、旧 Vue 迁移策略 |
| A-02 | 品牌字标、Token、字体、UI primitive、Visual Engine 基础、四幕框架、Workspace Shell、fallback |
| A-03 | Research Contract、Guided Tour、Project/Run、Repository Port、Fixture/HTTP、Atlas/Canvas/Observatory/Console、分享入口 |
| A-04 | 虚拟化数据表、字段字典、来源、质量、对照、CSV/JSON、Evidence 和完整状态 |
| A-05 | Query、来源、Candidate、去重、排序、选择依据、Demo/Live/Cached 与 Evidence |
| A-06 | 目标、方法、数据、结论、局限、跨文献对照、Evidence locator/quote/value |
| A-07 | Claim、候选/最终 Relation、Trace、条件、Evidence、最多三面板 |
| A-08 | React Flow 证据图谱、Observatory 联动、规模控制、无装饰性节点/边 |
| A-09 | Live/Cached/Fixture/Revised、version、retrieved_at、SourceSnapshot 与质量状态统一 |
| A-10 | Field/Source/Paper/Claim/Relation/Trace/GraphEdge 反馈、新 ArtifactVersion 和冲突状态 |

## 7. B 后端与安全验收

- 当前 `/api/v1` 在迁移门禁前保持可用；v2 不以修改 v1 响应伪装实现。
- FastAPI / Pydantic 生成 OpenAPI 3.1 / JSON Schema；`packages/contracts` 生成类型无漂移。
- PostgreSQL 是 Run、Step、Event、ArtifactVersion、Evidence 与 Share 的事实来源。
- 匿名 Session 使用 Secure/HttpOnly/SameSite Cookie、CSRF、ownership、配额和限流。
- Share token 高熵、只存 hash、可撤销/过期、最小范围、无法写入或跨 Project 扩权。
- 错误不暴露密钥、堆栈、连接串、受限全文或模型私有推理。
- Cancel、自动 retry、用户 retry、revision、fork 和 CacheSelector 有集成测试。

## 8. C / D 科研可信验收

- 至少一个主数据源真实可运行；字段、单位、转换、来源和质量可复现。
- 论文候选带 Query、来源、时间、去重、排序和入选/排除依据。
- PaperSummary 核心内容绑定 Evidence；不把模型总结当无条件事实。
- Accepted Relation 绑定 Evidence、条件和 ReasoningTrace，候选与最终分离。
- 每条 GraphEdge 绑定 Evidence；跨文献边绑定 Relation / Trace。
- ReasoningTrace 只含显式可审查依据，不保存 chain-of-thought。

## 9. 测试与治理门禁

目标实现至少覆盖：Token、Contract、Fixture/HTTP 一致性、Domain Mapper、组件、E2E、a11y、visual regression、WebGL fallback、Reduced Motion、Demo/Live/Cached/Revised、Graph Evidence、Session/Share 安全。

文档 PR 至少执行 `git diff --check`、`python scripts/check_foundation.py`、Markdown 链接/标题/Mermaid 结构检查（工具存在时），并证明未修改禁止范围。

## 10. 一票否决项

- 公网入口无法使用或只有 WebGL Canvas 没有静态内容。
- Fixture、seed 或手写数据冒充 Live / Cached。
- 数据、论文、Summary、Relation 或 GraphEdge 无法追溯 Evidence。
- 分享 token 泄露编辑会话、无法撤销、动态指向 latest 或暴露受限内容。
- 前端直连模型/外部来源、暴露密钥或渲染未经净化的外部 HTML。
- 保存或展示模型私有 chain-of-thought。
- 工作台以聊天流、IDE 或工具日志为核心，科研产物退居次要。
- WebGL 失败导致首页或工作台不可用。
- API / Data Model / Workflow / Issue 与实现明显不一致。
- 宣传任意天文方向、任意 PDF、任意图表或无证据科学发现已经实现。
