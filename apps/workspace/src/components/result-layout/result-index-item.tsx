import type { DomainEntityId } from "@xingwen/domain";
import { Badge, Button } from "@xingwen/ui";
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
    <div className="xw-result-index-item group flex items-center justify-between gap-3 rounded-md border border-transparent p-2 transition-colors hover:border-border/60 hover:bg-surface-hover/50">
      <Button
        variant="ghost"
        className="flex h-auto min-w-0 flex-1 items-start gap-2.5 p-0 text-left hover:bg-transparent"
        onClick={() => onOpen(latestVersionId)}
      >
        <div className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded border border-border/60 bg-surface-muted text-muted-foreground group-hover:text-foreground">
          <ResultKindIcon kind={kind} className="size-3.5" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              {kindLabel}
            </span>
            {statusLabel ? (
              <Badge variant={statusVariant} className="h-3.5 px-1 text-[9px]">
                {statusLabel}
              </Badge>
            ) : null}
          </div>

          <p className="truncate text-xs font-medium text-foreground">
            {title}
          </p>

          {metadataSummary ? (
            <p className="ui-text-label mt-0.5 truncate text-muted-foreground/80">
              {metadataSummary}
            </p>
          ) : null}
        </div>
      </Button>

      <Button
        size="icon"
        variant="ghost"
        className="size-6 shrink-0 opacity-0 group-hover:opacity-100"
        onClick={() => onOpen(latestVersionId)}
        aria-label={`查看 ${title} 完整结果`}
      >
        <ArrowRight
          className="size-3 text-muted-foreground"
          aria-hidden="true"
        />
      </Button>
    </div>
  );
}
