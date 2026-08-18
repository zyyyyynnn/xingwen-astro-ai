import type { PaperSummaryReview } from "@xingwen/domain";
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
import { useEffect, useRef, useState } from "react";
import { PaperSummaryFullscreenRenderer } from "./paper-summary-renderer";
import { PaperPdfViewer, type PaperPdfViewerHandle } from "./paper-pdf-viewer";

export interface PaperResultWorkspaceProps {
  readonly artifact: ResearchArtifactViewModel;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly review: PaperSummaryReview;
  readonly pdfUrl?: string | null;
  readonly requestedPage?: {
    readonly pageIndex: number;
    readonly nonce: number;
  } | null;
  readonly className?: string;
}

type PaperResultPane = "report" | "pdf";

export function PaperResultWorkspace({
  artifact,
  version,
  review,
  pdfUrl = null,
  requestedPage = null,
  className = "",
}: PaperResultWorkspaceProps) {
  const [activePane, setActivePane] = useState<PaperResultPane>("report");
  const [prevNonce, setPrevNonce] = useState<number | null>(null);

  const requestedPageIndex = requestedPage?.pageIndex ?? null;
  const requestedPageNonce = requestedPage?.nonce ?? null;

  if (requestedPageNonce !== null && requestedPageNonce !== prevNonce) {
    setPrevNonce(requestedPageNonce);
    setActivePane("pdf");
  }

  const widePdfRef = useRef<PaperPdfViewerHandle>(null);
  const narrowPdfRef = useRef<PaperPdfViewerHandle>(null);

  const jumpToPage = (pageIndex: number) => {
    setActivePane("pdf");
    // Both viewers stay mounted. Calling both keeps the visible viewer exact
    // across the desktop/narrow breakpoint without coupling scroll positions.
    widePdfRef.current?.jumpToPage(pageIndex);
    narrowPdfRef.current?.jumpToPage(pageIndex);
  };

  useEffect(() => {
    if (requestedPageIndex === null || requestedPageNonce === null) return;
    widePdfRef.current?.jumpToPage(requestedPageIndex);
    narrowPdfRef.current?.jumpToPage(requestedPageIndex);
  }, [requestedPageIndex, requestedPageNonce]);

  const report = (
    <PaperSummaryFullscreenRenderer
      artifact={artifact}
      version={version}
      review={review}
      onJumpToPage={jumpToPage}
    />
  );

  return (
    <div
      className={`xw-paper-result-workspace flex h-full w-full flex-col overflow-hidden bg-background ${className}`}
      data-testid="paper-result-workspace"
    >
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
            <TabsTrigger value="pdf" className="flex-1">
              论文原文
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <div className="hidden min-h-0 flex-1 overflow-hidden xl:flex">
        <ResizablePanelGroup orientation="horizontal" className="h-full w-full">
          <ResizablePanel
            id="report"
            defaultSize="44%"
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
            defaultSize="56%"
            minSize="25%"
            className="h-full overflow-hidden border-l border-border bg-muted/10"
          >
            <PaperPdfViewer
              src={pdfUrl}
              className="h-full w-full"
              ref={widePdfRef}
            />
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
          hidden={activePane !== "pdf"}
          aria-label="论文原文"
        >
          <PaperPdfViewer
            src={pdfUrl}
            className="h-full w-full"
            ref={narrowPdfRef}
          />
        </section>
      </div>
    </div>
  );
}
