# Handoff Guide

本目录用于开发组向总负责人/材料组交接真实技术素材。开发组不负责 Word、PPT、视频成片制作，但必须提供可引用、可复现、不过度宣传的技术材料。

默认提交接触顺序固定为：

```text
START HERE
-> 60–90 秒品牌短片
-> 公网首页 Guided Tour
-> Research Workspace
-> 技术方案 PDF
-> 源码 / API / 测试 / 复现材料
```

该顺序首先服务作品提交和自主阅读，也支持可能的终审现场展示；任何环节不得依赖口头讲解才能分清 Fixture、Live、Cached 来源与派生修订关系。

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
| 版本与来源清单 | execution mode、source mode、Project/Run/ArtifactVersion、Fixture scenario | `provenance-manifest.md` |
| START HERE | 短片、Web、PDF、源码/API/测试的一页入口 | `START-HERE.md` |
| 技术说明 | 架构图、模块说明、数据来源和论文来源说明 | `technical-notes.md` |

## 2. 素材要求

- 必须来自真实系统运行、明确标注的真实运行缓存，或明确标注的版本化 Demo Fixture。
- Fixture 必须写明 scenario、schema version、生成说明，不得标记为 Cached。
- Cached 必须能定位 origin Run、ArtifactVersion、SourceSnapshot 和时间。
- 截图中不能出现 API Key、数据库密码、内部 Token 或论文源凭据。
- 未实现能力只能写为“规划/预留/后续扩展”。
- 数据来源必须可追踪到 URL、查询参数或文献记录。
- 论文获取素材必须包含检索参数、来源、获取时间、去重规则和缓存状态。
- 跨文献推理素材必须包含 Claim、Relation、ReasoningTrace 和 Evidence。
- 演示步骤必须可复现。

## 3. 推荐交接节奏

| 阶段 | 交接物 |
| --- | --- |
| M1 开发基线 | 明确标注 Fixture 的 Demo Replay、API 初版说明、本地启动和前端目标架构状态 |
| M2 核心功能 | 数据结果截图、CSV、字段字典、溯源报告、论文获取截图、PaperCandidate JSON、文献总结截图、PaperSummary JSON、跨文献推理截图、ReasoningTrace JSON、图谱截图、Graph JSON、证据详情 |
| M3 反馈与交付 | 公网 Demo URL、完整演示脚本、反馈修正截图、缓存兜底验证、最终截图包 |

## 4. 禁止事项

- 不交付手写假数据冒充系统输出。
- 不把 Fixture、Demo Replay 或 seed list 冒充 Live / Cached。
- 不把 seed list 冒充自动论文获取结果。
- 不把模型推断写成已验证科研结论。
- 不把无证据跨文献关系写成最终结论。
- 不在截图、文档、视频素材中暴露密钥。
- 不承诺任意科研问题、任意 PDF、任意图表全自动处理或无边界科学发现。
