import type {
  AnalysisReportReviewContent,
  DomainEntityId,
  ScientificMetricReview,
  ScientificResultBlockReview,
} from "@xingwen/domain";
import { Badge } from "@xingwen/ui";
import { TriangleAlert } from "@xingwen/ui/icons";

import { EvidenceLinks } from "../evidence-links";

const FINDING_ALERT_STATUSES = new Set([
  "partial",
  "unverifiable",
  "conflicted",
]);

function displayValue(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return JSON.stringify(value, null, 2);
}

function recordRows(
  payload: unknown,
): readonly Record<string, unknown>[] | null {
  if (!payload || typeof payload !== "object") return null;
  const record = payload as Record<string, unknown>;
  const candidate = Object.values(record).find(
    (value) =>
      Array.isArray(value) &&
      value.length > 0 &&
      value.every(
        (item) =>
          item !== null && typeof item === "object" && !Array.isArray(item),
      ),
  );
  return Array.isArray(candidate)
    ? (candidate as readonly Record<string, unknown>[])
    : null;
}

export function ResultBlock({
  block,
  onSelectEvidence,
}: {
  readonly block: ScientificResultBlockReview;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  const rows = recordRows(block.payload);
  const visibleRows = rows?.slice(0, 50) ?? [];
  const columns = [
    ...new Set(visibleRows.flatMap((row) => Object.keys(row))),
  ].slice(0, 12);
  return (
    <section className="scientific-result">
      <header>
        <h4>{block.label}</h4>
        <span>{block.representation}</span>
      </header>
      {rows ? (
        <div className="scientific-result__table-scroll">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column} scope="col">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column}>{displayValue(row[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > visibleRows.length ? (
            <p>
              当前显示前 {visibleRows.length} / {rows.length} 行。
            </p>
          ) : null}
        </div>
      ) : (
        <pre>{displayValue(block.payload)}</pre>
      )}
      <EvidenceLinks
        evidenceIds={block.evidenceIds}
        label={`${block.label}的证据`}
        onSelectEvidence={onSelectEvidence}
      />
    </section>
  );
}

export function Metrics({
  metrics,
  baseline = [],
  onSelectEvidence,
}: {
  readonly metrics: readonly ScientificMetricReview[];
  readonly baseline?: readonly ScientificMetricReview[];
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  if (metrics.length === 0) return null;
  const baselineByLabel = new Map(
    baseline.map((metric) => [metric.label, metric]),
  );
  return (
    <section className="scientific-metrics" aria-label="评估指标">
      <h4>指标</h4>
      <dl>
        {metrics.map((metric) => (
          <div key={metric.metricId}>
            <dt>{metric.label}</dt>
            <dd>
              <strong>{metric.value}</strong>
              {metric.unit ? <span>{metric.unit}</span> : null}
              {baselineByLabel.has(metric.label) ? (
                <small>基线 {baselineByLabel.get(metric.label)?.value}</small>
              ) : null}
              <EvidenceLinks
                evidenceIds={metric.evidenceIds}
                label={`${metric.label}的证据`}
                onSelectEvidence={onSelectEvidence}
              />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function Limitations({ items }: { readonly items: readonly string[] }) {
  if (items.length === 0) return null;
  return (
    <section className="scientific-limitations">
      <h4>局限性</h4>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function AnalysisReportContent({
  content,
  onSelectEvidence,
}: {
  readonly content: AnalysisReportReviewContent;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  return (
    <>
      <p className="artifact-view__lead">{content.summary}</p>
      <Metrics metrics={content.metrics} onSelectEvidence={onSelectEvidence} />
      {content.findings.length > 0 ? (
        <section className="scientific-findings">
          <h4>研究发现</h4>
          {content.findings.map((finding) => (
            <article key={finding.findingId} data-status={finding.status}>
              <header>
                <strong>{finding.title}</strong>
                {FINDING_ALERT_STATUSES.has(finding.status) ? (
                  <Badge variant="outline">{finding.status}</Badge>
                ) : null}
              </header>
              <p>{finding.statement}</p>
              <EvidenceLinks
                evidenceIds={finding.evidenceIds}
                label={`${finding.title}的证据`}
                onSelectEvidence={onSelectEvidence}
              />
            </article>
          ))}
        </section>
      ) : null}
      {content.resultBlocks.map((block) => (
        <ResultBlock
          key={block.blockId}
          block={block}
          onSelectEvidence={onSelectEvidence}
        />
      ))}
      <Limitations items={content.limitations} />
      {content.humanRequired.length > 0 ? (
        <section className="scientific-warning">
          <TriangleAlert aria-hidden="true" />
          <div>
            <h4>需要人工确认</h4>
            <ul>
              {content.humanRequired.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
    </>
  );
}
