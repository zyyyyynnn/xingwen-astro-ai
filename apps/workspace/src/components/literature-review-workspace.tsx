import {
  parseEntityId,
  safeExternalUrl,
  type DomainEntityId,
  type PublicArtifactPresentation,
  type PublicPresentationEntry,
} from "@xingwen/domain";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Badge,
  Button,
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemSeparator,
  ItemTitle,
  Link,
  ScrollArea,
  ToggleGroup,
  ToggleGroupItem,
} from "@xingwen/ui";
import {
  ArrowRight,
  Check,
  ExternalLink,
  Quote,
  RotateCcw,
  X,
} from "@xingwen/ui/icons";
import { useMemo, useState } from "react";

import {
  polarityLabel,
  reviewStatusLabel,
  taxonomyLabel,
} from "./scientific-content/shared";
import type { PresentationRevisionIntent } from "./scientific-presentation";

type ReviewFilter = "all" | "candidate" | "accepted" | "rejected";

const FILTERS: readonly {
  readonly value: ReviewFilter;
  readonly label: string;
}[] = [
  { value: "all", label: "全部" },
  { value: "candidate", label: "待审" },
  { value: "accepted", label: "已纳入" },
  { value: "rejected", label: "未采用" },
];

function statusVariant(
  status: string | null,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "candidate") return "default";
  if (status === "rejected") return "outline";
  return "secondary";
}

function assessmentLabel(value: string | null): string | null {
  if (!value) return null;
  return value
    .split(" · ")
    .map((part) =>
      ["positive", "negative", "neutral", "mixed"].includes(part)
        ? polarityLabel(part)
        : taxonomyLabel(part),
    )
    .join(" · ");
}

function EvidenceActions({
  evidenceIds,
  onSelectEvidence,
  evidenceOrdinal,
}: {
  readonly evidenceIds: readonly DomainEntityId[];
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly evidenceOrdinal?: (evidenceId: DomainEntityId) => number | null;
}) {
  if (!onSelectEvidence || evidenceIds.length === 0) return null;
  return (
    <div className="literature-review__evidence-actions">
      {evidenceIds.map((evidenceId, index) => {
        const ordinal = evidenceOrdinal?.(evidenceId) ?? index + 1;
        if (ordinal === null || ordinal < 1) return null;
        return (
          <Button
            key={evidenceId}
            type="button"
            variant="ghost"
            size="xsmall"
            onClick={() => onSelectEvidence(evidenceId)}
          >
            <Quote data-icon="inline-start" aria-hidden="true" />
            证据 {ordinal}
          </Button>
        );
      })}
    </div>
  );
}

function EntryContext({
  entry,
  isRelations,
  onSelectEvidence,
  evidenceOrdinal,
  onRequestRevision,
}: {
  readonly entry: PublicPresentationEntry;
  readonly isRelations: boolean;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly evidenceOrdinal?: (evidenceId: DomainEntityId) => number | null;
  readonly onRequestRevision?: (intent: PresentationRevisionIntent) => void;
}) {
  const relationId = isRelations ? parseEntityId(entry.key) : null;
  const canAdjudicate =
    isRelations &&
    entry.status === "candidate" &&
    entry.canAdjudicate === true &&
    relationId !== null &&
    onRequestRevision !== undefined;
  const externalUrl = safeExternalUrl(entry.externalUrl);
  const assessment = assessmentLabel(entry.assessment);
  const reasoningTrace = entry.reasoningTrace;

  return (
    <aside className="literature-review__context" aria-live="polite">
      <header className="literature-review__context-header">
        {entry.relation ? (
          <div className="literature-review__claim-pair" aria-label="关联主张">
            <p>{entry.relation.sourceClaim}</p>
            <div className="literature-review__connector">
              <ArrowRight aria-hidden="true" />
              <span>{assessment}</span>
            </div>
            <p>{entry.relation.targetClaim}</p>
          </div>
        ) : (
          <h3>{entry.title}</h3>
        )}
        {assessment && !entry.relation ? (
          <p className="ui-text-label literature-review__assessment">
            {assessment}
          </p>
        ) : null}
      </header>

      {entry.paragraphs.length > 0 ? (
        <section className="literature-review__context-section">
          <h4>{isRelations ? "关系说明" : "声明内容"}</h4>
          {entry.paragraphs.map((paragraph, index) => (
            <p key={`${entry.key}:paragraph:${index}`}>{paragraph}</p>
          ))}
        </section>
      ) : null}

      {entry.facts.length > 0 ? (
        <section className="literature-review__context-section">
          <h4>{isRelations ? "比较条件" : "关键事实"}</h4>
          <dl className="literature-review__facts">
            {entry.facts.map((fact) => (
              <div key={`${entry.key}:fact:${fact.label}`}>
                <dt>{fact.label}</dt>
                <dd>{fact.values.join("、")}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {reasoningTrace ? (
        <Accordion
          type="single"
          collapsible
          className="literature-review__reasoning"
        >
          <AccordionItem value="reasoning">
            <AccordionTrigger>公开推导与限制</AccordionTrigger>
            <AccordionContent>
              <p className="font-medium">{reasoningTrace.conclusion}</p>
              {reasoningTrace.steps.length > 0 ? (
                <ol>
                  {reasoningTrace.steps.map((step, index) => (
                    <li key={`${entry.key}:step:${index}`}>{step}</li>
                  ))}
                </ol>
              ) : (
                <p>没有可公开展示的推导步骤。</p>
              )}
              {reasoningTrace.facts.length > 0 ? (
                <dl className="literature-review__facts">
                  {reasoningTrace.facts.map((fact) => (
                    <div key={fact.label}>
                      <dt>{fact.label}</dt>
                      <dd>{fact.values.join("、")}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              <EvidenceActions
                evidenceIds={reasoningTrace.evidenceIds}
                onSelectEvidence={onSelectEvidence}
                evidenceOrdinal={evidenceOrdinal}
              />
              {onRequestRevision ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="small"
                  onClick={() =>
                    onRequestRevision({
                      kind: "trace_correction",
                      traceId: reasoningTrace.traceId,
                    })
                  }
                >
                  <RotateCcw data-icon="inline-start" aria-hidden="true" />
                  重新分析此推导
                </Button>
              ) : null}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      ) : null}

      {entry.evidenceIds.length > 0 ? (
        <section className="literature-review__context-section">
          <h4>核验证据</h4>
          <EvidenceActions
            evidenceIds={entry.evidenceIds}
            onSelectEvidence={onSelectEvidence}
            evidenceOrdinal={evidenceOrdinal}
          />
        </section>
      ) : null}

      {externalUrl ? (
        <Link href={externalUrl} external className="literature-review__source">
          查看原文
          <ExternalLink data-icon="inline-end" aria-hidden="true" />
        </Link>
      ) : null}

      {canAdjudicate ? (
        <div className="literature-review__decision-bar" aria-label="关系审定">
          <Button
            type="button"
            variant="primary"
            onClick={() =>
              onRequestRevision({
                kind: "relation_adjudication",
                relationId,
                decision: "accepted",
              })
            }
          >
            <Check data-icon="inline-start" aria-hidden="true" />
            接受并进入图谱
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              onRequestRevision({
                kind: "relation_adjudication",
                relationId,
                decision: "rejected",
              })
            }
          >
            <X data-icon="inline-start" aria-hidden="true" />
            拒绝且不进入图谱
          </Button>
        </div>
      ) : null}

      {isRelations &&
      entry.status === "rejected" &&
      relationId !== null &&
      onRequestRevision ? (
        <Button
          type="button"
          variant="ghost"
          size="small"
          onClick={() =>
            onRequestRevision({ kind: "relation_correction", relationId })
          }
        >
          <RotateCcw data-icon="inline-start" aria-hidden="true" />
          重新分析此关系
        </Button>
      ) : null}
    </aside>
  );
}

export function LiteratureReviewWorkspace({
  title,
  presentation,
  onSelectEvidence,
  evidenceOrdinal,
  onRequestRevision,
  showTitle = true,
}: {
  readonly title: string;
  readonly presentation: PublicArtifactPresentation;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly evidenceOrdinal?: (evidenceId: DomainEntityId) => number | null;
  readonly onRequestRevision?: (intent: PresentationRevisionIntent) => void;
  readonly showTitle?: boolean;
}) {
  const isRelations = presentation.kind === "literature_relations";
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const orderedEntries = useMemo(
    () =>
      [...presentation.entries].sort((left, right) => {
        const priority = (status: string | null) =>
          status === "candidate"
            ? 0
            : status === "accepted"
              ? 1
              : status === "rejected"
                ? 2
                : 3;
        return priority(left.status) - priority(right.status);
      }),
    [presentation.entries],
  );
  const [selectedKey, setSelectedKey] = useState<string | null>(
    orderedEntries[0]?.key ?? null,
  );
  const filteredEntries =
    filter === "all"
      ? orderedEntries
      : orderedEntries.filter((entry) => entry.status === filter);
  const selectedEntry =
    filteredEntries.find((entry) => entry.key === selectedKey) ??
    filteredEntries[0] ??
    null;

  const counts = Object.fromEntries(
    FILTERS.map(({ value }) => [
      value,
      value === "all"
        ? orderedEntries.length
        : orderedEntries.filter((entry) => entry.status === value).length,
    ]),
  ) as Record<ReviewFilter, number>;

  return (
    <article
      className="literature-review"
      data-kind={isRelations ? "relations" : "claims"}
    >
      {showTitle ? (
        <header className="literature-review__header">
          <h2>{title}</h2>
        </header>
      ) : null}

      {presentation.sections.length > 0 ? (
        <Accordion
          type="single"
          collapsible
          className="literature-review__overview"
        >
          <AccordionItem value="overview">
            <AccordionTrigger>研究范围与说明</AccordionTrigger>
            <AccordionContent>
              {presentation.sections.map((section) => (
                <section key={section.title}>
                  <h3>{section.title}</h3>
                  {section.paragraphs.map((paragraph, index) => (
                    <p key={`${section.title}:${index}`}>{paragraph.text}</p>
                  ))}
                </section>
              ))}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      ) : null}

      <div className="literature-review__toolbar">
        <ToggleGroup
          type="single"
          variant="segmented"
          size="sm"
          value={filter}
          onValueChange={(value) => {
            if (value) setFilter(value as ReviewFilter);
          }}
          aria-label="筛选审查状态"
        >
          {FILTERS.map(({ value, label }) => (
            <ToggleGroupItem
              key={value}
              value={value}
              aria-label={`${label} ${counts[value]}`}
            >
              {label}
              <span className="literature-review__filter-count">
                {counts[value]}
              </span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <div className="literature-review__split">
        <ScrollArea className="literature-review__list-scroll">
          <ItemGroup className="literature-review__list" role="list">
            {filteredEntries.map((entry, index) => {
              const selected = entry.key === selectedEntry?.key;
              return (
                <div key={entry.key} role="listitem">
                  <Item asChild size="default" variant="default">
                    <Button
                      variant="ghost"
                      className="literature-review__entry"
                      data-selected={selected || undefined}
                      data-testid={`literature-entry-${entry.key}`}
                      aria-pressed={selected}
                      aria-label={`选择${entry.title}`}
                      onClick={() => setSelectedKey(entry.key)}
                    >
                      <ItemContent>
                        <div className="literature-review__entry-meta">
                          {entry.status ? (
                            <Badge
                              variant={statusVariant(entry.status)}
                              data-status={entry.status}
                            >
                              {isRelations
                                ? (FILTERS.find(
                                    ({ value }) => value === entry.status,
                                  )?.label ?? reviewStatusLabel(entry.status))
                                : reviewStatusLabel(entry.status)}
                            </Badge>
                          ) : null}
                        </div>
                        <ItemTitle>{entry.title}</ItemTitle>
                        {entry.paragraphs[0] ? (
                          <ItemDescription>
                            {entry.paragraphs[0]}
                          </ItemDescription>
                        ) : null}
                      </ItemContent>
                      <ArrowRight aria-hidden="true" />
                    </Button>
                  </Item>
                  {index < filteredEntries.length - 1 ? (
                    <ItemSeparator />
                  ) : null}
                </div>
              );
            })}
          </ItemGroup>
        </ScrollArea>

        {selectedEntry ? (
          <ScrollArea className="literature-review__context-scroll">
            <EntryContext
              entry={selectedEntry}
              isRelations={isRelations}
              onSelectEvidence={onSelectEvidence}
              evidenceOrdinal={evidenceOrdinal}
              onRequestRevision={onRequestRevision}
            />
          </ScrollArea>
        ) : (
          <div className="literature-review__empty">当前筛选没有结果。</div>
        )}
      </div>
    </article>
  );
}
