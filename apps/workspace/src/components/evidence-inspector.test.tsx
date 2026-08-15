import { QueryClientProvider } from "@tanstack/react-query";
import { asEntityId } from "@xingwen/domain";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { EvidenceInspector } from "./evidence-inspector";

afterEach(cleanup);

describe("EvidenceInspector", () => {
  it("loads the typed Evidence path and renders its locator without raw JSON", async () => {
    const runtime = createTestRuntime();
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <EvidenceInspector
          runtime={runtime}
          projectId={asEntityId("proj_01JEXAMPLE")}
          evidenceId={asEntityId("evd_01")}
          canGoBack={false}
          onBack={vi.fn()}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "证据核验" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("database_query")).toBeInTheDocument();
    expect(screen.getByText("qhash_01")).toBeInTheDocument();
    expect(screen.getAllByText("TOI-1234")).toHaveLength(2);
    expect(screen.queryByText(/"queryHash"/)).not.toBeInTheDocument();
  });
});
