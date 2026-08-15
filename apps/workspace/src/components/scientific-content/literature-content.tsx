import type {
  LiteratureClaimReferenceReview,
  LiteratureReasoningTraceReview,
} from "@xingwen/domain";
import type { LiteratureArtifactReviewViewModel } from "@xingwen/research-adapter";

import {
  comparabilityLabel,
  humanizeToken,
  limitNote,
  polarityLabel,
  reviewStatusLabel,
  ScientificContentHeader,
  SURFACE_LIMITS,
  sourceModeLabel,
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

type ReasoningTracesReview = Extract<
  LiteratureArtifactReviewViewModel,
  { readonly kind: "reasoning_traces" }
>;

function ClaimLabel({
  claim,
}: {
  readonly claim: LiteratureClaimReferenceReview | null;
}) {
  if (!claim) return <span>未提供声明</span>;
  return <span>{claim.text || "未提供声明"}</span>;
}

function EvidenceCount({ count }: { readonly count: number }) {
  return <span>{count > 0 ? `${count} 条` : "未提供"}</span>;
}

function ClaimsTable({
  review,
  surface,
}: {
  readonly review: LiteratureClaimsReview;
  readonly surface: ScientificContentSurface;
}) {
  const claims = review.claims.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">文献声明与公开证据</caption>
        <thead>
          <tr>
            <th scope="col">声明</th>
            <th scope="col">状态 / 类型</th>
            <th scope="col">对象</th>
            <th scope="col">指标</th>
            <th scope="col">证据</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((claim) => (
            <tr key={claim.claimId}>
              <th scope="row">{claim.text || "未提供公开声明"}</th>
              <td>
                <span>{reviewStatusLabel(claim.status)}</span>
                <small>
                  {polarityLabel(claim.polarity)} ·{" "}
                  {taxonomyLabel(claim.claimType)}
                </small>
              </td>
              <td>
                {claim.objects.length > 0
                  ? claim.objects.join("、")
                  : "未提供对象"}
              </td>
              <td>
                <span>
                  {claim.metric ? humanizeToken(claim.metric) : "未提供指标"}
                </span>
                <small>
                  {[claim.unit, claim.uncertainty]
                    .filter(Boolean)
                    .join(" · ") || "单位 / 不确定度未提供"}
                </small>
              </td>
              <td>
                <EvidenceCount count={claim.evidenceIds.length} />
                {claim.failureStage || claim.rejectionReason ? (
                  <small>{claim.rejectionReason ?? claim.failureStage}</small>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(review.claims.length, claims.length, "条声明") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(review.claims.length, claims.length, "条声明")}
        </p>
      ) : null}
    </div>
  );
}

function ReasoningTrace({
  trace,
}: {
  readonly trace: LiteratureReasoningTraceReview;
}) {
  return (
    <div className="scientific-artifact__trace">
      <div className="scientific-artifact__trace-heading">
        <span>公开推导轨迹 · {reviewStatusLabel(trace.relationStatus)}</span>
      </div>
      {trace.conclusion ? (
        <p className="scientific-artifact__trace-conclusion">
          {trace.conclusion}
        </p>
      ) : null}
      {trace.steps.length > 0 ? (
        <ol>
          {trace.steps.map((step) => (
            <li key={step.order}>
              <p>{step.statement || "未提供公开步骤说明"}</p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="scientific-artifact__empty">未提供公开推导步骤。</p>
      )}
    </div>
  );
}

function RelationsTable({
  review,
  surface,
}: {
  readonly review: LiteratureRelationsReview;
  readonly surface: ScientificContentSurface;
}) {
  const relations = review.relations.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table scientific-artifact__table--relations">
        <caption className="sr-only">文献声明关系与推导证据</caption>
        <thead>
          <tr>
            <th scope="col">关系</th>
            <th scope="col">类型 / 状态</th>
            <th scope="col">可比性</th>
            <th scope="col">置信度</th>
            <th scope="col">证据 / 图谱</th>
          </tr>
        </thead>
        <tbody>
          {relations.map((relation) => (
            <tr key={relation.relationId}>
              <th scope="row">
                <ClaimLabel claim={relation.sourceClaim} />
                <span className="scientific-artifact__relation-arrow">→</span>
                <ClaimLabel claim={relation.targetClaim} />
              </th>
              <td>
                <span>{taxonomyLabel(relation.relationType)}</span>
                <small>{reviewStatusLabel(relation.status)}</small>
              </td>
              <td>
                <span>
                  {comparabilityLabel(relation.comparability.objectStatus)}
                </span>
                <small>
                  {comparabilityLabel(relation.comparability.metricStatus)} ·{" "}
                  {comparabilityLabel(relation.comparability.unitStatus)}
                </small>
              </td>
              <td>
                {relation.confidence?.score === null || !relation.confidence
                  ? "未提供"
                  : relation.confidence.score.toFixed(3)}
                <small>
                  {relation.confidence?.decision
                    ? humanizeToken(relation.confidence.decision)
                    : "未评估"}
                </small>
              </td>
              <td>
                <span>
                  <EvidenceCount count={relation.evidenceIds.length} />
                  {relation.graphEligible ? " · 可进入图谱" : " · 不进入图谱"}
                </span>
                {relation.reasoningTrace ? (
                  <ReasoningTrace trace={relation.reasoningTrace} />
                ) : (
                  <small>未提供公开推导轨迹</small>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(review.relations.length, relations.length, "条关系") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(review.relations.length, relations.length, "条关系")}
        </p>
      ) : null}
    </div>
  );
}

function TraceTable({
  review,
  surface,
}: {
  readonly review: ReasoningTracesReview;
  readonly surface: ScientificContentSurface;
}) {
  const traces = review.traces.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__trace-list">
      {traces.map((trace, index) => (
        <section
          key={trace.traceId}
          className="scientific-artifact__trace-block"
        >
          <header>
            <span>推导轨迹 {index + 1}</span>
          </header>
          <ReasoningTrace trace={trace} />
        </section>
      ))}
      {traces.length === 0 ? (
        <p className="scientific-artifact__empty">
          当前版本没有可展示的公开推导轨迹。
        </p>
      ) : null}
      {limitNote(review.traces.length, traces.length, "条轨迹") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(review.traces.length, traces.length, "条轨迹")}
        </p>
      ) : null}
    </div>
  );
}

export function LiteratureContent({
  review,
  title,
  surface,
}: {
  readonly review: LiteratureArtifactReviewViewModel;
  readonly title: string;
  readonly surface: ScientificContentSurface;
}) {
  const label =
    review.kind === "literature_claims"
      ? "文献声明"
      : review.kind === "literature_relations"
        ? "文献关系"
        : "公开推导轨迹";
  const count =
    review.kind === "literature_claims"
      ? review.claims.length
      : review.kind === "literature_relations"
        ? review.relations.length
        : review.traces.length;
  return (
    <article
      className={`scientific-artifact scientific-artifact--${review.kind}`}
      data-surface={surface}
    >
      <ScientificContentHeader title={title} subtitle={label} />
      <div className="scientific-artifact__summary" aria-label={`${label}摘要`}>
        <span>共 {count} 条</span>
        <span>{sourceModeLabel(review.sourceMode)}</span>
      </div>
      {review.kind === "literature_claims" ? (
        <ClaimsTable review={review} surface={surface} />
      ) : review.kind === "literature_relations" ? (
        <RelationsTable review={review} surface={surface} />
      ) : (
        <TraceTable review={review} surface={surface} />
      )}
    </article>
  );
}
