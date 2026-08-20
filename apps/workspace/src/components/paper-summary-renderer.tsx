import { useState } from "react";
import type {
  PaperSummaryEvidenceReview,
  PaperSummaryReview,
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
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  Quote,
} from "@xingwen/ui/icons";

import {
  ARTIFACT_CARD_COPY,
  supportStatusLabel,
} from "../presentation/artifact-presentation-labels";

interface PaperSummaryRendererProps {
  readonly artifact: ResearchArtifactViewModel;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly review: PaperSummaryReview;
  /** Jump the linked PDF to a page (0-based) when a reliable locator exists. */
  readonly onJumpToPage?: ((pageIndex: number) => void) | null;
}

function SupportBadge({
  status,
}: {
  readonly status: PaperSummarySupportStatus;
}) {
  const isSupported = status === "supported";
  return (
    <Badge
      variant={isSupported ? "secondary" : "outline"}
      data-support-status={status}
      className={
        isSupported
          ? "gap-1 border-transparent bg-[var(--oh-surface-raised)] text-xs text-[var(--oh-status-success)]"
          : "gap-1 text-xs text-[var(--oh-warning)]"
      }
    >
      {isSupported ? (
        <CheckCircle2 className="size-3" aria-hidden="true" />
      ) : (
        <AlertCircle className="size-3" aria-hidden="true" />
      )}
      {supportStatusLabel(status)}
    </Badge>
  );
}

export function PaperSummaryThreadRenderer({
  review,
}: PaperSummaryRendererProps) {
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
          {review.experiments[0] ? (
            <p className="mb-0 mt-[var(--oh-space-1)] line-clamp-3 text-sm leading-6 text-[var(--oh-muted)]">
              {review.experiments[0].text}
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
  onJumpToPage,
}: {
  readonly evidence: PaperSummaryEvidenceReview;
  readonly onJumpToPage?: ((pageIndex: number) => void) | null;
}) {
  const locator = evidence.locator;
  const pageIndex = locator.kind === "paper_text" ? locator.pageIndex : null;
  const locationString =
    locator.kind === "paper_text"
      ? [
          locator.section,
          locator.paragraph === null ? null : `第 ${locator.paragraph} 段`,
          pageIndex === null ? null : `第 ${pageIndex + 1} 页`,
          locator.textRange,
        ]
          .filter(Boolean)
          .join(" · ")
      : `元数据字段：${locator.metadataField}`;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--oh-muted)]">
      <span className="text-xs">{locationString}</span>
      {pageIndex !== null && onJumpToPage ? (
        <Button
          variant="ghost"
          size="small"
          className="px-0 text-xs font-medium text-[var(--oh-accent)] hover:underline"
          onClick={() => onJumpToPage(pageIndex)}
          aria-label={`跳转到论文第 ${pageIndex + 1} 页`}
        >
          跳转到对应页码
        </Button>
      ) : null}
      {locator.sourceUrl !== null ? (
        <Link
          href={locator.sourceUrl}
          external
          className="inline-flex items-center gap-1 text-xs font-medium text-[var(--oh-accent)] hover:underline"
        >
          <span>打开来源</span>
          <ExternalLink className="size-3" aria-hidden="true" />
        </Link>
      ) : null}
    </div>
  );
}

function SourceSnapshot({
  snapshot,
}: {
  readonly snapshot: SourceSnapshotSummary | null;
}) {
  if (snapshot === null) {
    return (
      <Alert variant="destructive" className="mt-2">
        <AlertTitle>来源快照缺失</AlertTitle>
        <AlertDescription>
          无法核对该证据绑定的来源快照；此证据不能视为完整可复现。
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="mt-2 text-xs text-[var(--oh-muted)]">
      <span>获取时间：{snapshot.retrievedAt}</span>
    </div>
  );
}

function StatementEvidence({
  statement,
  review,
  onJumpToPage,
}: {
  readonly statement: PaperSummaryStatementReview;
  readonly review: PaperSummaryReview;
  readonly onJumpToPage?: ((pageIndex: number) => void) | null;
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
      <Alert variant="destructive" className="mt-2">
        <AlertTitle>证据链不完整</AlertTitle>
        <AlertDescription>
          {statement.evidenceIds.length === 0
            ? "该陈述没有绑定证据。"
            : "该陈述绑定的部分证据记录缺失。"}
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="paper-summary__evidence-list mt-2 flex flex-col gap-2.5">
      {evidence.map((item) => (
        <article key={item.evidenceId} className="paper-summary__evidence">
          <div className="flex items-start gap-2">
            <Quote
              className="size-3.5 shrink-0 text-[var(--oh-accent)] opacity-80"
              aria-hidden="true"
            />
            <blockquote className="m-0 text-xs leading-relaxed text-[var(--oh-text)]">
              {item.quoteOrValue}
            </blockquote>
          </div>
          <div className="mt-2 border-t border-[var(--oh-border)] pt-2">
            <EvidenceLocator evidence={item} onJumpToPage={onJumpToPage} />
          </div>
          <SourceSnapshot
            snapshot={snapshotsById.get(item.sourceSnapshotId) ?? null}
          />
        </article>
      ))}
    </div>
  );
}

function Statement({
  statement,
  review,
  forceOpen,
  onJumpToPage,
}: {
  readonly statement: PaperSummaryStatementReview;
  readonly review: PaperSummaryReview;
  readonly forceOpen?: boolean | null;
  readonly onJumpToPage?: ((pageIndex: number) => void) | null;
}) {
  const needsAttention =
    statement.status !== "supported" || statement.evidenceIds.length === 0;
  const [isOpen, setIsOpen] = useState(needsAttention);
  const effectiveOpen = forceOpen ?? isOpen;

  return (
    <Collapsible
      open={effectiveOpen}
      onOpenChange={setIsOpen}
      className="paper-summary__statement group/statement"
    >
      <div className="paper-summary__statement-heading flex items-start justify-between gap-3">
        <p className="m-0 flex-1 text-xs leading-relaxed text-[var(--oh-text)]">
          {statement.text}
        </p>
        <div className="flex shrink-0 items-center gap-1.5 pt-0.5">
          {statement.status === "supported" ? null : (
            <SupportBadge status={statement.status} />
          )}
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-6 p-0 text-[var(--oh-muted)] hover:text-[var(--oh-text)]"
              aria-label="查看证据"
            >
              <ChevronDown
                className="xw-disclosure-chevron size-3.5 group-data-[state=open]/statement:rotate-180"
                aria-hidden="true"
              />
            </Button>
          </CollapsibleTrigger>
        </div>
      </div>
      <CollapsibleContent className="paper-summary__statement-evidence pt-1">
        <StatementEvidence
          statement={statement}
          review={review}
          onJumpToPage={onJumpToPage}
        />
      </CollapsibleContent>
    </Collapsible>
  );
}

function SummarySection({
  title,
  statements,
  review,
  forceOpen,
  onJumpToPage,
}: {
  readonly title: string;
  readonly statements: readonly PaperSummaryStatementReview[];
  readonly review: PaperSummaryReview;
  readonly forceOpen?: boolean | null;
  readonly onJumpToPage?: ((pageIndex: number) => void) | null;
}) {
  return (
    <section className="paper-summary__section">
      <div className="flex items-center justify-between pb-1">
        <h3 className="text-xs font-semibold text-[var(--oh-text)]">{title}</h3>
      </div>
      {statements.length > 0 ? (
        <div className="paper-summary__statements">
          {statements.map((statement) => (
            <Statement
              key={statement.statementId}
              statement={statement}
              review={review}
              forceOpen={forceOpen}
              onJumpToPage={onJumpToPage}
            />
          ))}
        </div>
      ) : (
        <p className="paper-summary__empty">该部分未提供。</p>
      )}
    </section>
  );
}

export function PaperSummaryFullscreenRenderer({
  artifact,
  review,
  onJumpToPage,
}: PaperSummaryRendererProps) {
  const [expandAll, setExpandAll] = useState<boolean | null>(null);

  const toggleExpandAll = () => {
    setExpandAll((prev) => (prev === true ? false : true));
  };

  return (
    <article
      className="paper-summary"
      data-artifact-version-id={review.artifactVersionId}
    >
      <header className="paper-summary__header">
        <div className="flex w-full items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="small"
            onClick={toggleExpandAll}
            className="text-xs text-[var(--oh-muted)] hover:text-[var(--oh-text)]"
          >
            {expandAll === true ? "全部收起证据" : "全部展开证据"}
          </Button>
        </div>

        <h2>{review.paper.title || artifact.title}</h2>
        <p className="paper-summary__byline">
          {review.paper.authors.join("、") || "作者信息缺失"}
          {review.paper.year === null ? "" : ` · ${review.paper.year}`}
        </p>
      </header>

      <Separator />

      <SummarySection
        title="研究背景"
        statements={review.background}
        review={review}
        forceOpen={expandAll}
        onJumpToPage={onJumpToPage}
      />
      <SummarySection
        title="研究方法"
        statements={review.methodology}
        review={review}
        forceOpen={expandAll}
        onJumpToPage={onJumpToPage}
      />
      <SummarySection
        title="数据集"
        statements={review.dataset}
        review={review}
        forceOpen={expandAll}
        onJumpToPage={onJumpToPage}
      />
      <SummarySection
        title="实验与结果"
        statements={review.experiments}
        review={review}
        forceOpen={expandAll}
        onJumpToPage={onJumpToPage}
      />
      <SummarySection
        title="讨论"
        statements={review.discussion}
        review={review}
        forceOpen={expandAll}
        onJumpToPage={onJumpToPage}
      />
      <SummarySection
        title="局限性"
        statements={review.limitations}
        review={review}
        forceOpen={expandAll}
        onJumpToPage={onJumpToPage}
      />
      <SummarySection
        title="研究问题"
        statements={review.researchQuestions}
        review={review}
        forceOpen={expandAll}
        onJumpToPage={onJumpToPage}
      />

      {review.sourceConflicts.length > 0 ? (
        <Alert variant="destructive">
          <AlertTitle>来源信息存在冲突</AlertTitle>
          <AlertDescription>
            {review.sourceConflicts
              .map((conflict) => conflict.resolution)
              .join("；")}
          </AlertDescription>
        </Alert>
      ) : null}
    </article>
  );
}
