import type { DomainEntityId } from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  ResearchArtifactViewModel,
} from "@xingwen/research-adapter";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
  Tabs,
  TabsList,
  TabsTrigger,
} from "@xingwen/ui";
import { FileText, Info } from "@xingwen/ui/icons";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { PaperPdfViewer, type PaperPdfViewerHandle } from "./paper-pdf-viewer";
import { ArtifactPresentationContent } from "./scientific-presentation";

export interface PaperResultWorkspaceProps {
  readonly artifact: ResearchArtifactViewModel;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly onSelectEvidence: (evidenceId: DomainEntityId) => void;
  readonly documentUrl?: string | null;
  readonly documentKind?: "pdf" | "image" | null;
  readonly requestedPage?: {
    readonly pageIndex: number;
    readonly nonce: number;
  } | null;
  readonly toolbar?: ReactNode;
  readonly className?: string;
}

type PaperResultPane = "report" | "document";

export function PaperResultWorkspace({
  artifact,
  version,
  onSelectEvidence,
  documentUrl = null,
  documentKind = null,
  requestedPage = null,
  toolbar = null,
  className = "",
}: PaperResultWorkspaceProps) {
  const [activePane, setActivePane] = useState<PaperResultPane>("report");
  const [prevNonce, setPrevNonce] = useState<number | null>(null);

  const hasDocument = Boolean(documentUrl);

  const requestedPageIndex = requestedPage?.pageIndex ?? null;
  const requestedPageNonce = requestedPage?.nonce ?? null;

  if (requestedPageNonce !== null && requestedPageNonce !== prevNonce) {
    setPrevNonce(requestedPageNonce);
    if (hasDocument) {
      setActivePane("document");
    }
  }

  const widePdfRef = useRef<PaperPdfViewerHandle>(null);
  const narrowPdfRef = useRef<PaperPdfViewerHandle>(null);

  useEffect(() => {
    if (requestedPageIndex === null || requestedPageNonce === null) return;
    widePdfRef.current?.jumpToPage(requestedPageIndex);
    narrowPdfRef.current?.jumpToPage(requestedPageIndex);
  }, [requestedPageIndex, requestedPageNonce]);

  const report = (
    <ArtifactPresentationContent
      title={artifact.title}
      presentation={version.presentation}
      surface="fullscreen"
      onSelectEvidence={onSelectEvidence}
      showHeader={false}
    />
  );

  return (
    <div
      className={`xw-paper-result-workspace flex h-full w-full flex-col overflow-hidden bg-background ${className}`}
      data-testid="paper-result-workspace"
      data-artifact-version-id={version.id}
    >
      {hasDocument ? (
        <div className="flex border-b border-border bg-muted/40 p-1 xl:hidden">
          <Tabs
            value={activePane}
            onValueChange={(value) => setActivePane(value as PaperResultPane)}
            className="w-full"
          >
            <TabsList className="w-full">
              <TabsTrigger value="report" className="flex-1">
                研究报告
              </TabsTrigger>
              <TabsTrigger value="document" className="flex-1">
                原始文档
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      ) : null}

      {toolbar ? (
        <div className="shrink-0 border-b border-border bg-background px-4 py-2">
          {toolbar}
        </div>
      ) : null}

      {!hasDocument ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[48rem] px-6 py-8">
            <div className="mb-6 flex items-center justify-between gap-4 border-b border-border/80 pb-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <FileText className="size-3.5" aria-hidden="true" />
                  <span>文献研读报告</span>
                </div>
                <h2 className="font-serif text-2xl font-bold tracking-tight text-foreground">
                  {artifact.title}
                </h2>
              </div>
            </div>

            <div className="mb-6 rounded-md border border-border/60 bg-surface-muted/40 p-3 text-xs text-muted-foreground">
              <div className="flex items-center gap-2">
                <Info
                  className="size-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                <span>
                  全文文档当前未关联本地或线上
                  PDF，展示结构化研读结果与抽取结论。
                </span>
              </div>
            </div>

            {report}
          </div>
        </div>
      ) : (
        <>
          <div className="hidden min-h-0 flex-1 overflow-hidden xl:flex">
            <ResizablePanelGroup
              orientation="horizontal"
              className="h-full w-full"
            >
              <ResizablePanel
                id="report"
                defaultSize="50%"
                minSize="30%"
                className="h-full overflow-y-auto p-6"
              >
                {report}
              </ResizablePanel>
              <ResizableHandle
                id="report-paper-divider"
                aria-label="调整研究报告与论文原文的宽度"
                className="xw-resize-handle relative flex w-2 items-center justify-center bg-border/40 transition-colors hover:bg-primary/20 focus-visible:bg-primary/20"
              />
              <ResizablePanel
                id="paper"
                defaultSize="50%"
                minSize="25%"
                className="h-full overflow-hidden border-l border-border bg-muted/10"
              >
                {documentKind === "image" && documentUrl ? (
                  <img
                    src={documentUrl}
                    alt="论文原始文档"
                    className="h-full w-full object-contain"
                  />
                ) : (
                  <PaperPdfViewer
                    src={documentKind === "pdf" ? documentUrl : null}
                    className="h-full w-full"
                    ref={widePdfRef}
                  />
                )}
              </ResizablePanel>
            </ResizablePanelGroup>
          </div>

          <div className="min-h-0 flex-1 overflow-hidden xl:hidden">
            <section
              className="h-full overflow-y-auto p-4"
              hidden={activePane !== "report"}
              aria-label="研究报告"
            >
              {report}
            </section>
            <section
              className="h-full overflow-hidden"
              hidden={activePane !== "document"}
              aria-label="原始文档"
            >
              {documentKind === "image" && documentUrl ? (
                <img
                  src={documentUrl}
                  alt="论文原始文档"
                  className="h-full w-full object-contain"
                />
              ) : (
                <PaperPdfViewer
                  src={documentKind === "pdf" ? documentUrl : null}
                  className="h-full w-full"
                  ref={narrowPdfRef}
                />
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
