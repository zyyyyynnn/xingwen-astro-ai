import { useMutation } from "@tanstack/react-query";
import type {
  ArtifactExportFormat,
  ArtifactKind,
  DomainEntityId,
} from "@xingwen/domain";
import { Button } from "@xingwen/ui";
import { Download } from "@xingwen/ui/icons";

import { downloadBytes } from "../presentation/browser-download";
import type { WorkspaceRuntimeBoundaries } from "../boundaries";

const STRUCTURED_FORMATS = [
  { format: "json", label: "JSON" },
  { format: "provenance_report", label: "来源报告" },
] as const satisfies readonly {
  readonly format: ArtifactExportFormat;
  readonly label: string;
}[];

function exportFormats(
  kind: Extract<
    ArtifactKind,
    "dataset" | "field_dictionary" | "source_collection"
  >,
) {
  return kind === "dataset"
    ? ([{ format: "csv", label: "CSV" }, ...STRUCTURED_FORMATS] as const)
    : STRUCTURED_FORMATS;
}

function downloadFileName(title: string, format: ArtifactExportFormat): string {
  const safeTitle =
    title
      .trim()
      .replace(/[\\/:*?"<>|]+/gu, "-")
      .replace(/\s+/gu, " ")
      .slice(0, 80) || "研究结果";
  if (format === "csv") return `${safeTitle}.csv`;
  if (format === "provenance_report") return `${safeTitle}-来源报告.json`;
  return `${safeTitle}.json`;
}

export function ArtifactExportActions({
  runtime,
  projectId,
  artifactVersionId,
  artifactKind,
  artifactTitle,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly artifactKind: Extract<
    ArtifactKind,
    "dataset" | "field_dictionary" | "source_collection"
  >;
  readonly artifactTitle: string;
}) {
  const repository = runtime.repositories.artifactExports;
  const exportMutation = useMutation({
    mutationKey: ["artifact-export", artifactVersionId],
    mutationFn: async (format: ArtifactExportFormat) => {
      const created = await repository.create(artifactVersionId, format);
      const current = await repository.get(created.id);
      if (
        current.status !== "completed" ||
        current.artifactVersionId !== artifactVersionId ||
        current.projectId !== projectId
      ) {
        throw new Error("导出未完成或未固定到当前版本");
      }
      const download = await repository.download(current);
      return {
        record: current,
        download: {
          ...download,
          fileName: downloadFileName(artifactTitle, current.format),
        },
      };
    },
    onSuccess: ({ download }) => downloadBytes(download),
  });

  const exportError =
    exportMutation.error instanceof Error
      ? runtime.researchAdapter.toPublicApplicationError(exportMutation.error)
          .safeMessage
      : exportMutation.error
        ? "数据导出失败"
        : null;

  return (
    <div
      className="artifact-export flex flex-wrap items-center gap-2"
      aria-label="数据导出"
    >
      {exportFormats(artifactKind).map(({ format, label }) => (
        <Button
          key={format}
          type="button"
          variant="secondary"
          size="xsmall"
          disabled={exportMutation.isPending}
          onClick={() => exportMutation.mutate(format)}
          aria-label={`导出 ${label}`}
        >
          <Download data-icon="inline-start" aria-hidden="true" />
          {exportMutation.isPending && exportMutation.variables === format
            ? `生成中…`
            : label}
        </Button>
      ))}
      {exportError ? (
        <span className="ui-text-label text-[var(--color-error)]" role="alert">
          {exportError}
        </span>
      ) : null}
      {exportMutation.isSuccess ? (
        <span
          className="ui-text-label text-[var(--color-ink-secondary)]"
          role="status"
        >
          已导出 {exportMutation.data.record.format.toUpperCase()}
        </span>
      ) : null}
    </div>
  );
}
