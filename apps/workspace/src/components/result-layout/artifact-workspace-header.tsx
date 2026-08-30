import type { ReactNode } from "react";
import type { DomainEntityId } from "@xingwen/domain";
import type { ArtifactVersionSummary } from "@xingwen/domain";
import {
  Button,
  DialogClose,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@xingwen/ui";
import {
  ArrowLeft,
  ChevronDown,
  History,
  Quote,
  RotateCcw,
  Share2,
} from "@xingwen/ui/icons";

export interface ArtifactWorkspaceHeaderProps {
  readonly title: string;
  readonly artifactVersionId: DomainEntityId;
  readonly versions?: readonly ArtifactVersionSummary[];
  readonly onSelectVersion?: (versionId: DomainEntityId) => void;
  readonly hasEvidence?: boolean;
  readonly onOpenEvidence?: () => void;
  readonly canCompare?: boolean;
  readonly onOpenCompare?: () => void;
  readonly canShare?: boolean;
  readonly onOpenShare?: () => void;
  readonly canRevise?: boolean;
  readonly onOpenRevision?: () => void;
  readonly actions?: ReactNode;
}

function versionTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

export function ArtifactWorkspaceHeader({
  title,
  artifactVersionId,
  versions = [],
  onSelectVersion,
  hasEvidence = false,
  onOpenEvidence,
  canCompare = false,
  onOpenCompare,
  canShare = false,
  onOpenShare,
  canRevise = false,
  onOpenRevision,
  actions = null,
}: ArtifactWorkspaceHeaderProps) {
  const orderedVersions = [...versions].sort(
    (left, right) => right.versionNumber - left.versionNumber,
  );
  const selectedVersion =
    orderedVersions.find((version) => version.id === artifactVersionId) ?? null;
  const isCurrentVersion =
    orderedVersions.length > 0 && orderedVersions[0]?.id === artifactVersionId;

  return (
    <header
      className="xw-artifact-header flex min-h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border bg-background px-4 py-2"
      data-testid="artifact-fullscreen-header"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-3">
        <DialogClose asChild>
          <Button
            variant="ghost"
            size="small"
            className="ui-text-label flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft aria-hidden="true" />
            <span>返回研究</span>
          </Button>
        </DialogClose>
        <DialogTitle className="min-w-0 max-w-lg truncate font-serif text-lg font-semibold tracking-tight text-foreground">
          {title}
        </DialogTitle>
        {orderedVersions.length > 1 && selectedVersion && onSelectVersion ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="small"
                aria-haspopup="listbox"
                className="ui-text-label flex items-center gap-1 text-muted-foreground hover:text-foreground"
                data-testid="artifact-version-selector"
              >
                <span>{isCurrentVersion ? "当前结果" : "历史结果"}</span>
                <span className="text-xs">
                  {versionTimestamp(selectedVersion.createdAt)}
                </span>
                <ChevronDown aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="min-w-56">
              {orderedVersions.map((version) => {
                const isCurrent = orderedVersions[0]?.id === version.id;
                const isActive = version.id === artifactVersionId;
                return (
                  <DropdownMenuItem
                    key={version.id}
                    onClick={() => {
                      if (!isActive) onSelectVersion(version.id);
                    }}
                    className={isActive ? "font-medium" : undefined}
                  >
                    <span>{isCurrent ? "当前结果" : "历史结果"}</span>
                    <span className="ui-text-label ml-auto pl-4 text-muted-foreground">
                      {versionTimestamp(version.createdAt)}
                    </span>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-1.5">
        {actions}
        {hasEvidence && onOpenEvidence ? (
          <Button size="small" variant="ghost" onClick={onOpenEvidence}>
            <Quote aria-hidden="true" />
            证据
          </Button>
        ) : null}
        {canCompare && onOpenCompare ? (
          <Button size="small" variant="ghost" onClick={onOpenCompare}>
            <History aria-hidden="true" />
            比较结果
          </Button>
        ) : null}
        {canShare && onOpenShare ? (
          <Button
            size="small"
            variant="ghost"
            className="gap-1.5"
            onClick={onOpenShare}
          >
            <Share2 aria-hidden="true" />
            分享
          </Button>
        ) : null}
        {canRevise && onOpenRevision ? (
          <Button size="small" variant="ghost" onClick={onOpenRevision}>
            <RotateCcw aria-hidden="true" />
            基于此结果重新分析
          </Button>
        ) : null}
      </div>
    </header>
  );
}
