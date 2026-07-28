/**
 * Paper Acquisition Workspace (A-05) — the central-canvas review surface for
 * a `paper_collection` ArtifactVersion.
 *
 * Consumes only the `PaperAcquisitionRepository` port and domain models; it
 * never sees URLs, DTOs, cursors or envelopes. Continuous divided panels
 * (no card walls), light system only, and the server ranking order is never
 * recomputed — filters only hide rows while `stableRank` stays visible.
 */

import { useEffect, useRef, useState } from "react";
import type { PaperAcquisitionRepository } from "@xingwen/data-access";
import type {
  DomainEntityId,
  Evidence,
  PaperCandidateReview,
} from "@xingwen/domain";

import { CandidateReviewList } from "./candidate-review-list";
import {
  classifyPaperReviewError,
  EMPTY_CANDIDATE_FILTER,
  failedSourceExecutions,
  filterCandidates,
  sourceIdsOf,
  sourceModeLabel,
  type CandidateFilter,
  type GroupingFilter,
  type PaperReviewState,
  type SelectionFilter,
} from "./paper-acquisition-state";

export interface PaperAcquisitionWorkspaceProps {
  readonly artifactVersionId: DomainEntityId;
  readonly repository: PaperAcquisitionRepository;
  /** The owning ResearchRun's execution mode; display-only. */
  readonly executionMode: string | null;
  readonly ready: boolean;
  readonly disabled: boolean;
  readonly selectedCandidateId: string | null;
  readonly onSelectCandidate: (candidate: PaperCandidateReview) => void;
  readonly onSelectEvidence: (evidence: Evidence) => void;
}

export function PaperAcquisitionWorkspace({
  artifactVersionId,
  repository,
  executionMode,
  ready,
  disabled,
  selectedCandidateId,
  onSelectCandidate,
  onSelectEvidence,
}: PaperAcquisitionWorkspaceProps) {
  const [state, setState] = useState<PaperReviewState>({ status: "idle" });
  const [filter, setFilter] = useState<CandidateFilter>(EMPTY_CANDIDATE_FILTER);
  const [attempt, setAttempt] = useState(0);
  const requestSequence = useRef(0);

  useEffect(() => {
    if (!ready) return;
    const request = ++requestSequence.current;
    // Deferred to a microtask (same pattern as WorkspacePage) so the effect
    // never sets state synchronously; stale responses are ignored by sequence.
    void Promise.resolve().then(() => {
      if (request !== requestSequence.current) return;
      setState({ status: "loading" });
      setFilter(EMPTY_CANDIDATE_FILTER);
      repository.getReview(artifactVersionId).then(
        (review) => {
          if (request !== requestSequence.current) return;
          setState({ status: "ready", review });
        },
        (error: unknown) => {
          if (request !== requestSequence.current) return;
          setState(classifyPaperReviewError(error));
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
      <section className="work-panel" aria-labelledby="paper-review-title">
        <h2 id="paper-review-title">论文获取与候选审查</h2>
        <p aria-live="polite">正在读取论文获取产物与候选列表。</p>
      </section>
    );
  }
  if (state.status === "empty") {
    return (
      <section className="work-panel" aria-labelledby="paper-review-title">
        <h2 id="paper-review-title">论文获取与候选审查</h2>
        <p aria-live="polite">当前 ArtifactVersion 没有候选论文。</p>
        {retryButton}
      </section>
    );
  }
  if (state.status === "rate_limited") {
    return (
      <section
        className="alert-panel"
        role="alert"
        aria-labelledby="paper-review-title"
      >
        <h2 id="paper-review-title">论文获取与候选审查</h2>
        <p>
          论文来源限流。
          {state.retryAfterMs !== null
            ? `约 ${String(Math.ceil(state.retryAfterMs / 1000))} 秒后可重试。`
            : "请稍后重试。"}
        </p>
        {retryButton}
      </section>
    );
  }
  if (state.status === "source_failed") {
    return (
      <section
        className="alert-panel"
        role="alert"
        aria-labelledby="paper-review-title"
      >
        <h2 id="paper-review-title">论文获取与候选审查</h2>
        <p>论文来源失败，本次获取未产出可发布的候选集合。</p>
        {retryButton}
      </section>
    );
  }
  if (state.status === "invalid") {
    return (
      <section
        className="alert-panel"
        role="alert"
        aria-labelledby="paper-review-title"
      >
        <h2 id="paper-review-title">论文获取与候选审查</h2>
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
        aria-labelledby="paper-review-title"
      >
        <h2 id="paper-review-title">论文获取与候选审查</h2>
        <p>网络错误，无法读取候选审查数据。</p>
        {retryButton}
      </section>
    );
  }

  const { review } = state;
  const failedSources = failedSourceExecutions(review);
  const filtered = filterCandidates(review.candidates, filter);
  const setFilterField = (patch: Partial<CandidateFilter>) =>
    setFilter((current) => ({ ...current, ...patch }));

  return (
    <section
      className="work-panel paper-review"
      aria-labelledby="paper-review-title"
    >
      <h2 id="paper-review-title">论文获取与候选审查</h2>
      <p className="candidate-meta" data-testid="paper-review-provenance">
        <span className="candidate-meta-item">
          ArtifactVersion {String(review.artifactVersionId)}
        </span>
        <span className="candidate-meta-item">
          execution: {executionMode ?? "未知"}
        </span>
        <span className="candidate-meta-item">
          source: {sourceModeLabel(review)}
        </span>
        <span className="candidate-meta-item">
          benchmark: {String(review.benchmark.benchmarkId)} v
          {review.benchmark.benchmarkVersion}
        </span>
      </p>
      {review.sourceMode === "fixture" && (
        <p className="candidate-meta">
          <span className="candidate-meta-item">
            Demo Replay 确定性演示数据（scenario{" "}
            {String(review.benchmark.scenarioId)}，schema v
            {review.schemaVersion}），非本次实时检索。
          </span>
        </p>
      )}
      {review.sourceMode === "cached" && (
        <p className="candidate-meta">
          <span className="candidate-meta-item">
            Cached 结果，快照时间见来源执行；不代表本次实时检索。
          </span>
        </p>
      )}

      <div className="paper-review-grid">
        <div className="paper-review-main">
          <h3 className="paper-section-title">检索与来源</h3>
          <p className="candidate-meta">
            <span className="candidate-meta-item">
              Query: {review.query.normalizedQuery}
            </span>
            <span className="candidate-meta-item">
              原始: {review.query.originalQuery}
            </span>
          </p>
          <p className="candidate-meta">
            <span className="candidate-meta-item">
              关键词: {review.query.keywords.join("、")}
            </span>
            <span className="candidate-meta-item">
              年份: {review.query.yearFrom}–{review.query.yearTo}
            </span>
            <span className="candidate-meta-item">
              排序: {review.query.sortStrategy}
            </span>
            <span className="candidate-meta-item">
              候选上限: {review.query.candidateLimit}
            </span>
          </p>
          <p className="candidate-meta">
            <span className="candidate-meta-item">
              获取 {review.acquisition.startedAt} →{" "}
              {review.acquisition.finishedAt}
            </span>
            <span className="candidate-meta-item">
              状态: {review.acquisition.status}
            </span>
          </p>
          <ul className="source-execution-list" aria-label="来源执行">
            {review.sourceExecutions.map((execution) => (
              <li key={String(execution.sourceId)}>
                <span>{String(execution.sourceId)}</span>
                <span>
                  {execution.status === "completed" ? "完成" : "失败"}
                  {execution.failureClass !== null &&
                    `（${execution.failureClass}）`}
                  ・{execution.candidateCount} 候选・retrieved{" "}
                  {execution.pages[0]?.retrievedAt ?? execution.finishedAt}
                </span>
              </li>
            ))}
          </ul>
          {review.acquisition.status === "partial" && (
            <div className="alert-panel" role="alert">
              <p>
                本次获取为部分成功：保留成功来源与候选；失败来源：
                {failedSources.length > 0
                  ? failedSources
                      .map(
                        (execution) =>
                          `${String(execution.sourceId)}（${execution.failureClass ?? execution.failureCode ?? "未知"}）`,
                      )
                      .join("、")
                  : "未提供明细"}
                。
              </p>
            </div>
          )}

          <h3 className="paper-section-title">指标</h3>
          <p className="candidate-meta">
            <span className="candidate-meta-item">
              候选 {review.metrics.candidateCount}
            </span>
            <span className="candidate-meta-item">
              入选 {review.metrics.selectedCount}
            </span>
            <span className="candidate-meta-item">
              重复 {review.metrics.duplicateCandidateCount}（rate{" "}
              {review.metrics.duplicateRate}）
            </span>
            <span className="candidate-meta-item">
              来源失败 {review.metrics.sourceFailureCount} / 空结果{" "}
              {review.metrics.sourceEmptyResultCount}
            </span>
          </p>

          <h3 className="paper-section-title">筛选</h3>
          <div className="paper-filter-bar">
            <label>
              标题或作者
              <input
                value={filter.text}
                onChange={(event) =>
                  setFilterField({ text: event.target.value })
                }
                disabled={disabled}
              />
            </label>
            <label>
              入选状态
              <select
                value={filter.selection}
                onChange={(event) =>
                  setFilterField({
                    selection: event.target.value as SelectionFilter,
                  })
                }
                disabled={disabled}
              >
                <option value="all">全部</option>
                <option value="selected">入选</option>
                <option value="excluded">排除</option>
              </select>
            </label>
            <label>
              来源
              <select
                value={filter.sourceId}
                onChange={(event) =>
                  setFilterField({ sourceId: event.target.value })
                }
                disabled={disabled}
              >
                <option value="all">全部来源</option>
                {sourceIdsOf(review).map((sourceId) => (
                  <option key={sourceId} value={sourceId}>
                    {sourceId}
                  </option>
                ))}
              </select>
            </label>
            <label>
              重复与冲突
              <select
                value={filter.grouping}
                onChange={(event) =>
                  setFilterField({
                    grouping: event.target.value as GroupingFilter,
                  })
                }
                disabled={disabled}
              >
                <option value="all">全部</option>
                <option value="duplicates">仅重复组</option>
                <option value="conflicts">仅冲突</option>
              </select>
            </label>
            <button
              type="button"
              onClick={() => setFilter(EMPTY_CANDIDATE_FILTER)}
              disabled={disabled}
            >
              重置筛选
            </button>
          </div>
          <p aria-live="polite" className="candidate-meta">
            <span className="candidate-meta-item">
              显示 {filtered.length} / {review.candidates.length}{" "}
              项，按原始稳定排名。
            </span>
          </p>

          <h3 className="paper-section-title">候选列表</h3>
          <CandidateReviewList
            candidates={filtered}
            selectedCandidateId={selectedCandidateId}
            disabled={disabled}
            onSelectCandidate={onSelectCandidate}
            onSelectEvidence={onSelectEvidence}
          />
        </div>

        <aside className="paper-review-aside" aria-label="检索详情">
          <h3 className="paper-section-title">规则版本</h3>
          <p className="candidate-meta">
            <span className="candidate-meta-item">
              dedupe: {review.rules.dedupeRule} v{review.rules.dedupeVersion}
            </span>
            <span className="candidate-meta-item">
              ranking: {review.rules.rankingRule} v{review.rules.rankingVersion}
            </span>
            <span className="candidate-meta-item">
              selection: v{review.rules.selectionVersion}（limit{" "}
              {review.rules.selectionLimit}）
            </span>
            <span className="candidate-meta-item">
              adapter: {review.rules.adapterName} v{review.rules.adapterVersion}
            </span>
          </p>
          <h3 className="paper-section-title">复现标识</h3>
          <p className="candidate-meta">
            <span className="candidate-meta-item">
              query hash: {String(review.query.queryHash)}
            </span>
            <span className="candidate-meta-item">
              content hash: {String(review.contentHash)}
            </span>
            <span className="candidate-meta-item">
              input hash: {String(review.inputHash)}
            </span>
            <span className="candidate-meta-item">
              producer: {review.producerExecution.producerName} v
              {review.producerExecution.producerVersion}（
              {review.producerExecution.status}）
            </span>
          </p>
        </aside>
      </div>
    </section>
  );
}
