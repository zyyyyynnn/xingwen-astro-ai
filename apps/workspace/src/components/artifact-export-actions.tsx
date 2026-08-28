import { useMutation } from "@tanstack/react-query";
import type {
  ArtifactExportFormat,
  ArtifactKind,
  DomainEntityId,
} from "@xingwen/domain";
import { Alert, AlertDescription, Button } from "@xingwen/ui";
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

  return (
    <section
      className="artifact-export p-3 bg-[var(--color-surface-muted)] rounded-lg border border-[var(--color-border)] my-3"
      aria-label="数据导出"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-xs font-medium text-[var(--color-ink-primary)]">
          数据导出
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {exportFormats(artifactKind).map(({ format, label }) => (
          <Button
            key={format}
            type="button"
            variant="secondary"
            size="small"
            disabled={exportMutation.isPending}
            onClick={() => exportMutation.mutate(format)}
          >
            <Download data-icon="inline-start" aria-hidden="true" />
            {exportMutation.isPending && exportMutation.variables === format
              ? `正在生成 ${label}`
              : `导出 ${label}`}
          </Button>
        ))}
      </div>
      {exportMutation.isError ? (
        <Alert variant="destructive" className="mt-2">
          <AlertDescription>
            {exportMutation.error instanceof Error
              ? runtime.researchAdapter.toPublicApplicationError(
                  exportMutation.error,
                ).safeMessage
              : "数据导出失败"}
          </AlertDescription>
        </Alert>
      ) : null}
      {exportMutation.isSuccess ? (
        <p
          className="text-xs text-[var(--color-ink-secondary)] mt-2"
          role="status"
        >
          已成功导出 {exportMutation.data.record.format.toUpperCase()}{" "}
          格式数据。
        </p>
      ) : null}
    </section>
  );
}
