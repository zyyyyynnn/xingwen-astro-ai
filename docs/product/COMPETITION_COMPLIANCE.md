# Competition Compliance

| 元数据 | 值 |
| --- | --- |
| Authority | 竞赛方向、模型资格、差异化叙事与提交证据 |

## 1. 固定方向

产品固定参加 Track 2 / Direction 1 / A：科学数据查询、解析与整合。主叙事围绕可复核的科学数据纵向链，而不是通用聊天、通用 OCR、通用多 Agent 或外部能力集合。

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

参赛主案例的合格模型必须是 Qwen，并通过 Alibaba Cloud Model Studio / Bailian 或比赛官网明确认可的路径调用。模型由服务端运行环境显式选择，记录 requested model 与 provider 返回的真实模型身份。显式 revision 可选，提供时与声明的模型身份一致；浮动别名的 revision 为 null，其可复现边界以当次调用事实为准。

合格调用必须能够复核：provider 与官方接入路径、model name/version/revision、Prompt name/version/hash、Contract/input hash、参数、调用时间与运行环境、脱敏 request/call proof、response/output hash、Schema/Evidence admission、ProducerExecution 与最终 ArtifactVersion。

API Key、原始认证头、完整 provider 原始响应与模型私有 chain-of-thought 不进入提交材料、公开 Artifact 或日志；只保留完成复核所需的脱敏事实。

其他模型只可用于 benchmark、消融或对照，不得包装为合格主模型。

## 3. 差异化与能力归属

外部算法、工具、交互机制、benchmark 或工程经验只能作为研发输入：

- 外部调用记录不等于本项目的合格调用；
- 外部 benchmark 数字不等于当前产品性能；
- 外部 demo 不等于真实运行证据；
- 源码采用必须遵守许可证、attribution 与 provenance；
- 提交材料不以“整合了多少外部项目”作为技术差异化。

模型、算法或方法之间的性能比较只有在同一 frozen Contract/input、相同 Evidence/ground truth、相同指标定义和可比运行条件下才可形成横向结论；否则只能作为背景或探索性参考，不进入性能宣传。

作品差异化来自星文智析将多源天文数据、科学文档、文献推理、Evidence Graph、Scientific Skills、版本化 Artifact、Revision 与 Agent Workspace 收敛为一条可复核链。

## 4. 真实性等级

Live、Cached、Recorded、Fixture、Benchmark 与 Revision 必须清楚区分。只有本项目的真实 Run、真实合格模型调用、真实 ArtifactVersion/Evidence 才能作为主案例能力证明。

任何 partial、unsupported、provider failure、source failure 或 parser degradation 都按真实结果展示，不能为了演示完整性改写为成功。

## 5. 提交材料

最终材料至少包含：

- 主案例与赛道声明；
- 固定代码 Commit / container image / environment manifest；
- 合格模型 provider/model/revision 与脱敏调用证明；
- Research Intent → Contract → Run → ArtifactVersion → Evidence → Revision/Export/Share 的纵向链；
- Scientific Document / data integration / literature-reasoning / graph 的关键证据；
- benchmark 方法、固定输入、指标和限制；
- 依法需要的第三方 license/attribution；
- failure/degradation 示例；
- 可复现命令与稳定入口；
- secrets、私有 reasoning 与个人数据的脱敏说明。

无法复核 provider、实际模型身份、调用证明或无法回到 Evidence/provenance 的结论必须标为未证实，不能进入完成性宣传。只有实际声明并核对过的 revision 才进入提交证据。
