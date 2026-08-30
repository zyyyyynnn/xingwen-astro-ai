import { useQuery } from "@tanstack/react-query";
import type { DomainEntityId } from "@xingwen/domain";
import {
  Alert,
  AlertDescription,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
} from "@xingwen/ui";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import {
  buildEvidencePresentation,
  EvidencePresentationContent,
} from "./evidence-presentation";

export function ArtifactEvidenceSheet({
  runtime,
  projectId,
  evidenceId,
  open,
  onOpenChange,
  onJumpToPaperPage,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly evidenceId: DomainEntityId | null;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onJumpToPaperPage?: (pageIndex: number) => void;
}) {
  const query = useQuery({
    ...runtime.application.queries.evidence(
      projectId,
      evidenceId as DomainEntityId,
    ),
    enabled: open && evidenceId !== null,
  });
  const evidence = query.data ?? null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="artifact-evidence-sheet result-side-sheet"
      >
        <SheetHeader className="result-side-sheet__header">
          <SheetTitle>研究证据</SheetTitle>
          <SheetDescription>
            查看这一结论对应的真实来源与定位信息。
          </SheetDescription>
        </SheetHeader>
        <div className="result-sheet-body">
          {query.isPending ? <Skeleton className="h-36 w-full" /> : null}
          {query.isError ? (
            <Alert variant="destructive">
              <AlertDescription>
                {
                  runtime.researchAdapter.toPublicApplicationError(query.error)
                    .safeMessage
                }
              </AlertDescription>
            </Alert>
          ) : null}
          {evidence ? (
            <EvidencePresentationContent
              presentation={buildEvidencePresentation(evidence)}
              onJumpToPaperPage={
                onJumpToPaperPage
                  ? (pageIndex) => {
                      onJumpToPaperPage(pageIndex);
                      onOpenChange(false);
                    }
                  : undefined
              }
            />
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
