# Coding Standard

| 元数据 | 值 |
| --- | --- |
| Authority | 代码组织、命名、类型、安全输入与实现纪律 |

## 1. 实现原则

- 只实现当前授权范围；不夹带无关重构、格式化、依赖升级或“顺手清理”。
- 修改前先查现有 owner 与同类实现。优先 reuse、absorb、consolidate、delete，再新增抽象。
- 当前架构优先，不保留旧 API/schema/renderer/store/runtime 的双轨兼容，除非真实外部兼容要求明确授权。
- 不为假设的未来需求建立 generic registry、strategy/planner framework、audit subsystem、compatibility layer 或 hash system。
- 生产代码只保留一个事实 owner；新增或迁入能力必须进入现有 owner，而不是创建 parallel subsystem。

## 2. Backend / Python

- 公开函数、协议、领域模型具备完整静态类型；核心持久化实体使用仓库既有稳定 ID 规则，时间使用带时区 UTC。
- Pydantic v2 是 Transport Schema 与生成 Contract 的编写源；生成 DTO/Schema 不手写复制。
- Router 只负责 request/auth/application mapping；Application Service 管用例与事务；Workflow 管 Run/Step/Attempt/Event；Pipeline/Scientific Skill 管算法；Publisher 是正式 ArtifactVersion/Evidence 发布唯一入口。
- Repository/Adapter 集中数据访问；Router/Pipeline 不散落 raw SQL。
- 外部 API、模型响应、文件与 cache 都是不可信输入，先 schema/admission 再成为科研事实。
- 异常分类稳定；保留原始 cause，不吞异常后返回空结果或伪成功；公开错误统一映射到当前 Problem Details 边界。
- Schema / persistence 变更同步当前 SQLAlchemy/PostgreSQL 不变量，并提供失败退出与恢复路径。
- provider side effect 若可在调用前判定为非法，应在调用前失败。

## 3. Frontend / TypeScript

- Strict TypeScript；禁止 `any`、不安全断言和 `@ts-expect-error` 逃逸掩盖契约。
- Transport DTO 先校验再映射到 Domain；Page/Feature 不直接 `fetch` 或解析 raw DTO。
- `@xingwen/domain` 不依赖 React/DOM/HTTP；依赖只通过 package public exports。
- `@xingwen/ui` 是通用 primitive 入口；已采用的成熟交互、图表和图布局能力优先于手写基础机制。
- 新改业务 UI 的 spacing、dimension、typography、line-height、radius、border、shadow、z-index、breakpoint、density、panel geometry、motion 使用 semantic tokens/component variants；原始数值只在 token/base UI 定义或科学数据本身出现。
- Unknown Artifact kind fail closed 到统一 user-safe fallback；不显示 raw JSON dump。

## 4. Scientific Data / Version / Evidence

- ArtifactVersion immutable；Share/Export/Revision 绑定明确版本，不动态 latest。
- SourceSnapshot 与 Evidence locator 是科研审计事实，不当作可丢弃 metadata。
- accepted scientific facts 必须满足 Evidence/admission；candidate 与 accepted 明确区分。
- revision 使用 confirmed RevisionPlan 与 derived Run，旧版本保留。
- Live/Fixture/Recorded/Benchmark/Cached 数据语义不混用。
- SHA-256 只用于真实 content addressing、immutability、provenance、security/idempotency 等必要边界；不创建重复审计 hash。

## 5. 外部能力与源码

- 外部能力进入生产前必须映射到当前 owner、领域语义、错误语义、Evidence、Version 和 UX。
- 源码级采用必须确认许可证并保留必要法律归因；精确来源、revision 与 attribution 保存于法律文件或机器 provenance，不复制到治理 Markdown。
- 许可证不明确时只能进行行为、算法、协议或 benchmark 层面的分析，不把“可读取源码”当作复制授权。
- 不保留外部绝对路径、临时目录、凭据、硬编码环境、实验 UI 或外部 runtime 作为长期生产依赖。

## 6. 命名

- Python module/function：`snake_case`；class：`PascalCase`。
- TypeScript component/type：`PascalCase`；function/variable：`camelCase`。
- API JSON 字段：`snake_case`。
- 生产命名使用领域事实，不使用能力来源名称、工作阶段、batch、Review、临时状态或个人路径。
- 一字母紧跟整数的内部版本/阶段简写禁止用于代码、测试、fixture、文档、Prompt、Commit、Issue、PR、Review。真实外部版本、科学版本和严重级别具有本身语义时除外。

## 7. 清洁度

Touched area 收口前删除：dead code、duplicate component/path、obsolete alias、debug output、unused fixture、temporary bridge、stale generated contract、无生产 consumer 的 UI primitive。不要为了“代码整洁”扩散到未触达模块的大范围重构。
