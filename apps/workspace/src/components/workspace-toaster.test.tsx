import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { toast, WorkspaceToaster } from "./workspace-toaster";

describe("WorkspaceToaster", () => {
  it("renders transient feedback with an accessible retry action", async () => {
    const retry = vi.fn();
    render(<WorkspaceToaster />);

    act(() => {
      toast.error("消息发送失败", {
        description: "网络暂不可用，请稍后重试",
        action: { label: "重试", onClick: retry },
      });
    });

    expect(await screen.findByText("消息发送失败")).toBeVisible();
    expect(screen.getByText("网络暂不可用，请稍后重试")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
