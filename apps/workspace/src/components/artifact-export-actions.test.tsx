import { QueryClientProvider } from "@tanstack/react-query";
import { asEntityId } from "@xingwen/domain";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { ArtifactExportActions } from "./artifact-export-actions";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ArtifactExportActions", () => {
  it("creates, verifies, and downloads an export fixed to the selected version", async () => {
    const runtime = createTestRuntime();
    const project = (await runtime.repositories.projects.list()).items[0];
    if (!project) throw new Error("Fixture project missing");
    const repository = runtime.repositories.artifactExports;
    const create = vi.spyOn(repository, "create");
    const get = vi.spyOn(repository, "get");
    const download = vi.spyOn(repository, "download");
    const createObjectURL = vi.fn(() => "blob:artifact-export");
    const revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      () => undefined,
    );
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });

    const versionId = asEntityId("artv_dataset_01");
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ArtifactExportActions
          runtime={runtime}
          projectId={project.id}
          artifactVersionId={versionId}
          versionNumber={3}
          artifactKind="dataset"
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "导出 JSON" }));

    expect(await screen.findByRole("status")).toHaveTextContent("已生成 json");
    expect(create).toHaveBeenCalledWith(versionId, "json");
    expect(get).toHaveBeenCalledTimes(1);
    expect(download).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:artifact-export");
  });

  it("disables CSV when the fixed version is not a Dataset", async () => {
    const runtime = createTestRuntime();
    const project = (await runtime.repositories.projects.list()).items[0];
    if (!project) throw new Error("Fixture project missing");
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ArtifactExportActions
          runtime={runtime}
          projectId={project.id}
          artifactVersionId={asEntityId("artv_fdict_01")}
          versionNumber={1}
          artifactKind="field_dictionary"
        />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("button", { name: "导出 CSV" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "导出 JSON" })).toBeEnabled();
  });
});
