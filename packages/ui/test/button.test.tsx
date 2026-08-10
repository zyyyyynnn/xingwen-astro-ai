import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button, buttonClassName } from "../src/button";

describe("Button", () => {
  it("renders children text", () => {
    render(<Button>开始演示</Button>);
    expect(
      screen.getByRole("button", { name: "开始演示" }),
    ).toBeInTheDocument();
  });

  it("defaults to type=button", () => {
    render(<Button>Click</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("applies the variant class", () => {
    render(<Button variant="secondary">Secondary</Button>);
    expect(screen.getByRole("button")).toHaveAttribute(
      "data-variant",
      "secondary",
    );
  });

  it("merges consumer className", () => {
    render(<Button className="custom">Custom</Button>);
    expect(screen.getByRole("button")).toHaveClass("custom", "xw-button");
  });

  it("preserves native focus and disabled interaction semantics", () => {
    const onClick = vi.fn();
    render(
      <>
        <Button onClick={onClick}>Enabled</Button>
        <Button onClick={onClick} disabled>
          Disabled
        </Button>
      </>,
    );

    const enabled = screen.getByRole("button", { name: "Enabled" });
    enabled.focus();
    expect(enabled).toHaveFocus();
    fireEvent.click(enabled);
    fireEvent.click(screen.getByRole("button", { name: "Disabled" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Disabled" })).toBeDisabled();
  });

  it("requires and exposes an accessible name for icon-only controls", () => {
    render(
      <Button size="icon" variant="ghost" aria-label="关闭">
        <svg aria-hidden="true" />
      </Button>,
    );

    expect(screen.getByRole("button", { name: "关闭" })).toHaveAttribute(
      "data-size",
      "icon",
    );
  });

  it("shares the reviewed button classes with source-adopted mechanics", () => {
    expect(
      buttonClassName({ variant: "ghost", size: "icon", className: "layout" }),
    ).toBe("xw-button xw-button--ghost xw-button--icon layout");
  });
});
