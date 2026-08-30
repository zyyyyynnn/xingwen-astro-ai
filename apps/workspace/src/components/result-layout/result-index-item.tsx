import type { DomainEntityId } from "@xingwen/domain";
import {
  Badge,
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "@xingwen/ui";
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  Database,
  FileCheck2,
  FileText,
  ListChecks,
} from "@xingwen/ui/icons";

export interface ResultIndexItemProps {
  readonly artifactId: DomainEntityId;
  readonly latestVersionId: DomainEntityId;
  readonly kind: string;
  readonly kindLabel: string;
  readonly title: string;
  readonly metadataSummary?: string | null;
  readonly statusLabel?: string | null;
  readonly statusVariant?: "default" | "secondary" | "destructive" | "outline";
  readonly onOpen: (versionId: DomainEntityId) => void;
}

function ResultKindIcon({
  kind,
  className,
}: {
  readonly kind?: string;
  readonly className?: string;
}) {
  switch (kind) {
    case "dataset":
    case "field_dictionary":
    case "source_collection":
      return <Database className={className} aria-hidden="true" />;
    case "paper_summary":
    case "paper_collection":
      return <FileText className={className} aria-hidden="true" />;
    case "literature_claims":
    case "literature_relations":
      return <ListChecks className={className} aria-hidden="true" />;
    case "graph":
      return <BrainCircuit className={className} aria-hidden="true" />;
    case "analysis_report":
    case "visualization":
    case "model_evaluation":
    case "model_artifact":
    case "spectrum":
    case "light_curve":
      return <Activity className={className} aria-hidden="true" />;
    default:
      return <FileCheck2 className={className} aria-hidden="true" />;
  }
}

export function ResultIndexItem({
  latestVersionId,
  kind,
  kindLabel,
  title,
  metadataSummary,
  statusLabel,
  statusVariant = "secondary",
  onOpen,
}: ResultIndexItemProps) {
  return (
    <Item className="xw-result-index-item" size="sm" asChild>
      <button
        type="button"
        onClick={() => onOpen(latestVersionId)}
        aria-label={`查看 ${title} 完整结果`}
      >
        <ItemMedia className="xw-result-index-item__icon">
          <ResultKindIcon kind={kind} />
        </ItemMedia>
        <ItemContent>
          <div className="xw-result-index-item__meta">
            <span>{kindLabel}</span>
            {statusLabel ? (
              <Badge variant={statusVariant}>{statusLabel}</Badge>
            ) : null}
          </div>
          <ItemTitle>{title}</ItemTitle>
          {metadataSummary ? (
            <ItemDescription>{metadataSummary}</ItemDescription>
          ) : null}
        </ItemContent>
        <ItemActions>
          <ArrowRight data-icon="inline-end" aria-hidden="true" />
        </ItemActions>
      </button>
    </Item>
  );
}
