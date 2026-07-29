/**
 * Literature comparison grid (A-06) — an equal-width side-by-side reading of
 * up to three paper summaries, comparing goal, method and findings.
 *
 * Every column keeps its own ArtifactVersion identity, source mode and
 * per-statement support status; columns are never merged into an unsourced
 * conclusion. Empty slots are stated explicitly instead of being padded with
 * fabricated content.
 */

import type {
  PaperSummaryReview,
  PaperSummaryStatementReview,
} from "@xingwen/domain";

import {
  summarySourceModeLabel,
  supportStatusLabel,
} from "./literature-summary-state";

export interface LiteratureComparisonGridProps {
  /** 1–3 summaries; missing slots render as explicit empty columns. */
  readonly summaries: readonly PaperSummaryReview[];
}

const COMPARISON_SLOTS = 3;

function ComparisonCell({
  title,
  statements,
}: {
  readonly title: string;
  readonly statements: readonly PaperSummaryStatementReview[];
}) {
  return (
    <div className="paper-summary-comparison-cell">
      <h4 className="paper-section-title">{title}</h4>
      {statements.length === 0 ? (
        <p className="candidate-meta">
          <span className="candidate-meta-item">无陈述。</span>
        </p>
      ) : (
        <ul className="paper-summary-statement-list">
          {statements.map((statement) => (
            <li
              key={String(statement.statementId)}
              className="paper-summary-statement"
            >
              <span>{statement.text}</span>{" "}
              <span
                className={`paper-summary-badge paper-summary-badge--${statement.status}`}
              >
                {supportStatusLabel(statement.status)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function LiteratureComparisonGrid({
  summaries,
}: LiteratureComparisonGridProps) {
  const columns = Array.from(
    { length: COMPARISON_SLOTS },
    (_, index) => summaries[index] ?? null,
  );
  return (
    <section className="paper-summary-comparison" aria-label="文献总结对比">
      <h3 className="paper-section-title">文献总结对比</h3>
      <div className="paper-summary-comparison-grid">
        {columns.map((summary, index) =>
          summary === null ? (
            <article
              // Empty slots have no stable id; the position is the identity.
              key={`empty-slot-${String(index)}`}
              className="paper-summary-comparison-column paper-summary-comparison-column--empty"
              aria-label={`对比列 ${String(index + 1)}（空）`}
            >
              <p className="candidate-meta">
                <span className="candidate-meta-item">
                  空槽位：未选择文献总结。
                </span>
              </p>
            </article>
          ) : (
            <article
              key={String(summary.artifactVersionId)}
              className="paper-summary-comparison-column"
              aria-label={`对比列 ${String(index + 1)}`}
            >
              <p className="candidate-meta">
                <span className="candidate-meta-item">
                  paper {String(summary.paperId)}
                </span>
                <span className="candidate-meta-item">
                  ArtifactVersion {String(summary.artifactVersionId)}
                </span>
                <span className="candidate-meta-item">
                  source: {summarySourceModeLabel(summary.sourceMode)}
                </span>
              </p>
              <ComparisonCell
                title="研究目标"
                statements={
                  summary.researchGoal === null ? [] : [summary.researchGoal]
                }
              />
              <ComparisonCell
                title="研究方法"
                statements={summary.method === null ? [] : [summary.method]}
              />
              <ComparisonCell title="核心发现" statements={summary.findings} />
            </article>
          ),
        )}
      </div>
    </section>
  );
}
