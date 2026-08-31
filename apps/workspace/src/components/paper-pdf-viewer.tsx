import { Button, buttonClassName, Input, Skeleton } from "@xingwen/ui";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Search,
  ZoomIn,
  ZoomOut,
} from "@xingwen/ui/icons";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import PdfjsWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
} from "react";

pdfjs.GlobalWorkerOptions.workerSrc = PdfjsWorkerUrl;

const PDF_LOAD_OPTIONS = { withCredentials: true };

export interface PaperPdfViewerHandle {
  /** Jump to an exact PDF page. `pageIndex` is 0-based. */
  jumpToPage(pageIndex: number): void;
}

export interface PaperPdfViewerProps {
  readonly src?: string | null;
  readonly className?: string;
  readonly ref?: Ref<PaperPdfViewerHandle>;
}

type FitMode = "width" | "page" | null;

function pageText(items: readonly unknown[]): string {
  return items
    .map((item) =>
      item && typeof item === "object" && "str" in item ? String(item.str) : "",
    )
    .filter(Boolean)
    .join(" ");
}

export function PaperPdfViewer({
  src,
  className = "",
  ref,
}: PaperPdfViewerProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const pendingPageRef = useRef<number | null>(null);
  const [documentProxy, setDocumentProxy] = useState<PDFDocumentProxy | null>(
    null,
  );
  const [pageNumber, setPageNumber] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [renderedPage, setRenderedPage] = useState<{
    readonly src: string;
    readonly pageNumber: number;
  } | null>(null);
  const [scale, setScale] = useState(1);
  const [fitMode, setFitMode] = useState<FitMode>("width");
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      setViewport({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const jumpToPage = useCallback(
    (pageIndex: number) => {
      const next = Math.max(0, Math.floor(pageIndex));
      if (numPages <= 0) {
        pendingPageRef.current = next;
        return;
      }
      setPageNumber(Math.min(next + 1, numPages));
    },
    [numPages],
  );

  useImperativeHandle(ref, () => ({ jumpToPage }), [jumpToPage]);

  const onLoadSuccess = (pdf: PDFDocumentProxy) => {
    setDocumentProxy(pdf);
    setNumPages(pdf.numPages);
    setRenderedPage(null);
    setLoadError(null);
    const pending = pendingPageRef.current;
    if (pending !== null) {
      pendingPageRef.current = null;
      setPageNumber(Math.min(pending + 1, pdf.numPages));
    } else {
      setPageNumber((current) => Math.min(Math.max(current, 1), pdf.numPages));
    }
  };

  const runSearch = async () => {
    const term = query.trim().toLocaleLowerCase();
    if (!term || !documentProxy || searching) return;
    setSearching(true);
    setSearchMessage(null);
    try {
      const order = Array.from(
        { length: documentProxy.numPages },
        (_, index) => ((pageNumber + index) % documentProxy.numPages) + 1,
      );
      for (const candidate of order) {
        const page = await documentProxy.getPage(candidate);
        const content = await page.getTextContent();
        if (pageText(content.items).toLocaleLowerCase().includes(term)) {
          setPageNumber(candidate);
          setSearchMessage(`已定位到第 ${candidate} 页`);
          return;
        }
      }
      setSearchMessage("未在论文全文中找到该内容");
    } finally {
      setSearching(false);
    }
  };

  if (!src) {
    return (
      <div
        className={`xw-pdf-viewer-empty flex h-full flex-col items-center justify-center p-6 text-center ${className}`}
        data-testid="paper-pdf-unavailable"
      >
        <p className="text-sm font-medium">全文当前不可用</p>
        <p className="mt-1 text-xs">研究报告与已保存证据仍可继续阅读。</p>
      </div>
    );
  }

  const pageWidth =
    fitMode === "width" && viewport.width > 0
      ? Math.max(280, viewport.width - 32)
      : undefined;
  const pageHeight =
    fitMode === "page" && viewport.height > 0
      ? Math.max(320, viewport.height - 32)
      : undefined;

  return (
    <section
      className={`xw-pdf-viewer-container flex h-full min-h-0 w-full flex-col ${className}`}
      data-testid="paper-pdf-viewer"
      data-num-pages={numPages}
      data-rendered-page={
        renderedPage?.src === src && renderedPage.pageNumber === pageNumber
          ? pageNumber
          : ""
      }
      aria-label="论文原文"
    >
      <div className="xw-pdf-toolbar">
        <Button
          variant="ghost"
          size="icon"
          aria-label="上一页"
          disabled={pageNumber <= 1}
          onClick={() => setPageNumber((current) => Math.max(1, current - 1))}
        >
          <ChevronLeft aria-hidden="true" />
        </Button>
        <span className="xw-pdf-toolbar__page-count">
          {numPages > 0 ? `${pageNumber} / ${numPages}` : "— / —"}
        </span>
        <Button
          variant="ghost"
          size="icon"
          aria-label="下一页"
          disabled={numPages === 0 || pageNumber >= numPages}
          onClick={() =>
            setPageNumber((current) => Math.min(numPages, current + 1))
          }
        >
          <ChevronRight aria-hidden="true" />
        </Button>
        <span className="xw-pdf-toolbar__divider" aria-hidden="true" />
        <Button
          variant="ghost"
          size="icon"
          aria-label="缩小"
          onClick={() => {
            setFitMode(null);
            setScale((current) => Math.max(0.5, current - 0.1));
          }}
        >
          <ZoomOut aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="放大"
          onClick={() => {
            setFitMode(null);
            setScale((current) => Math.min(3, current + 0.1));
          }}
        >
          <ZoomIn aria-hidden="true" />
        </Button>
        <Button
          variant={fitMode === "width" ? "secondary" : "ghost"}
          size="small"
          onClick={() => setFitMode("width")}
        >
          适合宽度
        </Button>
        <Button
          variant={fitMode === "page" ? "secondary" : "ghost"}
          size="small"
          onClick={() => setFitMode("page")}
        >
          适合页面
        </Button>
        <div className="xw-pdf-toolbar__search">
          <Search aria-hidden="true" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void runSearch();
            }}
            placeholder="搜索全文"
            aria-label="搜索论文全文"
          />
          <Button
            variant="secondary"
            size="icon"
            aria-label="搜索"
            disabled={searching || !query.trim()}
            onClick={() => void runSearch()}
          >
            <Search aria-hidden="true" />
          </Button>
          <a
            href={src}
            download
            className={buttonClassName({
              variant: "secondary",
              size: "icon",
            })}
            aria-label="下载论文原文"
          >
            <Download aria-hidden="true" />
          </a>
        </div>
      </div>
      {searchMessage ? (
        <p className="xw-pdf-viewer__status" role="status">
          {searchMessage}
        </p>
      ) : null}
      <div
        ref={viewportRef}
        className="xw-pdf-viewer__viewport min-h-0 flex-1 overflow-auto p-4"
      >
        <Document
          file={src}
          options={PDF_LOAD_OPTIONS}
          onLoadSuccess={onLoadSuccess}
          onLoadError={() => setLoadError("论文原文载入失败，请稍后重试。")}
          loading={
            <div className="mx-auto max-w-3xl" aria-busy="true">
              <Skeleton className="h-12 w-3/4 mb-2" />
              <Skeleton className="h-[var(--workspace-result-pdf-loading-block-size)] w-full" />
            </div>
          }
          error={
            <div className="xw-pdf-viewer__error mx-auto max-w-xl py-12 text-center text-sm">
              {loadError ?? "论文原文载入失败，请稍后重试。"}
            </div>
          }
        >
          <div data-testid="paper-pdf-page">
            <Page
              pageNumber={pageNumber}
              width={pageWidth}
              height={pageHeight}
              scale={fitMode === null ? scale : undefined}
              renderTextLayer
              renderAnnotationLayer
              onRenderSuccess={() => setRenderedPage({ src, pageNumber })}
              className="mx-auto shadow-sm"
            />
          </div>
        </Document>
      </div>
    </section>
  );
}
