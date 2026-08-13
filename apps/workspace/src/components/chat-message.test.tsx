import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatMessage } from "../../upstream/openhands/src/root";

describe("ChatMessage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("reports long-message truncation without entering a render loop", async () => {
    const runtimeErrors: string[] = [];
    vi.spyOn(console, "error").mockImplementation((value: unknown) => {
      runtimeErrors.push(String(value));
    });

    render(
      <ChatMessage type="user" message={"需要保留的长研究消息。".repeat(40)} />,
    );

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "展开完整研究消息" }),
      ).toBeVisible(),
    );
    expect(
      runtimeErrors.filter((message) =>
        message.includes("Maximum update depth exceeded"),
      ),
    ).toEqual([]);
  });
});
