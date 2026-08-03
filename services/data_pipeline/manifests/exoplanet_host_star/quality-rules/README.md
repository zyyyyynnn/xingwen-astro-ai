# C-05 quality rules

`quality-rules.v1.json` is the frozen, versioned RuleSet for the C-05 quality
evaluation of the `exoplanet_host_star` case.  It is loaded through
`services.data_pipeline.data_quality.policy.load_frozen_quality_rule_set` and
must compare equal to the caller-supplied `DataQualityRuleSet`.

The RuleSet binds the C-02 manifests, C-04 candidate schemas and C-08 result
RuleSet. It closes the formula registry, Decimal ratio policy, applicability
and incomplete-source semantics, Contract gate bindings, Publisher policy and
capacity preflight. The API schema compiles it once into an immutable
`QualityEvaluationPlan`; execution, gate validation and result validation must
consume that plan instead of maintaining a second formula or gate registry.
The aggregate score is deliberately disabled in v1; raw field/row/dataset
metrics are authoritative and do not represent scientific conclusion accuracy.

Raw metrics intentionally do not carry Contract thresholds. Thresholds are
resolved through a gate binding's Contract locator only after
`ResearchContract.content_hash` has been verified. Formula scope/result field,
empty-denominator behavior and incomplete-source behavior are part of the
versioned plan.

The JSON `content_hash` is the canonical C-01 hash of the payload without the
`content_hash` member.  Changes to formulas, policies, thresholds, bindings or
capacity require a new RuleSet version and synchronized tests.
