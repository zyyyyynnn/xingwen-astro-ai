# Coding Standard

## 1. 通用原则

- 代码只实现当前 Issue 的明确范围。
- 依赖方向遵守 `MODULES.md`，禁止跨层捷径。
- 外部输入、模型输出和缓存内容都视为不可信输入。
- 核心业务对象使用稳定 ID、明确枚举和 UTC 时间。
- 未实现能力使用 TODO/规划说明，不提供伪实现结果。

## 2. Python / FastAPI

- Python 3.13，类型注解覆盖公开函数与协议。
- Pydantic v2 负责 API/模型边界校验。
- Router 只做请求解析、调用 application service、返回响应。
- 任务编排放在 `app.workflow`；Pipeline 业务逻辑放在 `services/*`。
- 数据访问集中在 repository/adapter，不在 Router 中散落 SQL。
- 捕获异常时保留 cause，公开错误不泄露内部信息。
- 异步函数只用于真实异步 I/O，不为形式全部 async。
- 新状态转换必须修改状态机测试和契约文档。

## 3. Vue / TypeScript

- 使用 Composition API 与严格 TypeScript。
- API 类型由共享契约/OpenAPI 生成或集中维护，不在组件重复声明。
- 页面组件不直接调用外部论文源、数据源或模型。
- 加载、成功、失败、空、缓存状态必须可区分。
- 图谱和表格优先可读性、可追踪性，不以动效掩盖证据不足。
- 依赖只通过 pnpm，禁止额外 lockfile。

## 4. Pipeline

- 输入输出均通过 Schema。
- 每个外部请求记录来源、参数、时间、超时和错误分类。
- 清洗规则、Prompt、图谱规则必须有版本标识。
- 不返回无法定位来源的关键值。
- 真实运行缓存与 seed fixtures 分开存放、分开标识。

## 5. 文件与命名

- 文档与代码使用 UTF-8。
- Python 模块/函数使用 snake_case，类使用 PascalCase。
- Issue/任务编号出现在 PR，而不是大量写入业务代码。
- Prompt 文件使用 `<name>/vN.md`。
- 样例文件名体现 case、版本和 `fixture` / `cached` 来源，二者不得混用。

## 6. Review 最低项

- 是否越过模块边界；
- 是否新增第二套 Schema；
- 是否存在未验证模型文本；
- 是否遗漏 Evidence；
- 是否可能记录密钥；
- 是否有可复现测试；
- 是否同步相关契约和风险文档。
