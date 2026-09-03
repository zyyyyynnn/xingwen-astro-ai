import { useMutation } from "@tanstack/react-query";
import type { DomainEntityId } from "@xingwen/domain";
import { Alert, AlertDescription, Button } from "@xingwen/ui";
import { Download } from "@xingwen/ui/icons";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { downloadBytes } from "../presentation/browser-download";

const FORMATS = [
  { format: "json", label: "JSON" },
  { format: "markdown", label: "Markdown" },
] as const;

export function PaperSummaryExportActions({
  runtime,
  artifactVersionId,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly artifactVersionId: DomainEntityId;
}) {
  const exportMutation = useMutation({
    mutationKey: ["paper-summary-export", artifactVersionId],
    mutationFn: async (format: "json" | "markdown") =>
      runtime.repositories.paperSummary.export(artifactVersionId, format),
    onSuccess: downloadBytes,
  });

  return (
    <section
      className="flex flex-wrap items-center gap-2"
      aria-label="论文摘要导出"
    >
      <span className="ui-text-label paper-summary-export__note">
        导出当前版本
      </span>
      {FORMATS.map(({ format, label }) => (
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
      {exportMutation.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {
              runtime.researchAdapter.toPublicApplicationError(
                exportMutation.error,
              ).safeMessage
            }
          </AlertDescription>
        </Alert>
      ) : null}
      {exportMutation.isSuccess ? (
        <p className="ui-text-label paper-summary-export__note" role="status">
          论文摘要已导出。
        </p>
      ) : null}
    </section>
  );
}
