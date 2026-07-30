/**
 * Literature Summary Reading Workspace (A-06) — the central-canvas reading
 * surface for a `paper_summary` ArtifactVersion.
 *
 * Consumes only the `PaperSummaryRepository` port and domain models; it never
 * sees URLs, DTOs or envelopes. Five fixed reading regions (goal, method,
 * dataset, findings, limitations & future work), each statement rendered with
 * its server-validated support status: an unsupported or unverifiable
 * statement is never presented as an unconditional fact, and evidence gaps
 * are stated instead of fabricated.
 *
 * `execution_mode` (Demo Replay | Live) and `source_mode`
 * (Fixture | Live | Cached) are orthogonal facts and are always displayed
 * separately; neither is ever inferred from the other.
 */

import { useEffect, useRef, useState } from "react";
import type { PaperSummaryRepository } from "@xingwen/data-access";
import type {
  DomainEntityId,
  Evidence,
  ExecutionMode,
  PaperSummaryEvidenceLocator,
  PaperSummaryReview,
  PaperSummarySourceConflictReview,
  PaperSummaryStatementReview,
} from "@xingwen/domain";
import { safeExternalUrl } from "@xingwen/domain";

import { executionModeLabel } from "../paper-acquisition/paper-acquisition-state";
import { LiteratureComparisonGrid } from "./literature-comparison-grid";
import {
  allStatements,
  classifyPaperSummaryError,
  genericEvidenceForStatement,
  summaryEvidenceForStatement,
  summarySourceModeLabel,
  supportStatusLabel,
  type PaperSummaryReviewState,
} from "./literature-summary-state";

export interface LiteratureSummaryWorkspaceProps {
  readonly artifactVersionId: DomainEntityId;
  /** Latest PaperSummary versions available in the active Run, capped to three. */
  readonly comparisonArtifactVersionIds?: readonly DomainEntityId[];
  readonly repository: PaperSummaryRepository;
  /** The owning ResearchRun's execution mode; display-only. */
  readonly executionMode: ExecutionMode | null;
  readonly ready: boolean;
  readonly disabled: boolean;
  readonly selectedEvidenceId: string | null;
  readonly onSelectEvidence: (evidence: Evidence) => void;
}

function StatusBadge({
  status,
}: {
  readonly status: PaperSummaryStatementReview["status"];
}) {
  return (
    <span className={`paper-summary-badge paper-summary-badge--${status}`}>
      {supportStatusLabel(status)}
    </span>
  );
}

function LocatorDetail({
  locator,
}: {
  readonly locator: PaperSummaryEvidenceLocator;
}) {
  if (locator.kind === "paper_text") {
    return (
      <span className="candidate-meta-item">
        原文位置：章节 {locator.section}
        {locator.paragraph !== null && `・段落 ${String(locator.paragraph)}`}
        {locator.textRange !== "" && `・范围 ${locator.textRange}`}
      </span>
    );
  }
  const safeUrl = safeExternalUrl(locator.sourceUrl);
  return (
    <span className="candidate-meta-item">
      元数据字段 {locator.metadataField}・来源{" "}
      {safeUrl ? (
        <a href={safeUrl} target="_blank" rel="noreferrer noopener">
          {safeUrl}
        </a>
      ) : (
        locator.sourceUrl
      )}
    </span>
  );
}

function StatementItem({
  review,
  statement,
  disabled,
  selectedEvidenceId,
  onSelectEvidence,
}: {
  readonly review: PaperSummaryReview;
  readonly statement: PaperSummaryStatementReview;
  readonly disabled: boolean;
  readonly selectedEvidenceId: string | null;
  readonly onSelectEvidence: (evidence: Evidence) => void;
}) {
  const generic = genericEvidenceForStatement(review, statement.statementId);
  const inlineEvidence = summaryEvidenceForStatement(review, statement);
  const isSelected =
    generic !== null && selectedEvidenceId === String(generic.id);
  return (
    <li
      className="paper-summary-statement"
      aria-current={isSelected ? "true" : undefined}
    >
      <div className="paper-summary-statement-head">
        <button
          type="button"
          className="paper-summary-statement-select"
          aria-pressed={isSelected}
          onClick={() => {
            // Only a real generic Evidence record can drive the observatory;
            // a missing record is stated below and never fabricated.
            if (generic !== null) onSelectEvidence(generic);
          }}
          // Without a generic Evidence record the button would be an enabled
          // no-op; disable it so assistive tech gets an honest affordance.
          disabled={disabled || generic === null}
        >
          {statement.text}
        </button>
        <StatusBadge status={statement.status} />
      </div>
      {generic === null && (
        <p className="paper-summary-no-evidence" role="note">
          无可核验证据：该陈述不能视为已验证事实。
        </p>
      )}
      {inlineEvidence.length > 0 && (
        <ul
          className="paper-summary-evidence"
          aria-label={`证据 ${String(statement.statementId)}`}
        >
          {inlineEvidence.map((item) => (
            <li key={String(item.evidenceId)}>
              <span className="paper-summary-quote">“{item.quoteOrValue}”</span>
              <StatusBadge status={item.status} />
              <LocatorDetail locator={item.locator} />
              <span className="candidate-meta-item">
                快照 {String(item.sourceSnapshotId)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function SourceConflicts({
  conflicts,
}: {
  readonly conflicts: readonly PaperSummarySourceConflictReview[];
}) {
  if (conflicts.length === 0) return null;
  return (
    <section className="alert-panel" role="alert" aria-label="来源版本冲突">
      <h3 className="paper-section-title">来源版本冲突</h3>
      <ul className="candidate-conflicts">
        {conflicts.map((conflict) => (
          <li key={String(conflict.conflictId)}>
            Evidence {String(conflict.evidenceId)}：声称版本{" "}
            {conflict.claimedSourceVersion}，快照版本{" "}
            {conflict.sourceSnapshotVersion}（{conflict.resolution}）
          </li>
        ))}
      </ul>
    </section>
  );
}

export function LiteratureSummaryView({
  review,
  executionMode,
  disabled,
  selectedEvidenceId,
  onSelectEvidence,
}: {
  readonly review: PaperSummaryReview;
  readonly executionMode: ExecutionMode | null;
  readonly disabled: boolean;
  readonly selectedEvidenceId: string | null;
  readonly onSelectEvidence: (evidence: Evidence) => void;
}) {
  return (
    <>
      <p className="candidate-meta" data-testid="paper-summary-provenance">
        <span className="candidate-meta-item">{review.paper.title}</span>
        <span className="candidate-meta-item">
          {review.paper.authors.join("、") || "作者未知"}（
          {review.paper.year ?? "年份未知"}）
        </span>
        <span className="candidate-meta-item">
          ArtifactVersion {String(review.artifactVersionId)}
        </span>
        <span className="candidate-meta-item">
          paper: {String(review.paperId)}
        </span>
        <span className="candidate-meta-item">
          execution: {executionModeLabel(executionMode)}
        </span>
        <span className="candidate-meta-item">
          source: {summarySourceModeLabel(review.sourceMode)}
        </span>
        <span className="candidate-meta-item">
          版本 {String(review.versionNumber)}
          {review.supersedesVersionId === null
            ? "（初始版本）"
            : `（修订自 ${String(review.supersedesVersionId)}）`}
        </span>
        <span className="candidate-meta-item">
          benchmark: {String(review.benchmark.benchmarkId)} v
          {review.benchmark.benchmarkVersion}
        </span>
        <span className="candidate-meta-item">
          model: {review.producer.modelName}
        </span>
        <span className="candidate-meta-item">
          prompt: {String(review.producer.promptName)}{" "}
          {review.producer.promptVersion}（hash{" "}
          {String(review.producer.promptHash)}）
        </span>
        <span className="candidate-meta-item">
          producer: {review.producer.producerName} v
          {review.producer.producerVersion}（{review.producer.status}）
        </span>
        <span className="candidate-meta-item">
          执行记录 {String(review.producerExecution.id)}（
          {review.producerExecution.status}）
        </span>
        <span className="candidate-meta-item">
          输入 PaperCollection{" "}
          {String(review.inputVersions.paperCollectionVersionId)}（hash{" "}
          {String(review.inputVersions.paperCollectionOutputHash)}）
        </span>
        {review.inputVersions.sourceSnapshots.map((snapshot) => (
          <span
            key={String(snapshot.sourceSnapshotId)}
            className="candidate-meta-item"
          >
            输入快照 {String(snapshot.sourceSnapshotId)}（hash{" "}
            {String(snapshot.contentHash)}）
          </span>
        ))}
      </p>
      {review.sourceMode === "cached" && (
        <section
          className="alert-panel"
          role="note"
          aria-label="Cached 来源审计"
        >
          <h3 className="paper-section-title">Cached 来源审计</h3>
          {review.cacheAudits.length === 0 ? (
            <p>缺少 Cached 来源审计，当前产物不可视为完整可复现。</p>
          ) : (
            <ul className="candidate-conflicts">
              {review.cacheAudits.map((audit) => (
                <li
                  key={`${String(audit.sourceId)}-${String(audit.sourceSnapshotId)}`}
                >
                  {String(audit.sourceId)} / cache {audit.cacheVersion} /
                  适用性：
                  {audit.cacheApplicability} / Live 失败：
                  {audit.liveFailureClass} / {audit.liveFailureCode} / origin：
                  {String(audit.originRunId)} /{" "}
                  {String(audit.originArtifactVersionId)}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {review.sourceMode === "fixture" && (
        <p className="candidate-meta">
          <span className="candidate-meta-item">
            确定性演示数据（Fixture，schema v{review.schemaVersion}
            ），由真实总结管线离线生成，非本次实时模型调用。
          </span>
        </p>
      )}
      <SourceConflicts conflicts={review.sourceConflicts} />
      <div className="paper-summary-grid">
        {allStatements(review).map((region) => (
          <section
            key={region.key}
            className="paper-summary-region"
            aria-labelledby={`paper-summary-region-${region.key}`}
          >
            <h3
              id={`paper-summary-region-${region.key}`}
              className="paper-section-title"
            >
              {region.title}
            </h3>
            {region.statements.length === 0 ? (
              <p className="candidate-meta">
                <span className="candidate-meta-item">本区域无陈述。</span>
              </p>
            ) : (
              <ul className="paper-summary-statement-list">
                {region.statements.map((statement) => (
                  <StatementItem
                    key={String(statement.statementId)}
                    review={review}
                    statement={statement}
                    disabled={disabled}
                    selectedEvidenceId={selectedEvidenceId}
                    onSelectEvidence={onSelectEvidence}
                  />
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </>
  );
}

export function LiteratureSummaryWorkspace({
  artifactVersionId,
  comparisonArtifactVersionIds = [],
  repository,
  executionMode,
  ready,
  disabled,
  selectedEvidenceId,
  onSelectEvidence,
}: LiteratureSummaryWorkspaceProps) {
  const [state, setState] = useState<PaperSummaryReviewState>({
    status: "idle",
  });
  const [attempt, setAttempt] = useState(0);
  const [comparisonState, setComparisonState] = useState<
    | { readonly status: "closed" }
    | { readonly status: "loading" }
    | {
        readonly status: "ready";
        readonly reviews: readonly PaperSummaryReview[];
      }
    | { readonly status: "error" }
  >({ status: "closed" });
  const requestSequence = useRef(0);
  const comparisonSequence = useRef(0);

  useEffect(() => {
    const request = ++requestSequence.current;
    // Deferred to a microtask (same pattern as PaperAcquisitionWorkspace) so
    // the effect never sets state synchronously; stale responses are ignored
    // by sequence.
    void Promise.resolve().then(() => {
      if (request !== requestSequence.current) return;
      comparisonSequence.current += 1;
      setComparisonState({ status: "closed" });
      if (!ready) {
        // A stale summary must never survive a session loss or version switch.
        setState({ status: "idle" });
        return;
      }
      setState({ status: "loading" });
      repository.getSummary(artifactVersionId).then(
        (review) => {
          if (request !== requestSequence.current) return;
          setState({ status: "ready", review });
        },
        (error: unknown) => {
          if (request !== requestSequence.current) return;
          setState(classifyPaperSummaryError(error));
        },
      );
    });
    return () => {
      requestSequence.current += 1;
    };
  }, [artifactVersionId, attempt, ready, repository]);

  const retry = () => setAttempt((current) => current + 1);
  const retryButton = (
    <button type="button" onClick={retry} disabled={disabled}>
      重新读取当前版本
    </button>
  );

  if (state.status === "idle" || state.status === "loading") {
    return (
      <section className="work-panel" aria-labelledby="paper-summary-title">
        <h2 id="paper-summary-title">文献总结阅读</h2>
        <p aria-live="polite">正在读取文献总结产物。</p>
      </section>
    );
  }
  if (state.status === "unavailable") {
    return (
      <section
        className="alert-panel"
        role="alert"
        aria-labelledby="paper-summary-title"
      >
        <h2 id="paper-summary-title">文献总结阅读</h2>
        <p>当前 ArtifactVersion 不存在或不可访问，请重新选择 Artifact。</p>
        {retryButton}
      </section>
    );
  }
  if (state.status === "invalid") {
    return (
      <section
        className="alert-panel"
        role="alert"
        aria-labelledby="paper-summary-title"
      >
        <h2 id="paper-summary-title">文献总结阅读</h2>
        <p>产物校验失败：返回内容不符合生成 Contract。</p>
        {retryButton}
      </section>
    );
  }
  if (state.status === "network_error") {
    return (
      <section
        className="alert-panel"
        role="alert"
        aria-labelledby="paper-summary-title"
      >
        <h2 id="paper-summary-title">文献总结阅读</h2>
        <p>网络错误，无法读取文献总结数据。</p>
        {retryButton}
      </section>
    );
  }

  const openComparison = () => {
    const request = ++comparisonSequence.current;
    const ids = [
      ...new Set(
        [artifactVersionId, ...comparisonArtifactVersionIds].map(String),
      ),
    ].slice(0, 3) as DomainEntityId[];
    setComparisonState({ status: "loading" });
    void Promise.all(
      ids.map((id) =>
        String(id) === String(artifactVersionId)
          ? Promise.resolve(state.review)
          : repository.getSummary(id),
      ),
    ).then(
      (reviews) => {
        if (request === comparisonSequence.current) {
          setComparisonState({ status: "ready", reviews });
        }
      },
      () => {
        if (request === comparisonSequence.current) {
          setComparisonState({ status: "error" });
        }
      },
    );
  };

  return (
    <section
      className="work-panel paper-summary"
      aria-labelledby="paper-summary-title"
    >
      <h2 id="paper-summary-title">文献总结阅读</h2>
      {comparisonState.status === "closed" ? (
        <>
          <button type="button" onClick={openComparison} disabled={disabled}>
            打开文献总结对比
          </button>
          <LiteratureSummaryView
            review={state.review}
            executionMode={executionMode}
            disabled={disabled}
            selectedEvidenceId={selectedEvidenceId}
            onSelectEvidence={onSelectEvidence}
          />
        </>
      ) : (
        <>
          <button
            type="button"
            onClick={() => {
              comparisonSequence.current += 1;
              setComparisonState({ status: "closed" });
            }}
            disabled={disabled}
          >
            返回单篇阅读
          </button>
          {comparisonState.status === "loading" && (
            <p aria-live="polite">正在读取对比文献总结。</p>
          )}
          {comparisonState.status === "error" && (
            <section className="alert-panel" role="alert">
              <p>无法读取全部对比文献总结，请返回后重试。</p>
            </section>
          )}
          {comparisonState.status === "ready" && (
            <LiteratureComparisonGrid summaries={comparisonState.reviews} />
          )}
        </>
      )}
    </section>
  );
}
