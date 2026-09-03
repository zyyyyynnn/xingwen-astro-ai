import { QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { DomainEntityId, UtcIsoTimestamp } from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { ArtifactShareDialog } from "./artifact-share-dialog";

const id = (value: string) => value as DomainEntityId;
const timestamp = (value: string) => value as UtcIsoTimestamp;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ArtifactShareDialog", () => {
  it("creates a frozen current-result link and copies the workspace URL", async () => {
    const runtime = createTestRuntime();
    const create = vi
      .spyOn(runtime.repositories.shares, "create")
      .mockResolvedValue({
        id: id("share_01"),
        projectId: id("project_01"),
        title: "恒星参数",
        status: "active",
        redactionPolicy: "redacted_public_snapshot",
        artifactVersionIds: [id("version_01")],
        evidenceIds: [id("evidence_01")],
        createdAt: timestamp("2026-08-24T00:00:00Z"),
        expiresAt: timestamp("2026-08-31T00:00:00Z"),
        revokedAt: null,
        shareToken: "one-time-share-token",
        shareUrl: "/api/public/shares/one-time-share-token",
      });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ArtifactShareDialog
          runtime={runtime}
          projectId={id("project_01")}
          artifactVersionId={id("version_01")}
          artifactTitle="恒星参数"
          open
          onOpenChange={() => undefined}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "创建链接" }));

    await waitFor(() => expect(create).toHaveBeenCalledOnce());
    expect(create).toHaveBeenCalledWith(
      id("project_01"),
      expect.objectContaining({
        title: "恒星参数",
        artifactVersionIds: [id("version_01")],
        redactionPolicy: "redacted_public_snapshot",
      }),
    );
    const link = await screen.findByLabelText("分享链接");
    expect(link).toHaveValue(
      "http://localhost:3000/share/one-time-share-token",
    );

    fireEvent.click(screen.getByRole("button", { name: "复制链接" }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        "http://localhost:3000/share/one-time-share-token",
      ),
    );
    expect(screen.getByRole("status")).toHaveTextContent("已复制");
  });

  it("keeps the dialog actionable when link creation fails", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.shares, "create").mockRejectedValue(
      new Error("provider unavailable"),
    );

    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ArtifactShareDialog
          runtime={runtime}
          projectId={id("project_01")}
          artifactVersionId={id("version_01")}
          artifactTitle="恒星参数"
          open
          onOpenChange={() => undefined}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "创建链接" }));

    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(screen.queryByLabelText("分享链接")).not.toBeInTheDocument();
  });
});
