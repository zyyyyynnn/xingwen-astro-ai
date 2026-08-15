import { useMutation } from "@tanstack/react-query";
import type {
  ArtifactExportFormat,
  ArtifactKind,
  DomainEntityId,
} from "@xingwen/domain";
import { Alert, AlertDescription, Badge, Button } from "@xingwen/ui";
import { Download } from "@xingwen/ui/icons";

import { downloadBytes } from "../presentation/browser-download";
import type { WorkspaceRuntimeBoundaries } from "../boundaries";

const FORMATS: readonly {
  readonly format: ArtifactExportFormat;
  readonly label: string;
}[] = [
  { format: "csv", label: "CSV" },
  { format: "json", label: "JSON" },
  { format: "provenance_report", label: "来源报告" },
];

export function ArtifactExportActions({
  runtime,
  projectId,
  artifactVersionId,
  versionNumber,
  artifactKind,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly versionNumber: number;
  readonly artifactKind: Extract<
    ArtifactKind,
    "dataset" | "field_dictionary" | "source_collection"
  >;
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
        throw new Error("导出未完成或未固定到当前 ArtifactVersion");
      }
      return {
        record: current,
        download: await repository.download(current),
      };
    },
    onSuccess: ({ download }) => downloadBytes(download),
  });

  return (
    <section className="artifact-export" aria-label="固定版本导出">
      <div>
        <strong>固定版本导出</strong>
        <span>
          <Badge variant="outline">ArtifactVersion</Badge>v{versionNumber}
        </span>
      </div>
      <div className="artifact-export__actions">
        {FORMATS.map(({ format, label }) => (
          <Button
            key={format}
            type="button"
            variant="secondary"
            size="small"
            disabled={
              exportMutation.isPending ||
              (format === "csv" && artifactKind !== "dataset")
            }
            title={
              format === "csv" && artifactKind !== "dataset"
                ? "CSV 仅适用于 Dataset"
                : undefined
            }
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
        <Alert variant="destructive">
          <AlertDescription>
            {exportMutation.error instanceof Error
              ? runtime.researchAdapter.toPublicApplicationError(
                  exportMutation.error,
                ).safeMessage
              : "版本导出失败"}
          </AlertDescription>
        </Alert>
      ) : null}
      {exportMutation.isSuccess ? (
        <p role="status">
          已生成 {exportMutation.data.record.format}；有效至{" "}
          {exportMutation.data.record.expiresAt}。
        </p>
      ) : null}
    </section>
  );
}
