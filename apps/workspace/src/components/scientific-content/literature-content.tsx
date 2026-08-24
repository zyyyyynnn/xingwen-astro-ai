import type {
  DomainEntityId,
  LiteratureClaimReferenceReview,
  LiteratureClaimReview,
  LiteratureReasoningTraceReview,
  LiteratureRelationReview,
} from "@xingwen/domain";
import type { LiteratureArtifactReviewViewModel } from "@xingwen/research-adapter";
import {
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@xingwen/ui";
import { ChevronDown, Quote } from "@xingwen/ui/icons";

import {
  comparabilityLabel,
  polarityLabel,
  reviewStatusLabel,
  ScientificContentHeader,
  taxonomyLabel,
  type ScientificContentSurface,
} from "./shared";

type LiteratureClaimsReview = Extract<
  LiteratureArtifactReviewViewModel,
  { readonly kind: "literature_claims" }
>;
type LiteratureRelationsReview = Extract<
  LiteratureArtifactReviewViewModel,
  { readonly kind: "literature_relations" }
>;

function meaningful(values: readonly (string | null | undefined)[]): string[] {
  return values.filter(
    (value): value is string =>
      typeof value === "string" && value.trim() !== "",
  );
}

function confidenceLabel(relation: LiteratureRelationReview): string {
  const score = relation.confidence?.score;
  if (score === null || score === undefined) return "尚无独立可信度评估";
  if (score >= 0.8) return "可信程度较高";
  if (score >= 0.6) return "可信程度中等";
  return "可信程度需要谨慎看待";
}

function rejectionExplanation(
  status: string,
  rejectionReason: string | null,
): string | null {
  if (status === "accepted") return null;
  const known: Record<string, string> = {
    duplicate_claim: "与已有论点重复，因此未重复纳入结论。",
    evidence_missing: "缺少可定位证据，因此未纳入结论。",
    evidence_snapshot_missing: "来源快照不完整，因此无法复核。",
    comparability_failed: "研究条件不可直接比较，因此未形成关系结论。",
    condition_conflict: "适用条件存在冲突，因此未纳入结论。",
    confidence_below_threshold: "现有证据不足以支持可靠结论。",
    invalid_json: "抽取结果无法形成可复核的结构化论点。",
    schema_invalid: "抽取结果缺少形成科学论点所需的信息。",
  };
  return rejectionReason
    ? (known[rejectionReason] ?? "证据或可比性未达到纳入结论的要求。")
    : "仍需更多证据或人工核验后才能纳入结论。";
}

function EvidenceActions({
  evidenceIds,
  onSelectEvidence,
}: {
  readonly evidenceIds: readonly DomainEntityId[];
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  if (evidenceIds.length === 0 || !onSelectEvidence) {
    return <p className="dossier__empty">没有可公开核验的证据。</p>;
  }
  return (
    <div className="dossier__evidence-actions" aria-label="可核验证据">
      {evidenceIds.map((evidenceId, index) => (
        <Button
          key={evidenceId}
          size="small"
          variant="ghost"
          onClick={() => onSelectEvidence(evidenceId)}
        >
          <Quote aria-hidden="true" />
          查看证据 {index + 1}
        </Button>
      ))}
    </div>
  );
}

function DossierFacts({
  facts,
}: {
  readonly facts: readonly {
    readonly label: string;
    readonly values: readonly (string | null | undefined)[];
  }[];
}) {
  const visible = facts
    .map((fact) => ({ ...fact, values: meaningful(fact.values) }))
    .filter((fact) => fact.values.length > 0);
  if (visible.length === 0) return null;
  return (
    <dl className="dossier__facts">
      {visible.map((fact) => (
        <div key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>{fact.values.join("；")}</dd>
        </div>
      ))}
    </dl>
  );
}

function ClaimLabel({
  claim,
}: {
  readonly claim: LiteratureClaimReferenceReview | null;
}) {
  return <span>{claim?.text || "论点内容未公开"}</span>;
}

function ClaimDossier({
  claim,
  onSelectEvidence,
}: {
  readonly claim: LiteratureClaimReview;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const scientificMeasure = claim.metric
    ? [
        taxonomyLabel(claim.metric),
        claim.unit ? `单位 ${claim.unit}` : null,
        claim.uncertainty ? `不确定度 ${claim.uncertainty}` : null,
        claim.comparisonBasis ? `比较依据 ${claim.comparisonBasis}` : null,
      ]
    : [];
  const explanation = rejectionExplanation(claim.status, claim.rejectionReason);
  return (
    <article className="dossier__entry" data-status={claim.status}>
      <header className="dossier__entry-header">
        <div>
          <p className="dossier__status">{reviewStatusLabel(claim.status)}</p>
          <h4>{claim.text || "论点内容未公开"}</h4>
        </div>
        <p className="dossier__assessment">
          {taxonomyLabel(claim.claimType)} · {polarityLabel(claim.polarity)}
        </p>
      </header>
      <DossierFacts
        facts={[
          { label: "研究对象", values: claim.objects },
          { label: "适用范围", values: claim.scope },
          { label: "成立条件", values: claim.conditions },
          { label: "限定说明", values: claim.qualifiers },
          { label: "关键科学量", values: scientificMeasure },
          { label: "限制", values: claim.limitations },
          { label: "未纳入原因", values: [explanation] },
        ]}
      />
      <EvidenceActions
        evidenceIds={claim.evidenceIds}
        onSelectEvidence={onSelectEvidence}
      />
    </article>
  );
}

function ReasoningTrace({
  trace,
  onSelectEvidence,
}: {
  readonly trace: LiteratureReasoningTraceReview;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  return (
    <Collapsible className="reasoning-trace">
      <CollapsibleTrigger asChild>
        <Button variant="ghost" className="reasoning-trace__trigger">
          <span>{trace.conclusion || "查看公开推导"}</span>
          <ChevronDown aria-hidden="true" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="reasoning-trace__content">
          {trace.steps.length > 0 ? (
            <ol>
              {trace.steps.map((step) => (
                <li key={step.order}>{step.statement || "公开步骤说明缺失"}</li>
              ))}
            </ol>
          ) : (
            <p>没有可公开展示的推导步骤。</p>
          )}
          <DossierFacts
            facts={[
              { label: "成立条件", values: trace.conditions },
              { label: "冲突", values: trace.conflicts },
              { label: "限制", values: trace.limitations },
            ]}
          />
          <EvidenceActions
            evidenceIds={trace.evidenceIds}
            onSelectEvidence={onSelectEvidence}
          />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function RelationDossier({
  relation,
  onSelectEvidence,
}: {
  readonly relation: LiteratureRelationReview;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const explanation = rejectionExplanation(
    relation.status,
    relation.rejectionReason,
  );
  const comparable = [
    `研究对象${comparabilityLabel(relation.comparability.objectStatus)}`,
    `科学指标${comparabilityLabel(relation.comparability.metricStatus)}`,
    `单位${comparabilityLabel(relation.comparability.unitStatus)}`,
  ];
  return (
    <article className="dossier__entry" data-status={relation.status}>
      <header className="dossier__entry-header">
        <div>
          <p className="dossier__status">
            {reviewStatusLabel(relation.status)} ·{" "}
            {taxonomyLabel(relation.relationType)}
          </p>
          <h4 className="dossier__relation-title">
            <ClaimLabel claim={relation.sourceClaim} />
            <span aria-hidden="true">→</span>
            <ClaimLabel claim={relation.targetClaim} />
          </h4>
        </div>
        <p className="dossier__assessment">{confidenceLabel(relation)}</p>
      </header>
      <DossierFacts
        facts={[
          { label: "可比性", values: comparable },
          { label: "成立条件", values: relation.conditions },
          { label: "条件冲突", values: relation.conditionConflicts },
          { label: "仍待确认", values: relation.conditionUncertainties },
          { label: "方向依据", values: [relation.direction.basis] },
          { label: "未纳入原因", values: [explanation] },
        ]}
      />
      <EvidenceActions
        evidenceIds={relation.evidenceIds}
        onSelectEvidence={onSelectEvidence}
      />
      {relation.reasoningTrace ? (
        <ReasoningTrace
          trace={relation.reasoningTrace}
          onSelectEvidence={onSelectEvidence}
        />
      ) : relation.status === "accepted" ? (
        <p className="dossier__empty">这条关系没有可公开核验的推导记录。</p>
      ) : null}
    </article>
  );
}

function ClaimsDossier({
  review,
  onSelectEvidence,
}: {
  readonly review: LiteratureClaimsReview;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  if (review.claims.length === 0) {
    return <p className="dossier__empty">当前结果没有可展示的文献论点。</p>;
  }
  return (
    <ol className="candidate-dossier" aria-label="文献论点档案">
      {review.claims.map((claim) => (
        <li key={claim.claimId}>
          <ClaimDossier claim={claim} onSelectEvidence={onSelectEvidence} />
        </li>
      ))}
    </ol>
  );
}

function RelationsDossier({
  review,
  onSelectEvidence,
}: {
  readonly review: LiteratureRelationsReview;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  if (review.relations.length === 0) {
    return <p className="dossier__empty">当前结果没有可展示的文献关系。</p>;
  }
  return (
    <ol className="candidate-dossier" aria-label="文献关系档案">
      {review.relations.map((relation) => (
        <li key={relation.relationId}>
          <RelationDossier
            relation={relation}
            onSelectEvidence={onSelectEvidence}
          />
        </li>
      ))}
    </ol>
  );
}

export function LiteratureContent({
  review,
  title,
  surface,
  onSelectEvidence,
}: {
  readonly review: LiteratureArtifactReviewViewModel;
  readonly title: string;
  readonly surface: ScientificContentSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const label = review.kind === "literature_claims" ? "论点档案" : "关系档案";
  const count =
    review.kind === "literature_claims"
      ? review.claims.length
      : review.relations.length;
  return (
    <article
      className={`scientific-artifact scientific-artifact--${review.kind}`}
      data-surface={surface}
    >
      <ScientificContentHeader
        title={title}
        subtitle={`${label}，共 ${count} 条`}
      />
      {review.kind === "literature_claims" ? (
        <ClaimsDossier review={review} onSelectEvidence={onSelectEvidence} />
      ) : (
        <RelationsDossier review={review} onSelectEvidence={onSelectEvidence} />
      )}
    </article>
  );
}
