import { QueryClientProvider } from "@tanstack/react-query";
import { asEntityId } from "@xingwen/domain";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { ResearchInputPanel } from "./research-input-panel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function renderPanel() {
  const runtime = createTestRuntime();
  const project = (await runtime.repositories.projects.list()).items[0];
  if (!project) throw new Error("Fixture project missing");
  render(
    <QueryClientProvider client={runtime.queryClient}>
      <ResearchInputPanel runtime={runtime} projectId={project.id} />
    </QueryClientProvider>,
  );
  return { runtime, project };
}

describe("ResearchInputPanel", () => {
  it("lists Project-owned inputs and creates accepted text without binding a Run", async () => {
    const { runtime, project } = await renderPanel();
    const create = vi.spyOn(runtime.repositories.researchInputs, "create");
    const bind = vi.spyOn(runtime.repositories.researchInputs, "bindToRun");

    expect(await screen.findByText("host-star-notes.txt")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("内容"), {
      target: { value: "TESS candidate notes" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加文本" }));

    const createdInput = (await screen.findByText("input.txt")).closest("li");
    if (createdInput === null) throw new Error("Created input row missing");
    expect(within(createdInput).getByText("已接收")).toBeInTheDocument();
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        projectId: project.id,
        type: "text",
        mimeType: "text/plain",
      }),
    );
    expect(bind).not.toHaveBeenCalled();
  });

  it("uploads XLSX and preserves Markdown as type=text with semantic MIME", async () => {
    const { runtime, project } = await renderPanel();
    const create = vi.spyOn(runtime.repositories.researchInputs, "create");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "文件" }), {
      button: 0,
      ctrlKey: false,
    });
    const fileInput = screen.getByLabelText("选择文件");
    const workbook = new File(["xlsx"], "targets.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    Object.defineProperty(workbook, "arrayBuffer", {
      value: vi.fn(async () => new TextEncoder().encode("xlsx").buffer),
    });
    fireEvent.change(fileInput, { target: { files: [workbook] } });
    fireEvent.click(screen.getByRole("button", { name: "上传文件" }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({ projectId: project.id, type: "xlsx" }),
      ),
    );

    const imageDataset = new File(["PK"], "training-images.zip", { type: "" });
    Object.defineProperty(imageDataset, "arrayBuffer", {
      value: vi.fn(async () => new TextEncoder().encode("PK").buffer),
    });
    fireEvent.change(fileInput, { target: { files: [imageDataset] } });
    fireEvent.click(screen.getByRole("button", { name: "上传文件" }));
    await waitFor(() =>
      expect(create).toHaveBeenLastCalledWith(
        expect.objectContaining({
          projectId: project.id,
          type: "image_dataset",
          filename: "training-images.zip",
          mimeType: null,
        }),
      ),
    );

    const markdown = new File(["# Notes"], "notes.markdown", {
      type: "text/x-markdown",
    });
    Object.defineProperty(markdown, "text", {
      value: vi.fn(async () => "# Notes"),
    });
    fireEvent.change(fileInput, { target: { files: [markdown] } });
    fireEvent.click(screen.getByRole("button", { name: "上传文件" }));
    await waitFor(() =>
      expect(create).toHaveBeenLastCalledWith(
        expect.objectContaining({
          projectId: project.id,
          type: "text",
          filename: "notes.markdown",
          mimeType: "text/x-markdown",
        }),
      ),
    );
  });

  it("renders unsupported and failed ingestion states with size and MIME", async () => {
    const runtime = createTestRuntime();
    const project = (await runtime.repositories.projects.list()).items[0];
    if (!project) throw new Error("Fixture project missing");
    vi.spyOn(
      runtime.repositories.researchInputs,
      "listByProject",
    ).mockResolvedValue([
      {
        id: asEntityId("input_unsupported"),
        type: "fits",
        filename: "cube.fits",
        mimeType: "application/fits",
        sizeBytes: 2048,
        status: "unsupported_processing",
        sourceType: "upload",
        sourceSnapshotId: null,
        contentHash: "hash",
        createdAt: "2026-08-14T00:00:00Z" as never,
      },
      {
        id: asEntityId("input_failed"),
        type: "json",
        filename: "bad.json",
        mimeType: "application/json",
        sizeBytes: 12,
        status: "failed_ingestion",
        sourceType: "upload",
        sourceSnapshotId: null,
        contentHash: "hash",
        createdAt: "2026-08-14T00:00:00Z" as never,
      },
    ]);
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ResearchInputPanel runtime={runtime} projectId={project.id} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("暂不支持处理")).toBeInTheDocument();
    expect(screen.getByText("入库失败")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
    expect(screen.getByText("application/fits")).toBeInTheDocument();
  });

  it("renders an empty state and a retryable list failure", async () => {
    const emptyRuntime = createTestRuntime();
    const project = (await emptyRuntime.repositories.projects.list()).items[0];
    if (!project) throw new Error("Fixture project missing");
    vi.spyOn(
      emptyRuntime.repositories.researchInputs,
      "listByProject",
    ).mockResolvedValue([]);
    const { unmount } = render(
      <QueryClientProvider client={emptyRuntime.queryClient}>
        <ResearchInputPanel runtime={emptyRuntime} projectId={project.id} />
      </QueryClientProvider>,
    );
    expect(
      await screen.findByText("当前 Project 尚无研究输入。"),
    ).toBeInTheDocument();
    unmount();

    const failedRuntime = createTestRuntime();
    vi.spyOn(
      failedRuntime.repositories.researchInputs,
      "listByProject",
    ).mockRejectedValue(new Error("offline"));
    render(
      <QueryClientProvider client={failedRuntime.queryClient}>
        <ResearchInputPanel runtime={failedRuntime} projectId={project.id} />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("button", { name: "重试" })).toBeEnabled();
  });
});
