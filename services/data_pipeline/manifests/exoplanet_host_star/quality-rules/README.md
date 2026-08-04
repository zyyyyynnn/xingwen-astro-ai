# C-05 quality rules

`quality-rules.v1.json` is the frozen, versioned RuleSet for the C-05 quality
evaluation of the `exoplanet_host_star` case.  It is loaded through
`services.data_pipeline.data_quality.policy.load_frozen_quality_rule_set` and
must compare equal to the caller-supplied `DataQualityRuleSet`.

The RuleSet binds the C-02 manifests, C-04 candidate schemas and C-08 result
RuleSet. It closes the formula registry, Decimal ratio policy, applicability
and incomplete-source semantics, Contract gate bindings, Publisher policy and
capacity preflight. The API schema compiles it once into an immutable
`QualityEvaluationPlan`; each formula has a closed formula kind plus numerator
and denominator observation bindings. The plan interpreter owns counting,
applicability, empty-denominator behavior and incomplete-source behavior;
execution, gate validation and result validation must consume that plan instead
of maintaining a second formula or gate registry.
The aggregate score is deliberately disabled in v1; raw field/row/dataset
metrics are authoritative and do not represent scientific conclusion accuracy.

Raw metrics intentionally do not carry Contract thresholds. Thresholds are
resolved through a gate binding's Contract locator only after the persisted
Contract has been projected to `ResearchContractInput` and verified by the
Core/Contract production content-identity function. Formula scope/result field,
empty-denominator behavior and incomplete-source behavior are part of the
versioned plan.

Row low-confidence consumes the C-08 record-to-edge component projection based
on candidate membership and has a dedicated confidence-applicable denominator.
Only paired records with an interpretable C-08 confidence band are applicable;
ConflictGroup and unpaired records are not applicable. Row review-required has
its own paired/conflict adjudicable denominator and consumes the final frozen
C-04 alignment status, so accepted/rejected adjudications are not reopened.

Unit consistency counts retained non-null `SourceValue` assertions, not mapped
cells. Observation IDs and formula definitions explicitly use that assertion
granularity. Observations traverse each C-04 row outcome once while accumulating
field, row and dataset counters.

`max_metric_records` is the exact count of emitted field metrics, row metrics,
dataset metrics and Contract gate checks derived from the compiled plan. It is
not an estimate of cell-processing work. Missing Evidence remains a C-04
candidate-admission failure; C-05 coverage metrics audit only admitted typed
Evidence and do not maintain a duplicate unreachable Evidence-gap rejection.

The JSON `content_hash` is the canonical C-01 hash of the payload without the
`content_hash` member.  Changes to formulas, policies, thresholds, bindings or
capacity require a new RuleSet version and synchronized tests.
