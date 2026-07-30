/**
 * Literature comparison grid (A-06) — an equal-width side-by-side reading of
 * up to three paper summaries, comparing goal, method, dataset, findings and
 * limitations & future work.
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
  allStatements,
  summarySourceModeLabel,
  supportStatusLabel,
} from "./literature-summary-state";

export interface LiteratureComparisonGridProps {
  /** 1–3 summaries; missing slots render as explicit empty columns. */
  readonly summaries: readonly PaperSummaryReview[];
}

const COMPARISON_SLOTS = 3;

function ComparisonProvenance({
  summary,
}: {
  readonly summary: PaperSummaryReview;
}) {
  const statements = allStatements(summary).flatMap(
    (region) => region.statements,
  );
  const supportedCount = statements.filter(
    (statement) => statement.status === "supported",
  ).length;
  return (
    <dl className="paper-dl">
      <dt>model / Prompt</dt>
      <dd>
        {summary.producer.modelName} / {String(summary.producer.promptName)}@
        {summary.producer.promptVersion}
      </dd>
      <dt>Evidence coverage</dt>
      <dd>
        {supportedCount}/{statements.length} 有证据支持；
        {statements.length - supportedCount} 项存在覆盖缺口
      </dd>
      {summary.cacheAudits.map((audit) => (
        <div
          key={`${String(audit.sourceId)}:${String(audit.sourceSnapshotId)}`}
        >
          <dt>Cached source</dt>
          <dd>
            {String(audit.sourceId)} / cache {audit.cacheVersion} / 适用条件：
            {audit.cacheApplicability} / Live 失败：
            {audit.liveFailureClass}:{audit.liveFailureCode} / origin Run{" "}
            {String(audit.originRunId)} / ArtifactVersion{" "}
            {String(audit.originArtifactVersionId)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

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
                  {summary.paper.title}
                </span>
                <span className="candidate-meta-item">
                  {summary.paper.authors.join("、") || "作者未知"}（
                  {summary.paper.year ?? "年份未知"}）
                </span>
                <span className="candidate-meta-item">
                  paper {String(summary.paperId)}
                </span>
                <span className="candidate-meta-item">
                  ArtifactVersion {String(summary.artifactVersionId)}
                </span>
                <span className="candidate-meta-item">
                  source: {summarySourceModeLabel(summary.sourceMode)}
                </span>
                <span className="candidate-meta-item">
                  版本 {String(summary.versionNumber)}
                  {summary.supersedesVersionId === null
                    ? "（初始版本）"
                    : `（修订自 ${String(summary.supersedesVersionId)}）`}
                </span>
              </p>
              <ComparisonProvenance summary={summary} />
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
              <ComparisonCell
                title="使用数据集"
                statements={summary.dataset === null ? [] : [summary.dataset]}
              />
              <ComparisonCell title="核心发现" statements={summary.findings} />
              <ComparisonCell
                title="局限与未来工作"
                statements={[...summary.limitations, ...summary.futureWork]}
              />
            </article>
          ),
        )}
      </div>
    </section>
  );
}
