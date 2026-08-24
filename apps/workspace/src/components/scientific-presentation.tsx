import {
  safeExternalUrl,
  type DomainEntityId,
  type PublicArtifactPresentation,
  type PublicPresentationFact,
  type SourceMode,
} from "@xingwen/domain";
import {
  Badge,
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Link,
} from "@xingwen/ui";
import { ChevronDown, Quote } from "@xingwen/ui/icons";

import {
  polarityLabel,
  reviewStatusLabel,
  ScientificContentHeader,
  taxonomyLabel,
  type ScientificContentSurface,
} from "./scientific-content/shared";
import { sourceModeLabel } from "../presentation/artifact-presentation-labels";
import { ScientificTable } from "./scientific-table";

export function ArtifactSourceMode({
  sourceMode,
}: {
  readonly sourceMode: SourceMode;
}) {
  const label = sourceModeLabel(sourceMode);
  return label ? (
    <Badge variant="outline" data-source-mode={sourceMode}>
      {label}
    </Badge>
  ) : null;
}

export function PresentationEvidenceActions({
  evidenceIds,
  onSelectEvidence,
  evidenceOrdinal,
}: {
  readonly evidenceIds: readonly DomainEntityId[];
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly evidenceOrdinal?: (evidenceId: DomainEntityId) => number | null;
}) {
  if (evidenceIds.length === 0 || !onSelectEvidence) return null;
  const actions = evidenceIds.flatMap((evidenceId, index) => {
    const ordinal = evidenceOrdinal ? evidenceOrdinal(evidenceId) : index + 1;
    return ordinal !== null && ordinal > 0 ? [{ evidenceId, ordinal }] : [];
  });
  if (actions.length === 0) return null;
  return (
    <div className="dossier__evidence-actions" aria-label="可核验证据">
      {actions.map(({ evidenceId, ordinal }) => (
        <Button
          key={evidenceId}
          size="small"
          variant="ghost"
          onClick={() => onSelectEvidence(evidenceId)}
        >
          <Quote aria-hidden="true" />
          查看证据 {ordinal}
        </Button>
      ))}
    </div>
  );
}

export function PresentationFacts({
  facts,
}: {
  readonly facts: readonly PublicPresentationFact[];
}) {
  if (facts.length === 0) return null;
  return (
    <dl className="dossier__facts">
      {facts.map((fact) => (
        <div key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>{fact.values.join("；")}</dd>
        </div>
      ))}
    </dl>
  );
}

function PresentationTables({
  presentation,
  onSelectEvidence,
}: {
  readonly presentation: PublicArtifactPresentation;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  return presentation.tables.map((table) => (
    <section className="scientific-artifact__section" key={table.title}>
      <h3>{table.title}</h3>
      <ScientificTable
        caption={table.title}
        columns={table.columns}
        rows={table.rows.map((row) => ({
          id: row.key,
          identity: row.identity,
          cells: Object.fromEntries(
            row.cells.map((cell) => [
              cell.columnKey,
              {
                value: cell.value,
                status: cell.status,
                reason: cell.reason,
                evidenceIds: cell.evidenceIds,
              },
            ]),
          ),
        }))}
        maxRows={table.rows.length}
        maxColumns={table.columns.length}
        totalRowCount={table.totalRowCount}
        totalColumnCount={table.totalColumnCount}
        showIdentity
        onSelectEvidence={
          onSelectEvidence
            ? (evidenceIds) => {
                const first = evidenceIds[0];
                if (first) onSelectEvidence(first);
              }
            : undefined
        }
      />
    </section>
  ));
}

function PresentationTrace({
  trace,
  onSelectEvidence,
  evidenceOrdinal,
}: {
  readonly trace: NonNullable<
    PublicArtifactPresentation["entries"][number]["reasoningTrace"]
  >;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly evidenceOrdinal?: (evidenceId: DomainEntityId) => number | null;
}) {
  return (
    <Collapsible className="reasoning-trace">
      <CollapsibleTrigger asChild>
        <Button variant="ghost" className="reasoning-trace__trigger">
          <span>{trace.conclusion}</span>
          <ChevronDown aria-hidden="true" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="reasoning-trace__content">
          {trace.steps.length > 0 ? (
            <ol>
              {trace.steps.map((step, index) => (
                <li key={`${index}:${step}`}>{step}</li>
              ))}
            </ol>
          ) : (
            <p>没有可公开展示的推导步骤。</p>
          )}
          <PresentationFacts facts={trace.facts} />
          <PresentationEvidenceActions
            evidenceIds={trace.evidenceIds}
            onSelectEvidence={onSelectEvidence}
            evidenceOrdinal={evidenceOrdinal}
          />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function presentationAssessment(value: string | null): string | null {
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

export function PresentationGraphRelationships({
  nodes,
  edges,
  selectedKey = null,
  onSelectRelationship,
  onSelectEvidence,
  evidenceOrdinal,
}: {
  readonly nodes: readonly {
    readonly key: string;
    readonly label: string;
  }[];
  readonly edges: readonly {
    readonly key: string;
    readonly kind: string;
    readonly sourceKey: string;
    readonly targetKey: string;
    readonly evidenceIds: readonly DomainEntityId[];
  }[];
  readonly selectedKey?: string | null;
  readonly onSelectRelationship?: (key: string) => void;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly evidenceOrdinal?: (evidenceId: DomainEntityId) => number | null;
}) {
  const labels = new Map(nodes.map((node) => [node.key, node.label]));
  const interactive = onSelectRelationship !== undefined;
  return (
    <ol
      className={interactive ? "graph-workspace__list" : "graph-fallback-list"}
      aria-label={interactive ? "关系图列表替代视图" : "证据关系列表"}
    >
      {edges.map((edge) => {
        const content = (
          <>
            <span>{labels.get(edge.sourceKey) ?? "起点未公开"}</span>
            <span aria-hidden="true">→</span>
            <span>{labels.get(edge.targetKey) ?? "终点未公开"}</span>
            <small>{taxonomyLabel(edge.kind)}</small>
          </>
        );
        return (
          <li key={edge.key}>
            {onSelectRelationship ? (
              <Button
                variant={selectedKey === edge.key ? "secondary" : "ghost"}
                onClick={() => onSelectRelationship(edge.key)}
              >
                {content}
              </Button>
            ) : (
              <p>{content}</p>
            )}
            {!interactive ? (
              <PresentationEvidenceActions
                evidenceIds={edge.evidenceIds}
                onSelectEvidence={onSelectEvidence}
                evidenceOrdinal={evidenceOrdinal}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export function ArtifactPresentationContent({
  title,
  presentation,
  surface,
  onSelectEvidence,
  evidenceOrdinal,
  showHeader = true,
}: {
  readonly title: string;
  readonly presentation: PublicArtifactPresentation;
  readonly surface: ScientificContentSurface;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
  readonly evidenceOrdinal?: (evidenceId: DomainEntityId) => number | null;
  readonly showHeader?: boolean;
}) {
  const count =
    presentation.entries.length ||
    presentation.graphNodes.length ||
    presentation.sections.length ||
    presentation.facts.length;
  return (
    <article
      className={`scientific-artifact scientific-artifact--${presentation.kind}`}
      data-surface={surface}
    >
      {showHeader ? (
        <ScientificContentHeader
          title={title}
          subtitle={count > 0 ? `共 ${count} 项` : "冻结科研结果"}
        />
      ) : null}
      {presentation.summary ? (
        <p className="scientific-artifact__summary">{presentation.summary}</p>
      ) : null}
      <PresentationFacts facts={presentation.facts} />
      <PresentationTables
        presentation={presentation}
        onSelectEvidence={onSelectEvidence}
      />
      {presentation.sections.map((section) => (
        <section className="scientific-artifact__section" key={section.title}>
          <h3>{section.title}</h3>
          {section.paragraphs.map((paragraph, index) => (
            <div
              className="scientific-artifact__paragraph"
              key={`${section.title}:${index}`}
            >
              {paragraph.status && paragraph.status !== "supported" ? (
                <p
                  className="dossier__status"
                  data-support-status={paragraph.status}
                >
                  {reviewStatusLabel(paragraph.status)}
                </p>
              ) : null}
              <p>{paragraph.text}</p>
              <PresentationEvidenceActions
                evidenceIds={paragraph.evidenceIds}
                onSelectEvidence={onSelectEvidence}
                evidenceOrdinal={evidenceOrdinal}
              />
            </div>
          ))}
        </section>
      ))}
      {presentation.entries.length > 0 ? (
        <ol className="candidate-dossier" aria-label="科学结果档案">
          {presentation.entries.map((entry) => {
            const externalUrl = safeExternalUrl(entry.externalUrl);
            return (
              <li key={entry.key}>
                <article className="dossier__entry" data-status={entry.status}>
                  <header className="dossier__entry-header">
                    <div>
                      {entry.status ? (
                        <p className="dossier__status">
                          {reviewStatusLabel(entry.status)}
                        </p>
                      ) : null}
                      <h4>
                        {externalUrl ? (
                          <Link href={externalUrl} external>
                            {entry.title}
                          </Link>
                        ) : (
                          entry.title
                        )}
                      </h4>
                    </div>
                    {entry.assessment ? (
                      <p className="dossier__assessment">
                        {presentationAssessment(entry.assessment)}
                      </p>
                    ) : null}
                  </header>
                  {entry.paragraphs.map((paragraph, index) => (
                    <p key={`${entry.key}:paragraph:${index}`}>{paragraph}</p>
                  ))}
                  <PresentationFacts facts={entry.facts} />
                  <PresentationEvidenceActions
                    evidenceIds={entry.evidenceIds}
                    onSelectEvidence={onSelectEvidence}
                    evidenceOrdinal={evidenceOrdinal}
                  />
                  {entry.reasoningTrace ? (
                    <PresentationTrace
                      trace={entry.reasoningTrace}
                      onSelectEvidence={onSelectEvidence}
                      evidenceOrdinal={evidenceOrdinal}
                    />
                  ) : null}
                </article>
              </li>
            );
          })}
        </ol>
      ) : null}
      {presentation.graphEdges.length > 0 ? (
        <PresentationGraphRelationships
          nodes={presentation.graphNodes}
          edges={presentation.graphEdges}
          onSelectEvidence={onSelectEvidence}
          evidenceOrdinal={evidenceOrdinal}
        />
      ) : null}
      {count === 0 && !presentation.summary ? (
        <p className="scientific-artifact__empty">当前结果没有可展示的内容。</p>
      ) : null}
    </article>
  );
}
