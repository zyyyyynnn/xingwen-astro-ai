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
import { Info } from "@xingwen/ui/icons";
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
  readonly paperMeta?: {
    readonly title?: string;
    readonly authors?: readonly string[];
    readonly year?: number | null;
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
  paperMeta = null,
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
  const reportSections = version.presentation?.sections ?? [];

  useEffect(() => {
    if (requestedPageIndex === null || requestedPageNonce === null) return;
    widePdfRef.current?.jumpToPage(requestedPageIndex);
    narrowPdfRef.current?.jumpToPage(requestedPageIndex);
  }, [requestedPageIndex, requestedPageNonce]);

  const renderReport = (sectionIdPrefix: string) => (
    <div className="xw-paper-report flex h-full flex-col">
      <header className="paper-report__header">
        <h2 className="font-serif text-2xl font-bold tracking-tight text-foreground">
          {paperMeta?.title ?? artifact.title}
        </h2>
        <dl className="paper-report__metadata">
          {paperMeta?.authors?.length ? (
            <div>
              <dt>作者</dt>
              <dd>{paperMeta.authors.join("，")}</dd>
            </div>
          ) : null}
          {paperMeta?.year ? (
            <div>
              <dt>年份</dt>
              <dd>{paperMeta.year}</dd>
            </div>
          ) : null}
          <div>
            <dt>章节</dt>
            <dd>{reportSections.length}</dd>
          </div>
          <div>
            <dt>原文</dt>
            <dd>{hasDocument ? "已关联，可同屏核对" : "未关联"}</dd>
          </div>
        </dl>
        {reportSections.length > 1 ? (
          <nav className="paper-report__section-nav" aria-label="报告章节">
            <span>快速定位</span>
            <div>
              {reportSections.map((section, index) => (
                <a
                  key={section.title}
                  href={`#${sectionIdPrefix}-${index + 1}`}
                >
                  {section.title}
                </a>
              ))}
            </div>
          </nav>
        ) : null}
      </header>
      <ArtifactPresentationContent
        title={artifact.title}
        presentation={version.presentation}
        surface="fullscreen"
        onSelectEvidence={onSelectEvidence}
        showHeader={false}
        sectionIdPrefix={sectionIdPrefix}
      />
    </div>
  );

  return (
    <div
      className={`xw-paper-result-workspace flex h-full w-full flex-col overflow-hidden bg-background ${className}`}
      data-testid="paper-result-workspace"
      data-artifact-version-id={version.id}
    >
      {hasDocument ? (
        <div className="flex bg-muted/40 p-1 xl:hidden">
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
        <div className="shrink-0 bg-surface-muted/50 px-4 py-2">{toolbar}</div>
      ) : null}

      {!hasDocument ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[var(--workspace-result-reading-max-inline-size)] px-6 py-8">
            <div className="paper-report__notice">
              <div className="flex items-center gap-2">
                <Info
                  className="size-[var(--icon-size-md)] shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                <span>
                  全文文档当前未关联本地或线上
                  PDF，展示结构化研读结果与抽取结论。
                </span>
              </div>
            </div>

            {renderReport("paper-report")}
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
                defaultSize="58%"
                minSize="30%"
                className="h-full overflow-y-auto p-6"
              >
                {renderReport("paper-report-wide")}
              </ResizablePanel>
              <ResizableHandle
                id="report-paper-divider"
                aria-label="调整研究报告与论文原文的宽度"
                className="xw-resize-handle relative flex w-2 items-center justify-center transition-colors hover:bg-primary/10 focus-visible:bg-primary/10"
              />
              <ResizablePanel
                id="paper"
                defaultSize="42%"
                minSize="25%"
                className="h-full overflow-hidden bg-muted/10"
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
              {renderReport("paper-report-narrow")}
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
