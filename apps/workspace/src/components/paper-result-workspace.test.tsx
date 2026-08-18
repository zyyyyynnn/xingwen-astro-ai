import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useImperativeHandle, type Ref } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PaperResultWorkspace } from "./paper-result-workspace";
import type { PaperPdfViewerHandle } from "./paper-pdf-viewer";

afterEach(cleanup);

const jumpToPage = vi.fn();

vi.mock("./paper-pdf-viewer", () => ({
  PaperPdfViewer: ({ ref }: { readonly ref?: Ref<PaperPdfViewerHandle> }) => {
    useImperativeHandle(ref, () => ({ jumpToPage }));
    return <div data-testid="mock-pdf-viewer">PDF</div>;
  },
}));

vi.mock("./paper-summary-renderer", () => ({
  PaperSummaryFullscreenRenderer: () => (
    <div data-testid="mock-paper-report">REPORT</div>
  ),
}));

const artifact = {} as never;
const version = {} as never;
const review = {} as never;

describe("PaperResultWorkspace narrow reading state", () => {
  // A pane carrying the `hidden` attribute computes an empty accessible
  // name, so the panes are located by their `aria-label` attribute instead
  // of a role/name query.
  function pane(label: string): HTMLElement {
    const element = screen
      .getByTestId("paper-result-workspace")
      .querySelector<HTMLElement>(`section[aria-label="${label}"]`);
    if (!element) {
      throw new Error(`Pane ${label} is not rendered.`);
    }
    return element;
  }

  it("keeps report and PDF panes mounted while switching tabs", () => {
    render(
      <PaperResultWorkspace
        artifact={artifact}
        version={version}
        review={review}
        pdfUrl="/api/research-inputs/source"
      />,
    );

    expect(screen.getAllByTestId("mock-paper-report")).toHaveLength(2);
    expect(screen.getAllByTestId("mock-pdf-viewer")).toHaveLength(2);

    const reportSection = pane("研究报告");
    const pdfSection = pane("论文原文");
    expect(reportSection).not.toHaveAttribute("hidden");
    expect(pdfSection).toHaveAttribute("hidden");

    // Radix tabs select on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "论文原文" }));
    expect(reportSection).toHaveAttribute("hidden");
    expect(pdfSection).not.toHaveAttribute("hidden");
    expect(screen.getAllByTestId("mock-paper-report")).toHaveLength(2);
    expect(screen.getAllByTestId("mock-pdf-viewer")).toHaveLength(2);
  });

  it("queues an evidence locator into both mounted PDF viewers", () => {
    const { rerender } = render(
      <PaperResultWorkspace
        artifact={artifact}
        version={version}
        review={review}
        pdfUrl="/api/research-inputs/source"
      />,
    );
    jumpToPage.mockClear();

    rerender(
      <PaperResultWorkspace
        artifact={artifact}
        version={version}
        review={review}
        pdfUrl="/api/research-inputs/source"
        requestedPage={{ pageIndex: 4, nonce: 1 }}
      />,
    );

    expect(jumpToPage).toHaveBeenCalledTimes(2);
    expect(jumpToPage).toHaveBeenNthCalledWith(1, 4);
    expect(jumpToPage).toHaveBeenNthCalledWith(2, 4);
    expect(pane("论文原文")).not.toHaveAttribute("hidden");
  });
});
