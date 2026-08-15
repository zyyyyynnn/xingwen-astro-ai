import type {
  PaperSummaryEvidenceReview,
  PaperSummaryReview,
  PaperSummarySectionReview,
  PaperSummaryStatementReview,
  PaperSummarySupportStatus,
  SourceSnapshotSummary,
} from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  ResearchArtifactViewModel,
} from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  CardContent,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Link,
  Separator,
} from "@xingwen/ui";
import { ChevronDown, Maximize2 } from "@xingwen/ui/icons";

import {
  ARTIFACT_CARD_COPY,
  artifactKindLabel,
  executionStatusLabel,
  sourceModeLabel,
  supportStatusLabel,
} from "../presentation/artifact-presentation-labels";

interface PaperSummaryRendererProps {
  readonly artifact: ResearchArtifactViewModel;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly review: PaperSummaryReview;
  readonly surface: "thread" | "docked" | "fullscreen";
  readonly onOpenFullscreen: (() => void) | null;
  readonly onReturnToOverview: (() => void) | null;
}

function SupportBadge({
  status,
}: {
  readonly status: PaperSummarySupportStatus;
}) {
  return (
    <Badge
      variant={status === "supported" ? "secondary" : "outline"}
      data-support-status={status}
    >
      {supportStatusLabel(status)}
    </Badge>
  );
}

function ArtifactStatus({
  sourceMode,
  status,
}: {
  readonly sourceMode: PaperSummaryReview["sourceMode"] | null;
  readonly status: PaperSummaryReview["producerExecution"]["status"];
}) {
  const sourceLabel = sourceMode === null ? null : sourceModeLabel(sourceMode);
  return (
    <div className="artifact-version-identity" aria-label="产物状态">
      <Badge variant="outline">{artifactKindLabel("paper_summary")}</Badge>
      {sourceLabel === null ? null : <span>{sourceLabel}</span>}
      <Badge variant="secondary">{executionStatusLabel(status)}</Badge>
      <span className="sr-only">
        研究产物类型：{artifactKindLabel("paper_summary")}
      </span>
    </div>
  );
}

export function PaperSummaryThreadRenderer({
  review,
}: PaperSummaryRendererProps) {
  const keyFinding = sectionStatements(review.discussion)[0] ?? null;
  return (
    <CardContent className="min-h-[7.75rem]">
      <div className="flex flex-col gap-[var(--oh-space-3)]">
        <div>
          <p className="m-0 text-xs text-[var(--oh-muted)]">
            {ARTIFACT_CARD_COPY.originalPaper}
          </p>
          <p className="mb-0 mt-[var(--oh-space-1)] line-clamp-1 text-sm font-medium leading-6 text-[var(--oh-text)]">
            {review.paper.title}
          </p>
        </div>
        <div>
          <p className="m-0 text-xs text-[var(--oh-muted)]">
            {ARTIFACT_CARD_COPY.keyFinding}
          </p>
          {keyFinding ? (
            <p className="mb-0 mt-[var(--oh-space-1)] line-clamp-3 text-sm leading-6 text-[var(--oh-muted)]">
              {keyFinding.text}
            </p>
          ) : (
            <p className="mb-0 mt-[var(--oh-space-1)] text-sm text-[var(--oh-muted)]">
              {ARTIFACT_CARD_COPY.missingFinding}
            </p>
          )}
        </div>
      </div>
    </CardContent>
  );
}

function EvidenceLocator({
  evidence,
}: {
  readonly evidence: PaperSummaryEvidenceReview;
}) {
  const locator = evidence.locator;
  return (
    <dl className="paper-summary__evidence-meta">
      <div>
        <dt>来源</dt>
        <dd>
          {evidence.sourceId} · {evidence.sourceRecordId}
        </dd>
      </div>
      <div>
        <dt>定位</dt>
        <dd>
          {locator.kind === "paper_text"
            ? [
                locator.section,
                locator.paragraph === null
                  ? null
                  : `第 ${locator.paragraph} 段`,
                locator.textRange,
              ]
                .filter(Boolean)
                .join(" · ")
            : `元数据字段：${locator.metadataField}`}
        </dd>
      </div>
      <div>
        <dt>原文位置</dt>
        <dd>
          {locator.sourceUrl ? (
            <Link href={locator.sourceUrl} external>
              打开来源
            </Link>
          ) : (
            "来源未提供公开地址"
          )}
        </dd>
      </div>
    </dl>
  );
}

function SourceSnapshot({
  snapshot,
  evidence,
}: {
  readonly snapshot: SourceSnapshotSummary | null;
  readonly evidence: PaperSummaryEvidenceReview;
}) {
  if (snapshot === null) {
    return (
      <Alert variant="destructive">
        <AlertTitle>来源快照缺失</AlertTitle>
        <AlertDescription>
          无法核对快照 {evidence.sourceSnapshotId}；此证据不能视为完整可复现。
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <dl className="paper-summary__snapshot">
      <div>
        <dt>来源快照</dt>
        <dd>{snapshot.id}</dd>
      </div>
      <div>
        <dt>版本</dt>
        <dd>{snapshot.sourceVersionOrEtag ?? "来源未提供版本标识"}</dd>
      </div>
      <div>
        <dt>获取时间</dt>
        <dd>{snapshot.retrievedAt}</dd>
      </div>
      <div>
        <dt>许可</dt>
        <dd>{snapshot.licenseNote}</dd>
      </div>
    </dl>
  );
}

function StatementEvidence({
  statement,
  review,
}: {
  readonly statement: PaperSummaryStatementReview;
  readonly review: PaperSummaryReview;
}) {
  const evidenceById = new Map(
    review.summaryEvidence.map((evidence) => [evidence.evidenceId, evidence]),
  );
  const snapshotsById = new Map(
    review.sourceSnapshots.map((snapshot) => [snapshot.id, snapshot]),
  );
  const evidence = statement.evidenceIds
    .map((evidenceId) => evidenceById.get(evidenceId) ?? null)
    .filter((item): item is PaperSummaryEvidenceReview => item !== null);
  const missingIds = statement.evidenceIds.filter(
    (evidenceId) => !evidenceById.has(evidenceId),
  );
  if (statement.evidenceIds.length === 0 || missingIds.length > 0) {
    return (
      <Alert variant="destructive">
        <AlertTitle>证据链不完整</AlertTitle>
        <AlertDescription>
          {statement.evidenceIds.length === 0
            ? "该陈述没有绑定证据。"
            : `缺少证据记录：${missingIds.join(", ")}`}
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="paper-summary__evidence-list">
      {evidence.map((item) => (
        <article key={item.evidenceId} className="paper-summary__evidence">
          <blockquote>{item.quoteOrValue}</blockquote>
          <EvidenceLocator evidence={item} />
          <SourceSnapshot
            snapshot={snapshotsById.get(item.sourceSnapshotId) ?? null}
            evidence={item}
          />
        </article>
      ))}
    </div>
  );
}

function Statement({
  statement,
  review,
}: {
  readonly statement: PaperSummaryStatementReview;
  readonly review: PaperSummaryReview;
}) {
  const needsAttention =
    statement.status !== "supported" || statement.evidenceIds.length === 0;
  return (
    <Collapsible
      className="paper-summary__statement"
      defaultOpen={needsAttention}
    >
      <div className="paper-summary__statement-heading">
        <p>{statement.text}</p>
        <SupportBadge status={statement.status} />
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="查看证据">
            <ChevronDown aria-hidden="true" />
          </Button>
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent className="paper-summary__statement-evidence">
        <StatementEvidence statement={statement} review={review} />
      </CollapsibleContent>
    </Collapsible>
  );
}

function SummarySection({
  title,
  statements,
  review,
}: {
  readonly title: string;
  readonly statements: readonly PaperSummaryStatementReview[];
  readonly review: PaperSummaryReview;
}) {
  return (
    <section className="paper-summary__section">
      <h3>{title}</h3>
      {statements.length > 0 ? (
        <div className="paper-summary__statements">
          {statements.map((statement) => (
            <Statement
              key={statement.statementId}
              statement={statement}
              review={review}
            />
          ))}
        </div>
      ) : (
        <p className="paper-summary__empty">该版本未提供此部分。</p>
      )}
    </section>
  );
}

function TechnicalProvenance({
  review,
}: {
  readonly review: PaperSummaryReview;
}) {
  return (
    <Collapsible className="paper-summary__provenance">
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="small">
          技术溯源
          <ChevronDown aria-hidden="true" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <dl>
          <div>
            <dt>ArtifactVersion</dt>
            <dd>{review.artifactVersionId}</dd>
          </div>
          <div>
            <dt>Schema / 来源模式</dt>
            <dd>
              {review.schemaVersion} / {review.sourceMode}
            </dd>
          </div>
          <div>
            <dt>Producer</dt>
            <dd>
              {review.producer.producerName} {review.producer.producerVersion} ·{" "}
              {review.producer.status}
            </dd>
          </div>
          <div>
            <dt>执行记录</dt>
            <dd>
              {review.producerExecution.id} · {review.producerExecution.status}
            </dd>
          </div>
          <div>
            <dt>内容 / 输入哈希</dt>
            <dd>
              {review.contentHash} / {review.inputHash}
            </dd>
          </div>
        </dl>
      </CollapsibleContent>
    </Collapsible>
  );
}

function sectionStatements(
  section: PaperSummarySectionReview,
): readonly PaperSummaryStatementReview[] {
  return section.overview === null
    ? section.items
    : [section.overview, ...section.items];
}

export function PaperSummaryDetailRenderer({
  artifact,
  review,
  surface,
  onOpenFullscreen,
  onReturnToOverview,
}: PaperSummaryRendererProps) {
  return (
    <article
      className="paper-summary"
      data-artifact-version-id={review.artifactVersionId}
      data-surface={surface}
    >
      <header className="paper-summary__header">
        {onReturnToOverview ? (
          <Button variant="ghost" size="small" onClick={onReturnToOverview}>
            返回研究概览
          </Button>
        ) : null}
        <p className="paper-summary__eyebrow">论文摘要报告</p>
        <h2>{review.paper.title || artifact.title}</h2>
        <p className="paper-summary__byline">
          {review.paper.authors.join("、") || "作者信息缺失"}
          {review.paper.year === null ? "" : ` · ${review.paper.year}`}
        </p>
        <ArtifactStatus
          sourceMode={review.sourceMode}
          status={review.producerExecution.status}
        />
        {onOpenFullscreen ? (
          <Button variant="secondary" size="small" onClick={onOpenFullscreen}>
            <Maximize2 data-icon="inline-start" aria-hidden="true" />
            全屏阅读
          </Button>
        ) : null}
      </header>
      <Separator />
      <SummarySection
        title="研究背景"
        statements={sectionStatements(review.background)}
        review={review}
      />
      <SummarySection
        title="研究方法"
        statements={sectionStatements(review.methodology)}
        review={review}
      />
      <SummarySection
        title="数据集"
        statements={sectionStatements(review.dataset)}
        review={review}
      />
      <SummarySection
        title="实验与结果"
        statements={sectionStatements(review.experiments)}
        review={review}
      />
      <SummarySection
        title="讨论与结论"
        statements={sectionStatements(review.discussion)}
        review={review}
      />
      <SummarySection
        title="局限性"
        statements={sectionStatements(review.limitations)}
        review={review}
      />
      <SummarySection
        title="研究问题"
        statements={sectionStatements(review.researchQuestions)}
        review={review}
      />
      {review.sourceConflicts.length > 0 ? (
        <Alert variant="destructive">
          <AlertTitle>来源版本存在冲突</AlertTitle>
          <AlertDescription>
            {review.sourceConflicts
              .map((conflict) => conflict.resolution)
              .join("；")}
          </AlertDescription>
        </Alert>
      ) : null}
      <Separator />
      <TechnicalProvenance review={review} />
    </article>
  );
}
