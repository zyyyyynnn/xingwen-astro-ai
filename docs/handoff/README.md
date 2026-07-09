# Handoff Guide

本目录用于开发组向总负责人/材料组交接真实技术素材。开发组不负责 Word、PPT、视频成片制作，但必须提供可引用、可复现、不过度宣传的技术材料。

## 1. 交接内容

| 类型 | 内容 | 文件建议 |
| --- | --- | --- |
| 页面截图 | 首页、任务流程、数据结果、论文获取、文献总结、跨文献推理、学术图谱、反馈修正 | `screenshots/*.png` |
| 导出结果 | CSV、数据字典、溯源报告、论文候选、推理关系 JSON | `exports/*` |
| 论文获取样例 | PaperSearchQuery、PaperAcquisitionRun、PaperCandidate | `papers/*` |
| 推理样例 | LiteratureClaim、LiteratureRelation、ReasoningTrace | `reasoning/*` |
| 图谱样例 | Graph JSON、节点详情、证据详情 | `graph/*` |
| 接口说明 | 核心 API 请求和响应 | `api-examples/*.json` |
| 演示说明 | 固定输入、演示步骤、失败兜底说明 | `demo-script.md` |
| 技术说明 | 架构图、模块说明、数据来源和论文来源说明 | `technical-notes.md` |

## 2. 素材要求

- 必须来自真实系统运行或明确标注的真实运行缓存。
- 截图中不能出现 API Key、数据库密码、内部 Token 或论文源凭据。
- 未实现能力只能写为“规划/预留/后续扩展”。
- 数据来源必须可追踪到 URL、查询参数或文献记录。
- 论文获取素材必须包含检索参数、来源、获取时间、去重规则和缓存状态。
- 跨文献推理素材必须包含 Claim、Relation、ReasoningTrace 和 Evidence。
- 演示步骤必须可复现。

## 3. 推荐交接节奏

| 阶段 | 交接物 |
| --- | --- |
| M1 | Mock 工作流截图、API 初版说明 |
| M2 | 数据结果截图、CSV、字段字典、溯源报告 |
| M3 | 论文获取截图、PaperCandidate JSON、文献总结截图、PaperSummary JSON |
| M4 | 跨文献推理截图、ReasoningTrace JSON、图谱截图、Graph JSON、证据详情 |
| M5 | 公网 Demo URL、完整演示脚本、最终截图包 |

## 4. 禁止事项

- 不交付手写假数据冒充系统输出。
- 不把 seed list 冒充自动论文获取结果。
- 不把模型推断写成已验证科研结论。
- 不把无证据跨文献关系写成最终结论。
- 不在截图、文档、视频素材中暴露密钥。
- 不承诺任意科研问题、任意 PDF、任意图表全自动处理或无边界科学发现。
