# Competition Compliance

| 元数据 | 值 |
| --- | --- |
| Authority | 竞赛方向、模型资格、差异化叙事与提交证据 |

## 1. 固定方向

产品固定参加 Track 2 / Direction 1 / A：科学数据查询、解析与整合。主叙事围绕可复核的科学数据纵向链，而不是通用聊天、通用 OCR、通用多 Agent 或 Reference 项目集合。

```text
confirmed Contract
→ multi-source acquisition
→ parsing / cleaning / alignment / annotation
→ scientific analysis
→ typed ArtifactVersion
→ Evidence / SourceSnapshot / provenance
→ human review / revision
```

## 2. 合格模型

参赛主案例的合格模型必须是 Qwen，并通过 Alibaba Cloud Model Studio / Bailian 或比赛官网明确认可的路径调用。提交证据不得使用浮动 latest。

合格调用必须能够复核：provider 与官方接入路径、model name/version/revision、Prompt name/version/hash、Contract/input hash、参数、调用时间与运行环境、脱敏 request/call proof、response/output hash、Schema/Evidence admission、ProducerExecution 与最终 ArtifactVersion。

API Key、原始认证头、完整 provider 原始响应与模型私有 chain-of-thought 不进入提交材料、公开 Artifact 或日志；只保留完成复核所需的脱敏事实。

DeepSeek、Gemini 或其他模型只可用于 benchmark、消融或 reference，不得包装为合格 Qwen 主模型。

## 3. Reference 项目的角色

AutoAstro、MAVIS、inosum 等 Reference 可以贡献算法、工具、交互机制、benchmark 和工程经验，但：

- Reference 的模型调用记录不等于 Xingwen 的合格调用；
- Reference benchmark 数字不等于 Xingwen 当前性能；
- Reference 的公开论文或 demo 不等于 Xingwen 的真实运行证据；
- 引入源码必须遵守许可证、attribution 与 provenance；
- 提交材料不能把“集成多个开源项目”本身包装成技术差异化。

真正的作品差异化来自 Xingwen 将多源天文数据、科学文档、文献推理、Evidence Graph、Scientific Skills、版本化 Artifact、Revision 与成熟 Agent Workspace 收敛为一条可复核链。

## 4. 真实性等级

Live、Cached、Recorded、Fixture、Benchmark 与 Revision 必须清楚区分。只有 Xingwen 的真实 Run、真实合格模型调用、真实 ArtifactVersion/Evidence 才能作为主案例能力证明。

任何 partial、unsupported、provider failure、source failure 或 parser degradation 都按真实结果展示，不能为了演示完整性改写为成功。

## 5. 提交材料

最终材料至少包含：

- 主案例与赛道声明；
- 固定代码 Commit / container image / environment manifest；
- 合格 Qwen provider/model/revision 与脱敏调用证明；
- Research Intent → Contract → Run → ArtifactVersion → Evidence → Revision/Export/Share 的纵向链；
- Scientific Document / data integration / literature-reasoning / graph 的关键证据；
- benchmark 方法、固定输入、指标和限制；
- Reference license/attribution 与自有改造说明；
- failure/degradation 示例；
- 可复现命令与稳定入口；
- secrets、私有 reasoning 与个人数据的脱敏说明。

无法复核 provider/model/revision/call proof 或无法回到 Evidence/provenance 的结论必须标为未证实，不能进入完成性宣传。
