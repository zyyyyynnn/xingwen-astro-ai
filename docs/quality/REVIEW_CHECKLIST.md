# Review Checklist

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 单个 Pull Request 的正式技术 Review 与合并清单 |

本清单由正式技术 Review 使用，回答“这个 PR 是否可以合并”。里程碑与阶段退出由 [Acceptance](../product/ACCEPTANCE.md) 校验。

## 1. 范围

- [ ] PR 对应单一 Task / Bug 或明确的用户授权，无非相关变更。
- [ ] 当前 PR 是唯一有效 Open PR，无冲突或重复拉取。
- [ ] 变动仅包含达成单一目标必需的修改，未夹带无关重构或格式化。
- [ ] PR title 与分支 Commit subject 符合 [Contributing §1](../../CONTRIBUTING.md#1-分支与提交) 的唯一 Title Grammar。

## 2. 正确性

- [ ] 逻辑符合业务预期，正常路径与边界条件处理正确。
- [ ] 错误分类明确，没有静默吞掉异常或返回伪造兜底数据。
- [ ] 无代码死循环、资源泄露、内存溢出或并发冲突风险。

## 3. 架构与契约

- [ ] 遵循单向依赖与模块边界，未跨越 Repository / Domain / Workflow 偷跑。
- [ ] 接口变更通过 Pydantic / OpenAPI 导出生成，非手写重复 DTO。
- [ ] 前端组件经由 Repository Port 消费 Domain，未直连外部 API 或解析 Raw DTO。

## 4. 科研可信

- [ ] 数据等级准确标明为 Live、Fixture 或 Cached，未伪造数据真实性。
- [ ] PaperSummary 核心内容与 Accepted Relation 逐项绑定 Evidence。
- [ ] ReasoningTrace 只保存可审查依据，未泄露模型私有 chain-of-thought。
- [ ] 结果修订创建新 ArtifactVersion，未原地覆盖历史版本。

## 5. 安全

- [ ] 源码、配置与日志中无 API Key、密码、Token 或敏感 Secrets。
- [ ] 输入数据在入库、渲染或发往外部前经由 Schema 与安全净化。
- [ ] 敏感资源受 Session ownership 与权限保护，未暴露枚举接口。

## 6. 测试

- [ ] 单元测试、集成测试或 E2E 测试按变更范围成功通过。
- [ ] 未通过降低测试断言或删除既有测试掩盖缺陷。
- [ ] 测试数据等级表达清晰，命令可在标准环境中复现。

## 7. 文档

- [ ] 契约、实体、工作流或 UI 规则变更已同步对应的唯一 Authority。
- [ ] 活跃规范保持简练，未引入具体 Task 编号、个人路径或过程历史。
- [ ] 新增或移动文件已同步 [docs/README.md](../README.md) 索引。

## 8. 合并条件

- [ ] 相关自动化 CI 检查全部成功通过。
- [ ] 代码与目标分支元数据无漂移，无阻塞审查意见。
- [ ] PR 描述真实反映变动内容与验证结果，满足 Squash merge 条件。
