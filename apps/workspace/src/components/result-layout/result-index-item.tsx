import type { DomainEntityId } from "@xingwen/domain";
import {
  Badge,
  Button,
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "@xingwen/ui";
import {
  AudioWaveform,
  ArrowRight,
  BookOpen,
  ChartSpline,
  Cpu,
  Database,
  FileCheck2,
  FileText,
  Gauge,
  Library,
  Microscope,
  Network,
  Quote,
  ScatterChart,
  TableProperties,
  Waypoints,
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
      return <TableProperties className={className} aria-hidden="true" />;
    case "field_dictionary":
      return <BookOpen className={className} aria-hidden="true" />;
    case "source_collection":
      return <Database className={className} aria-hidden="true" />;
    case "paper_collection":
      return <Library className={className} aria-hidden="true" />;
    case "paper_summary":
      return <FileText className={className} aria-hidden="true" />;
    case "literature_claims":
      return <Quote className={className} aria-hidden="true" />;
    case "literature_relations":
      return <Waypoints className={className} aria-hidden="true" />;
    case "graph":
      return <Network className={className} aria-hidden="true" />;
    case "analysis_report":
      return <Microscope className={className} aria-hidden="true" />;
    case "visualization":
      return <ScatterChart className={className} aria-hidden="true" />;
    case "model_evaluation":
      return <Gauge className={className} aria-hidden="true" />;
    case "model_artifact":
      return <Cpu className={className} aria-hidden="true" />;
    case "spectrum":
      return <AudioWaveform className={className} aria-hidden="true" />;
    case "light_curve":
      return <ChartSpline className={className} aria-hidden="true" />;
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
      <Button
        variant="ghost"
        onClick={() => onOpen(latestVersionId)}
        aria-label={`查看 ${title} 完整结果`}
      >
        <ItemMedia variant="icon" className="xw-result-index-item__icon">
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
      </Button>
    </Item>
  );
}
