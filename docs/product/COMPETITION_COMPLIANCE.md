# Competition Compliance

| 元数据 | 值 |
| --- | --- |
| Authority | 竞赛方向、模型资格、差异化叙事与提交证据 |

## 1. 固定方向

产品参加科学数据查询、解析与整合方向。主叙事围绕可复核的科学数据纵向链，而不是通用聊天、通用 OCR、通用多 Agent 或外部能力集合。

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

参赛主案例必须使用赛题指定的合格模型，并通过比赛规则认可的官方平台或调用路径。提交证据不得使用浮动 latest。

合格调用必须能够复核：provider 与官方接入路径、model name/version/revision、Prompt name/version/hash、Contract/input hash、参数、调用时间与运行环境、脱敏 request/call proof、response/output hash、Schema/Evidence admission、ProducerExecution 与最终 ArtifactVersion。

API Key、原始认证头、完整 provider 原始响应与模型私有 chain-of-thought 不进入提交材料、公开 Artifact 或日志；只保留完成复核所需的脱敏事实。

非合格模型只可用于 benchmark、消融或对照，不得包装为合格主模型。

## 3. 差异化与能力归属

外部算法、工具、交互机制、benchmark 或工程经验只能作为研发输入：

- 外部调用记录不等于本项目的合格调用；
- 外部 benchmark 数字不等于当前产品性能；
- 外部 demo 不等于真实运行证据；
- 源码采用必须遵守许可证、attribution 与 provenance；
- 提交材料不以“整合了多少外部项目”作为技术差异化。

作品差异化来自星文智析将多源天文数据、科学文档、文献推理、Evidence Graph、Scientific Skills、版本化 Artifact、Revision 与 Agent Workspace 收敛为一条可复核链。

## 4. 真实性等级

Live、Cached、Recorded、Fixture、Benchmark 与 Revision 必须清楚区分。只有本项目的真实 Run、真实合格模型调用、真实 ArtifactVersion/Evidence 才能作为主案例能力证明。

任何 partial、unsupported、provider failure、source failure 或 parser degradation 都按真实结果展示，不能为了演示完整性改写为成功。

## 5. 提交材料

最终材料至少包含：

- 主案例与参赛方向声明；
- 固定代码 Commit / container image / environment manifest；
- 合格模型 provider/model/revision 与脱敏调用证明；
- Research Intent → Contract → Run → ArtifactVersion → Evidence → Revision/Export/Share 的纵向链；
- Scientific Document / data integration / literature-reasoning / graph 的关键证据；
- benchmark 方法、固定输入、指标和限制；
- 依法需要的第三方 license/attribution；
- failure/degradation 示例；
- 可复现命令与稳定入口；
- secrets、私有 reasoning 与个人数据的脱敏说明。

无法复核 provider/model/revision/call proof 或无法回到 Evidence/provenance 的结论必须标为未证实，不能进入完成性宣传。
