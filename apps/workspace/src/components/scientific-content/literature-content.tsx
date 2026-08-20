import type {
  DomainEntityId,
  LiteratureClaimReferenceReview,
  LiteratureReasoningTraceReview,
} from "@xingwen/domain";
import type { LiteratureArtifactReviewViewModel } from "@xingwen/research-adapter";
import { Button } from "@xingwen/ui";

import {
  comparabilityLabel,
  humanizeToken,
  limitNote,
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
  return <span>{claim?.text || "未提供声明"}</span>;
}

function EvidenceAction({
  evidenceIds,
  onSelectEvidence,
}: {
  readonly evidenceIds: readonly DomainEntityId[];
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const evidenceId = evidenceIds[0] ?? null;
  return evidenceId && onSelectEvidence ? (
    <Button
      size="small"
      variant="ghost"
      onClick={() => onSelectEvidence(evidenceId)}
    >
      查看来源
    </Button>
  ) : (
    <span className="text-xs text-[var(--oh-muted)]">未提供公开证据</span>
  );
}

function ClaimsTable({
  review,
  surface,
  onSelectEvidence,
}: {
  readonly review: LiteratureClaimsReview;
  readonly surface: ScientificContentSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const claims = review.claims.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll my-3 overflow-x-auto rounded border border-[var(--oh-border)]">
      <table className="w-full border-collapse text-left text-xs">
        <caption className="sr-only">文献论点与公开证据</caption>
        <thead>
          <tr className="border-b border-[var(--oh-border)] bg-[var(--oh-surface-subtle)]">
            <th scope="col" className="p-2.5 font-medium">
              论点
            </th>
            <th scope="col" className="p-2.5 font-medium">
              关键科学量
            </th>
            <th scope="col" className="p-2.5 font-medium">
              证据 / 异常
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--oh-border)]">
          {claims.map((claim) => (
            <tr key={claim.claimId}>
              <th
                scope="row"
                className="p-2.5 align-top font-medium leading-5 text-[var(--oh-foreground)]"
              >
                {claim.text || "未提供公开论点"}
                {claim.status !== "accepted" ? (
                  <div className="mt-1 text-xs font-normal text-[var(--oh-warning)]">
                    {reviewStatusLabel(claim.status)}
                  </div>
                ) : null}
              </th>
              <td className="p-2.5 align-top">
                {claim.metric ? (
                  <>
                    <div>{humanizeToken(claim.metric)}</div>
                    <div className="mt-1 text-xs text-[var(--oh-muted)]">
                      {[claim.unit, claim.uncertainty]
                        .filter(Boolean)
                        .join(" · ") || "单位 / 不确定度未提供"}
                    </div>
                  </>
                ) : (
                  <span className="text-[var(--oh-muted)]">
                    未提供结构化科学量
                  </span>
                )}
              </td>
              <td className="p-2.5 align-top">
                <EvidenceAction
                  evidenceIds={claim.evidenceIds}
                  onSelectEvidence={onSelectEvidence}
                />
                {claim.failureStage || claim.rejectionReason ? (
                  <div className="mt-1 text-xs text-[var(--oh-danger)]">
                    {claim.rejectionReason ?? claim.failureStage}
                  </div>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(review.claims.length, claims.length, "条论点") ? (
        <p className="border-t border-[var(--oh-border)] bg-[var(--oh-surface-subtle)] p-2 text-xs text-[var(--oh-muted)]">
          {limitNote(review.claims.length, claims.length, "条论点")}
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
    <details className="rounded border border-[var(--oh-border)] bg-[var(--oh-surface-subtle)] p-3">
      <summary className="cursor-pointer text-xs font-medium text-[var(--oh-foreground)]">
        {trace.conclusion || "查看公开推导过程"}
      </summary>
      <div className="mt-3 space-y-2 text-xs">
        {trace.steps.length > 0 ? (
          <ol className="list-decimal space-y-1 pl-5 text-[var(--oh-muted)]">
            {trace.steps.map((step) => (
              <li key={step.order}>{step.statement || "未提供公开步骤说明"}</li>
            ))}
          </ol>
        ) : (
          <p className="text-[var(--oh-muted)]">未提供公开推导步骤。</p>
        )}
        {trace.conflicts.length > 0 ? (
          <p className="text-[var(--oh-danger)]">
            冲突：{trace.conflicts.join("；")}
          </p>
        ) : null}
        {trace.limitations.length > 0 ? (
          <p className="text-[var(--oh-muted)]">
            限制：{trace.limitations.join("；")}
          </p>
        ) : null}
      </div>
    </details>
  );
}

function RelationsTable({
  review,
  surface,
  onSelectEvidence,
}: {
  readonly review: LiteratureRelationsReview;
  readonly surface: ScientificContentSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const relations = review.relations.slice(0, SURFACE_LIMITS[surface]);
  const traces = relations.flatMap((relation) =>
    relation.reasoningTrace ? [relation.reasoningTrace] : [],
  );
  return (
    <div className="space-y-4">
      <div className="scientific-artifact__table-scroll my-3 overflow-x-auto rounded border border-[var(--oh-border)]">
        <table className="w-full border-collapse text-left text-xs">
          <caption className="sr-only">文献论点关系与证据</caption>
          <thead>
            <tr className="border-b border-[var(--oh-border)] bg-[var(--oh-surface-subtle)]">
              <th scope="col" className="p-2.5 font-medium">
                关系
              </th>
              <th scope="col" className="p-2.5 font-medium">
                可比性
              </th>
              <th scope="col" className="p-2.5 font-medium">
                证据 / 异常
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--oh-border)]">
            {relations.map((relation) => (
              <tr key={relation.relationId}>
                <th
                  scope="row"
                  className="p-2.5 align-top font-medium leading-5 text-[var(--oh-foreground)]"
                >
                  <div className="flex items-start gap-1.5">
                    <ClaimLabel claim={relation.sourceClaim} />
                    <span className="text-[var(--oh-muted)]">→</span>
                    <ClaimLabel claim={relation.targetClaim} />
                  </div>
                  <div className="mt-1 text-xs font-normal text-[var(--oh-muted)]">
                    {taxonomyLabel(relation.relationType)}
                    {relation.status !== "accepted"
                      ? ` · ${reviewStatusLabel(relation.status)}`
                      : ""}
                    {relation.confidence?.score !== null && relation.confidence
                      ? ` · 置信度 ${relation.confidence.score.toFixed(2)}`
                      : ""}
                  </div>
                </th>
                <td className="p-2.5 align-top">
                  <div>
                    {comparabilityLabel(relation.comparability.objectStatus)}
                  </div>
                  <div className="mt-1 text-xs text-[var(--oh-muted)]">
                    指标{" "}
                    {comparabilityLabel(relation.comparability.metricStatus)} ·
                    单位 {comparabilityLabel(relation.comparability.unitStatus)}
                  </div>
                </td>
                <td className="p-2.5 align-top">
                  <EvidenceAction
                    evidenceIds={relation.evidenceIds}
                    onSelectEvidence={onSelectEvidence}
                  />
                  {relation.failureStage || relation.rejectionReason ? (
                    <div className="mt-1 text-xs text-[var(--oh-danger)]">
                      {relation.rejectionReason ?? relation.failureStage}
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {limitNote(review.relations.length, relations.length, "条关系") ? (
          <p className="border-t border-[var(--oh-border)] bg-[var(--oh-surface-subtle)] p-2 text-xs text-[var(--oh-muted)]">
            {limitNote(review.relations.length, relations.length, "条关系")}
          </p>
        ) : null}
      </div>
      {traces.length > 0 ? (
        <section className="space-y-2" aria-label="公开推导过程">
          <h3 className="text-sm font-medium text-[var(--oh-foreground)]">
            公开推导过程
          </h3>
          {traces.map((trace) => (
            <ReasoningTrace key={trace.traceId} trace={trace} />
          ))}
        </section>
      ) : null}
    </div>
  );
}

function TraceList({
  review,
  surface,
  onSelectEvidence,
}: {
  readonly review: ReasoningTracesReview;
  readonly surface: ScientificContentSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const traces = review.traces.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="my-3 space-y-3">
      {traces.map((trace) => (
        <div key={trace.traceId} className="space-y-1">
          <ReasoningTrace trace={trace} />
          <EvidenceAction
            evidenceIds={trace.evidenceIds}
            onSelectEvidence={onSelectEvidence}
          />
        </div>
      ))}
      {traces.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--oh-muted)]">
          当前结果没有可展示的公开推导过程。
        </p>
      ) : null}
      {limitNote(review.traces.length, traces.length, "条推导") ? (
        <p className="text-xs text-[var(--oh-muted)]">
          {limitNote(review.traces.length, traces.length, "条推导")}
        </p>
      ) : null}
    </div>
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
  const label =
    review.kind === "literature_claims"
      ? "文献论点"
      : review.kind === "literature_relations"
        ? "文献关系"
        : "公开推导过程";
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
      <div
        className="my-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--oh-muted)]"
        aria-label={`${label}摘要`}
      >
        <span>共 {count} 条</span>
        <span>{sourceModeLabel(review.sourceMode)}</span>
      </div>
      {review.kind === "literature_claims" ? (
        <ClaimsTable
          review={review}
          surface={surface}
          onSelectEvidence={onSelectEvidence}
        />
      ) : review.kind === "literature_relations" ? (
        <RelationsTable
          review={review}
          surface={surface}
          onSelectEvidence={onSelectEvidence}
        />
      ) : (
        <TraceList
          review={review}
          surface={surface}
          onSelectEvidence={onSelectEvidence}
        />
      )}
    </article>
  );
}
