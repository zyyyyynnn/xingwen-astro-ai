import { QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { NetworkError } from "@xingwen/data-access/errors";
import { asEntityId, CASE_KEY } from "@xingwen/domain";
import { afterEach, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { PaperFullTextForm } from "./paper-full-text-form";

afterEach(cleanup);

async function setup(isLive = true) {
  const runtime = createTestRuntime();
  const { id: projectId } = await runtime.repositories.projects.create({
    name: "Paper review",
    caseKey: CASE_KEY,
    idempotencyKey: "test-project",
  });
  const input = await runtime.repositories.researchInputs.create({
    projectId,
    type: "pdf",
    file: new Blob(["test document"]),
    filename: "paper.pdf",
    mimeType: "application/pdf",
    idempotencyKey: "test-upload",
  });
  render(
    <QueryClientProvider client={runtime.queryClient}>
      <PaperFullTextForm
        runtime={runtime}
        projectId={projectId}
        artifactVersionId={asEntityId("paper-collection")}
        candidateId={asEntityId("candidate-paper")}
        canonicalPaperId={asEntityId("doi:paper")}
        sourceUrl="https://publisher.example/article"
        isLive={isLive}
      />
    </QueryClientProvider>,
  );
  return { runtime, input };
}

function fillOpenAccess() {
  fireEvent.change(screen.getByLabelText("全文地址"), {
    target: { value: "https://publisher.example/article.pdf" },
  });
  fireEvent.change(screen.getByLabelText("许可或开放获取依据"), {
    target: { value: "CC BY 4.0" },
  });
}

it("submits through the application boundary and reuses the same action when retrying a failed acquisition", async () => {
  const { runtime, input } = await setup();
  const acquire = vi
    .spyOn(runtime.repositories.paperAcquisition, "acquireFullText")
    .mockRejectedValueOnce(new NetworkError("Connection interrupted"))
    .mockResolvedValueOnce(input);
  const invalidate = vi.spyOn(runtime.queryClient, "invalidateQueries");
  fillOpenAccess();
  fireEvent.click(screen.getByRole("button", { name: "获取并关联全文" }));
  expect(await screen.findByRole("alert")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "获取并关联全文" }));
  expect(await screen.findByRole("status")).toHaveTextContent("全文已关联");
  expect(acquire).toHaveBeenCalledTimes(2);
  expect(acquire.mock.calls[0]?.[0]).toEqual(acquire.mock.calls[1]?.[0]);
  expect(acquire.mock.calls[1]?.[0]).toMatchObject({
    candidateId: "candidate-paper",
    canonicalPaperId: "doi:paper",
    accessKind: "publisher_open_access",
    accessUrl: "https://publisher.example/article.pdf",
    evidenceUrl: "https://publisher.example/article",
    license: "CC BY 4.0",
  });
  expect(invalidate).toHaveBeenCalled();
});

it("locks pending controls and reports an unsupported input without claiming document evidence is available", async () => {
  const { runtime, input } = await setup();
  let finish: (() => void) | undefined;
  vi.spyOn(
    runtime.repositories.paperAcquisition,
    "acquireFullText",
  ).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = () => resolve({ ...input, status: "unsupported_processing" });
      }),
  );
  fillOpenAccess();
  fireEvent.click(screen.getByRole("button", { name: "获取并关联全文" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "正在关联全文…" }),
    ).toBeDisabled(),
  );
  expect(screen.getByLabelText("全文地址")).toBeDisabled();
  expect(screen.getByRole("combobox", { name: "开放来源" })).toBeDisabled();
  finish?.();
  expect(await screen.findByRole("status")).toHaveTextContent(
    "当前格式无法解析",
  );
  expect(
    screen.queryByText("全文已关联。重新分析后可查看文档证据。"),
  ).not.toBeInTheDocument();
});

it("keeps recorded demonstration data out of real acquisition", async () => {
  const { runtime } = await setup(false);
  const acquire = vi.spyOn(
    runtime.repositories.paperAcquisition,
    "acquireFullText",
  );
  expect(screen.getByRole("radio", { name: "开放全文链接" })).toBeDisabled();
  expect(screen.getByText("演示结果不执行真实全文获取。")).toBeVisible();
  expect(acquire).not.toHaveBeenCalled();
});
