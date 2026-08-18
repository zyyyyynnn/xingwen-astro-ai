import { useQuery } from "@tanstack/react-query";
import { safeExternalUrl, type DomainEntityId } from "@xingwen/domain";
import {
  Alert,
  AlertDescription,
  Button,
  buttonClassName,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
} from "@xingwen/ui";
import { ExternalLink } from "@xingwen/ui/icons";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

function sourceUrl(metadata: Readonly<Record<string, unknown>>): string | null {
  for (const key of ["source_url", "url", "original_url", "landing_url"]) {
    const value = metadata[key];
    if (typeof value === "string") {
      const safe = safeExternalUrl(value);
      if (safe) return safe;
    }
  }
  return null;
}

function locatorLabel(
  locator: {
    readonly kind: string;
    readonly page?: number | null;
    readonly section?: string;
    readonly paragraph?: number | null;
  } | null,
): string | null {
  if (!locator) return null;
  if (locator.kind === "paper_text") {
    const parts = [
      locator.page === null || locator.page === undefined
        ? null
        : `第 ${locator.page + 1} 页`,
      locator.section || null,
      locator.paragraph === null || locator.paragraph === undefined
        ? null
        : `第 ${locator.paragraph} 段`,
    ].filter(Boolean);
    return parts.join(" · ") || "论文原文定位";
  }
  if (locator.kind === "database_cell") return "数据单元格";
  if (locator.kind === "model_extraction") return "模型提取来源";
  if (locator.kind === "reasoning_trace") return "推理链证据";
  return null;
}

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
  const safeUrl = evidence?.source
    ? sourceUrl(evidence.source.requestMetadata)
    : null;
  const locator = evidence?.locator ?? null;
  const locatorText = locatorLabel(locator);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-[min(30rem,92vw)] overflow-y-auto"
      >
        <SheetHeader>
          <SheetTitle>研究证据</SheetTitle>
          <SheetDescription>
            查看这一结论对应的真实来源与定位信息。
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-5 px-4 pb-6 text-sm">
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
            <>
              <section className="space-y-2">
                <h3 className="font-medium text-foreground">来源内容</h3>
                <p className="whitespace-pre-wrap leading-6 text-foreground">
                  {evidence.quoteOrValue ?? "该证据没有可公开展示的原文摘录。"}
                </p>
              </section>
              {locatorText ? (
                <section className="space-y-1">
                  <h3 className="font-medium text-foreground">定位</h3>
                  <p className="text-muted-foreground">{locatorText}</p>
                  {locator?.kind === "paper_text" &&
                  locator.page !== null &&
                  onJumpToPaperPage ? (
                    <Button
                      size="small"
                      variant="secondary"
                      onClick={() => {
                        onJumpToPaperPage(locator.page ?? 0);
                        onOpenChange(false);
                      }}
                    >
                      在论文中查看
                    </Button>
                  ) : null}
                </section>
              ) : null}
              {evidence.source ? (
                <section className="space-y-1">
                  <h3 className="font-medium text-foreground">来源</h3>
                  <p className="text-muted-foreground">
                    {evidence.source.sourceType} · 获取于{" "}
                    {new Date(evidence.source.retrievedAt).toLocaleString()}
                  </p>
                  <p className="text-muted-foreground">
                    {evidence.source.licenseNote}
                  </p>
                  {safeUrl ? (
                    <a
                      href={safeUrl}
                      target="_blank"
                      rel="noreferrer"
                      className={buttonClassName({
                        size: "small",
                        variant: "ghost",
                      })}
                    >
                      打开来源
                      <ExternalLink
                        className="ml-1 size-3.5"
                        aria-hidden="true"
                      />
                    </a>
                  ) : null}
                </section>
              ) : null}
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
