# Literature Reasoning Protocol

本文规定跨文献 Claim、Relation 和 ReasoningTrace 的生成与准入流程。

## 1. 输入前提

只接收已完成以下校验的输入：

- Paper/PaperSummary 可定位到来源；
- Claim 候选绑定 Evidence；
- Evidence 含 locator、quote_or_value、source_snapshot；
- 比较对象、字段、单位和研究范围可识别。

标题相似或关键词重合不能单独作为科学关系依据。

## 2. 处理流程

```text
PaperSummary
  -> Claim normalization
  -> Candidate pairing
  -> Relation classification
  -> Evidence consistency check
  -> ReasoningTrace construction
  -> Final relation admission
```

## 3. 关系判定

### supports

两条 Claim 在对象、指标、条件和结论方向上相容。表述为“提供支持证据”，不得写成绝对证明。

### extends / derived_from

后续工作明确扩展数据范围、对象范围、方法或分析；`derived_from` 需要可核验的前置数据/方法依赖。

### limits

文献对适用范围、数据质量、样本偏差或解释强度施加限制。

### contradicts

只有在比较对象、定义、单位、条件和统计口径足够一致时使用；否则优先使用 `limits` 或保留候选状态。

### uses_same_dataset / compares_method

作为结构关系使用，不自动推导支持或矛盾。

## 4. ReasoningTrace

每条最终 Relation 的 Trace 至少包含：

- source_claim_id；
- target_claim_id；
- 分步 rationale；
- 每步引用的 evidence_ids；
- 关系类型选择理由；
- 不确定性与适用条件；
- Prompt/模型版本或规则版本。

Trace 是审查记录，不暴露模型私有思维过程；只保存可核验的简洁推理依据。

## 5. 准入门槛

最终 Relation 必须满足：

- 两端 Claim 存在；
- relation_type 合法；
- Evidence 存在且属于对应来源；
- reasoning_trace_id 存在；
- Trace 的 Evidence 覆盖双方；
- confidence 在合法范围；
- 无权限/全文边界未被绕过。

不满足的记录进入候选集合，不进入最终图谱。

## 6. 人工修正

人工修正必须：

- 创建 UserFeedback；
- 记录原 Relation/Trace 版本；
- 生成新版本，不覆盖原记录；
- 说明修正依据；
- 重新验证 GraphEdge 的 evidence/trace 绑定。
