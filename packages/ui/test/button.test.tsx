import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "../src/button";

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
    expect(screen.getByRole("button")).toHaveClass("xw-button--secondary");
  });

  it("merges consumer className", () => {
    render(<Button className="custom">Custom</Button>);
    expect(screen.getByRole("button")).toHaveClass("custom", "xw-button");
  });

  it("supports disabled state", () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
