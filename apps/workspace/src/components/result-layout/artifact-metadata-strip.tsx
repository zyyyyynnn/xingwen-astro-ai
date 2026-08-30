import { Badge } from "@xingwen/ui";

export interface ArtifactMetadataStripProps {
  readonly sourceCount?: number;
  readonly sourceLabel?: string | null;
  readonly sourceMode?: string | null;
  readonly retrievedAt?: string | null;
  readonly qualityStatus?: "pass" | "warn" | "fail" | "unknown" | string | null;
  readonly evidenceCount?: number;
  readonly recordCount?: number | null;
  readonly fieldCount?: number | null;
  readonly statusBadge?: {
    readonly label: string;
    readonly variant?: "default" | "secondary" | "destructive" | "outline";
  } | null;
  readonly className?: string;
}

function formatTimestamp(value: string): string {
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

export function ArtifactMetadataStrip({
  sourceCount,
  sourceLabel,
  sourceMode,
  retrievedAt,
  qualityStatus,
  evidenceCount,
  recordCount,
  fieldCount,
  statusBadge = null,
  className = "",
}: ArtifactMetadataStripProps) {
  return (
    <div
      className={`xw-metadata-strip flex flex-wrap items-center gap-x-4 gap-y-1.5 py-2 text-xs text-muted-foreground ${className}`}
      aria-label="结果元数据"
    >
      {statusBadge ? (
        <Badge
          variant={statusBadge.variant ?? "secondary"}
          className="h-5 px-1.5 text-xs"
        >
          {statusBadge.label}
        </Badge>
      ) : null}

      {sourceLabel ? (
        <span className="flex items-center gap-1">
          <span className="font-medium text-foreground/80">来源：</span>
          <span>{sourceLabel}</span>
        </span>
      ) : typeof sourceCount === "number" ? (
        <span className="flex items-center gap-1">
          <span className="font-medium text-foreground/80">来源：</span>
          <span>
            {sourceCount > 0 ? `${sourceCount} 个来源快照` : "未提供"}
          </span>
        </span>
      ) : null}

      {sourceMode ? (
        <span className="flex items-center gap-1">
          <span className="font-medium text-foreground/80">模式：</span>
          <span>
            {{
              live: "实时来源",
              cached: "缓存来源",
              recorded: "录制响应",
              fixture: "演示数据",
            }[sourceMode] ?? sourceMode}
          </span>
        </span>
      ) : null}

      {typeof recordCount === "number" ? (
        <span className="flex items-center gap-1">
          <span className="font-medium text-foreground/80">记录：</span>
          <span>{recordCount} 项</span>
        </span>
      ) : null}

      {typeof fieldCount === "number" ? (
        <span className="flex items-center gap-1">
          <span className="font-medium text-foreground/80">字段：</span>
          <span>{fieldCount} 项</span>
        </span>
      ) : null}

      {retrievedAt ? (
        <span className="flex items-center gap-1">
          <span className="font-medium text-foreground/80">获取：</span>
          <span>{formatTimestamp(retrievedAt)}</span>
        </span>
      ) : null}

      {qualityStatus ? (
        <span className="flex items-center gap-1">
          <span className="font-medium text-foreground/80">质量：</span>
          <span
            className={
              qualityStatus === "pass"
                ? "text-[var(--color-success)]"
                : qualityStatus === "warn"
                  ? "text-[var(--color-warning)]"
                  : qualityStatus === "fail"
                    ? "text-[var(--color-error)]"
                    : undefined
            }
          >
            {qualityStatus === "pass"
              ? "已校验通过"
              : qualityStatus === "warn"
                ? "存在警告"
                : qualityStatus === "fail"
                  ? "未通过"
                  : "未知"}
          </span>
        </span>
      ) : null}

      {typeof evidenceCount === "number" && evidenceCount > 0 ? (
        <span className="flex items-center gap-1">
          <span className="font-medium text-foreground/80">证据：</span>
          <span>{evidenceCount} 条</span>
        </span>
      ) : null}
    </div>
  );
}
