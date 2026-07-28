/**
 * Paper Acquisition Workspace (A-05) — the central-canvas review surface for
 * a `paper_collection` ArtifactVersion.
 *
 * Consumes only the `PaperAcquisitionRepository` port and domain models; it
 * never sees URLs, DTOs, cursors or envelopes. Continuous divided panels
 * (no card walls), light system only, and the server ranking order is never
 * recomputed — filters only hide rows while `stableRank` stays visible.
 *
 * `execution_mode` (Demo Replay | Live) and `source_mode`
 * (Fixture | Live | Cached) are orthogonal facts and are always displayed
 * separately; neither is ever inferred from the other.
 */

import { useEffect, useRef, useState } from "react";
import type { PaperAcquisitionRepository } from "@xingwen/data-access";
import type {
  DomainEntityId,
  Evidence,
  ExecutionMode,
  PaperAcquisitionReview,
  PaperCandidateReview,
  PaperSourceExecutionReview,
  ReviewMetadataEntry,
} from "@xingwen/domain";

import { CandidateReviewList } from "./candidate-review-list";
import {
  classifyPaperReviewError,
  EMPTY_CANDIDATE_FILTER,
  executionModeLabel,
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
  readonly executionMode: ExecutionMode | null;
  readonly ready: boolean;
  readonly disabled: boolean;
  readonly selectedCandidateId: string | null;
  readonly onSelectCandidate: (candidate: PaperCandidateReview) => void;
  readonly onSelectEvidence: (evidence: Evidence) => void;
}

function MetadataEntries({
  entries,
}: {
  readonly entries: readonly ReviewMetadataEntry[];
}) {
  if (entries.length === 0) {
    return <span className="candidate-meta-item">（无）</span>;
  }
  return (
    <>
      {entries.map((entry) => (
        <span key={entry.key} className="candidate-meta-item">
          {entry.key}: {entry.value}
        </span>
      ))}
    </>
  );
}

function SourceExecutionAudit({
  execution,
}: {
  readonly execution: PaperSourceExecutionReview;
}) {
  return (
    <details className="paper-execution-details">
      <summary>
        {String(execution.sourceId)}・
        {execution.status === "completed" ? "完成" : "失败"}
        {execution.failureClass !== null && `（${execution.failureClass}）`}・
        {execution.candidateCount} 候选・source {sourceModeLabelOf(execution)}
      </summary>
      <dl className="paper-dl">
        <dt>data level</dt>
        <dd>{execution.dataLevel}</dd>
        <dt>retry count</dt>
        <dd>{execution.retryCount}</dd>
        <dt>query hash</dt>
        <dd>{String(execution.queryHash)}</dd>
        <dt>request parameters hash</dt>
        <dd>{String(execution.requestParametersHash)}</dd>
        <dt>pagination</dt>
        <dd>
          page_size {execution.pagination.pageSize} / max_pages{" "}
          {execution.pagination.maxPages} / candidate_limit{" "}
          {execution.pagination.candidateLimit}
        </dd>
        <dt>snapshot</dt>
        <dd>
          {execution.sourceSnapshotId !== null
            ? String(execution.sourceSnapshotId)
            : "无"}
        </dd>
        <dt>时间</dt>
        <dd>
          {execution.startedAt} → {execution.finishedAt}
        </dd>
      </dl>
      {execution.pages.length > 0 && (
        <table className="paper-page-table">
          <caption>来源分页请求</caption>
          <thead>
            <tr>
              <th scope="col">page</th>
              <th scope="col">offset</th>
              <th scope="col">req/ret rows</th>
              <th scope="col">total</th>
              <th scope="col">attempt</th>
              <th scope="col">status</th>
              <th scope="col">retrieved</th>
              <th scope="col">request hash</th>
              <th scope="col">response hash</th>
              <th scope="col">rate limit</th>
            </tr>
          </thead>
          <tbody>
            {execution.pages.map((page) => (
              <tr key={page.pageNumber}>
                <td>{page.pageNumber}</td>
                <td>{page.offset}</td>
                <td>
                  {page.requestedRows}/{page.returnedRows}
                </td>
                <td>{page.totalResults ?? "—"}</td>
                <td>{page.attemptCount}</td>
                <td>{page.statusCode}</td>
                <td>{page.retrievedAt}</td>
                <td className="paper-hash-cell">{String(page.requestHash)}</td>
                <td className="paper-hash-cell">{String(page.responseHash)}</td>
                <td>
                  {page.rateLimitMetadata.length > 0 ? (
                    <MetadataEntries entries={page.rateLimitMetadata} />
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </details>
  );
}

function sourceModeLabelOf(execution: PaperSourceExecutionReview): string {
  switch (execution.sourceMode) {
    case "fixture":
      return "Fixture";
    case "cached":
      return "Cached";
    case "live":
      return "Live";
  }
}

function CachedProvenance({
  review,
}: {
  readonly review: PaperAcquisitionReview;
}) {
  const cachedExecutions = review.sourceExecutions.filter(
    (execution) => execution.sourceMode === "cached",
  );
  if (cachedExecutions.length === 0) return null;
  const originSnapshots = review.sourceSnapshots.filter(
    (snapshot) => snapshot.cachedOrigin !== null,
  );
  return (
    <section className="paper-cached-audit" aria-label="缓存审计">
      <h3 className="paper-section-title">Cached 审计</h3>
      {cachedExecutions.map((execution) => (
        <dl className="paper-dl" key={String(execution.sourceId)}>
          <dt>来源</dt>
          <dd>{String(execution.sourceId)}</dd>
          <dt>缓存适用性</dt>
          <dd>{execution.cache?.applicability}</dd>
          <dt>本次 Live 失败</dt>
          <dd>
            {execution.cache
              ? `${execution.cache.liveFailureClass}（${execution.cache.liveFailureCode}）`
              : "—"}
          </dd>
        </dl>
      ))}
      {originSnapshots.map((snapshot) => (
        <dl className="paper-dl" key={String(snapshot.id)}>
          <dt>origin Run</dt>
          <dd>{String(snapshot.cachedOrigin?.originRunId)}</dd>
          <dt>origin ArtifactVersion</dt>
          <dd>{String(snapshot.cachedOrigin?.originArtifactVersionId)}</dd>
          <dt>cache version</dt>
          <dd>{snapshot.cacheVersion ?? "—"}</dd>
          <dt>快照时间</dt>
          <dd>{snapshot.retrievedAt}</dd>
        </dl>
      ))}
      <p className="candidate-meta">
        <span className="candidate-meta-item">
          此结果来自真实历史 Run 的缓存，不代表本次实时检索。如需刷新，请以 Live
          模式重新启动检索 Run；当前工作区不提供一键重跑。
        </span>
      </p>
    </section>
  );
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
    const request = ++requestSequence.current;
    // Deferred to a microtask (same pattern as WorkspacePage) so the effect
    // never sets state synchronously; stale responses are ignored by sequence.
    void Promise.resolve().then(() => {
      if (request !== requestSequence.current) return;
      if (!ready) {
        // A stale review must never survive a session loss or version switch.
        setState({ status: "idle" });
        return;
      }
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
  if (state.status === "unavailable") {
    return (
      <section
        className="alert-panel"
        role="alert"
        aria-labelledby="paper-review-title"
      >
        <h2 id="paper-review-title">论文获取与候选审查</h2>
        <p>当前 ArtifactVersion 不存在或不可访问，请重新选择 Artifact。</p>
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
          execution: {executionModeLabel(executionMode)}
        </span>
        <span className="candidate-meta-item">
          source: {sourceModeLabel(review)}
        </span>
        <span className="candidate-meta-item">
          benchmark: {String(review.benchmark.benchmarkId)} v
          {review.benchmark.benchmarkVersion}
        </span>
        <span className="candidate-meta-item">
          scenario: {String(review.benchmark.scenarioId)}
        </span>
      </p>
      {review.sourceMode === "fixture" && (
        <p className="candidate-meta">
          <span className="candidate-meta-item">
            Fixture 确定性演示数据（schema v{review.schemaVersion}
            ），由真实获取管线离线生成，非本次实时检索。
          </span>
        </p>
      )}
      {review.sourceMode === "cached" && (
        <p className="candidate-meta">
          <span className="candidate-meta-item">
            Cached 结果：详见下方缓存审计；不代表本次实时检索。
          </span>
        </p>
      )}

      <div className="paper-review-grid">
        <div className="paper-review-main">
          <h3 className="paper-section-title">检索与来源</h3>
          <dl className="paper-dl">
            <dt>Query</dt>
            <dd>{review.query.normalizedQuery}</dd>
            <dt>原始 Query</dt>
            <dd>{review.query.originalQuery}</dd>
            <dt>query id</dt>
            <dd>{String(review.query.queryId)}</dd>
            <dt>normalization</dt>
            <dd>v{review.query.normalizationRuleVersion}</dd>
            <dt>关键词</dt>
            <dd>{review.query.normalizedKeywords.join("、")}</dd>
            <dt>原始关键词</dt>
            <dd>{review.query.originalKeywords.join("、")}</dd>
            <dt>年份</dt>
            <dd>
              {review.query.yearFrom}–{review.query.yearTo}
            </dd>
            <dt>排序</dt>
            <dd>{review.query.sortStrategy}</dd>
            <dt>分页</dt>
            <dd>
              page_size {review.query.pagination.pageSize} / max_pages{" "}
              {review.query.pagination.maxPages} / 候选上限{" "}
              {review.query.pagination.candidateLimit}
            </dd>
            <dt>query hash</dt>
            <dd>{String(review.query.queryHash)}</dd>
          </dl>
          {review.query.sourceParameters.map((entry) => (
            <details
              key={String(entry.sourceId)}
              className="paper-execution-details"
            >
              <summary>来源参数 {String(entry.sourceId)}</summary>
              <p className="candidate-meta">
                <MetadataEntries entries={entry.parameters} />
              </p>
            </details>
          ))}
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
                <SourceExecutionAudit execution={execution} />
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
          <CachedProvenance review={review} />

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
              期望 {review.metrics.expectedCandidateCount} / 召回{" "}
              {review.metrics.recalledExpectedCandidateCount}
              {review.metrics.candidateRecall !== null &&
                `（recall ${String(review.metrics.candidateRecall)}）`}
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
          <dl className="paper-dl">
            <dt>dedupe</dt>
            <dd>
              {review.rules.dedupeRule} v{review.rules.dedupeVersion}
            </dd>
            <dt>ranking</dt>
            <dd>
              {review.rules.rankingRule} v{review.rules.rankingVersion}
            </dd>
            <dt>selection</dt>
            <dd>
              v{review.rules.selectionVersion}（limit{" "}
              {review.rules.selectionLimit}）
            </dd>
            <dt>normalization</dt>
            <dd>v{review.rules.queryNormalizationVersion}</dd>
            <dt>canonicalization</dt>
            <dd>v{review.rules.canonicalizationVersion}</dd>
            <dt>adapter</dt>
            <dd>
              {review.rules.adapterName} v{review.rules.adapterVersion}
            </dd>
            <dt>retry policy</dt>
            <dd>v{review.rules.retryPolicyVersion}</dd>
            <dt>source policy</dt>
            <dd>v{review.rules.sourcePolicyVersion}</dd>
          </dl>
          <h3 className="paper-section-title">复现标识</h3>
          <dl className="paper-dl">
            <dt>content hash</dt>
            <dd>{String(review.contentHash)}</dd>
            <dt>input hash</dt>
            <dd>{String(review.inputHash)}</dd>
            <dt>benchmark payload hash</dt>
            <dd>{String(review.benchmark.contentHash)}</dd>
            <dt>producer</dt>
            <dd>
              {review.producerExecution.producerName} v
              {review.producerExecution.producerVersion}（
              {review.producerExecution.status}）
            </dd>
            <dt>producer input/output</dt>
            <dd>
              {String(review.producerExecution.inputHash)} /{" "}
              {review.producerExecution.outputHash !== null
                ? String(review.producerExecution.outputHash)
                : "无"}
            </dd>
          </dl>
          <h3 className="paper-section-title">SourceSnapshot</h3>
          {review.sourceSnapshots.map((snapshot) => (
            <dl className="paper-dl" key={String(snapshot.id)}>
              <dt>snapshot</dt>
              <dd>
                {String(snapshot.id)} / {String(snapshot.sourceId)}
              </dd>
              <dt>retrieved</dt>
              <dd>{snapshot.retrievedAt}</dd>
              <dt>license</dt>
              <dd>{snapshot.licenseNote}</dd>
              <dt>request metadata</dt>
              <dd>
                <MetadataEntries entries={snapshot.requestMetadata} />
              </dd>
            </dl>
          ))}
        </aside>
      </div>
    </section>
  );
}
