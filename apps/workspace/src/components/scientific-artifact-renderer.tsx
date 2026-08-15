import type {
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
  PaperAcquisitionReviewViewModel,
} from "@xingwen/research-adapter";
import type {
  DomainEntityId,
  GraphEdgeReview,
  GraphNodeReview,
  LiteratureClaimReferenceReview,
  LiteratureReasoningTraceReview,
  LightCurveArtifactReviewContent,
  ScientificArtifactReview as DomainScientificArtifactReview,
  ScientificArtifactReviewContent,
  SpectrumArtifactReviewContent,
} from "@xingwen/domain";
import type { ReactNode } from "react";
import { safeExternalUrl } from "@xingwen/domain";
import { Badge, Link, Separator } from "@xingwen/ui";
import { EvidenceLinks } from "./evidence-links";

export type ScientificArtifactSurface = "thread" | "docked" | "fullscreen";

type ScientificArtifactReview =
  | (PaperAcquisitionReviewViewModel & { readonly kind: "paper_collection" })
  | LiteratureArtifactReviewViewModel
  | GraphArtifactReviewViewModel
  | DomainScientificArtifactReview;

export interface ScientificArtifactRendererProps {
  readonly review: ScientificArtifactReview;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: ScientificArtifactSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}

const SURFACE_LIMITS: Record<ScientificArtifactSurface, number> = {
  thread: 4,
  docked: 20,
  fullscreen: 80,
};

type PaperCollectionReviewViewModel = PaperAcquisitionReviewViewModel & {
  readonly kind: "paper_collection";
};

type ScientificReviewFor<Kind extends ScientificArtifactReviewContent["kind"]> =
  Omit<DomainScientificArtifactReview, "content"> & {
    readonly content: Extract<ScientificArtifactReviewContent, { kind: Kind }>;
  };

function valueOrUnavailable(value: string | number | null | undefined): string {
  if (value === null || value === undefined || String(value).trim() === "") {
    return "未提供";
  }
  return String(value);
}

function sourceModeLabel(mode: string): string {
  if (mode === "live") return "实时数据";
  if (mode === "cached") return "缓存数据";
  return "演示数据";
}

function formatNumber(value: number | null | undefined, digits = 4): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "未提供"
    : value.toFixed(digits);
}

function reviewSchemaVersion(review: ScientificArtifactReview): string {
  return "content" in review
    ? review.content.schemaVersion
    : review.schemaVersion;
}

function isGraphReview(
  review: ScientificArtifactReview,
): review is GraphArtifactReviewViewModel {
  return "kind" in review && review.kind === "graph";
}

function limitNote(total: number, shown: number, unit: string): string | null {
  return total > shown ? `当前显示前 ${shown} / ${total} ${unit}。` : null;
}

function VersionMeta({
  review,
  surface,
}: {
  readonly review: ScientificArtifactReview;
  readonly surface: ScientificArtifactSurface;
}) {
  const sourceSnapshotCount =
    "sourceSnapshots" in review
      ? review.sourceSnapshots.length
      : isGraphReview(review)
        ? review.integrity.counts.sourceSnapshotCount
        : "未提供";
  const evidenceCount =
    "evidenceIds" in review
      ? review.evidenceIds.length
      : "content" in review
        ? review.evidence.length
        : isGraphReview(review)
          ? review.evidenceUseCount
          : "未提供";
  return (
    <dl className="scientific-artifact__metadata">
      <div>
        <dt>来源模式</dt>
        <dd>{sourceModeLabel(review.sourceMode)}</dd>
      </div>
      <div>
        <dt>Schema</dt>
        <dd>{reviewSchemaVersion(review)}</dd>
      </div>
      <div>
        <dt>来源快照</dt>
        <dd>{sourceSnapshotCount}</dd>
      </div>
      {surface === "fullscreen" ? (
        <div>
          <dt>证据</dt>
          <dd>{evidenceCount}</dd>
        </div>
      ) : null}
    </dl>
  );
}

function ArtifactHeader({
  title,
  subtitle,
  badges,
}: {
  readonly title: string;
  readonly subtitle: string;
  readonly badges: readonly ReactNode[];
}) {
  return (
    <header className="scientific-artifact__header">
      <div>
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>
      <div className="scientific-artifact__badges">{badges}</div>
    </header>
  );
}

function PaperCandidateTable({
  review,
  surface,
}: {
  readonly review: PaperCollectionReviewViewModel;
  readonly surface: ScientificArtifactSurface;
}) {
  const candidates = review.candidates.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">论文候选与筛选结果</caption>
        <thead>
          <tr>
            <th scope="col">排名 / 选择</th>
            <th scope="col">论文</th>
            <th scope="col">作者 / 年</th>
            <th scope="col">标识</th>
            <th scope="col">相关性</th>
            <th scope="col">重复 / 冲突</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => {
            const safeUrl = safeExternalUrl(candidate.url);
            return (
              <tr key={candidate.candidateId}>
                <th scope="row">
                  <span>#{candidate.stableRank}</span>
                  <small>
                    {candidate.selection.kind === "selected" ? "已选" : "未选"}
                  </small>
                </th>
                <td>
                  {safeUrl ? (
                    <Link href={safeUrl} external>
                      {candidate.title || "未提供标题"}
                    </Link>
                  ) : (
                    candidate.title || "未提供标题"
                  )}
                  {candidate.selection.reason ? (
                    <small>{candidate.selection.reason}</small>
                  ) : null}
                </td>
                <td>
                  <span>
                    {candidate.authors.slice(0, 2).join("、") || "未提供作者"}
                  </span>
                  <small>{candidate.year ?? "年份未提供"}</small>
                </td>
                <td>
                  <span>
                    {candidate.doi ?? candidate.arxivId ?? "未提供 DOI / arXiv"}
                  </span>
                  {candidate.doi && candidate.arxivId ? (
                    <small>{candidate.arxivId}</small>
                  ) : null}
                </td>
                <td>{candidate.relevanceScore.toFixed(3)}</td>
                <td>
                  <span>
                    {candidate.duplicateGroup.candidateIds.length > 1
                      ? "重复组"
                      : "单项组"}
                  </span>
                  <small>
                    {candidate.conflicts.length > 0
                      ? `冲突 ${candidate.conflicts.length}`
                      : "无冲突"}
                  </small>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {limitNote(review.candidates.length, candidates.length, "条候选") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(review.candidates.length, candidates.length, "条候选")}
        </p>
      ) : null}
    </div>
  );
}

function PaperCollectionRenderer({
  review,
  title,
  versionNumber,
  surface,
}: {
  readonly review: PaperCollectionReviewViewModel;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: ScientificArtifactSurface;
}) {
  return (
    <article
      className="scientific-artifact scientific-artifact--paper-collection"
      data-surface={surface}
    >
      <ArtifactHeader
        title={title}
        subtitle={`论文集合 · v${versionNumber}`}
        badges={[
          <Badge key="candidates" variant="outline">
            {review.metrics.candidateCount} 条候选
          </Badge>,
          <Badge key="selected" variant="secondary">
            已选 {review.metrics.selectedCount}
          </Badge>,
          ...(review.metrics.sourceFailureCount > 0
            ? [
                <Badge key="failures" variant="destructive">
                  来源失败 {review.metrics.sourceFailureCount}
                </Badge>,
              ]
            : []),
        ]}
      />
      <VersionMeta review={review} surface={surface} />
      <div className="scientific-artifact__summary" aria-label="论文集合摘要">
        <span>查询：{review.query.normalizedQuery}</span>
        <span>重复候选 {review.metrics.duplicateCandidateCount}</span>
        <span>召回 {valueOrUnavailable(review.metrics.candidateRecall)}</span>
      </div>
      <Separator />
      {review.candidates.length > 0 ? (
        <PaperCandidateTable review={review} surface={surface} />
      ) : (
        <p className="scientific-artifact__empty">
          当前版本没有可展示的论文候选。
        </p>
      )}
    </article>
  );
}

function ClaimLabel({
  claim,
}: {
  readonly claim: LiteratureClaimReferenceReview | null;
}) {
  if (!claim) return <span>未提供声明</span>;
  return (
    <span>
      {claim.text || "未提供声明"}
      <small>{claim.claimId}</small>
    </span>
  );
}

function EvidenceCount({ count }: { readonly count: number }) {
  return <span>{count > 0 ? `${count} 条` : "未提供"}</span>;
}

function ClaimsTable({
  review,
  surface,
}: {
  readonly review: Extract<
    LiteratureArtifactReviewViewModel,
    { readonly kind: "literature_claims" }
  >;
  readonly surface: ScientificArtifactSurface;
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
              <th scope="row">
                <span>{claim.text || "未提供公开声明"}</span>
                <small>{claim.claimId}</small>
              </th>
              <td>
                <span>{claim.status}</span>
                <small>
                  {claim.polarity} · {claim.claimType}
                </small>
              </td>
              <td>
                {claim.objects.length > 0
                  ? claim.objects.join("、")
                  : "未提供对象"}
              </td>
              <td>
                <span>{claim.metric ?? "未提供指标"}</span>
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
        <span>公开推导轨迹</span>
        <Badge variant="outline">{trace.relationStatus}</Badge>
      </div>
      {trace.conclusion ? (
        <p className="scientific-artifact__trace-conclusion">
          {trace.conclusion}
        </p>
      ) : null}
      {trace.steps.length > 0 ? (
        <ol>
          {trace.steps.map((step) => (
            <li key={`${trace.traceId}-${step.order}`}>
              <span>{step.operation}</span>
              <p>{step.statement || "未提供公开步骤说明"}</p>
              <small>
                声明 {step.claimIds.length} · 证据 {step.evidenceIds.length}
              </small>
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
  readonly review: Extract<
    LiteratureArtifactReviewViewModel,
    { readonly kind: "literature_relations" }
  >;
  readonly surface: ScientificArtifactSurface;
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
                <span>{relation.relationType}</span>
                <small>{relation.status}</small>
              </td>
              <td>
                <span>{relation.comparability.objectStatus}</span>
                <small>
                  {relation.comparability.metricStatus} ·{" "}
                  {relation.comparability.unitStatus}
                </small>
              </td>
              <td>
                {relation.confidence?.score === null || !relation.confidence
                  ? "未提供"
                  : relation.confidence.score.toFixed(3)}
                <small>{relation.confidence?.decision ?? "未评估"}</small>
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
  readonly review: Extract<
    LiteratureArtifactReviewViewModel,
    { readonly kind: "reasoning_traces" }
  >;
  readonly surface: ScientificArtifactSurface;
}) {
  const traces = review.traces.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__trace-list">
      {traces.map((trace) => (
        <section
          key={trace.traceId}
          className="scientific-artifact__trace-block"
        >
          <header>
            <span>{trace.traceId}</span>
            <Badge variant="outline">{trace.relationStatus}</Badge>
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

function LiteratureRenderer({
  review,
  title,
  versionNumber,
  surface,
}: {
  readonly review: LiteratureArtifactReviewViewModel;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: ScientificArtifactSurface;
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
      <ArtifactHeader
        title={title}
        subtitle={`${label} · v${versionNumber}`}
        badges={[
          <Badge key="count" variant="outline">
            {count} 条
          </Badge>,
          <Badge key="source" variant="secondary">
            {sourceModeLabel(review.sourceMode)}
          </Badge>,
        ]}
      />
      <VersionMeta review={review} surface={surface} />
      <Separator />
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

function NodeTable({
  nodes,
  surface,
}: {
  readonly nodes: readonly GraphNodeReview[];
  readonly surface: ScientificArtifactSurface;
}) {
  const visible = nodes.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">证据图谱节点</caption>
        <thead>
          <tr>
            <th scope="col">节点</th>
            <th scope="col">类型 / 标签</th>
            <th scope="col">逻辑引用</th>
            <th scope="col">版本绑定</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((node) => (
            <tr key={node.nodeId}>
              <th scope="row">{node.nodeId}</th>
              <td>
                <span>{node.nodeType}</span>
                <small>{node.label || "未提供节点标签"}</small>
              </td>
              <td>
                {node.logicalReference.length > 0
                  ? node.logicalReference
                      .map((part) => `${part.name}: ${part.value}`)
                      .join(" · ")
                  : "未提供逻辑引用"}
              </td>
              <td>{node.versionBindings.length || "未提供"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(nodes.length, visible.length, "个节点") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(nodes.length, visible.length, "个节点")}
        </p>
      ) : null}
    </div>
  );
}

function EdgeTable({
  edges,
  surface,
}: {
  readonly edges: readonly GraphEdgeReview[];
  readonly surface: ScientificArtifactSurface;
}) {
  const visible = edges.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">证据图谱边与上游证据</caption>
        <thead>
          <tr>
            <th scope="col">边</th>
            <th scope="col">路径</th>
            <th scope="col">类型</th>
            <th scope="col">证据使用</th>
            <th scope="col">关系 / 聚合</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((edge) => (
            <tr key={edge.edgeId}>
              <th scope="row">{edge.edgeId}</th>
              <td>
                {edge.sourceNodeId && edge.targetNodeId
                  ? `${edge.sourceNodeId} → ${edge.targetNodeId}`
                  : "未提供节点路径"}
              </td>
              <td>{edge.edgeType}</td>
              <td>{edge.evidenceUseIds.length || "未提供"}</td>
              <td>
                <span>
                  {edge.relation
                    ? edge.relation.relationType
                    : edge.dataAggregation
                      ? `聚合行 ${edge.dataAggregation.projectedRowCount}`
                      : "未提供关系明细"}
                </span>
                {edge.relationTrace ? (
                  <small>
                    推导证据 {edge.relationTrace.traceEvidenceIds.length}
                  </small>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(edges.length, visible.length, "条边") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(edges.length, visible.length, "条边")}
        </p>
      ) : null}
    </div>
  );
}

function GraphRenderer({
  review,
  title,
  versionNumber,
  surface,
}: {
  readonly review: GraphArtifactReviewViewModel;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: ScientificArtifactSurface;
}) {
  return (
    <article
      className="scientific-artifact scientific-artifact--graph"
      data-surface={surface}
    >
      <ArtifactHeader
        title={title}
        subtitle={`证据图谱 · v${versionNumber}`}
        badges={[
          <Badge key="nodes" variant="outline">
            {review.nodeCount} 节点
          </Badge>,
          <Badge key="edges" variant="outline">
            {review.edgeCount} 边
          </Badge>,
          <Badge
            key="integrity"
            variant={
              review.integrity.status === "valid" ? "secondary" : "outline"
            }
          >
            完整性 {review.integrity.status}
          </Badge>,
        ]}
      />
      <VersionMeta review={review} surface={surface} />
      <div className="scientific-artifact__summary" aria-label="证据图谱摘要">
        <span>证据使用 {review.evidenceUseCount}</span>
        <span>布局 {review.layoutStrategy}</span>
        <span>
          渐进构建 {review.progressive.complete ? "已完成" : "未完成"}
        </span>
      </div>
      {review.integrity.findings.length > 0 ? (
        <p className="scientific-artifact__warning">
          完整性发现：{review.integrity.findings[0]?.message ?? "未提供说明"}
        </p>
      ) : null}
      <Separator />
      <section className="scientific-artifact__section">
        <h4>节点</h4>
        {review.nodes.length > 0 ? (
          <NodeTable nodes={review.nodes} surface={surface} />
        ) : (
          <p className="scientific-artifact__empty">
            当前版本没有可展示的节点。
          </p>
        )}
      </section>
      <section className="scientific-artifact__section">
        <h4>边</h4>
        {review.edges.length > 0 ? (
          <EdgeTable edges={review.edges} surface={surface} />
        ) : (
          <p className="scientific-artifact__empty">当前版本没有可展示的边。</p>
        )}
      </section>
    </article>
  );
}

function SpectrumPointTable({
  points,
  surface,
  wavelengthUnit,
  fluxUnit,
}: {
  readonly points: readonly SpectrumArtifactReviewContent["points"][number][];
  readonly surface: ScientificArtifactSurface;
  readonly wavelengthUnit: string;
  readonly fluxUnit: string;
}) {
  const visible = points.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">光谱采样点</caption>
        <thead>
          <tr>
            <th scope="col">波长 ({wavelengthUnit})</th>
            <th scope="col">通量 ({fluxUnit})</th>
            <th scope="col">连续谱</th>
            <th scope="col">归一化通量</th>
            <th scope="col">不确定度</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((point, index) => (
            <tr key={`${point.wavelength}-${index}`}>
              <th scope="row">{formatNumber(point.wavelength)}</th>
              <td>{formatNumber(point.flux)}</td>
              <td>{formatNumber(point.continuum)}</td>
              <td>{formatNumber(point.normalizedFlux)}</td>
              <td>{formatNumber(point.uncertainty)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(points.length, visible.length, "个采样点") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(points.length, visible.length, "个采样点")}
        </p>
      ) : null}
    </div>
  );
}

function SpectrumLineTable({
  lines,
  surface,
  wavelengthUnit,
}: {
  readonly lines: readonly SpectrumArtifactReviewContent["detectedLines"][number][];
  readonly surface: ScientificArtifactSurface;
  readonly wavelengthUnit: string;
}) {
  const visible = lines.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">检测到的谱线</caption>
        <thead>
          <tr>
            <th scope="col">谱线</th>
            <th scope="col">类型</th>
            <th scope="col">观测波长 ({wavelengthUnit})</th>
            <th scope="col">归一化通量</th>
            <th scope="col">显著性 / 等效宽度</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((line) => (
            <tr key={line.lineId}>
              <th scope="row">{line.lineId}</th>
              <td>{line.kind === "emission" ? "发射" : "吸收"}</td>
              <td>{formatNumber(line.observedWavelength)}</td>
              <td>{formatNumber(line.normalizedFlux)}</td>
              <td>
                <span>{formatNumber(line.significanceSigma)} σ</span>
                <small>等效宽度 {formatNumber(line.equivalentWidth)}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(lines.length, visible.length, "条谱线") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(lines.length, visible.length, "条谱线")}
        </p>
      ) : null}
    </div>
  );
}

function SpectrumRenderer({
  review,
  title,
  versionNumber,
  surface,
}: {
  readonly review: ScientificReviewFor<"spectrum">;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: ScientificArtifactSurface;
}) {
  const content = review.content;
  return (
    <article
      className="scientific-artifact scientific-artifact--spectrum"
      data-surface={surface}
    >
      <ArtifactHeader
        title={content.title || title}
        subtitle={`光谱 · ${content.objectName} · v${versionNumber}`}
        badges={[
          <Badge key="samples" variant="outline">
            {content.sampleCount} 点
          </Badge>,
          <Badge key="snr" variant="secondary">
            S/N {formatNumber(content.signalToNoise, 2)}
          </Badge>,
          <Badge key="lines" variant="outline">
            谱线 {content.detectedLines.length}
          </Badge>,
        ]}
      />
      <VersionMeta review={review} surface={surface} />
      <div className="scientific-artifact__summary" aria-label="光谱摘要">
        <span>
          波长 {content.wavelengthUnit} · 通量 {content.fluxUnit}
        </span>
        <span>静止波长 {formatNumber(content.restWavelength)}</span>
        <span>径向速度 {formatNumber(content.radialVelocityKmS)} km/s</span>
        <span>技能执行 {content.skillExecutions.length}</span>
      </div>
      <Separator />
      <section className="scientific-artifact__section">
        <h4>采样点</h4>
        {content.points.length > 0 ? (
          <SpectrumPointTable
            points={content.points}
            surface={surface}
            wavelengthUnit={content.wavelengthUnit}
            fluxUnit={content.fluxUnit}
          />
        ) : (
          <p className="scientific-artifact__empty">未提供光谱采样点。</p>
        )}
      </section>
      <section className="scientific-artifact__section">
        <h4>检测到的谱线</h4>
        {content.detectedLines.length > 0 ? (
          <SpectrumLineTable
            lines={content.detectedLines}
            surface={surface}
            wavelengthUnit={content.wavelengthUnit}
          />
        ) : (
          <p className="scientific-artifact__empty">当前版本未检测到谱线。</p>
        )}
      </section>
    </article>
  );
}

function PeriodogramTable({
  peaks,
  surface,
  timeUnit,
}: {
  readonly peaks: readonly LightCurveArtifactReviewContent["periodPeaks"][number][];
  readonly surface: ScientificArtifactSurface;
  readonly timeUnit: string;
}) {
  const visible = peaks.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">光变周期峰值</caption>
        <thead>
          <tr>
            <th scope="col">周期 ({timeUnit})</th>
            <th scope="col">功率</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((peak, index) => (
            <tr key={`${peak.period}-${index}`}>
              <th scope="row">{formatNumber(peak.period)}</th>
              <td>{formatNumber(peak.power)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(peaks.length, visible.length, "个周期峰值") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(peaks.length, visible.length, "个周期峰值")}
        </p>
      ) : null}
    </div>
  );
}

function LightCurvePointTable({
  points,
  surface,
  timeUnit,
  valueUnit,
}: {
  readonly points: readonly LightCurveArtifactReviewContent["points"][number][];
  readonly surface: ScientificArtifactSurface;
  readonly timeUnit: string;
  readonly valueUnit: string;
}) {
  const visible = points.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">光变曲线采样点</caption>
        <thead>
          <tr>
            <th scope="col">时间 ({timeUnit})</th>
            <th scope="col">值 ({valueUnit})</th>
            <th scope="col">归一化值</th>
            <th scope="col">不确定度</th>
            <th scope="col">质量 / 相位</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((point, index) => (
            <tr key={`${point.time}-${index}`}>
              <th scope="row">{formatNumber(point.time)}</th>
              <td>{formatNumber(point.value)}</td>
              <td>{formatNumber(point.normalizedValue)}</td>
              <td>{formatNumber(point.uncertainty)}</td>
              <td>
                <span>{point.quality === "good" ? "有效" : "剔除"}</span>
                <small>相位 {formatNumber(point.phase, 3)}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(points.length, visible.length, "个采样点") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(points.length, visible.length, "个采样点")}
        </p>
      ) : null}
    </div>
  );
}

function LightCurveRenderer({
  review,
  title,
  versionNumber,
  surface,
}: {
  readonly review: ScientificReviewFor<"light_curve">;
  readonly title: string;
  readonly versionNumber: number;
  readonly surface: ScientificArtifactSurface;
}) {
  const content = review.content;
  return (
    <article
      className="scientific-artifact scientific-artifact--light-curve"
      data-surface={surface}
    >
      <ArtifactHeader
        title={content.title || title}
        subtitle={`光变曲线 · ${content.objectName} · v${versionNumber}`}
        badges={[
          <Badge key="samples" variant="outline">
            {content.sampleCount} 点
          </Badge>,
          <Badge key="accepted" variant="secondary">
            有效 {content.acceptedSampleCount}
          </Badge>,
          <Badge key="period" variant="outline">
            周期 {formatNumber(content.bestPeriod)} {content.timeUnit}
          </Badge>,
        ]}
      />
      <VersionMeta review={review} surface={surface} />
      <div className="scientific-artifact__summary" aria-label="光变曲线摘要">
        <span>
          {content.timeScale.toUpperCase()} · {content.timeUnit}
        </span>
        <span>
          {content.valueKind} · {content.valueUnit} · {content.normalization}
        </span>
        <span>剔除 {content.rejectedSampleCount}</span>
        <span>FAP {formatNumber(content.falseAlarmProbability, 4)}</span>
        <span>技能执行 {content.skillExecutions.length}</span>
      </div>
      <Separator />
      <section className="scientific-artifact__section">
        <h4>周期分析</h4>
        <div className="scientific-artifact__summary">
          <span>最佳功率 {formatNumber(content.bestPower, 4)}</span>
          <span>
            持续时间 {formatNumber(content.duration)} {content.timeUnit}
          </span>
          <span>
            中位采样间隔 {formatNumber(content.medianCadence)}{" "}
            {content.timeUnit}
          </span>
        </div>
        {content.periodPeaks.length > 0 ? (
          <PeriodogramTable
            peaks={content.periodPeaks}
            surface={surface}
            timeUnit={content.timeUnit}
          />
        ) : (
          <p className="scientific-artifact__empty">未提供周期峰值。</p>
        )}
      </section>
      <section className="scientific-artifact__section">
        <h4>采样点</h4>
        {content.points.length > 0 ? (
          <LightCurvePointTable
            points={content.points}
            surface={surface}
            timeUnit={content.timeUnit}
            valueUnit={content.valueUnit}
          />
        ) : (
          <p className="scientific-artifact__empty">未提供光变曲线采样点。</p>
        )}
      </section>
    </article>
  );
}

function ScientificArtifactContent({
  review,
  title,
  versionNumber,
  surface,
}: Omit<ScientificArtifactRendererProps, "onSelectEvidence">) {
  if ("content" in review) {
    if (review.content.kind === "spectrum") {
      return (
        <SpectrumRenderer
          review={review as ScientificReviewFor<"spectrum">}
          title={title}
          versionNumber={versionNumber}
          surface={surface}
        />
      );
    }
    if (review.content.kind === "light_curve") {
      return (
        <LightCurveRenderer
          review={review as ScientificReviewFor<"light_curve">}
          title={title}
          versionNumber={versionNumber}
          surface={surface}
        />
      );
    }
    return null;
  }
  if (review.kind === "paper_collection") {
    return (
      <PaperCollectionRenderer
        review={review}
        title={title}
        versionNumber={versionNumber}
        surface={surface}
      />
    );
  }
  if (review.kind === "graph") {
    return (
      <GraphRenderer
        review={review}
        title={title}
        versionNumber={versionNumber}
        surface={surface}
      />
    );
  }
  return (
    <LiteratureRenderer
      review={review}
      title={title}
      versionNumber={versionNumber}
      surface={surface}
    />
  );
}

export function ScientificArtifactRenderer({
  onSelectEvidence,
  ...props
}: ScientificArtifactRendererProps) {
  const evidenceIds =
    "content" in props.review
      ? props.review.content.evidenceIds
      : "evidenceIds" in props.review
        ? props.review.evidenceIds
        : [];
  return (
    <>
      <ScientificArtifactContent {...props} />
      <EvidenceLinks
        evidenceIds={evidenceIds}
        label={`${props.title}的证据`}
        onSelectEvidence={onSelectEvidence}
      />
    </>
  );
}
